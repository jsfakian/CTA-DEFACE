#!/usr/bin/env python
"""
Single-directory CTA-DEFACE pipeline:

    DICOM (original)
        ↓
    NIfTI (nnUNet naming, _0000.nii.gz)
        ↓
    CTA-DEFACE (nnUNetv2, CPU-only)
        ↓
    NIfTI (defaced)
        ↓
    DICOM (defaced, FULL header reuse)

- No anonymization: all DICOM headers (Study/Series/SOP UIDs, Patient tags) are preserved.
- Only PixelData is replaced.
- Use in controlled research context only.
"""

import os
import sys
import argparse
import glob
import subprocess

import numpy as np
import SimpleITK as sitk
import pydicom
import nibabel as nib


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def sorted_dicom_files(dicom_dir: str):
    """
    Return a sorted list of DICOM file paths in dicom_dir for a single series.
    Sorting uses InstanceNumber or z-position.
    """
    files = []
    for ext in ("*.dcm", "*"):
        files.extend(glob.glob(os.path.join(dicom_dir, ext)))

    ds_list = []
    for f in files:
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True, force=True)
            ds_list.append((f, ds))
        except Exception:
            continue

    if not ds_list:
        raise RuntimeError(f"No readable DICOM files found in {dicom_dir!r}")

    def sort_key(item):
        ds = item[1]
        if hasattr(ds, "InstanceNumber"):
            return int(ds.InstanceNumber)
        ipp = getattr(ds, "ImagePositionPatient", None)
        if ipp is not None and len(ipp) == 3:
            return float(ipp[2])
        return 0

    ds_list.sort(key=sort_key)
    return [f for f, _ in ds_list]

def load_dicom_series_groups(dicom_dir: str):
    """
    Load all DICOMs in dicom_dir and group them by SeriesInstanceUID.

    Returns:
        dict: {SeriesInstanceUID: [(filepath, dataset), ...], ...}
    """
    dicom_dir = os.path.abspath(dicom_dir)
    files = []
    for ext in ("*.dcm", "*"):
        files.extend(glob.glob(os.path.join(dicom_dir, ext)))

    groups = {}
    for f in files:
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True, force=True)
        except Exception:
            continue
        suid = getattr(ds, "SeriesInstanceUID", None)
        if suid is None:
            continue
        groups.setdefault(suid, []).append((f, ds))

    if not groups:
        raise RuntimeError(f"No readable DICOM series found in {dicom_dir!r}")

    # Sort each series by InstanceNumber or z-position
    def sort_key(item):
        ds = item[1]
        if hasattr(ds, "InstanceNumber"):
            return int(ds.InstanceNumber)
        ipp = getattr(ds, "ImagePositionPatient", None)
        if ipp is not None and len(ipp) == 3:
            return float(ipp[2])
        return 0

    for suid, lst in groups.items():
        lst.sort(key=sort_key)

    return groups

# -------------------------------------------------------------------------
# DICOM → NIfTI (nnUNet naming)
# -------------------------------------------------------------------------

def dicom_to_nifti(dicom_dir: str, output_dir: str) -> str:
    """
    Convert a single DICOM series in dicom_dir to a NIfTI (.nii.gz) file
    stored in output_dir, with nnUNet-style *_0000.nii.gz naming.

    Returns the full path to the NIfTI file.
    """
    dicom_dir = os.path.abspath(dicom_dir)
    output_dir = os.path.abspath(output_dir)
    ensure_dir(output_dir)

    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(dicom_dir)
    if not series_ids:
        raise RuntimeError(f"No DICOM series found in {dicom_dir!r}")

    if len(series_ids) > 1:
        print(f"[dicom2nii] WARNING: found {len(series_ids)} series. Using the first: {series_ids[0]}")

    series_id = series_ids[0]
    fnames = reader.GetGDCMSeriesFileNames(dicom_dir, series_id)
    reader.SetFileNames(fnames)

    # SimpleITK >= 2: Execute()
    image = reader.Execute()

    base_name = series_id + "_0000"
    output_file = os.path.join(output_dir, base_name + ".nii.gz")

    sitk.WriteImage(image, output_file)
    print(f"[dicom2nii] Wrote NIfTI: {output_file}")
    return output_file


