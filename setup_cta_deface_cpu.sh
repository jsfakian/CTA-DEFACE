#!/usr/bin/env bash
set -euo pipefail

### CONFIG #####################################################################

PYTHON_BIN=${PYTHON_BIN:-python3}
VENV_DIR=${VENV_DIR:-.venv_cta_deface}
REQ_FILE=${REQ_FILE:-requirements-cta-deface.txt}

# Default nnUNet directory layout (local to repo)
NNUNET_BASE=${NNUNET_BASE:-"$PWD/nnunet_data"}
export nnUNet_raw="${NNUNET_BASE}/nnUNet_raw"
export nnUNet_preprocessed="${NNUNET_BASE}/nnUNet_preprocessed"
export nnUNet_results="${NNUNET_BASE}/nnUNet_results"

# CTA-DEFACE model folder (as per README)
MODEL_DIR=${MODEL_DIR:-"$PWD/model"}
MODEL_SUBDIR="${MODEL_DIR}/Dataset001_DEFACE"
GDRIVE_URL=${GDRIVE_URL:-"https://drive.google.com/drive/folders/1k4o35Dkl7PWd2yvHqWA2ia-BNKrWBrqg?usp=sharing"}

###############################################################################

echo "=== CTA-DEFACE CPU setup ==="
echo "Python:   ${PYTHON_BIN}"
echo "Venv:     ${VENV_DIR}"
echo "nnUNet:   raw='${nnUNet_raw}', preprocessed='${nnUNet_preprocessed}', results='${nnUNet_results}'"
echo "Model dir:${MODEL_DIR}"
echo

### 1. Check Python version ####################################################

echo "[1/5] Checking Python version..."
"${PYTHON_BIN}" - << 'PYCHECK'
import sys
major, minor = sys.version_info[:2]
if (major, minor) < (3, 9):
    raise SystemExit(
        f"Python >= 3.9 required, found {major}.{minor}. "
        "Set PYTHON_BIN to a proper interpreter and re-run."
    )
PYCHECK
echo "Python version OK."
echo

### 2. Create / reuse virtualenv ##############################################

echo "[2/5] Creating / reusing virtualenv..."

NEED_NEW_VENV=0

if [ ! -d "${VENV_DIR}" ]; then
    echo "No existing virtualenv found, creating new one..."
    NEED_NEW_VENV=1
else
    # Check if it *looks* like a valid venv (has activate script)
    if [ ! -f "${VENV_DIR}/bin/activate" ] && [ ! -f "${VENV_DIR}/Scripts/activate" ]; then
        echo "Existing '${VENV_DIR}' does not contain a valid virtualenv."
        echo "Recreating virtualenv..."
        rm -rf "${VENV_DIR}"
        NEED_NEW_VENV=1
    else
        echo "Virtualenv already exists at ${VENV_DIR} – reusing."
    fi
fi

if [ "${NEED_NEW_VENV}" -eq 1 ]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    echo "Created virtualenv at ${VENV_DIR}"
fi

# Activate venv (Linux/macOS: bin/activate, Windows: Scripts/activate)
if [ -f "${VENV_DIR}/bin/activate" ]; then
    # shellcheck disable=SC1090
    source "${VENV_DIR}/bin/activate"
elif [ -f "${VENV_DIR}/Scripts/activate" ]; then
    # shellcheck disable=SC1090
    source "${VENV_DIR}/Scripts/activate"
else
    echo "ERROR: Could not find activate script in '${VENV_DIR}'."
    echo "       Expected '${VENV_DIR}/bin/activate' or '${VENV_DIR}/Scripts/activate'."
    exit 1
fi

echo "Virtualenv activated."
echo


### 3. Install / ensure CPU-only PyTorch #######################################

echo "[3/5] Ensuring CPU-only PyTorch is installed..."

if python -c "import torch; print(torch.__version__)" >/dev/null 2>&1; then
    echo "torch already installed – leaving as is."
else
    echo "Installing CPU-only torch & torchvision from PyTorch CPU wheels..."
    # You can pin versions if you want; this keeps it a bit more future-proof.
    pip install --upgrade pip
    pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
fi

echo "torch backend:"
python - << 'PYTORCHCHK'
import torch
print("  torch version:", torch.__version__)
print("  CUDA available:", torch.cuda.is_available())
PYTORCHCHK
echo

### 4. Install Python dependencies (including nnunetv2 & gdown) ###############

echo "[4/5] Installing CTA-DEFACE + nnUNet dependencies..."

if [ -f "${REQ_FILE}" ]; then
    echo "Using requirements file: ${REQ_FILE}"
    pip install -r "${REQ_FILE}"
else
    echo "WARNING: ${REQ_FILE} not found, installing core packages directly."
    pip install numpy scipy nibabel tqdm scikit-image pydicom SimpleITK nnunetv2 gdown
fi

# Make sure nnunetv2 is importable
python - << 'PYNN'
import nnunetv2
print("nnunetv2 version:", getattr(nnunetv2, "__version__", "unknown"))
PYNN
echo

# Ensure nnUNet directory structure exists
echo "Ensuring nnUNet directory structure exists..."
mkdir -p "${nnUNet_raw}" "${nnUNet_preprocessed}" "${nnUNet_results}"
echo "nnUNet dirs OK."
echo

### 5. Download CTA-DEFACE trained model (if missing) #########################

echo "[5/5] Checking for CTA-DEFACE model..."
mkdir -p "${MODEL_DIR}"

if [ -d "${MODEL_SUBDIR}" ]; then
    echo "Model directory '${MODEL_SUBDIR}' already exists – skipping download."
else
    echo "Model directory not found. Attempting download from Google Drive:"
    echo "  ${GDRIVE_URL}"
    echo

    # Ensure gdown is available (should already be via requirements, but just in case)
    if ! command -v gdown >/dev/null 2>&1; then
        echo "gdown not found in PATH – installing..."
        pip install gdown
    fi

    # Download folder to MODEL_DIR
    gdown --folder "${GDRIVE_URL}" -O "${MODEL_DIR}" || {
        echo "ERROR: gdown download failed."
        echo "       Please download the 'Dataset001_DEFACE' folder manually"
        echo "       into: ${MODEL_DIR}"
        exit 1
    }

    if [ -d "${MODEL_SUBDIR}" ]; then
        echo "Model successfully downloaded to '${MODEL_SUBDIR}'."
    else
        echo "WARNING: Download completed but '${MODEL_SUBDIR}' not found."
        echo "         Please check contents of '${MODEL_DIR}' manually."
    fi
fi
echo

### Summary ###################################################################

cat << EOF

=== CTA-DEFACE CPU environment ready ===

Virtualenv: ${VENV_DIR}
To use it in this shell:
    source ${VENV_DIR}/bin/activate

Environment variables (for nnUNet):
    export nnUNet_raw="${nnUNet_raw}"
    export nnUNet_preprocessed="${nnUNet_preprocessed}"
    export nnUNet_results="${nnUNet_results}"

Model location:
    ${MODEL_SUBDIR}

To run CTA-DEFACE (CPU-only) once venv is active:
    export CUDA_VISIBLE_DEVICES=""
    python run_CTA-DEFACE.py -i input -o output

(Optionally use the helper script 'run_cta_deface_cpu.sh' below.)

EOF

