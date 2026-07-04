@echo off
REM =====================================================================
REM  Kalandra - Update Database (standalone; overlay need NOT be open)
REM =====================================================================
cd /d "%~dp0.."
set "PYEXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE ( py -3.12 --version >nul 2>nul && set "PYEXE=py -3.12" )
if not defined PYEXE ( py -3 --version >nul 2>nul && set "PYEXE=py -3" )
if not defined PYEXE ( python --version >nul 2>nul && set "PYEXE=python" )
if not defined PYEXE (
    echo [ERROR] Python not found. Run Setup.bat first to install it.
    pause
    goto :eof
)
echo Using Python: %PYEXE%
%PYEXE% scripts\update_db.py
echo.
pause
