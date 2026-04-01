# Fase 1 — Melhorias na Extração de Dados do Cliente

**Data:** 2026-03-20
**Status:** Em discussão
**Objetivo:** Corrigir bugs, extrair campos faltantes e preparar a base de dados para a Fase 2 (vínculos e conexões)

---

## 1. Contexto

A Fase 1 é responsável por extrair os dados do cliente (dicionário SX + fontes ADVPL/TLPP) e armazená-los no SQLite + ChromaDB. Hoje existem **3 categorias de problemas**:

- **Bloco A:** Bugs e dados incorretos (parser quebrado, encoding, parsing frágil)
- **Bloco B:** Campos importantes não extraídos (F3, CBOX, VLDUSER, PROPRI, call graph)
- **Bloco C:** Armazenamento incompleto (fonte_chunks vazio, sem tabela de vínculos)

---

## 2. Bloco A — Corrigir o que está errado

### 2.1 SIX (Índices) — Parser QUEBRADO

**Problema:** O parser `parse_six()` busca colunas com prefixo `X6_` (`X6_ARQUIVO`, `X6_ORDEM`, `X6_CHAVE`, `X6_DESCRI`) mas o CSV real da SIX tem colunas **sem prefixo** (`INDICE`, `ORDEM`, `CHAVE`, `DESCRICAO`). Resultado: **0 índices extraídos**.

**CSV Real:**
```
"INDICE","ORDEM","CHAVE","DESCRICAO","DESCSPA","DESCENG","PROPRI","F3","NICKNAME","SHOWPESQ","IX_VIRTUAL","IX_VIRCUST","D_E_L_E_T_","R_E_C_N_O_","R_E_C_D_E_L_"
"AA4","4","AA4_FILIAL+AA4_CODFAB+...","Fabricante + Loja...","...","...","S","SA1+XXX+SB1","","S","2","3"," ",34,0
```

**Parser atual (ERRADO):**
```python
tabela = row.get("X6_ARQUIVO", "")  # não existe no CSV
indice = row.get("X6_ORDEM", "")    # deveria ser "ORDEM"
```

**Correção — mapeamento correto:**

| Coluna CSV | Campo no parser | Campo no SQLite | Descrição |
|---|---|---|---|
| `INDICE` | `indice` | `tabela` | Tabela/alias do índice (ex: SA1, SC7) |
| `ORDEM` | `ordem` | `ordem` | Número da ordem do índice (1, 2, 3...) |
| `CHAVE` | `chave` | `chave` | Composição da chave (ex: A1_FILIAL+A1_COD+A1_LOJA) |
| `DESCRICAO` | `descricao` | `descricao` | Descrição do índice |
| `PROPRI` | `proprietario` | `proprietario` | S=padrão, U=custom |
| `F3` | `f3` | `f3` | Consulta F3 vinculada |
| `NICKNAME` | `nickname` | `nickname` | Apelido do índice |
| `SHOWPESQ` | `showpesq` | `showpesq` | Exibe na pesquisa (S/N) |

**Schema SQLite — tabela `indices` atualizada:**
```sql
CREATE TABLE IF NOT EXISTS indices (
    tabela TEXT,
    ordem TEXT,
    chave TEXT,
    descricao TEXT,
    proprietario TEXT DEFAULT 'S',
    f3 TEXT DEFAULT '',
    nickname TEXT DEFAULT '',
    showpesq TEXT DEFAULT 'S',
    custom INTEGER DEFAULT 0,
    PRIMARY KEY (tabela, ordem)
)
```

**Arquivo:** `backend/services/parser_sx.py` — função `parse_six()`

---

### 2.2 Encoding de Fontes — Corrupção silenciosa

**Problema:** `parser_source.py` tenta UTF-8 primeiro. Se o arquivo é CP1252 (Windows-1252) com caracteres acentuados que **por acaso** são válidos em UTF-8, o arquivo é lido sem erro mas com caracteres corrompidos. O chardet só é usado nos parsers SX, não nos fontes.

