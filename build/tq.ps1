# ==============================================================================
# Script de Troca Quente (TQ) do RPO Protheus para ambiente Windows (PowerShell)
# ==============================================================================

Write-Host "--------------------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO" -ForegroundColor Yellow
Write-Host "sempre sera criada pois ele busca a data e hora atual do sistema para" -ForegroundColor Yellow
Write-Host "nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini" -ForegroundColor Yellow
Write-Host "Execute com precisao e cuidado!" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------------------------" -ForegroundColor Yellow

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$PASTA_APO = "${PASTA_APO}"
$PASTA_CMP = "${PASTA_CMP}"
$PASTA_BIN = "${PASTA_BIN}"

# Verifica se a pasta alvo existe
if (-not (Test-Path $PASTA_APO)) {
    Write-Host "Erro: O diretório PASTA_APO não foi encontrado em: $PASTA_APO" -ForegroundColor Red
    exit 1
}

# Procura o diretório mais recente que começa com '202'
Write-Host "Procurando o diretorio mais recente em: $PASTA_APO" -ForegroundColor Cyan

$anoAtual = (Get-Date).Year.ToString().Substring(0, 3) # Pega "202" ou "203" etc
$diretorios = Get-ChildItem -Path $PASTA_APO -Directory -Filter "${anoAtual}*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $diretorios) {
    Write-Host "Erro: Nenhum diretório começando com '202' foi encontrado em $PASTA_APO" -ForegroundColor Red
    exit 1
}

$ORIGEM = $diretorios.Name

# Obtém a data e hora atual no formato desejado
$DESTINO = Get-Date -Format "yyyyMMdd_HHmm"

# Mostra em tela as pastas que serão atualizadas
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "Pasta de ORIGEM: $ORIGEM" -ForegroundColor Green
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "Pasta de DESTINO: $DESTINO" -ForegroundColor Green
Write-Host "-------------------------------------------" -ForegroundColor Cyan

Write-Host "REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS..." -ForegroundColor Yellow

# Cria o diretório de destino
$PASTA_DESTINO = Join-Path $PASTA_APO $DESTINO
New-Item -ItemType Directory -Path $PASTA_DESTINO -Force | Out-Null

# Copia os arquivos RPO para o novo diretório de destino
Copy-Item -Path "$PASTA_CMP\tttm120.rpo" -Destination $PASTA_DESTINO -Force
Copy-Item -Path "$PASTA_CMP\custom.rpo" -Destination $PASTA_DESTINO -Force

Write-Host "Arquivos RPO copiados com sucesso!" -ForegroundColor Green

Write-Host "REALIZANDO TQ..." -ForegroundColor Yellow
Write-Host "Buscando arquivos appserver*.ini em $PASTA_BIN e subdiretórios..." -ForegroundColor Cyan

# Localiza os arquivos .ini RECURSIVAMENTE e substitui a string
$arquivosEncontrados = Get-ChildItem -Path $PASTA_BIN -Filter "appserver*.ini" -File -Recurse

if ($arquivosEncontrados) {
    Write-Host "Arquivos encontrados: $($arquivosEncontrados.Count)" -ForegroundColor Cyan
    
    $arquivosEncontrados | ForEach-Object {
        Write-Host "`nProcessando: $($_.FullName)" -ForegroundColor Yellow
        
        $conteudo = Get-Content $_.FullName -Raw
        
        # Verifica se encontrou a string de origem
        if ($conteudo -match [regex]::Escape($ORIGEM)) {
            Write-Host "  Substituindo '$ORIGEM' por '$DESTINO'" -ForegroundColor Yellow
            $conteudo = $conteudo -replace [regex]::Escape($ORIGEM), $DESTINO
            $conteudo | Set-Content $_.FullName -Force
            Write-Host "  Atualizado com sucesso!" -ForegroundColor Green
        } else {
            Write-Host "  String '$ORIGEM' nao encontrada (arquivo pode ja estar atualizado)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "NENHUM arquivo appserver*.ini encontrado!" -ForegroundColor Red
    Write-Host "Verifique o caminho: $PASTA_BIN" -ForegroundColor Yellow
}

Write-Host "`nPROCESSO CONCLUIDO!" -ForegroundColor Green