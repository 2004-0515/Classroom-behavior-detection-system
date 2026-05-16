@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Missing Python runtime: "%PYTHON_EXE%"
    exit /b 1
)

"%PYTHON_EXE%" "%~dp0scripts\real_demo_service_audit.py"
exit /b %errorlevel%
