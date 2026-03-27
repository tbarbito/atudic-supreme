#!/bin/bash

# ==============================================================================
# Script de compilação de fontes Protheus para ambiente Linux (Bash)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BUILD_DIR="/home/barbito/aturpo/build"
FONTES_DIR="/home/barbito/totvs/protheus/projects/protheus/develop"
INCLUDE_DIR="/home/barbito/totvs/protheus/includes"
LOG_DIR="/home/barbito/aturpo/build"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
PROTHEUS_SERVER="localhost"
PROTHEUS_PORT="4500"
PROTHEUS_SECURE="0"
PROTHEUS_BUILD="7.00.240223P"
PROTHEUS_ENV="protheus_cmp"
PROTHEUS_USER="admin"
PROTHEUS_PASSWORD="protheus"

# --- DEFINIÇÃO DE ARQUIVOS ---
LST_FILE="$BUILD_DIR/compila.txt"
INI_FILE="$BUILD_DIR/compila.ini"
LOG_FILE="$LOG_DIR/compila.log"
ADVPLS_EXE="$BUILD_DIR/advpls"

echo "========================================="
echo " 🔄 GERANDO LISTA DE FONTES"
echo "========================================="

rm -f "$LST_FILE"

cd "$FONTES_DIR" || exit 1
find . -maxdepth 1 -type f \( -iname "*.prw" -o -iname "*.tlpp" -o -iname "*.prx" \) -printf "%f\n" > "$LST_FILE"

echo "✅ Lista de fontes gerada: $LST_FILE"

echo "========================================="
echo " 📄 GERANDO ARQUIVO DE CONFIGURAÇÃO"
echo "========================================="

cat > "$INI_FILE" << EOF
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
EOF

echo "✅ Arquivo INI gerado com sucesso: $INI_FILE"

echo "========================================="
echo " 🔧 COMPILANDO FONTES"
echo "========================================="

if [ ! -f "$ADVPLS_EXE" ]; then
    echo "❌ Executável não encontrado: $ADVPLS_EXE"
    echo "Verifique a variável BUILD_DIR no sistema."
    exit 1
fi

"$ADVPLS_EXE" cli "$INI_FILE"

# 🆕 Verificar se advpls executou com sucesso
if [ $? -ne 0 ]; then
    echo "========================================="
    echo "❌ ERRO na compilação! O advpls retornou código de erro."
    echo "Verifique os logs acima para mais detalhes."
    echo "========================================="
    exit 1
fi

echo "========================================="
echo "✅ Processo de compilação concluído! 🎉"
echo "========================================="