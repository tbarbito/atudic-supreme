---
name: sql_protheus
description: Templates SQL para consultas em tabelas Protheus com regras por driver
intents: [table_info, knowledge_search, general]
keywords: [sql, query, select, tabela, campo, SX2, SX3, SX5, SIX, SA1, SA2, SB1, SC5, SC6, SD1, SD2, SE1, SE2, SF1, SF2, dicionario, metadado, indice, index, clientes, fornecedores, produtos, pedidos, titulos, notas, banco, consulta, parametro, MV_]
priority: 80
max_tokens: 800
specialist: "database"
---

## REGRAS SQL PARA PROTHEUS

### Drivers e sintaxe
| Driver | TOP/LIMIT | String concat | NOLOCK | Schema |
|--------|-----------|---------------|--------|--------|
| SQL Server | `SELECT TOP N` | `+` | `WITH (NOLOCK)` | `dbo.` |
| Oracle | `WHERE ROWNUM <= N` ou `FETCH FIRST N ROWS ONLY` | `\|\|` | nao tem | owner.table |
| PostgreSQL | `LIMIT N` | `\|\|` | nao tem | public. |

### Filtro obrigatorio
SEMPRE incluir `D_E_L_E_T_ = ' '` (espaco, nao vazio) para excluir registros deletados logicamente.

### R_E_C_N_O_ e R_E_C_D_E_L_
- `R_E_C_N_O_`: chave fisica. Em SQL Server e auto-identity. Em Oracle/PG pode ser sequence.
- `R_E_C_D_E_L_`: controle de exclusao logica. `0` = ativo.

### Sufixo de empresa (REGRA OBRIGATORIA — APLICAR EM TODA QUERY)
Nome fisico = `{PREFIXO}{M0_CODIGO}0` onde M0_CODIGO vem da SYS_COMPANY.
Exemplos: empresa 99 → SA1**990**, SX3**990**, SIX**990**, SX6**990**. Empresa 01 → SA1**010**, SX3**010**, SX6**010**.
NUNCA assuma sufixo — descubra o M0_CODIGO PRIMEIRO com:
```sql
SELECT M0_CODIGO, M0_NOME FROM SYS_COMPANY ORDER BY M0_CODIGO
```
Se o operador disse "banco HML" ou "conexao 1", use a conexao para rodar essa query ANTES de qualquer outra.
Depois aplique o M0_CODIGO em TODAS as tabelas: `FROM SX6{M0_CODIGO}0`, `FROM SA1{M0_CODIGO}0`, etc.
Excecao: TOP_FIELD e SYS_COMPANY NAO tem sufixo (tabelas unicas por banco).
**Multi-empresa:** Se SYS_COMPANY retornar mais de 1 empresa, PERGUNTE ao operador qual usar (ex: "Encontrei empresas 01 e 99. Qual?"). Se so tem 1, use direto. Se o operador ja mencionou a empresa ou ja usou uma na sessao, reutilize.

### Templates de consulta frequentes
Nos exemplos abaixo, `{suf}` = sufixo da empresa (ex: 990, 010).

**Estrutura de tabela (SX2 + SX3):**
```sql
-- Campos de uma tabela (ex: SA1 = Clientes)
SELECT X3_CAMPO, X3_TITULO, X3_DESCRIC, X3_TIPO, X3_TAMANHO, X3_DECIMAL,
       X3_OBRIGAT, X3_VISUAL, X3_CONTEXT, X3_CBOX
FROM {schema}SX3{suf}
WHERE X3_ARQUIVO = 'SA1'
  AND D_E_L_E_T_ = ' '
ORDER BY X3_ORDEM
```

**Indices (SIX):**
```sql
SELECT INDICE, ORDEM, CHAVE, DESCRICAO, SHOWPESQ
FROM {schema}SIX{suf}
WHERE INDICE = 'SA1'
  AND D_E_L_E_T_ = ' '
ORDER BY INDICE, ORDEM
```

**Validacoes e gatilhos (SX7):**
```sql
SELECT X7_CAMPO, X7_SEQUENC, X7_REGRA, X7_CDOMIN, X7_TIPO
FROM {schema}SX7{suf}
WHERE X7_CAMPO LIKE 'A1_%'
  AND D_E_L_E_T_ = ' '
```

**Consulta padrao com filial:**
```sql
SELECT A1_COD, A1_LOJA, A1_NOME, A1_CGC, A1_EST, A1_MUN
FROM {schema}SA1{suf}
WHERE A1_FILIAL = '{filial}'
  AND D_E_L_E_T_ = ' '
ORDER BY A1_COD, A1_LOJA
```

### Tabelas SX (metadados) — referencia rapida
| Tabela | Conteudo |
|--------|----------|
| SX1 | Perguntas (parametros de relatorios) |
| SX2 | Tabelas (cadastro de arquivos) |
| SX3 | Campos (dicionario de dados) |
| SX5 | Tabelas genericas (dominios) |
| SX6 | Parametros do sistema (MV_*) |
| SX7 | Gatilhos (triggers de campo) |
| SX9 | Relacionamentos entre tabelas |
| SXB | Consultas padrao (F3) |
| SIX | Indices |

### Template: Descobrir empresas do banco

```sql
SELECT M0_CODIGO, M0_NOME, M0_FILIAL FROM SYS_COMPANY WITH (NOLOCK) WHERE D_E_L_E_T_ = ' '
```

### Template: Consultar parametro SX6

