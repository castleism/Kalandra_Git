@echo off
REM =====================================================================
REM  Kalandra dependency installer (console). Prefer Setup.bat (GUI).
REM =====================================================================
cd /d "%~dp0"
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
%PYEXE% install_dependencies.py %*
echo.
pause
