@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0verify_citywide_preview.ps1"
if errorlevel 1 (
  echo The preview copy is incomplete or changed. Copy the folder again before measuring.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0serve_citywide_preview.ps1"
if errorlevel 1 (
  echo The local preview could not start. See the error above.
  pause
)
