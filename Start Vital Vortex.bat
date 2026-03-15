@echo off
title Vital Vortex
echo.
echo   Starting Vital Vortex...
echo   Keep this window open while using the app.
echo.
python server.py
if errorlevel 1 (
    echo.
    echo   Python not found. Please install Python from https://python.org
    pause
)
