# PROMPT — Phase 5: Módulo Auditor de INI Protheus

> **Projeto:** AtuDIC (aturpo_demo)
> **Data:** 2026-03-21
> **Autor:** Barbito + Claude Opus 4.6
> **Status:** Implementado

---

## Resumo Executivo

Novo módulo **Auditor** que permite ao usuário fazer upload de arquivos `.ini` de servidores TOTVS Protheus (appserver.ini, dbaccess.ini, smartclient.ini), compará-los automaticamente contra boas práticas armazenadas no PostgreSQL e receber orientações sobre como está e como poderia estar cada configuração, com dicas e insights.

A arquitetura prioriza **economia de tokens**: 80-90% das análises são determinísticas (Python + PostgreSQL), e o LLM só é chamado para gerar texto explicativo humanizado sobre o delta de problemas encontrados.

---

## Problema Resolvido

Administradores de servidores Protheus frequentemente configuram arquivos `.ini` sem seguir as melhores práticas da TDN (TOTVS Developer Network). Isso causa:
- Problemas de performance (MaxStringSize incorreto, falta de limites de memória)
- Falhas de conectividade (DBAccess mal configurado)
- Dificuldade de diagnóstico (logs desabilitados, sem timestamp)
- Vulnerabilidades (comunicação sem SSL, falta de limites)

O Auditor resolve isso automatizando a verificação contra regras conhecidas e fornecendo orientação clara e contextualizada.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│  FLUXO DO AUDITOR                                   │
│                                                      │
│  1. Upload .ini ──→ Parser (configparser)            │
│  2. Parser ──→ Extrai seções/chaves/valores          │
│  3. PostgreSQL ──→ Busca best practices cadastradas  │
│     (tabela: ini_best_practices)                     │
│  4. Diff local ──→ Compara config vs best practices  │
│  5. LLM (só o delta) ──→ Gera insights/explicações   │
│  6. Resultado ──→ Salva no PG + retorna ao frontend  │
└─────────────────────────────────────────────────────┘
```

### Camadas de custo de tokens

| Camada | O que faz | Custo |
|--------|-----------|-------|
| Best practices no PG | Regras por seção/chave do INI | Zero tokens |
| Diff local em Python | Compara .ini vs regras do PG | Zero tokens |
| Cache de respostas no PG | Reutiliza análises anteriores | Zero tokens |
| LLM só para o delta | Gera texto explicativo | ~500-2000 tokens/análise |

---

## Arquivos Criados/Modificados

### Novos

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `app/database/migrations/018_ini_auditor.py` | Migration | 3 tabelas: ini_audits, ini_best_practices, ini_audit_results |
| `app/services/ini_auditor.py` | Service | Parser INI, motor de comparação, integração LLM, seed |
| `app/routes/auditor.py` | Route | Blueprint com 7 endpoints REST |
| `static/js/integration-auditor.js` | Frontend | Módulo JS lazy-loaded com 4 tabs |
| `guia/PROMPT_PHASE5_AUDITOR_INI.md` | Doc | Este documento |

### Modificados

| Arquivo | Alteração |
|---------|-----------|
| `app/database/migrate.py` | Adicionadas migrations 017 e 018 na lista `_KNOWN_MIGRATIONS` |
| `run.py` | Import + register_blueprint do `auditor_bp` |
| `static/js/integration-core.js` | Registro em: `_isModuleAlreadyLoaded`, `PAGE_MODULES`, `CATEGORIES` (key `'monitoramento'`), `pageRenderFunctions`, `PAGE_LABELS` |

**Nota importante:** A key da categoria no `CATEGORIES` é `'monitoramento'` (não `'observabilidade'`). A nomenclatura foi padronizada no refactor `77218b1`. O módulo Auditor fica na categoria **Monitoramento** ao lado de "Monitoramento de Logs" e "Banco de Dados":

```javascript
'monitoramento': { label: 'Monitoramento', icon: 'fa-eye',
    pages: ['observability', 'database', 'auditor'], defaultPage: 'observability' },
