# 🧠 CTA-DEFACE — CPU-Only CT Defacing Pipeline (DICOM ⇄ NIfTI)

CTA-DEFACE is a **beginner-friendly** end-to-end pipeline for defacing CT head/neck scans:

> **DICOM → NIfTI → nnUNet (mask) → Defaced NIfTI → Defaced DICOM**

This fork adds:

- ✅ **CPU-only support** (no GPU / CUDA required)
- ✅ **Linux & Windows** setup and run scripts
- ✅ **Single-case and multi-case batch processing**
- ✅ **Full DICOM header reuse** (no anonymization, only PixelData is changed)
- ✅ **Robust handling of series, slice mismatches and nnUNet quirks** :contentReference[oaicite:0]{index=0}  

> ⚠️ **Important:** This pipeline **does not anonymize DICOM metadata**. It only defaces image pixels.  
> If you need GDPR-compliant anonymization, you must perform it **before** or **after** this pipeline with appropriate tools.

---

## 📂 Main Components (Files You’ll Use)

In the repo root:

- `run_CTA-DEFACE.py`  
  Runs nnUNetv2 (CPU) to generate a **face mask** and combine it with the original CT to produce a **defaced NIfTI**.

- `cta_deface_pipeline_multi2.py`  
  The **main batch pipeline**:
  - Detects DICOM case folders
  - Converts DICOM → NIfTI
  - Runs `run_CTA-DEFACE.py`
  - Picks the correct defaced NIfTI
  - Rebuilds **defaced DICOM** using **full original headers**

- `cta_deface_convert.py` (optional / helper)  
  Simple DICOM ⇄ NIfTI converter for testing.

- `requirements_cpu.txt` (Linux)  
  Python dependencies for CPU-only use.

- `requirements_cta_deface_windows.txt` (Windows)  
  Python dependencies for Windows CPU-only use.

- `setup_cta_deface_cpu.sh` (Linux)  
  Shell script to create a virtualenv and install everything for **CPU-only** execution.

- `setup_cta_deface_cpu.ps1` (Windows)  
  PowerShell version of the setup script (creates venv + installs requirements + CPU-only PyTorch + nnUNetv2).

- `run_cta_deface_batch.ps1` (Windows)  
  PowerShell wrapper that runs `cta_deface_pipeline_multi2.py` for **batch** defacing.

---

## 🧱 Directory Layout (Input & Output)

**Input DICOM root** can be:

### 1) Single case

