#!/usr/bin/env python
"""
Batch CTA-DEFACE pipeline

For each DICOM case directory under dicom-root-in:

    DICOM (original, possibly multiple series in folder)
        ↓
    NIfTI (single *_0000.nii.gz per case, nnUNet style)
        ↓
    CTA-DEFACE (CPU-only, via run_CTA-DEFACE.py)
        ↓
    Defaced NIfTI (chosen among CTA-DEFACE outputs)
        ↓
    DICOM (defaced, full header reuse, only PixelData changed)

Features
--------
- Handles ONE or MANY DICOM case folders:
      dicom-root-in/
          case1/
          case2/
          ...
  Output DICOM mirrors input structure under dicom-root-out.
- Optional nifti-root-out to keep defaced NIfTIs per case.
- Cleans per-case work directories (no stale nifti_out).
- Tolerates CTA-DEFACE exit code != 0 as long as it produced .nii files.
- Filters out mask NIfTIs and picks the defaced CT volume based on
  input basename (SeriesUID[_0000]) and naming.
- When a DICOM folder has multiple SeriesInstanceUIDs, chooses the series
  whose slice count best matches the NIfTI volume.
- NO anonymization: all patient/UID tags are reused, only PixelData changes.
"""

import os
import glob
import argparse
import subprocess
import shutil
from typing import Dict, List, Tuple

import numpy as np
import SimpleITK as sitk
import pydicom
from pydicom.uid import ImplicitVRLittleEndian
from pydicom.dataset import FileMetaDataset
import nibabel as nib

# -------------------------------
# Rotation mode for NIfTI->DICOM
# -------------------------------
# "none"     -> disable all heuristics (k=0 always)
# "auto90"   -> auto rotation across k={0,1,3} (no 180°)
# "auto_all" -> auto rotation across k={0,1,2,3}
#
# For safety in a mixed clinical / research repository, "none" or "auto90"
# are recommended. You can change this here if you like.
ROTATION_MODE = "auto90"   # "none" --> safest default


# -------------------------------------------------------------------------
# Generic helpers
# -------------------------------------------------------------------------

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def dicom_has_files(d: str) -> bool:
    """
    Heuristic: does this directory directly contain any DICOM files?

    - Only considers regular files (ignores subdirectories).
    - First looks for *.dcm.
    - Then (for files with no extension or odd extensions) tries
      pydicom.dcmread() on them.
    """
    d = os.path.abspath(d)

    # Fast path: *.dcm
    for p in glob.glob(os.path.join(d, "*.dcm")):
        if os.path.isfile(p):
            return True

    # Fallback: try reading other files as DICOM
    for p in glob.glob(os.path.join(d, "*")):
        if not os.path.isfile(p):
            continue
        try:
            pydicom.dcmread(p, stop_before_pixels=True, force=True)
            return True
        except Exception:
            continue

    return False


def find_case_dirs(root: str) -> List[str]:
    """
    Discover case directories under root.

    - If root itself contains DICOMs, treat it as one case.
    - Additionally include each immediate subdirectory that contains DICOMs.

    This covers both:
        dicom_root_in/series1/*.dcm
    and:
        dicom_root_in/patientA/series/*.dcm
    (one level down).
    """
    root = os.path.abspath(root)
    case_dirs = []

    # Root itself as a case dir
    if dicom_has_files(root):
        case_dirs.append(root)

    # Immediate subdirs
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isdir(p) and dicom_has_files(p):
            case_dirs.append(p)

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for d in case_dirs:
        if d not in seen:
            uniq.append(d)
            seen.add(d)
    return uniq


# -------------------------------------------------------------------------
# DICOM → NIfTI (nnUNet style)
# -------------------------------------------------------------------------

