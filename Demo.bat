@echo off
rem Simulated data, no iRacing needed. Runs alongside the real HUD. Quit from its tray icon.
cd /d "%~dp0"
start "" pythonw hud.py --demo
