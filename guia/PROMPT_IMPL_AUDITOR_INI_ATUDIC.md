# PROMPT DE IMPLEMENTAÇÃO — Módulo Auditor de INI Protheus

> **Para:** Projeto ATURPO_2 (produção)
> **Origem:** Prototipado e validado no AtuDIC (aturpo_demo)
> **Versão:** 2.0 (atualizado após validação completa)
> **Data de referência:** 2026-03-21

---

## Objetivo

Implementar o módulo **Auditor de INI Protheus** no ATURPO_2. O módulo permite que administradores façam upload de arquivos `.ini` de servidores TOTVS Protheus e recebam uma análise automatizada com:

- **Score de conformidade** (0-100) ponderado por severidade
- **Análise contextual** — só avalia seções presentes no arquivo
- **Detecção de environments dinâmicos** — `[P12_PRODUCAO]` em vez de `[Environment]`
- **Validação de encoding** — ANSI (CP1252) obrigatório para Protheus
- **Detecção de sujeira** — linhas malformadas, chaves inválidas, valores vazios
- **Chaves comentadas** — detecta `;key=value` com explicação do impacto
- **Seções comentadas** — detecta `;[NomeSecao]` inteiras desabilitadas
- **INI sugerido** — gera arquivo corrigido em ANSI, pronto para usar
- **LLM especialista** — insights humanizados com contexto rico da TDN
- **207 regras** cobrindo appserver.ini, dbaccess.ini, Broker e 20+ seções
- **Histórico** com cache de resultados no PostgreSQL

---

## Contexto Técnico

O módulo foi prototipado no `aturpo_demo` e está funcional e validado. Esta implementação deve seguir as convenções e padrões **específicos do ATURPO_2**, que podem diferir do demo em estrutura de pastas, auth, frontend e migrations.

**Use este prompt como especificação funcional e técnica. Adapte a implementação aos padrões do ATURPO_2.**

---

## Especificação Funcional

### 1. Upload e Análise

```
COMO administrador do Protheus
QUERO fazer upload de um arquivo .ini (appserver, dbaccess, smartclient)
PARA receber análise automática de conformidade com boas práticas
```

**Critérios de aceite:**
- Upload via drag-and-drop ou seletor de arquivo
- Aceitar apenas `.ini`, limite 1MB
- Detecção automática do tipo de INI (appserver/dbaccess/smartclient/custom)
- Resultado instantâneo com score, findings e resumo

### 2. Validação de Encoding

```
COMO sistema
QUERO verificar se o encoding do arquivo é ANSI (CP1252)
PARA alertar o usuário se o arquivo é incompatível com Protheus
```

**Critérios de aceite:**
- Detectar: UTF-8 BOM, UTF-8 sem BOM, UTF-16 LE/BE, CP1252, ASCII puro
- Badge verde "Compatível" ou vermelho "INCOMPATÍVEL" com explicação
- Alertar sobre BOM (3 bytes EF BB BF que o Protheus não suporta)
- INI sugerido gerado sempre em ANSI (CP1252)

### 3. Detecção de Sujeira

```
COMO sistema
QUERO identificar linhas malformadas no arquivo INI
PARA alertar sobre problemas que podem causar erro no Protheus
```

**Critérios de aceite:**
- Linhas fora de qualquer seção (sem `[seção]` antes)
- Chaves com nomes inválidos (caracteres especiais)
- Chaves com valor vazio (`Key=`)
- Linhas sem formato `chave=valor` (nem comentário)
- Mostrar número da linha + conteúdo + motivo

### 4. Motor de Comparação Contextual

```
COMO sistema
QUERO comparar APENAS seções presentes no arquivo contra regras do PG
PARA evitar falsos positivos de chaves irrelevantes
```