**Código atual (ERRADO):**
```python
for enc in ["utf-8", "cp1252", "latin-1"]:
    try:
        return file_path.read_text(encoding=enc)
    except:
        continue
```

**Correção — usar chardet primeiro:**
```python
import chardet

def _read_source_file(file_path):
    raw = file_path.read_bytes()
    detected = chardet.detect(raw)
    encoding = detected.get("encoding", "cp1252") or "cp1252"
    # Protheus files are almost always cp1252
    if encoding.lower() in ("ascii", "utf-8") and b'\x80' <= max(raw) <= b'\xff':
        encoding = "cp1252"  # Force cp1252 if has high bytes
    try:
        return raw.decode(encoding)
    except:
        return raw.decode("cp1252", errors="replace")
```

**Arquivo:** `backend/services/parser_source.py`

---

### 2.3 X3_OBRIGAT — Parsing frágil

**Problema:** O parser verifica `row.get("X3_OBRIGAT", "").strip().strip('"') == "S"`. Funciona só se o valor é `"S"` entre aspas. Pode falhar com `S` sem aspas, `Sim`, `1`, espaços.

**Correção:**
```python
obrig_raw = row.get("X3_OBRIGAT", "").strip().strip('"').strip().upper()
obrigatorio = 1 if obrig_raw in ("S", "SIM", "1", ".T.") else 0
```

**Arquivo:** `backend/services/parser_sx.py` — função `parse_sx3()`

---

## 3. Bloco B — Extrair campos faltantes

### 3.1 SX3 (Campos) — 10 campos importantes

**Campos a adicionar no parser e no SQLite:**

| Campo CSV | Nome no SQLite | Tipo | Por que é importante |
|---|---|---|---|
| `X3_F3` | `f3` | TEXT | Consulta F3 — mostra relacionamento com outra tabela |
| `X3_CBOX` | `cbox` | TEXT | Combo box — lista de valores permitidos pro campo |
| `X3_VLDUSER` | `vlduser` | TEXT | Validação do usuário — **pode chamar U_xxx, crucial pra Fase 2** |
| `X3_WHEN` | `when_expr` | TEXT | Condição de exibição — quando o campo aparece |
| `X3_PROPRI` | `proprietario` | TEXT | S=padrão — melhora detecção de custom |
| `X3_BROWSE` | `browse` | TEXT | Se aparece no browse da rotina |
| `X3_TRIGGER` | `trigger` | TEXT | Se tem gatilho vinculado (S/N) |
| `X3_VISUAL` | `visual` | TEXT | Modo: Alterar/Visualizar/Ambos |
| `X3_CONTEXT` | `context` | TEXT | Contexto: Real/Virtual |
| `X3_FOLDER` | `folder` | TEXT | Pasta/aba onde o campo aparece |

**Schema SQLite — tabela `campos` atualizada:**
```sql
CREATE TABLE IF NOT EXISTS campos (
    tabela TEXT,
    campo TEXT,
    tipo TEXT,
    tamanho INTEGER,
    decimal INTEGER DEFAULT 0,
    titulo TEXT,
    descricao TEXT,
    validacao TEXT DEFAULT '',
    inicializador TEXT DEFAULT '',
    obrigatorio INTEGER DEFAULT 0,
    custom INTEGER DEFAULT 0,
    f3 TEXT DEFAULT '',
    cbox TEXT DEFAULT '',
    vlduser TEXT DEFAULT '',
    when_expr TEXT DEFAULT '',
    proprietario TEXT DEFAULT 'S',
    browse TEXT DEFAULT '',
    trigger_flag TEXT DEFAULT '',
    visual TEXT DEFAULT '',
    context TEXT DEFAULT '',
    folder TEXT DEFAULT '',
    PRIMARY KEY (tabela, campo)
)
```

**Impacto na Fase 2:**
- `f3` → permite descobrir relacionamentos entre tabelas automaticamente
- `vlduser` → permite mapear campo → função (U_xxx chamada na validação)
- `cbox` → permite saber valores permitidos de cada campo
- `proprietario` → melhora detecção de custom (hoje usa regex no nome do campo)

