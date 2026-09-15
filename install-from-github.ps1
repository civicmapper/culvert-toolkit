[CmdletBinding()]
param(
    [string]$Version = "latest",
    [string]$EnvironmentName,
    [string]$Conda = "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe",
    [switch]$SkipClone
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = "civicmapper/culvert-toolkit"

function Invoke-Native([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath $Conda)) { throw "ArcGIS Pro conda.exe not found: $Conda" }
$releaseUri = if ($Version -eq "latest") {
    "https://api.github.com/repos/$repo/releases/latest"
} else {
    "https://api.github.com/repos/$repo/releases/tags/$Version"
}

Write-Host "Resolving GitHub release $Version..."
$release = Invoke-RestMethod -Uri $releaseUri -Headers @{ Accept = "application/vnd.github+json" }
$wheel = @($release.assets | Where-Object name -like "*.whl")
if ($wheel.Count -ne 1) { throw "Expected exactly one wheel asset in release $($release.tag_name); found $($wheel.Count)." }
if (-not $EnvironmentName) {
    $safeVersion = $release.tag_name -replace '^v', '' -replace '[^A-Za-z0-9_.-]', '-'
    $EnvironmentName = "culvert-toolkit-$safeVersion"
}

$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("culvert-toolkit-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    $wheelPath = Join-Path $tempDir $wheel[0].name
    Invoke-WebRequest -Uri $wheel[0].browser_download_url -OutFile $wheelPath
    if (-not $SkipClone) {
        Invoke-Native { & $Conda create --clone arcgispro-py3 --name $EnvironmentName --yes }
    }
    Invoke-Native { & $Conda run --name $EnvironmentName python -m pip install $wheelPath }
    Invoke-Native { & $Conda run --name $EnvironmentName python -m pip check }
    Invoke-Native { & $Conda run --name $EnvironmentName python -c "import drainit; print(drainit.__version__)" }
} finally {
    if (Test-Path -LiteralPath $tempDir) { Remove-Item -LiteralPath $tempDir -Recurse -Force }
}

Write-Host "Installed release $($release.tag_name) into $EnvironmentName. Select this environment in ArcGIS Pro."
