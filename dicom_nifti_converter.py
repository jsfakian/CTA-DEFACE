#!/usr/bin/env python3
import os
import sys
import argparse
import json
import pydicom
import nibabel as nib
import numpy as np
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian

# -------------------------------------------------
# Utility: collect all files in folder (recursive)
# -------------------------------------------------
def collect_files(path):
    if os.path.isdir(path):
        out = []
        for r, _, fs in os.walk(path):
            for f in fs:
                out.append(os.path.join(r, f))
        return sorted(out)
    else:
        return [path]

# -------------------------------------------------
# DICOM → NIfTI  (with metadata JSON)
# -------------------------------------------------
def dicom_to_nifti(input_path, output_path):
    files = [f for f in collect_files(input_path) if f.lower().endswith(".dcm")]
    if not files:
        print("No DICOM files found.")
        return

    print(f"Loading {len(files)} DICOM slices...")

    dss = [pydicom.dcmread(f) for f in files]
    dss = sorted(dss, key=lambda ds: int(ds.InstanceNumber))

    pixel_arrays = [ds.pixel_array for ds in dss]
    volume = np.stack(pixel_arrays, axis=-1)

    nifti_img = nib.Nifti1Image(volume.astype(np.int16), affine=np.eye(4))

    os.makedirs(output_path, exist_ok=True)
    nii_out = os.path.join(output_path, "image.nii.gz")
    json_out = os.path.join(output_path, "dicom_metadata.json")

    nib.save(nifti_img, nii_out)

    # Extract metadata (excluding pixel data)
    metadata = {}
    for tag in dss[0].keys():
        if tag == (0x7FE0, 0x0010):  # PixelData
            continue
        elem = dss[0][tag]
        metadata[elem.keyword or str(tag)] = elem.value

    with open(json_out, "w") as f:
        json.dump(metadata, f, indent=2)

    print("Conversion complete:")
    print(f"  NIfTI image:   {nii_out}")
    print(f"  Metadata JSON: {json_out}")

# -------------------------------------------------
# NIfTI → DICOM  (restoring metadata)
# -------------------------------------------------
def nifti_to_dicom(input_path, output_path):
    nii_files = [f for f in collect_files(input_path) if f.endswith(".nii") or f.endswith(".nii.gz")]
    if not nii_files:
        print("No NIfTI files found.")
        return

    nii = nib.load(nii_files[0])
    volume = nii.get_fdata().astype(np.int16)

    # Look for metadata.json next to the nifti file
    json_path = os.path.join(os.path.dirname(nii_files[0]), "dicom_metadata.json")
    if not os.path.exists(json_path):
        print("Warning: dicom_metadata.json not found. Will create minimal DICOM metadata.")
        metadata = {}
    else:
        metadata = json.load(open(json_path))

    os.makedirs(output_path, exist_ok=True)

    num_slices = volume.shape[-1]

    print(f"Reconstructing {num_slices} DICOM slices...")

    for i in range(num_slices):
        slice_data = volume[:, :, i]

        file_meta = Dataset()
        file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = FileDataset("anon", {}, file_meta=file_meta, preamble=b"\0" * 128)

        # Restore metadata
        for key, val in metadata.items():
            try:
                setattr(ds, key, val)
            except Exception:
                pass  # Skip incompatible metadata fields

        # Required updates
        ds.SOPInstanceUID = generate_uid()
        ds.InstanceNumber = i + 1

        # Pixel data
        ds.Rows, ds.Columns = slice_data.shape
        ds.PixelData = slice_data.tobytes()
        ds.BitsStored = 16
        ds.BitsAllocated = 16
        ds.HighBit = 15
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"

        out_name = os.path.join(output_path, f"slice_{i+1:04}.dcm")
        ds.save_as(out_name)

    print(f"Conversion complete. Output written to {output_path}")

# -------------------------------------------------
# CLI
# -------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Convert DICOM <-> NIfTI while preserving DICOM metadata.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "-i", "--input",
        help="Input DICOM folder/file or NIfTI file/folder"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output folder for the converted files"
    )
    parser.add_argument(
        "--mode",
        choices=["d2n", "n2d"],
        help="d2n = DICOM → NIfTI\nn2d = NIfTI → DICOM"
    )

    args = parser.parse_args()

    if not args.input or not args.output or not args.mode:
        parser.print_help()
        print("\nExamples:")
        print("  Convert DICOM directory → NIfTI:")
        print("     python dicom_nifti_converter.py -i ./dicoms -o ./out --mode d2n\n")
        print("  Convert NIfTI → DICOM series:")
        print("     python dicom_nifti_converter.py -i image.nii.gz -o ./dicoms_out --mode n2d\n")
        sys.exit(1)

    if args.mode == "d2n":
        dicom_to_nifti(args.input, args.output)
    elif args.mode == "n2d":
        nifti_to_dicom(args.input, args.output)

if __name__ == "__main__":
    main()

