# Culvert Analysis Toolkit Installer for ArcGIS Pro
# This script automates environment setup and installation using the ArcGIS Pro Python Command Prompt

# Default locations
$arcgisPythonCmd = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\activate.bat"
$baseEnv = "arcgispro-py3"
$githubApiUrl = "https://api.github.com/repos/civicmapper/culvert-toolkit/releases/latest"

# Check if ArcGIS Pro Python Command Prompt exists
if (!(Test-Path $arcgisPythonCmd)) {
    Write-Error "ArcGIS Pro Python Command Prompt not found at $arcgisPythonCmd. Please check your installation path."
    exit 1
}

# Get latest release info from GitHub
Write-Host "Fetching latest release info from GitHub..."
$release = Invoke-RestMethod -Uri $githubApiUrl

# Find the wheel asset
$wheel = $release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
if (-not $wheel) {
    Write-Error "No wheel file found in the latest release."
    exit 1
}

$wheelName = $wheel.name
$wheelUrl = $wheel.browser_download_url
$envName = [System.IO.Path]::GetFileNameWithoutExtension($wheelName)

Write-Host "Latest wheel: $wheelName"
Write-Host "Environment name will be: $envName"

# Download the wheel file
Write-Host "Downloading wheel file..."
Invoke-WebRequest -Uri $wheelUrl -OutFile $wheelName

# Build install command string
$installCmd = @"
conda create --name $envName --clone $baseEnv && conda activate $envName && pip install `"$wheelName`"
"@

Write-Host "Launching ArcGIS Pro Python Command Prompt to complete installation..."
Start-Process "cmd.exe" -ArgumentList "/k `"$arcgisPythonCmd $baseEnv && $installCmd`""

Write-Host "A new command prompt window will open. The environment will be cloned, activated, and the toolkit installed."
Write-Host "When finished, restart ArcGIS Pro and verify the Culvert Analysis Toolkit is available."