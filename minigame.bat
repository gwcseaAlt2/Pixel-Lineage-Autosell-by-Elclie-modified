@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up .venv...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error
)

".venv\Scripts\python.exe" minigame.py %*
echo.
pause
exit /b

:error
echo Setup failed. Make sure Python is installed and on PATH.
pause
exit /b 1
