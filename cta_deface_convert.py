#!/usr/bin/env python
"""
CTA-DEFACE conversion helper:
- DICOM -> NIfTI (nnUNet-compatible naming)
- NIfTI -> DICOM (using reference DICOM for metadata)

Requires:
    SimpleITK
    pydicom
    nibabel
    numpy
"""

import os
import sys
import argparse
import glob
from typing import List

import numpy as np
import SimpleITK as sitk
import pydicom
from pydicom.uid import generate_uid
import nibabel as nib


# -------------------------------------------------------------------------
# Utility helpers
# -------------------------------------------------------------------------

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def sorted_dicom_files(dicom_dir: str) -> List[str]:
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

    # sort by InstanceNumber or ImagePositionPatient (z)
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


# -------------------------------------------------------------------------
# DICOM -> NIfTI
# -------------------------------------------------------------------------

def dicom_to_nifti(input_dir: str, output_path: str, nnunet_style: bool = True):
    """
    Convert a single DICOM series in input_dir to a NIfTI (.nii.gz) file.
    """

    input_dir = os.path.abspath(input_dir)

    # Detect series with SimpleITK
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(input_dir)
    if not series_ids:
        raise RuntimeError(f"No DICOM series found in {input_dir!r}")

    if len(series_ids) > 1:
        print(f"[dicom2nii] WARNING: found {len(series_ids)} series. Using the first one: {series_ids[0]}")

    series_id = series_ids[0]
    fnames = reader.GetGDCMSeriesFileNames(input_dir, series_id)
    reader.SetFileNames(fnames)

    # ✔ FIX HERE:
    image = reader.Execute()

    # Prepare output path
    if os.path.isdir(output_path) or output_path.endswith(os.sep):
        ensure_dir(output_path)
        base_name = series_id
        if nnunet_style:
            base_name += "_0000"
        output_file = os.path.join(output_path, base_name + ".nii.gz")
    else:
        ensure_dir(os.path.dirname(output_path))
        output_file = output_path
        if nnunet_style and not output_file.endswith("_0000.nii.gz"):
            root = output_file[:-7] if output_file.endswith(".nii.gz") else output_file
            output_file = root + "_0000.nii.gz"

    sitk.WriteImage(image, output_file)
    print(f"[dicom2nii] Wrote NIfTI: {output_file}")
    return output_file



# -------------------------------------------------------------------------
# NIfTI -> DICOM
# -------------------------------------------------------------------------

