@echo off
REM Puts a clickable "Kalandra" icon on your Desktop.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Make-Shortcut.ps1"
echo.
echo Done. Look for the "Kalandra" icon on your Desktop.
pause
