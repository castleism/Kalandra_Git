@echo off
REM =====================================================================
REM  Kalandra - one-time cleanup: move the INSTALLED Path of Building app
REM  out of the source-code clone (tools\PathOfBuildingCommunity-...\)
REM  up to tools\, then update data_engine\config.json to match.
REM  Native move = instant same-volume rename. Close PoB before running.
REM =====================================================================
cd /d "%~dp0.."
set "SRC=tools\PathOfBuildingCommunity-PathOfBuilding-PoE2\Path of Building Community (PoE2)"
set "DST=tools\Path of Building Community (PoE2)"

if not exist "%SRC%" (
    echo Nothing to move: "%SRC%" not found ^(already relocated?^).
    pause
    exit /b 0
)
if exist "%DST%" (
    echo Destination already exists: "%DST%" - not overwriting.
    pause
    exit /b 1
)

echo Moving the installed PoB app out of the source clone...
move "%SRC%" "%DST%" >nul
if errorlevel 1 (
    echo MOVE FAILED - is Path of Building running? Close it and try again.
    pause
    exit /b 1
)

echo Updating data_engine\config.json paths...
set "PYEXE=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
"%PYEXE%" -c "import json,os; p='data_engine/config.json'; c=json.load(open(p,encoding='utf-8')); root=os.path.abspath('.'); new=os.path.join(root,'tools','Path of Building Community (PoE2)'); c['pob_install_dir']=new; c['pob_exe']=os.path.join(new,'Path of Building-PoE2.exe'); b=os.path.join(new,'Builds'); c.update({'pob_builds_dir':b} if os.path.isdir(b) else {}); json.dump(c,open(p,'w',encoding='utf-8'),indent=2); print('config updated:', new)"
if errorlevel 1 (
    echo Config update failed - set pob_install_dir / pob_exe manually in
    echo data_engine\config.json to the new tools\Path of Building... folder.
)

echo.
echo Done. The source clone stays at tools\PathOfBuildingCommunity-...
echo (the headless sim uses it); the app now lives at "%DST%".
pause
