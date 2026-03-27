#!/bin/bash

# ==============================================================================
# Script de aplicação de patches Protheus para ambiente Linux (Bash)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BASE_DIR_PATCHES="${BASE_DIR_PATCHES}"
BUILD_DIR="${BUILD_DIR}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
PROTHEUS_SERVER="${PROTHEUS_SERVER}"
PROTHEUS_PORT="${PROTHEUS_PORT}"
PROTHEUS_SECURE="${PROTHEUS_SECURE}"
PROTHEUS_BUILD="${PROTHEUS_BUILD}"
PROTHEUS_ENV="${PROTHEUS_ENV}"
PROTHEUS_USER="${PROTHEUS_USER}"
PROTHEUS_PASSWORD="${PROTHEUS_PASSWORD}"

# --- DEFINIÇÃO DAS PASTAS ---
PENDENTES_DIR="$BASE_DIR_PATCHES/pendentes"
ZIPS_PROCESSADOS_DIR="$BASE_DIR_PATCHES/zips_processados"
APLICADOS_DIR="$BASE_DIR_PATCHES/aplicados"
OUTPUT_INI_FILE="$BUILD_DIR/apply_patches.ini"
LOG_FILE="$BUILD_DIR/apply_patch.log"
ADVPLS_EXECUTABLE="$BUILD_DIR/advpls"

# --- INÍCIO DO SCRIPT ---
echo "========================================="
echo "📦 Extraindo arquivos ZIP da pasta pendentes..."
echo "========================================="

# Encontra todos os arquivos .zip no diretório
zip_files=$(find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.zip")

if [ -n "$zip_files" ]; then
    file_count=$(echo "$zip_files" | wc -l)
    echo "✅ Encontrados $file_count arquivos ZIP para extração"

    # Cria a pasta de processados se não existir
    mkdir -p "$ZIPS_PROCESSADOS_DIR"

    # Itera e extrai cada arquivo zip
    echo "$zip_files" | while read -r zip_file; do
        filename=$(basename "$zip_file")
        echo "📄 Extraindo: $filename"
        # O comando unzip -o sobrescreve arquivos existentes sem perguntar
        unzip -o "$zip_file" -d "$PENDENTES_DIR"
        
        # Move o arquivo zip para a pasta de processados
        mv "$zip_file" "$ZIPS_PROCESSADOS_DIR/"
    done

    echo "🎉 Extração de arquivos ZIP concluída"
else
    echo "⚠️ Nenhum arquivo ZIP encontrado para extração"
fi

echo "========================================="
echo "📄 Gerando script com lista de patches..."
echo "========================================="

# Verifica se a pasta de patches existe
if [ ! -d "$PENDENTES_DIR" ]; then
    echo "❌ Pasta de patches não encontrada: $PENDENTES_DIR"
    echo "🔨 Criando a pasta..."
    mkdir -p "$PENDENTES_DIR"
    echo "📁 Pasta criada. Por favor, coloque os arquivos de patch na pasta e execute novamente."
    exit 1
fi

# Encontra todos os arquivos .PTM, ordenados por nome
patch_files=$(find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.PTM" | sort)

if [ -z "$patch_files" ]; then
    echo "⚠️ Nenhum arquivo de patch PTM encontrado na pasta: $PENDENTES_DIR"
    exit 0
fi

patch_count=$(echo "$patch_files" | wc -l)
echo "📋 Encontrados $patch_count arquivos de patch"

# Cria o conteúdo do arquivo INI (sobrescreve se já existir)
cat > "$OUTPUT_INI_FILE" << EOF
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
EOF

# Adiciona as sessões de patch dinamicamente
session_number=1
echo "$patch_files" | while read -r patch_file; do
    # Adiciona cada sessão de patch ao final do arquivo INI
    cat >> "$OUTPUT_INI_FILE" << EOF

[patchApply_$session_number]
action=patchApply
patchFile=$patch_file
localPatch=True
applyOldProgram=False
EOF
    ((session_number++))
done

# Adiciona a sessão final de desfragmentação
cat >> "$OUTPUT_INI_FILE" << EOF

;Sessão que faz defrag do rpo
[defragRPO]
action=defragRPO
EOF

echo "✅ Arquivo INI gerado com sucesso: $OUTPUT_INI_FILE"
echo "📊 Total de sessões de patch: $patch_count"

echo "========================================="
echo "🔧 Aplicando patches..."
echo "========================================="

# Verifica se o executável existe
if [ ! -f "$ADVPLS_EXECUTABLE" ]; then
    echo "❌ Executável não encontrado em: $ADVPLS_EXECUTABLE"
    echo "Verifique a variável BUILD_DIR no sistema."
    exit 1
fi

# Executa o comando
"$ADVPLS_EXECUTABLE" cli "$OUTPUT_INI_FILE"

echo "========================================="
echo "🧹 Limpando arquivos de patches..."
echo "========================================="

# Cria o diretório 'aplicados' se não existir
mkdir -p "$APLICADOS_DIR"

# Move todos os arquivos .ptm para o diretório 'aplicados'
find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.ptm" -exec mv -t "$APLICADOS_DIR/" {} +
echo "Arquivos .ptm movidos para $APLICADOS_DIR"

# Remove todos os arquivos restantes do diretório 'pendentes'
rm -R -f "$PENDENTES_DIR"/*
echo "Arquivos restantes em $PENDENTES_DIR foram removidos."

echo "✅ Processo concluído."