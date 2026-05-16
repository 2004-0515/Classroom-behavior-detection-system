@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "APP_HOST=%APP_HOST%"
set "APP_PORT=%APP_PORT%"
if not defined APP_HOST set "APP_HOST=0.0.0.0"
if not defined APP_PORT set "APP_PORT=5000"

set "OUT_LOG=%~dp0outputs\classroom_app.out.log"
set "ERR_LOG=%~dp0outputs\classroom_app.err.log"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "APP_FILE=%~dp0app.py"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Missing Python runtime: "%PYTHON_EXE%"
    exit /b 1
)

if not exist "%~dp0outputs" mkdir "%~dp0outputs"

echo.>> "%OUT_LOG%"
echo [%date% %time%] starting classroom app>> "%OUT_LOG%"
echo [%date% %time%] starting classroom app>> "%ERR_LOG%"

set "DISPLAY_HOST=%APP_HOST%"
if /I "%DISPLAY_HOST%"=="0.0.0.0" set "DISPLAY_HOST=127.0.0.1"
if /I "%DISPLAY_HOST%"=="::" set "DISPLAY_HOST=127.0.0.1"

echo [INFO] Starting classroom app
echo [INFO] URL: http://%DISPLAY_HOST%:%APP_PORT%
echo [INFO] Stdout log: outputs\classroom_app.out.log
echo [INFO] Stderr log: outputs\classroom_app.err.log

"%PYTHON_EXE%" "%APP_FILE%" 1>> "%OUT_LOG%" 2>> "%ERR_LOG%"
exit /b %errorlevel%
