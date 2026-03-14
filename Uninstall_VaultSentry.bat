@echo off
:: =============================================================================
::   Uninstall_VaultSentry.bat — VaultSentry v1.0
::   Egyan | Red Parrot Accounting Ltd
:: =============================================================================

title VaultSentry Uninstaller
echo.
echo ============================================================
echo   VaultSentry v1.0 Uninstaller
echo   Red Parrot Accounting Ltd
echo ============================================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Please run as Administrator.
    pause
    exit /b 1
)

echo [1] Removing scheduled task...
schtasks /delete /f /tn "VaultSentry Nightly Verify" >nul 2>&1
echo [OK] Scheduled task removed.

echo [2] Log files and database preserved at C:\SecurityLogs\VaultSentry\
echo     Delete manually if no longer needed.

echo.
echo ============================================================
echo   VaultSentry has been uninstalled.
echo ============================================================
echo.
pause
