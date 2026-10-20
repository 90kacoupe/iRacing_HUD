@echo off
rem Restarts the HUD with a console window so any errors can be seen. Close this window to stop it.
cd /d "%~dp0"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*dash_overlay.py*' -or $_.CommandLine -like '*side_indicator.py*' -or $_.CommandLine -like '*hud.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 2 /nobreak >nul
python hud.py
echo.
echo The HUD stopped. Any error is shown above (older ones are in %APPDATA%\SimRacingHUD\hud.log).
pause
