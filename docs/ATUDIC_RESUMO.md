# AtuDic — Modulo de Dicionario do AtuDIC

## Visao Geral

O **AtuDic** e o modulo de gerenciamento de dicionario Protheus do AtuDIC. Permite comparar, validar, equalizar e ingerir definicoes de dicionario entre ambientes Protheus, operando sobre as 13 tabelas de metadados padrao (SX2, SX3, SIX, SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL).

---

## Funcionalidades Habilitadas

### 1. Listar Empresas

`GET /api/dictionary/companies/<conn_id>`

Consulta a tabela `SYS_COMPANY` de uma conexao e retorna as empresas disponiveis (codigos como `01`, `02`, etc.).

---

### 2. Comparar Dicionario

`POST /api/dictionary/compare`

Compara metadados entre **dois bancos Protheus** (conexao A vs conexao B) para uma mesma empresa.

- Compara as 13 tabelas de metadados usando chaves primarias logicas (ex: `X3_ARQUIVO + X3_CAMPO` para SX3)
- Identifica registros **apenas em A**, **apenas em B** e **diferentes** (com detalhe campo a campo)
- Suporta filtro por tabelas especificas e por alias de tabela Protheus
- Opcao de incluir ou excluir registros deletados (`D_E_L_E_T_ = '*'`)
- Ignora automaticamente colunas de controle (`R_E_C_N_O_`, `R_E_C_D_E_L_`, `S_T_A_M_P_`, `I_N_S_D_T_`)
- Salva resultado no historico com resumo e duracao

---

### 3. Validar Integridade

`POST /api/dictionary/validate`

Verifica a consistencia interna de **um unico ambiente** entre metadados Protheus e o schema fisico do banco. Executa ate 19 camadas de validacao:

**Camadas Basicas (1-4):**
| Camada | Descricao |
|--------|-----------|
| `sx2_schema` | Tabelas registradas no SX2 que nao existem fisicamente |
| `sx3_schema` | Campos do SX3 que nao existem na tabela fisica |
| `sx3_topfield` | Campos D/N/M sem registro ou com tipo divergente no TOP_FIELD |
| `six_indexes` | Indices do SIX sem indice fisico correspondente |

**Camadas Avancadas (F1-F5):**
| Camada | Descricao |
|--------|-----------|
| `schema_sx3` | Colunas fisicas que existem mas nao tem registro no SX3 |
| `sx3_field_size` | Tamanho do campo fisico diferente do declarado no SX3 |
| `virtual_in_schema` | Campos virtuais do SX3 que existem fisicamente (nao deveriam) |
| `sx2_unique_fields` | Campos da chave unica (X2_UNICO) que nao existem no SX3 |
| `sx2_unique_virtual` | Campos da chave unica que sao virtuais |
| `sx2_no_sx3` | Tabelas no SX2 sem nenhum campo no SX3 |
| `sx3_no_sx2` | Campos no SX3 cuja tabela nao existe no SX2 |
| `sx2_no_six` | Tabelas no SX2 sem nenhum indice no SIX |
| `six_no_sx2` | Indices no SIX cuja tabela nao existe no SX2 |
| `six_fields_sx3` | Campos usados em indices (CHAVE) que nao existem no SX3 |
| `six_virtual_memo` | Indices que referenciam campos virtuais ou memo |
| `duplicates` | Registros duplicados em SX3 ou SIX |
| `sx2_sharing` | Tabelas que compartilham colunas fisicas com outra tabela |
| `sx3_ref_sxg` | Campos com X3_GRPSXG que referenciam grupo inexistente |
| `sx3_ref_sxa` | Campos com X3_FOLDER que referenciam folder inexistente |
| `sx3_ref_sxb` | Campos com X3_BROWSE/CBOX que referenciam combo inexistente |

- Aceita parametro `layers` para executar apenas camadas especificas
- Salva resultado no historico

---

### 4. Equalizar Dicionario

Sincroniza seletivamente estrutura entre dois bancos Protheus. Fluxo em duas etapas:

#### 4.1 Preview

`POST /api/dictionary/equalize/preview`

Gera os SQLs que seriam executados **sem aplicar nada**. Recebe a lista de `items` (diferencas selecionadas do compare) e retorna:

- **Fase 1 (DDL):** `ALTER TABLE ADD COLUMN`, `CREATE TABLE`, `CREATE INDEX`
- **Fase 2 (DML):** `INSERT`/`UPDATE` em SX2, SX3, SIX, TOP_FIELD e demais metadados
- Token de confirmacao (hash SHA-256 dos SQLs gerados)

