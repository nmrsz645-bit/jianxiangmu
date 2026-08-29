@echo off
chcp 65001 >nul
echo Setting Windows AC power mode: no sleep, no hibernate, no monitor/disk timeout...
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /hibernate off
echo.
echo Done. If access is denied, right-click this file and run as administrator.
pause
