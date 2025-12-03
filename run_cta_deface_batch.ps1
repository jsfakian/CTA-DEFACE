Param(
    [Parameter(Mandatory = $true)]
    [string]$DicomRootIn,

    [Parameter(Mandatory = $true)]
    [string]$DicomRootOut,

    [string]$NiftiRootOut = "",
    [string]$WorkRoot = "work_deface_batch",

    [string]$VenvName = ".venv_cta_deface",

    # Extra args passed directly to run_CTA-DEFACE.py
    [string[]]$CtaExtraArgs = @()
)

Write-Host "=== CTA-DEFACE batch run (Windows) ==="

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $repoRoot $VenvName
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-Not (Test-Path $venvPython)) {
    Write-Error "Virtualenv not found at $venvPath. Run setup_cta_deface_cpu.ps1 first."
    exit 1
}

$DicomRootIn  = (Resolve-Path $DicomRootIn).Path
$DicomRootOut = (Resolve-Path $DicomRootOut -Relative:$false)
if ($NiftiRootOut -ne "") {
    $NiftiRootOut = (Resolve-Path $NiftiRootOut -Relative:$false)
}

$pipelineScript = Join-Path $repoRoot "cta_deface_pipeline_multi2.py"
if (-Not (Test-Path $pipelineScript)) {
    Write-Error "Pipeline script not found: $pipelineScript"
    exit 1
}

# Build base command
$cmd = @(
    $venvPython
    $pipelineScript
    "-i", $DicomRootIn
    "-o", $DicomRootOut
    "-w", $WorkRoot
)

if ($NiftiRootOut -ne "") {
    $cmd += @("--nifti-root-out", $NiftiRootOut)
}

if ($CtaExtraArgs.Count -gt 0) {
    $cmd += @("--cta-extra-args")
    $cmd += $CtaExtraArgs
}

Write-Host "Running pipeline:"
Write-Host "  " ($cmd -join " ")

& $cmd
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Warning "Pipeline exited with code $exitCode"
} else {
    Write-Host "=== Pipeline finished successfully. ==="
}
exit $exitCode
