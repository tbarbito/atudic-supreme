# TcRefresh pós-equalização — Conversa completa de desenvolvimento

> Data: 2026-03-21
> Participantes: Barbito + Claude
> Projeto: AtuDIC (aturpo_demo) — Módulo Equalizador de Dicionário

---

## 1. Problema inicial: entender o APSDU

**Barbito:** Preciso entender o que o APSDU faz no banco ao abrir uma tabela pelo Top Connect, para aplicar a mesma lógica no AtuDIC (módulo equalizador).

**Análise do APSDU** (`/home/barbito/protheus/Lib912/SIGAWIN/APSDU.PRW`):

O fluxo de abertura de tabela no APSDU via Top Connect:

### 1.1 Conexão com o banco (`SducGetTop` - linha 637)
- Lê parâmetros de conexão do `.ini` nas seções `[TopConnect]` e `[TotvsDbAccess]`
- Conecta via `TcLink(cBanco, cServer, nPort)`
- `TCInternal(1, APSDU_BUILD)` — identifica o client para o DBAccess
- `TcInternal(8, __cNome)` — seta o nome do usuário na conexão

### 1.2 Listar tabelas (`SduPesqTab` - linha 786)
- Abre `TOP_FILES` com alias `TRBXXANT`
- Coleta tabelas cujo nome não começa com `TOP_`

### 1.3 Abrir a tabela (`SduOpenFile` - linha 479)
- **`TcRefresh(cFile)`** — força DBAccess a recarregar cache de metadados
- **`DbUseArea(.T., "TOPCONN", cFile, cAlias, lShared, lRead)`**
- Verifica `NetErr()`

### 1.4 Carregar índices (linhas 572-581)
- Loop com `TcCanOpen` + `OrdListAdd`

### 1.5 Posicionar (linhas 591-592)
- `DbSetOrder(0)` + `DbGoTop()`

---

## 2. Análise do CFGX031/APCFG10 — como o Protheus cria campos

**Barbito:** Veja também o CFGX031 e como ele cria um campo novo. A diferença é que o Protheus precisa de modo exclusivo e o AtuDIC é a quente.

**Análise dos fontes APCFG10** (`/home/barbito/protheus/Lib912/SIGACFG/apcfg10*.prw`):

### Fluxo do Configurador
1. **EditSX3** (apcfg10c.prw) — UI de criação de campo, salva em tabela temporária `SX3X31`
2. **X31Update** (apcfg10i.prw) — Wizard de atualização de dicionário
3. **X31UpdTable** (apcfg10i.prw, linhas 1453-1639) — Único lugar que altera estrutura física

### Função crítica: `TcAlter` (linha 1531)
```advpl
If cDriver == "TOPCONN" .and. TCSRVTYPE() <> "AS/400"
    DbSelectArea("TMPX31")
    DbCloseArea()
    If !TcAlter(cArquivo, aArqStru, aSX3Stru)
        X31Message(STR0039+cChave, MSG_ERROR)
        __lError := .T.
    EndIf
```

O `TcAlter` é nativo do DBAccess e faz tudo num pacote:
- ALTER TABLE internamente
- Atualiza TOP_FIELD automaticamente
- Reconstrói cache interno do DBAccess

### Análise do AtuDIC (equalizador existente)

O AtuDIC já fazia corretamente:
- Phase 1: `ALTER TABLE ADD [campo]` (DDL direto no SQL Server)
- Phase 2: `INSERT SX3` + `INSERT TOP_FIELD` (metadados)
- Phase 3: `UPDATE SYSTEM_INFO` (sinalização)

---

## 3. O problema real identificado

**Barbito:** O campo é criado perfeitamente, mas as rotinas do Protheus não realizam UPDATE nele. A rotina visualiza o campo, eu consigo inserir valor, o front grava e diz sucesso, mas o backend não faz o UPDATE. Aí quando abro a tabela pelo APSDU, o campo fica editável.

### Diagnóstico

O **DBAccess mantém cache interno** da `TOP_FIELD` que **não é invalidado** pelo INSERT direto na tabela. O ciclo do problema:

