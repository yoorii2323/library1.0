@echo off
REM Keep ASCII-only output to avoid encoding issues in cmd/PowerShell
setlocal enabledelayedexpansion

REM Move to backend folder relative to this script
pushd "%~dp0backend" || (
  echo ERROR: Unable to change directory to backend.
  pause
  exit /b 1
)

echo ========================================
echo Starting Library Catalog server
echo ========================================
echo.

echo Looking for Python...
set "PY_CMD="

REM Prefer Windows launcher
where py >nul 2>&1 && set "PY_CMD=py -3"

REM Fallback to python
if not defined PY_CMD (
  where python >nul 2>&1 && set "PY_CMD=python"
)

REM Fallback to python3
if not defined PY_CMD (
  where python3 >nul 2>&1 && set "PY_CMD=python3"
)

if not defined PY_CMD (
  echo ERROR: Python not found in PATH.
  echo Please install Python from https://www.python.org/downloads/ and check "Add to PATH".
  echo Also disable Windows App Execution Aliases for Python if necessary.
  pause
  exit /b 1
)

for /f "usebackq tokens=*" %%v in (`%PY_CMD% --version 2^>^&1`) do set "_PY_VER=%%v"
echo Found: !_PY_VER!

echo Checking dependencies...
%PY_CMD% -m pip show beautifulsoup4 >nul 2>&1
if errorlevel 1 (
  echo Installing/updating dependencies...
  %PY_CMD% -m pip install -r requirements.txt || (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
  )
) else (
  echo All dependencies are installed.
)

echo.
echo Launching server at http://localhost:5000
echo Press Ctrl+C to stop.
echo.

%PY_CMD% app.py

popd
endlocal
pause

