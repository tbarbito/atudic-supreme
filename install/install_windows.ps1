# =============================================================================
# 🚀 ATUDIC DEVOPS - INSTALADOR WINDOWS
# =============================================================================
# Instala o sistema como serviço Windows usando NSSM
# Uso: Executar como Administrador
#      .\install_windows.ps1
# =============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🚀 ATUDIC DEVOPS - Instalador Windows" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Variáveis de configuração
$APP_NAME = "ATUDIC-DevOps"
$SERVICE_NAME = "AtudicDevOps"
$INSTALL_DIR = "C:\AtudicDevOps"
$PYTHON_VERSION = "3.11"
$NSSM_VERSION = "2.24"

# Funções auxiliares
function Write-Success {
    param($Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param($Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-InfoMsg {
    param($Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Yellow
}

# Verificar se está rodando como administrador
function Test-Administrator {
    $user = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal $user
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-ErrorMsg "Este script precisa ser executado como Administrador!"
    Write-Host ""
    Write-Host "Clique com botão direito no PowerShell e selecione 'Executar como Administrador'" -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Verificar se Python está instalado
function Test-PythonInstalled {
    Write-Host ""
    Write-Host "🐍 Verificando instalação do Python..." -ForegroundColor Cyan
    Write-Host ""
    
    try {
        $pythonVersion = python --version 2>&1
        if ($pythonVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            
            if ($major -ge 3 -and $minor -ge 9) {
                Write-Success "Python $pythonVersion detectado"
                return $true
            }
        }
    } catch {
        # Python não encontrado
    }
    
    Write-ErrorMsg "Python 3.9+ não encontrado!"
    Write-Host ""
    Write-Host "Por favor, instale o Python:" -ForegroundColor Yellow
    Write-Host "1. Acesse: https://www.python.org/downloads/" -ForegroundColor White
    Write-Host "2. Baixe Python $PYTHON_VERSION ou superior" -ForegroundColor White
    Write-Host "3. Durante a instalação, marque 'Add Python to PATH'" -ForegroundColor White
    Write-Host ""
    
    $install = Read-Host "Deseja abrir o site de download? (S/N)"
    if ($install -eq "S" -or $install -eq "s") {
        Start-Process "https://www.python.org/downloads/"
    }
    
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Verificar PostgreSQL
function Test-PostgreSQLInstalled {
    Write-Host ""
    Write-Host "🐘 Verificando instalação do PostgreSQL..." -ForegroundColor Cyan
    Write-Host ""
    
    $pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
    
    if ($pgService) {
        Write-Success "PostgreSQL detectado"
        return $true
    } else {
        Write-ErrorMsg "PostgreSQL não encontrado!"
        Write-Host ""
        Write-Host "Por favor, instale o PostgreSQL:" -ForegroundColor Yellow
        Write-Host "1. Acesse: https://www.postgresql.org/download/windows/" -ForegroundColor White
        Write-Host "2. Baixe e instale PostgreSQL 13 ou superior" -ForegroundColor White
        Write-Host "3. Anote a senha do usuário 'postgres'" -ForegroundColor White
        Write-Host ""
        
        $install = Read-Host "Deseja abrir o site de download? (S/N)"
        if ($install -eq "S" -or $install -eq "s") {
            Start-Process "https://www.postgresql.org/download/windows/"
        }
        
        Read-Host "Pressione Enter para sair"
        exit 1
    }
}

# Baixar e instalar NSSM
function Install-NSSM {
    Write-Host ""
    Write-Host "📦 Instalando NSSM (Non-Sucking Service Manager)..." -ForegroundColor Cyan
    Write-Host ""
    
    $nssmPath = "C:\Windows\System32\nssm.exe"
    
    if (Test-Path $nssmPath) {
        Write-Success "NSSM já está instalado"
        return $nssmPath
    }
    
    $tempDir = "$env:TEMP\nssm"
    $nssmZip = "$tempDir\nssm.zip"
    $nssmUrl = "https://nssm.cc/release/nssm-$NSSM_VERSION.zip"
    
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    
    Write-InfoMsg "Baixando NSSM de $nssmUrl..."
    Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip
    
    Write-InfoMsg "Extraindo NSSM..."
    Expand-Archive -Path $nssmZip -DestinationPath $tempDir -Force
    
    # Detectar arquitetura
    $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
    $nssmExe = "$tempDir\nssm-$NSSM_VERSION\$arch\nssm.exe"
    
    if (Test-Path $nssmExe) {
        Copy-Item $nssmExe -Destination $nssmPath -Force
        Write-Success "NSSM instalado com sucesso"
        return $nssmPath
    } else {
        Write-ErrorMsg "Erro ao extrair NSSM"
        exit 1
    }
}

# Criar diretório de instalação
function New-InstallDirectory {
    Write-Host ""
    Write-Host "📂 Criando diretório de instalação..." -ForegroundColor Cyan
    Write-Host ""
    
    if (Test-Path $INSTALL_DIR) {
        Write-InfoMsg "Diretório já existe: $INSTALL_DIR"
        $overwrite = Read-Host "Deseja sobrescrever? (S/N)"
        if ($overwrite -ne "S" -and $overwrite -ne "s") {
            Write-ErrorMsg "Instalação cancelada"
            exit 1
        }
    }
    
    New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
    New-Item -ItemType Directory -Force -Path "$INSTALL_DIR\logs" | Out-Null
    New-Item -ItemType Directory -Force -Path "$INSTALL_DIR\cloned_repos" | Out-Null
    
    Write-Success "Diretório criado: $INSTALL_DIR"
}

# Copiar arquivos da aplicação
function Copy-ApplicationFiles {
    Write-Host ""
    Write-Host "📋 Copiando arquivos da aplicação..." -ForegroundColor Cyan
    Write-Host ""
    
    $currentDir = Get-Location
    
    # Copiar arquivos principais
    $files = @("app.py", "index.html", "integration.js", "api-client.js")
    
    foreach ($file in $files) {
        $sourcePath = Join-Path $currentDir $file
        if (Test-Path $sourcePath) {
            Copy-Item $sourcePath -Destination $INSTALL_DIR -Force
            Write-InfoMsg "Copiado: $file"
        } else {
            Write-ErrorMsg "Arquivo não encontrado: $file"
        }
    }
    
    Write-Success "Arquivos copiados para $INSTALL_DIR"
}

# Criar requirements.txt
function New-RequirementsFile {
    Write-Host ""
    Write-Host "📝 Criando requirements.txt..." -ForegroundColor Cyan
    Write-Host ""
    
    $requirements = @"
Flask==3.0.0
Flask-CORS==4.0.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
cryptography==41.0.7
pytz==2023.3
"@
    
    $requirements | Out-File -FilePath "$INSTALL_DIR\requirements.txt" -Encoding UTF8
    Write-Success "requirements.txt criado"
}

# Criar ambiente virtual Python
function New-PythonEnvironment {
    Write-Host ""
    Write-Host "🐍 Criando ambiente virtual Python..." -ForegroundColor Cyan
    Write-Host ""
    
    Push-Location $INSTALL_DIR
    
    # Criar venv
    python -m venv venv
    
    # Ativar venv e instalar dependências
    & "$INSTALL_DIR\venv\Scripts\Activate.ps1"
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    
    Pop-Location
    
    Write-Success "Ambiente Python configurado"
}

# Configurar PostgreSQL
function Set-PostgreSQLDatabase {
    Write-Host ""
    Write-Host "🐘 Configurando PostgreSQL..." -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Digite as informações do PostgreSQL:" -ForegroundColor Yellow
    Write-Host ""
    
    $dbHost = Read-Host "Host do PostgreSQL (padrão: localhost)"
    if ([string]::IsNullOrWhiteSpace($dbHost)) { $dbHost = "localhost" }
    
    $dbPort = Read-Host "Porta do PostgreSQL (padrão: 5432)"
    if ([string]::IsNullOrWhiteSpace($dbPort)) { $dbPort = "5432" }
    
    $dbUser = Read-Host "Usuário do PostgreSQL (padrão: atudic_user)"
    if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = "atudic_user" }
    
    $dbPassword = Read-Host "Senha do usuário" -AsSecureString
    $dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPassword)
    )
    
    $dbName = Read-Host "Nome do banco (padrão: atudic_devops)"
    if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = "atudic_devops" }
    
    # Criar script SQL
    $sqlScript = @"
-- Criar usuário (se não existir)
DO `$`$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '$dbUser') THEN
        CREATE USER $dbUser WITH PASSWORD '$dbPasswordPlain';
    END IF;
END `$`$;

-- Criar banco de dados (se não existir)
SELECT 'CREATE DATABASE $dbName OWNER $dbUser'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$dbName');

-- Conceder privilégios
GRANT ALL PRIVILEGES ON DATABASE $dbName TO $dbUser;
"@
    
    $sqlFile = "$env:TEMP\setup_db.sql"
    $sqlScript | Out-File -FilePath $sqlFile -Encoding UTF8
    
    Write-InfoMsg "Executando script de criação do banco..."
    Write-Host "Você precisará digitar a senha do usuário 'postgres'" -ForegroundColor Yellow
    
    # Executar via psql
    try {
        $env:PGPASSWORD = Read-Host "Senha do usuário 'postgres'" -AsSecureString | ConvertFrom-SecureString -AsPlainText
        & psql -U postgres -f $sqlFile
        Write-Success "Banco de dados configurado"
    } catch {
        Write-ErrorMsg "Erro ao configurar banco: $_"
        Write-InfoMsg "Você pode configurar manualmente executando:"
        Write-Host $sqlScript -ForegroundColor White
    }
    
    # Criar arquivo .env
    $secretKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | ForEach-Object {[char]$_})
    
    $envContent = @"
DB_HOST=$dbHost
DB_PORT=$dbPort
DB_NAME=$dbName
DB_USER=$dbUser
DB_PASSWORD=$dbPasswordPlain
FLASK_SECRET_KEY=$secretKey
"@
    
    $envContent | Out-File -FilePath "$INSTALL_DIR\.env" -Encoding UTF8
    Write-Success "Arquivo .env criado"
}

