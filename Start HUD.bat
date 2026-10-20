@echo off
rem Starts the HUD with no console window. If it's already running, this opens its settings instead.
cd /d "%~dp0"
start "" pythonw hud.py
