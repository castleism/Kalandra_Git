@echo off
REM Kalandra clean uninstaller - walks through keeping/moving/deleting the
REM bundled add-ons (PoB, Obsidian, LuaJIT...), preserving your data, and
REM finally removing the app. Nothing is deleted without asking.
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\installer\Kalandra-Uninstall.ps1"
pause
