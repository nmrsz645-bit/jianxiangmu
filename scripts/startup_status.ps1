param(
    [string]$TaskName = "OceanEngineProjectMonitor",
    [string]$BaseDir = ""
)

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$StartupCmd = Join-Path ([Environment]::GetFolderPath("Startup")) "$TaskName.cmd"
if ($null -eq $Task) {
    Write-Host "startup_task_exists=false"
} else {
    $Info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "startup_task_exists=true"
    Write-Host "state=$($Task.State)"
    Write-Host "last_run_time=$($Info.LastRunTime)"
    Write-Host "last_task_result=$($Info.LastTaskResult)"
    Write-Host "next_run_time=$($Info.NextRunTime)"
}

Write-Host "task_name=$TaskName"
Write-Host "startup_folder_file_exists=$((Test-Path -LiteralPath $StartupCmd))"
Write-Host "startup_file=$StartupCmd"
