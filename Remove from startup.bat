@echo off
rem Stops the HUD starting with Windows. (Quit a running copy from its tray icon.)
cd /d "%~dp0"
python hud.py --remove-startup
pause
