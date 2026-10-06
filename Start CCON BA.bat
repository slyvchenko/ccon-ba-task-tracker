@echo off
setlocal
cd /d "%~dp0"
if exist ".python-path" (
  set /p DESK_PYTHON=<".python-path"
  goto custom
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 server.py --open
  goto end
)
python --version >nul 2>&1
if not errorlevel 1 (
  python server.py --open
  goto end
)
set "DESK_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
:custom
if exist "%DESK_PYTHON%" (
  "%DESK_PYTHON%" server.py --open
) else (
  echo Python 3.10+ is required. Install Python from python.org, then run this file again.
)
:end
pause
