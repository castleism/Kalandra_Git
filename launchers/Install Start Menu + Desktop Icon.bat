@echo off
REM Registers Kalandra as a proper installed Windows program:
REM   - a Start Menu entry (so it shows up when you search from the Start button)
REM   - an Apps & Features listing (Settings > Apps > Installed apps)
REM   - a Desktop shortcut
REM No administrator rights needed. Safe to run again any time to repair.
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\installer\Make-Shortcut.ps1"
echo.
echo Done. Press the Start button and type "Kalandra" to launch it.
pause
