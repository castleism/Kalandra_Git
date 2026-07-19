@echo off
REM =====================================================================
REM  Kalandra Voice installer — free offline neural voice for the Orb.
REM  No account, no API key: downloads the Piper engine (~25 MB) and one
REM  voice model (~63 MB) into tools\piper\ and selects it automatically.
REM
REM  Pick a different voice:   Install Kalandra Voice.bat --voice ryan
REM  See the voice menu:       Install Kalandra Voice.bat --list
REM =====================================================================
cd /d "%~dp0.."
set "PYEXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE ( py -3.12 --version >nul 2>nul && set "PYEXE=py -3.12" )
if not defined PYEXE ( py -3 --version >nul 2>nul && set "PYEXE=py -3" )
if not defined PYEXE ( python --version >nul 2>nul && set "PYEXE=python" )
if not defined PYEXE (
    echo [ERROR] Python not found. Install Python 3.12:  winget install -e --id Python.Python.3.12
    pause
    goto :eof
)
echo Using Python: %PYEXE%
%PYEXE% scripts\install_voice.py %*
echo.
pause
