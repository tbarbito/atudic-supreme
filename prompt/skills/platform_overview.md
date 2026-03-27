---
name: platform_overview
description: Arquitetura AtuDIC, stack, modulos ativos, estrutura de diretorios
intents: [general, environment_status]
keywords: [arquitetura, stack, tecnologia, flask, postgresql, diretorio, estrutura, modulo, blueprint, como funciona, atudic]
priority: 60
always_load: false
max_tokens: 400
specialist: general
---

## ARQUITETURA AtuDIC

### O que e o AtuDIC
Plataforma DevOps completa para TOTVS Protheus — orquestracao CI/CD, observabilidade, gestao de dicionario e auditoria.

### Modulos Ativos
| Categoria | Modulos | Funcionalidades |
| --------- | ------- | --------------- |
| Dashboard | Dashboard | KPIs, metricas, visao geral |
| CI/CD | Pipelines | Criacao, execucao, agendamento de pipelines |
| CI/CD | Schedule | Agendamentos cron-like |
| CI/CD | Comandos | Comandos de build/deploy |
| Repositorios | Repositorios GitHub | Integracao GitHub API, clone, branches |
| Repositorios | Controle de Versao | Explorer de arquivos, historico de commits |
| Monitoramento | Observabilidade | Alertas, logs, parsing inteligente |
| Monitoramento | Banco de Dados | Conexoes, schema, dicionario, equalizacao |
| Monitoramento | Processos | Mapeamento de processos da empresa |
| Monitoramento | Auditor INI | Analise de appserver.ini, boas praticas |
| Conhecimento | Agente GolIAs | Chat, memoria, busca KB |
| Conhecimento | Base de Conhecimento | Erros Protheus catalogados |
| Conhecimento | Documentacao | Geracao automatica de docs |
| Workspace | Dev Workspace | Ambiente de desenvolvimento integrado |
| Admin | Usuarios | Perfis, sessoes |
| Admin | Configuracoes | Ambientes, variaveis, GitHub, servicos, LLM, branch policies |

### Stack
| Componente | Tecnologia |
| ---------- | ---------- |
| Backend | Python 3.12, Flask 3.0, Gunicorn + Gevent |
| Banco | PostgreSQL 16 (pool min=2, max=30) |
| Banco Agente | SQLite com FTS5 (BM25) |
| Frontend | SPA Vanilla JS, Bootstrap 5.3, Tailwind CSS |
| Criptografia | Fernet (symmetric), bcrypt 12 rounds |

### Estrutura

```
aturpo_demo/
├── run.py                  # Entry point
├── app/
│   ├── routes/             # Blueprints (endpoints)
│   ├── services/           # Logica de negocio
│   ├── database/           # PostgreSQL, seeds, migrations
│   └── utils/              # Security, crypto, audit
├── static/js/              # Modulos JS lazy-loaded
├── memory/                 # Memoria do agente (SQLite FTS5)
└── prompt/skills_v2/       # Skills modulares do GolIAs
```