**Critérios de aceite:**
- Só avaliar regras para seções que EXISTEM no arquivo (exceto obrigatórias)
- Comparação case-insensitive em seções e chaves
- 5 tipos de avaliação: string, integer, boolean, range, enum
- Score ponderado: critical=3.0, warning=1.5, info=0.5
- Status por chave: ok | mismatch | missing

### 5. Detecção de Environments Dinâmicos

```
COMO sistema
QUERO detectar seções de Environment pelo conteúdo, não pelo nome
PARA avaliar environments customizados como [P12_PRODUCAO], [SIGAMDI]
```

**Critérios de aceite:**
- Detectar pela presença de chaves indicadoras: `RootPath`, `SourcePath`, `StartPath`, `RpoDb`, `RpoVersion`, `RpoLanguage`
- Aplicar regras de `[Environment]` em CADA environment detectado
- Mostrar o nome real da seção nos findings (ex: `[P12_PRODUCAO]`)
- Suportar múltiplos environments no mesmo arquivo

**Implementação:**
```python
env_indicator_keys = {"rootpath", "sourcepath", "startpath", "rpodb", "rpoversion", "rpolanguage"}
for sec_name, sec_keys in sections.items():
    sec_keys_lower = {k.lower() for k in sec_keys}
    if sec_keys_lower & env_indicator_keys:  # Interseção
        detected_environments.append(sec_name)
```

### 6. Chaves e Seções Comentadas

```
COMO administrador
QUERO ser alertado sobre configurações comentadas
PARA saber se algo foi desabilitado intencionalmente ou por erro
```

**Critérios de aceite:**
- Detectar chaves comentadas: `;MaxStringSize=4` ou `#ConsoleLog=0`
- Detectar seções inteiras comentadas: `;[General]`
- Gerar explicação do impacto (obrigatória comentada = crítico)
- Mostrar em card separado com coluna "Por quê?"

### 7. INI Sugerido

```
COMO administrador
QUERO baixar uma versão corrigida do meu INI
PARA aplicar as correções recomendadas no servidor
```

**Critérios de aceite:**
- Baseado no arquivo original (mantém estrutura)
- Marcações: `; [CORRIGIDO] era: key=old` → `key=new`
- Marcações: `; [DESCOMENTADO] era: ;key=val` → `key=recommended`
- Marcações: `; [ADICIONADO] recomendação` → `key=val`
- Download em encoding **ANSI (CP1252)** — pronto para Protheus
- Header com metadados: tipo do INI, data da geração

### 8. LLM Especialista

```
COMO administrador
QUERO um resumo humanizado dos problemas com linguagem de especialista
PARA entender rapidamente o impacto e como corrigir
```

**Critérios de aceite:**
- LLM é OPCIONAL — análise funciona 100% sem ele
- System prompt de especialista sênior Protheus (15+ anos)
- Contexto específico por tipo de INI (appserver vs dbaccess)
- User prompt enriquecido com: descrições das regras do PG + URLs TDN
- Instrução: críticos primeiro → impacto real → como corrigir
- Resposta em português, markdown, direto e prático
- Temperatura baixa (0.3) para consistência
- Modelo recomendado: `gemini-2.5-flash-lite` (custo: ~R$0,003/análise, tem tier free)

### 9. Frontend — Resultado com Cards Colapsáveis

```
COMO administrador
QUERO uma interface limpa e organizada nos resultados
PARA navegar facilmente entre os diferentes aspectos da análise
```

**Critérios de aceite — Todos os cards com:**
- Collapse (colapsável com chevron ▼)
- Scroll interno (max-height para não crescer demais)
- Badge com contagem

**Ordem dos cards na tela de resultados:**
1. **Score Header** — score, filename, tipo, contadores, botões (Baixar INI, CSV, expandir/colapsar)
2. **Encoding** — badge compatível/incompatível (colapsado, expande se erro)
3. **Sujeira** — linhas malformadas (colapsado)
4. **Seções Comentadas** — `;[NomeSecao]` (colapsado)
5. **INI Sugerido** — preview dark mode + download ANSI (colapsado)
6. **Análise IA** — resumo LLM (expandido, scroll 400px)
7. **Chaves Comentadas** — `;key=value` com "Por quê?" (colapsado, scroll 300px)
8. **Análise Detalhada** — findings por seção (expandido, scroll 600px)
   - Cada seção é um sub-card colapsável
   - Expande automaticamente apenas seções com problemas
   - Thead sticky nas tabelas