def dicom_to_nifti(dicom_dir: str, output_dir: str) -> str:
    """
    Convert the FIRST DICOM series in dicom_dir to a single NIfTI file
    named <SeriesInstanceUID>_0000.nii.gz in output_dir.
    """
    dicom_dir = os.path.abspath(dicom_dir)
    output_dir = os.path.abspath(output_dir)
    ensure_dir(output_dir)

    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(dicom_dir)
    if not series_ids:
        raise RuntimeError(f"No DICOM series found in {dicom_dir!r}")

    if len(series_ids) > 1:
        print(f"[dicom2nii] WARNING: found {len(series_ids)} series in {dicom_dir}, using the first one.")

    series_id = series_ids[0]
    fnames = reader.GetGDCMSeriesFileNames(dicom_dir, series_id)
    reader.SetFileNames(fnames)
    image = reader.Execute()

    base_name = series_id + "_0000"
    out_file = os.path.join(output_dir, base_name + ".nii.gz")
    sitk.WriteImage(image, out_file)
    print(f"[dicom2nii] Wrote NIfTI: {out_file}")
    return out_file


# -------------------------------------------------------------------------
# Run CTA-DEFACE (CPU) and collect outputs
# -------------------------------------------------------------------------

def run_cta_deface(nifti_in_dir: str, nifti_out_dir: str, extra_args=None) -> List[str]:
    """
    Call run_CTA-DEFACE.py with CPU-only settings.

    - Cleans nifti_out_dir before running.
    - Allows non-zero exit code.
    - Returns list of all .nii* files created in nifti_out_dir.
    """
    if extra_args is None:
        extra_args = []

    script_path = os.path.join(os.path.dirname(__file__), "run_CTA-DEFACE.py")
    if not os.path.isfile(script_path):
        raise RuntimeError(f"run_CTA-DEFACE.py not found at: {script_path}")

    # Make sure output folder is clean for this case
    if os.path.isdir(nifti_out_dir):
        shutil.rmtree(nifti_out_dir, ignore_errors=True)
    ensure_dir(nifti_out_dir)

    cmd = [os.sys.executable, script_path, "-i", nifti_in_dir, "-o", nifti_out_dir] + extra_args

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""  # force CPU

    print(f"[CTA-DEFACE] Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, env=env)
    if res.returncode != 0:
        print(f"[CTA-DEFACE] WARNING: exited with code {res.returncode}")

    nii_files = sorted(glob.glob(os.path.join(nifti_out_dir, "*.nii*")))
    if not nii_files:
        raise RuntimeError(f"CTA-DEFACE produced no NIfTI in {nifti_out_dir!r}")

    print(f"[CTA-DEFACE] Output NIfTIs: {nii_files}")
    return nii_files


# -------------------------------------------------------------------------
# Defaced NIfTI selection
# -------------------------------------------------------------------------

def find_defaced_nifti(nifti_out_dir: str, nifti_input_file: str) -> str:
    """
    Select the defaced CT NIfTI from CTA-DEFACE outputs.

    Rules:
    - Prefer files whose name contains 'defaced' (from patched run_CTA-DEFACE.py).
    - Otherwise, consider .nii* files whose names do NOT contain 'mask'.
    - Prefer basenames starting with the SeriesUID from nifti_input.
    - Additionally require that the chosen file is NOT pixel-wise identical
      to nifti_input; if identical, treat as defacing failure.

    If no suitable defaced NIfTI is found, raise RuntimeError.
    """
    nifti_out_dir = os.path.abspath(nifti_out_dir)
    nifti_input_file = os.path.abspath(nifti_input_file)

    in_base = os.path.basename(nifti_input_file)
    in_root = in_base
    for suffix in (".nii.gz", ".nii"):
        if in_root.endswith(suffix):
            in_root = in_root[: -len(suffix)]
    if in_root.endswith("_0000"):
        in_root = in_root[:-5]  # strip trailing "_0000"

    all_nii = sorted(glob.glob(os.path.join(nifti_out_dir, "*.nii*")))
    if not all_nii:
        raise RuntimeError(f"No NIfTI files found in {nifti_out_dir!r}")

    print(f"[defaced] All NIfTI outputs in {nifti_out_dir}: {all_nii}")

    # 1) Prefer explicit *_defaced.nii.gz if present
    defaced_named = [
        f for f in all_nii
        if "defaced" in os.path.basename(f).lower()
        and "mask" not in os.path.basename(f).lower()
    ]

    # 2) Otherwise, use non-mask files
    non_mask = [f for f in all_nii if "mask" not in os.path.basename(f).lower()]

    candidates = defaced_named if defaced_named else non_mask
    if not candidates:
        raise RuntimeError(
            f"CTA-DEFACE produced only mask NIfTIs in {nifti_out_dir!r}, "
            "no candidate defaced image. Check run_CTA-DEFACE.py for this case."
        )

    # Prefer those whose basename starts with input SeriesUID
    preferred = []
    for f in candidates:
        name = os.path.basename(f)
        root = name
        for suffix in (".nii.gz", ".nii"):
            if root.endswith(suffix):
                root = root[: -len(suffix)]
        if root.startswith(in_root):
            preferred.append(f)

    if preferred:
        candidates = preferred

    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple possible defaced NIfTIs for {nifti_input_file!r}: {candidates}"
        )

    chosen = candidates[0]
    print(f"[defaced] Candidate defaced NIfTI: {chosen}")

    # Ensure it is not identical to the original nifti_input
    try:
        nii_in = nib.load(nifti_input_file)
        nii_def = nib.load(chosen)
        arr_in = np.asarray(nii_in.get_fdata())
        arr_def = np.asarray(nii_def.get_fdata())
        if arr_in.shape == arr_def.shape:
            diff = np.abs(arr_in - arr_def)
            n_diff = int((diff != 0).sum())
            print(f"[defaced] Voxels changed between input and defaced: {n_diff}")
            if n_diff == 0:
                raise RuntimeError(
                    "Selected defaced NIfTI is pixel-wise identical to input. "
                    "Defacing appears not to have been applied for this case."
                )
        else:
            print("[defaced] Input and defaced shapes differ, assuming defacing applied.")
    except Exception as e:
        print(f"[defaced] WARNING: could not compare input/defaced NIfTIs: {e}")

    print(f"[defaced] Selected defaced NIfTI: {chosen}")
    return chosen


