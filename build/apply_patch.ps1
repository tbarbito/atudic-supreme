# ==============================================================================
# Script de aplicação de patches Protheus para ambiente Windows (PowerShell)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$BASE_DIR_PATCHES = "${BASE_DIR_PATCHES}"
$BUILD_DIR = "${BUILD_DIR}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
$PROTHEUS_SERVER = "${PROTHEUS_SERVER}"
$PROTHEUS_PORT = "${PROTHEUS_PORT}"
$PROTHEUS_SECURE = "${PROTHEUS_SECURE}"
$PROTHEUS_BUILD = "${PROTHEUS_BUILD}"
$PROTHEUS_ENV = "${PROTHEUS_ENV}"
$PROTHEUS_USER = "${PROTHEUS_USER}"
$PROTHEUS_PASSWORD = "${PROTHEUS_PASSWORD}"

# --- DEFINIÇÃO DAS PASTAS ---
$PENDENTES_DIR = "$BASE_DIR_PATCHES\pendentes"
$ZIPS_PROCESSADOS_DIR = "$BASE_DIR_PATCHES\zips_processados"
$APLICADOS_DIR = "$BASE_DIR_PATCHES\aplicados"
$OUTPUT_INI_FILE = "$BUILD_DIR\apply_patches.ini"
$LOG_FILE = "$BUILD_DIR\apply_patch.log"
$ADVPLS_EXECUTABLE = "$BUILD_DIR\advpls.exe"

# --- INÍCIO DO SCRIPT ---
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📦 Extraindo arquivos ZIP da pasta pendentes..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Encontra todos os arquivos .zip no diretório
$zip_files = Get-ChildItem -Path $PENDENTES_DIR -Filter "*.zip" -File

if ($zip_files.Count -gt 0) {
    Write-Host "✅ Encontrados $($zip_files.Count) arquivos ZIP para extração" -ForegroundColor Green

    # Cria a pasta de processados se não existir
    if (-not (Test-Path $ZIPS_PROCESSADOS_DIR)) {
        New-Item -ItemType Directory -Path $ZIPS_PROCESSADOS_DIR -Force | Out-Null
    }

    # Itera e extrai cada arquivo zip
    foreach ($zip_file in $zip_files) {
        Write-Host "📄 Extraindo: $($zip_file.Name)" -ForegroundColor Yellow
        Expand-Archive -Path $zip_file.FullName -DestinationPath $PENDENTES_DIR -Force
        
        # Move o arquivo zip para a pasta de processados
        Move-Item -Path $zip_file.FullName -Destination $ZIPS_PROCESSADOS_DIR -Force
    }

    Write-Host "🎉 Extração de arquivos ZIP concluída" -ForegroundColor Green
} else {
    Write-Host "⚠️ Nenhum arquivo ZIP encontrado para extração" -ForegroundColor Yellow
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📄 Gerando script com lista de patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Verifica se a pasta de patches existe
if (-not (Test-Path $PENDENTES_DIR)) {
    Write-Host "❌ Pasta de patches não encontrada: $PENDENTES_DIR" -ForegroundColor Red
    Write-Host "🔨 Criando a pasta..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $PENDENTES_DIR -Force | Out-Null
    Write-Host "📁 Pasta criada. Por favor, coloque os arquivos de patch na pasta e execute novamente." -ForegroundColor Green
    exit 1
}

# Encontra todos os arquivos .PTM, ordenados por nome
$patch_files = Get-ChildItem -Path $PENDENTES_DIR -Filter "*.PTM" -File | Sort-Object Name

if ($patch_files.Count -eq 0) {
    Write-Host "⚠️ Nenhum arquivo de patch PTM encontrado na pasta: $PENDENTES_DIR" -ForegroundColor Yellow
    exit 0
}

Write-Host "📋 Encontrados $($patch_files.Count) arquivos de patch" -ForegroundColor Green

# Cria o conteúdo do arquivo INI (sobrescreve se já existir)
$iniContent = @"
logToFile=$LOG_FILE
showConsoleOutput=true

;Sessão de Autenticação
[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Sessões para aplicar os patches no rpo, geradas automaticamente
"@

# Adiciona as sessões de patch dinamicamente
$session_number = 1
foreach ($patch_file in $patch_files) {
    $iniContent += @"

[patchApply_$session_number]
action=patchApply
patchFile=$($patch_file.FullName)
localPatch=True
applyOldProgram=False
"@
    $session_number++
}

# Adiciona a sessão final de desfragmentação
$iniContent += @"

;Sessão que faz defrag do rpo
[defragRPO]
action=defragRPO
"@

# Salva o arquivo INI
$iniContent | Out-File -FilePath $OUTPUT_INI_FILE -Encoding UTF8 -Force

Write-Host "✅ Arquivo INI gerado com sucesso: $OUTPUT_INI_FILE" -ForegroundColor Green
Write-Host "📊 Total de sessões de patch: $($patch_files.Count)" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🔧 Aplicando patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Verifica se o executável existe
if (-not (Test-Path $ADVPLS_EXECUTABLE)) {
    Write-Host "❌ Executável não encontrado em: $ADVPLS_EXECUTABLE" -ForegroundColor Red
    Write-Host "Verifique a variável BUILD_DIR no sistema." -ForegroundColor Yellow
    exit 1
}

# Executa o comando
& $ADVPLS_EXECUTABLE cli $OUTPUT_INI_FILE

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🧹 Limpando arquivos de patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Cria o diretório 'aplicados' se não existir
if (-not (Test-Path $APLICADOS_DIR)) {
    New-Item -ItemType Directory -Path $APLICADOS_DIR -Force | Out-Null
}

# Move todos os arquivos .ptm para o diretório 'aplicados'
Get-ChildItem -Path $PENDENTES_DIR -Filter "*.ptm" -File | Move-Item -Destination $APLICADOS_DIR -Force
Write-Host "Arquivos .ptm movidos para $APLICADOS_DIR" -ForegroundColor Green

# Remove todos os arquivos restantes do diretório 'pendentes'
Get-ChildItem -Path $PENDENTES_DIR -Recurse | Remove-Item -Force -Recurse
Write-Host "Arquivos restantes em $PENDENTES_DIR foram removidos." -ForegroundColor Green

Write-Host "✅ Processo concluído." -ForegroundColor Green