# Criar script de inicialização
function New-StartupScript {
    Write-Host ""
    Write-Host "📝 Criando script de inicialização..." -ForegroundColor Cyan
    Write-Host ""
    
    $startScript = @"
@echo off
cd /d "$INSTALL_DIR"
call venv\Scripts\activate.bat
python app.py
"@
    
    $startScript | Out-File -FilePath "$INSTALL_DIR\start.bat" -Encoding ASCII
    Write-Success "Script start.bat criado"
}

# Instalar como serviço Windows
function Install-WindowsService {
    param($nssmPath)
    
    Write-Host ""
    Write-Host "⚙️  Instalando como serviço Windows..." -ForegroundColor Cyan
    Write-Host ""
    
    # Verificar se serviço já existe
    $existingService = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-InfoMsg "Serviço já existe. Removendo..."
        & $nssmPath stop $SERVICE_NAME
        & $nssmPath remove $SERVICE_NAME confirm
        Start-Sleep -Seconds 2
    }
    
    # Instalar serviço
    $pythonExe = "$INSTALL_DIR\venv\Scripts\python.exe"
    $appScript = "$INSTALL_DIR\app.py"
    
    & $nssmPath install $SERVICE_NAME $pythonExe $appScript
    & $nssmPath set $SERVICE_NAME AppDirectory $INSTALL_DIR
    & $nssmPath set $SERVICE_NAME DisplayName "ATUDIC DevOps Dashboard"
    & $nssmPath set $SERVICE_NAME Description "Sistema de DevOps para automação de pipelines Protheus"
    & $nssmPath set $SERVICE_NAME Start SERVICE_AUTO_START
    
    # Configurar saída de logs
    & $nssmPath set $SERVICE_NAME AppStdout "$INSTALL_DIR\logs\service-output.log"
    & $nssmPath set $SERVICE_NAME AppStderr "$INSTALL_DIR\logs\service-error.log"
    
    # Configurar rotação de logs
    & $nssmPath set $SERVICE_NAME AppRotateFiles 1
    & $nssmPath set $SERVICE_NAME AppRotateBytes 10485760  # 10MB
    
    Write-Success "Serviço Windows instalado"
}

