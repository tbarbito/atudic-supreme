# Prompt: Extrator de Dicionario Protheus para Ingestao ATUDIC

> **Versao:** 1.0
> **Objetivo:** Extrair definicoes de dicionario de dados de um ambiente Protheus e gerar um arquivo estruturado (JSON ou Markdown) compativel com o **Ingestor de Dicionario do ATUDIC**.
> **Uso:** Aplique este prompt em um agente IA com acesso ao banco de dados Protheus de origem (SQL Server ou Oracle) para gerar o arquivo de exportacao.

---

## Contexto

Voce e um especialista em dicionario de dados TOTVS Protheus. Sua tarefa e extrair definicoes de objetos (campos, indices, tabelas, metadados) de um ambiente Protheus e gerar um arquivo de exportacao que sera importado em outro ambiente Protheus usando o sistema ATUDIC.

O arquivo gerado deve conter **todas as informacoes necessarias** para recriar os objetos no ambiente de destino, incluindo estrutura fisica (tipos SQL) e metadados logicos (SX2, SX3, SIX, TOP_FIELD, e tabelas auxiliares).

---

## Instrucoes

### 1. Identifique os objetos a exportar

Pergunte ao usuario quais objetos ele deseja exportar. Aceite qualquer combinacao de:

- **Campos individuais**: ex. "campo A1_XNOVO da SA1"
- **Indices individuais**: ex. "indice ordem F da SA1"
- **Tabelas completas**: ex. "tabela ZA1 inteira"
- **Metadados genericos**: ex. "gatilho SX7 do campo A1_COD", "parametro MV_XPARAM"

### 2. Execute as queries de extracao

Para cada tipo de objeto, execute as queries SQL abaixo no banco Protheus de origem.

> **IMPORTANTE**: Substitua `{EMPRESA}` pelo codigo da empresa (ex: `01`). A tabela fisica sera `SX3{EMPRESA}0` (ex: `SX3010`).

#### 2.1 Para CAMPOS (field)

```sql
-- Metadado SX3: definicao logica do campo
SELECT *
FROM SX3{EMPRESA}0
WHERE X3_ARQUIVO = '{ALIAS}'
  AND X3_CAMPO   = '{CAMPO}'
  AND D_E_L_E_T_ = ' '

-- Estrutura fisica: tipo SQL real da coluna
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME  = '{ALIAS}{EMPRESA}0'
  AND COLUMN_NAME = '{CAMPO}'

-- TOP_FIELD: metadado DBAccess (obrigatorio para campos N, D, L, M)
SELECT FIELD_TABLE, FIELD_NAME, FIELD_TYPE, FIELD_PREC, FIELD_DEC
FROM TOP_FIELD
WHERE FIELD_TABLE LIKE '%{ALIAS}{EMPRESA}0%'
  AND FIELD_NAME  = '{CAMPO}'
```

#### 2.2 Para INDICES (index)

```sql
-- Metadado SIX: definicao logica do indice
SELECT *
FROM SIX{EMPRESA}0
WHERE INDICE = '{ALIAS}'
  AND ORDEM  = '{ORDEM}'
  AND D_E_L_E_T_ = ' '

-- Estrutura fisica: colunas do indice
-- SQL Server:
SELECT
    i.name AS INDEX_NAME,
    COL_NAME(ic.object_id, ic.column_id) AS COLUMN_NAME,
    ic.key_ordinal
FROM sys.indexes i
JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
WHERE OBJECT_NAME(i.object_id) = '{ALIAS}{EMPRESA}0'
  AND i.name = '{ALIAS}{EMPRESA}0{ORDEM}'
ORDER BY ic.key_ordinal
```

#### 2.3 Para TABELAS COMPLETAS (full_table)

