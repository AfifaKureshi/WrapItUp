@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  set PY_CMD=py -3
) else (
  where python >nul 2>nul
  if not errorlevel 1 (
    set PY_CMD=python
  ) else (
    echo Python was not found. Install Python 3.12 or newer and enable the PATH option.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local Python environment...
  %PY_CMD% -m venv .venv
  if errorlevel 1 exit /b 1
  echo Installing backend dependencies...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements-dev.txt
  if errorlevel 1 exit /b 1
)

set DATABASE_URL=sqlite:///./packwise-dev.db
set SEED_DEMO=true
set DEMO_PASSWORD=PackWiseDemo123!
set SECRET_KEY=local-development-only-secret-with-32-characters

cd backend
"..\.venv\Scripts\python.exe" scripts\dev_bootstrap.py

set DATABASE_URL=sqlite:///./packwise-dev.db
set SEED_DEMO=true
set DEMO_PASSWORD=PackWiseDemo123!
set SECRET_KEY=local-development-only-secret-with-32-characters
echo Starting PackWise API at http://0.0.0.0:8000 (accessible via localhost, 10.0.2.2 for Android emulators, or your local Wi-Fi IP for physical phones)
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
