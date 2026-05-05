@echo off
setlocal enabledelayedexpansion

:: 1. Ensure we are operating relative to the script's location
:: %~dp0 is the Batch equivalent of $(dirname "$0")
cd /d "%~dp0"

echo [*] Initializing Python environment in %CD%

:: 2. Set Vendored Path
:: Note: Windows uses backslashes, but Python usually handles both.
:: We use backslashes here for native CMD compatibility.
set "VENDORED_ROOT=..\..\vendor\python"
set "PYTHON_BIN=%VENDORED_ROOT%\win_x64\python.exe"

:: 3. Verify Vendored Binary Exists
if not exist "%PYTHON_BIN%" (
    echo [!] Error: Vendored Python not found at: %PYTHON_BIN%
    echo [!] Please ensure the standalone Python distribution is placed in the vendor directory.
    pause
    exit /b 1
)

:: Display Python version
echo [*] Using Vendored Python:
"%PYTHON_BIN%" --version

:: 4. Create Virtual Environment if it doesn't exist
if not exist ".venv" (
    echo [*] Creating .venv using vendored interpreter...
    "%PYTHON_BIN%" -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [!] Error: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [*] .venv already exists. Skipping creation.
)

:: 5. Install/Update Dependencies
set "VENV_PYTHON=.venv\Scripts\python.exe"

if exist "requirements.txt" (
    echo [*] Installing dependencies from requirements.txt...

    :: Upgrade pip first
    "%VENV_PYTHON%" -m pip install --upgrade pip

    :: Install requirements
    "%VENV_PYTHON%" -m pip install -r requirements.txt

    if %ERRORLEVEL% neq 0 (
        echo [!] Error: Failed to install requirements.
        pause
        exit /b 1
    )
) else (
    echo [!] Warning: requirements.txt not found. No libraries installed.
)

echo [*] Setup Complete. Your AnitoScan Python environment is ready.
pause
