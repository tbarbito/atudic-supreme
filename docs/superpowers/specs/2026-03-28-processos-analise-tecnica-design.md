# Processos do Cliente — Analise Tecnica + Chat + Cadastro Inteligente

**Data:** 2026-03-28
**Status:** Aprovado

## Resumo

Transformar o `ProcessoDialog` num hub completo de cada processo: ao abrir, exibe analise tecnica (gerada ou cacheada), chat inline para aprofundar/enriquecer, e um mecanismo de cadastro inteligente de processos acessivel tanto pela UI quanto como tool do Peca ao Analista.

## Motivacao

Hoje o dialog mostra dados basicos + fluxo Mermaid. A analise tecnica profunda so existe no Peca ao Analista, mas nao fica vinculada ao processo. O objetivo e:

1. Cada processo ter sua analise tecnica persistida (JSON + markdown)
2. Chat inline para aprofundar sem sair do contexto
3. Processos se auto-enriquecerem conforme o Analista conversa com o usuario
4. Cadastro inteligente que busca antes de criar, disponivel como tool interna

## 1. Modelo de Dados

### 1a. Novas colunas em `processos_detectados`

As colunas sao adicionadas no `SCHEMA` constant em `database.py` (dentro do CREATE TABLE) e tambem via ALTER TABLE no bloco de migracoes idemponentes em `Database.initialize()` (padrao try/except existente) para DBs ja criados:

```sql
ALTER TABLE processos_detectados ADD COLUMN analise_markdown TEXT DEFAULT NULL;
ALTER TABLE processos_detectados ADD COLUMN analise_json TEXT DEFAULT NULL;
ALTER TABLE processos_detectados ADD COLUMN analise_updated_at TEXT DEFAULT NULL;
```

- `analise_markdown`: relatorio tecnico completo (write-points, triggers, PEs, parametros)
- `analise_json`: dados estruturados para consulta programatica
- `analise_updated_at`: timestamp da ultima geracao/atualizacao

### 1b. Nova tabela `processo_mensagens`

Criada no `SCHEMA` constant em `database.py` (mesmo local que `processos_detectados`, ja que referencia essa tabela):

```sql
CREATE TABLE IF NOT EXISTS processo_mensagens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES processos_detectados(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_proc_msg_processo ON processo_mensagens(processo_id);
```

## 2. Backend — Endpoints

### 2a. `GET /api/analista/processos/{id}/analise`

- **Cache hit:** se `analise_markdown` existe, retorna `{ analise_markdown, analise_json, analise_updated_at }`
- **Cache miss:** dispara investigacao usando as tools existentes:
  - Para cada tabela do processo: `tool_analise_impacto()`, `tool_operacoes_tabela()`, `tool_investigar_condicao()`, `tool_buscar_pes()`, `tool_buscar_parametros()`
  - Envia resultados ao LLM para gerar markdown + JSON estruturado
  - Salva nas colunas do processo
  - Retorna resultado
- **Query param `?force=true`:** regenera mesmo se cache existe

**Concorrencia:** se `analise_updated_at` e null e outra request ja esta gerando, a segunda request aguarda (poll simples no DB ate `analise_updated_at` nao ser null, timeout 120s). Para sinalizar geracao em andamento, seta `analise_updated_at = 'generating'` antes de iniciar.

**Estrutura do `analise_json`:**
```json
{
  "tabelas": [
    {
      "codigo": "ZB8",
      "write_points": [
        { "fonte": "XFATA01.PRW", "funcao": "A010Inclui", "campos": ["B8_FILIAL","B8_STATUS"], "condicao": "cTipo == '1'" }
      ],
      "triggers": [
        { "campo": "B8_STATUS", "gatilho": "U_ZB8STAT", "tipo": "change" }
      ],
      "operacoes": [
        { "tipo": "reclock", "funcao": "A010Inclui", "modo": "inclusao" }
      ]
    }
  ],
  "entry_points": [
    { "pe": "A010INCPRE", "fonte": "XFATA01.PRW", "descricao": "Pre-inclusao do pedido" }
  ],
  "parametros": [
    { "nome": "MV_XZBAPR", "conteudo": ".T.", "descricao": "Ativa aprovacao automatica" }
  ],
  "fontes_envolvidas": ["XFATA01.PRW", "XFATA02.PRW"],
  "condicoes_criticas": [
    { "condicao": "cTipo == '1' .And. lAprov", "impacto": "Controla fluxo de aprovacao", "fonte": "XFATA01.PRW" }
  ]
}
```

### 2b. `POST /api/analista/processos/{id}/chat`

- **Body:** `{ "message": "string" }`
- **Comportamento:**
  1. Carrega ultimas 30 mensagens de `processo_mensagens` (frontend pode pedir mais com `?offset=`)
  2. Carrega `analise_json` como contexto
  3. Salva mensagem do user em `processo_mensagens` imediatamente
  4. Usa engine de streaming SSE (mesmo do Analista, modo "duvida")
  5. Acumula texto completo durante o stream
  6. No evento `done` (apos stream completo): salva mensagem assistant em `processo_mensagens`
  7. Avalia se ha info tecnica nova relevante no texto completo
  8. Se sim: merge silencioso no `analise_json` e append no `analise_markdown`
  9. Se stream falhar mid-way: mensagem assistant NAO e salva (user message ja foi salva no passo 3)