**Arquivo:** `backend/services/parser_sx.py` — `parse_sx3()` + `backend/services/database.py`

---

### 3.2 SX7 (Gatilhos) — 6 campos faltantes

| Campo CSV | Nome no SQLite | Por que é importante |
|---|---|---|
| `X7_CONDIC` | `condicao` | Condição de disparo — sem isso não sabe QUANDO o gatilho executa |
| `X7_PROPRI` | `proprietario` | S=padrão — saber se é customizado |
| `X7_SEEK` | `seek` | Chave de busca — como encontra o registro |
| `X7_ALIAS` | `alias` | Tabela consultada pelo gatilho |
| `X7_ORDEM` | `ordem` | Ordem de execução quando há múltiplos |
| `X7_CHAVE` | `chave` | Chave do registro |

**Nota:** O parser atual não extrai `X7_REGRA` da coluna correta? Verificar — no CSV a coluna `X7_REGRA` aparece **após** `D_E_L_E_T_`, o que pode causar problema no parsing.

**Schema SQLite — tabela `gatilhos` atualizada:**
```sql
CREATE TABLE IF NOT EXISTS gatilhos (
    campo_origem TEXT,
    sequencia TEXT,
    campo_destino TEXT,
    regra TEXT DEFAULT '',
    tipo TEXT DEFAULT '',
    tabela TEXT DEFAULT '',
    condicao TEXT DEFAULT '',
    proprietario TEXT DEFAULT 'S',
    seek TEXT DEFAULT '',
    alias TEXT DEFAULT '',
    ordem TEXT DEFAULT '',
    chave TEXT DEFAULT '',
    custom INTEGER DEFAULT 0,
    PRIMARY KEY (campo_origem, sequencia)
)
```

**Arquivo:** `backend/services/parser_sx.py` — `parse_sx7()` + `backend/services/database.py`

---

### 3.3 Parser Source — Extrações faltantes

#### 3.3.1 Call Graph (quem chama quem)

**O que falta:** Hoje extrai funções definidas no arquivo, mas não extrai **chamadas a outras funções**.

**Extrair:**
- Chamadas a `U_xxx()` — funções de usuário
- Chamadas a `ExecBlock()` — blocos de código
- Chamadas a `StaticCall()` / `FunName()` — chamadas indiretas
- Referências a outros fontes via `#Include`

**Como:**
```python
# Regex para chamadas de função U_
call_pattern = re.compile(r'\bU_(\w+)\s*\(', re.IGNORECASE)
calls_u = list(set(call_pattern.findall(content)))

# Chamadas ExecBlock
execblock_pattern = re.compile(r'ExecBlock\s*\(\s*["\'](\w+)', re.IGNORECASE)
calls_execblock = list(set(execblock_pattern.findall(content)))
```

**Armazenar em:** novo campo `calls_u` e `calls_execblock` na tabela `fontes`

#### 3.3.2 Referência de campos específicos

**O que falta:** Hoje extrai quais **tabelas** cada fonte acessa, mas não quais **campos** específicos.

**Extrair:**
```python
# Campos referenciados: SA1->A1_NOME, Replace A1_NOME, SC5->C5_NUM
field_ref_pattern = re.compile(r'(?:\w{2,3}->|Replace\s+)(\w{2,3}_\w+)', re.IGNORECASE)
fields_referenced = list(set(field_ref_pattern.findall(content)))
```

**Armazenar em:** novo campo `fields_ref` na tabela `fontes`

#### 3.3.3 Melhoria na detecção de PEs

**Adicionar padrão:** PE que começa com nome do módulo (ex: `FATA410`, `COMA120`)

**Arquivo:** `backend/services/parser_source.py`

---

### 3.4 SX6 (Parâmetros) — Campos faltantes

Verificar colunas completas do CSV:

