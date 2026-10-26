@echo off
setlocal
cd /d "%~dp0"
set "DESK_OPEN=--open"
if /I "%~1"=="--scheduled" set "DESK_OPEN="
if exist ".python-path" (
  set /p DESK_PYTHON=<".python-path"
  goto custom
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 server.py %DESK_OPEN%
  goto end
)
python --version >nul 2>&1
if not errorlevel 1 (
  python server.py %DESK_OPEN%
  goto end
)
set "DESK_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
:custom
if exist "%DESK_PYTHON%" (
  "%DESK_PYTHON%" server.py %DESK_OPEN%
  goto end
)
echo Python 3.10+ is required. Install Python from python.org, then run this file again.
set "DESK_EXIT_CODE=1"
goto finish
:end
set "DESK_EXIT_CODE=%ERRORLEVEL%"
:finish
if /I not "%~1"=="--scheduled" pause
exit /b %DESK_EXIT_CODE%

