# 🧠 CTA-DEFACE — CPU-Only Defacing Pipeline (DICOM ⇄ NIfTI)

CTA-DEFACE is a complete, automated pipeline for defacing CT head/neck scans using **nnUNet-v2**–based segmentation and a custom image-blending routine that preserves anatomical quality while removing facial identifiers.

This repository extends the original work with:

- ✔ **CPU-only pipeline (no GPU required)**
- ✔ Fully automated **multi-case batch pipeline**
- ✔ Complete **DICOM → NIfTI → Deface → DICOM** workflow
- ✔ Header-preserving reconstruction (**no anonymization**)
- ✔ Robust multi-series handling
- ✔ Slice-mismatch tolerance and error-proof execution
- ✔ Clean working-directory structure

---

# 📦 Features

### 🔹 High-quality craniofacial defacing  
Uses nnUNetv2 segmentation to remove facial voxels while preserving diagnostic information.

### 🔹 CPU-only support  
No CUDA or GPU required (forced via `CUDA_VISIBLE_DEVICES=""`).

### 🔹 Multi-directory batch processing  
Automatically detects multiple DICOM case folders and processes each independently.

### 🔹 Full DICOM header preservation  
Generates defaced DICOM slices with original metadata and UIDs untouched.

### 🔹 Robust on problematic datasets  
Handles known CTA-DEFACE model quirks (e.g. `_0000.nii.gz` crash) and continues safely.

### 🔹 Tolerant to slice mismatches  
If a defaced NIfTI has fewer slices than the DICOM series, overlapping slices are updated while remaining slices are preserved.

---

# 📁 Repository Structure

```
CTA-DEFACE/
│
├── cta_deface_pipeline_multi.py     # Multi-case batch pipeline (recommended)
├── cta_deface_convert.py            # Single-case DICOM⇄NIfTI converter
├── run_CTA-DEFACE.py                # Main defacing script (CPU)
│
├── models/                          # nnUNetv2 pre-trained models
├── scripts/                         # Setup utilities
│
└── README.md                        # (this file)
```

---

# ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/jsfakian/CTA-DEFACE.git
cd CTA-DEFACE
```

### 2. Create CPU-only Python environment

```bash
python3 -m venv .venv_cta_deface
source .venv_cta_deface/bin/activate
```

### 3. Install requirements

```bash
pip install -r requirements_cpu.txt
```

### 4. Download nnUNetv2 pre-trained model(s)

```bash
bash scripts/download_nnunet_cpu.sh
```

This automatically downloads models into the correct nnUNetv2 folder structure.

---

# 🚀 Quick Start (Single Case)

To deface a **single DICOM directory**:

```bash
python cta_deface_pipeline_multi.py \
    -i dicom_input/ \
    -o dicom_output/
```

---

# 🚀 Batch Mode (Multiple DICOM Case Folders)

If your dataset contains multiple case directories:

```
dicom_root/
    case01/
    case02/
    case03/
```

Run:

```bash
python cta_deface_pipeline_multi.py \
    -i dicom_root \
    -o dicom_output \
    --nifti-root-out nifti_output
```

Output layout:

```
dicom_output/
    case01/
    case02/
    case03/

nifti_output/
    case01/
    case02/
    case03/
```

---

# ⚡ Pipeline Overview

Below is a simplified overview of CTA-DEFACE’s batch pipeline.

---

## **1. DICOM → NIfTI**

```
┌────────────────────────────┐
│  Input DICOM series        │
└──────────────┬─────────────┘
               ▼
        SimpleITK reader
               ▼
┌────────────────────────────┐
│  SeriesUID_0000.nii.gz     │
└────────────────────────────┘
```

---

## **2. Defacing (CTA-DEFACE / nnUNetv2 CPU)**

```
┌────────────────────────────┐
│  input NIfTI (_0000)       │
└──────────────┬─────────────┘
               ▼
      nnUNetv2 segmentation
               ▼
      Face mask generation
               ▼
    Image–mask blending logic
               ▼
┌────────────────────────────┐
│ defaced.nii.gz             │
│ defaced_mask.nii.gz        │
└────────────────────────────┘
```

---

## **3. Select Correct Output**

```
nifti_out/
 ├── <SeriesUID>.nii.gz         ← selected (defaced image)
 └── <SeriesUID>_mask.nii.gz    ← ignored
```

---

## **4. NIfTI → DICOM (Header-Preserving Reconstruction)**

```
┌────────────────────────────┐
│ Reference DICOM series     │
└──────────────┬─────────────┘
               ▼ match slice count
               ▼ or closest series
┌────────────────────────────┐
│ Defaced NIfTI (3D)         │
└──────────────┬─────────────┘
               ▼
  Replace PixelData only
  Preserve all metadata
               ▼
┌──────────────────────────────┐
│ Defaced DICOM series          │
└──────────────────────────────┘
```

---

# 🧰 CLI Options

### `cta_deface_pipeline_multi.py`

| Option | Description |
|--------|-------------|
| `-i, --dicom-root-in` | Root folder containing DICOM case directories |
| `-o, --dicom-root-out` | Output directory for defaced DICOMs |
| `--nifti-root-out` | Optional directory to store defaced NIfTIs per case |
| `-w, --work-root` | Working directory for intermediate files |
| `--cta-extra-args ...` | Extra args passed directly to run_CTA-DEFACE.py |
| `-h, --help` | Show help message |

---

# 🛠 Advanced Usage

### Extra nnUNet arguments

```bash
python cta_deface_pipeline_multi.py \
  -i dicom_root \
  -o dicom_out \
  --cta-extra-args --num_workers 1 --patch_size 192
```

### Custom work directory

```bash
python cta_deface_pipeline_multi.py \
  -i dicom_root \
  -o dicom_out \
  -w /fast_ssd/tmp
```

---

# 🔬 Supported Input Layouts

### **Single-case directory**

```
dicom_input/
    IMG_0001.dcm
    IMG_0002.dcm
```

### **Multi-case directory**

```
dicom_root/
    patient01/
        *.dcm
    patient02/
        *.dcm
```

Both modes are supported automatically.

---

# 🧪 Known Issues & Automatic Handling

### **1. CTA-DEFACE crashes when loading `<SeriesUID>_0000.nii.gz`**

This is a known issue with the segmentation model.

The pipeline:

- Ignores the crash  
- Continues processing  
- Uses the correct non-`_0000` NIfTI  
- Completes normally  

### **2. Slice-count mismatches**

- Updates the first matching slices  
- Copies remaining unchanged  
- Avoids crashing  
- Keeps consistent DICOM format  

---

# 🧹 Cleaning Up

Remove intermediate data:

```bash
rm -rf work_deface_batch/
```

This does **not** remove final defaced DICOMs or NIfTIs.

---

# 🙌 Credits

Developed by **jsfakian**

Enhancements include:

- CPU-only execution
- Robust multi-case batch processor
- Header-preserving DICOM reconstruction
- Safer nnUNet inference handling
- Improved slice/series matching logic
- Error-tolerant pipeline design

---



