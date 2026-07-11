@echo off
REM Registers Kalandra as an installed program: Start Menu (searchable),
REM Apps & Features, and a Desktop shortcut. (Kept under the old name so
REM existing docs/links still work; it now does the full registration.)
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\installer\Make-Shortcut.ps1"
echo.
echo Done. Press the Start button and type "Kalandra" to launch it.
pause
