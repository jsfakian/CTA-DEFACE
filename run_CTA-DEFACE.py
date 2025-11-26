import argparse
import os
import subprocess
import sys
from pathlib import Path
import nibabel as nib
import numpy as np
import re
import torch
#
###----pre-processing step in run_CTA-DEFACE.py that:
#looks for *.nii.gz not ending in _0000.nii.gz
#creates a symlink (or copy) with the correct name so nnUNet is happy
#
import os
import glob
import shutil

def ensure_nnunet_naming(input_dir, suffix="_0000.nii.gz", copy=False):
    """
    For every *.nii.gz in input_dir that does NOT end with `_0000.nii.gz`,
    create a symlink (or copy) with the correct nnUNet-style name.

    input_dir: folder with your CTA/CT nifti files
    suffix:    modality suffix, default '_0000.nii.gz'
    copy:      if True, copy files instead of symlink (e.g. for NFS or Windows)
    """
    input_dir = os.path.abspath(input_dir)

    for path in glob.glob(os.path.join(input_dir, "*.nii.gz")):
        fname = os.path.basename(path)
        if fname.endswith(suffix):
            continue  # already nnUNet-compatible

        # Strip .nii.gz
        if fname.endswith(".nii.gz"):
            stem = fname[:-7]  # remove ".nii.gz"
        else:
            stem, _ = os.path.splitext(fname)

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


os.environ['nnUNet_results'] = './model'
os.environ['nnUNet_preprocessed'] = './model'
os.environ['nnUNet_raw'] = './model'
# export nnUNet_raw="./model"
# export nnUNet_preprocessed="./model"
# export nnUNet_results="./model"


def run_nnunet_inference(input_folder, output_folder):

    command = [
        "nnUNetv2_predict",
        "-i", input_folder,
        "-o", output_folder,
        "-d", "001",
        "-c", "3d_fullres",
        "-f", "all",
        "--disable_tta",           # disable test-time augmentation for speed
        "-device", "cpu"          # force GPU usage
    ]

    print("Executing command:", " ".join(command))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("Command output (if any):", result.stdout)
    print("Command error (if any):", result.stderr)
    if result.returncode != 0:
        print(f"Command failed with return code: {result.returncode}")
        sys.exit(1)

def save_mask(mask, affine, output_path):
    mask_nifti = nib.Nifti1Image(mask, affine)
    nib.save(mask_nifti, output_path)

def create_defaced_image(image_path, mask, output_path):

    # Load image and move to GPU
    image = nib.load(image_path)
    image_data_np = image.get_fdata()
    p10 = np.percentile(image_data_np, 10)

    image_tensor = torch.tensor(image_data_np, dtype=torch.float32, device="cuda")
    mask_tensor = torch.tensor(mask, dtype=torch.bool, device="cuda")

    # Deface using 10th percentile on GPU
    defaced_tensor = torch.where(mask_tensor, torch.tensor(p10, device="cuda"), image_tensor)

    # Move back to CPU and save
    defaced_np = defaced_tensor.cpu().numpy()
    defaced_nifti = nib.Nifti1Image(defaced_np, image.affine)
    nib.save(defaced_nifti, output_path)

def create_defaced_image(image_path, mask, output_path):
    import numpy as np
    import nibabel as nib

    image = nib.load(image_path)
    image_data = image.get_fdata()
    percentile_10th = np.percentile(image_data, 10)
    defaced_image = np.where(mask == 1, percentile_10th, image_data)
    defaced_nifti = nib.Nifti1Image(defaced_image, image.affine)
    nib.save(defaced_nifti, output_path)


def main(input_folder, output_folder):
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)


    run_nnunet_inference(str(input_path), str(output_path))



    for pred_file in output_path.glob("*.nii.gz"):
        case_id = pred_file
        mask_image = nib.load(pred_file)
        mask, affine = mask_image.get_fdata().astype(np.uint8), mask_image.affine
        print("...")
        print(case_id)

        mask_output_path = (re.sub(".nii.gz","",str(case_id)) + "_mask.nii.gz")
        save_mask(mask, affine, mask_output_path)


        original_image_path = re.sub("output","input",re.sub(".nii.gz","_0000.nii.gz",str(case_id)))
        defaced_output_path = (str(re.sub(".nii.gz","",str(case_id))) + "_defaced.nii.gz")
        create_defaced_image(str(original_image_path), mask, defaced_output_path)
        print(f"Defaced image saved to {defaced_output_path}")

if __name__ == "__main__":
    print(f"##############################################")
    print(f"Please cite: Mahmutoglu MA, Rastogi A, Schell M, Foltyn-Dumitru M, Baumgartner M, Maier-Hein KH, Deike-Hofmann K, Radbruch A, Bendszus M, Brugnara G, Vollmuth P. Deep learning-based defacing tool for CT angiography: CTA-DEFACE. Eur Radiol Exp. 2024 Oct 9;8(1):111. doi: 10.1186/s41747-024-00510-9.")
    print(f"##############################################")
    parser = argparse.ArgumentParser(description="Create segmentation and defaced images.")
    parser.add_argument("-i", "--input_folder", type=str, required=True, help="Path to input folder containing .nii.gz images")
    parser.add_argument("-o", "--output_folder", type=str, required=True, help="Path to output folder where results will be saved")

    args = parser.parse_args()
    main(args.input_folder, args.output_folder)
