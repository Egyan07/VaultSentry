@echo off
:: =============================================================================
::   Install_VaultSentry.bat — VaultSentry v1.0
::   Egyan | Red Parrot Accounting Ltd
::
::   Installs VaultSentry as a nightly Windows Scheduled Task.
::   Run as Administrator.
:: =============================================================================

title VaultSentry Installer
echo.
echo ============================================================
echo   VaultSentry v1.0 Installer
echo   Red Parrot Accounting Ltd
echo ============================================================
echo.

:: Check for admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Please run as Administrator.
    pause
    exit /b 1
)

set SCRIPT_DIR=%~dp0
set PYTHON=python
set MAIN=%SCRIPT_DIR%main.py
set LOG_DIR=C:\SecurityLogs\VaultSentry

:: Create log directory
echo [1] Creating log directory...
mkdir "%LOG_DIR%" 2>nul
mkdir "%LOG_DIR%\Reports" 2>nul

:: Install dependencies
echo [2] Installing Python dependencies...
%PYTHON% -m pip install openpyxl --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Could not install openpyxl. Excel reports will be disabled.
)

:: Build baseline
echo [3] Running baseline (first-time hash)...
%PYTHON% "%MAIN%" --baseline
if %errorlevel% neq 0 (
    echo [ERROR] Baseline failed. Check config.py and backup paths.
    pause
    exit /b 1
)

:: Create nightly scheduled task (2:00 AM daily)
echo [4] Creating scheduled task (nightly at 02:00)...
schtasks /create /f /tn "VaultSentry Nightly Verify" ^
    /tr "\"%PYTHON%\" \"%MAIN%\" --verify" ^
    /sc daily /st 02:00 /ru SYSTEM ^
    /rl HIGHEST >nul

if %errorlevel% neq 0 (
    echo [WARNING] Could not create scheduled task. Run manually instead.
) else (
    echo [OK] Scheduled task created.
)

echo.
echo ============================================================
echo   Installation complete.
echo   VaultSentry will verify backups nightly at 02:00.
echo   Launch GUI: python main.py --gui
echo   Manual verify: python main.py --verify
echo   Logs: %LOG_DIR%
echo ============================================================
echo.
pause