```
AtuDIC faz INSERT INTO TOP_FIELD     → registro existe no banco
AppServer manda gravar               → DBAccess usa CACHE INTERNO de TOP_FIELD
DBAccess NÃO releu a TOP_FIELD       → não sabe que o campo existe
DBAccess ignora o campo no UPDATE    → campo fica vazio
```

### Por que o APSDU resolve
Quando o APSDU abre a tabela (linha 541):
```advpl
TcRefresh(cFile)    // ← ESTA é a mágica
DbUseArea(.T., "TOPCONN", cFile, cAlias, .T., .F.)
```
O `TcRefresh()` força a reconstrução do cache interno do DBAccess.

### Por que o TcAlter funciona no Configurador
O `TcAlter()` faz ALTER TABLE + atualiza TOP_FIELD + reconstrói cache, tudo internamente.

---

## 4. Solução implementada: Phase 4 via REST

### 4.1 Fonte ADVPL — `ZATUREF.PRW`

Endpoint REST compilado no RPO do Protheus. Recebe `{"tables": ["SA1010"]}` e executa:
1. `TcRefresh(cTable)` — descarta cache do DBAccess
2. `DbUseArea(.T., "TOPCONN", cTable, cAlias, .T., .T.)` — força reconstrução
3. `DbCloseArea()` — libera work area

Arquivo: `/home/barbito/protheus/ZATUREF.PRW` (ANSI/Windows-1252, CRLF)

### 4.2 Migration 017 — campo `rest_url`

Adiciona `rest_url TEXT` na tabela `database_connections` para configurar a URL REST do AppServer por conexão.

### 4.3 Backend — rotas de conexão

- SELECT inclui `dc.rest_url`
- INSERT inclui `rest_url`
- UPDATE lista `rest_url` como campo atualizável

### 4.4 Frontend — modal de conexão

Campo "REST URL do AppServer" no modal de conexão de banco de dados, com badge "REST" no card quando preenchido.

### 4.5 Service — `_phase4_tcrefresh`

Executada **após o COMMIT** da equalização:
- Extrai tabelas dos DDLs via regex
- Busca `rest_url` da conexão target
- Chama `POST {rest_url}/ZATUREF` com Basic Auth

---

## 5. Evolução das credenciais REST

### Versão 1: hardcoded
Credenciais `rest`/`Marfrig@rest1` hardcoded no código.

### Versão 2: variáveis de ambiente (.env)
`PROTHEUS_REST_USER` e `PROTHEUS_REST_PASS` no `.env`.

### Versão 3 (final): server_variables do AtuDIC com sufixo de ambiente

Reutiliza as **mesmas variáveis que o runner de pipelines já usa**:

| Ambiente | Usuário | Senha |
|----------|---------|-------|
| Produção | `PROTHEUS_USER_PRD` | `PROTHEUS_PASSWORD_PRD` |
| Homologação | `PROTHEUS_USER_HOM` | `PROTHEUS_PASSWORD_HOM` |
| Desenvolvimento | `PROTHEUS_USER_DEV` | `PROTHEUS_PASSWORD_DEV` |
| Testes | `PROTHEUS_USER_TST` | `PROTHEUS_PASSWORD_TST` |
| Fallback | `PROTHEUS_USER` | `PROTHEUS_PASSWORD` |

Mapa de sufixos (mesmo do `runner.py` linhas 691-696):
```python
_ENV_SUFFIX_MAP = {
    "Produção": "PRD",
    "Homologação": "HOM",
    "Desenvolvimento": "DEV",
    "Testes": "TST",
}
```

Nenhuma variável nova precisa ser criada.

---

## 6. Controle transacional — Phase 4 fora do rollback

**Barbito:** O equalizador tem controle de transação. A integração via API entra nesse controle? Tem que ter status 200 para dar commit?

**Resposta:** Não. A Phase 4 executa **após o COMMIT**, por design:

