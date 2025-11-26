# DICOM ↔ NIfTI Conversion Tool (with Metadata Preservation)

This repository provides a command-line tool to convert DICOM → NIfTI and NIfTI → DICOM, while preserving metadata from the original DICOM series.

The tool is designed for CT modality, but it will also work with other single-frame modalities (MR, PET, etc.) as long as they follow standard DICOM structure.

The program accepts either:

* A directory containing DICOM files, or
* A directory containing NIfTI (.nii/.nii.gz) files

and writes the converted output to a specified directory.

If no parameters are provided, the script prints a help message.

## Features

* Convert DICOM → NIfTI, preserving key DICOM metadata in JSON sidecar files.
* Convert NIfTI → DICOM, restoring metadata from the preserved JSON.
* Accepts directories as input and processes all supported files.
* Preserves DICOM tags such as:
    * PatientID
    * PatientName
    * StudyInstanceUID
    * SeriesInstanceUID
    * FrameOfReferenceUID
    * SliceThickness
    * PixelSpacing
    * ImagePositionPatient / ImageOrientationPatient
* Skips pixel data when printing metadata.
* Works on multi-slice CT series.
* Clean code built with:
    * pydicom
    * nibabel
    * numpy

## Installation

Create a virtual environment and install dependencies:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Your requirements.txt should include:

```
pydicom
nibabel
numpy
```

## Usage

### Convert a DICOM directory to NIfTI

```
python convert.py --dicom2nifti \
    --input /path/to/dicom_folder \
    --output /path/to/nifti_output
```

This will produce:

```
output/
    series.nii.gz
    series_metadata.json
```

### Convert a NIfTI directory back to DICOM

```
python convert.py --nifti2dicom \
    --input /path/to/nifti_folder \
    --output /path/to/dicom_output
```

This will generate:

```
output/
    DICOM/
       <restored DICOM slices>
```

Metadata will be restored from the .json file generated during the DICOM→NIfTI conversion.

## Help Message

Run the script without arguments:

```
python dicom_nifti_converter.py
```

It will print:

```
Usage:
  --dicom2nifti   Convert DICOM directory to NIfTI
  --nifti2dicom   Convert NIfTI directory back to DICOM
  --input PATH    Input directory containing DICOM or NIfTI files
  --output PATH   Output directory where converted files will be saved

Examples:
  python convert.py --dicom2nifti --input ./dicom --output ./nifti
  python convert.py --nifti2dicom --input ./nifti --output ./dicom

Notes:
  - CT modality supported.
  - Metadata is preserved in a JSON sidecar.
  - Pixel data is fully preserved in conversions.
```

## Folder Structure Example

```
project/
│
├── convert.py
├── requirements.txt
└── README.md
```

## Metadata Preservation Strategy

✔ When converting DICOM → NIfTI:
* The script stores critical DICOM tags in a JSON file next to the NIfTI file.
* Pixel data goes into the .nii.gz file.

✔ When converting NIfTI → DICOM:
* The tool reconstructs a full DICOM series using:
    * NIfTI volume slices
    * Original metadata from JSON
    * A new SeriesInstanceUID (unless you want to reuse)

## Known Limitations

* Multiframe DICOM is not supported yet (coming soon).
* Only CT metadata is fully preserved.
* Sequence (SQ) tags are not restored (JSON preserves basic key tags only).

## Testing the Tool

Example test commands:

```
# Convert sample DICOM → NIfTI
python convert.py --dicom2nifti \
    --input ./samples/CT_DICOM \
    --output ./nifti_out

# Convert back
python convert.py --nifti2dicom \
    --input ./nifti_out \
    --output ./dicom_restored
```