```

---

## Banco de Dados — Migration 018

### Tabela: `ini_audits`
Histórico de uploads e análises.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | SERIAL PK | ID da auditoria |
| environment_id | INTEGER | Ambiente associado |
| user_id | INTEGER | Usuário que fez upload |
| filename | VARCHAR(255) | Nome do arquivo |
| ini_type | VARCHAR(50) | appserver, dbaccess, smartclient, custom |
| raw_content | TEXT | Conteúdo bruto do arquivo |
| parsed_json | TEXT | JSON com seções/chaves parseadas |
| total_sections | INTEGER | Total de seções |
| total_keys | INTEGER | Total de chaves |
| score | NUMERIC(5,2) | Nota geral 0-100 |
| llm_summary | TEXT | Resumo gerado pelo LLM (cache) |
| llm_provider | VARCHAR(50) | Provider usado |
| llm_model | VARCHAR(100) | Modelo usado |
| status | VARCHAR(20) | pending, analyzed, error |
| created_at | TIMESTAMP | Data de criação |

### Tabela: `ini_best_practices`
Regras de boas práticas por seção/chave.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | SERIAL PK | ID da regra |
| ini_type | VARCHAR(50) | Tipo de INI |
| section | VARCHAR(100) | Seção (ex: General, DBAccess) |
| key_name | VARCHAR(100) | Chave (ex: MaxStringSize) |
| recommended_value | TEXT | Valor recomendado |
| value_type | VARCHAR(20) | string, integer, boolean, range, enum |
| min_value | TEXT | Valor mínimo (para ranges) |
| max_value | TEXT | Valor máximo (para ranges) |
| enum_values | TEXT | JSON array de valores válidos |
| severity | VARCHAR(20) | critical, warning, info |
| description | TEXT | Descrição da regra |
| tdn_url | TEXT | Link TDN de referência |
| is_required | BOOLEAN | Se a chave é obrigatória |
| is_active | BOOLEAN | Se a regra está ativa |
| UNIQUE | | (ini_type, section, key_name) |

### Tabela: `ini_audit_results`
Resultados detalhados por chave analisada.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | SERIAL PK | ID |
| audit_id | INTEGER FK | Referência ao ini_audits |
| best_practice_id | INTEGER FK | Referência ao ini_best_practices |
| section | VARCHAR(100) | Seção avaliada |
| key_name | VARCHAR(100) | Chave avaliada |
| current_value | TEXT | Valor encontrado no arquivo |
| recommended_value | TEXT | Valor recomendado |
| severity | VARCHAR(20) | Severidade |
| status | VARCHAR(20) | ok, mismatch, missing, unknown |
| llm_insight | TEXT | Insight individual (futuro) |

---

## API Endpoints

| Método | Endpoint | Auth | Descrição |
|--------|----------|------|-----------|
| POST | `/api/auditor/upload` | auth | Upload e análise de .ini |
| GET | `/api/auditor/history` | auth | Histórico de auditorias |
| GET | `/api/auditor/audit/<id>` | auth | Detalhe de uma auditoria |
| DELETE | `/api/auditor/audit/<id>` | admin | Remove auditoria |
| GET | `/api/auditor/best-practices` | auth | Lista boas práticas |
| POST | `/api/auditor/best-practices/seed` | admin | Popula do TDN |
| PUT | `/api/auditor/best-practices/<id>` | admin | Atualiza regra |

### POST /api/auditor/upload

**Aceita:** `multipart/form-data` com campo `ini_file` ou JSON com `content` + `filename`.

**Resposta:**
```json
{
    "audit_id": 1,
    "filename": "appserver.ini",
    "ini_type": "appserver",
    "score": 72.5,
    "summary": {"ok": 8, "mismatch": 3, "missing": 2},
    "findings": [...],
    "llm_summary": "Markdown com análise humanizada...",
    "parsed": {"total_sections": 5, "total_keys": 42}
}
```

---

## Service: ini_auditor.py

### Funções Principais

| Função | Descrição |
|--------|-----------|
| `parse_ini_file(content, filename)` | Parseia INI com configparser, detecta tipo automaticamente |
| `get_best_practices(ini_type)` | Busca regras ativas do PostgreSQL |
| `compare_against_best_practices(parsed, ini_type)` | Motor determinístico de comparação |
| `generate_llm_insights(findings, ini_type, env_id)` | Gera resumo via LLM (opcional) |
| `run_audit(content, filename, user_id, env_id)` | Orquestrador: parse → compare → LLM → salvar |
| `get_audit_history(env_id, limit, offset)` | Histórico paginado |
| `get_audit_detail(audit_id)` | Detalhes + resultados com JOIN |
| `seed_best_practices()` | Popula regras do TDN (~30 regras iniciais) |

### Motor de Avaliação (`_evaluate_value`)

Suporta 5 tipos de valor:
- **string** — comparação case-insensitive
- **integer** — comparação numérica com range opcional (min/max)
- **boolean** — normaliza 0/1/true/false/yes/no/.t./.f.
- **range** — verifica se está entre min_value e max_value
- **enum** — verifica se pertence à lista de valores válidos

### Score

Score ponderado por severidade:
- **Critical**: peso 3.0
- **Warning**: peso 1.5
- **Info**: peso 0.5

Fórmula: `(soma_pesos_ok / soma_pesos_total) × 100`

---

## Frontend: integration-auditor.js

### 4 Tabs

1. **Upload & Análise** — Drag-and-drop de .ini, análise instantânea com resultado rápido
2. **Resultados** — Findings agrupados por seção, expandíveis, com links TDN
3. **Histórico** — Tabela paginada de auditorias anteriores
4. **Boas Práticas** — Visualização e gestão das regras (seed TDN para admins)

### Features UI
- Score visual com código de cores (verde/amarelo/vermelho)
- Badges de severidade (critical/warning/info)
- Ícones de status (ok/mismatch/missing)
- Links diretos para documentação TDN
- Exportação CSV dos resultados
- Análise IA renderizada em markdown (quando LLM disponível)

---

## Regras de Seed Iniciais (~30 regras)

### AppServer.ini — [General] (13 regras)
- MaxStringSize = 10 (critical, obrigatório)
- ConsoleLog = 1 (warning)
- ConsoleMaxSize = 50-500 (info)
- LogTimeStamp = 1 (warning)
- ShowIPClient = 1 (info)
- ServerType = enum [Master, Slave] (info)
- InactiveTimeout >= 300 (warning)
- MaxBucketCommitTime >= 10 (warning)
- ServerMemoryLimit >= 512 (warning)
- HeapLimit >= 256 (info)
- CanAcceptMonitor = 1 (warning)
- CanRunJobs (info)
- EchoConsoleLog = 0 (info)

### AppServer.ini — [Drivers] (3 regras)
- Active = TCP (critical, obrigatório)
- MultiProtocolPort = 1 (info)
- Secure = 1 (warning)

### AppServer.ini — [DBAccess] (4 regras)
- Database (critical, obrigatório)
- Server (critical, obrigatório)
- Port = 7890 (critical, obrigatório)
- Alias (warning)

### AppServer.ini — [Webapp] (2 regras)
- Port = 80-65535 (info)
- MaxBodySize >= 1024 (info)

### AppServer.ini — [LicenseServer] (1 regra)
- IPCGOTIMEOUT >= 5 (info)

### DBAccess.ini (3 regras)
- [General] Port = 7890 (critical)
- [MSSQL] Server (critical, obrigatório)
- [MSSQL] Database (critical, obrigatório)

---

## Integração LLM

O módulo reutiliza a infraestrutura existente de LLM do AtuDIC:
- Tabela `llm_provider_configs` (migration 015)
- Classe `LLMProvider` de `app/services/llm_providers.py`
- Função `create_provider_from_config()`
- Descriptografia via `crypto.token_encryption.decrypt_token()`

### Recomendação de modelo

| Modelo | Custo (1M tokens) | Avaliação |
|--------|-------------------|-----------|
| **Gemini 2.0 Flash** | ~$0.10 / $0.40 | Melhor custo-benefício |
| Groq (Llama 3.3) | Gratuito (rate limited) | Fallback zero-custo |
| Claude Haiku 3.5 | $0.80 / $4.00 | Bom mas mais caro |
| DeepSeek V3 | $0.27 / $1.10 | Alternativa sólida |

**O módulo funciona 100% sem LLM.** O LLM é opcional e só adiciona um resumo humanizado.

---

## Fluxo de Uso

```
1. Usuário navega para Monitoramento → Auditor INI
2. Faz upload do appserver.ini (drag & drop ou click)
3. Sistema parseia o INI automaticamente
4. Compara contra ~30 regras de boas práticas do PostgreSQL
5. Calcula score ponderado (0-100)
6. Se LLM configurado: envia apenas os problemas (~500 tokens) para gerar resumo
7. Salva tudo no PostgreSQL (auditoria + resultados)
8. Exibe score, findings por seção, links TDN, e análise IA
9. Usuário pode exportar CSV, ver histórico, ou gerenciar regras
```

---

## Próximos Passos (Roadmap)

1. **Insights individuais por chave** — campo `llm_insight` em `ini_audit_results` para explicação detalhada por chave
2. **Comparação entre auditorias** — diff visual entre duas auditorias do mesmo tipo
3. **Scraper TDN automático** — extrair regras dinamicamente dos JSONs em `tdn_scraper/`
4. **SmartClient.ini completo** — ampliar regras para smartclient.ini
5. **Geração de INI ideal** — gerar arquivo .ini corrigido com base nas recomendações
6. **Alertas** — notificar quando score cai abaixo de threshold

---

## Decisões Técnicas

| Decisão | Justificativa |
|---------|---------------|
| `configparser.RawConfigParser` com `optionxform = str` | Protheus INI é case-sensitive |
| Fallback UTF-8 → cp1252 | Padrão Protheus é ANSI/cp1252, mas alguns arquivos podem ser UTF-8 |
| Parser manual como fallback | Alguns INIs Protheus têm formato não-standard |
| Score ponderado por severidade | Problemas críticos impactam mais que informacionais |
| LLM opcional com fallback gracioso | Funcionalidade core não depende de API externa |
| Seed embutido no service | Não precisa de script separado; chamado via rota admin |
| Upload limitado a 1MB | Arquivos INI raramente excedem 50KB |
| Armazenamento em TEXT (não em disco) | Segurança: sem arquivos temporários; conteúdo no banco |

### Bug corrigido durante implementação

**Race condition no i18n** — O `loadLocale()` era fire-and-forget no `initializeApp()`, permitindo que módulos renderizassem antes do locale carregar, exibindo chaves i18n brutas (`observability.title`) em vez de textos traduzidos. Corrigido tornando `initializeApp()` async com `await loadLocale()` antes da renderização. Commit: `edaad6d`.