| Fase | Dentro da transação? | Se falhar... |
|------|---------------------|--------------|
| Phase 1 (DDL) | Sim | ROLLBACK tudo |
| Phase 2 (DML) | Sim | ROLLBACK tudo |
| Phase 3 (SYSTEM_INFO) | Sim (try interno) | Warning, não bloqueia |
| **COMMIT** | — | — |
| Phase 4 (REST/TcRefresh) | **Não** | Reporta no response |

**Justificativa:** O TcRefresh é uma operação de **ativação**, não de **criação**. Se o ALTER TABLE + SX3 + TOP_FIELD deram certo e foram commitados, não faz sentido desfazer isso porque o AppServer não respondeu o REST. O campo foi criado corretamente — o refresh é um bônus para ativação imediata. Se falhar, resolve abrindo pelo APSDU (comportamento anterior).

---

## 7. Fluxo completo final

```
Equalização no AtuDIC:
  Phase 1 (DDL):     ALTER TABLE ADD [campo]          ← SQL direto no banco
  Phase 2 (DML):     INSERT SX3 + INSERT TOP_FIELD    ← metadados Protheus
  Phase 3 (Signal):  UPDATE SYSTEM_INFO                ← AppServer recarrega SX3
  ─── COMMIT ───
  Phase 4 (Refresh): POST /rest/ZATUREF                ← DBAccess reconhece o campo
                     → Auth: Basic (PROTHEUS_USER_PRD:PROTHEUS_PASSWORD_PRD)
                     → TcRefresh(tabela)
                     → DbUseArea + DbCloseArea

Resultado: campo funciona imediatamente nas rotinas do Protheus
```

---

## 8. Commits realizados

| Commit | Descrição |
|--------|-----------|
| `bc4a139` | feat(equalizador): TcRefresh via REST após equalização — migration 017, rotas, service, frontend |
| `e1c3f23` | fix(equalizador): adicionar Basic Auth na chamada REST |
| `0fb3556` | refactor(equalizador): credenciais REST via variáveis de ambiente |
| `af68542` | refactor(equalizador): credenciais via server_variables com sufixo do ambiente |
| `e336fdc` | refactor(equalizador): usar PROTHEUS_USER/PASSWORD das server_variables existentes |

---

## 9. Arquivos criados/modificados

### Criados
- `/home/barbito/aturpo_demo/app/database/migrations/017_rest_url.py`
- `/home/barbito/protheus/ZATUREF.PRW` (ADVPL, ANSI/CRLF)
- `/home/barbito/protheus/PROMPT_TCREFRESH_ATURPO.md` (prompt para replicar no AtuDIC)

### Modificados
- `/home/barbito/aturpo_demo/app/routes/database.py` — SELECT, INSERT, UPDATE com rest_url
- `/home/barbito/aturpo_demo/app/services/dictionary_equalizer.py` — Phase 4 + credenciais
- `/home/barbito/aturpo_demo/static/js/integration-database.js` — campo REST URL no modal

---

## 10. Referências nos fontes Protheus

| Arquivo | Linhas | O que faz |
|---------|--------|-----------|
| `APSDU.PRW` | 541 | `TcRefresh(cFile)` antes de abrir tabela |
| `APSDU.PRW` | 548 | `DbUseArea(.T., "TOPCONN", ...)` |
| `APSDU.PRW` | 572-581 | Loop de `TcCanOpen` + `OrdListAdd` para índices |
| `APSDU.PRW` | 637-729 | `SducGetTop` — conexão com diálogo Server/Banco/Porta |
| `APSDU.PRW` | 786-815 | `SduPesqTab` — lista tabelas via `TOP_FILES` |
| `apcfg10i.prw` | 1528-1531 | `TcAlter(cArquivo, aArqStru, aSX3Stru)` |
| `apcfg10i.prw` | 1453-1639 | `X31UpdTable` — único lugar que modifica estrutura física |
| `apcfg10i.prw` | 1772-1827 | `X31CompStru` — compara SX3 vs estrutura física |
| `ApUpd030.prw` | 7321-7337 | `TcAlter` no updater de RPO |
