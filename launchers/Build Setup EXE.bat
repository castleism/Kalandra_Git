@echo off
REM Builds the Kalandra Setup wizard (onedir; the onefile bootloader threw
REM "ordinal not found" on this machine). Icon passed as an ABSOLUTE path:
REM --specpath makes relative paths resolve against the spec dir, which is
REM why the release build died with "Icon input file ... not found".
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PYEXE=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
%PYEXE% -m pip install pyinstaller --quiet
if not exist "build" mkdir build
if exist "Kalandra-Setup.exe" del /q "Kalandra-Setup.exe"
if exist "Kalandra-Setup" rmdir /s /q "Kalandra-Setup"

echo === [1/2] RELEASE build (onedir, windowed, owl icon) ===
%PYEXE% -m PyInstaller --onedir --windowed --noupx --clean --noconfirm --name Kalandra-Setup ^
    --icon "%ROOT%\gui_overlay\assets\kalandra.ico" ^
    --distpath . --workpath "build\pyi" --specpath "build\pyi" ^
    installer\setup_wizard.py

echo.
echo === [2/2] DEBUG build (onedir, console - shows real errors) ===
%PYEXE% -m PyInstaller --onedir --console --noupx --clean --noconfirm --name Kalandra-Setup-Debug ^
    --distpath "build\debug" --workpath "build\pyi-dbg" --specpath "build\pyi-dbg" ^
    installer\setup_wizard.py

echo.
if exist "Kalandra-Setup\Kalandra-Setup.exe" (
    echo Release: Kalandra-Setup\Kalandra-Setup.exe  ^(run THAT exe^)
) else (echo RELEASE BUILD FAILED - see output above)
if exist "build\debug\Kalandra-Setup-Debug\Kalandra-Setup-Debug.exe" (
    echo Debug:   build\debug\Kalandra-Setup-Debug\Kalandra-Setup-Debug.exe
)
pause
