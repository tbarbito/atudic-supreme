# ExtraiRPO Database Schema — Complete Reference

**Database:** `workspace/clients/marfrig/db/extrairpo.db`
**Total tables:** 44 (+ sqlite_sequence)
**Generated:** 2026-03-26

---

## Table of Contents

1. [Source Code Analysis](#source-code-analysis) — fontes, funcao_docs, fonte_chunks, propositos, acervo_fontes, operacoes_escrita
2. [Graph / Vinculos](#graph--vinculos) — vinculos (relationship graph)
3. [Data Dictionary — Client](#data-dictionary--client) — tabelas, campos, indices, gatilhos, consultas, parametros, perguntas, pastas, relacionamentos, tabelas_genericas, record_counts
4. [Data Dictionary — Standard (padrao)](#data-dictionary--standard-padrao) — padrao_tabelas, padrao_campos, padrao_indices, padrao_gatilhos, padrao_consultas, padrao_parametros, padrao_pastas, padrao_relacionamentos, padrao_menus, padrao_pes
5. [Diff (Client vs Standard)](#diff-client-vs-standard) — diff
6. [Menus](#menus) — menus
7. [Jobs & Schedules](#jobs--schedules) — jobs, schedules
8. [Analista (AI Agent)](#analista-ai-agent) — analista_projetos, analista_demandas, analista_artefatos, analista_documentos, analista_mensagens, analista_diretrizes, analista_outputs
9. [Chat & Annotations](#chat--annotations) — chat_history, anotacoes
10. [Pipeline Control](#pipeline-control) — ingest_progress

---

## Source Code Analysis

### fontes (1,987 rows)

Core table storing metadata extracted from every custom source file (.prw, .prx, etc.).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| arquivo | TEXT | 1 | File name (e.g. `MGFCOM08.prw`) |
| caminho | TEXT | | Full file path on disk |
| tipo | TEXT | | Always `custom` for client sources |
| modulo | TEXT | | Protheus module (estoque, compras, financeiro, etc.) |
| funcoes | TEXT | | **JSON array** — all functions defined in the file |
| user_funcs | TEXT | | **JSON array** — User Functions (callable entry points) |
| pontos_entrada | TEXT | | **JSON array** — Pontos de Entrada (standard hooks) |
| tabelas_ref | TEXT | | **JSON array** — tables READ by this source |
| write_tables | TEXT | | **JSON array** — tables WRITTEN by this source |
| includes | TEXT | | **JSON array** — #include files |
| calls_u | TEXT | | **JSON array** — other User Functions called (U_xxx) |
| calls_execblock | TEXT | | **JSON array** — ExecBlock/NamedExecBlock calls |
| fields_ref | TEXT | | **JSON array** — non-table fields referenced (e.g. TX_ variables) |
| lines_of_code | INTEGER | | Total lines of code |
| hash | TEXT | | MD5 hash for change detection |
| encoding | TEXT | | File encoding (cp1252, utf-8, etc.) |
| reclock_tables | TEXT | | **JSON array** — tables locked via RecLock() |

**JSON column structures:**

```json
// funcoes, user_funcs, pontos_entrada — simple string arrays
["A010TOK"]

// tabelas_ref, write_tables, reclock_tables — table alias arrays
["SB2", "SB8", "SB9", "SBE", "SBF", "SDA", "SX1"]

// calls_u — called user functions
["MGFEST65", "MGFINT38", "MGFINT75", "MGFINU03"]

// calls_execblock — ExecBlock references
["MGFCOMDF"]

// includes — include file names
["totvs.ch"]

// fields_ref — non-standard field references
["TX_A103CLAS"]
```

**Sample data:**
```
arquivo              | tipo   | modulo   | funcoes        | tabelas_ref | write_tables | calls_u
_F3XX8FIL.prw        | custom |          | ["_F3XX8FIL"]  | []          | []           | []
A010TOK.PRW          | custom | estoque  | ["A010TOK"]    | ["SB1"]     | []           | ["MGFEST65","MGFINT38",...]
MGFA103.prw          | custom | compras  | ["A103CLAS"..] | ["SC1"]     | []           | [...]
```

---

### funcao_docs (8,766 rows)

Per-function documentation — both auto-extracted and AI-generated.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| arquivo | TEXT | 1 | Source file name |
| funcao | TEXT | 2 | Function name |
| tipo | TEXT | | Function type: Function, User Function, WSMETHOD, METHOD, Static Function |
| assinatura | TEXT | | Signature string (e.g. `A010TOK()`) |
| resumo | TEXT | | **JSON object** or plain text — function summary. AI-generated entries have dual structure |
| tabelas_ref | TEXT | | **JSON array** — tables referenced by this function |
| campos_ref | TEXT | | **JSON array** — specific fields referenced |
| chama | TEXT | | **JSON array** — functions called by this function |
| chamada_por | TEXT | | **JSON array** — functions that call this function |
| retorno | TEXT | | Return value description |
| fonte | TEXT | | Source of the doc: `auto` (static analysis) or `ia` (AI-generated) |
| updated_at | TEXT | | Last update timestamp |
| params | TEXT | | **JSON object** — parameter info (sx6, sx1 references) |

**JSON column structures:**

```json
// resumo (when fonte='ia') — dual human/machine summary
{
  "humano": "A função trata o motivo do bloqueio para aprovação...",
  "ia": {
    "acao": "validacao",
    "entidade": "outro",
    "tabelas_leitura": [],
    "tabelas_escrita": [],
    "campos_chave": [],
    "retorno_tipo": "logical",
    "retorno_descricao": ".T. permite, .F. bloqueia",
    "impacto": "medio"
  }
}

// resumo (when fonte='auto') — empty or plain text

// tabelas_ref, campos_ref, chama, chamada_por — string arrays
["SC1"]
["C1_ZBLQFLG"]
["xMC11ASc"]
["A410CONS", "MT410BRW"]

// params — parameter references
{"sx6": [], "sx1": []}
```

**Sample data:**
```
arquivo          | funcao              | tipo       | fonte | resumo (truncated)
MGFCOM08.prw     | 06                  | Function   | ia    | {"humano": "A função trata o motivo do bloqueio..."}
MGFCOM11.prw     | AprovarSolicitacao  | WSMETHOD   | auto  | (empty)
applicationArea.prw | new              | METHOD     | auto  | (empty)
```

---

### fonte_chunks (8,597 rows)

Source code chunked by function — used for RAG retrieval and AI analysis.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | TEXT | 1 | Composite key: `{arquivo}::{funcao}` |
| arquivo | TEXT | | Source file name |
| funcao | TEXT | | Function name |
| content | TEXT | | Full source code of the function |
| modulo | TEXT | | Protheus module |

**Sample data:**
```
id                         | arquivo          | funcao    | modulo   | content (preview)
_F3XX8FIL.prw::_F3XX8FIL  | _F3XX8FIL.prw    | _F3XX8FIL |          | User Function _F3XX8FIL\nLocal aArea := GetArea()...
A010TOK.PRW::A010TOK       | A010TOK.PRW      | A010TOK   | estoque  | User Function A010TOK\n\tlocal lRet := .T....
```

---

### propositos (189 rows)

AI-generated high-level purpose descriptions for source files.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tipo | TEXT | | Entity type (always `fonte`) |
| chave | TEXT | 1 | Source file name |
| proposito | TEXT | | **JSON object** or plain text — detailed purpose description |
| tags | TEXT | | **JSON array** — classification tags |
| updated_at | TEXT | | Last update timestamp |

**JSON column structures:**

```json
// proposito — dual human/machine purpose (newer format)
{
  "humano": "O programa AGRMATR.prw automatiza o envio de pedidos de compra...",
  "ia": {
    "processo": "pedido_compras",
    "modulo": "SIGACOM",
    "tipo_programa": "relatorio",
    "rotinas_padrao": ["MATA120"],
    "tabelas_principais": ["SC7", "SC1"],
    "tabelas_escrita": ["SC7"],
    "funcionalidades": ["envio de pedido por e-mail", "geração de relatório"],
    "complexidade": "media",
    "fluxo_resumido": "SC1 → cotação → SC7 → aprovação"
  },
  "tags": ["compras", "pedido"]
}

// proposito — plain text (older format)
"O programa MGF260Conc.prw tem como objetivo principal realizar a conciliação..."

// tags — string array
["compras", "pedido", "validação"]
```

---

### acervo_fontes (0 rows — empty)

Aggregated source file statistics. Structure mirrors `fontes` but with numeric counts instead of JSON arrays.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| arquivo | TEXT | 1 | File name |
| caminho | TEXT | | File path |
| tipo | TEXT | | Source type |
| modulo | TEXT | | Module |
| total_funcoes | INTEGER | | Count of functions |
| total_user_funcs | INTEGER | | Count of User Functions |
| total_pes | INTEGER | | Count of Pontos de Entrada |
| total_tabelas_leitura | INTEGER | | Count of tables read |
| total_tabelas_escrita | INTEGER | | Count of tables written |
| total_chamadas_u | INTEGER | | Count of U_ calls |
| funcoes_json | TEXT | | JSON — function names |
| classificacao | TEXT | | AI classification |
| complexidade | TEXT | | Complexity rating |
| linhas_codigo | INTEGER | | Lines of code |
| hash | TEXT | | File hash |

---

### operacoes_escrita (2,528 rows)

Structured write operations extracted from source code. Each row represents a RecLock, SQL UPDATE/DELETE, or dbDelete found in a function, with the fields being written and their value origins.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment ID |
| arquivo | TEXT | | Source file name (e.g. `MGFTAE14.PRW`) |
| funcao | TEXT | | Function name containing the write operation |
| tipo | TEXT | | Operation type: `reclock_inc`, `reclock_alt`, `db_delete`, `sql_delete`, `sql_update` |
| tabela | TEXT | | Target table alias (e.g. `ZZM`, `SC5`) |
| campos | TEXT | | **JSON array** — fields being written in this operation |
| origens | TEXT | | **JSON object** — maps each field to its value source |
| condicao | TEXT | | Enclosing IF condition (e.g. `bEmite`, `NOT (bEmite)`) |
| linha | INTEGER | | Line number in source file |

**Indexes:** `idx_oe_tabela` (tabela), `idx_oe_arquivo` (arquivo)

**Operation type distribution:**

| tipo | count |
|------|------:|
| reclock_alt | 1,753 |
| reclock_inc | 535 |
| db_delete | 207 |
| sql_delete | 30 |
| sql_update | 3 |

**Coverage:** 656 source files, 398 distinct tables affected.

**JSON column structures:**

```json
// campos — list of fields written in the RecLock block
["ZZM_VLDESC", "ZZM_VLACR", "ZZM_STATUS"]

// origens — maps field name to value source with classification
{
  "ZZM_VLDESC": "variavel:nVAL_DESCONTO",    // from a function parameter/local variable
  "ZZM_STATUS": "literal:'1'",                // hardcoded value
  "ZZM_EMITE": "tabela:SA2->A2_ZEMINFE",     // from another table
  "ZZM_OBS": "tela:M->ZZM_OBS",              // from screen (user input)
  "ZZM_EMISSA": "funcao:STOD(cDAT_EMISSAO)"  // from a function call
}

// condicao — the IF condition that controls whether this write executes
"bEmite"           // write only happens when bEmite is true
"NOT (bEmite)"     // write only happens when bEmite is false
""                 // unconditional write
```

**Sample data:**
```
arquivo          | funcao     | tipo        | tabela | campos                      | condicao    | linha
MGFTAE14.PRW     | MGFTAE14   | reclock_inc | ZZM    | ["ZZM_VLDESC","ZZM_VLACR"]  | NOT (cAcao == '3') | 183
MGFTAE15.PRW     | TAE15_GRV  | reclock_alt | ZZM    | ["ZZM_VLDESC","ZZM_VLACR"]  | bEmite      | 329
MGFTAE15.PRW     | TAE15_GRV  | reclock_alt | ZZM    | ["ZZM_OBS","ZZM_VENCE"]     | NOT (bEmite)| 353
```

**Key use cases:**
- "Who writes to field X?" → `SELECT * FROM operacoes_escrita WHERE campos LIKE '%FIELD%'`
- "What conditions control writing to table Y?" → `SELECT condicao FROM operacoes_escrita WHERE tabela='Y' AND condicao != ''`
- "What fields does source Z modify?" → `SELECT tabela, campos FROM operacoes_escrita WHERE arquivo='Z'`

---

## Graph / Vinculos

### vinculos (19,686 rows)

Universal relationship graph connecting all entities (functions, sources, tables, modules).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment ID |
| tipo | TEXT | NN | Relationship type (see distribution below) |
| origem_tipo | TEXT | NN | Origin entity type: `funcao`, `fonte`, `campo`, `pe`, `gatilho`, `modulo`, `tabela` |
| origem | TEXT | NN | Origin entity key |
| destino_tipo | TEXT | NN | Destination entity type |
| destino | TEXT | NN | Destination entity key |
| modulo | TEXT | | Module context |
| contexto | TEXT | | Additional context |
| peso | INTEGER | | Weight/importance (default 1) |

**Relationship type distribution:**

| tipo | count | description |
|------|------:|-------------|
| funcao_definida_em | 8,607 | Function → Source file it's defined in |
| fonte_le_tabela | 4,839 | Source file → Table it reads |
| fonte_chama_funcao | 3,935 | Source file → Function it calls |
| fonte_escreve_tabela | 1,114 | Source file → Table it writes to |
| campo_consulta_tabela | 420 | Field → Table it looks up (F3 consulta) |
| pe_afeta_rotina | 411 | Ponto de Entrada → Standard routine it hooks into |
| gatilho_executa_funcao | 172 | Trigger → Function it executes |
| campo_valida_funcao | 137 | Field → Validation function |
| tabela_pertence_modulo | 40 | Table → Module ownership |
| modulo_integra_modulo | 11 | Module → Module integration |

**Sample data:**
```
id | tipo                  | origem_tipo | origem     | destino_tipo | destino          | modulo
1  | funcao_definida_em    | funcao      | _F3XX8FIL  | fonte        | _F3XX8FIL.prw    |
2  | funcao_definida_em    | funcao      | A010TOK    | fonte        | A010TOK.PRW      | estoque
5  | funcao_definida_em    | funcao      | A103CLAS   | fonte        | A103CLAS.PRW     | compras
```

---

## Data Dictionary — Client

### tabelas (11,264 rows)

Client's table dictionary (SX2).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| codigo | TEXT | 1 | Table alias (e.g. `SA1`, `SC5`, `ZA1`) |
| nome | TEXT | | Table description |
| modo | TEXT | | Access mode: C=Compartilhado, E=Exclusivo |
| custom | INTEGER | | 1=custom table, 0=standard |

**Sample data:**
```
codigo | nome                          | modo | custom
AAE    | Índices - Taxas               | C    | 0
AAF    | Históricos                    | C    | 0
AAG    | Ocorrências                   | C    | 0
```

---

### campos (187,633 rows)

Client's field dictionary (SX3) — the largest table. Every field in every table.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela | TEXT | 1 | Table alias |
| campo | TEXT | 2 | Field name |
| tipo | TEXT | | Field type: C=Character, N=Numeric, D=Date, L=Logical, M=Memo |
| tamanho | INTEGER | | Field size |
| decimal | INTEGER | | Decimal places |
| titulo | TEXT | | Short title (column header) |
| descricao | TEXT | | Full description |
| validacao | TEXT | | Validation expression (X3_VALID) |
| inicializador | TEXT | | Initializer expression (X3_RELACAO) |
| obrigatorio | INTEGER | | 1=required, 0=optional |
| custom | INTEGER | | 1=custom field, 0=standard |
| f3 | TEXT | | F3 lookup (consulta padrão) |
| cbox | TEXT | | Combobox values |
| vlduser | TEXT | | User validation expression |
| when_expr | TEXT | | When expression (field editability) |
| proprietario | TEXT | | Owner: S=System, N=Custom |
| browse | TEXT | | Show in browse: S/N |
| trigger_flag | TEXT | | Has trigger: S/N |
| visual | TEXT | | Visual mode: V=Visualize, A=Alter |
| context | TEXT | | Context: R=Real, V=Virtual |
| folder | TEXT | | Folder/tab number |
| valid_customizada | INTEGER | | 1=has custom validation, 0=standard |

**Sample data:**
```
tabela | campo       | tipo | tamanho | titulo       | obrigatorio | custom | f3  | proprietario
ABG    | ABG_NUMSA   | C    | 6       | Nr.SA Armaz. | 1           | 0      |     | N
ABG    | ABG_CODTEC  | C    | 14      | Atendente    | 1           | 0      |     | S
ABG    | ABG_SEQ     | C    | 2       | Seq.Atendim. | 1           | 0      |     | S
```

---

### indices (26,486 rows)

Client's index dictionary (SIX).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela | TEXT | 1 | Table alias |
| ordem | TEXT | 2 | Index order number |
| chave | TEXT | | Index key expression |
| descricao | TEXT | | Index description |
| proprietario | TEXT | | S=System, N=Custom |
| f3 | TEXT | | F3 lookup target |
| nickname | TEXT | | Index nickname |
| showpesq | TEXT | | Show in search: S/N |
| custom | INTEGER | | 1=custom index |

**Sample data:**
```
tabela | ordem | chave                                                           | descricao
AA5    | 1     | AA5_FILIAL+AA5_CODSER                                          | Serviço
AA5    | 2     | AA5_FILIAL+AA5_TES                                             | TES
```

---

### gatilhos (18,051 rows)

Client's trigger dictionary (SX7).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| campo_origem | TEXT | 1 | Origin field that fires the trigger |
| sequencia | TEXT | 2 | Sequence number |
| campo_destino | TEXT | | Destination field to fill |
| regra | TEXT | | Expression to evaluate |
| tipo | TEXT | | Trigger type: P=Posicione (seek) |
| tabela | TEXT | | Target table alias |
| condicao | TEXT | | Condition expression |
| proprietario | TEXT | | S=System |
| seek | TEXT | | S=Do seek, N=No seek |
| alias | TEXT | | Table alias for seek |
| ordem | TEXT | | Index order for seek |
| chave | TEXT | | Seek key expression |
| custom | INTEGER | | 1=custom trigger |
| regra_customizada | INTEGER | | 1=custom rule expression |

**Sample data:**
```
campo_origem | seq | campo_destino | regra            | tipo | tabela | alias
A5_FORNECE   | 004 | A5_NOMERED    | SA2->A2_NREDUZ   | P    | SA2    | SA2
A5_LOJA      | 001 | A5_NOMEFOR    | SA2->A2_NOME     | P    | SA2    | SA2
A6_CODCLI    | 001 | A6_LOJCLI     | SA1->A1_LOJA     | P    |        |
```

---

### consultas (46,669 rows)

Client's lookup definitions (SXB).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| alias | TEXT | 1 | Lookup alias name |
| tipo | TEXT | | Line type: 1=Header, 2=Filter, 3=?, 4=Column def, 5=Column content |
| sequencia | TEXT | 2 | Sequence |
| coluna | TEXT | 3 | Column number |
| descricao | TEXT | | Column description |
| conteudo | TEXT | | Content/expression |

**Sample data:**
```
alias   | tipo | seq | coluna | descricao    | conteudo
ZM0DEP  | 4    | 01  | 02     | Desc Deposit | ZM0_DESDEP
ZM0DEP  | 5    | 01  |        |              | ZM0->ZM0_CODDEP
ZM0DEP  | 5    | 02  |        |              | ZM0->ZM0_DESDEP
```

---

### parametros (18,435 rows)

Client's parameter dictionary (SX6).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| filial | TEXT | 1 | Branch code (empty = all branches) |
| variavel | TEXT | 2 | Parameter name (MV_xxx) |
| tipo | TEXT | | Value type: C=Char, N=Numeric, L=Logical |
| descricao | TEXT | | Description |
| conteudo | TEXT | | Current value |
| proprietario | TEXT | | S=System |
| custom | INTEGER | | 1=custom parameter |

**Sample data:**
```
filial | variavel     | tipo | descricao                              | conteudo    | custom
       | MV_973ENC    | C    | Arquivo de termo de encerramento ISSQN | MTR973EN.TRM| 0
       | MV_A030FAC   | C    | Campos SA1 que não...                  |             | 0
```

---

### perguntas (59,485 rows)

Client's report/process parameter prompts (SX1).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| grupo | TEXT | 1 | Question group (routine name) |
| ordem | TEXT | 2 | Order within group |
| pergunta | TEXT | | Question text |
| variavel | TEXT | | Variable name (MV_CHx) |
| tipo | TEXT | | Value type: C, N, D |
| tamanho | INTEGER | | Field size |
| decimal | INTEGER | | Decimal places |
| f3 | TEXT | | F3 lookup |
| validacao | TEXT | | Validation expression |
| conteudo_padrao | TEXT | | Default value |

**Sample data:**
```
grupo    | ordem | pergunta         | variavel | tipo | tamanho | f3
ABSENT2  | 03    | Data Até ?       | MV_CH3   | D    | 8       |
ABSENT2  | 04    | Departamento De? | MV_CH4   | C    | 9       | SQB
```

---

### relacionamentos (25,930 rows)

Client's table relationship definitions (SX9).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela_origem | TEXT | 1 | Source table alias |
| identificador | TEXT | 2 | Relationship ID |
| tabela_destino | TEXT | 3 | Target table alias |
| expressao_origem | TEXT | | Source key expression |
| expressao_destino | TEXT | | Target key expression |
| proprietario | TEXT | | S=System |
| condicao_sql | TEXT | | SQL condition |
| custom | INTEGER | | 1=custom relationship |

**Sample data:**
```
tabela_origem | id  | tabela_destino | expressao_origem                          | expressao_destino
AA3           | 001 | ABE            | AA3_CODFAB+AA3_LOJAFA+AA3_CODPRO+AA3_NUMSER | ABE_CODFAB+ABE_LOJAFA+ABE_CODPRO+ABE_NUMSER
AA3           | 002 | ABD            | AA3_CODFAB+AA3_LOJAFA+AA3_CODPRO+AA3_NUMSER | ABD_CODFAB+ABD_LOJAFA+ABD_CODPRO+ABD_NUMSER
```

---

### pastas (1,833 rows)

Client's folder/tab definitions (SXA).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| alias | TEXT | 1 | Table alias |
| ordem | TEXT | 2 | Tab order |
| descricao | TEXT | | Tab label |
| proprietario | TEXT | | S=System |
| agrupamento | TEXT | | Grouping |

---

### tabelas_genericas (12,890 rows)

Client's generic lookup tables (SX5).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| filial | TEXT | 1 | Branch (empty = all) |
| tabela | TEXT | 2 | Table code (2-char) |
| chave | TEXT | 3 | Key value |
| descricao | TEXT | | Description |
| custom | INTEGER | | 1=custom entry |

**Sample data:**
```
filial | tabela | chave | descricao                          | custom
       | 00     | 83    | REGIME ESPECIAL DE TRIBUTACAO       | 0
       | 00     | 84    | TIPO DE REGISTRO - DMA/BA           | 0
```

---

### record_counts (923 rows)

Row counts per table in the client's production environment.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela | TEXT | 1 | Table alias |
| registros | INTEGER | | Row count in production |

**Sample data:**
```
tabela | registros
ABW    | 1
ACA    | 1
ACB    | 217840
ACC    | 672
ACJ    | 99
```

---

## Data Dictionary — Standard (padrao)

These tables mirror the client dictionary tables but contain the **standard Protheus dictionary** for diff comparison.

### padrao_tabelas (9,558 rows)

Standard table dictionary. Same schema as `tabelas`.

### padrao_campos (174,358 rows)

Standard field dictionary. Same schema as `campos` (minus `valid_customizada` column).

### padrao_indices (25,059 rows)

Standard index dictionary. Same schema as `indices`.

### padrao_gatilhos (16,418 rows)

Standard trigger dictionary. Same schema as `gatilhos` (minus `regra_customizada` column).

### padrao_consultas (55,330 rows)

Standard lookup definitions.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela | TEXT | 1 | Lookup alias / table reference |
| tipo | TEXT | 2 | Line type |
| sequencia | TEXT | 3 | Sequence |
| coluna | TEXT | 4 | Column number |
| descricao | TEXT | | Description |
| contem | TEXT | | Content expression |

### padrao_parametros (11,632 rows)

Standard parameter dictionary. Same schema as `parametros`.

### padrao_pastas (1,706 rows)

Standard folder definitions.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela | TEXT | 1 | Table alias |
| ordem | TEXT | 2 | Tab order |
| descricao | TEXT | | Tab label |
| proprietario | TEXT | | S=System |

### padrao_relacionamentos (25,160 rows)

Standard table relationships.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tabela_origem | TEXT | 1 | Source table |
| identificador | TEXT | 2 | Relationship ID |
| tabela_destino | TEXT | 3 | Target table |
| expressao | TEXT | | Source key expression |
| expressao_dest | TEXT | | Target key expression |
| proprietario | TEXT | | S=System |

### padrao_menus (2,872 rows)

Standard module menus and their routines.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| modulo | TEXT | 1 | Module code (e.g. SIGATCF) |
| rotina | TEXT | 2 | Routine function name |
| nome | TEXT | | Menu item label |
| menu | TEXT | | Menu path (e.g. "Atualizações > Cadastros") |
| ordem | INTEGER | | Display order |

**Sample data:**
```
modulo   | rotina  | nome            | menu                                   | ordem
SIGATCF  | MATA175 | Configurações   | Atualizações > Configurações           | 2
SIGATCF  | SBIR190 | Dados Cadastrais| Atualizações > Configurações > Dados C.| 3
```

### padrao_pes (457 rows)

Standard Pontos de Entrada (extension hooks) documentation from TDN.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| nome | TEXT | 1 | PE name |
| modulo | TEXT | | Module (SIGAFIN, SIGACOM, etc.) |
| rotina | TEXT | | Standard routine it belongs to |
| onde_chamado | TEXT | | Context where it's called |
| objetivo | TEXT | | Purpose description |
| params_entrada | TEXT | | Input parameters |
| params_saida | TEXT | | Expected return |
| link_tdn | TEXT | | URL to TDN documentation |

**Sample data:**
```
nome     | modulo   | rotina  | onde_chamado          | objetivo                                      | link_tdn
200GEMBX | SIGAFIN  | FINA200 | Baixa bancária CNAB   | Tratar valores dos títulos na baixa bancária   | http://tdn.totvs.com/...
A085ABRW | SIGAFIN  | FINA085A| Browse de Ordens Pgto | Filtro do browse de Ordens de Pagamento        | https://tdn.totvs.com/...
```

---

## Diff (Client vs Standard)

### diff (31,768 rows)

Differences between client and standard dictionaries.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| tipo_sx | TEXT | 1 | Dictionary type: `campo` (SX3) or `gatilho` (SX7) |
| tabela | TEXT | 2 | Table alias |
| chave | TEXT | 3 | Field or trigger key |
| acao | TEXT | 4 | Action: `adicionado`, `alterado`, `removido` |
| campo_diff | TEXT | 5 | Which property changed (for `alterado`) |
| valor_padrao | TEXT | | Standard value |
| valor_cliente | TEXT | | Client value |
| modulo | TEXT | | Module |

**Action distribution:**

| acao | count |
|------|------:|
| alterado | 16,694 |
| adicionado | 14,991 |
| removido | 83 |

**Type distribution:**

| tipo_sx | count |
|---------|------:|
| campo | 29,975 |
| gatilho | 1,793 |

**Sample data:**
```
tipo_sx  | tabela | chave       | acao       | campo_diff | valor_padrao | valor_cliente
campo    | AA1    | AA1_CODSUP  | adicionado |            |              |
campo    | AA1    | AA1_ICAROL  | adicionado |            |              |
campo    | SA1    | A1_COD      | alterado   | tamanho    | 6            | 8
```

---

## Menus

### menus (43,934 rows)

Client's full menu structure — all modules, all routines.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| modulo | TEXT | 1 | Module code (SIGACOM, SIGAFIN, etc.) |
| rotina | TEXT | 2 | Routine function name |
| nome | TEXT | | Menu item label |
| menu | TEXT | | Full menu path |
| ordem | INTEGER | | Display order |

**Sample data:**
```
modulo  | rotina     | nome              | menu                            | ordem
SIGAAPD | APDR050    | Status Avaliações | Relatorios > Relatório Crystall | 0
SIGAAPT | APTA080    | Tipos             | Atualizações > Cadastros        | 0
```

---

## Jobs & Schedules

### jobs (214 rows)

AppServer INI job configurations.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| arquivo_ini | TEXT | 1 | INI file name |
| sessao | TEXT | 2 | Session/section name |
| rotina | TEXT | | Function to execute (U_xxx) |
| refresh_rate | INTEGER | | Refresh rate in seconds |
| parametros | TEXT | | Parameters or "N/A" |

**Sample data:**
```
arquivo_ini           | sessao    | rotina       | refresh_rate | parametros
AppServer_job01.ini   | MGFFIN81  | U_MGFFIN81   | 90           | N/A
AppServer_job01.ini   | MGFFINA4  | U_MGFFINA4   | 90           | N/A
```

---

### schedules (96 rows)

Protheus scheduler (CFGA020) entries.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| codigo | TEXT | 1 | Schedule code |
| rotina | TEXT | | Function to execute |
| empresa_filial | TEXT | 2 | Company/branch (e.g. 01/010001) |
| environment | TEXT | | Environment name |
| modulo | INTEGER | | Module code number |
| status | TEXT | | Status: Ativo, Inativo |
| tipo_recorrencia | TEXT | | Recurrence type: Diario, Semanal, Mensal |
| detalhe_recorrencia | TEXT | | Human-readable recurrence description |
| execucoes_dia | INTEGER | | Executions per day |
| intervalo | TEXT | | Interval between executions |
| hora_inicio | TEXT | | Start time |
| data_criacao | TEXT | | Creation date |
| ultima_execucao | TEXT | | Last execution date |
| ultima_hora | TEXT | | Last execution time |
| recorrencia_raw | TEXT | | Raw recurrence expression |

**Sample data:**
```
codigo | rotina       | empresa_filial | environment | status | tipo_recorrencia | hora_inicio
000339 | U_MGFFATCK   | 01/010001      | SCHD15      | Ativo  | Diario           | 08:00
000239 | U_MGFWSC28   | 01/010041      | SCHD25      | Ativo  | Diario           | 00:00
000268 | U_MGFLOJ01   | 01/010065      | SCHD22      | Ativo  | Diario           | 09:00
```

---

## Analista (AI Agent)

These tables support the "Peça ao Analista" feature — an agentic AI pipeline that analyzes demands and generates technical specifications.

### analista_projetos (6 rows)

Top-level projects (each demand creates one).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| nome | TEXT | NN | Project name (usually the user's request) |
| descricao | TEXT | | Description |
| status | TEXT | | Status: `rascunho`, `concluido` |
| created_at | TEXT | | Creation timestamp |
| updated_at | TEXT | | Last update |

---

### analista_demandas (13 rows)

Classified demands with entity extraction and research data.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| tipo | TEXT | NN | Demand type: `projeto`, `bug`, `consulta` |
| nome | TEXT | NN | Demand description |
| descricao | TEXT | | Extended description |
| status | TEXT | | Status: `classificando`, `concluido` |
| entidades_json | TEXT | | **JSON object** — extracted entities |
| research_json | TEXT | | **JSON object** — research results |
| confianca | REAL | | AI confidence score |
| created_at | TEXT | | Creation timestamp |
| updated_at | TEXT | | Last update |

**JSON column structures:**

```json
// entidades_json — extracted entities from the demand
{
  "tabelas": ["SA1"],
  "campos": [],
  "fontes": [],
  "parametros": [],
  "grupos_sx1": [],
  "tabelas_sx5": [],
  "modulos": []
}
```

---

### analista_artefatos (52 rows)

Generated artifacts (fields, tables, sources to create/modify).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| projeto_id | INTEGER | NN | FK to analista_projetos |
| tipo | TEXT | NN | Artifact type: `campo`, `fonte`, `tabela`, `indice` |
| nome | TEXT | NN | Artifact name |
| tabela | TEXT | | Related table |
| acao | TEXT | | Action: `criar`, `alterar` |
| spec | TEXT | | Text specification |
| created_at | TEXT | | Timestamp |
| spec_json | TEXT | | **JSON** — structured specification |
| demanda_id | INTEGER | | FK to analista_demandas |

**JSON column structures:**
```json
// spec_json
{"descricao": "Função de validação do campo E2_VENCTO"}
```

---

### analista_documentos (39 rows)

Generated documents (technical specs, management reports).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| projeto_id | INTEGER | NN | FK to analista_projetos |
| tipo | TEXT | NN | Document type: `gerencial`, `tecnico` |
| titulo | TEXT | NN | Document title |
| conteudo | TEXT | NN | Full markdown content |
| created_at | TEXT | | Timestamp |

---

### analista_mensagens (31 rows)

Chat conversation history with the analyst agent.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| projeto_id | INTEGER | NN | FK to analista_projetos |
| role | TEXT | NN | `user` or `assistant` |
| content | TEXT | NN | Message content |
| tool_data | TEXT | | JSON — tool call data |
| created_at | TEXT | | Timestamp |
| demanda_id | INTEGER | | FK to analista_demandas |

---

### analista_diretrizes (12 rows)

Knowledge base of development guidelines for the AI analyst.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| tipo_demanda | TEXT | | Demand type this applies to (e.g. `bug`) |
| categoria | TEXT | | Category: `mvc`, `query`, `sx3`, etc. |
| titulo | TEXT | NN | Guideline title |
| conteudo | TEXT | NN | Full guideline text |
| fonte | TEXT | | Source: `seed` (built-in) |
| ativo | INTEGER | | 1=active |
| created_at | TEXT | | Timestamp |

**Sample data:**
```
id | tipo_demanda | categoria | titulo                         | conteudo (preview)
1  |              | mvc       | MVC — Estrutura básica         | Fontes MVC do Protheus usam funções padrão: ModelDef()...
2  |              | mvc       | MVC — Validações no Model      | Validações em MVC devem ser feitas no ModelDef via regra...
3  | bug          | query     | Query — RECNO em subquery      | Nunca use R_E_C_N_O_ em subqueries ou JOINs...
```

---

### analista_outputs (8 rows)

Final outputs generated by the analyst (AtuDic JSON, Markdown specs).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| demanda_id | INTEGER | | FK to analista_demandas |
| formato | TEXT | NN | Output format: `json`, `markdown` |
| conteudo | TEXT | NN | Full output content |
| titulo | TEXT | | Output title |
| created_at | TEXT | | Timestamp |

**Sample AtuDic JSON output structure:**
```json
{
  "format": "atudic-ingest",
  "version": "1.0",
  "items": [
    {
      "type": "field_diff",
      "name": "A2_ZTPCTAB",
      "tabela": "SA2",
      ...
    }
  ]
}
```

---

## Chat & Annotations

### chat_history (0 rows — empty)

General-purpose chat history (not the analyst chat).

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| role | TEXT | | user/assistant |
| content | TEXT | | Message content |
| sources | TEXT | | JSON — source references |
| doc_updated | TEXT | | Document that was updated |
| created_at | TEXT | | Timestamp |

---

### anotacoes (0 rows — empty)

User annotations on any entity.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| id | INTEGER | 1 | Auto-increment |
| tipo | TEXT | | Entity type |
| chave | TEXT | | Entity key |
| texto | TEXT | | Annotation text |
| autor | TEXT | | Author (default: `consultor`) |
| tags | TEXT | | JSON array of tags |
| data | TEXT | | Timestamp |

---

## Pipeline Control

### ingest_progress (33 rows)

Tracks the progress of data ingestion pipeline stages.

| Column | Type | PK | Description |
|--------|------|:--:|-------------|
| item | TEXT | 1 | Item being processed (e.g. `SX2.csv`, `SX3.csv`) |
| fase | INTEGER | | Pipeline phase number |
| status | TEXT | | Status: `done`, `error`, `running` |
| error_msg | TEXT | | Error message if failed |
| updated_at | TEXT | | Last update timestamp |

**Sample data:**
```
item     | fase | status | error_msg | updated_at
SX2.csv  | 1    | done   |           | 2026-03-20 19:44:44
SX3.csv  | 1    | done   |           | 2026-03-20 19:44:53
SIX.csv  | 1    | done   |           | 2026-03-20 19:44:54
```

---

## Summary Statistics

| Category | Tables | Total Rows |
|----------|-------:|------------|
| Source Code Analysis | 5 | 19,539 |
| Graph (vinculos) | 1 | 19,686 |
| Client Dictionary | 11 | 409,098 |
| Standard Dictionary | 10 | 322,550 |
| Diff | 1 | 31,768 |
| Menus | 1 | 43,934 |
| Jobs & Schedules | 2 | 310 |
| Analista (AI) | 7 | 161 |
| Chat & Annotations | 2 | 0 |
| Pipeline Control | 1 | 33 |
| **Total** | **41** | **~847,079** |

---

## Entity Relationship Overview

```
fontes ──────── funcao_docs (arquivo)
   │                │
   │                ├── fonte_chunks (arquivo + funcao)
   │                │
   └──── vinculos ──┘  (universal graph connecting everything)
             │
             ├── tabelas / campos / indices / gatilhos
             ├── padrao_* (standard mirror)
             └── diff (computed delta)

analista_projetos
   ├── analista_demandas
   ├── analista_artefatos
   ├── analista_documentos
   ├── analista_mensagens
   └── analista_outputs

menus ←→ padrao_menus (client vs standard)
parametros ←→ padrao_parametros
jobs / schedules (standalone)
```