def nifti_to_dicom(nifti_file: str, ref_dicom_dir: str, output_dir: str):
    """
    Convert a NIfTI volume back to a DICOM series using a reference DICOM
    series (for geometry + metadata).

    This is intended for research/QA workflows, NOT clinical replacement.
    - Copies most header fields from the reference series
    - Generates new SeriesInstanceUID and SOPInstanceUIDs
    """
    nifti_file = os.path.abspath(nifti_file)
    ref_dicom_dir = os.path.abspath(ref_dicom_dir)
    output_dir = os.path.abspath(output_dir)
    ensure_dir(output_dir)

    print(f"[nii2dicom] NIfTI:  {nifti_file}")
    print(f"[nii2dicom] Ref:    {ref_dicom_dir}")
    print(f"[nii2dicom] Output: {output_dir}")

    # Load nifti
    nii = nib.load(nifti_file)
    data = nii.get_fdata()
    # Expecting [z, y, x] or [y, x, z]. We will try to guess.
    arr = np.asarray(data)

    # Load reference DICOM series (sorted)
    ref_files = sorted_dicom_files(ref_dicom_dir)
    ref_ds_list = [pydicom.dcmread(f) for f in ref_files]

    # Determine slice dimension
    # Assuming ref series is [rows, cols, slices] in the usual layout
    n_slices_ref = len(ref_ds_list)
    print(f"[nii2dicom] Reference slices: {n_slices_ref}")

    shape = arr.shape
    print(f"[nii2dicom] NIfTI shape: {shape}")

    if len(shape) == 3:
        # check if one of the dims matches number of slices
        if shape[0] == n_slices_ref:
            arr_slices_first = arr
        elif shape[2] == n_slices_ref:
            # reorder [y, x, z] -> [z, y, x]
            arr_slices_first = np.moveaxis(arr, 2, 0)
        else:
            raise RuntimeError(
                f"NIfTI shape {shape} not compatible with reference slice count {n_slices_ref}"
            )
    else:
        raise RuntimeError("Only 3D NIfTI volumes are supported for now.")

    # Cast to same type as reference pixel data
    sample_ref = ref_ds_list[0]
    ref_dtype = np.dtype(np.int16)  # default
    if hasattr(sample_ref, "pixel_array"):
        ref_dtype = sample_ref.pixel_array.dtype

    arr_slices_first = arr_slices_first.astype(ref_dtype)

    # New UIDs for series and frame-of-reference (simple approach)
    new_series_uid = generate_uid()
    new_for_uid = generate_uid()

    print(f"[nii2dicom] New SeriesInstanceUID: {new_series_uid}")
    print(f"[nii2dicom] New FrameOfReferenceUID: {new_for_uid}")

    for i, (ds_ref, slice_data) in enumerate(zip(ref_ds_list, arr_slices_first)):
        ds = ds_ref.copy()

        # Basic header adaptations
        ds.SeriesInstanceUID = new_series_uid
        ds.FrameOfReferenceUID = new_for_uid
        ds.SOPInstanceUID = generate_uid()

        # Make it obvious this is defaced / processed
        ds.SeriesDescription = (getattr(ds, "SeriesDescription", "") + " CTA-DEFACE").strip()
        ds.ImageComments = "Generated from NIfTI via cta_deface_convert.py"

        # Update instance number if needed
        ds.InstanceNumber = i + 1

        # Pixel data
        # Ensure shape matches Rows x Columns
        slice_arr = np.asarray(slice_data)
        if slice_arr.shape != (ds.Rows, ds.Columns):
            raise RuntimeError(
                f"Slice {i}: array shape {slice_arr.shape} does not match DICOM ({ds.Rows}, {ds.Columns})"
            )

        ds.PixelData = slice_arr.tobytes()

        # Save new DICOM
        out_name = os.path.join(output_dir, f"IM_{i+1:04d}.dcm")
        ds.save_as(out_name)
        # Optional: print per-slice if debugging
        # print(f"[nii2dicom] Wrote: {out_name}")

    print(f"[nii2dicom] Wrote {len(ref_ds_list)} DICOM slices to {output_dir}")


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CTA-DEFACE DICOM <-> NIfTI converter (CPU-only friendly)."
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # dicom2nii
    p_d2n = subparsers.add_parser("dicom2nii", help="Convert DICOM series to NIfTI")
    p_d2n.add_argument(
        "-i", "--input", required=True,
        help="Input DICOM directory containing a single series"
    )
    p_d2n.add_argument(
        "-o", "--output", required=True,
        help="Output NIfTI file OR directory. "
             "If a directory, filename is based on SeriesInstanceUID."
    )
    p_d2n.add_argument(
        "--no-nnunet-style", action="store_true",
        help="Disable automatic '_0000.nii.gz' naming for nnUNet."
    )

    # nii2dicom
    p_n2d = subparsers.add_parser("nii2dicom", help="Convert NIfTI back to DICOM")
    p_n2d.add_argument(
        "-n", "--nifti", required=True,
        help="Input NIfTI file (e.g. defaced output)"
    )
    p_n2d.add_argument(
        "-r", "--ref-dicom", required=True,
        help="Reference DICOM directory (original series, for metadata/geometry)"
    )
    p_n2d.add_argument(
        "-o", "--output", required=True,
        help="Output directory for new DICOM series"
    )

    args = parser.parse_args()

    if args.cmd == "dicom2nii":
        dicom_to_nifti(
            args.input,
            args.output,
            nnunet_style=not args.no_nnunet_style
        )
    elif args.cmd == "nii2dicom":
        nifti_to_dicom(
            args.nifti,
            args.ref_dicom,
            args.output
        )
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