---

## Especificação Técnica

### Schema do Banco (PostgreSQL)

```sql
-- Tabela 1: Histórico de auditorias
CREATE TABLE IF NOT EXISTS ini_audits (
    id SERIAL PRIMARY KEY,
    environment_id INTEGER,
    user_id INTEGER,
    filename VARCHAR(255) NOT NULL,
    ini_type VARCHAR(50) NOT NULL,
    raw_content TEXT NOT NULL,
    parsed_json TEXT,
    total_sections INTEGER DEFAULT 0,
    total_keys INTEGER DEFAULT 0,
    score NUMERIC(5,2),
    llm_summary TEXT,
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela 2: Regras de boas práticas
CREATE TABLE IF NOT EXISTS ini_best_practices (
    id SERIAL PRIMARY KEY,
    ini_type VARCHAR(50) NOT NULL,
    section VARCHAR(100) NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    recommended_value TEXT,
    value_type VARCHAR(20) DEFAULT 'string',
    min_value TEXT,
    max_value TEXT,
    enum_values TEXT,
    severity VARCHAR(20) DEFAULT 'info',
    description TEXT,
    tdn_url TEXT,
    is_required BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ini_type, section, key_name)
);

-- Tabela 3: Resultados por chave
CREATE TABLE IF NOT EXISTS ini_audit_results (
    id SERIAL PRIMARY KEY,
    audit_id INTEGER NOT NULL REFERENCES ini_audits(id) ON DELETE CASCADE,
    best_practice_id INTEGER REFERENCES ini_best_practices(id),
    section VARCHAR(100) NOT NULL,
    key_name VARCHAR(100) NOT NULL,
    current_value TEXT,
    recommended_value TEXT,
    severity VARCHAR(20) DEFAULT 'info',
    status VARCHAR(20) DEFAULT 'mismatch',
    llm_insight TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### API REST

| Método | Endpoint | Auth | Descrição |
|--------|----------|------|-----------|
| `POST` | `/api/auditor/upload` | user | Upload + análise (multipart ou JSON) |
| `GET` | `/api/auditor/history` | user | Histórico paginado |
| `GET` | `/api/auditor/audit/:id` | user | Detalhe completo |
| `DELETE` | `/api/auditor/audit/:id` | admin | Remove auditoria |
| `GET` | `/api/auditor/best-practices` | user | Lista regras |
| `POST` | `/api/auditor/best-practices/seed` | admin | Popula 207 regras |
| `PUT` | `/api/auditor/best-practices/:id` | admin | Atualiza regra |

**IMPORTANTE:** O endpoint de upload deve ler `environment_id` tanto do form data quanto do header `X-Environment-Id` (fallback). Sem o `environment_id`, o LLM não é chamado.

### Resposta do POST /upload

```json
{
    "audit_id": 1,
    "filename": "appserver.ini",
    "ini_type": "appserver",
    "score": 70.2,
    "summary": { "ok": 38, "mismatch": 4, "missing": 50, "commented": 3 },
    "findings": [...],
    "commented_findings": [
        {
            "section": "General",
            "key_name": "MaxStringSize",
            "commented_value": "4",
            "recommended_value": "10",
            "severity": "critical",
            "status": "commented",
            "reason": "A chave MaxStringSize é OBRIGATÓRIA mas está comentada..."
        }
    ],
    "commented_sections": [
        { "line": 45, "section": "FTP", "raw": ";[FTP]" }
    ],
    "dirty_lines": [
        { "line": 12, "content": "isso não é chave", "reason": "Linha sem formato chave=valor..." }
    ],
    "encoding_info": {
        "detected": "ASCII puro",
        "is_valid": true,
        "has_bom": false,
        "issues": []
    },
    "suggested_ini": "; === INI SUGERIDO ===\n[General]\n; [CORRIGIDO] era: MaxStringSize=4\nMaxStringSize=10\n...",
    "llm_summary": "## Análise do appserver.ini\n\n...",
    "parsed": {
        "total_sections": 5,
        "total_keys": 42,
        "total_commented": 3,
        "total_commented_sections": 1,
        "total_dirty_lines": 2
    }
}
```

---

## Lógica do Parser INI

O parser é **manual** (não usa `configparser`) para detectar chaves comentadas e sujeira:

```python
for line_num, line in enumerate(content.splitlines(), 1):
    stripped = line.strip()

    # 1. Seção comentada: ;[NomeSecao]
    if re.match(r"^[;#]\s*\[(.+)\]", stripped):
        commented_sections.append(...)

    # 2. Seção ativa: [NomeSecao]
    elif re.match(r"^\[(.+)\]$", stripped):
        current_section = ...

    # 3. Chave comentada: ;key=value
    elif re.match(r"^[;#]\s*([A-Za-z_]\w*)\s*=\s*(.*)", stripped):
        commented[section][key] = value

    # 4. Comentário puro: ;texto sem =
    elif stripped.startswith(";") or stripped.startswith("#"):
        continue

    # 5. Chave ativa: key=value
    elif "=" in stripped:
        # Detectar nome inválido
        if not re.match(r"^[A-Za-z_][\w.]*$", key):
            dirty_lines.append(...)
        # Detectar valor vazio
        if not value:
            dirty_lines.append(...)

    # 6. Sujeira: linha sem formato reconhecido
    else:
        dirty_lines.append(...)
