# ==============================================================================
# Script de compilação de fontes Protheus para ambiente Windows (PowerShell)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$BUILD_DIR = "${BUILD_DIR}"
$FONTES_DIR = "${FONTES_DIR}"
$INCLUDE_DIR = "${INCLUDE_DIR}"
$LOG_DIR = "${LOG_DIR}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
$PROTHEUS_SERVER = "${PROTHEUS_SERVER}"
$PROTHEUS_PORT = "${PROTHEUS_PORT}"
$PROTHEUS_SECURE = "${PROTHEUS_SECURE}"
$PROTHEUS_BUILD = "${PROTHEUS_BUILD}"
$PROTHEUS_ENV = "${PROTHEUS_ENV}"
$PROTHEUS_USER = "${PROTHEUS_USER}"
$PROTHEUS_PASSWORD = "${PROTHEUS_PASSWORD}"

# --- DEFINIÇÃO DE ARQUIVOS ---
$LST_FILE = "$BUILD_DIR\compila.txt"
$INI_FILE = "$BUILD_DIR\compila.ini"
$LOG_FILE = "$LOG_DIR\compila.log"
$ADVPLS_EXE = "$BUILD_DIR\advpls.exe"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 🔄 GERANDO LISTA DE FONTES" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Remove arquivo de lista se existir
if (Test-Path $LST_FILE) {
    Remove-Item $LST_FILE -Force
}

# Lista apenas arquivos (.prw, .tlpp, .prx) no diretório e salva no arquivo de lista
Get-ChildItem -Path $FONTES_DIR -File -Include "*.prw", "*.tlpp", "*.prx" | 
    Select-Object -ExpandProperty Name | 
    Out-File -FilePath $LST_FILE -Encoding UTF8

Write-Host "✅ Lista de fontes gerada: $LST_FILE" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 📄 GERANDO ARQUIVO DE CONFIGURAÇÃO" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Cria o conteúdo do arquivo INI dinamicamente
$iniContent = @"
logToFile=$LOG_FILE
showConsoleOutput=true

[user]
INCLUDE_DIR=$INCLUDE_DIR
LOG_DIR=$LOG_DIR
BUILD_DIR=$BUILD_DIR

[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Compila somente fontes diferentes do rpo
[compile]
action=compile
recompile=F
programlist=$LST_FILE
includes=$INCLUDE_DIR

;faz defrag do rpo
[defragRPO]
action=defragRPO
"@

# Salva o arquivo INI
$iniContent | Out-File -FilePath $INI_FILE -Encoding UTF8 -Force

Write-Host "✅ Arquivo INI gerado com sucesso: $INI_FILE" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 🔧 COMPILANDO FONTES" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Verifica se o executável existe
if (-not (Test-Path $ADVPLS_EXE)) {
    Write-Host "❌ Executável não encontrado: $ADVPLS_EXE" -ForegroundColor Red
    Write-Host "Verifique a variável BUILD_DIR no sistema." -ForegroundColor Yellow
    exit 1
}

# Executa o compilador
& $ADVPLS_EXE cli $INI_FILE

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✅ Processo de compilação concluído! 🎉" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan