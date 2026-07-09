@echo off
REM =====================================================================
REM  Kalandra Setup  -  double-click me on a fresh Windows machine.
REM  Detects an existing Kalandra install in THIS folder OR elsewhere on
REM  the machine (via the desktop shortcut) and offers Repair / Uninstall
REM  before doing a fresh install.
REM =====================================================================
cd /d "%~dp0"

set "EXISTING="
set "WHERE=%~dp0"
if exist "data_engine\config.json" set "EXISTING=1"
if exist "data_engine\localized_knowledge.db" set "EXISTING=1"

REM -- Machine-wide check 1: the HKCU install marker (the real record).
if not defined EXISTING (
    for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command ^
        "$d=(Get-ItemProperty -Path 'HKCU:\Software\Kalandra' -ErrorAction SilentlyContinue).InstallPath; if ($d -and (Test-Path (Join-Path $d 'version.py'))) { $d }"`) do set "OTHER=%%K"
)
REM -- Machine-wide check 2: does the desktop shortcut point at another copy?
if not defined EXISTING if not defined OTHER (
    for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command ^
        "$p=[Environment]::GetFolderPath('Desktop')+'\Kalandra.lnk'; if (Test-Path $p) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($p); $d=$s.WorkingDirectory; if ($d -and (Test-Path (Join-Path $d 'version.py'))) { $d } }"`) do set "OTHER=%%K"
)
if defined OTHER (
    if /i not "%OTHER%\"=="%~dp0" (
        set "EXISTING=1"
        set "WHERE=%OTHER%"
    )
)

if defined EXISTING (
    echo.
    echo  An existing Kalandra installation was detected:
    echo    %WHERE%
    echo.
    echo    [R] Repair / Uninstall it  ^(walks add-ons, data, then the app^)
    echo    [I] Fresh install here anyway
    echo.
    choice /c RI /n /m "Repair-Uninstall, or Install? [R/I]: "
    if errorlevel 2 goto :install
    if exist "%WHERE%\installer\Kalandra-Uninstall.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%WHERE%\installer\Kalandra-Uninstall.ps1"
    ) else (
        echo That copy has no uninstaller ^(older version^) - remove it
        echo manually or run its own Setup.bat.
    )
    echo.
    echo Done. Re-run Setup.bat afterwards if you want a fresh install.
    pause
    exit /b 0
)

:install
REM Prefer the wizard exe (it must run FROM its folder - onedir exes need
REM their _internal\ beside them); fall back to the PowerShell installer.
if exist "%~dp0Kalandra-Setup\Kalandra-Setup.exe" (
    start "" "%~dp0Kalandra-Setup\Kalandra-Setup.exe"
    exit /b 0
)
echo Starting the Kalandra installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Kalandra-Setup.ps1"
if errorlevel 1 (
    echo.
    echo The installer exited with an error. See the messages above.
    pause
)
