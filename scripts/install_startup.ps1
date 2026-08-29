param(
    [string]$TaskName = "OceanEngineProjectMonitor",
    [string]$BaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
$Watchdog = Join-Path $BaseDir "scripts\watchdog.bat"
$DesktopApp = Join-Path $BaseDir "建项目监控.exe"
$StartupCmdName = "$TaskName.cmd"
$StartupCmd = Join-Path ([Environment]::GetFolderPath("Startup")) $StartupCmdName

if ((-not (Test-Path -LiteralPath $DesktopApp)) -and (-not (Test-Path -LiteralPath $Watchdog))) {
    throw "watchdog not found: $Watchdog"
}

if (Test-Path -LiteralPath $DesktopApp) {
    $Action = New-ScheduledTaskAction -Execute $DesktopApp -Argument "--worker --base-dir `"$BaseDir`"" -WorkingDirectory $BaseDir
    $LaunchMode = "desktop app"
} else {
    $Action = New-ScheduledTaskAction -Execute "$env:ComSpec" -Argument "/c call `"$Watchdog`"" -WorkingDirectory $BaseDir
    $LaunchMode = "legacy watchdog"
}

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Auto start OceanEngine project monitor watchdog on Windows logon." `
        -Force | Out-Null

    Write-Host "startup_task_installed=true"
    Write-Host "startup_folder_installed=false"
    Write-Host "task_name=$TaskName"
    Write-Host "base_dir=$BaseDir"
    Write-Host "launch_mode=$LaunchMode"
    Write-Host "mode=scheduled task, run when current Windows user logs on"
    exit 0
} catch {
    if (Test-Path -LiteralPath $DesktopApp) {
        $Lines = @("@echo off", "start `"`" /min `"$DesktopApp`" --worker --base-dir `"$BaseDir`"")
    } else {
        $Lines = @("@echo off", "cd /d `"$BaseDir`"", "call `"$Watchdog`"")
    }
    Set-Content -LiteralPath $StartupCmd -Value $Lines -Encoding ASCII
    Write-Host "startup_task_installed=false"
    Write-Host "startup_task_error=$($_.Exception.Message)"
    Write-Host "startup_folder_installed=true"
    Write-Host "startup_file=$StartupCmd"
    Write-Host "base_dir=$BaseDir"
    Write-Host "launch_mode=$LaunchMode"
    Write-Host "mode=Windows Startup folder, run when current Windows user logs on"
}