# -------------------------------------------------------------------------
# DICOM grouping & NIfTI → DICOM (full header reuse)
# -------------------------------------------------------------------------

def load_dicom_series_groups(dicom_dir: str) -> Dict[str, List[Tuple[str, pydicom.dataset.Dataset]]]:
    """
    Load all DICOMs in dicom_dir and group them by SeriesInstanceUID.

    Returns:
        {SeriesInstanceUID: [(filepath, dataset), ...], ...}, each list sorted
        by InstanceNumber or z-position.
    """
    dicom_dir = os.path.abspath(dicom_dir)

    # Collect each file path only once
    files_set = set()
    for ext in ("*.dcm", "*"):
        for p in glob.glob(os.path.join(dicom_dir, ext)):
            if os.path.isfile(p):
                files_set.add(p)

    files = sorted(files_set)

    groups: Dict[str, List[Tuple[str, pydicom.dataset.Dataset]]] = {}

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

    # Sort each series by InstanceNumber / z-position
    def sort_key(item):
        ds = item[1]
        if hasattr(ds, "InstanceNumber"):
            try:
                return int(ds.InstanceNumber)
            except Exception:
                pass
        ipp = getattr(ds, "ImagePositionPatient", None)
        if ipp is not None and len(ipp) == 3:
            try:
                return float(ipp[2])
            except Exception:
                pass
        return 0

    for suid, lst in groups.items():
        lst.sort(key=sort_key)

    return groups


