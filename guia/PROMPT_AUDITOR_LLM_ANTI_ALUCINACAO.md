# Prompt de Implementacao — Auditor INI: LLM Anti-Alucinacao + Ficha Tecnica

> **Projeto:** AtuDIC (aturpo_demo)
> **Arquivo alvo:** `app/services/ini_auditor.py`
> **Commits de referencia:** 36b0f0a..26bb128
> **Data:** 2026-03-22
> **Autor:** Barbito + Claude Opus 4.6

---

## Problema

O LLM (Gemini, Claude, etc.) ao gerar o resumo executivo da auditoria de INI estava:

1. **Inventando dados** — citava servidores, IPs e conexoes que NAO existiam no arquivo (ex: "Slave de Broker REST conectado ao Master SPDWVPTH002F" em um INI que conecta a `localhost`)
2. **Ignorando o formato resumo executivo** — fazia analise item-por-item detalhada ("O que esta errado / Por que importa / Como corrigir") que ja e mostrada nos findings da auditoria automatica
3. **Verbosidade excessiva** — respostas de 500+ palavras em vez do maximo de 200

**Causa raiz:** O LLM recebia apenas a lista de problemas, sem dados concretos do arquivo. Sem ancoragem em fatos reais, o modelo preenchia lacunas com alucinacoes.

---

## Solucao: Ficha Tecnica + Prompt Anti-Alucinacao

### Principio: Ancoragem em dados reais

O LLM so pode citar o que esta na **ficha tecnica** — um bloco de dados extraidos automaticamente do INI parseado, incluindo secoes, servidores, portas e bancos REAIS.

---

## 1. Ficha Tecnica no User Prompt (`_build_user_prompt`)

### Antes (sem contexto do arquivo)

```
Arquivo: appserver.ini
Role detectado: WS REST Slave (ws_rest_slave)
Total de problemas: 4

[CRITICAL] [General] MaxStringSize: AUSENTE (recomendado: 10)
...
```

### Depois (com ficha tecnica)

```
## Ficha Tecnica do Arquivo
- **Arquivo:** appserver_teste.ini
- **Tipo detectado:** appserver
- **Papel na infraestrutura:** WS REST Slave (`ws_rest_slave`)
- **Evidencias:** Secoes: [httpjob], [httprest], [httpuri], [httpv11]
- **Secoes encontradas (15):** [protheus], [protheus_cmp], [protheus_rest], [General], [dbaccess], [Drivers], [TCP], [Service], [LICENSECLIENT], [WEBAPP], [HTTPV11], [HTTPREST], [HTTPURI], [HTTPJOB], [WebApp/webapp]
- **Servidor (dbaccess):** localhost
- **Porta (dbaccess):** 7890
- **Banco (dbaccess):** Postgres
- **Porta (TCP):** 1234
- **Porta (HTTPREST):** 8019

## Problemas Encontrados (4)
[CRITICAL] [General] MaxStringSize: AUSENTE (recomendado: 10)
...
```

### Implementacao

A funcao `_build_user_prompt()` recebe dois novos parametros: `parsed` (dict parseado do INI) e `filename` (nome do arquivo).

```python
def _build_user_prompt(findings, commented_findings, ini_type, all_practices,
                       ini_role=None, role_label=None, role_evidence=None,
                       parsed=None, filename=None):
```

**Dados extraidos automaticamente para a ficha tecnica:**

| Campo | Fonte | Chaves detectadas |
|-------|-------|-------------------|
| Arquivo | `filename` parametro | - |
| Tipo | `ini_type` | - |
| Papel | `ini_role` + `role_label` | - |
| Evidencias | `role_evidence` | - |
| Secoes | `parsed["sections"].keys()` | - |
| Servidores | `sections[*]` | `server`, `dbserver`, `masterserver` |
| Portas | `sections[*]` | `port`, `dbport`, `masterport` |
| Bancos | `sections[*]` | `database` |

Isso garante que o LLM so tem acesso a dados que EXISTEM no arquivo.

---

## 2. System Prompt Anti-Alucinacao (`_build_specialist_prompt`)

### Formato obrigatorio reescrito

```
## Formato da resposta — RESUMO EXECUTIVO (OBRIGATORIO):
Responda APENAS neste formato. NAO faca analise item-por-item. NAO invente dados.

### Titulo (1 linha)
Descreva o papel do servidor usando APENAS dados do arquivo (secoes, servidores, portas
que EXISTEM no INI). NUNCA invente nomes de servidores ou conexoes.

### Estado geral (1-2 frases)
Avaliacao concisa da saude do arquivo para o papel detectado.

### Pontos de atencao (maximo 5 bullets)
APENAS itens que REALMENTE impactam este papel. Se a auditoria automatica reportou
algo que nao faz sentido para o papel, IGNORE ou critique como falso positivo.

### Dicas (opcional, maximo 3 bullets)
Sugestoes praticas e rapidas. NAO sugira adicionar secoes/chaves irrelevantes.

REGRAS ABSOLUTAS:
- Maximo 200 palavras no total
- NAO repita "O que esta errado / Por que importa / Como corrigir" — os findings ja mostram isso
- NAO invente nomes de servidores, IPs ou paths que nao estejam no arquivo
- Use APENAS dados da ficha tecnica fornecida abaixo
- Portugues brasileiro, markdown
```

