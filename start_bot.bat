@echo off
rem ============================================================
rem  AquaMark launcher for Windows (RDP / VPS / desktop)
rem  Just double-click this file. It checks the setup, then
rem  starts the bot. Keep the window open; to stop press Ctrl+C.
rem ============================================================
setlocal
cd /d "%~dp0"

rem -- find python (python.exe from python.org, or the py launcher) --
where python >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set "PY=py"
    ) else (
        echo ERROR: Python not found.
        echo Install it from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" during setup.
        pause
        exit /b 1
    )
)

echo === AquaMark - preflight check =============================
%PY% bot.py --check
if errorlevel 1 (
    echo.
    echo Preflight found a problem - fix it, then run this file again.
    pause
    exit /b 1
)

echo.
echo === Starting AquaMark ======================================
echo Close this window or press Ctrl+C to stop the bot.
echo Tip: disconnect RDP with the X button ^(not Sign out^) to keep it running.
echo.
%PY% bot.py
echo.
echo Bot stopped.
pause
