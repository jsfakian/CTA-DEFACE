#!/usr/bin/env python

import argparse
import os
import subprocess
import sys
from pathlib import Path
import glob
import shutil
import re

import nibabel as nib
import numpy as np

#
# nnUNet environment
#
os.environ["nnUNet_results"] = "./model"
os.environ["nnUNet_preprocessed"] = "./model"
os.environ["nnUNet_raw"] = "./model"


# -------------------------------------------------------------------------
# Helper: ensure nnUNet-style naming
# -------------------------------------------------------------------------
def ensure_nnunet_naming(input_dir, suffix="_0000.nii.gz", copy=False):
    """
    For every *.nii.gz in input_dir that does NOT end with `_0000.nii.gz`,
    create a symlink (or copy) with the correct nnUNet-style name.

    Example:
        CTA.nii.gz -> CTA_0000.nii.gz

    This makes nnUNet happy when using -i <folder> mode.
    """
    input_dir = os.path.abspath(input_dir)

    for path in glob.glob(os.path.join(input_dir, "*.nii.gz")):
        fname = os.path.basename(path)
        if fname.endswith(suffix):
            continue  # already nnUNet-compatible

        # Strip .nii.gz
        stem = fname[:-7]  # remove ".nii.gz"
        new_fname = stem + suffix
        new_path = os.path.join(input_dir, new_fname)

        if os.path.exists(new_path):
            # Don't overwrite if the correct file already exists
            continue

        if copy:
            shutil.copy2(path, new_path)
        else:
            # symlink relative path (works best on Linux)
            os.symlink(fname, new_path)

        print(f"[nnUNet rename] {fname} -> {new_fname}")


# -------------------------------------------------------------------------
# nnUNet inference
# -------------------------------------------------------------------------
def run_nnunet_inference(input_folder, output_folder):
    """
    Run nnUNetv2_predict (CPU-only) on all cases in input_folder.

    NOTE: This function will exit with non-zero status if nnUNet fails.
    In your external pipeline, you may choose to ignore this and just
    inspect which outputs exist.
    """
    command = [
        "nnUNetv2_predict",
        "-i",
        input_folder,
        "-o",
        output_folder,
        "-d",
        "001",
        "-c",
        "3d_fullres",
        "-f",
        "all",
        "--disable_tta",  # disable test-time augmentation for speed
        "-device",
        "cpu",  # force CPU
    ]

    print("Executing command:", " ".join(command))
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    print("Command output (if any):", result.stdout)
    print("Command error (if any):", result.stderr)
    if result.returncode != 0:
        print(f"Command failed with return code: {result.returncode}")
        # For standalone use, we exit non-zero. In the batch pipeline, this
        # is usually ignored and only the presence of output files matters.
        sys.exit(result.returncode)


# -------------------------------------------------------------------------
# Save mask
# -------------------------------------------------------------------------
def save_mask(mask, affine, output_path):
    mask_nifti = nib.Nifti1Image(mask, affine)
    nib.save(mask_nifti, output_path)


# -------------------------------------------------------------------------
# Create defaced image (CPU)
# -------------------------------------------------------------------------
def create_defaced_image(image_path, mask, output_path):
    """
    Apply defacing using a binary mask on the CPU.

    - image_path: original CT/CTA NIfTI
    - mask: numpy array (same shape), 1 where face / region to remove is
    - output_path: where to save defaced NIfTI

    Defacing strategy: voxels where mask==1 are set to the 10th percentile
    of the original intensities.
    """
    image = nib.load(image_path)
    image_data = image.get_fdata()
    percentile_10th = np.percentile(image_data, 10)

    # Create boolean mask
    mask_bool = mask.astype(bool)

    defaced_image = np.where(mask_bool, percentile_10th, image_data)
    defaced_nifti = nib.Nifti1Image(defaced_image, image.affine, image.header)
    nib.save(defaced_nifti, output_path)


