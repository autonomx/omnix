$ErrorActionPreference = "Stop"

$EnvName = "omnix312"
$PythonVersion = "3.12"

Write-Host ""
Write-Host "=== Omnix FLUX environment bootstrap ==="
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

# Ensure conda exists
Step "Checking conda"
$condaCmd = Get-Command conda -ErrorAction SilentlyContinue
if (-not $condaCmd) {
    Fail "conda was not found in PATH. Open an Anaconda/Miniconda shell and run again."
}
Ok "conda found"

# Create env if missing
Step "Checking whether env '$EnvName' already exists"
$envList = conda env list | Out-String
if ($envList -match "(?m)^\s*$EnvName\s") {
    Ok "Environment already exists"
} else {
    Step "Creating conda env '$EnvName' with Python $PythonVersion"
    conda create -n $EnvName python=$PythonVersion -y
    Ok "Environment created"
}

# Helper to run commands inside env
function InEnv($command) {
    conda run -n $EnvName powershell -NoProfile -Command $command
}

Step "Upgrading pip/setuptools/wheel"
InEnv "python -m pip install --upgrade pip setuptools wheel"
Ok "pip toolchain upgraded"

Step "Installing PyTorch CUDA 12.4 wheels"
InEnv "python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124"
Ok "PyTorch installed"

Step "Installing core FLUX runtime dependencies"
InEnv "python -m pip install diffusers transformers accelerate safetensors sentencepiece"
Ok "Core FLUX dependencies installed"

if (Test-Path "requirements.txt") {
    Step "Installing project requirements"
    InEnv "python -m pip install -r requirements.txt"
    Ok "requirements.txt installed"
} else {
    Write-Host "WARN: requirements.txt not found in current directory, skipping." -ForegroundColor Yellow
}

Step "Printing interpreter path"
InEnv "python -c ""import sys; print(sys.executable)"""

Step "Verifying imports"
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
from diffusers import Flux2KleinPipeline
print('Flux2KleinPipeline: OK')
"
'@
Ok "Imports verified"

if (Test-Path "src/tests/unit/rpg/test_phase1212_flux_klein_runtime.py") {
    Step "Running FLUX runtime regression test"
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