def prepare_dataset_for_write(ds: pydicom.dataset.Dataset):
    """
    Ensure the Dataset has a non-ambiguous PixelData VR and a valid
    transfer syntax before saving with pydicom.
    """
    # Fix PixelData VR
    if "PixelData" in ds:
        bits = getattr(ds, "BitsAllocated", 16)
        ds["PixelData"].VR = "OB" if bits <= 8 else "OW"

    # Ensure file_meta exists
    if not hasattr(ds, "file_meta") or ds.file_meta is None:
        ds.file_meta = FileMetaDataset()

    # Force a safe transfer syntax if missing
    if not getattr(ds.file_meta, "TransferSyntaxUID", None):
        ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian

    # Keep dataset flags consistent with transfer syntax
    if ds.file_meta.TransferSyntaxUID == ImplicitVRLittleEndian:
        ds.is_implicit_VR = True
        ds.is_little_endian = True


def _determine_best_rotation(slice_def: np.ndarray,
                             slice_dcm: np.ndarray,
                             mode: str = "none") -> int:
    """
    Determine best rotation (np.rot90(k)) for matching defaced NIfTI
    to original DICOM. Controlled by ROTATION_MODE:

        "none"     -> always return k=0
        "auto90"   -> search k in {0,1,3}
        "auto_all" -> search k in {0,1,2,3}

    Returns:
        k = 0,1,2,3
    """
    if mode == "none":
        print("[rot-test] ROTATION_MODE=none → k=0")
        return 0

    if mode == "auto90":
        allowed_ks = [0, 1, 3]       # forbid 180°
    elif mode == "auto_all":
        allowed_ks = [0, 1, 2, 3]    # full brute force
    else:
        print(f"[rot-test] Invalid mode='{mode}', using k=0.")
        return 0

    sd = slice_def.astype(np.float32)
    so = slice_dcm.astype(np.float32)
    if sd.shape != so.shape:
        print("[rot-test] Slice shapes differ; returning k=0.")
        return 0

    errors = {}
    for k in allowed_ks:
        cand = np.rot90(sd, k=k)
        if cand.shape != so.shape:
            continue
        diff = so - cand
        err = float(np.mean(diff * diff))
        errors[k] = err

    if not errors:
        print("[rot-test] No valid rotations, defaulting to k=0.")
        return 0

    print(f"[rot-test] allowed_ks={allowed_ks}, errors={errors}")
    best_k = min(errors, key=errors.get)
    print(f"[rot-test] ROTATION_MODE={mode} → chosen k={best_k}")
    return best_k