```text
dicom_input/
    IMG_0001.dcm
    IMG_0002.dcm
    ...

2) Multiple cases (recommended)

dicom_root/
    case01/
        *.dcm
    case02/
        *.dcm
    case03/
        *.dcm
    ...

Output (after running the pipeline) will look like:

dicom_output/
    case01/
        # defaced DICOMs
    case02/
    case03/
    ...

nifti_output/             # only if you enable --nifti-root-out
    case01/
        <SeriesUID>_defaced.nii.gz
    case02/
    case03/

🧩 Requirements
Hardware

    Any modern CPU-only machine

    RAM: 8–16 GB recommended (nnUnet)

    Disk: Enough space for your DICOMs + NIfTIs (often 2–3× raw DICOM size)

Software (Both Linux & Windows)

    Python 3.10+

    Git (to clone repository)

    Internet access (first time only, to download Python packages & nnUNet models)

🐧 Linux Setup (Beginner-Friendly)

All commands below assume you are in a terminal and you start in your home folder.
1️⃣ Clone the repository

cd ~
git clone https://github.com/jsfakian/CTA-DEFACE.git
cd CTA-DEFACE

2️⃣ Run the automatic CPU setup script

This will:

    Create a virtual environment .venv_cta_deface

    Install Python dependencies from requirements_cpu.txt

    Install CPU-only PyTorch

    Install nnUNetv2

bash setup_cta_deface_cpu.sh

If everything is OK, you should see messages like:

    Python version OK.

    Virtualenv created at .venv_cta_deface

    nnUNetv2 OK

3️⃣ Activate the environment (for manual runs)

source .venv_cta_deface/bin/activate

Your shell prompt may change to something like:

(.venv_cta_deface) user@machine:~/CTA-DEFACE$

To deactivate later:

deactivate

▶️ Linux: Running the Pipeline

Assume:

    Input DICOMs: ~/CTA-DEFACE/dicom_input/

    Output defaced DICOMs: ~/CTA-DEFACE/dicom_output/

    Optional defaced NIfTIs: ~/CTA-DEFACE/nifti_output/

🔹 A. Single case (one DICOM folder)

If all your DICOM slices are directly in dicom_input/:

source .venv_cta_deface/bin/activate

python cta_deface_pipeline_multi2.py \
    -i dicom_input \
    -o dicom_output

    The script automatically detects DICOM files in dicom_input/.

    Outputs defaced DICOMs into dicom_output/.

🔹 B. Multiple cases

Structure:

dicom_input/
    case01/
        *.dcm
    case02/
        *.dcm

Run:

source .venv_cta_deface/bin/activate

python cta_deface_pipeline_multi2.py \
    -i dicom_input \
    -o dicom_output \
    --nifti-root-out nifti_output

    Each detected case directory under dicom_input/ is processed.

    Defaced DICOMs are written under dicom_output/<case>/.

    Defaced NIfTIs are written under nifti_output/<case>/.

🪟 Windows Setup (Beginner-Friendly)

You’ll use PowerShell (not CMD).
1️⃣ Open PowerShell

    Press Start, type “PowerShell”, and run Windows PowerShell.

Optionally, allow local scripts (one-time):

Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

2️⃣ Clone the repository

cd $HOME
git clone https://github.com/jsfakian/CTA-DEFACE.git
cd CTA-DEFACE

3️⃣ Run the automatic CPU setup script

.\setup_cta_deface_cpu.ps1

This will:

    Create .venv_cta_deface\

    Install packages from requirements_cta_deface_windows.txt

    Install CPU-only PyTorch

    Check nnUNetv2

If it ends with something like:

=== Setup complete! ===
Virtualenv: C:\Users\...\CTA-DEFACE\.venv_cta_deface

…you are good.

You can activate the environment manually if needed:

.\.venv_cta_deface\Scripts\Activate.ps1

▶️ Windows: Running the Pipeline

Assume the following folders under CTA-DEFACE\:

CTA-DEFACE\
    dicom_input\
    dicom_output\
    nifti_output\

🔹 A. Quick batch run with wrapper script

Use the provided wrapper run_cta_deface_batch.ps1.
Example 1 — Only defaced DICOM output

cd $HOME\CTA-DEFACE

.\run_cta_deface_batch.ps1 `
    -DicomRootIn  ".\dicom_input" `
    -DicomRootOut ".\dicom_output"

Example 2 — Also save defaced NIfTIs

cd $HOME\CTA-DEFACE

.\run_cta_deface_batch.ps1 `
    -DicomRootIn  ".\dicom_input" `
    -DicomRootOut ".\dicom_output" `
    -NiftiRootOut ".\nifti_output"

The script will:

    Use the virtualenv .venv_cta_deface

    Call cta_deface_pipeline_multi2.py with correct arguments

    Process all detected case directories under dicom_input\

🔧 What the Pipeline Does Internally (Step by Step)

For each case directory (e.g. dicom_input/case01):
1️⃣ DICOM → NIfTI

    Uses SimpleITK to read all slices belonging to the first DICOM series in that folder.

    Builds a 3D volume.

    Writes SeriesInstanceUID_0000.nii.gz into a case-specific working folder:

    work_deface_batch/<case>/nifti_in/<SeriesUID>_0000.nii.gz

2️⃣ Defacing with nnUNetv2 (CPU)

    Calls:

    python run_CTA-DEFACE.py -i <nifti_in> -o <nifti_out>

    run_CTA-DEFACE.py:

        Ensures nnUNet naming (*_0000.nii.gz)

        Runs nnUNetv2 on CPU to segment face region

        Saves:

            <SeriesUID>_mask.nii.gz (binary mask)

            <SeriesUID>_defaced.nii.gz (original CT with face voxels replaced by a low-intensity background, e.g. 10th percentile)

3️⃣ Picking the correct defaced NIfTI