### O que mudou vs anterior

| Aspecto | Antes | Depois |
|---------|-------|--------|
| Titulo | Exemplo induzia alucinacao ("Master SPDWVPTH002F") | "Use APENAS dados do arquivo" |
| Formato | "1. Avaliacao geral... 2. Problemas CRITICOS..." (vago) | Secoes nomeadas obrigatorias (Titulo/Estado/Pontos/Dicas) |
| Analise detalhada | "Para cada: o que esta errado -> por que importa -> como corrigir" | "NAO repita — os findings ja mostram isso" |
| Ancoragem | Nenhuma referencia a dados reais | "Use APENAS dados da ficha tecnica fornecida" |
| Anti-invencao | Nao mencionado | "NAO invente nomes de servidores, IPs ou paths" |
| Limite | "maximo ~200 palavras" (sugestao) | "Maximo 200 palavras" em REGRAS ABSOLUTAS |

---

## 3. Propagacao dos Parametros

A cadeia de chamadas foi atualizada para propagar `parsed` e `filename`:

```
run_audit(content, filename, ...)
    ↓
generate_llm_insights(..., parsed=parsed, filename=filename)
    ↓
_build_user_prompt(..., parsed=parsed, filename=filename)
    → Gera ficha tecnica com dados reais
    → LLM recebe contexto ancorado
```

### `generate_llm_insights()` — novos parametros

```python
def generate_llm_insights(findings, commented_findings, ini_type, environment_id, conn=None,
                          ini_role=None, role_label=None, role_evidence=None,
                          parsed=None, filename=None):
```

### `run_audit()` — chamada atualizada

```python
llm_result = generate_llm_insights(
    comparison["findings"],
    comparison["commented_findings"],
    ini_type,
    environment_id,
    conn=conn,
    ini_role=ini_role,
    role_label=role_label,
    role_evidence=role_info.get("evidence", []),
    parsed=parsed,        # NOVO
    filename=filename,    # NOVO
)
```

---

## 4. Resultado Esperado

### Exemplo: appserver_teste.ini (WS REST Slave conectando a localhost)

**Antes (alucinacao):**
> Slave de Broker REST conectado ao Master SPDWVPTH002F
>
> O arquivo appserver.ini apresenta muitos pontos de atencao...
>
> Problemas Criticos:
> * [CRITICAL] [protheus_cmp] SourcePath: AUSENTE
> * O que esta errado: A chave SourcePath na secao [protheus_cmp] esta ausente.
> * Por que importa: Esta chave e fundamental para que o Application Server...
> * Como corrigir: Defina a chave SourcePath na secao...
>
> (500+ palavras, item por item)

**Depois (ancorado):**
> **AppServer REST com 3 environments conectando a Postgres via localhost:7890**
>
> Arquivo funcional com 15 secoes. Configuracao REST ativa na porta 8019.
> MaxStringSize ausente em [General] e o ponto critico.
>
> **Pontos de atencao:**
> - MaxStringSize ausente — adicionar `MaxStringSize=10` em [General]
> - [protheus_cmp] tem `SSourcePath` (possivel typo, deveria ser `SourcePath`)
> - Encoding UTF-8 detectado — Protheus espera ANSI (CP1252)
>
> **Dicas:**
> - Considerar habilitar `LogTimeStamp=1` para correlacao de eventos
>
> (~80 palavras)

---

## 5. Validacao

1. Upload de INI com `Server=localhost` → LLM deve citar "localhost", nunca inventar outro servidor
2. Upload de INI sem [Broker] → LLM NAO deve mencionar broker
3. Upload de broker → LLM NAO deve sugerir [Environment] ou MaxStringSize
4. Resposta do LLM deve ter no maximo ~200 palavras
5. Resposta do LLM NAO deve conter "O que esta errado / Por que importa / Como corrigir"
6. Resposta deve seguir formato: Titulo → Estado → Pontos → Dicas

---

## 6. Licoes Aprendidas

| Licao | Detalhe |
|-------|---------|
| **LLM preenche lacunas** | Sem dados concretos, o modelo inventa. Sempre fornecer ficha tecnica. |
| **Exemplos no prompt induzem** | O exemplo "Master SPDWVPTH002F" fez o LLM repetir o padrao com outros nomes. Remover exemplos que contem dados ficticios. |
| **"NAO faca X" e fraco** | Dizer apenas "nao faca analise detalhada" nao e suficiente. Fornecer formato estruturado obrigatorio (secoes nomeadas) forca o LLM a seguir. |
| **Repetir instrucoes em blocos diferentes** | A regra "maximo 200 palavras" aparece tanto no formato quanto nas REGRAS ABSOLUTAS. Redundancia intencional para reforco. |
| **Dados > instrucoes** | Fornecer dados reais (ficha tecnica) e mais eficaz que instruir "nao invente". O modelo se ancora naturalmente no que recebe. |
