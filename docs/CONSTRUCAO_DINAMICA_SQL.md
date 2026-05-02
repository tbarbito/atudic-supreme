# Construcao Dinamica de INSERT/UPDATE — Equalizacao de Dicionario Protheus

Documento descrevendo a logica de geracao de comandos `INSERT` e `UPDATE`
durante a equalizacao de dicionario entre dois bancos Protheus.

**Resumo:** nada e hardcoded. Os comandos sao montados em runtime a partir
dos `dict` retornados pelo `SELECT *` no source, com regras especificas
do Protheus aplicadas por nome de coluna.

---

## Sumario

1. [Premissa](#1-premissa)
2. [Builder de INSERT — clone fiel do row source](#2-builder-de-insert--clone-fiel-do-row-source)
3. [Builder de UPDATE — apenas o que mudou](#3-builder-de-update--apenas-o-que-mudou)
4. [Quoting de identificadores e valores](#4-quoting-de-identificadores-e-valores)
5. [Resumo do que e dinamico vs. fixo](#5-resumo-do-que-e-dinamico-vs-fixo)

---

## 1. Premissa

Os comandos DML sao **gerados dinamicamente** a partir de tres entradas:

| Entrada | Origem |
|---|---|
| Estrutura das colunas | `dict` retornado pelo `SELECT * FROM <tabela_metadado>` no source |
| Nome fisico da tabela | Convencao Protheus: `{PREFIXO}{M0_CODIGO}0` (ex.: empresa `99` -> `SA1990`) |
| Chave logica do `WHERE` | Lookup em uma tabela de configuracao por metadado (`TABLE_KEYS`) |

Se a TOTVS adicionar uma coluna nova em qualquer tabela SX, ela ja e replicada
automaticamente, sem alteracao de codigo. A unica coisa "fixa" sao as
**regras Protheus** (tratamento de R_E_C_N_O_, R_E_C_D_E_L_, D_E_L_E_T_,
quoting, NOT NULL DEFAULT) e a tabela de chaves logicas.

---

## 2. Builder de INSERT — clone fiel do row source

```python
def build_insert_sql(table_name, row_dict, driver):
    cols, vals = [], []
    table_q = quote_id(table_name, driver)

    for k, v in sorted(row_dict.items()):       # ordenado p/ SQL deterministico
        key_upper = k.strip().upper()

        if key_upper == "R_E_C_N_O_":            # IDENTITY/SERIAL — banco gera
            continue

        if key_upper == "R_E_C_D_E_L_":          # forcado para 0
            cols.append(quote_id(key_upper, driver))
            vals.append("0")
            continue

        if key_upper == "D_E_L_E_T_":            # espaco se vazio
            cols.append(quote_id(key_upper, driver))
            vals.append(quote_value(v if v and str(v).strip() else " "))
            continue

        cols.append(quote_id(key_upper, driver))
        vals.append(quote_value(v))              # escapa aspas, NULL -> ' '

    return f"INSERT INTO {table_q} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
```

### Caracteristicas

- Nao ha lista fixa de colunas. O `dict` que entra vira o `INSERT` que sai.
- Se a TOTVS adicionar uma coluna nova ao SX3 numa atualizacao, ela ja e
  replicada automaticamente.
- A ordem e deterministica (`sorted`) — dois SELECTs iguais geram exatamente
  a mesma string SQL, garantindo hash SHA-256 estavel para o token de
  confirmacao.
- As regras de controle Protheus sao aplicadas **por nome da coluna**, nao
  por posicao.

### Exemplo concreto

Input — row `dict` retornado pelo `SELECT * FROM SX3990` no source:

```python
{
  "X3_ARQUIVO": "SA1",
  "X3_CAMPO":   "A1_NICKNAME",
  "X3_TIPO":    "C",
  "X3_TAMANHO": 20,
  "X3_DECIMAL": 0,
  "X3_TITULO":  "Apelido",
  "X3_DESCRIC": "Nome de fantasia do cliente",
  "R_E_C_N_O_": 18472,                 # <- omitido (IDENTITY/SERIAL gera)
  "R_E_C_D_E_L_": 0,                   # <- forcado para 0
  "D_E_L_E_T_": " ",
  ...
}
```

Output gerado:

```sql
INSERT INTO [SX3990] (
  D_E_L_E_T_, R_E_C_D_E_L_, X3_ARQUIVO, X3_CAMPO,
  X3_DECIMAL, X3_DESCRIC, X3_TAMANHO, X3_TIPO, X3_TITULO, ...
) VALUES (
  ' ', 0, 'SA1', 'A1_NICKNAME',
  0, 'Nome de fantasia do cliente', 20, 'C', 'Apelido', ...
)
```

### Tratamento das colunas de controle

| Coluna | Comportamento no INSERT |
|---|---|
| `R_E_C_N_O_` | **Omitida** — banco gera (`IDENTITY` no MSSQL, `SERIAL` no PG, sequence no Oracle) |
| `R_E_C_D_E_L_` | Forcado para `0` |
| `D_E_L_E_T_` | Forcado para `' '` (espaco) se vazio/null |
| Demais | Valor original do source com aspas escapadas; `NULL` substituido por `' '` |

---

## 3. Builder de UPDATE — apenas o que mudou

```python
def build_update_sql(table_name, set_dict, where_dict, driver):
    table_q = quote_id(table_name, driver)
    set_parts   = [f"{quote_id(c.upper(), driver)} = {quote_value(v)}"
                   for c, v in sorted(set_dict.items())]
    where_parts = [f"{quote_id(c.upper(), driver)} = {quote_value(v)}"
                   for c, v in sorted(where_dict.items())]
    return f"UPDATE {table_q} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
```

### Origem dos parametros

#### `set_dict` — colunas a atualizar

Vem da lista `diff_fields` retornada pelo comparador. Cada item tem o formato:

```python
{"field": "X3_TAMANHO", "val_a": "60", "val_b": "40"}
```

- `val_a` = valor no source (sera aplicado no target)
- `val_b` = valor atual no target (ignorado na geracao do UPDATE, usado apenas
  para exibicao no UI de revisao)

Antes de montar o `set_dict`, colunas de controle sao filtradas:

```python
CONTROL_COLUMNS = {"R_E_C_N_O_", "R_E_C_D_E_L_"}

set_dict = {}
for f in diff_fields:
    fname = f["field"].upper()
    if fname in CONTROL_COLUMNS or fname == "D_E_L_E_T_":
        continue
    set_dict[fname] = f["val_a"]
```

#### `where_dict` — chave logica para o WHERE

Lookup em uma tabela de configuracao mapeando o metadado para sua chave logica:

```python
TABLE_KEYS = {
    "SIX": ["INDICE", "ORDEM"],
    "SX1": ["X1_GRUPO", "X1_ORDEM"],
    "SX2": ["X2_CHAVE"],
    "SX3": ["X3_ARQUIVO", "X3_CAMPO"],
    "SX5": ["X5_FILIAL", "X5_TABELA", "X5_CHAVE"],
    "SX6": ["X6_VAR", "X6_FIL"],
    "SX7": ["X7_CAMPO", "X7_SEQUENC", "X7_REGRA"],
    "SX9": ["X9_DOM", "X9_IDENT", "X9_CDOM"],
    "SXA": ["XA_ALIAS", "XA_ORDEM"],
    "SXB": ["XB_ALIAS", "XB_TIPO"],
    "XXA": ["XXA_PERG", "XXA_ORDEM"],
    "XAM": ["XAM_ALIAS", "XAM_ORDEM"],
    "XAL": ["XAL_ALIAS", "XAL_CAMPO"],
}
```

Os valores do `WHERE` sao extraidos do row source da mesma chave:

```python
where_dict = {col: row_source[col] for col in TABLE_KEYS[meta_table]}
```

### Exemplo concreto

Comparador detectou que no SX3 do source o campo `A1_NOME` tem `X3_TAMANHO=60`,
mas no target esta `40`. `diff_fields` retorna:

```python
[{"field": "X3_TAMANHO", "val_a": "60", "val_b": "40"}]
```

Apos os filtros:

- `set_dict`   = `{"X3_TAMANHO": "60"}` (val_a vai para o target)
- `where_dict` = `{"X3_ARQUIVO": "SA1", "X3_CAMPO": "A1_NOME"}` (de `TABLE_KEYS["SX3"]`)

SQL gerado:

```sql
UPDATE [SX3990] SET X3_TAMANHO = '60'
              WHERE X3_ARQUIVO = 'SA1' AND X3_CAMPO = 'A1_NOME'
```

Se o diff tivesse cinco colunas divergentes, o `SET` teria cinco clausulas.
Se tivesse uma, so uma. **A funcao e totalmente data-driven**.

### Caso especial: campo SX3 com mudanca fisica

Quando um campo divergente tem alteracao em `X3_TIPO`, `X3_TAMANHO` ou
`X3_DECIMAL`, alem do `UPDATE SX3` o equalizador tambem gera:

- `ALTER COLUMN` no schema fisico (com sintaxe especifica por driver)
- `UPDATE TOP_FIELD` para sincronizar o cache do DBAccess

Esse `UPDATE TOP_FIELD` segue a mesma estrutura `set_dict` / `where_dict`:

```python
set_dict   = {"FIELD_TYPE": "C", "FIELD_PREC": "60", "FIELD_DEC": "0"}
where_dict = {"FIELD_TABLE": "SA1990", "FIELD_NAME": "A1_NOME"}
```

---

## 4. Quoting de identificadores e valores

Ambos os builders usam dois helpers comuns:

### `quote_id` — quoting de identificador

```python
def quote_id(name, driver):
    if driver == "mssql":
        return f"[{name}]"
    if driver == "postgresql":
        return f'"{name.lower()}"'
    return f'"{name}"'        # oracle / mysql / fallback
```

### `quote_value` — quoting de valor literal

```python
def quote_value(value):
    if value is None or value == "":
        return "' '"                       # Protheus nao aceita NULL
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("'", "''")      # SQL standard escape
    return f"'{s}'"
```

**Pontos relevantes:**

- Aspas simples no conteudo sao duplicadas (escape padrao SQL).
- Strings vazias e `NULL` viram `' '` (um espaco) — Protheus rejeita `NULL`.
- Booleanos viram `1`/`0` (compativel com `BIT`, `BOOLEAN`, `INT`).
- Numericos sao emitidos sem aspas.
- Nomes de tabela e coluna nunca vem do payload do cliente — vem das
  tabelas SX e do `INFORMATION_SCHEMA`. Mesmo assim sao quoted para
  evitar conflito com palavras reservadas.

---

## 5. Resumo do que e dinamico vs. fixo

| Pergunta | Resposta |
|---|---|
| Lista de colunas hardcoded? | Nao — vem do `dict` retornado pelo `SELECT *` |
| Nome da tabela hardcoded? | Nao — montado por convencao `{PREFIXO}{empresa}0` |
| Chave do `WHERE` hardcoded? | Nao — lookup em `TABLE_KEYS[meta_table]` |
| Quais colunas do `UPDATE`? | Apenas as que vieram em `diff_fields` do comparador |
| Tratamento de NULL/aspas? | Helper `quote_value` (escape `'` -> `''`, NULL -> `' '`) |
| Ordem das colunas estavel? | Sim — `sorted(dict.items())` para hash deterministico |

### O que e fixo

- **Regras Protheus por coluna**: omitir `R_E_C_N_O_`, forcar `R_E_C_D_E_L_=0`,
  forcar `D_E_L_E_T_=' '` quando vazio.
- **Tabela `TABLE_KEYS`**: define a chave logica de cada metadado SX.
- **Quoting por driver** (`[...]` vs `"..."` vs `"..."` lowercase).
- **Substituicao de NULL por `' '`** — limitacao da arquitetura Protheus.

### O que e dinamico

- Estrutura de colunas de cada tabela SX (clonada do `SELECT *`).
- Conjunto de colunas no `SET` do `UPDATE` (so o que diferiu).
- Valores do `WHERE` do `UPDATE` (extraidos do row source).
- Nome fisico da tabela (montado a partir do `M0_CODIGO` da empresa).
- Tipo SQL no DDL (lido do `INFORMATION_SCHEMA`, normalizado por driver).

Esse desenho garante que o equalizador continua funcionando sem manutencao
de codigo quando a TOTVS:

- Adiciona campos novos em tabelas SX existentes.
- Lanca uma nova versao com colunas extras nos metadados.
- Customizacoes locais introduzem campos `Z*` no SX3.

A unica situacao que exige ajuste de codigo e o surgimento de uma **tabela
de metadado nova** (alem das 13 ja mapeadas) — nesse caso, basta adicionar
uma entrada em `TABLE_KEYS` com as colunas que formam a chave logica.