| Campo CSV | Extraído? | Importância |
|---|---|---|
| `X6_FIL` | Sim | Filial |
| `X6_VAR` | Sim | Nome do parâmetro |
| `X6_TIPO` | Sim | Tipo |
| `X6_DESCRIC` + `X6_DESC1` | Sim | Descrição |
| `X6_CONTEUD` | Sim | Valor/Conteúdo |
| `X6_PROPRI` | Sim | Proprietário |
| `X6_PESSION` | **Falta** | Se é por filial (permite personalizar por filial) |

---

## 4. Bloco C — Armazenar melhor

### 4.1 Popular `fonte_chunks` (tabela existe mas está vazia)

**Problema:** A tabela `fonte_chunks` existe no schema mas nunca é populada. O código das funções deveria ser indexado pra busca semântica.

**Correção:** Na Fase 2 do ingestor, após parsear cada fonte:
1. Chunkar o código por função (já existe lógica em `parser_source.py`)
2. Inserir na tabela `fonte_chunks` com: id, arquivo, funcao, content, modulo
3. Indexar no ChromaDB coleção `fontes_custom`

### 4.2 Nova tabela: `vinculos` (para Fase 2)

**Propósito:** Armazenar as conexões entre elementos do sistema.

```sql
CREATE TABLE IF NOT EXISTS vinculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_origem TEXT,       -- 'campo', 'gatilho', 'pe', 'fonte', 'parametro'
    origem TEXT,            -- ex: 'A1_CGC', 'MT410GRV', 'MGFCOM01.prw'
    tipo_destino TEXT,      -- 'fonte', 'funcao', 'rotina', 'tabela', 'campo'
    destino TEXT,           -- ex: 'U_VALCLI', 'MATA120', 'SC7'
    tipo_vinculo TEXT,      -- 'valida', 'chama', 'escreve', 'le', 'dispara', 'pertence'
    contexto TEXT DEFAULT '',-- info adicional (ex: expressão de validação)
    custom INTEGER DEFAULT 0
)
```

**Exemplos de vínculos que serão populados na Fase 2:**

| Origem | Tipo | Destino | Vínculo |
|---|---|---|---|
| `A1_CGC` (campo) | campo → fonte | `U_VALCGC` | valida (via X3_VLDUSER) |
| `C7_PRODUTO` (campo) | campo → campo | `C7_DESCRI` | dispara (via SX7 gatilho) |
| `MT410GRV` (PE) | pe → rotina | `MATA410` | pertence |
| `MGFCOM01.prw` (fonte) | fonte → tabela | `SC7` | escreve (via RecLock) |
| `MGFCOM01.prw` (fonte) | fonte → tabela | `SA1` | le (via DbSelectArea) |
| `U_VALPED` (funcao) | funcao → funcao | `U_CHECKCRED` | chama |
| `MV_APRSC` (parametro) | parametro → rotina | `MATA110` | configura |

### 4.3 Nova tabela: `acervo_fontes` (metadados enriquecidos)

```sql
CREATE TABLE IF NOT EXISTS acervo_fontes (
    arquivo TEXT PRIMARY KEY,
    caminho TEXT,
    tipo TEXT,              -- 'prw', 'tlpp'
    modulo TEXT,
    total_funcoes INTEGER DEFAULT 0,
    total_user_funcs INTEGER DEFAULT 0,
    total_pes INTEGER DEFAULT 0,
    total_tabelas_leitura INTEGER DEFAULT 0,
    total_tabelas_escrita INTEGER DEFAULT 0,
    total_chamadas_u INTEGER DEFAULT 0,
    funcoes_json TEXT,      -- JSON array com detalhes de cada função
    classificacao TEXT,     -- 'ponto_entrada', 'rotina_custom', 'biblioteca', 'job', 'webservice'
    complexidade TEXT,      -- 'baixa', 'media', 'alta' (baseado em linhas + branches)
    linhas_codigo INTEGER DEFAULT 0,
    hash TEXT
)
```

---

## 5. Resumo de mudanças por arquivo

### Backend

