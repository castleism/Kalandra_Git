@echo off
REM =====================================================================
REM  Kalandra Setup  -  double-click me on a fresh Windows machine.
REM  Launches the PowerShell GUI installer (no admin required; Python is
REM  installed per-user). If Windows blocks the script, this bypasses the
REM  execution policy for THIS run only.
REM
REM  If an existing Kalandra install is detected (a config/database from a
REM  previous run), it offers REPAIR (via the Uninstall/Repair tool)
REM  before doing a fresh install.
REM =====================================================================
cd /d "%~dp0"

REM -- Existing-install detection: runtime files only exist after a run.
set "EXISTING="
if exist "data_engine\config.json" set "EXISTING=1"
if exist "data_engine\localized_knowledge.db" set "EXISTING=1"
if defined EXISTING (
    echo.
    echo  An existing Kalandra installation was detected on this machine.
    echo.
    echo    [R] Repair it   ^(reinstall deps, fix config, verify tool paths^)
    echo    [U] Uninstall   ^(walk through removing/moving add-ons and data^)
    echo    [I] Fresh install anyway
    echo.
    choice /c RUI /n /m "Repair, Uninstall, or Install? [R/U/I]: "
    if errorlevel 3 goto :install
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Kalandra-Uninstall.ps1"
    echo.
    echo Done. Re-run Setup.bat afterwards if you want a fresh install.
    pause
    exit /b 0
)

:install
echo Starting the Kalandra installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Kalandra-Setup.ps1"
if errorlevel 1 (
    echo.
    echo The installer exited with an error. See the messages above.
    pause
)
