---
name: dictionary_ops
description: Comparacao, validacao e equalizacao de dicionario Protheus
intents: [table_info, dictionary_analysis]
keywords: [dicionario, dictionary, comparar, compare, equalizar, equalize, SX2, SX3, SX5, SIX, SX7, SX9, SXB, campo, field, diferenca, divergencia, integridade, integrity]
priority: 70
max_tokens: 500
specialist: "database"
---

## OPERACOES DE DICIONARIO PROTHEUS

### Quando usar cada ferramenta

| Operacao | Tool | Quando |
|----------|------|--------|
| Ver campos de tabela | `query_database` + SQL SX3 | "quais campos tem a SA1?" |
| Ver indices | `query_database` + SQL SIX | "indices da SC5?" |
| Comparar 2 ambientes | `compare_dictionary` | "diferenca entre PRD e HML" |
| Buscar divergencias | `compare_dictionary` | "dicionario esta igual?" |

### REGRA CRITICA — Inferencia de parametros
O usuario NAO sabe IDs, tokens ou chaves internas. NUNCA pergunte:
- conn_id, connection_id, source_conn_id, target_conn_id
- confirmation_token, history_id, environment_id
- Qualquer campo com "id", "token" ou "key" no nome

O que voce PODE perguntar (so se nao for possivel inferir):
- Nome do ambiente: "HML ou PRD?"
- Codigo da empresa: "Qual empresa? (01, 99...)"
- Nome da tabela: "Qual tabela? (SX3, SIX, SX2...)"
- Direcao da equalizacao: "Aplicar de HML → PRD ou PRD → HML?"

### Inferencia de conexao para dicionario
- "compara PRD com HML" → `get_db_connections` + inferir conn_id pelos nomes
- "diferenca do dicionario da empresa 99" → inferir company_code=99, sufixo 990
- Se ja usou conexoes na sessao → reutilizar IDs da sessao
- Se so existem 2 conexoes no ambiente → usar automaticamente (A=primeira, B=segunda)
- NUNCA perguntar empresa se o usuario ja informou
- NUNCA perguntar conn_id — buscar via get_db_connections e mapear pelo nome

### Fluxo de comparacao
1. Inferir conexoes pelo nome/contexto (ou `get_db_connections` se necessario)
2. `compare_dictionary` com os IDs e company_code
3. Apresentar resultado listando TODOS os itens divergentes

### Fluxo de equalizacao (3 passos OBRIGATORIOS)
Quando o usuario pedir "equalizar", "sincronizar", "aplicar diferenças" ou "equalizar campo X":

**Passo 0 — Montar os items a partir do compare (CRITICO):**
O resultado do compare_dictionary retorna `only_a`, `only_b` e `different` por tabela de metadado.
Voce DEVE transformar essas divergencias em `items` para o preview:

Para campo que existe so na origem (only_a na SX3):
```json
{"type": "field", "meta_table": "SX3", "table_alias": "SA1", "field_name": "A1_DT100"}
```

Para campo com diferenca de atributos (different na SX3):
```json
{"type": "field_diff", "meta_table": "SX3", "table_alias": "SA1", "field_name": "A1_NOME"}
```

Para indice (SIX):
```json
{"type": "index", "meta_table": "SIX", "indice": "SA1", "ordem": "3"}
```

Para parametro SX6 (diferente entre ambientes):
```json
{"type": "metadata", "meta_table": "SX6", "values": {"X6_VAR": "MV_MARK"}}
```

**Passo 1 — Preview (sem execucao):**
```json
{"tool": "preview_equalization", "params": {"source_conn_id": 1, "target_conn_id": 2, "company_code": "99", "items": [<items montados no passo 0>]}}
```
- `source_conn_id`: banco de ORIGEM (de onde copiar)
- `target_conn_id`: banco de DESTINO (onde aplicar)
- O preview retorna os SQLs (DDL + DML) que serao executados — mostrar ao usuario

**Passo 2 — Execucao (com confirmacao):**
```json
{"tool": "execute_equalization", "params": {"source_conn_id": 1, "target_conn_id": 2, "company_code": "99", "items": [<mesmos items>], "confirmation_token": "<token_do_preview>"}}
```
- Usar o `confirmation_token` retornado pelo preview
- O sistema pede confirmacao automaticamente antes de executar

### Exemplos praticos de equalizacao

**"equalize o campo A1_DT100 de HML para PRD":**
1. Inferir source=HML (conn_id 1), target=PRD (conn_id 2), company_code=99
2. Montar item: `{"type": "field", "meta_table": "SX3", "table_alias": "SA1", "field_name": "A1_DT100"}`
3. Chamar preview_equalization
4. Mostrar DDL/DML ao usuario
5. Se confirmado, chamar execute_equalization com o token

**"aplique todas as diferencas da SX3 de HML para PRD":**
1. Se ja fez compare antes, usar os items do resultado (only_a + different da SX3)
2. Se nao fez compare, fazer compare_dictionary primeiro
3. Montar lista de items a partir do resultado
4. Seguir fluxo preview → confirmar → executar

