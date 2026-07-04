@echo off
REM =====================================================================
REM  Kalandra  -  double-click to open the overlay (no console window).
REM  Uses pythonw.exe so it launches silently. If you need to SEE logs for
REM  troubleshooting, use "Windows Diagnostic Launcher.bat" instead.
REM =====================================================================
cd /d "%~dp0.."
set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not defined PYW where pythonw.exe >nul 2>nul && set "PYW=pythonw.exe"
if not defined PYW (
    REM no pythonw found - fall back to python (shows a console)
    start "" python main.py
    goto :eof
)
start "" "%PYW%" main.py
