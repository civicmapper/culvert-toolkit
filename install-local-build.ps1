# Culvert Analysis Toolkit Dev Setup for ArcGIS Pro
# PowerShell version of setup-for-arcgispro.bat

$conda = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe"
$baseEnv = "arcgispro-py3"
$devEnv = "culvert-toolkit-dev"
$requirements = "setup/requirements.txt"
$pipRequirements = "setup/pip-requirements.txt"

Write-Host "Installing Culvert Analysis Toolkit for ArcGIS Pro..."

& $conda config --add channels conda-forge
& $conda config --add channels esri
# & $conda config --set channel_priority strict

Write-Host "Cloning the base ArcGIS Pro Anaconda Python environment..."
& $conda create --clone $baseEnv --name $devEnv --verbose

Write-Host "Installing additional dependencies via conda..."
if (Test-Path $requirements) {
    Get-Content $requirements | ForEach-Object {
        & $conda install --name $devEnv --yes --verbose $_
    }
}

Write-Host "Installing additional dependencies via pypi..."
if (Test-Path $pipRequirements) {
    Get-Content $pipRequirements | ForEach-Object {
        & $conda run -n $devEnv pip install $_
    }
}

Write-Host "Done!"