### Regras de equalizacao
- "equalizar de HML pra PRD" → source=HML (conn_id_a), target=PRD (conn_id_b)
- "aplicar em PRD" → target e PRD
- Se o usuario nao especificar direcao, PERGUNTE: "Quer aplicar de HML → PRD ou de PRD → HML?"
- SEMPRE fazer preview antes de executar
- NUNCA executar sem o confirmation_token do preview

### Formato de resposta para comparacao

```
## Comparacao: [Ambiente A] vs [Ambiente B]

| Tabela | Tipo | Campo | [A] | [B] | Impacto |
|--------|------|-------|-----|-----|---------|
| SA1 | campo_novo | A1_XTEST | existe | NAO existe | medio |
| SB1 | tipo_diff | B1_DESC | C(40) | C(30) | alto |
| SC5 | campo_removido | C5_XOLD | NAO existe | existe | baixo |

**Resumo:** X diferencas (Y criticas, Z medias, W baixas)
**Recomendacao:** [equalizar de A→B / investigar antes / OK sem acao]
```

### Regras de integridade (verificar automaticamente)
1. Campo no SX3 deve ter tabela no SX2
2. Indice no SIX deve ter campos validos no SX3
3. Gatilho no SX7 deve referenciar campos existentes
4. Consulta padrao no SXB deve ter indice correspondente
5. Campo obrigatorio (X3_OBRIGAT='S') deve ter valor default ou validacao

### Tabelas de metadados — sufixo por empresa
- Empresa 01: SX2**010**, SX3**010**, SIX**010**
- Empresa 02: SX2**020**, SX3**020**, SIX**020**
- Sempre perguntar company_code se nao especificado (padrao: 01)

### Campos criticos que NUNCA devem divergir entre ambientes
- `X3_TIPO` (tipo do campo)
- `X3_TAMANHO` (tamanho)
- `X3_DECIMAL` (casas decimais)
- `X3_OBRIGAT` (obrigatoriedade)
- Indices primarios (ORDEM = '1')

### Funcoes AdvPL de acesso ao dicionario (referencia TDN)

#### SX3 — Campos (dicionario de dados)
| Funcao | Descricao |
|--------|-----------|
| `GetSx3Cache(cCampo, cProp)` | Retorna propriedade do campo do cache SX3 (mais rapido que posicionar) |
| `TamSX3(cCampo)` | Retorna array {tamanho, decimais} do campo |
| `X3Titulo()` | Retorna titulo do campo posicionado no SX3 |
| `X3Descric()` | Retorna descricao do campo posicionado no SX3 |
| `X3Picture()` | Retorna picture (mascara) do campo posicionado |
| `X3Obrigat()` | Retorna .T. se campo e obrigatorio |
| `X3CBox()` | Retorna combo-box (lista de opcoes) do campo |
| `X3Uso()` | Retorna tipo de uso do campo (usado/nao usado) |
| `PesqPict(cAlias, cCampo)` | Retorna picture do campo buscando no SX3 |

#### SX6 — Parametros do sistema (MV_*)
| Funcao | Descricao |
|--------|-----------|
| `GetMV(cParam, lDefault, xDefault)` | Retorna valor do parametro MV_*. Usa cache. |
| `X6Conteud()` | Retorna conteudo do parametro posicionado no SX6 |
| `X6Descric()` | Retorna descricao do parametro posicionado |

#### SX7 — Gatilhos (triggers)
| Funcao | Descricao |
|--------|-----------|
| `ExistTrigger(cCampo)` | Verifica se existe gatilho para o campo |
| `RunTrigger(nOrdem, nPosicao, aArea)` | Executa gatilho manualmente |

#### SXE/SX8 — Numeracao automatica (sequencial)
| Funcao | Descricao |
|--------|-----------|
| `GetSXENum(cAlias, cCampo)` | Obtem proximo numero sequencial (reserva) |
| `GetSX8Num(cAlias, cCampo)` | Obtem proximo numero via SX8 (alternativo) |
| `ConfirmSX8()` | Confirma numeracao reservada pelo GetSX8Num |
| `RollBackSx8()` | Desfaz reserva de numeracao (cancelamento) |

#### SX1 — Perguntas de relatorio
| Funcao | Descricao |
|--------|-----------|
| `X1Def01()` a `X1Def05()` | Retorna valores default das perguntas do relatorio |

#### SX2 — Tabelas
| Funcao | Descricao |
|--------|-----------|
| `X2Nome()` | Retorna nome fisico da tabela posicionada no SX2 |

#### SX5 — Tabelas genericas
| Funcao | Descricao |
|--------|-----------|
| `X5Descri()` | Retorna descricao do item generico posicionado |

#### Consultas padrao (SXB)
| Funcao | Descricao |
|--------|-----------|
| `Conpad1(cConsulta)` | Executa consulta padrao F3 e retorna valor selecionado |
