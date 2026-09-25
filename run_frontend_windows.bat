@echo off
setlocal
cd /d "%~dp0frontend"
where flutter >nul 2>nul
if errorlevel 1 (
  echo Flutter was not found. Install Flutter, add its bin folder to PATH, then run this file again.
  pause
  exit /b 1
)
if not exist "windows" if not exist "web" if not exist "android" (
  echo Generating Flutter platform runner files...
  flutter create --project-name packwise --org com.packwise .
  if errorlevel 1 exit /b 1
)
flutter pub get
flutter run -d chrome --dart-define=API_URL=http://localhost:8000