def nifti_to_dicom_fullref(nifti_file: str, ref_dicom_dir: str, output_dir: str):
    """
    Convert NIfTI back to DICOM using a reference DICOM series, reusing FULL headers.

    - Groups ref_dicom_dir by SeriesInstanceUID.
    - Finds the series whose slice count matches the NIfTI volume
      along dim 0 or dim 2 (after possible reorientation).
    - Reuses patient/study/series/instance UIDs and all metadata.
    - Only PixelData is replaced slice by slice.

    If the slice counts do not match exactly, updates only the overlapping
    number of slices and leaves extra DICOM slices unchanged.

    Rotation behaviour is controlled by ROTATION_MODE.
    """
    nifti_file = os.path.abspath(nifti_file)
    ref_dicom_dir = os.path.abspath(ref_dicom_dir)
    output_dir = os.path.abspath(output_dir)
    ensure_dir(output_dir)

    print(f"[nii2dicom] NIfTI: {nifti_file}")
    print(f"[nii2dicom] Ref DICOM dir: {ref_dicom_dir}")

    nii = nib.load(nifti_file)
    data = nii.get_fdata()
    arr = np.asarray(data)

    if arr.ndim != 3:
        raise RuntimeError("Only 3D NIfTI volumes are supported.")

    print("[nii2dicom] NIfTI shape:", arr.shape)

    groups = load_dicom_series_groups(ref_dicom_dir)

    dim0, dim2 = arr.shape[0], arr.shape[2]
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
        chosen_dim_index = 0
        chosen_suid, chosen_list = candidates_dim0[0]
    else:
        print("[nii2dicom] WARNING: no exact slice count match, choosing closest series.")
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

        n_slices = len(best_list)
        chosen_dim_index = 0 if abs(n_slices - dim0) <= abs(n_slices - dim2) else 2
        chosen_suid = best_suid
        chosen_list = best_list

    n_slices_ref = len(chosen_list)
    print("[nii2dicom] Using SeriesInstanceUID:", chosen_suid)
    print("[nii2dicom] Reference slices:", n_slices_ref)
    print("[nii2dicom] Matching along NIfTI dim index:", chosen_dim_index)

    # Reorient NIfTI so slices are first dimension
    if chosen_dim_index == 0:
        arr_slices_first = arr
    else:
        arr_slices_first = np.moveaxis(arr, 2, 0)

    n_slices_nifti = arr_slices_first.shape[0]

    if n_slices_nifti != n_slices_ref:
        print(
            f"[nii2dicom] WARNING: NIfTI slices ({n_slices_nifti}) "
            f"!= DICOM slices ({n_slices_ref}). "
            "Will update only the overlapping subset."
        )

    n_slices_update = min(n_slices_nifti, n_slices_ref)
    print(f"[nii2dicom] Updating first {n_slices_update} slices with defaced data.")

    # Match dtype of reference pixel data
    sample_ref = pydicom.dcmread(chosen_list[0][0])
    if hasattr(sample_ref, "pixel_array"):
        ref_dtype = sample_ref.pixel_array.dtype
        sample_orig_slice = sample_ref.pixel_array
    else:
        ref_dtype = np.int16
        sample_orig_slice = None

    arr_slices_first = arr_slices_first.astype(ref_dtype)

    # Determine rotation; always define best_k
    if sample_orig_slice is not None:
        idx_mid = 0 if n_slices_update == 1 else n_slices_update // 2
        sample_def_slice = arr_slices_first[idx_mid]
        best_k = _determine_best_rotation(
            sample_def_slice, sample_orig_slice, mode=ROTATION_MODE
        )
    else:
        best_k = 0
        print("[rot-test] No sample_orig_slice; defaulting best_k=0")

    # 1) Update overlapping slices
    for (src_path, ds_ref), slice_data in zip(
        chosen_list[:n_slices_update],
        arr_slices_first[:n_slices_update]
    ):
        ds = ds_ref  # full header reuse
        slice_arr = np.asarray(slice_data)

        # Apply chosen rotation
        slice_arr = np.rot90(slice_arr, k=best_k)

        if slice_arr.shape != (ds.Rows, ds.Columns):
            raise RuntimeError(
                f"Slice from NIfTI has shape {slice_arr.shape}, expected "
                f"({ds.Rows}, {ds.Columns})."
            )

        ds.PixelData = slice_arr.tobytes()
        prepare_dataset_for_write(ds)
        out_name = os.path.join(output_dir, os.path.basename(src_path))
        ds.save_as(out_name)

    # 2) Copy remaining slices unchanged (if any)
    if n_slices_ref > n_slices_update:
        print(f"[nii2dicom] Copying remaining {n_slices_ref - n_slices_update} slices unchanged.")
        for src_path, ds_ref in chosen_list[n_slices_update:]:
            prepare_dataset_for_write(ds_ref)
            out_name = os.path.join(output_dir, os.path.basename(src_path))
            ds_ref.save_as(out_name)

    print(f"[nii2dicom] Wrote {n_slices_ref} DICOM slices to {output_dir}")


# -------------------------------------------------------------------------
# Per-case pipeline
# -------------------------------------------------------------------------

