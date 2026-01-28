
# 🧠 CTA-DEFACE — CPU-Only CT Defacing Pipeline (DICOM ⇄ NIfTI)

CTA-DEFACE is a **beginner-friendly** end-to-end pipeline for defacing CT head/neck scans:

> **DICOM → NIfTI → nnUNet (mask) → Defaced NIfTI → Defaced DICOM**

This fork adds:

- ✅ **CPU-only support** (no GPU / CUDA required)
- ✅ **Linux & Windows** setup and run scripts
- ✅ **Single-case and multi-case batch processing**
- ✅ **Full DICOM header reuse** (no anonymization, only PixelData is changed)
- ✅ **Robust handling of series, slice mismatches and nnUNet quirks**

⚠️ **Important:** This pipeline **does not anonymize DICOM metadata**.  
It only removes facial anatomy from image pixels.

---

## 🌍 Who is this for?

- Beginners with **zero experience** in nnUNet or medical imaging Python tooling  
- Medical physicists, radiologists, AI researchers  
- Anyone needing CT defacing **without GPU**  
- Anyone wanting a **ready-to-run**, fully automated DICOM → NIfTI → DEFACE → DICOM workflow

---

# 📁 Repository Contents

```
CTA-DEFACE/
│
├── run_CTA-DEFACE.py                 # nnUNet CPU inference + mask application
├── cta_deface_pipeline_multi2.py     # Full multi-case batch pipeline
├── cta_deface_convert.py             # Simple DICOM <-> NIfTI converter
│
├── setup_cta_deface_cpu.sh           # Linux CPU setup script
├── setup_cta_deface_cpu.ps1          # Windows CPU setup script
├── run_cta_deface_batch.ps1          # Windows batch runner
│
├── requirements_cpu.txt              # Linux dependencies
├── requirements_cta_deface_windows.txt
│
└── README.md                         # This file
```

---

# 🧱 Requirements

## Hardware
- Any **CPU-only** computer  
- RAM 8–16 GB recommended  
- Disk space: ~3× your DICOM dataset

## Software
- Python **3.10–3.12**
- Git
- Windows PowerShell **or** Linux bash

---

# 🐧 Linux Installation (Step by Step)

### 1. Clone repo
```bash
git clone https://github.com/jsfakian/CTA-DEFACE.git
cd CTA-DEFACE
```

### 2. Run setup
```bash
bash setup_cta_deface_cpu.sh
```

Creates `.venv_cta_deface/` and installs:
- nnUNetv2
- CPU-only PyTorch
- nibabel, SimpleITK, pydicom, tqdm, numpy…

### 3. Activate environment
```bash
source .venv_cta_deface/bin/activate
```

---

# ▶️ Linux: Running the Pipeline

### A. Single-case defacing
```bash
python cta_deface_pipeline_multi2.py     -i dicom_input     -o dicom_output
```

### B. Multi-case defacing
Input layout:
```
dicom_input/
 ├── case01/
 ├── case02/
 └── case03/
```

Run:
```bash
python cta_deface_pipeline_multi2.py     -i dicom_input     -o dicom_output     --nifti-root-out nifti_output
```

---

# 🪟 Windows Installation (Step by Step)

### 1. Install Git (Only once)

Git is required to download (clone) the project from GitHub.
Steps

    Go to: https://git-scm.com/download/win
    Download Git for Windows
    Run the installer
    During installation:
        Keep the default options
        Make sure "Git from the command line and also from 3rd-party software" is selected
    Finish installation

### 2. Verify Git installation

Open PowerShell and run: git --version

You should see something like: git version 2.x.x


### 3. Clone this repo
```powershell
git clone https://github.com/jsfakian/CTA-DEFACE.git
```

### 4. Run setup and download CTA_DEFACE model from google
```powershell
.\setup_cta_deface_cpu.ps1
.\download_cta_deface_model.ps1
```

### 5. Activate environment
```powershell
.\.venv_cta_deface\Scripts\Activate.ps1
```

---

# Prerequisites for run

```
mkdir dicom_input
mkdir dicom_output
mkdir work_deface_batch
```

Then place the input dicom images in dicom_input

---

# ▶️ Windows: Running the Pipeline

### Multi-case batch defacing (recommended)
```powershell
cd $HOME\CTA-DEFACE

python .\cta_deface_pipeline_multi2.py -i .\dicom_input\ -o .\dicom_output\ --nifti-root-out .\nifti_out\
```

---

# 🔧 What the Pipeline Does Internally

## 1️⃣ DICOM → NIfTI
- SimpleITK reads series
- Writes:  
  `work_deface_batch/<case>/nifti_in/<SeriesUID>_0000.nii.gz`

## 2️⃣ nnUNetv2 (CPU) defacing
`run_CTA-DEFACE.py` performs:
- Mask prediction (`*_mask.nii.gz`)
- Defaced reconstruction (`*_defaced.nii.gz`)  
  (face replaced by safe background intensity)

## 3️⃣ Selecting correct defaced NIfTI
Pipeline ensures:
- Picks `*_defaced.nii.gz`
- Verifies it differs pixel-wise from original

## 4️⃣ NIfTI → DICOM reconstruction
- Looks for best-matching SeriesInstanceUID
- Reuses **all** DICOM metadata:
  - PatientID
  - StudyInstanceUID
  - SeriesInstanceUID
  - Orientation
  - Slice geometry  
- Only `PixelData` is replaced

Output is written to:
```
dicom_output/<case>/<slice>.dcm
```

---

# 💻 CLI Reference

```
python cta_deface_pipeline_multi2.py     -i <dicom_root_in>     -o <dicom_root_out>     [--nifti-root-out PATH]     [-w work_deface_batch]     [--cta-extra-args ...]
```

---

# 📚 Citation

Please cite:

**Mahmutoglu et al. (2024), CTA-DEFACE — Deep learning-based CT defacing**  
_European Radiology Experimental_

---


