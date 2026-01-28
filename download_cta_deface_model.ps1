Param(
    [string]$VenvName = ".venv_cta_deface",
    [string]$ModelFolderUrl = "https://drive.google.com/drive/folders/1k4o35Dkl7PWd2yvHqWA2ia-BNKrWBrqg?usp=sharing"
)

Write-Host "=== CTA-DEFACE: Download pretrained model (Windows) ==="

# Repo root = folder where this .ps1 is located
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$venvPath   = Join-Path $repoRoot $VenvName
$venvPython = Join-Path $venvPath "Scripts\python.exe"

Write-Host "[INFO] Repo root: $repoRoot"
Write-Host "[INFO] Venv path: $venvPath"
Write-Host "[INFO] Venv python: $venvPython"

if (-not (Test-Path $venvPython)) {
    Write-Error "Virtualenv python not found at: $venvPython"
    Write-Error "Run setup first (setup_cta_deface_cpu.ps1) or set -VenvName to the correct venv folder."
    exit 1
}

# Install gdown inside venv
Write-Host "[1/4] Installing/upgrading gdown..."
& "$venvPython" -m pip install --upgrade pip gdown
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install gdown. Cannot download model."
    exit 1
}

$modelDir = Join-Path $repoRoot "model"
$tmpModel = Join-Path $repoRoot "_tmp_model_download"

# Clean temp folder
if (Test-Path $tmpModel) {
    Remove-Item -Recurse -Force $tmpModel -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force $tmpModel | Out-Null
New-Item -ItemType Directory -Force $modelDir | Out-Null

Write-Host "[2/4] Downloading model folder from Google Drive..."
Write-Host "      $ModelFolderUrl"

& "$venvPython" -m gdown --folder "$ModelFolderUrl" --output "$tmpModel"
if ($LASTEXITCODE -ne 0) {
    Write-Error "gdown failed downloading the model folder. Check URL/network."
    exit 1
}

Write-Host "[3/4] Extracting/copying downloaded content into .\model..."

# A) Extract all zips
$zips = Get-ChildItem -Path $tmpModel -Recurse -File -Filter "*.zip" -ErrorAction SilentlyContinue
if ($zips -and $zips.Count -gt 0) {
    foreach ($zip in $zips) {
        Write-Host "  - Extracting ZIP: $($zip.FullName)"
        Expand-Archive -Path $zip.FullName -DestinationPath $modelDir -Force
    }
}

# B) Copy any DatasetXXX_* dirs (either from download or from extracted zips)
$datasetDirs = Get-ChildItem -Path $tmpModel -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^Dataset\d{3}_.+' }

if ($datasetDirs -and $datasetDirs.Count -gt 0) {
    foreach ($d in $datasetDirs) {
        $dest = Join-Path $modelDir $d.Name
        if (-not (Test-Path $dest)) {
            Write-Host "  - Copying dataset folder: $($d.FullName) -> $dest"
            Copy-Item -Recurse -Force $d.FullName $dest
        }
    }
}

# C) Also detect DatasetXXX_* dirs inside model (after unzip) and report
$datasetsInModel = Get-ChildItem -Path $modelDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^Dataset\d{3}_.+' }

Write-Host "[4/4] Verifying..."
if (-not $datasetsInModel -or $datasetsInModel.Count -eq 0) {
    Write-Warning "No DatasetXXX_* folders found in $modelDir."
    Write-Warning "nnUNet will fail if the pretrained model isn't placed correctly."
    Write-Host "Contents of model folder:"
    Get-ChildItem -Path $modelDir -Recurse | Select-Object FullName | Format-Table -AutoSize
    exit 2
} else {
    Write-Host "✅ Model installed. Found dataset folder(s):"
    $datasetsInModel | ForEach-Object { Write-Host "   " $_.FullName }
}

Write-Host ""
Write-Host "Next step (PowerShell session): set nnUNet env vars to this model folder:"
Write-Host "  `$env:nnUNet_raw          = `"$modelDir`""
Write-Host "  `$env:nnUNet_preprocessed = `"$modelDir`""
Write-Host "  `$env:nnUNet_results      = `"$modelDir`""