def process_case(case_dicom_dir: str,
                 root_in: str,
                 root_out_dicom: str,
                 root_out_nifti: str,
                 work_root: str,
                 extra_args=None):
    """Run full pipeline for a single DICOM case directory."""
    rel = os.path.relpath(case_dicom_dir, root_in)
    case_label = rel.replace(os.sep, "__")

    print("\n==============================")
    print(f"[case] {rel}")
    print("==============================")

    # Working dirs for this case
    work_dir = os.path.join(work_root, case_label)
    nifti_in_dir = os.path.join(work_dir, "nifti_in")
    nifti_out_dir = os.path.join(work_dir, "nifti_out")

    # Fresh work dir
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)
    ensure_dir(nifti_in_dir)
    ensure_dir(nifti_out_dir)

    # Output DICOM dir mirrors relative structure
    dicom_out_dir = os.path.join(root_out_dicom, rel)
    ensure_dir(dicom_out_dir)

    # Final NIfTI dir (optional)
    nifti_final_dir = None
    if root_out_nifti is not None:
        nifti_final_dir = os.path.join(root_out_nifti, rel)
        ensure_dir(nifti_final_dir)

    # 1) DICOM → NIfTI
    print("[step 1] DICOM -> NIfTI")
    nifti_input = dicom_to_nifti(case_dicom_dir, nifti_in_dir)

    # 2) CTA-DEFACE
    print("[step 2] CTA-DEFACE (CPU)")
    run_cta_deface(nifti_in_dir, nifti_out_dir, extra_args=extra_args)

    # 3) Select defaced NIfTI
    print("[step 3] Select defaced NIfTI")
    defaced_nifti = find_defaced_nifti(nifti_out_dir, nifti_input)

    if nifti_final_dir is not None:
        target = os.path.join(nifti_final_dir, os.path.basename(defaced_nifti))
        shutil.copy2(defaced_nifti, target)
        print(f"[case] Copied defaced NIfTI to {target}")

    # 4) NIfTI → DICOM
    print("[step 4] NIfTI -> DICOM")
    nifti_to_dicom_fullref(defaced_nifti, case_dicom_dir, dicom_out_dir)

    print(f"[case] Done: {rel}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Batch CTA-DEFACE pipeline: DICOM dirs -> defaced NIfTI + DICOM (full header reuse)."
    )
    ap.add_argument(
        "-i", "--dicom-root-in", required=True,
        help="Root input folder containing DICOM case directories (or a single DICOM dir)."
    )
    ap.add_argument(
        "-o", "--dicom-root-out", required=True,
        help="Root output folder for defaced DICOM directories (mirrors structure of dicom-root-in)."
    )
    ap.add_argument(
        "--nifti-root-out", default=None,
        help="Optional root folder to store defaced NIfTIs per case (mirrors structure)."
    )
    ap.add_argument(
        "-w", "--work-root", default="work_deface_batch",
        help="Working directory root for intermediate files."
    )
    ap.add_argument(
        "--cta-extra-args", nargs=argparse.REMAINDER,
        help="Extra args passed to run_CTA-DEFACE.py after -i/-o."
    )

    args = ap.parse_args()

    root_in = os.path.abspath(args.dicom_root_in)
    root_out_dicom = os.path.abspath(args.dicom_root_out)
    root_out_nifti = os.path.abspath(args.nifti_root_out) if args.nifti_root_out else None
    work_root = os.path.abspath(args.work_root)

    ensure_dir(root_out_dicom)
    if root_out_nifti is not None:
        ensure_dir(root_out_nifti)
    ensure_dir(work_root)

    cases = find_case_dirs(root_in)
    if not cases:
        raise SystemExit(f"No DICOM cases found under {root_in!r}")

    print(f"Found {len(cases)} case directory(ies) under {root_in}:")
    for c in cases:
        print("  -", os.path.relpath(c, root_in))

    extra_args = args.cta_extra_args if args.cta_extra_args is not None else []

    for case_dir in cases:
        process_case(case_dir, root_in, root_out_dicom, root_out_nifti, work_root, extra_args=extra_args)

    print("\nAll cases processed.")


if __name__ == "__main__":
    main()
