# Processos do Cliente — Design Spec

**Data:** 2026-03-27
**Status:** Aprovado pelo usuário

---

## Objetivo

Criar uma nova página "Processos do Cliente" no sidebar do frontend, listando os processos detectados pelo pipeline de descoberta (`processos_detectados`). O usuário pode filtrar, clicar num processo para ver detalhes e um fluxo Mermaid gerado por LLM, e navegar para o chat do Analista com contexto pré-carregado.

---

## Arquitetura

### Frontend

- **Rota:** `/processos` — nova entrada em `frontend/src/router.js`, inserida após `/analista` (linha 13), antes de `/padrao`
- **Sidebar:** automático via `meta.label` — `App.vue` já filtra `router.getRoutes()` por `r.meta?.label`. Adicionar a rota com `meta: { label: 'Processos', icon: 'pi pi-list' }`. **Nenhuma edição direta em `App.vue` é necessária.**
- **Componentes:**
  - `frontend/src/views/ProcessosCliente.vue` — página principal com DataTable
  - `frontend/src/components/ProcessoDialog.vue` — Dialog de detalhe (filho de ProcessosCliente)
- **Mermaid:** já instalado (`mermaid ^11.13.0`). `ProcessoDialog.vue` deve importar `ensureInit` de `frontend/src/composables/useMermaid.js`. A função `ensureInit` atualmente não é exportada — adicionar `export` a ela. Os callers internos existentes (ex: `renderMermaidBlocks`) continuam funcionando sem alteração. Chamar `ensureInit()` antes de `mermaid.render()`. **Não** chamar `mermaid.initialize()` diretamente. **Não** importar `generateFlowFromYaml` (exclusivo de `FlowDiagram.vue`).

### Backend

- **Novo endpoint:** `POST /analista/processos/{id}/fluxo` onde `id: int` — gera diagrama Mermaid via LLM, salva no banco, retorna string
  - Query param `force: bool = False` (FastAPI converte `?force=true` para `True`)
- **Atualização obrigatória antes do frontend:** `tool_processos_cliente()` em `backend/services/analista_tools.py` — adicionar `fluxo_mermaid` ao SELECT e ao dict retornado. O `GET /analista/processos` depende disso para expor o campo ao frontend; sem essa atualização o frontend receberá `undefined` para `fluxo_mermaid`.
- **Endpoints existentes sem outras alterações:**
  - `GET /analista/processos`
  - `POST /analista/processos/descobrir`

### Banco de dados

- Adicionar coluna `fluxo_mermaid TEXT DEFAULT NULL` à tabela `processos_detectados` em **dois lugares**:
  1. Na constante `SCHEMA` em `database.py` (para novos bancos): adicionar `fluxo_mermaid TEXT DEFAULT NULL,` antes do fechamento do `CREATE TABLE processos_detectados`
  2. Migration para bancos existentes: em `initialize()`, **fora do bloco `if key not in _initialized_dbs`**, após o `if` block:
  ```python
  # Migration idempotente — SQLite serializa writes por default, sem race condition
  try:
      self._conn.execute(
          "ALTER TABLE processos_detectados ADD COLUMN fluxo_mermaid TEXT DEFAULT NULL"
      )
      self._conn.commit()
  except Exception:
      pass  # coluna já existe
  ```

---

## Componentes em Detalhe

### `ProcessosCliente.vue`

**Ao montar:** chama `GET /analista/processos` → preenche DataTable.

**Header da página:**
- Título "Processos do Cliente"
- Badge com total de processos
- Dropdown filtro por tipo (todos, workflow, integracao, logistica, fiscal, etc.)
- Dropdown filtro por criticidade (todos, alta, media, baixa)
- Botão "Redescobrir" → `POST /analista/processos/descobrir` com spinner (timeout Axios: 120s)
  - Sucesso: recarrega lista + toast "Processos atualizados"
  - Timeout ou erro HTTP 5xx: toast "Erro ao redescobrir processos. Tente novamente."

**DataTable (PrimeVue):**
| Coluna | Tipo | Detalhe |
|--------|------|---------|
| Nome | texto | clicável |
| Tipo | badge colorido | cor por tipo |
| Criticidade | badge | vermelho=alta, laranja=media, cinza=baixa |
| Score | número | `.toFixed(2)`, colorido (verde ≥0.85, amarelo ≥0.7, cinza abaixo) |
| Tabelas | chips | máx 3 visíveis + "+N" se mais |

O objeto de cada linha contém: `id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid`. Click na linha → abre `ProcessoDialog` passando o objeto completo.

