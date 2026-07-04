@echo off
REM Builds a shareable Kalandra-Setup.zip on your Desktop.
REM Excludes ALL personal data (data_engine: config/keys/profile/chats),
REM .env, .git, and the multi-GB tools folder — then re-scans the archive
REM for key-shaped strings and refuses to finish if any are found.
cd /d "%~dp0.."
set "PYEXE=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
%PYEXE% scripts\make_release_zip.py
pause