#### 4.2 Executar

`POST /api/dictionary/equalize/execute`

Aplica os SQLs em transacao atomica no banco de destino:

- **Fase 1 (DDL):** Alteracoes de schema (fisico primeiro)
- **Fase 2 (DML):** Metadados depois
- **Fase 3 (Signal):** `UPDATE SYSTEM_INFO` para invalidar cache do AppServer
- **Fase 4 (TcRefresh):** Chamada REST `ZATUREF` para refresh do DBAccess
- Qualquer erro = **ROLLBACK completo**
- Salva resultado no historico com detalhes de execucao

**Regra de ouro:** fisico primeiro (DDL), metadado depois (DML).

---

### 5. Ingestor de Dicionario

Importa definicoes de dicionario a partir de **arquivo externo** (JSON ou Markdown) e aplica no banco de destino. Fluxo em tres etapas:

#### 5.1 Upload + Parse

`POST /api/dictionary/ingest/upload`

Aceita upload via `multipart/form-data` ou JSON inline. Formatos suportados:

- **JSON** (`format: "atudic-ingest"`)
- **Markdown** (headers `##` com blocos Campo/Indice/Tabela/Metadado)
- Auto-deteccao por extensao ou conteudo

**Tipos de item suportados:**
| Tipo | Descricao |
|------|-----------|
| `field` | Campo novo (DDL + INSERT SX3 + INSERT TOP_FIELD) |
| `field_diff` | Atualizacao de campo existente (UPDATE SX3 + DDL se necessario) |
| `index` | Indice novo (CREATE INDEX + INSERT SIX) |
| `full_table` | Tabela inteira (CREATE TABLE + todos metadados) |
| `metadata` | INSERT generico em qualquer tabela de metadado (SX1, SX5, SX6, SX7, etc.) |
| `metadata_diff` | UPDATE generico em registro de metadado existente |

Validacoes no parse:
- Remove colunas de controle (`R_E_C_N_O_`, `R_E_C_D_E_L_`, `S_T_A_M_P_`, `I_N_S_D_T_`)
- Filtra colunas invalidas usando schema de referencia (`protheus_metadata_schema.py`)
- Forca `D_E_L_E_T_` como espaco se vazio

#### 5.2 Preview

`POST /api/dictionary/ingest/preview`

Gera SQLs sem executar, com as mesmas validacoes do equalizador:
- Detecta duplicatas (campo/indice/tabela ja existe no destino)
- Gera DDL a partir do SX3 quando nao ha informacao fisica no arquivo
- Auto-gera TOP_FIELD para tipos N, D, L, M
- Retorna token de confirmacao

#### 5.3 Executar

`POST /api/dictionary/ingest/execute`

Execucao identica ao equalizador (4 fases), com `operation_type = 'ingest'` no historico.

---

### 6. Historico de Operacoes

| Endpoint | Descricao |
|----------|-----------|
| `GET /api/dictionary/history` | Lista operacoes recentes (compare, validate, equalize, ingest) |
| `GET /api/dictionary/history/<id>` | Detalhes completos de uma operacao |
| `DELETE /api/dictionary/history/<id>` | Exclui registro do historico |

---

### 7. Exportar CSV

`GET /api/dictionary/export/<operation_type>/<history_id>`

Exporta resultado de qualquer operacao como CSV (separador `;`):
- **compare:** Tabela, Tipo (Apenas em A/B, Diferente), Chave, Campo, Valor_A, Valor_B
- **validate:** Camada, Tipo, Tabela, Campo, Detalhe
- **equalize/ingest:** Fase, Descricao, SQL, Origem

---

## Schema de Referencia

O modulo `protheus_metadata_schema.py` contem o schema completo das 13 tabelas de metadados Protheus (colunas e tipos SQL), usado para validar dados antes de gerar INSERTs. Fonte: INFORMATION_SCHEMA do SQL Server (Protheus 12.1.2310+).

---

## Seguranca

Todos os endpoints requerem autenticacao via `@require_admin`. Operacoes de escrita (equalize/ingest) exigem token de confirmacao (hash dos SQLs) para prevenir execucao acidental.

---

## Drivers Suportados

- **SQL Server (mssql)** — quoting com `[coluna]`
- **Oracle** — quoting com `"COLUNA"`
- **PostgreSQL** — quoting com `"coluna"` (lowercase)
