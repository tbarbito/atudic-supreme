#!/bin/bash

# ==============================================================================
# Script de Troca Quente (TQ) do RPO Protheus para ambiente Linux (Bash)
# ==============================================================================

echo "--------------------------------------------------------------------------"
echo "ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO"
echo "sempre sera criada pois ele busca a data e hora atual do sistema para"
echo "nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini"
echo "Execute com precisao e cuidado!"
echo "--------------------------------------------------------------------------"

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
PASTA_APO="${PASTA_APO}"
PASTA_CMP="${PASTA_CMP}"
PASTA_BIN="${PASTA_BIN}"

# Verifica se a pasta alvo existe
if [ ! -d "$PASTA_APO" ]; then
    echo "Erro: O diretório PASTA_APO não foi encontrado em: $PASTA_APO"
    exit 1
fi

# Procura o diretório mais recente que começa com '202'
echo "Procurando o diretorio mais recente em: $PASTA_APO"
ANO_ATUAL=$(date +'%Y' | cut -c1-3)  # Pega "202" ou "203" etc
DIRETORIO_MAIS_RECENTE=$(ls -td "$PASTA_APO"/${ANO_ATUAL}*/ 2>/dev/null | head -n 1)

if [ -z "$DIRETORIO_MAIS_RECENTE" ]; then
    echo "Erro: Nenhum diretório começando com '202' foi encontrado em $PASTA_APO"
    exit 1
fi

ORIGEM=$(basename "$DIRETORIO_MAIS_RECENTE")

# Obtém a data e hora atual no formato desejado
DESTINO=$(date +'%Y%m%d_%H%M')

# Mostra em tela as pastas que serão atualizadas
echo "-------------------------------------------"
echo "Pasta de ORIGEM: ${ORIGEM}"
echo "-------------------------------------------"
echo "-------------------------------------------"
echo "Pasta de DESTINO: ${DESTINO}"
echo "-------------------------------------------"

echo "REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS..."

# Cria o diretório de destino
mkdir -p "${PASTA_APO}/${DESTINO}"

# Copia os arquivos RPO para o novo diretório de destino
cp -p "${PASTA_CMP}/tttm120.rpo" "${PASTA_CMP}/custom.rpo" "${PASTA_APO}/${DESTINO}/"

echo "✅ Arquivos RPO copiados com sucesso!"

echo "REALIZANDO TQ..."

# Localiza os arquivos .ini e substitui a string
find "$PASTA_BIN" -type f -iname "appserver*.ini" -exec sed -i "s#${ORIGEM}#${DESTINO}#g" {} +

echo "PROCESSO CONCLUIDO!"