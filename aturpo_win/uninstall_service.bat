@echo off
REM ============================================================================
REM BiizHubOps - Script de Desinstalação do Serviço Windows
REM Versão: 2.2
REM Data: 2026-04-08
REM ============================================================================

setlocal EnableDelayedExpansion

set "SERVICE_NAME=BiizHubOpsService"
set "SCRIPT_DIR=%~dp0"
set "NSSM_PATH=%SCRIPT_DIR%nssm.exe"

echo.
echo ============================================================================
echo  BiizHubOps - Desinstalacao do Servico
echo ============================================================================
echo.

REM Verificar se NSSM existe
if exist "%NSSM_PATH%" (
    echo [INFO] Parando servico...
    "%NSSM_PATH%" stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 3 /nobreak >nul
    
    echo [INFO] Removendo servico...
    "%NSSM_PATH%" remove "%SERVICE_NAME%" confirm >nul 2>&1
) else (
    echo [INFO] Usando sc.exe para remover servico...
    sc stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 3 /nobreak >nul
    sc delete "%SERVICE_NAME%" >nul 2>&1
)

echo [OK] Servico removido!
echo.

exit /b 0