# -------------------------------------------------------------------------
# Main processing
# -------------------------------------------------------------------------
def main(input_folder, output_folder):
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # Make sure input NIfTIs follow nnUNet naming convention (case_0000.nii.gz)
    ensure_nnunet_naming(str(input_path), suffix="_0000.nii.gz", copy=False)

    # Run nnUNetv2 segmentation
    run_nnunet_inference(str(input_path), str(output_path))

    # For each nnUNet prediction, create:
    #   - case_mask.nii.gz
    #   - case_defaced.nii.gz
    # and (optionally) remove the raw prediction case.nii.gz
    for pred_file in sorted(output_path.glob("*.nii.gz")):
        # Skip any files we ourselves already created
        if pred_file.name.endswith("_mask.nii.gz") or pred_file.name.endswith("_defaced.nii.gz"):
            continue

    # pred_file.name is something like "1.2.840....885.nii.gz"
    name = pred_file.name
    if name.endswith(".nii.gz"):
        case_root = name[:-7]  # strip ".nii.gz"
    elif name.endswith(".nii"):
        case_root = name[:-4]  # strip ".nii"
    else:
        # Fallback: Path.stem (last suffix only)
        case_root = pred_file.stem

    print("...")
    print(f"[run_CTA-DEFACE] Processing nnUNet prediction: {pred_file}")
    print(f"[run_CTA-DEFACE] Case root: {case_root}")

    # Load nnUNet prediction as mask
    mask_image = nib.load(pred_file)
    mask_data = mask_image.get_fdata()
    mask = (mask_data > 0).astype(np.uint8)
    affine = mask_image.affine

    # Save explicit mask file
    mask_output_path = output_path / f"{case_root}_mask.nii.gz"
    save_mask(mask, affine, str(mask_output_path))
    print(f"[run_CTA-DEFACE] Saved mask: {mask_output_path}")

    # Original CT/CTA is assumed to be in input_path with "_0000.nii.gz"
    original_image_path = input_path / f"{case_root}_0000.nii.gz"
    if not original_image_path.is_file():
        print(
            f"[run_CTA-DEFACE] WARNING: original image not found: {original_image_path}. "
            "Skipping defaced image for this case."
        )
    else:
        defaced_output_path = output_path / f"{case_root}_defaced.nii.gz"
        create_defaced_image(str(original_image_path), mask, str(defaced_output_path))
        print(f"[run_CTA-DEFACE] Defaced image saved to {defaced_output_path}")

    # Optional: remove the raw nnUNet prediction (case.nii.gz) to avoid confusion
    try:
        pred_file.unlink()
        print(f"[run_CTA-DEFACE] Removed raw nnUNet prediction: {pred_file}")
    except OSError as e:
        print(f"[run_CTA-DEFACE] WARNING: could not remove {pred_file}: {e}")



# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------
if __name__ == "__main__":
    print("##############################################")
    print(
        "Please cite: Mahmutoglu MA, Rastogi A, Schell M, Foltyn-Dumitru M, "
        "Baumgartner M, Maier-Hein KH, Deike-Hofmann K, Radbruch A, Bendszus M, "
        "Brugnara G, Vollmuth P. Deep learning-based defacing tool for CT "
        "angiography: CTA-DEFACE. Eur Radiol Exp. 2024 Oct 9;8(1):111. "
        "doi: 10.1186/s41747-024-00510-9."
    )
    print("##############################################")

    parser = argparse.ArgumentParser(
        description="Create segmentation masks and defaced images using nnUNetv2."
    )
    parser.add_argument(
        "-i",
        "--input_folder",
        type=str,
        required=True,
        help="Path to input folder containing .nii.gz images",
    )
    parser.add_argument(
        "-o",
        "--output_folder",
        type=str,
        required=True,
        help="Path to output folder where results will be saved",
    )

    args = parser.parse_args()
    main(args.input_folder, args.output_folder)