# Iniciar serviço
function Start-AtudicService {
    Write-Host ""
    Write-Host "🚀 Iniciando serviço..." -ForegroundColor Cyan
    Write-Host ""
    
    try {
        Start-Service -Name $SERVICE_NAME
        Start-Sleep -Seconds 3
        
        $service = Get-Service -Name $SERVICE_NAME
        if ($service.Status -eq "Running") {
            Write-Success "Serviço iniciado com sucesso!"
        } else {
            Write-ErrorMsg "Falha ao iniciar o serviço"
            Write-Host "Status: $($service.Status)" -ForegroundColor Yellow
        }
    } catch {
        Write-ErrorMsg "Erro ao iniciar serviço: $_"
    }
}

# Configurar Windows Firewall
function Set-FirewallRule {
    Write-Host ""
    $configFw = Read-Host "🔥 Deseja configurar o Windows Firewall? (S/N)"
    
    if ($configFw -eq "S" -or $configFw -eq "s") {
        Write-Host ""
        Write-InfoMsg "Configurando firewall..."
        
        try {
            New-NetFirewallRule -DisplayName "ATUDIC DevOps" `
                                -Direction Inbound `
                                -LocalPort 5000 `
                                -Protocol TCP `
                                -Action Allow `
                                -ErrorAction SilentlyContinue
            
            Write-Success "Regra de firewall criada para porta 5000"
        } catch {
            Write-ErrorMsg "Erro ao configurar firewall: $_"
        }
    }
}

# Exibir informações finais
function Show-FinalInfo {
    $ipAddress = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*"} | Select-Object -First 1).IPAddress
    
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "✅ INSTALAÇÃO CONCLUÍDA!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "📌 Informações importantes:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Diretório: $INSTALL_DIR" -ForegroundColor White
    Write-Host "   Serviço: $SERVICE_NAME" -ForegroundColor White
    Write-Host ""
    Write-Host "🔧 Comandos úteis:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   Verificar status:    Get-Service -Name $SERVICE_NAME" -ForegroundColor White
    Write-Host "   Parar serviço:       Stop-Service -Name $SERVICE_NAME" -ForegroundColor White
    Write-Host "   Iniciar serviço:     Start-Service -Name $SERVICE_NAME" -ForegroundColor White
    Write-Host "   Reiniciar serviço:   Restart-Service -Name $SERVICE_NAME" -ForegroundColor White
    Write-Host "   Ver logs:            Get-Content $INSTALL_DIR\logs\*.log -Tail 50 -Wait" -ForegroundColor White
    Write-Host ""
    Write-Host "🌐 Acesso à aplicação:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   URL Local:   http://localhost:5000" -ForegroundColor White
    Write-Host "   URL Rede:    http://${ipAddress}:5000" -ForegroundColor White
    Write-Host ""
    Write-Host "   Usuário padrão: admin" -ForegroundColor White
    Write-Host "   Senha padrão:   admin123" -ForegroundColor White
    Write-Host ""
    Write-Host "⚠️  IMPORTANTE: Altere a senha padrão após o primeiro login!" -ForegroundColor Red
    Write-Host ""
}

# EXECUÇÃO PRINCIPAL
function Main {
    try {
        Test-PythonInstalled
        Test-PostgreSQLInstalled
        $nssmPath = Install-NSSM
        New-InstallDirectory
        Copy-ApplicationFiles
        New-RequirementsFile
        New-PythonEnvironment
        Set-PostgreSQLDatabase
        New-StartupScript
        Install-WindowsService -nssmPath $nssmPath
        Start-AtudicService
        Set-FirewallRule
        Show-FinalInfo
        
    } catch {
        Write-ErrorMsg "Erro durante a instalação: $_"
        Write-Host $_.ScriptStackTrace -ForegroundColor Red
        Read-Host "Pressione Enter para sair"
        exit 1
    }
}

# Executar instalação
Main

Write-Host ""
Read-Host "Pressione Enter para sair"
