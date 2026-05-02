# Equalizacao de Dicionario Protheus — Logica Tecnica

Documento de referencia descrevendo a logica de execucao para sincronizar
seletivamente a estrutura de dicionario entre dois bancos Protheus
(**source** = referencia, **target** = destino).

---

## Sumario

1. [Visao geral do processo](#1-visao-geral-do-processo)
2. [Cenarios de equalizacao](#2-cenarios-de-equalizacao)
3. [Modelo de execucao em duas etapas](#3-modelo-de-execucao-em-duas-etapas)
4. [Carregamento de metadados (queries SELECT)](#4-carregamento-de-metadados-queries-select)
5. [Introspeccao do schema fisico](#5-introspeccao-do-schema-fisico)
6. [Pre-validacao metadado vs fisico](#6-pre-validacao-metadado-vs-fisico)
7. [Geracao de SQL por cenario](#7-geracao-de-sql-por-cenario)
8. [Regras Protheus aplicadas no SQL](#8-regras-protheus-aplicadas-no-sql)
9. [Execucao transacional](#9-execucao-transacional)
10. [Sinalizacao de mudanca de dicionario (SYSTEM_INFO)](#10-sinalizacao-de-mudanca-de-dicionario-system_info)
11. [Request REST para o AppServer Protheus (TcRefresh)](#11-request-rest-para-o-appserver-protheus-tcrefresh)
12. [Seguranca de execucao](#12-seguranca-de-execucao)

---

## 1. Visao geral do processo

A equalizacao consiste em replicar do banco source para o banco target tres
classes de objetos do dicionario Protheus:

- **Objetos fisicos** — tabelas, colunas e indices no schema relacional.
- **Metadados Protheus** — registros nas tabelas SX (SX2, SX3, SIX, SX1, SX5,
  SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL).
- **Metadados do DBAccess** — registros na tabela `TOP_FIELD` (controla o
  reconhecimento de campos pelo middleware Protheus).

A regra de ouro do processo e: **fisico primeiro (DDL), metadado depois (DML),
em uma unica transacao atomica**. Qualquer erro durante a execucao provoca
`ROLLBACK` completo, restaurando o estado anterior do banco target.

Apos o `COMMIT`, e disparado um `TcRefresh()` via REST no AppServer Protheus
para invalidar o cache do DBAccess.

---

## 2. Cenarios de equalizacao

A diferenca entre source e target e classificada em seis cenarios:

| Cenario | Origem do diff | DDL | DML |
|---|---|---|---|
| Campo faltante | `SX3.only_a` | `ALTER TABLE ADD COLUMN` | `INSERT SX3` + `INSERT TOP_FIELD` |
| Campo divergente | `SX3.different` | `ALTER COLUMN` (so se fisico difere) | `UPDATE SX3` + `UPDATE TOP_FIELD` |
| Indice faltante | `SIX.only_a` | `CREATE INDEX` | `INSERT SIX` |
| Tabela inteira nova | `SX2.only_a` | `CREATE TABLE` + N `CREATE INDEX` | `INSERT SX2` + N `INSERT SX3` + N `INSERT SIX` + N `INSERT TOP_FIELD` |
| Metadado puro | `<X>.only_a` (SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL) | — | `INSERT <X>` |
| Metadado divergente | `<X>.different` | — | `UPDATE <X>` (so colunas divergentes) |

A chave logica de cada metadado e fixada em uma tabela de configuracao:

```
SX2 -> (X2_CHAVE)
SX3 -> (X3_ARQUIVO, X3_CAMPO)
SIX -> (INDICE, ORDEM)
SX5 -> (X5_FILIAL, X5_TABELA, X5_CHAVE)
SX6 -> (X6_VAR, X6_FIL)
SX7 -> (X7_CAMPO, X7_SEQUENC, X7_REGRA)
SX9 -> (X9_DOM, X9_IDENT, X9_CDOM)
SXA -> (XA_ALIAS, XA_ORDEM)
SXB -> (XB_ALIAS, XB_TIPO)
XXA -> (XXA_PERG, XXA_ORDEM)
XAM -> (XAM_ALIAS, XAM_ORDEM)
XAL -> (XAL_ALIAS, XAL_CAMPO)
```

Essa chave e usada tanto na comparacao (montar `only_a` / `only_b` / `different`)
quanto na clausula `WHERE` dos `UPDATE`.

Nome fisico das tabelas Protheus:
`{PREFIXO}{M0_CODIGO}0` (ex.: empresa `99` -> `SA1990`, `SX3990`, `SIX990`).

---

## 3. Modelo de execucao em duas etapas

A equalizacao acontece em duas chamadas separadas:

### 3.1 Etapa de **Preview**

Recebe a lista de items a equalizar (cada item descreve um cenario da secao 2).
Gera os SQLs em memoria, **sem executar nada** no target. Retorna:

- Lista de DDLs (Fase 1)
- Lista de DMLs (Fase 2)
- Lista de warnings (DDLs ignorados, divergencias detectadas, dependencias ausentes)
- Resumo agregado (contagens por tipo)
- **Token de confirmacao**: hash SHA-256 do conteudo concatenado de todos os SQLs

```
token = SHA-256( "\n".join(stmt.sql for stmt in all_statements) )
```

### 3.2 Etapa de **Execute**

Recebe os mesmos SQLs gerados no preview e o token. Antes de abrir a conexao
de escrita, recalcula o hash:

```python
expected_token = sha256("\n".join(s["sql"] for s in sql_statements))
if expected_token != confirmation_token:
    raise ValueError("Token de confirmacao invalido")
```

Se houver qualquer alteracao no payload entre preview e execute, o hash diverge
e a execucao e bloqueada. Esse mecanismo impede que o cliente edite os SQLs
revisados pelo usuario antes de submeter para execucao real.

### 3.3 Fluxo completo

```
[1] Comparar (diff entre source e target)
       v
[2] Usuario seleciona items a equalizar
       v
[3] Preview        -> retorna SQLs + token SHA-256
       v
       (usuario revisa o SQL exato no UI)
       v
[4] Execute        -> envia mesmos SQLs + mesmo token
       v
[5] BEGIN
    Fase 1: DDL no fisico
    Fase 2: DML nos metadados
    Fase 3: UPDATE SYSTEM_INFO (sinal de metadata change)
    COMMIT
       v
[6] Fase 4: TcRefresh REST por tabela alterada
       v
[7] Auditoria persistida (status: success / partial)
```

---

## 4. Carregamento de metadados (queries SELECT)

Para cada item recebido no preview, o processo identifica quais tabelas SX
precisam ser carregadas e executa um `SELECT *` por tabela em cada banco:

```
field / field_diff   -> SX3
index                -> SIX
full_table           -> SX2 + SX3 + SIX
metadata / diff      -> tabela apontada por meta_table
```

Implementacao do SELECT (variacao por driver):

```python
def fetch_all_rows(cursor, driver, table_name):
    if driver == "mssql":      query = f"SELECT * FROM [{table_name}]"
    elif driver == "oracle":   query = f"SELECT * FROM {table_name}"
    elif driver == "postgresql": query = f"SELECT * FROM {table_name.lower()}"
    else:                       query = f'SELECT * FROM "{table_name}"'
    cursor.execute(query)
    return [dict(r) for r in cursor.fetchall()]
```

As linhas retornadas sao indexadas em estruturas de acesso rapido:

```
sx2[ALIAS]                         = row
sx3[ARQUIVO|CAMPO]                 = row
sx3_by_table[ALIAS]                = [rows]
six[INDICE|ORDEM]                  = row
six_by_table[INDICE]               = [rows]
other[<METATABLE>|<chave composta>] = row
```

Esses dicionarios servem como **fonte da verdade** para a geracao dos `INSERT`
de metadado — todos os campos do row source sao clonados fielmente, evitando
derivacoes que poderiam introduzir inconsistencias.

---

## 5. Introspeccao do schema fisico

Em paralelo aos metadados, sao carregadas as informacoes do schema fisico dos
dois bancos. As queries sao **bulk** (uma chamada cobre todas as tabelas) para
minimizar overhead de rede:

### 5.1 Tabelas existentes

| Driver | Query |
|---|---|
| **mssql** | `SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'` |
| **postgresql** | `SELECT tablename FROM pg_tables WHERE schemaname='public'` |
| **mysql** | `SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'` |
| **oracle** | `SELECT TABLE_NAME FROM USER_TABLES` |

### 5.2 Colunas de todas as tabelas

| Driver | Query |
|---|---|
| **mssql** | `SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo'` |
| **postgresql** | mesma estrutura em `information_schema.columns WHERE table_schema='public'` |
| **mysql** | analoga, filtrando `TABLE_SCHEMA = DATABASE()` |
| **oracle** | `SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE FROM USER_TAB_COLUMNS` |

Resultado em memoria: `{TABLE_NAME: {COLUMN_NAME: <info>}}`.

### 5.3 Indices fisicos

Cada driver tem catalogo proprio:

- **mssql**: join entre `sys.indexes`, `sys.tables`, `sys.index_columns`,
  `sys.columns`, ordenado por `key_ordinal`.
- **postgresql**: join entre `pg_index`, `pg_class`, `pg_namespace`,
  `pg_attribute`, ordenado por `array_position(indkey, attnum)`.
- **mysql**: `INFORMATION_SCHEMA.STATISTICS` ordenado por `SEQ_IN_INDEX`.
- **oracle**: `USER_IND_COLUMNS` ordenado por `COLUMN_POSITION`.

Resultado: `{TABLE_NAME: {INDEX_NAME: [columns ordenadas]}}`.

A ordem das colunas no indice e relevante: o `CREATE INDEX` gerado replica
exatamente essa ordem.

### 5.4 TOP_FIELD

Tabela do DBAccess que define como o middleware enxerga cada campo:

```sql
SELECT FIELD_TABLE, FIELD_NAME, FIELD_TYPE, FIELD_PREC, FIELD_DEC FROM TOP_FIELD
```

Indexada em memoria como `{(TABLE.upper(), FIELD.upper()): {type, prec, dec, raw_table, raw_name}}`.
O prefixo `dbo.` e removido para normalizar.

---

## 6. Pre-validacao metadado vs fisico

Antes de gerar SQL, o processo confronta o metadado SX3/SIX com o objeto fisico
**no mesmo banco** (source e target separadamente). Divergencias indicam que o
banco esta em estado inconsistente — equalizar a partir desse estado tende a
contaminar o destino.

Mapeamento de tipo SX3 -> tipo SQL aceitavel:

```
X3_TIPO  Tipos SQL aceitos
-------  ------------------
C        VARCHAR, NVARCHAR, CHAR, NCHAR
N        NUMERIC, DECIMAL, FLOAT, REAL, DOUBLE PRECISION, INT, INTEGER
D        VARCHAR, NVARCHAR, CHAR, NCHAR    (data armazenada como string)
L        VARCHAR, NVARCHAR, CHAR, NCHAR, BIT, BOOLEAN
M        VARCHAR, NVARCHAR, TEXT, NTEXT
```

Verificacoes:

- **Tipo**: base SQL na coluna fisica precisa estar no conjunto aceito pelo `X3_TIPO`.
- **Tamanho** (tipos C/D/L/M): `X3_TAMANHO` == `CHARACTER_MAXIMUM_LENGTH`.
- **Precisao/escala** (tipo N): `(X3_TAMANHO, X3_DECIMAL)` == `(NUMERIC_PRECISION, NUMERIC_SCALE)`.
- **Indices**: cada `(INDICE, ORDEM)` no SIX precisa ter um indice fisico chamado
  `<INDICE><EMPRESA>0<ORDEM>` (ex.: SA1 ordem 2 -> `SA19902`).

Se alguma verificacao falha, e adicionado um warning bloqueante:

> ATENCAO: Foram detectadas divergencias entre metadado e objeto fisico no mesmo
> banco. Recomenda-se executar a rotina de Integridade antes de prosseguir com
> a equalizacao.

O usuario decide se prossegue mesmo assim — mas a divergencia fica registrada
no historico.

---

## 7. Geracao de SQL por cenario

### 7.1 Campo faltante

```sql
-- Fase 1 (DDL):
ALTER TABLE [SA1990] ADD [A1_NICKNAME] VARCHAR(20) NOT NULL DEFAULT '                    '

-- Fase 2 (DML):
INSERT INTO [SX3990] (X3_ARQUIVO, X3_CAMPO, X3_TIPO, ...)
              VALUES ('SA1', 'A1_NICKNAME', 'C', ...)

INSERT INTO TOP_FIELD (FIELD_TABLE, FIELD_NAME, FIELD_TYPE, FIELD_PREC, FIELD_DEC)
              VALUES ('SA1990', 'A1_NICKNAME', 'C', '20', '0')
```

Algoritmo:

1. Se a coluna **ja existe** fisicamente no target -> pula o `ALTER`, emite warning.
2. Le a definicao **fisica** do source (nao do SX3) — garante fidelidade total.
3. Aplica o tipo + clausula `NOT NULL DEFAULT` adequada (secao 8).
4. INSERT no SX3 e clone fiel do row source (nenhum campo derivado).
5. INSERT no TOP_FIELD apenas se o source tem entrada para esse campo.

### 7.2 Campo divergente

A funcao decide se gera DDL com base na lista de campos divergentes do SX3:

- Se algum dos campos divergentes esta em `{X3_TIPO, X3_TAMANHO, X3_DECIMAL}`,
  ha potencial mudanca fisica.
- Mas o `ALTER COLUMN` so e emitido se a definicao **fisica** do source e do
  target realmente difere — assim, quando apenas o SX3 estava errado e o fisico
  ja esta correto, nao se emite DDL desnecessario.

Sintaxe multi-dialeto:

| Driver | Sequencia DDL |
|---|---|
| **mssql** | (1) `DROP CONSTRAINT` da default constraint dinamica via `sys.default_constraints`, (2) `ALTER COLUMN tipo NOT NULL`, (3) `ADD CONSTRAINT DF_tabela_campo DEFAULT v` |
| **postgresql** | `ALTER TABLE t ALTER COLUMN c TYPE T, ALTER COLUMN c SET NOT NULL, ALTER COLUMN c SET DEFAULT v` |
| **oracle** | `ALTER TABLE t MODIFY (c TIPO NOT NULL DEFAULT v)` |

Detalhe MSSQL — recuperar o nome da default constraint antes de droppa-la:

```sql
DECLARE @df NVARCHAR(256);
SELECT @df = d.name
  FROM sys.default_constraints d
  JOIN sys.columns c ON d.parent_column_id = c.column_id
                    AND d.parent_object_id = c.object_id
 WHERE c.name = 'A1_NOME'
   AND d.parent_object_id = OBJECT_ID('SA1990');
IF @df IS NOT NULL EXEC('ALTER TABLE [SA1990] DROP CONSTRAINT ' + @df);
```

DML — `UPDATE` apenas das colunas divergentes:

```sql
UPDATE [SX3990] SET X3_TAMANHO = '60'
  WHERE X3_ARQUIVO = 'SA1' AND X3_CAMPO = 'A1_NOME'

UPDATE TOP_FIELD SET FIELD_TYPE='C', FIELD_PREC='60', FIELD_DEC='0'
  WHERE FIELD_TABLE='SA1990' AND FIELD_NAME='A1_NOME'
```

Colunas de controle (`R_E_C_N_O_`, `R_E_C_D_E_L_`, `D_E_L_E_T_`) sao filtradas
explicitamente do `SET`.

### 7.3 Indice faltante

```sql
-- Fase 1:
CREATE INDEX [SA19909] ON [SA1990] (A1_FILIAL, A1_NICKNAME)

-- Fase 2:
INSERT INTO [SIX990] (INDICE, ORDEM, CHAVE, DESCRICAO, ...)
              VALUES ('SA1', '9', 'A1_FILIAL+A1_NICKNAME', '...', ...)
```

As colunas e a ordem do indice vem da introspeccao fisica do source, nao do
parsing de `SIX.CHAVE`. Isso garante funcionamento mesmo quando a chave usa
expressoes ou funcoes.

### 7.4 Tabela inteira nova

Sequencia gerada:

1. `CREATE TABLE` com todas as colunas do source:
   - `R_E_C_N_O_` -> `INT IDENTITY(1,1) NOT NULL` (mssql) ou `SERIAL NOT NULL` (pg)
   - `R_E_C_D_E_L_` -> `INT NOT NULL DEFAULT 0`
   - Demais -> tipo + clausula `NOT NULL DEFAULT` da secao 8
2. `CREATE INDEX` para cada SIX da tabela.
3. `INSERT SX2` (clone fiel do row source).
4. `INSERT SX3` para cada campo.
5. `INSERT SIX` para cada indice.
6. `INSERT TOP_FIELD` para cada campo com entrada no source.

### 7.5 Metadado puro / divergente

Para SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL nao ha objeto fisico:
apenas DML.

- `metadata` -> `INSERT` clone do source.
- `metadata_diff` -> `UPDATE` apenas das colunas divergentes, com `WHERE`
  baseado na chave logica (secao 2).

---

## 8. Regras Protheus aplicadas no SQL

### 8.1 NOT NULL DEFAULT obrigatorio

Protheus **nao aceita NULL** em nenhum campo. Toda coluna criada ou alterada
recebe `NOT NULL DEFAULT` apropriado ao tipo:

| Tipo base | Default |
|---|---|
| `VARCHAR(N)`, `CHAR(N)`, `NVARCHAR(N)`, `NCHAR(N)` | `'<N espacos>'` |
| `NUMERIC`, `DECIMAL`, `FLOAT`, `REAL`, `DOUBLE PRECISION`, `INT`, `BIGINT`, `SMALLINT`, `TINYINT`, `BIT`, `BOOLEAN` | `0` |
| `TEXT`, `NTEXT`, `DATETIME`, `TIMESTAMP`, `IMAGE`, `BYTEA`, `BLOB` | `' '` (um espaco) |

Exemplo concreto: `VARCHAR(20)` recebe `NOT NULL DEFAULT '                    '`
(20 espacos literais, casando o `length` do campo).

### 8.2 Colunas de controle Protheus

| Coluna | Tratamento no INSERT |
|---|---|
| `R_E_C_N_O_` | **Omitida** — banco gera (`IDENTITY` no MSSQL, `SERIAL` no PG, sequence no Oracle) |
| `R_E_C_D_E_L_` | Forcado para `0` |
| `D_E_L_E_T_` | Forcado para `' '` (espaco) se vazio/null |
| `S_T_A_M_P_`, `I_N_S_D_T_` | Tratadas como colunas comuns ou ignoradas conforme a tabela |
| Demais | Valor original do source, com aspas escapadas |

`NULL` jamais e emitido — o helper de quoting substitui por `' '` (espaco).

### 8.3 Normalizacao de tipo entre dialetos

Para permitir replicar source -> target mesmo entre engines diferentes,
o tipo da coluna e normalizado:

| Source | mssql | postgresql | oracle |
|---|---|---|---|
| `VARCHAR(-1)` (sem limite) | `VARCHAR(MAX)` | `TEXT` | (manter origem) |
| `DATETIME` | `DATETIME` | `TIMESTAMP` | `DATETIME` |
| `TIMESTAMP` | `DATETIME` | `TIMESTAMP` | `TIMESTAMP` |
| `BIT` | `BIT` | `BOOLEAN` | `BIT` |
| `BOOLEAN` | `BIT` | `BOOLEAN` | `BOOLEAN` |
| `IMAGE` / `BLOB` / `BYTEA` | `IMAGE` | `BYTEA` | `IMAGE` |
| `NUMERIC(p,s)` / `DECIMAL(p,s)` | preserva precisao e escala | preserva | preserva |

### 8.4 Quoting de identificadores

| Driver | Sintaxe |
|---|---|
| `mssql` | `[NOME]` |
| `postgresql` | `"nome"` (lowercase) |
| `oracle` / outros | `"NOME"` |

### 8.5 Quoting de valores

```python
def quote_value(value):
    if value is None or value == "":
        return "' '"                  # Protheus nao aceita NULL
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("'", "''") # SQL escape
    return f"'{s}'"
```

Aspas simples no conteudo sao duplicadas (SQL standard escape). Strings vazias
viram `' '` (um espaco) para nao violar `NOT NULL`.

---

## 9. Execucao transacional

A execucao roda em uma unica transacao por banco target. A conexao e aberta
em modo write (autocommit OFF, readonly OFF).

```
BEGIN
   |
   v
Fase 1 — DDL                 (ALTER / CREATE TABLE / CREATE INDEX / drop+recriar default)
   |
   v
Fase 2 — DML                 (INSERT / UPDATE em SX*, TOP_FIELD)
   |
   v
Fase 3 — SYSTEM_INFO update  (sinal de metadata change, parametrizada)
   |
   v
COMMIT
   |
   v
Fase 4 — TcRefresh REST      (best-effort, pos-commit)
```

Pseudocodigo da execucao:

```python
target_conn = connect(target, writable=True)
cursor = target_conn.cursor()

executed = 0
try:
    for stmt in phase1_ddl:
        cursor.execute(stmt.sql)
        executed += 1

    for stmt in phase2_dml:
        cursor.execute(stmt.sql)
        executed += 1

    cursor.execute(SYSTEM_INFO_UPDATE_SQL, params)   # parametrizada

    target_conn.commit()

    refresh = call_tcrefresh_rest(target, altered_tables)

    return {
        "success": True,
        "status": "partial" if not refresh.success else "success",
        "executed": executed,
        "tcrefresh": refresh,
    }

except Exception as e:
    target_conn.rollback()
    return {"success": False, "error": str(e), "executed_before_error": executed}

finally:
    target_conn.close()
```

Pontos relevantes:

- **Falha em qualquer statement antes do `COMMIT`** -> `ROLLBACK` total.
  O target volta exatamente ao estado anterior. `executed_before_error`
  indica em qual statement quebrou para diagnostico.
- **Falha pos-`COMMIT`** (Fase 4) -> resultado `partial`. O dicionario foi
  alterado com sucesso, mas o cache do DBAccess pode estar desatualizado.
- **`COMMIT` so dispara depois de todos os DDL+DML+Fase 3 terem sucesso**.

---

## 10. Sinalizacao de mudanca de dicionario (SYSTEM_INFO)

A Fase 3 atualiza um registro especifico em `SYSTEM_INFO` para sinalizar a
mudanca de dicionario aos AppServers que compartilham o mesmo DBAccess:

```sql
UPDATE SYSTEM_INFO
   SET MPI_VALUE = ?,                  -- "YYYYMMDDhh:mm:ss.mmm"  (21 chars)
       MPI_DATE  = ?                   -- "YYYYMMDDHHmmss"        (14 chars)
 WHERE MPI_KEY    = 'METADATA_CHANGE_<empresa>'
   AND D_E_L_E_T_ = ' '
```

Geracao dos valores:

```python
now        = datetime.now()
mpi_date   = now.strftime("%Y%m%d%H%M%S")                                       # 14 chars
mpi_value  = f"{now.strftime('%Y%m%d%H:%M:%S')}.{now.microsecond // 1000:03d}"  # 21 chars
mpi_key    = f"METADATA_CHANGE_{company_code}"
```

A query e executada **parametrizada** (`cursor.execute(sql, (mpi_value, mpi_date, mpi_key))`),
nunca por concatenacao de strings.

Falha nessa fase **nao aborta** a transacao — emite warning e segue para o
`COMMIT`. O `TcRefresh` da Fase 4 ja garante a propagacao mesmo se a
sinalizacao via `SYSTEM_INFO` nao tiver efeito.

---

## 11. Request REST para o AppServer Protheus (TcRefresh)

### 11.1 Por que e necessario

O DBAccess mantem em memoria o layout de cada tabela Protheus. Apos um
`ALTER TABLE`, ele continua usando o layout antigo ate alguem chamar
`TcRefresh()` em ADVPL. Sem isso, qualquer rotina (FWBrowse, MsExecAuto,
include de XCD, etc.) que toque a tabela alterada vai falhar com
"campo nao encontrado" ate o AppServer ser reiniciado.

A solucao e expor uma custom function ADVPL acessivel via REST que recebe
a lista de tabelas e chama `TcRefresh()` para cada uma.

### 11.2 Custom function ADVPL no AppServer

A function vive no RPO Protheus e tem assinatura simplificada:

```advpl
WSRESTFUL ZATUREF DESCRIPTION "Refresh DBAccess"
    WSDATA tables AS ARRAY OF STRING
    WSMETHOD POST DESCRIPTION "Refresh tables"
END WSRESTFUL

WSMETHOD POST WSSERVICE ZATUREF
    Local cTable
    For nI := 1 To Len(self:tables)
        cTable := self:tables[nI]
        TcRefresh(cTable)
    Next
    self:setResponse('{"status":"ok"}')
Return .T.
```

O endpoint precisa estar publicado no `appserver.ini` como WSRESTFUL.

### 11.3 Extracao das tabelas alteradas

Apos o `COMMIT`, as tabelas afetadas sao extraidas dos DDLs da Fase 1 via regex:

```python
import re
altered_tables = set()
for stmt in phase1_stmts:
    sql = stmt["sql"].upper()
    m = re.search(r'(?:ALTER|CREATE)\s+TABLE\s+[\[\"]?(\w+)[\]\"]?', sql)
    if m:
        altered_tables.add(m.group(1))
```

### 11.4 Montagem da requisicao

```python
import urllib.request, urllib.error, json, base64

url     = f"{rest_url.rstrip('/')}/ZATUREF"
payload = json.dumps({"tables": [table]}).encode("utf-8")

headers = {"Content-Type": "application/json"}
if rest_user and rest_pass:
    auth = base64.b64encode(f"{rest_user}:{rest_pass}".encode()).decode()
    headers["Authorization"] = f"Basic {auth}"

req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
with urllib.request.urlopen(req, timeout=15) as resp:
    body = resp.read().decode("utf-8", errors="replace")
```

### 11.5 Politica de retry

Cada tabela e tentada ate **3 vezes**, com **2 segundos** entre tentativas:

```python
MAX_RETRIES   = 3
RETRY_DELAY_S = 2
HTTP_TIMEOUT  = 15

for table in altered_tables:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ...POST...
            break                     # sucesso
        except urllib.error.HTTPError as he:
            last_error = (he.code, he.read().decode("utf-8", "replace"))
        except Exception as e:
            last_error = ("exception", str(e))
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_S)
```

### 11.6 Resposta agregada

```json
{
  "called": true,
  "success": true,
  "url": "http://protheus-appserver:8080/rest",
  "tables": [
    {"table": "SA1990", "status": 200, "response": "{\"status\":\"ok\"}", "attempt": 1}
  ],
  "errors": []
}
```

Se `success=false` apos `COMMIT`, o status do job e marcado como `partial` e
os erros ficam registrados na auditoria para diagnostico.

### 11.7 Comportamento com REST nao configurado

Se a URL REST nao estiver disponivel ou as credenciais nao estiverem definidas,
a Fase 4 retorna `called=false, skipped_reason="..."`. O dicionario ja foi
alterado (commit feito), mas o operador precisa rodar `TcRefresh` manualmente
ou reiniciar o AppServer para o efeito ser aplicado.

---

## 12. Seguranca de execucao

| Camada | Mecanismo |
|---|---|
| **Autorizacao** | Operacao restrita a perfil administrativo |
| **Credenciais de banco** | Senhas armazenadas criptografadas, descriptografadas apenas no momento de abrir a conexao; nunca persistidas em log |
| **Modo de conexao** | Preview usa conexao readonly (PG) ou autocommit OFF (demais drivers); execute exige `writable=True` explicito |
| **Token de confirmacao** | SHA-256 dos statements impede edicao do payload entre preview e execute |
| **Transacao atomica** | `BEGIN` -> Fase 1 -> Fase 2 -> Fase 3 -> `COMMIT`, com `ROLLBACK` em qualquer excecao |
| **Pre-validacao** | Warning bloqueante quando metadado vs fisico divergem nos dois bancos |
| **DDL idempotente** | Verifica se campo/indice ja existe no target antes de gerar `ALTER`/`CREATE` |
| **Quoting de identificadores** | Funcao dedicada por driver; nomes de tabela/coluna nunca vem do payload do cliente — vem das tabelas SX e do `INFORMATION_SCHEMA` |
| **Quoting de valores** | Aspas simples escapadas (`'` -> `''`); `NULL` substituido por `' '` |
| **Query parametrizada** | A unica query sensivel a input externo (`UPDATE SYSTEM_INFO`) usa `cursor.execute(sql, params)` |
| **REST credentials** | Armazenadas em variaveis de ambiente/configuracao, nunca hardcoded; suporte a sufixo por ambiente |
| **Retry controlado** | 3 tentativas, 2s entre elas, timeout 15s — evita travamento se AppServer estiver lento |
| **Auditoria** | Cada execucao persiste usuario, ambiente, conexoes, summary, statements completos, status final |

### Limites conhecidos

- O preview gera SQL com **literais** (nao parametrizados) — intencional para
  permitir copiar-colar os SQLs em ferramentas como SSMS/DBeaver para
  validacao manual antes da execucao. A protecao contra injection vem do
  fato de **nao haver entrada arbitraria do usuario nos valores**: todos
  vem do banco source via `SELECT *`. Aspas e caracteres especiais sao
  escapados pelo helper de quoting.
- A Fase 4 (TcRefresh) e **best-effort** apos o `COMMIT`. Se falhar, o
  dicionario ja esta alterado e e necessario rodar `TcRefresh()` manualmente
  no Protheus ou reiniciar o AppServer.
- Mudanca de tipo (campo divergente com DDL) **nao migra dados**: se o tipo
  novo nao acomodar o conteudo existente (ex.: encurtar `VARCHAR` ou trocar
  `C` -> `N`), o `ALTER COLUMN` falha e o `ROLLBACK` restaura o estado original.
- Indices com expressoes/funcoes sao replicados a partir das colunas indexadas
  reportadas pelo catalogo do banco — formulas complexas que dependam de
  funcoes proprietarias podem requerer ajuste manual.