The pipeline then searches in nifti_out:

    Preferred: file containing "defaced" in its name (e.g. <SeriesUID>_defaced.nii.gz)

    Otherwise: the only .nii.gz file without "mask" in the name.

    It also checks that:

        The defaced NIfTI is not identical to the original (voxel-wise); if it is, you get an error: “no defacing applied”.

If you used --nifti-root-out, this chosen defaced NIfTI is also copied to:

nifti_output/<case>/<SeriesUID>_defaced.nii.gz

4️⃣ NIfTI → DICOM (header-preserving reconstruction)

For NIfTI → DICOM:

    All DICOMs in the original case folder are loaded and grouped by SeriesInstanceUID.

    The series whose slice count best matches the NIfTI volume is chosen.

    Only PixelData is replaced slice-by-slice.

    All patient/study/series/instance UIDs and metadata are preserved.

    When slice counts differ (e.g. NIfTI has 36 slices, DICOM has 72):

        The first 36 slices are replaced with defaced data.

        Remaining slices are copied unchanged.

    The result is written into:

dicom_output/<case>/*.dcm

    💡 This means: your defaced DICOM series looks and behaves like the original in typical viewers, but with the face area removed.

💻 CLI Reference (Linux & Windows, Same Script)

The core script is:

python cta_deface_pipeline_multi2.py [options]

Required arguments
Option	Description
-i, --dicom-root-in PATH	Root folder containing DICOM case dirs or a single DICOM dir
-o, --dicom-root-out PATH	Root output folder where defaced DICOMs are written
Optional arguments
Option	Description
--nifti-root-out PATH	Also save defaced NIfTIs per case (mirrors input structure)
-w, --work-root PATH	Working directory for intermediate NIfTI files (default: work_deface_batch)
--cta-extra-args ...	Any extra arguments passed directly to run_CTA-DEFACE.py (currently rarely needed)
-h, --help	Show help

Examples (Linux):

python cta_deface_pipeline_multi2.py \
    -i dicom_input \
    -o dicom_output

python cta_deface_pipeline_multi2.py \
    -i dicom_input \
    -o dicom_output \
    --nifti-root-out nifti_output \
    -w /tmp/work_deface_batch

Examples (Windows / PowerShell, with explicit venv):

.\.venv_cta_deface\Scripts\Activate.ps1

python cta_deface_pipeline_multi2.py `
    -i ".\dicom_input" `
    -o ".\dicom_output"

🧪 Tips & Troubleshooting (Beginner Notes)
1. No cases found

Error:

    No DICOM cases found under ...

Check that -i points to a folder that actually contains DICOM files or subfolders with DICOMs.
2. CTA-DEFACE produced only mask NIfTIs

Error:

    CTA-DEFACE produced only mask NIfTIs ... no candidate defaced image.

Means:

    nnUNet only produced a mask; the defaced image is missing.

    Check run_CTA-DEFACE.py output and logs in work_deface_batch/<case>/nifti_out.

    Sometimes this indicates a format or naming issue in the input NIfTI.

3. Orientation looks odd in some viewers

    Internally the pipeline keeps the geometry consistent slice-by-slice.

    Different viewers may interpret DICOM tags differently (LPS/RAS, patient position).

    If one viewer shows images 90° off but another looks correct, it may be a viewer convention rather than a true pipeline error.

4. Cleaning temporary files

If you want to start fresh:

rm -rf work_deface_batch/

(Windows):

Remove-Item -Recurse -Force .\work_deface_batch\

This does not touch dicom_output or nifti_output.
🙏 Citation

If you use this tool in scientific work, please cite the original CTA-DEFACE paper:

    Mahmutoglu MA, Rastogi A, Schell M, Foltyn-Dumitru M, Baumgartner M, Maier-Hein KH, Deike-Hofmann K, Radbruch A, Bendszus M, Brugnara G, Vollmuth P.
    Deep learning-based defacing tool for CT angiography: CTA-DEFACE.
    Eur Radiol Exp. 2024;8(1):111. doi: 10.1186/s41747-024-00510-9.

And optionally reference this GitHub repository (jsfakian/CTA-DEFACE) in your methods.