# -------------------------------------------------------------------------
# Run CTA-DEFACE (CPU-only, tolerant to exit!=0)
# -------------------------------------------------------------------------

def run_cta_deface(nifti_in_dir: str, nifti_out_dir: str, extra_args=None):
    """
    Call run_CTA-DEFACE.py in CPU mode: -i nifti_in_dir -o nifti_out_dir

    NOTE:
    CTA-DEFACE may produce the defaced NIfTI and then crash in a
    post-processing step (e.g. looking for *_0000.nii.gz in the output).
    For our pipeline, we only care that a defaced NIfTI exists in the
    output directory, so we allow a non-zero return code as long as we
    see at least one NIfTI file there.
    """
    if extra_args is None:
        extra_args = []

    script_path = os.path.join(os.path.dirname(__file__), "run_CTA-DEFACE.py")
    if not os.path.isfile(script_path):
        raise RuntimeError(f"run_CTA-DEFACE.py not found at: {script_path}")

    cmd = [
        sys.executable,
        script_path,
        "-i", nifti_in_dir,
        "-o", nifti_out_dir,
    ] + extra_args

    env = os.environ.copy()
    # Force CPU
    env["CUDA_VISIBLE_DEVICES"] = ""

    print(f"[pipeline] Running CTA-DEFACE:\n  {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)  # no check=True

    if result.returncode != 0:
        print(f"[pipeline] WARNING: CTA-DEFACE exited with code {result.returncode}.")

    # Check that we actually have NIfTI output
    nii_files = sorted(
        glob.glob(os.path.join(nifti_out_dir, "*.nii.gz")) +
        glob.glob(os.path.join(nifti_out_dir, "*.nii"))
    )
    if not nii_files:
        raise RuntimeError(
            f"CTA-DEFACE did not produce any NIfTI output in {nifti_out_dir!r}."
        )

    print("[pipeline] CTA-DEFACE produced NIfTI output; continuing pipeline.")


def find_single_nii(folder: str) -> str:
    """
    Find the defaced NIfTI file in folder.

    CTA-DEFACE writes:
      - <case>.nii.gz          (defaced image)
      - <case>_mask.nii.gz     (mask)

    We want the image, not the mask.
    """
    all_nii = sorted(
        glob.glob(os.path.join(folder, "*.nii.gz")) +
        glob.glob(os.path.join(folder, "*.nii"))
    )
    if not all_nii:
        raise RuntimeError(f"No NIfTI files found in {folder!r}")

    # Prefer files that are NOT masks
    candidates = [f for f in all_nii if "_mask" not in os.path.basename(f)]

    if not candidates:
        raise RuntimeError(
            f"Only mask NIfTI(s) found in {folder!r}, cannot determine defaced image:\n  "
            + "\n  ".join(all_nii)
        )

    if len(candidates) > 1:
        raise RuntimeError(
            f"Expected one defaced NIfTI in {folder!r}, found multiple:\n  "
            + "\n  ".join(candidates)
        )

    return candidates[0]



# -------------------------------------------------------------------------
# NIfTI → DICOM (FULL header reuse)
# -------------------------------------------------------------------------

def nifti_to_dicom_fullref(nifti_file: str, ref_dicom_dir: str, output_dir: str):
    """
    Convert NIfTI back to DICOM using a reference DICOM series.

    - Groups all DICOMs in ref_dicom_dir by SeriesInstanceUID.
    - Chooses the series whose slice count matches one of the NIfTI dimensions
      (typically arr.shape[0] or arr.shape[2]).
    - REUSES FULL HEADERS of that series (no anonymization).
    - Only PixelData is replaced; filenames are preserved (per slice).

    WARNING:
    - This is intentionally NON-anonymizing.
    - Suitable only if you explicitly want to keep all identifiers.
    """
    nifti_file = os.path.abspath(nifti_file)
    ref_dicom_dir = os.path.abspath(ref_dicom_dir)
    output_dir = os.path.abspath(output_dir)
    ensure_dir(output_dir)

    print(f"[nii2dicom] NIfTI:  {nifti_file}")
    print(f"[nii2dicom] Ref:    {ref_dicom_dir}")
    print(f"[nii2dicom] Output: {output_dir}")

    # Load NIfTI
    nii = nib.load(nifti_file)
    data = nii.get_fdata()
    arr = np.asarray(data)

    if arr.ndim != 3:
        raise RuntimeError("Only 3D NIfTI volumes are supported.")

    print(f"[nii2dicom] NIfTI shape: {arr.shape}")

    # Load DICOM series groups
    groups = load_dicom_series_groups(ref_dicom_dir)

    # Candidate slice counts from NIfTI
    dim0 = arr.shape[0]
    dim2 = arr.shape[2]

    # Find series whose slice count matches dim0 or dim2
    candidates_dim0 = []
    candidates_dim2 = []
    for suid, lst in groups.items():
        n_slices = len(lst)
        if n_slices == dim0:
            candidates_dim0.append((suid, lst))
        if n_slices == dim2:
            candidates_dim2.append((suid, lst))

    chosen_dim_index = None
    chosen_suid = None
    chosen_list = None

    if candidates_dim0 and not candidates_dim2:
        chosen_dim_index = 0
        chosen_suid, chosen_list = candidates_dim0[0]
    elif candidates_dim2 and not candidates_dim0:
        chosen_dim_index = 2
        chosen_suid, chosen_list = candidates_dim2[0]
    elif candidates_dim0 and candidates_dim2:
        # both match (rare, but possible if dim0 == dim2)
        chosen_dim_index = 0
        chosen_suid, chosen_list = candidates_dim0[0]
    else:
        # No exact match; choose the series with the closest slice count
        print("[nii2dicom] WARNING: no series with slice count equal to "
              f"{dim0} or {dim2}. Choosing closest match.")
        best_suid = None
        best_list = None
        best_diff = None
        for suid, lst in groups.items():
            n_slices = len(lst)
            diff = min(abs(n_slices - dim0), abs(n_slices - dim2))
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_suid = suid
                best_list = lst
        if best_suid is None:
            raise RuntimeError("Could not select any DICOM series.")
        # Decide which dimension is closer
        n_slices = len(best_list)
        if abs(n_slices - dim0) <= abs(n_slices - dim2):
            chosen_dim_index = 0
        else:
            chosen_dim_index = 2
        chosen_suid = best_suid
        chosen_list = best_list

    n_slices_ref = len(chosen_list)
    print(f"[nii2dicom] Using SeriesInstanceUID: {chosen_suid}")
    print(f"[nii2dicom] Reference slices (chosen series): {n_slices_ref}")
    print(f"[nii2dicom] Matching along NIfTI dim index: {chosen_dim_index}")

    # Re-orient NIfTI so slices are first dimension
    if chosen_dim_index == 0:
        arr_slices_first = arr
    elif chosen_dim_index == 2:
        arr_slices_first = np.moveaxis(arr, 2, 0)  # [y,x,z] -> [z,y,x]
    else:
        raise RuntimeError("Internal error: invalid chosen_dim_index.")

    if arr_slices_first.shape[0] != n_slices_ref:
        raise RuntimeError(
            f"NIfTI slice count {arr_slices_first.shape[0]} does not "
            f"match chosen DICOM series slice count {n_slices_ref}"
        )

    # Match dtype with reference pixel data
    sample_ref = pydicom.dcmread(chosen_list[0][0])
    if hasattr(sample_ref, "pixel_array"):
        ref_dtype = sample_ref.pixel_array.dtype
    else:
        ref_dtype = np.int16

    arr_slices_first = arr_slices_first.astype(ref_dtype)

    # Replace pixel data slice-by-slice, preserving headers and filenames
    for (src_path, ds_ref), slice_data in zip(chosen_list, arr_slices_first):
        ds = ds_ref  # full header reuse

        slice_arr = np.asarray(slice_data)
        if slice_arr.shape != (ds.Rows, ds.Columns):
            raise RuntimeError(
                f"Slice from NIfTI has shape {slice_arr.shape}, expected "
                f"({ds.Rows}, {ds.Columns}) from DICOM."
            )

        ds.PixelData = slice_arr.tobytes()

        out_name = os.path.join(output_dir, os.path.basename(src_path))
        ds.save_as(out_name)

    print(f"[nii2dicom] Wrote {len(chosen_list)} DICOM slices to {output_dir}")


# -------------------------------------------------------------------------
# Main pipeline
# -------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Single-directory CTA-DEFACE pipeline: "
                    "DICOM → NIfTI → CTA-DEFACE → NIfTI → DICOM (full header reuse)."
    )
    parser.add_argument(
        "-i", "--dicom-dir", required=True,
        help="Input DICOM directory containing a single series."
    )
    parser.add_argument(
        "-o", "--dicom-out", required=True,
        help="Output DICOM directory for defaced series."
    )
    parser.add_argument(
        "-w", "--work-dir", default="work_deface_single",
        help="Working directory for intermediate NIfTI files (default: work_deface_single)."
    )
    parser.add_argument(
        "--keep-intermediate", action="store_true",
        help="Keep intermediate NIfTI files (default: delete them)."
    )
    parser.add_argument(
        "--cta-extra-args", nargs=argparse.REMAINDER,
        help="Extra args passed directly to run_CTA-DEFACE.py after -i/-o."
    )

    args = parser.parse_args()

    dicom_dir = os.path.abspath(args.dicom_dir)
    dicom_out = os.path.abspath(args.dicom_out)
    work_dir = os.path.abspath(args.work_dir)

    ensure_dir(work_dir)
    nifti_in_dir = os.path.join(work_dir, "nifti_in")
    nifti_out_dir = os.path.join(work_dir, "nifti_out")
    ensure_dir(nifti_in_dir)
    ensure_dir(nifti_out_dir)

    print("=== CTA-DEFACE Single-Dir Pipeline (FULL DICOM re-reference) ===")
    print(f"Input DICOM dir:   {dicom_dir}")
    print(f"Output DICOM dir:  {dicom_out}")
    print(f"Work dir:          {work_dir}")
    print()

    # 1) DICOM → NIfTI
    print("[1/4] Converting DICOM → NIfTI...")
    nifti_input_file = dicom_to_nifti(dicom_dir, nifti_in_dir)
    print(f"[1/4] NIfTI for CTA-DEFACE: {nifti_input_file}")
    print()

    # 2) CTA-DEFACE (CPU-only)
    print("[2/4] Running CTA-DEFACE (CPU-only)...")
    extra_args = args.cta_extra_args if args.cta_extra_args is not None else []
    run_cta_deface(nifti_in_dir, nifti_out_dir, extra_args=extra_args)
    print()

    # 3) Defaced NIfTI
    print("[3/4] Locating defaced NIfTI...")
    nifti_defaced = find_single_nii(nifti_out_dir)
    print(f"[3/4] Defaced NIfTI: {nifti_defaced}")
    print()

    # 4) NIfTI → DICOM (full header reuse)
    print("[4/4] Converting defaced NIfTI → DICOM (full header reuse)...")
    nifti_to_dicom_fullref(nifti_defaced, dicom_dir, dicom_out)
    print("[4/4] Defaced DICOM series created.")
    print()

    # Cleanup
    if not args.keep_intermediate:
        import shutil
        print("[cleanup] Removing working directory with intermediate files.")
        shutil.rmtree(work_dir, ignore_errors=True)
    else:
        print(f"[cleanup] Keeping intermediate files in: {work_dir}")

    print("=== Pipeline complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
