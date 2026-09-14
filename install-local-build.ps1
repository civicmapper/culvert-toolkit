[CmdletBinding()]
param(
    [string]$EnvironmentName = "culvert-toolkit-dev",
    [string]$Conda = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe",
    [switch]$SkipClone,
    [string]$Wheel
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-Native([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath $Conda)) { throw "ArcGIS Pro conda.exe not found: $Conda" }
if (-not $SkipClone) {
    Invoke-Native { & $Conda create --clone arcgispro-py3 --name $EnvironmentName --yes }
}

# Install the wheel when supplied; otherwise install this checkout. Existing
# ArcGIS-bundled compiled packages are retained when they already satisfy the
# project's version-independent requirements.
$installTarget = if ($Wheel) { (Resolve-Path -LiteralPath $Wheel).Path } else { $projectRoot }
Invoke-Native { & $Conda run --name $EnvironmentName python -m pip install $installTarget }
Invoke-Native { & $Conda run --name $EnvironmentName python -m pip check }
Invoke-Native { & $Conda run --name $EnvironmentName python -c "import drainit, drainit.models, drainit.calculators; print(drainit.__version__)" }

Write-Host "Installed $installTarget into $EnvironmentName. Select this environment in ArcGIS Pro."