```sql
SELECT X6_VAR, X6_CONTEUD, X6_DESCRIC, X6_FILIAL
FROM dbo.SX6{M0_CODIGO}0 WITH (NOLOCK)
WHERE X6_VAR = '{PARAMETRO}' AND D_E_L_E_T_ = ' '
```

### Regra de inferencia de conexao (CRITICO)

1. Se o usuario menciona o nome da conexao na mensagem (ex: "protheus homolog", "linux", "PRD"):
   **INFERIR o connection_id pelo nome, sem perguntar**
2. Se ja usou uma conexao na sessao (historico): **REUTILIZAR a mesma, sem perguntar**
3. Se o ambiente tem 1 unica conexao: usar automaticamente, sem perguntar
4. So perguntar qual conexao usar se ha ambiguidade REAL e nenhum contexto no historico
5. NUNCA chutar connection_id — usar o ID real da tabela `database_connections`
6. Se o usuario pede "cade?" ou "traga X" apos uma query, reutilize a MESMA conexao

### Tabelas de negocio por modulo — referencia rapida

#### SIGAFAT — Faturamento / Vendas
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| SA1 | Clientes | A1_COD, A1_LOJA, A1_NOME, A1_CGC |
| SC5 | Pedidos de Venda (cabecalho) | C5_NUM, C5_CLIENTE, C5_LOJA, C5_EMISSAO |
| SC6 | Itens do Pedido de Venda | C6_NUM, C6_ITEM, C6_PRODUTO, C6_QTDVEN, C6_PRCVEN |
| SC9 | Liberacoes de Pedido | C9_PEDIDO, C9_ITEM, C9_PRODUTO |
| SF2 | Cabecalho NF Saida | F2_DOC, F2_SERIE, F2_CLIENTE, F2_LOJA |
| SD2 | Itens NF Saida | D2_DOC, D2_SERIE, D2_COD, D2_QUANT, D2_TOTAL |
| SF4 | TES (Tipo Entrada/Saida) | F4_CODIGO, F4_TEXTO, F4_CF |

#### SIGACOM — Compras
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| SA2 | Fornecedores | A2_COD, A2_LOJA, A2_NOME, A2_CGC |
| SC1 | Solicitacoes de Compra | C1_NUM, C1_ITEM, C1_PRODUTO |
| SC7 | Pedidos de Compra | C7_NUM, C7_ITEM, C7_PRODUTO, C7_QUANT, C7_PRECO |
| SF1 | Cabecalho NF Entrada | F1_DOC, F1_SERIE, F1_FORNECE, F1_LOJA |
| SD1 | Itens NF Entrada | D1_DOC, D1_SERIE, D1_COD, D1_QUANT, D1_TOTAL |

#### SIGAFIN — Financeiro
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| SE1 | Contas a Receber | E1_NUM, E1_PREFIXO, E1_PARCELA, E1_CLIENTE, E1_VALOR |
| SE2 | Contas a Pagar | E2_NUM, E2_PREFIXO, E2_PARCELA, E2_FORNECE, E2_VALOR |
| SE5 | Movimentacao Bancaria | E5_DATA, E5_VALOR, E5_BANCO |
| SA6 | Bancos | A6_COD, A6_AGENCIA, A6_NUMCON |
| FK2 | Extrato Bancario | FK2_DATA, FK2_VALOR, FK2_BANCO |

#### SIGAEST — Estoque
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| SB1 | Produtos | B1_COD, B1_DESC, B1_TIPO, B1_UM, B1_GRUPO |
| SB2 | Saldos em Estoque | B2_COD, B2_LOCAL, B2_QATU, B2_RESERVA |
| SB5 | Dados Complementares Produto | B5_COD, B5_CEME |
| SD3 | Movimentacoes Internas | D3_DOC, D3_COD, D3_QUANT, D3_TM |

#### SIGAFIS — Fiscal
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| SF3 | Livros Fiscais | F3_DOC, F3_SERIE, F3_CFO, F3_VALICM |
| CDO | SPED/EFD Contribuicoes | CDO_CODIGO, CDO_DESCRI |
| CDA | Apuracao ICMS | CDA_PERANT, CDA_VALOR |

#### SIGAMNT — Manutencao de Ativos
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| ST9 | Equipamentos | T9_CODBEM, T9_NOME, T9_SITUA |
| TJ1 | Ordens de Servico | TJ1_NUMOS, TJ1_CODBEM, TJ1_TIPO |
| SN1 | Ativo Fixo | N1_CBASE, N1_DESCRIC, N1_GRUPO |

#### Contabilidade
| Alias | Descricao | Campos-chave |
|-------|-----------|-------------|
| CT1 | Plano de Contas | CT1_CONTA, CT1_DESC01 |
| CT2 | Lancamentos Contabeis | CT2_DATA, CT2_DEBITO, CT2_CREDIT, CT2_VALOR |

### Ao gerar SQL

1. Infira o driver a partir das conexoes do ambiente (ou use get_db_connections pra descobrir)
2. Use tool `query_database` com connection_id correto (ID real da tabela database_connections)
3. **ANTES de qualquer query em tabela Protheus:** descubra M0_CODIGO via `SELECT M0_CODIGO, M0_NOME FROM SYS_COMPANY`
4. Aplique o sufixo {M0_CODIGO}0 em TODA tabela: `FROM SX6{M0_CODIGO}0`, `FROM SA1{M0_CODIGO}0`
5. Limite a 100 linhas por padrao (max_rows)
6. Para contagem, use `COUNT(*)` em vez de trazer todos os registros
7. NUNCA gere UPDATE, DELETE, INSERT — apenas SELECT
8. Excecoes SEM sufixo: SYS_COMPANY, TOP_FIELD