```

### Análise de Encoding

```python
def _analyze_encoding(content_bytes):
    # BOM UTF-8: EF BB BF
    # BOM UTF-16 LE: FF FE
    # BOM UTF-16 BE: FE FF
    # ASCII puro: todos bytes <= 0x7F
    # CP1252 válido mas não UTF-8: é ANSI
    # UTF-8 válido com multibyte: INCOMPATÍVEL
```

---

## Motor de Avaliação Contextual

### Regra principal: só avaliar seções presentes

```python
present_sections = {s.lower() for s in sections}
for bp in practices:
    is_section_present = sec.lower() in present_sections
    # Só avaliar se seção existe OU regra é obrigatória
    if not is_section_present and not bp["is_required"]:
        continue
```

### Detecção de environments dinâmicos

```python
env_indicator_keys = {"rootpath", "sourcepath", "startpath", "rpodb", "rpoversion", "rpolanguage"}
for sec_name, sec_keys in sections.items():
    if {k.lower() for k in sec_keys} & env_indicator_keys:
        detected_environments.append(sec_name)

# Aplicar regras de [Environment] em CADA environment detectado
if sec.lower() == "environment" and detected_environments:
    for env_name in detected_environments:
        _evaluate_bp_against_section(bp, env_name, ...)
```

### Cálculo de Score

```python
weights = {"critical": 3.0, "warning": 1.5, "info": 0.5}
score = (ok_weight / total_weight) * 100
```

---

## LLM Especialista — Prompts

### System Prompt

```
Você é um especialista sênior em infraestrutura TOTVS Protheus com 15+ anos
de experiência em configuração, tunning e troubleshooting de ambientes
Application Server e DBAccess.

[Contexto específico por tipo de INI]

Seu conhecimento inclui:
- Todas as seções e chaves documentadas na TDN
- Impacto real de cada configuração em produção
- A seção [Environment] tem nome customizado pelo cliente
- Encoding OBRIGATÓRIO é ANSI (Windows-1252 / CP1252)
- Boas práticas de segurança: SSL/TLS 1.2+, desabilitar SSLv2/v3
- Boas práticas de performance: MaxStringSize=10, limits de memória
- Boas práticas de diagnóstico: ConsoleLog, LogTimeStamp, ShowIPClient

