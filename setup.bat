@echo off
rem One-time setup. Safe to run again (e.g. after an update).
cd /d "%~dp0"
echo Closing the old separate dash and side indicator, and any running HUD...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*dash_overlay.py*' -or $_.CommandLine -like '*side_indicator.py*' -or $_.CommandLine -like '*hud.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo.
echo Installing the Python packages the HUD needs (pyirsdk, PySide6)...
python -m pip install --upgrade pyirsdk PySide6
if errorlevel 1 (
  echo.
  echo Python was not found. Install it from python.org, tick "Add Python to PATH", then run this again.
  pause
  exit /b 1
)
echo.
python hud.py --install-startup
echo.
echo Starting the HUD now. Look for its icon in the tray (bottom right of the taskbar).
start "" pythonw hud.py
pause
