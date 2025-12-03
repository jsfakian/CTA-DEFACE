Param(
    [string]$PythonExe = "python",
    [string]$VenvName = ".venv_cta_deface"
)

Write-Host "=== CTA-DEFACE CPU setup (Windows) ==="

# ------------------------
# 1. Check Python
# ------------------------
Write-Host "[1/4] Checking Python..."
try {
    $pyVersion = & $PythonExe -c "import sys; print(sys.version.split()[0])"
    Write-Host "Python version:" $pyVersion
} catch {
    Write-Error "Could not run '$PythonExe'. Ensure Python is in PATH."
    exit 1
}

# ------------------------
# 2. Create / reuse venv
# ------------------------
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $repoRoot $VenvName

Write-Host "[2/4] Creating / reusing virtual environment at $venvPath ..."
if (-Not (Test-Path $venvPath)) {
    & $PythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment."
        exit 1
    }
    Write-Host "Virtual environment created."
} else {
    Write-Host "Virtual environment already exists – reusing."
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

# ------------------------
# 3. Upgrade pip & install requirements
# ------------------------
Write-Host "[3/4] Installing Python dependencies (CPU only)..."

# Upgrade pip
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upgrade pip."
    exit 1
}

# Install core requirements
$reqFile = Join-Path $repoRoot "requirements_cta_deface_windows.txt"
if (-Not (Test-Path $reqFile)) {
    Write-Error "Requirements file not found: $reqFile"
    exit 1
}

& $venvPython -m pip install -r $reqFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install requirements."
    exit 1
}

# Install CPU-only PyTorch (official CPU index)
Write-Host "Installing CPU-only PyTorch..."
& $venvPython -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install CPU-only PyTorch."
    exit 1
}

# ------------------------
# 4. Quick sanity checks
# ------------------------
Write-Host "[4/4] Running quick checks..."

& $venvPython -c "import torch; print('Torch:', torch.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyTorch test failed."
    exit 1
}

& $venvPython -c "import nnunetv2; print('nnUNetv2 OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "nnUNetv2 import failed."
    exit 1
}

Write-Host ""
Write-Host "=== Setup complete! ==="
Write-Host "Virtualenv: $venvPath"
Write-Host "To activate in PowerShell:"
Write-Host "    `& '$venvPath\Scripts\Activate.ps1'"
Write-Host "Then run:"
Write-Host "    python cta_deface_pipeline_multi2.py -h"