**Estado vazio:** se lista vazia → mensagem "Nenhum processo descoberto. Clique em Redescobrir para analisar o cliente."

### `ProcessoDialog.vue`

Props: `processo` (objeto com `id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid`).

**Seção informações:**
- Nome (título do dialog)
- Tipo, Criticidade, Score
- Descrição completa
- Tabelas envolvidas (chips)

**Seção fluxo:**

Se `processo.fluxo_mermaid` não null ao abrir: renderiza direto. Caso null: mostra botão "Gerar fluxo". Padrão de render (usar em ambos os casos):
```js
import { ensureInit } from '../composables/useMermaid.js'
import mermaid from 'mermaid'

const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`
ensureInit()
try {
  const { svg } = await mermaid.render(id, mermaidStr)
  containerRef.value.innerHTML = svg
} catch (err) {
  // Limpar o que o Mermaid injeta no DOM
  document.getElementById(id)?.remove()
  document.querySelectorAll('.mermaid-error, [id^="dmermaid-"]').forEach(el => el.remove())
  // Fallback: mostrar descricao
  showFallback.value = true
}
```

- Botão "Gerar fluxo" → `POST /analista/processos/{id}/fluxo` com skeleton loader enquanto aguarda
- Botão "Regenerar" (visível após fluxo existir) → mesma chamada com `?force=true`
- Fallback: exibe `processo.descricao` em texto com aviso "Diagrama indisponível"

**Footer do Dialog:**
- Botão "Perguntar ao Analista" → `router.push({ path: '/analista', query: { processo: processo.nome } })`
- Botão "Fechar"

### `AnalistaView.vue` — modificação

Adicionar `import { useRoute } from 'vue-router'` (atualmente não existe nesse arquivo). No `onMounted` existente (linha 1576), adicionar após as 3 chamadas existentes:
```js
const route = useRoute()
if (route.query.processo) {
  userMessage.value = `Me explique o processo: ${route.query.processo}`
}
```
`userMessage` é o `ref('')` na linha 800 de `AnalistaView.vue` que controla o `InputText` principal do chat. Apenas pré-preenche — não auto-envia.

---

## Endpoint: `POST /analista/processos/{id}/fluxo`

```
POST /analista/processos/{id}/fluxo?force=false   # id: int
Response 200: { "fluxo_mermaid": "flowchart TD\n..." }
Response 404: { "detail": "Processo não encontrado" }
Response 500: { "detail": "Erro ao gerar fluxo: <mensagem>" }
```

**Aquisição do LLM:**
```python
from backend.routers.chat import _get_services
try:
    db_svc, vs, ks, llm, client_dir = _get_services()
except Exception as e:
    raise HTTPException(500, f"Erro ao iniciar serviços: {str(e)[:200]}")
```

**Acesso ao banco:** usar `_get_db()` disponível em `analista.py`. Rows retornam como tuplas:
```python
row = db.execute(
    "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
    "FROM processos_detectados WHERE id = ?", (id,)
).fetchone()
# row[0]=id, row[1]=nome, row[2]=tipo, row[3]=descricao,
# row[4]=criticidade, row[5]=tabelas, row[6]=score, row[7]=fluxo_mermaid
```

**Lógica (extrair em função síncrona `gerar_fluxo_processo(db, llm, processo_id: int, force: bool) -> str | None`):**
1. Busca por `id` — se `row` é None → retorna `None` (endpoint → HTTP 404)
2. Se `row[7]` não null e `force=False` → retorna `row[7]` (cache hit)
3. Monta prompt com nome, tipo, descrição, tabelas, criticidade; constrói `messages = [{"role": "user", "content": prompt}]`
4. Chama `llm.chat(messages)` (síncrono). No endpoint async, chamar via `await asyncio.to_thread(gerar_fluxo_processo, db, llm, id, force)`
5. Extrai código Mermaid:
   - Tenta `re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", text)` → `group(1).strip()`
   - Se não match e `text.strip()` começa com `flowchart` ou `graph` → usa `text.strip()`
   - Se nenhum → levanta `ValueError("Resposta do LLM não é um diagrama Mermaid válido")`
6. `db.execute("UPDATE processos_detectados SET fluxo_mermaid = ? WHERE id = ?", (mermaid_str, id))` + `db.commit()`
7. Retorna string Mermaid

**Prompt template:**
```
Gere um diagrama Mermaid `flowchart TD` para o processo "{nome}" do tipo "{tipo}".
Descrição: {descricao}
Tabelas envolvidas: {tabelas}
Criticidade: {criticidade}
Represente as etapas principais do processo de forma clara. Retorne APENAS o código Mermaid, sem explicações.
```

