@echo off
title Vital Vortex — Save Snapshot
cd /d "C:\Vital Vortex"
git add -A
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set d=%%b-%%c-%%d
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set t=%%a:%%b
git commit -m "Session snapshot %d% %t%"
if errorlevel 1 (
    echo.
    echo   Nothing new to save, or something went wrong.
) else (
    echo.
    echo   Snapshot saved!
)
echo.
pause
