$ErrorActionPreference = "Stop"

$OmnixScriptsRoot = Split-Path -Parent $PSScriptRoot
$OmnixRepoRoot = Split-Path -Parent $OmnixScriptsRoot
Set-Location -LiteralPath $OmnixRepoRoot

$EnvName = "omnix311"
$PythonVersion = "3.11"

Write-Host ""
Write-Host "=== Omnix image environment bootstrap ==="
Write-Host "Env: $EnvName"
Write-Host "Python: $PythonVersion"
Write-Host ""

function Fail($msg) {
    Write-Host ""
    Write-Host "FAILED: $msg" -ForegroundColor Red
    exit 1
}

function Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Ok($msg) {
    Write-Host "OK: $msg" -ForegroundColor Green
}

Step "Checking conda"
$condaCmd = Get-Command conda -ErrorAction SilentlyContinue
if (-not $condaCmd) {
    Fail "conda was not found in PATH. Open an Anaconda/Miniconda shell and run again."
}
Ok "conda found"

Step "Checking whether env '$EnvName' already exists"
$envList = conda env list | Out-String
if ($envList -match "(?m)^\s*$EnvName\s") {
    Ok "Environment already exists"
} else {
    Step "Creating conda env '$EnvName' with Python $PythonVersion"
    conda create -n $EnvName python=$PythonVersion -y
    Ok "Environment created"
}

function InEnv($command) {
    conda run -n $EnvName powershell -NoProfile -Command $command
}

if (Test-Path "requirements/image.lock.txt") {
    Step "Installing the hash-locked image runtime"
    InEnv "python -m pip install --require-hashes -r requirements/image.lock.txt"
    Ok "Hash-locked image runtime installed"
} else {
    Fail "requirements/image.lock.txt was not found. Run the lock generation step first."
}

Step "Printing interpreter path"
InEnv "python -c ""import sys; print(sys.executable)"""

Step "Verifying image runtime imports"
InEnv @'
python -c "
import sys
print('Python:', sys.version)
import numpy
print('numpy:', numpy.__version__)
import torch
print('torch:', torch.__version__)
print('cuda available:', torch.cuda.is_available())
import diffusers
print('diffusers:', diffusers.__version__)
import transformers
print('transformers:', transformers.__version__)
import accelerate
print('accelerate:', accelerate.__version__)
import safetensors
print('safetensors:', safetensors.__version__)
from diffusers import Flux2KleinPipeline, Krea2Pipeline, ZImagePipeline
print('Flux2KleinPipeline: OK')
print('Krea2Pipeline: OK')
print('ZImagePipeline: OK')
"
'@
Ok "Imports verified"

if (Test-Path "src/tests/unit/rpg/test_phase1212_flux_klein_runtime.py") {
    Step "Running image runtime regression test"
    InEnv "python -m pytest src/tests/unit/rpg/test_phase1212_flux_klein_runtime.py -q"
    Ok "Regression test passed"
} else {
    Write-Host "WARN: src/tests/unit/rpg/test_phase1212_flux_klein_runtime.py not found, skipping pytest." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== PASS ===" -ForegroundColor Green
Write-Host "Activate with: conda activate $EnvName"
Write-Host "Then start your app from that env."
Write-Host ""