| Arquivo | Mudanças |
|---|---|
| `backend/services/parser_sx.py` | Fix parse_six() colunas; adicionar 10 campos no parse_sx3(); adicionar 6 campos no parse_sx7(); fix X3_OBRIGAT |
| `backend/services/parser_source.py` | Fix encoding (chardet); adicionar call graph (calls_u, calls_execblock); adicionar fields_ref; melhorar PE detection |
| `backend/services/database.py` | Atualizar schema: indices (8 cols), campos (+10 cols), gatilhos (+6 cols), nova tabela vinculos, nova tabela acervo_fontes |
| `backend/services/ingestor.py` | Fase 1: usar novos campos dos parsers; Fase 2: popular fonte_chunks + acervo_fontes |
| `backend/services/knowledge.py` | Atualizar queries pra usar novos campos (f3, vlduser, proprietario, etc.) |
| `backend/services/doc_pipeline.py` | collect() usa novos campos; _build_context_text() inclui F3, CBOX, VLDUSER |

### Dados

| Arquivo | Mudança |
|---|---|
| Schema SQLite | 2 tabelas novas (vinculos, acervo_fontes) + 3 tabelas alteradas (indices, campos, gatilhos) |

---

## 6. Ordem de execução

```
PASSO 1: Fix parser_sx.py
├── Corrigir parse_six() (colunas erradas)
├── Adicionar campos no parse_sx3() (F3, CBOX, VLDUSER, etc.)
├── Adicionar campos no parse_sx7() (CONDIC, PROPRI, etc.)
├── Fix X3_OBRIGAT parsing
└── Testar com CSV real do cliente

PASSO 2: Fix parser_source.py
├── Encoding com chardet
├── Extrair call graph (calls_u, calls_execblock)
├── Extrair fields_ref
└── Testar com fontes reais do cliente

PASSO 3: Atualizar database.py
├── Schema indices (novas colunas)
├── Schema campos (novas colunas)
├── Schema gatilhos (novas colunas)
├── Nova tabela vinculos
├── Nova tabela acervo_fontes
└── Migration: recriar tabelas (DROP + CREATE)

PASSO 4: Atualizar ingestor.py
├── Fase 1: usar novos campos dos parsers
├── Fase 2: popular fonte_chunks + acervo_fontes
└── Testar ingestão completa com dados reais

PASSO 5: Atualizar knowledge.py + doc_pipeline.py
├── Queries com novos campos
├── collect() enriquecido
└── _build_context_text() com F3, CBOX, VLDUSER

PASSO 6: Testar tudo
├── Re-ingerir dados do cliente
├── Verificar que índices aparecem (antes eram 0!)
├── Verificar campos obrigatórios corretos
├── Verificar encoding dos fontes
└── Gerar doc e confirmar que saída melhorou
```

---

## 7. Impacto na Fase 2

Com esses dados extraídos corretamente, a Fase 2 poderá:

1. **Construir vínculos automaticamente:**
   - `X3_VLDUSER` contém `U_VALCLI` → vínculo campo→função
   - `X7_REGRA` contém `U_CALC` → vínculo gatilho→função
   - `calls_u` do parser_source → vínculo função→função (call graph)
   - `fields_ref` do parser_source → vínculo fonte→campo

2. **Classificar fontes automaticamente:**
   - Tem PE? → classificação "ponto_entrada"
   - Tem ExecAuto? → classificação "job/processamento"
   - Só U_ functions? → classificação "biblioteca"

3. **Detectar módulo com mais precisão:**
   - Usar tabelas de escrita (não só leitura)
   - Usar PEs detectados (MT410 → SIGAFAT)
   - Cruzar com SIX (índices custom → tabelas custom → módulo)

---

## 8. Fora de escopo (Fase 2+)

- Popular a tabela `vinculos` (será feito na Fase 2)
- Análise de complexidade de código (será feito na Fase 2)
- Geração do template MD do cliente (será feito após Fase 2)
- Merge padrão × cliente (será feito após templates prontos)