```sql
-- SX2: registro da tabela
SELECT *
FROM SX2{EMPRESA}0
WHERE X2_CHAVE = '{ALIAS}'
  AND D_E_L_E_T_ = ' '

-- SX3: todos os campos da tabela
SELECT *
FROM SX3{EMPRESA}0
WHERE X3_ARQUIVO = '{ALIAS}'
  AND D_E_L_E_T_ = ' '
ORDER BY X3_ORDEM

-- SIX: todos os indices da tabela
SELECT *
FROM SIX{EMPRESA}0
WHERE INDICE = '{ALIAS}'
  AND D_E_L_E_T_ = ' '
ORDER BY ORDEM

-- Estrutura fisica completa
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = '{ALIAS}{EMPRESA}0'
ORDER BY ORDINAL_POSITION

-- TOP_FIELD: todos os campos da tabela
SELECT FIELD_TABLE, FIELD_NAME, FIELD_TYPE, FIELD_PREC, FIELD_DEC
FROM TOP_FIELD
WHERE FIELD_TABLE LIKE '%{ALIAS}{EMPRESA}0%'

-- Indices fisicos
SELECT
    i.name AS INDEX_NAME,
    COL_NAME(ic.object_id, ic.column_id) AS COLUMN_NAME,
    ic.key_ordinal
FROM sys.indexes i
JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
WHERE OBJECT_NAME(i.object_id) = '{ALIAS}{EMPRESA}0'
ORDER BY i.name, ic.key_ordinal
```

#### 2.4 Para METADADOS GENERICOS

```sql
-- SX1 (perguntas): SELECT * FROM SX1{EMPRESA}0 WHERE X1_GRUPO = '{GRUPO}' AND D_E_L_E_T_ = ' '
-- SX5 (tabelas genericas): SELECT * FROM SX5{EMPRESA}0 WHERE X5_TABELA = '{TABELA}' AND D_E_L_E_T_ = ' '
-- SX6 (parametros): SELECT * FROM SX6{EMPRESA}0 WHERE X6_VAR = '{VARIAVEL}' AND D_E_L_E_T_ = ' '
-- SX7 (gatilhos): SELECT * FROM SX7{EMPRESA}0 WHERE X7_CAMPO = '{CAMPO}' AND D_E_L_E_T_ = ' '
-- SX9 (relacionamentos): SELECT * FROM SX9{EMPRESA}0 WHERE X9_DOM = '{ALIAS}' AND D_E_L_E_T_ = ' '
-- SXA (folders/abas): SELECT * FROM SXA{EMPRESA}0 WHERE XA_ALIAS = '{ALIAS}' AND D_E_L_E_T_ = ' '
-- SXB (browses): SELECT * FROM SXB{EMPRESA}0 WHERE XB_ALIAS = '{ALIAS}' AND D_E_L_E_T_ = ' '
```

### 3. Gere o arquivo de saida

Com os resultados das queries, gere o arquivo no formato especificado abaixo. O usuario pode escolher JSON ou Markdown.

---

## Formato JSON (recomendado para automacao)