Instruções:
1. Avaliação geral do arquivo (1-2 frases)
2. Problemas CRÍTICOS primeiro com impacto real
3. Para cada: o que está errado → por que importa → como corrigir
4. Chaves comentadas: seguro ou arriscado?
5. Problemas de encoding: impacto
6. Recomendações gerais
7. Links TDN quando fornecidos
8. Português brasileiro, markdown, direto e prático
```

### User Prompt (enriquecido)

```
Arquivo: appserver.ini
Total de problemas: 5

[CRITICAL] [General] MaxStringSize: AUSENTE (recomendado: 10)
[WARNING] [Drivers] Secure: AUSENTE (recomendado: 1)

Chaves COMENTADAS detectadas (2):
[CRITICAL] [General] ;MaxStringSize=4 — A chave é OBRIGATÓRIA...

## Referência de Boas Práticas (base de conhecimento TDN)
### [General]
- **MaxStringSize**: Tamanho máximo de strings. Deve ser 10... [TDN](url)
- **;ConsoleLog** (comentada): Chave está comentada...
```

### Modelo recomendado

| Modelo | Input | Output | Custo/análise | Nota |
|--------|-------|--------|---------------|------|
| **gemini-2.5-flash-lite** | $0.10/1M | $0.40/1M | R$ 0,003 | **Recomendado** (tem tier free) |
| gemini-2.0-flash | $0.10/1M | $0.40/1M | R$ 0,003 | Alternativa |
| gemini-3.1-flash-lite | $0.25/1M | $1.50/1M | R$ 0,019 | Mais caro |

---

## Regras de Seed — 207 Regras

### AppServer.ini (196 regras)

| Seção | Qtd | Destaques |
|-------|-----|-----------|
| [General] | 40 | MaxStringSize, memória, logs, segurança, performance |
| [Drivers] | 4 | Active=TCP, SSL, MultiProtocol |
| [DBAccess] | 6 | Server, Port, Database, Alias, Driver, MemoMega |
| [SSLConfigure] | 16 | SSL2/3=0 (INSEGURO), TLS1.2/1.3=1, certificados |
| [Environment] | 17 | RootPath, SourcePath, RPO, memória por thread |
| [HTTP] | 10 | CORS, HSTS, compressão, logging |
| [HTTPS] | 3 | SecureCookie, ClientCertVerify |
| [Webapp] | 11 | Port, SSL, MaxBody, NonStopOnError |
| [LicenseServer] | 6 | Enable, Port, timeouts, ShowStatus |
| [Update] | 2 | Enable, ForceUpdate |
| [Mail] | 5 | Protocol, SMTP, auth, TLS |
| [FTP] | 3 | Enable=0 (desativar), CheckPassword |
| [Telnet] | 2 | Enable=0 (inseguro em produção) |
| [LockServer] | 4 | Enable, Port, SecureConnection |
| [OnStart] | 2 | Jobs, RefreshRate |
| [BTMonitor] | 3 | Enable, Type, LogLevel |
| [Broker] | 15 | Enable, Port, Type, Servers, HA, WebMonitor, SSL |
| [BrokerAgent] | 3 | Enable, Port, BrokerServer |
| [WebAgent] | 2 | Port, Version |
| [SQLiteServer] | 3 | Enable, Port, Instances |
| [Tec.AppServer.Memory] | 1 | Enable |
| [APP_MONITOR] | 1 | Enable |

### DBAccess.ini (11 regras + 16 Environment + 3 SSL)

| Seção | Qtd | Destaques |
|-------|-----|-----------|
| [General] | 16 | Port, MaxStringSize, consoleLog, threads, deadlock, monitor |
| [Environment] | 18 | UseBind, UseHint, LockTimeOut, compression, SeekBind |
| [MSSQL] | 2 | Server, Database |
| [Oracle] | 2 | Server, Database |
| [PostgreSQL] | 3 | Server, Database, Port |
| [SSLConfigure] | 3 | Enable, CertificateFile, KeyFile |

---

## Navegação — Onde o módulo fica no frontend

```
Monitoramento (tab)
├── Monitoramento de Logs   (observability)
├── Banco de Dados          (database)
└── Auditor INI             (auditor)   ← novo módulo
```

**IMPORTANTE:** A key da categoria é `'monitoramento'`, NÃO `'observabilidade'`.

### Permissões

O módulo `'auditor'` deve ser adicionado nas listas de permissões de **todos os perfis**:
- `admin`: inclui `'auditor'`
- `operator`: inclui `'auditor'`
- `viewer`: inclui `'auditor'`

---

## Checklist de Implementação

### Backend
- [ ] Criar migration (adaptar número ao ATURPO_2)
- [ ] Registrar migration no runner
- [ ] Criar service `ini_auditor.py`
  - [ ] `parse_ini_file()` — parser manual com detecção de comentados, sujeira e encoding
  - [ ] `_analyze_encoding()` — detecta BOM, UTF-8, UTF-16, CP1252
  - [ ] `_detect_ini_type()` — por nome e conteúdo
  - [ ] `compare_against_best_practices()` — análise contextual (só seções presentes)
  - [ ] Detecção de environments dinâmicos por chaves indicadoras
  - [ ] `_evaluate_bp_against_section()` — avaliação por seção para environments
  - [ ] `_evaluate_value()` — 5 tipos (string, integer, boolean, range, enum)
  - [ ] `_explain_commented()` — explicação do impacto de chave comentada
  - [ ] `_generate_suggested_ini()` — INI corrigido com marcações
  - [ ] `generate_llm_insights()` — chamada LLM com prompt especialista
  - [ ] `_build_specialist_prompt()` — system prompt por tipo de INI
  - [ ] `_build_rules_context()` — contexto das regras do PG para o LLM
  - [ ] `run_audit()` — orquestrador
  - [ ] `get_audit_history()` — histórico paginado
  - [ ] `get_audit_detail()` — detalhe com JOIN
  - [ ] `seed_best_practices()` — 207 regras com helper `r()`
- [ ] Criar route `auditor.py` com blueprint
  - [ ] POST `/api/auditor/upload` (multipart + JSON, ler `X-Environment-Id`)
  - [ ] GET `/api/auditor/history`
  - [ ] GET `/api/auditor/audit/:id`
  - [ ] DELETE `/api/auditor/audit/:id` (admin)
  - [ ] GET `/api/auditor/best-practices`
  - [ ] POST `/api/auditor/best-practices/seed` (admin)
  - [ ] PUT `/api/auditor/best-practices/:id` (admin)
- [ ] Registrar blueprint no app

### Frontend
- [ ] Criar módulo JS/componente
- [ ] Registrar na categoria **Monitoramento** (key `'monitoramento'`)
- [ ] Adicionar `'auditor'` nas permissões de todos os perfis
- [ ] Usar `authToken` (não `sessionStorage.token`) para upload multipart
- [ ] Usar `apiRequest(endpoint, 'POST')` (não `{method: 'POST'}`) para chamadas
- [ ] Verificar nome correto da função de notificação (`showNotification`, não `showToast`)
- [ ] Verificar campo de perfil do usuário (`currentUser.profile`, não `.role`)
- [ ] Tab Upload: drag-and-drop, seletor, resultado rápido com score
- [ ] Tab Resultados: cards colapsáveis com scroll (ver ordem acima)
- [ ] Tab Histórico: tabela paginada, click para detalhe
- [ ] Tab Boas Práticas: listagem, seed TDN (admin), filtro por tipo
- [ ] Download INI sugerido em ANSI (CP1252)
- [ ] Registrar no router/navegação

### Testes
- [ ] parse_ini_file — UTF-8, cp1252, BOM, sujeira, comentados
- [ ] _analyze_encoding — todos os cenários
- [ ] _detect_ini_type — por nome e conteúdo
- [ ] compare_against_best_practices — contextual, environments dinâmicos
- [ ] _evaluate_value — todos os 5 tipos
- [ ] _generate_suggested_ini — correções e descomentados
- [ ] Upload endpoint — multipart, JSON, X-Environment-Id
- [ ] seed_best_practices — 207 regras

### Deploy
- [ ] Rodar migration
- [ ] Seed de boas práticas (via endpoint admin)
- [ ] Configurar LLM (recomendado: gemini-2.5-flash-lite via Google direto)
- [ ] Testar com appserver.ini real (com múltiplos environments)
- [ ] Testar com dbaccess.ini real

---

## Lições Aprendidas no Protótipo

### 1. Race condition no i18n
O `loadLocale()` era fire-and-forget, causando chaves i18n brutas na tela. Correção: `await loadLocale()` antes de renderizar.

### 2. Permissões do módulo
O módulo não aparecia no sidebar porque `'auditor'` não estava na lista de `hasPermission()`. Adicionar em TODOS os perfis.

### 3. Auth token no upload multipart
O `apiRequest` do projeto usa `authToken` (de `sessionStorage.auth_token`), não `sessionStorage.token` com `Bearer`. Para upload multipart (FormData), enviar o token no header manualmente usando a variável global.

### 4. Assinatura do apiRequest
O `apiRequest` recebe `(endpoint, method, data)` — não `(endpoint, {method: 'POST'})`.

### 5. Campo de perfil do usuário
O projeto usa `currentUser.profile`, não `currentUser.role`. A verificação de admin é `isRootAdmin() || currentUser.profile === 'admin'`.

### 6. Nomenclatura observabilidade → monitoramento
A key da categoria `CATEGORIES` deve ser `'monitoramento'`, não `'observabilidade'`.

### 7. environment_id para LLM
O endpoint de upload deve ler `environment_id` do header `X-Environment-Id` como fallback, senão o LLM nunca é chamado em uploads multipart.

### 8. Encoding ANSI obrigatório
Arquivos INI do Protheus DEVEM ser ANSI (CP1252). O INI sugerido deve ser baixado nesse encoding. No browser, usar conversão manual (charCodeAt → Uint8Array).

### 9. Seção [Environment] é dinâmica
Nenhum INI real tem `[Environment]` — o nome é definido pelo cliente (ex: `[P12_PRODUCAO]`). Detectar pelo conteúdo (presença de RootPath, SourcePath, etc.).

---

## Referência: Código-fonte do protótipo

O protótipo funcional e validado está em:
- `aturpo_demo/app/database/migrations/018_ini_auditor.py`
- `aturpo_demo/app/services/ini_auditor.py` (1800+ linhas, 207 regras)
- `aturpo_demo/app/routes/auditor.py`
- `aturpo_demo/static/js/integration-auditor.js`

Use como referência, mas **adapte aos padrões do ATURPO_2**.

---

## Evolução Futura (v2)

1. **Skill dedicada no GolIAs** — agente especialista com RAG da base TDN
2. **Insights por chave** — LLM gera explicação individual por finding
3. **Diff entre auditorias** — compara evolução do mesmo arquivo
4. **Scraper TDN dinâmico** — extrair regras automaticamente dos JSONs
5. **Gerador de INI do zero** — gerar INI ideal baseado em questionário
6. **SmartClient.ini completo** — ampliar cobertura
7. **Webhooks** — notifica quando score < threshold
8. **Bulk audit** — analisar múltiplos INIs de uma vez
9. **Comparação entre environments** — detectar inconsistências entre prod/homolog
