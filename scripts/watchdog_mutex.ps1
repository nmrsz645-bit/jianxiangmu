$ErrorActionPreference = "Stop"

$BaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $BaseDir "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$MutexName = "Global\OceanEngineProjectMonitorWatchdog"
$Created = $false
$Mutex = New-Object System.Threading.Mutex($true, $MutexName, [ref]$Created)

if (-not $Created) {
    $Msg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] watchdog already running, skip duplicate start"
    Add-Content -LiteralPath (Join-Path $LogDir "watchdog.log") -Value $Msg
    Write-Host "Project monitor watchdog is already running. Duplicate start skipped."
    exit 0
}

try {
    Add-Content -LiteralPath (Join-Path $LogDir "watchdog.log") -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] watchdog lock acquired"
    & "$PSScriptRoot\watchdog_loop.bat"
    exit $LASTEXITCODE
}
finally {
    try {
        $Mutex.ReleaseMutex()
    } catch {
    }
    $Mutex.Dispose()
}
