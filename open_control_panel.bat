@echo off
setlocal
cd /d "%~dp0"
title Auto Job Applier - Control Panel Server
if not exist ".venv\Scripts\python.exe" (
    echo The Python environment is missing. Running the setup launcher...
    call start.bat
    exit /b
)
echo Starting the control panel. Keep this window open.
echo Use the FULL address printed below, including the port number.
echo Example: http://127.0.0.1:5000
set "PANEL_OPEN_BROWSER=1"
".venv\Scripts\python.exe" -u app.py
set "SERVER_EXIT=%ERRORLEVEL%"
echo.
echo The control panel server stopped. Exit code: %SERVER_EXIT%
echo If an error appears above, copy it when requesting help.
pause
exit /b %SERVER_EXIT%