- **Response:** SSE stream (eventos: status, content, done)

### 2c. `POST /api/analista/processos/registrar`

- **Body:** `{ "descricao": "string" }`
- **Comportamento:**
  1. Extrai nome/tipo/tabelas da descricao via LLM
  2. Fuzzy match em 2 estagios:
     - **Estagio 1 (barato):** busca textual no SQLite — `WHERE nome LIKE '%termo%' OR descricao LIKE '%termo%'` usando termos-chave extraidos no passo 1. Retorna top 10 candidatos.
     - **Estagio 2 (LLM):** se estagio 1 retornou candidatos, envia apenas esses ao LLM para confirmar match (sim/nao + score 0-1). Threshold: score >= 0.7 = match confirmado.
  3. Se match confirmado: enriquece (merge tabelas, descricao, evidencias). Atualiza `metodo` para `{metodo_original}+manual`.
  4. Se nenhum match ou score < 0.7: cria novo com `metodo='manual'`
- **Response:** `{ "acao": "criado|enriquecido", "processo": {...} }`

**UX do "Incluir Processo":** toast mostra "Processo X criado com sucesso" ou "Processo X enriquecido com novas informacoes". No caso de enriquecimento, o toast inclui o nome do processo encontrado para o usuario confirmar visualmente.

## 3. Backend — Tool para o Analista

### `tool_registrar_processo(nome, tipo, descricao, tabelas, criticidade)`

- Registrada em `analista_tools.py`
- Recebe dados ja estruturados (o Analista ja conhece nome/tipo/tabelas do contexto da conversa)
- NAO chama LLM para extracao (diferente do endpoint que recebe texto livre)
- Faz o mesmo fuzzy match 2-estagios do endpoint para decidir criar vs enriquecer
- Prompt dos 3 modos do Analista ganha instrucao: "Quando identificar um processo de negocio do cliente que nao esta catalogado, use tool_registrar_processo para registra-lo silenciosamente."

## 4. Frontend — ProcessoDialog

### Layout atualizado (900px largura, max-width: 90vw para telas menores, dialog scrollavel com max-height: 85vh)

```
+-------------------------------------+
| Nome do Processo                  X |
|-------------------------------------|
| [tipo] [criticidade] Score: 0.95    |
| Descricao do processo...            |
| [ZB8] [ZB9] [ZZC] [+3]            |
|-------------------------------------|
| Fluxo do Processo      [Regenerar]  |
| +-------------------------------+   |
| |   diagrama mermaid            |   |
| +-------------------------------+   |
|-------------------------------------|
| Analise Tecnica          [Regerar]  |
| +-------------------------------+   |
| |  ## Write Points              |   |
| |  ## Triggers                  |   |
| |  ## Entry Points              |   |
| |  ## Parametros                |   |
| |  (scroll, max-height ~400px)  |   |
| +-------------------------------+   |
|-------------------------------------|
| Chat do Processo                    |
| +-------------------------------+   |
| | user: detalha a integracao    |   |
| | bot: A integracao usa...      |   |
| +-------------------------------+   |
| [________________] [Enviar]         |
|-------------------------------------|
|                          [Fechar]   |
+-------------------------------------+
```

### Comportamento

- **Ao abrir:** chama `GET /processos/{id}/analise` automaticamente
  - Cache hit: renderiza markdown direto
  - Cache miss: skeleton + "Gerando analise tecnica..."
- **Botao "Regerar":** chama com `?force=true`
- **Chat:** streaming SSE, historico carregado ao abrir
- **Remove** botao "Perguntar ao Analista" (chat agora e inline)

### ProcessosCliente.vue — Botao "Incluir Processo"

- Novo botao no header da tela (ao lado de filtros)
- Abre mini-dialog com textarea para descrever o processo
- Chama `POST /processos/registrar`
- Toast com resultado (criado ou enriquecido)
- Recarrega lista

## 5. Fluxo de Enriquecimento Automatico

```
Usuario conversa no Peca ao Analista
    |
    v
Analista identifica processo de negocio
    |
    v
Chama tool_registrar_processo() silenciosamente
    |
    v
Fuzzy match no banco
    |
   / \
  /   \
Existe  Nao existe
  |        |
  v        v
Merge   Cria novo
info    processo
```

## 6. Arquivos Impactados

**Backend:**
- `backend/services/database.py` — novas colunas + tabela processo_mensagens
- `backend/routers/analista.py` — 3 novos endpoints (analise, chat, registrar)
- `backend/services/analista_tools.py` — nova tool_registrar_processo
- `backend/services/analista_prompts.py` — instrucao de cadastro nos 3 prompts

**Frontend:**
- `frontend/src/components/ProcessoDialog.vue` — secoes analise + chat
- `frontend/src/views/ProcessosCliente.vue` — botao incluir processo
