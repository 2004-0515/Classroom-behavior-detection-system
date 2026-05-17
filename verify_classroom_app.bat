@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHON_EXE="
if defined CLASSROOM_PYTHON if exist "%CLASSROOM_PYTHON%" set "PYTHON_EXE=%CLASSROOM_PYTHON%"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%I in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%~fI"

if not defined PYTHON_EXE (
    echo [ERROR] Missing Python runtime. Set CLASSROOM_PYTHON, prepare .venv, or ensure python is on PATH.
    exit /b 1
)

"%PYTHON_EXE%" -V >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python runtime is not executable: "%PYTHON_EXE%"
    exit /b 1
)

set "CLASSROOM_PYTHON=%PYTHON_EXE%"
"%PYTHON_EXE%" "%~dp0scripts\verify_all.py"
exit /b %errorlevel%