```json
{
  "version": "1.0",
  "format": "atudic-ingest",
  "source_environment": "<nome descritivo do ambiente de origem>",
  "source_driver": "mssql|oracle",
  "exported_at": "<ISO 8601 timestamp>",
  "exported_by": "<usuario ou agente que gerou>",
  "company_code": "<codigo empresa, ex: 01>",
  "items": [
    {
      "type": "field",
      "table_alias": "<alias SX3, ex: SA1>",
      "field_name": "<nome do campo, ex: A1_XNOVO>",
      "physical": {
        "data_type": "<tipo SQL, ex: VARCHAR>",
        "character_maximum_length": 20,
        "numeric_precision": null,
        "numeric_scale": null
      },
      "sx3": {
        "X3_ARQUIVO": "SA1",
        "X3_CAMPO": "A1_XNOVO",
        "X3_TIPO": "C",
        "X3_TAMANHO": 20,
        "X3_DECIMAL": 0,
        "X3_TITULO": "Campo Novo",
        "X3_TITSPA": "Campo Nuevo",
        "X3_TITENG": "New Field",
        "X3_DESCRIC": "Campo customizado",
        "X3_DESCSPA": "Campo personalizado",
        "X3_DESCENG": "Custom field",
        "X3_PICTURE": "@!",
        "X3_VALID": "",
        "X3_USADO": "",
        "X3_RELACAO": "SPACE(20)",
        "X3_F3": "",
        "X3_NIVEL": "1",
        "X3_RESERV": "",
        "X3_CHECK": "",
        "X3_TRIGGER": "",
        "X3_PROPRI": "U",
        "X3_BROWSE": "S",
        "X3_VISUAL": "A",
        "X3_CONTEXT": "R",
        "X3_OBRIGAT": "",
        "X3_VLDUSER": "",
        "X3_CBOX": "",
        "X3_CBOXSPA": "",
        "X3_CBOXENG": "",
        "X3_PICTVAR": "",
        "X3_WHEN": "",
        "X3_ESSION": "",
        "X3_GRPSXG": "",
        "X3_FOLDER": "",
        "X3_PESSION": "",
        "X3_ORDEM": "99",
        "D_E_L_E_T_": " "
      },
      "top_field": {
        "FIELD_TABLE": "SA1010",
        "FIELD_NAME": "A1_XNOVO",
        "FIELD_TYPE": "C",
        "FIELD_PREC": "20",
        "FIELD_DEC": "0"
      }
    },
    {
      "type": "index",
      "indice": "<alias, ex: SA1>",
      "ordem": "<ordem, ex: F>",
      "physical": {
        "columns": ["A1_FILIAL", "A1_XNOVO"]
      },
      "six": {
        "INDICE": "SA1",
        "ORDEM": "F",
        "CHAVE": "A1_FILIAL+A1_XNOVO",
        "DESCRICAO": "Por Campo Novo",
        "DESCSPA": "Por Campo Nuevo",
        "DESCENG": "By New Field",
        "PROPRI": "U",
        "F3": "",
        "NICKNAME": "",
        "D_E_L_E_T_": " "
      }
    },
    {
      "type": "full_table",
      "table_alias": "<alias, ex: ZA1>",
      "physical": {
        "columns": [
          {
            "COLUMN_NAME": "ZA1_FILIAL",
            "DATA_TYPE": "VARCHAR",
            "CHARACTER_MAXIMUM_LENGTH": 8,
            "NUMERIC_PRECISION": null,
            "NUMERIC_SCALE": null
          }
        ]
      },
      "sx2": {
        "X2_CHAVE": "ZA1",
        "X2_PATH": "",
        "X2_ARQUIVO": "ZA1 - Cadastro Customizado",
        "X2_NOME": "Cadastro Customizado",
        "X2_NOMESPA": "Registro Personalizado",
        "X2_NOMEENG": "Custom Registration",
        "X2_MODO": "C",
        "X2_MODOUN": "E",
        "X2_UESSION": "",
        "X2_PESSION": "",
        "D_E_L_E_T_": " "
      },
      "fields": [
        {
          "sx3": { "...campos SX3 completos..." },
          "top_field": { "...se aplicavel..." }
        }
      ],
      "indexes": [
        {
          "six": { "...campos SIX completos..." },
          "physical_columns": ["ZA1_FILIAL", "ZA1_CODIGO"]
        }
      ]
    },
    {
      "type": "metadata",
      "meta_table": "<SX1|SX5|SX6|SX7|SX9|SXA|SXB|XXA|XAM|XAL>",
      "key": "<chave logica separada por |>",
      "values": {
        "...todos os campos da row..."
      }
    }
  ]
}
```

## Formato Markdown (para documentacao e revisao humana)

