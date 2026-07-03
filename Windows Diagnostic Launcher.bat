@echo off
cd /d "%~dp0"

echo =========================================================
echo          KALANDRA OVERLAY DESKTOP LAUNCHER
echo =========================================================
echo.
echo Active Directory: %CD%
echo.

:: -------------------------------------------------------------------
:: Choose a Python interpreter.
:: Prefer the python.org "py" launcher pinned to 3.12 (avoids the
:: Microsoft Store Python shadowing problem). Fall back to plain python.
:: -------------------------------------------------------------------
set "PYEXE="

REM Prefer the winget per-user Python (where Setup installs the packages).
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto FOUND
)

py -3.12 --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PYEXE=py -3.12"
    goto FOUND
)

py -3 --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PYEXE=py -3"
    goto FOUND
)

python --version >nul 2>nul
if %errorlevel% equ 0 (
    set "PYEXE=python"
    goto FOUND
)

echo [CRITICAL ERROR] No Python interpreter found!
echo.
echo Install Python 3.12 from python.org, OR run in a terminal:
echo     winget install -e --id Python.Python.3.12
echo.
echo Be sure to check "[x] Add python.exe to PATH" if using the installer.
goto ERROR_PAUSE

:FOUND
echo [1/2] Using interpreter: %PYEXE%
%PYEXE% --version
echo.

echo [2/2] Running Kalandra Mirror Application...
echo.
%PYEXE% main.py

if %errorlevel% neq 0 (
    echo.
    echo [CRITICAL ERROR] The application crashed during runtime.
    goto ERROR_PAUSE
)

echo.
echo Application closed cleanly by user.
goto END

:ERROR_PAUSE
echo.
echo =========================================================
echo          DIAGNOSTIC LAUNCHER CONSOLE PAUSED
echo =========================================================
echo Review the traceback printed above.
echo.
echo Press any key to close this terminal...
pause > nul

:END
