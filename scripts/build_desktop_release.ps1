param(
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "release")
)

$ErrorActionPreference = "Stop"
$BaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$VersionPath = Join-Path $BaseDir "release_template\version.json"
$Version = ([System.IO.File]::ReadAllText($VersionPath, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json).version
$ReleaseDir = Join-Path $OutputDir "建项目监控-$Version"

if (Test-Path -LiteralPath $ReleaseDir) {
    throw "release directory already exists: $ReleaseDir"
}

$WorkDir = Join-Path $BaseDir ("build\desktop-release-" + [guid]::NewGuid().ToString("N"))
$DistDir = Join-Path $WorkDir "dist"
$PushedLocation = $false
try {
    New-Item -ItemType Directory -Path $WorkDir, $OutputDir -Force | Out-Null
    Push-Location $BaseDir
    $PushedLocation = $true
    & python -m PyInstaller --noconfirm --clean --windowed --name "建项目监控" --distpath $DistDir --workpath (Join-Path $WorkDir "work") --specpath (Join-Path $WorkDir "spec") --paths $BaseDir --hidden-import app.project_monitor --hidden-import app.status_panel app\manager_gui.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    Pop-Location
    $PushedLocation = $false

    New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $DistDir "建项目监控") -Destination $ReleaseDir -Recurse
    Copy-Item -LiteralPath (Join-Path $BaseDir "scripts") -Destination (Join-Path $ReleaseDir "scripts") -Recurse
    Copy-Item -LiteralPath (Join-Path $BaseDir "release_template\使用说明.txt") -Destination $ReleaseDir
    Copy-Item -LiteralPath (Join-Path $BaseDir "release_template\version.json") -Destination $ReleaseDir
    Write-Host "release_dir=$ReleaseDir"
    Write-Host "copy_the_entire_directory=true"
} finally {
    if ($PushedLocation) {
        Pop-Location
    }
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
}