```markdown
# Dicionario Protheus — Exportacao para ATUDIC Ingestor
- **Ambiente de origem:** <nome>
- **Driver:** mssql|oracle
- **Empresa:** <codigo>
- **Exportado em:** <data/hora>
- **Exportado por:** <usuario>

---

## Campo: {ALIAS}.{CAMPO}

### Estrutura Fisica
| Atributo | Valor |
|----------|-------|
| Tipo SQL | VARCHAR(20) |
| Precision | - |
| Scale | - |

### Metadado SX3
| Campo SX3 | Valor |
|-----------|-------|
| X3_ARQUIVO | SA1 |
| X3_CAMPO | A1_XNOVO |
| X3_TIPO | C |
| X3_TAMANHO | 20 |
| X3_DECIMAL | 0 |
| X3_TITULO | Campo Novo |
| X3_DESCRIC | Campo customizado |
| X3_PICTURE | @! |
| X3_VALID | |
| X3_RELACAO | SPACE(20) |
| X3_F3 | |
| X3_NIVEL | 1 |
| X3_PROPRI | U |
| X3_BROWSE | S |
| X3_VISUAL | A |
| X3_CONTEXT | R |
| X3_OBRIGAT | |
| X3_VLDUSER | |
| X3_CBOX | |
| X3_WHEN | |
| X3_ORDEM | 99 |
| D_E_L_E_T_ | (espaco) |

### TOP_FIELD
| Campo | Valor |
|-------|-------|
| FIELD_TABLE | SA1010 |
| FIELD_NAME | A1_XNOVO |
| FIELD_TYPE | C |
| FIELD_PREC | 20 |
| FIELD_DEC | 0 |

---

## Indice: {ALIAS} Ordem {ORDEM}

### Estrutura Fisica
- **Colunas:** A1_FILIAL, A1_XNOVO

### Metadado SIX
| Campo SIX | Valor |
|-----------|-------|
| INDICE | SA1 |
| ORDEM | F |
| CHAVE | A1_FILIAL+A1_XNOVO |
| DESCRICAO | Por Campo Novo |
| PROPRI | U |
| D_E_L_E_T_ | (espaco) |

---

## Tabela Completa: {ALIAS}

### SX2 (Registro da Tabela)
| Campo SX2 | Valor |
|-----------|-------|
| X2_CHAVE | ZA1 |
| X2_ARQUIVO | ZA1 - Cadastro Customizado |
| X2_NOME | Cadastro Customizado |
| X2_MODO | C |

### Campos (SX3)
(repetir bloco de campo para cada campo da tabela)

### Indices (SIX)
(repetir bloco de indice para cada indice da tabela)

---

## Metadado: {META_TABLE} — {KEY}

| Campo | Valor |
|-------|-------|
| (todos os campos da row) |
```

---

## Regras de Validacao

Antes de gerar o arquivo, valide:

1. **D_E_L_E_T_ deve ser espaco** (`' '`). Nunca exportar registros com `D_E_L_E_T_ = '*'` (deletados).
2. **Campos de controle**: Nunca incluir `R_E_C_N_O_`, `R_E_C_D_E_L_`, `S_T_A_M_P_`, `I_N_S_D_T_` nos valores de metadado. Eles serao gerados automaticamente no destino.
3. **TOP_FIELD e obrigatorio** para campos dos tipos: `N` (numerico), `D` (data), `L` (logico), `M` (memo). Para tipo `C` (caractere) e opcional mas recomendado.
4. **X3_ORDEM**: manter a ordem original do source. Se nao disponivel, usar "99".
5. **Consistencia tipo/tamanho**: o tipo SQL fisico deve ser coerente com X3_TIPO e X3_TAMANHO:
   - `X3_TIPO = C` → `VARCHAR(X3_TAMANHO)`
   - `X3_TIPO = N` → `NUMERIC(X3_TAMANHO, X3_DECIMAL)`
   - `X3_TIPO = D` → `VARCHAR(8)` (Protheus armazena datas como string YYYYMMDD)
   - `X3_TIPO = L` → `VARCHAR(1)` (Protheus armazena logico como string)
   - `X3_TIPO = M` → `VARCHAR(10)` (Protheus memo e referencia)
6. **Indices**: a `CHAVE` no SIX usa `+` como separador de campos (ex: `A1_FILIAL+A1_COD+A1_LOJA`). Garantir que todos os campos referenciados existam nos items exportados ou ja existam no destino.
7. **X3_PROPRI**: marcar como `U` (user/customizado) se for campo customizado. Campos standard TOTVS usam `S`.

---

## Exemplo de Uso

**Pedido do usuario:**
> "Exporte os campos A1_XNOVO e A1_XCRED da SA1, com o indice ordem F, da empresa 01 do ambiente de producao."

**Resposta esperada:**
1. Executar queries de SX3, INFORMATION_SCHEMA, TOP_FIELD para cada campo
2. Executar queries de SIX, sys.indexes para o indice
3. Montar arquivo JSON/MD com todos os dados
4. Validar regras acima
5. Entregar arquivo pronto para upload no ATUDIC Ingestor

---

## Notas Importantes

- Este arquivo sera processado automaticamente pelo ATUDIC. Nao altere a estrutura dos campos.
- O ATUDIC fara validacao de duplicatas antes de aplicar — se o campo/indice/tabela ja existir no destino, sera reportado como warning e ignorado (nao sobrescreve).
- Para atualizar campos existentes (mudar tamanho, tipo, etc.), use o **Equalizador** do ATUDIC, nao o Ingestor.
- O Ingestor foi projetado para **adicionar objetos novos** que nao existem no destino.
