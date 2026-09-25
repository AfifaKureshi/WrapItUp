@echo off
setlocal
cd /d "%~dp0"
echo Start the backend in one Command Prompt with run_backend_windows.bat.
echo Start the Flutter client in a second Command Prompt with run_frontend_windows.bat.
start "PackWise Backend" cmd /k "%~dp0run_backend_windows.bat"
timeout /t 3 /nobreak >nul
start "PackWise Flutter" cmd /k "%~dp0run_frontend_windows.bat"
