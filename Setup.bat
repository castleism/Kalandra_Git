@echo off
REM =====================================================================
REM  Kalandra Setup  -  double-click me on a fresh Windows machine.
REM  Launches the PowerShell GUI installer (no admin required; Python is
REM  installed per-user). If Windows blocks the script, this bypasses the
REM  execution policy for THIS run only.
REM =====================================================================
cd /d "%~dp0"
echo Starting the Kalandra installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Kalandra-Setup.ps1"
if errorlevel 1 (
    echo.
    echo The installer exited with an error. See the messages above.
    pause
)
