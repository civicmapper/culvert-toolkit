# Culvert Analysis Toolkit Build Script (PowerShell)
# This script builds the project in the 'culvert-toolkit-dev' conda environment.

$conda = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe"
$devEnv = "culvert-toolkit-dev"
$installScript = "install-local-build.ps1"

# Check if the environment exists
$envExists = & $conda env list | Select-String $devEnv
Write-Host "Checking for conda environment '$devEnv'..."
Write-Host $envExists
if (-not $envExists) {
    Write-Host "Conda environment '$devEnv' not found. Running $installScript to create it..."
    & powershell -ExecutionPolicy Bypass -File $installScript
    # Re-check if the environment exists after running install
    $envExists = & $conda env list | Select-String $devEnv
    if (-not $envExists) {
        Write-Error "Failed to create conda environment '$devEnv'. Exiting build."
        exit 1
    }
}

Write-Host "Running build steps in '$devEnv' environment..."

# Run make_tbx_files.py
& $conda run -n $devEnv python setup/make_tbx_files.py

# Upgrade build package
& $conda run -n $devEnv python -m pip install --upgrade build

# Build the project
& $conda run -n $devEnv python -m build

Write-Host "Build complete!"