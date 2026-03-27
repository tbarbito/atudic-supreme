# =============================================================================
# 🗑️ ATUDIC DEVOPS - DESINSTALADOR WINDOWS
# =============================================================================
# Remove completamente o sistema e serviço
# Uso: Executar como Administrador
#      .\uninstall_windows.ps1
# =============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🗑️  ATUDIC DEVOPS - Desinstalador Windows" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Variáveis
$SERVICE_NAME = "AtudicDevOps"
$INSTALL_DIR = "C:\AtudicDevOps"

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

# Confirmação
Write-Host "⚠️  ATENÇÃO: Esta ação irá:" -ForegroundColor Yellow
Write-Host ""
Write-Host "   • Parar e remover o serviço $SERVICE_NAME"
Write-Host "   • Remover todos os arquivos em $INSTALL_DIR"
Write-Host "   • Remover banco de dados PostgreSQL (OPCIONAL)"
Write-Host ""

$confirm = Read-Host "Tem certeza que deseja continuar? (digite SIM para confirmar)"

if ($confirm -ne "SIM") {
    Write-Host "Desinstalação cancelada." -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 0
}

Write-Host ""
Write-InfoMsg "Iniciando desinstalação..."

# Parar serviço
try {
    $service = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
    if ($service) {
        if ($service.Status -eq "Running") {
            Write-Host ""
            Write-InfoMsg "Parando serviço..."
            Stop-Service -Name $SERVICE_NAME -Force
            Start-Sleep -Seconds 2
            Write-Success "Serviço parado"
        }
        
        # Remover serviço usando NSSM
        Write-Host ""
        Write-InfoMsg "Removendo serviço..."
        
        $nssmPath = "C:\Windows\System32\nssm.exe"
        if (Test-Path $nssmPath) {
            & $nssmPath stop $SERVICE_NAME
            & $nssmPath remove $SERVICE_NAME confirm
            Write-Success "Serviço removido"
        } else {
            # Tentar remover com sc
            sc.exe delete $SERVICE_NAME
            Write-Success "Serviço removido"
        }
    }
} catch {
    Write-ErrorMsg "Erro ao remover serviço: $_"
}

# Remover diretório de instalação
if (Test-Path $INSTALL_DIR) {
    Write-Host ""
    Write-InfoMsg "Removendo diretório de instalação..."
    
    try {
        Remove-Item -Path $INSTALL_DIR -Recurse -Force
        Write-Success "Diretório removido: $INSTALL_DIR"
    } catch {
        Write-ErrorMsg "Erro ao remover diretório: $_"
        Write-InfoMsg "Você pode precisar remover manualmente: $INSTALL_DIR"
    }
}

# Remover banco de dados (opcional)
Write-Host ""
$removeDb = Read-Host "Deseja remover o banco de dados PostgreSQL? (S/N)"

if ($removeDb -eq "S" -or $removeDb -eq "s") {
    Write-Host ""
    Write-InfoMsg "Removendo banco de dados..."
    
    $sqlScript = @"
DROP DATABASE IF EXISTS atudic_devops;
DROP USER IF EXISTS atudic_user;
"@
    
    $sqlFile = "$env:TEMP\uninstall_db.sql"
    $sqlScript | Out-File -FilePath $sqlFile -Encoding UTF8
    
    try {
        Write-Host "Digite a senha do usuário 'postgres':" -ForegroundColor Yellow
        $pgPassword = Read-Host -AsSecureString
        $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgPassword)
        )
        
        & psql -U postgres -f $sqlFile
        Write-Success "Banco de dados removido"
        
        Remove-Item $sqlFile -Force
    } catch {
        Write-ErrorMsg "Erro ao remover banco: $_"
        Write-InfoMsg "Você pode precisar remover manualmente executando:"
        Write-Host $sqlScript -ForegroundColor White
    }
}

# Remover regra de firewall (opcional)
Write-Host ""
$removeFw = Read-Host "Deseja remover a regra do Windows Firewall? (S/N)"

if ($removeFw -eq "S" -or $removeFw -eq "s") {
    Write-Host ""
    Write-InfoMsg "Removendo regra de firewall..."
    
    try {
        Remove-NetFirewallRule -DisplayName "ATUDIC DevOps" -ErrorAction SilentlyContinue
        Write-Success "Regra de firewall removida"
    } catch {
        Write-ErrorMsg "Erro ao remover regra: $_"
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ DESINSTALAÇÃO CONCLUÍDA!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "Pressione Enter para sair"
