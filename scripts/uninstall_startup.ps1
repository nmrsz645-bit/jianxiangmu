param(
    [string]$TaskName = "OceanEngineProjectMonitor",
    [string]$BaseDir = ""
)

$ErrorActionPreference = "Stop"
$StartupCmd = Join-Path ([Environment]::GetFolderPath("Startup")) "$TaskName.cmd"
$Removed = $false

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $Task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    $Removed = $true
    Write-Host "startup_task_removed=true"
} else {
    Write-Host "startup_task_removed=false"
}

if (Test-Path -LiteralPath $StartupCmd) {
    Remove-Item -LiteralPath $StartupCmd -Force
    $Removed = $true
    Write-Host "startup_folder_file_removed=true"
    Write-Host "startup_file=$StartupCmd"
} else {
    Write-Host "startup_folder_file_removed=false"
}

Write-Host "task_name=$TaskName"
Write-Host "removed_any=$Removed"