---

## `tool_processos_cliente()` — atualização obrigatória

Em `backend/services/analista_tools.py`, atualizar o SELECT:
```python
# antes:
db.execute("SELECT id, nome, tipo, descricao, criticidade, tabelas, score FROM processos_detectados ORDER BY score DESC")
# depois:
db.execute("SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid FROM processos_detectados ORDER BY score DESC")
```
No dicionário retornado por linha, adicionar `"fluxo_mermaid": r[7]`.

---

## Error Handling

| Situação | Comportamento |
|----------|---------------|
| `GET /processos` sem cache | DataTable vazia + mensagem de estado vazio |
| "Redescobrir" sucesso | Recarrega lista + toast "Processos atualizados" |
| "Redescobrir" timeout ou HTTP 5xx | Toast "Erro ao redescobrir processos. Tente novamente." |
| "Gerar fluxo" HTTP 5xx | Frontend: "Erro ao gerar fluxo. Tente novamente." |
| LLM retorna texto sem Mermaid | `ValueError` → HTTP 500 com mensagem específica |
| `mermaid.render()` falha no frontend | Limpeza DOM + fallback para descrição + "Diagrama indisponível" |
| Processo não encontrado | HTTP 404 |

---

## Testes

### Backend (`tests/test_processos_fluxo.py`)

**Padrão:** testar `gerar_fluxo_processo()` diretamente (sem TestClient — o projeto testa funções de serviço diretamente).

**Fixture:**
```python
import pytest
from unittest.mock import MagicMock
from backend.services.database import Database

@pytest.fixture
def db_com_processo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()  # SCHEMA + migration fluxo_mermaid
    db.execute(
        "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, score) "
        "VALUES (?,?,?,?,?,?)",
        ("Integração Taura WMS", "integracao", "Pedidos ao Taura", "alta", '["SC5","ZZE"]', 0.92)
    )
    db.commit()
    return db

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat.return_value = "flowchart TD\nA-->B"
    return llm
```

**Testes:**
- `test_fluxo_gera_e_salva(db_com_processo, mock_llm)` — chama `gerar_fluxo_processo(db, mock_llm, 1, False)`. Verifica retorno contém `"flowchart"`. Verifica `db.execute("SELECT fluxo_mermaid FROM processos_detectados WHERE id=1").fetchone()[0]` não é None.
- `test_fluxo_retorna_cache(db_com_processo, mock_llm)` — atualiza com `fluxo_mermaid = "flowchart TD\nX-->Y"`. Chama `gerar_fluxo_processo(db, mock_llm, 1, False)`. Verifica `mock_llm.chat.call_count == 0` e retorno == `"flowchart TD\nX-->Y"`.
- `test_fluxo_force_regenera(db_com_processo, mock_llm)` — processo com cache. Chama com `force=True`. Verifica `mock_llm.chat.call_count == 1`.
- `test_fluxo_processo_nao_encontrado(db_com_processo, mock_llm)` — chama com `processo_id=9999`. Verifica retorno `None`.

### Frontend

Sem testes unitários (projeto não possui setup de testes Vue).

---

## Ordem de implementação recomendada

1. `database.py` — SCHEMA + migration
2. `analista_tools.py` — adicionar `fluxo_mermaid` ao SELECT
3. `analista.py` — novo endpoint + `gerar_fluxo_processo()`
4. `tests/test_processos_fluxo.py` — testes do backend
5. `useMermaid.js` — exportar `ensureInit`
6. `router.js` — nova rota
7. `ProcessosCliente.vue` — página DataTable
8. `ProcessoDialog.vue` — dialog de detalhe
9. `AnalistaView.vue` — pré-preencher a partir de query param

---

## Arquivos a criar/modificar

| Arquivo | Ação |
|---------|------|
| `backend/services/database.py` | Modificar — `fluxo_mermaid` no SCHEMA + ALTER TABLE em `initialize()` |
| `backend/services/analista_tools.py` | Modificar — `fluxo_mermaid` no SELECT e no dict |
| `backend/routers/analista.py` | Modificar — endpoint `POST /processos/{id}/fluxo` + `gerar_fluxo_processo()` |
| `tests/test_processos_fluxo.py` | Criar |
| `frontend/src/composables/useMermaid.js` | Modificar — exportar `ensureInit` |
| `frontend/src/router.js` | Modificar — nova rota `/processos` |
| `frontend/src/views/ProcessosCliente.vue` | Criar |
| `frontend/src/components/ProcessoDialog.vue` | Criar |
| `frontend/src/views/AnalistaView.vue` | Modificar — `useRoute` + `route.query.processo` |
