@echo off
set SCRIPT_DIR=%~dp0

if not exist "%SCRIPT_DIR%venv" (
    echo ERROR: Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call "%SCRIPT_DIR%venv\Scripts\activate.bat"
python "%SCRIPT_DIR%app\main.py" %*
