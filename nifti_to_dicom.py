#!/usr/bin/env python3
import os
import json
import copy
from typing import Dict, Any

import numpy as np
import nibabel as nib
import pydicom
from pydicom.dataset import FileDataset
from pydicom.tag import Tag
from pydicom.uid import ExplicitVRLittleEndian, generate_uid


def load_metadata(metadata_json_path: str) -> Dict[str, Any]:
    with open(metadata_json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def rebuild_base_dataset(meta: Dict[str, Any]) -> FileDataset:
    """
    Create a FileDataset and populate it with metadata except PixelData.
    """
    file_meta = pydicom.dataset.FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = meta.get("00080016", {}).get("value", "1.2.840.10008.5.1.4.1.1.2")  # CT Image Storage default
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(
        filename_or_obj="",
        dataset={},
        file_meta=file_meta,
        preamble=b"\0" * 128,
    )

    ds.is_little_endian = True
    ds.is_implicit_VR = False

    for tag_hex, info in meta.items():
        vr = info.get("vr", "LO")
        value = info.get("value")
        # Some values we saved as strings; that's usually fine for many VRs.
        t = Tag(int(tag_hex, 16))
        if t.group == 0x0002:
            # File Meta tags belong in file_meta, but we already set key ones.
            continue
        try:
            ds.add_new(t, vr, value)
        except Exception:
            # Best-effort; you can log problematic tags here if needed
            pass

    return ds


def nifti_to_dicom_series(
    nifti_path: str,
    metadata_json_path: str,
    out_dir: str,
) -> None:
    os.makedirs(out_dir, exist_ok=True)

    img = nib.load(nifti_path)
    data = img.get_fdata()  # shape: (X, Y, Z) or (X, Y, Z, T)
    if data.ndim == 4:
        # take first volume if 4D
        data = data[..., 0]

    data = np.asarray(data)
    if data.ndim != 3:
        raise RuntimeError(f"Expected 3D data, got shape {data.shape}")

    meta = load_metadata(metadata_json_path)
    base_ds = rebuild_base_dataset(meta)

    # Update geometry from NIfTI
    affine = img.affine
    dx = float(np.linalg.norm(affine[0, :3]))
    dy = float(np.linalg.norm(affine[1, :3]))
    dz = float(np.linalg.norm(affine[2, :3]))

    base_ds.Rows = data.shape[0]
    base_ds.Columns = data.shape[1]
    base_ds.PixelSpacing = [str(dx), str(dy)]
    base_ds.SliceThickness = str(dz)
    base_ds.BitsAllocated = 16
    base_ds.BitsStored = 16
    base_ds.HighBit = 15
    base_ds.SamplesPerPixel = 1
    base_ds.PhotometricInterpretation = "MONOCHROME2"
    base_ds.PixelRepresentation = 1  # signed integers

    # Simple scaling to int16 if needed
    if data.dtype != np.int16:
        dmin = data.min()
        dmax = data.max()
        if dmax == dmin:
            scaled = np.zeros_like(data, dtype=np.int16)
        else:
            scaled = ((data - dmin) / (dmax - dmin) * 32767).astype(np.int16)
        data = scaled

    num_slices = data.shape[2]
    for i in range(num_slices):
        slice_ds = copy.deepcopy(base_ds)
        slice_ds.InstanceNumber = i + 1

        # Very naive position; for serious use, derive from affine properly.
        # Here we just step along z.
        if "ImagePositionPatient" in slice_ds:
            ipp = list(slice_ds.ImagePositionPatient)
        else:
            ipp = [0.0, 0.0, 0.0]
        ipp[2] = float(ipp[2]) + i * dz
        slice_ds.ImagePositionPatient = [str(x) for x in ipp]

        # Pixel data
        slice_arr = data[:, :, i]
        slice_ds.PixelData = slice_arr.tobytes()

        # New SOPInstanceUID per slice
        slice_ds.SOPInstanceUID = str(pydicom.uid.generate_uid())

        out_fname = os.path.join(out_dir, f"slice_{i+1:04d}.dcm")
        slice_ds.save_as(out_fname, write_like_original=False)

    print(f"Wrote {num_slices} DICOM slices to {out_dir}")


if __name__ == "__main__":
    # Example usage:
    nifti_in = "series.nii.gz"
    meta_in = "series_metadata.json"
    dicom_out_dir = "reconstructed_dicom"
    nifti_to_dicom_series(nifti_in, meta_in, dicom_out_dir)

