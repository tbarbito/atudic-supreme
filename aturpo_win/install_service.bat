@echo off
REM ============================================================================
REM ATURPO DevOps - Script de Instalação do Serviço Windows (NSSM)
REM Versão: 2.1
REM Data: 2025-12-03
REM ============================================================================

setlocal EnableDelayedExpansion

REM Parâmetros
set "EXE_PATH=%~1"
set "APP_PORT=%~2"
set "ENV_FILE=%~3"

REM Nome do serviço
set "SERVICE_NAME=ATURPODevOpsService"
set "SERVICE_DISPLAY=ATURPO DevOps Service"
set "SERVICE_DESC=Sistema de CI/CD e DevOps para Protheus ERP"

REM Caminho do NSSM (mesmo diretório do instalador)
set "SCRIPT_DIR=%~dp0"
set "NSSM_PATH=%SCRIPT_DIR%nssm.exe"

echo.
echo ============================================================================
echo  ATURPO DevOps - Instalacao do Servico Windows (NSSM)
echo ============================================================================
echo.

REM Verificar se está rodando como administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script requer privilegios de administrador!
    echo        Execute como Administrador.
    echo.
    pause
    exit /b 1
)

REM Verificar se o NSSM existe
if not exist "%NSSM_PATH%" (
    echo [ERRO] NSSM nao encontrado: %NSSM_PATH%
    echo        Copie o nssm.exe para o diretorio de instalacao.
    echo.
    pause
    exit /b 1
)

REM Verificar se o executável existe
if not exist "%EXE_PATH%" (
    echo [ERRO] Executavel nao encontrado: %EXE_PATH%
    echo.
    pause
    exit /b 1
)

echo [INFO] Verificando servico existente...

REM Verificar se o serviço já existe
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] Servico existente encontrado. Removendo...
    
    REM Parar o serviço se estiver rodando
    "%NSSM_PATH%" stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 3 /nobreak >nul
    
    REM Remover o serviço
    "%NSSM_PATH%" remove "%SERVICE_NAME%" confirm >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo [INFO] Criando novo servico com NSSM...

REM Instalar o serviço usando NSSM
"%NSSM_PATH%" install "%SERVICE_NAME%" "%EXE_PATH%"
if %errorLevel% neq 0 (
    echo [ERRO] Falha ao criar o servico!
    echo.
    pause
    exit /b 1
)

echo [OK] Servico criado com sucesso!

REM Configurar nome de exibição
"%NSSM_PATH%" set "%SERVICE_NAME%" DisplayName "%SERVICE_DISPLAY%"

REM Configurar descrição
"%NSSM_PATH%" set "%SERVICE_NAME%" Description "%SERVICE_DESC%"

REM Configurar diretório de trabalho (usar diretório do script - mais confiável)
set "APP_DIR=%~dp0"
REM Remover barra final se existir
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"
"%NSSM_PATH%" set "%SERVICE_NAME%" AppDirectory "%APP_DIR%"

REM Configurar variáveis de ambiente (arquivo .env)
if exist "%ENV_FILE%" (
    "%NSSM_PATH%" set "%SERVICE_NAME%" AppEnvironmentExtra "CONFIG_FILE=%ENV_FILE%"
)

REM Configurar início automático
"%NSSM_PATH%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

REM Configurar saída de logs na pasta da aplicação
set "LOGS_DIR=%~dp0logs"
REM Remover barra duplicada se existir
set "LOGS_DIR=%LOGS_DIR:\\=\%"
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

"%NSSM_PATH%" set "%SERVICE_NAME%" AppStdout "%LOGS_DIR%\service_stdout.log"
"%NSSM_PATH%" set "%SERVICE_NAME%" AppStderr "%LOGS_DIR%\service_stderr.log"
"%NSSM_PATH%" set "%SERVICE_NAME%" AppStdoutCreationDisposition 4
"%NSSM_PATH%" set "%SERVICE_NAME%" AppStderrCreationDisposition 4
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRotateBytes 10485760

REM Configurar ação em caso de falha (reiniciar)
"%NSSM_PATH%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRestartDelay 5000

REM Conceder permissões ao diretório de logs
icacls "%LOGS_DIR%" /grant Users:(OI)(CI)M /T >nul 2>&1

echo [OK] Configuracoes aplicadas!

echo.
echo ============================================================================
echo [OK] Servico instalado com sucesso!
echo ============================================================================
echo.
echo Nome do Servico: %SERVICE_NAME%
echo Display Name: %SERVICE_DISPLAY%
echo Executavel: %EXE_PATH%
echo Logs: %LOGS_DIR%
echo.
echo Para iniciar o servico, execute:
echo    nssm start %SERVICE_NAME%
echo.
echo Para verificar o status:
echo    nssm status %SERVICE_NAME%
echo.
echo ============================================================================
echo.

exit /b 0
