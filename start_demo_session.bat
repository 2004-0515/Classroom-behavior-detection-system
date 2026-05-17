@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PYTHON_EXE="
if defined CLASSROOM_PYTHON if exist "%CLASSROOM_PYTHON%" set "PYTHON_EXE=%CLASSROOM_PYTHON%"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%I in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%~fI"
set "APP_FILE=%~dp0app.py"
set "PREVIEW_ONLY=0"
set "APP_HOST=0.0.0.0"
set "APP_PORT=5000"
set "UI_DEFAULT_MODE=image"
set "STUDENT_MODEL_PATH=%~dp0models\behavior.pt"
set "TEACHER_MODEL_PATH=%~dp0models\head.pt"

if /I "%~1"=="--preflight-only" set "PREVIEW_ONLY=1"

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
call "%~dp0demo_preflight.bat"
if errorlevel 1 exit /b %errorlevel%

echo.
echo [INFO] Demo URL: http://127.0.0.1:5000
echo [INFO] Demo startup models: models\behavior.pt + models\head.pt
echo [INFO] Fixed single image: testfile\0014012.jpg
echo [INFO] Fixed batch images: testfile\0009008.jpg, testfile\0009013.jpg, testfile\0009022.jpg
echo [INFO] Fixed video: testfile\QQ202618-01246-HD.mp4

if "%PREVIEW_ONLY%"=="1" (
    echo [INFO] Preflight-only mode complete.
    exit /b 0
)

"%PYTHON_EXE%" "%~dp0scripts\demo_preflight.py" --check-running-demo-entry-contract >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Existing classroom demo app detected on port 5000, and it already matches the demo entry contract. Reusing current service.
    exit /b 0
)

"%PYTHON_EXE%" "%~dp0scripts\demo_preflight.py" --check-running-demo >nul 2>nul
if not errorlevel 1 (
    echo [ERROR] Existing classroom app detected on port 5000, but it does not match the demo entry contract.
    echo [ERROR] Stop the current 5000 service, then rerun start_demo_session.bat.
    exit /b 1
)

echo [INFO] Starting app in foreground. Keep this window open during the demo.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%PYTHON_EXE%" "%APP_FILE%"
exit /b %errorlevel%
