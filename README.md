# AtuDIC DevOps

Orquestrador CI/CD + Observabilidade para ERP TOTVS Protheus.

Plataforma web para automação de builds, deploys, controle de serviços e monitoramento de logs do Protheus, com interface responsiva (desktop e mobile).

## Funcionalidades

- **Pipelines CI/CD** — Criação, execução e agendamento (cron) de pipelines de build e deploy
- **Controle de Serviços** — Start/Stop/Restart de serviços Protheus remotos via SSH
- **Repositórios GitHub** — Integração com GitHub API para clonar, gerenciar branches e tags
- **Controle de Versão** — Explorador de arquivos e histórico de commits dos repositórios
- **Observabilidade** — Parser inteligente de logs do Protheus (15+ categorias de erros: SSL, TopConnect, RPO, Thread Error, ORA, etc.)
- **Dashboard** — Visão geral com KPIs de pipelines, serviços e saúde do ambiente
- **Ambientes** — Gestão de múltiplos ambientes (Produção, Homologação, Desenvolvimento)
- **Notificações** — Email e WhatsApp (Evolution API / Z-API) para alertas de pipeline e serviços
- **Webhooks** — Dispatcher de eventos para integrações externas
- **API REST** — API externa autenticada via API Keys para integração com ferramentas de terceiros
- **Agendamento** — Scheduler cron-like para execução automática de pipelines
- **Licenciamento** — Sistema de licenças por hardware ID

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.12, Flask 3.0, Gunicorn + Gevent |
| Banco de Dados | PostgreSQL 16 (produção), SQLite (fallback) |
| Frontend | HTML5, Vanilla JS, Bootstrap 5.3, CSS customizado |
| Segurança | Bcrypt (12 rounds), Fernet (cryptography), Rate Limiting |
| Infra | Docker, Docker Compose, GitHub Actions CI/CD |

## Configuração para Desenvolvimento

### Pré-requisitos

- Python 3.10+
- PostgreSQL 16 (ou SQLite para desenvolvimento local)
- Git

### Setup

```bash
# Clonar o repositório
git clone https://github.com/tbarbito/aturpo_2.git
cd aturpo_2
git checkout develop

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
# Criar arquivo .env ou config.env com:
#   DB_HOST=localhost
#   DB_PORT=5432
#   DB_NAME=atudic
#   DB_USER=atudic
#   DB_PASSWORD=atudic

# Iniciar a aplicação
python run.py
```

A aplicação ficará acessível em `http://localhost:5000`.

### Docker

```bash
docker compose up -d            # Iniciar (PostgreSQL + App)
docker compose logs -f app      # Ver logs
docker compose down             # Parar
```

## Testes e Lint

```bash
# Rodar todos os testes com coverage
pytest

# Apenas testes unitários ou de integração
pytest tests/unit/ -v
pytest tests/integration/ -v

# Teste específico
pytest tests/unit/test_crypto.py -v
pytest -k "test_login" -v

# Lint e formatação
black --check --line-length 120 app/ run.py
flake8 app/ run.py
```

O CI (GitHub Actions) exige: `black --check`, `flake8` e `pytest --cov-fail-under=58`.

## Build Windows (.exe)

```bash
# Requer Windows com PyInstaller e Inno Setup instalados
python build_installer.py
```

Artefatos gerados em `aturpo_win/dist/` (executável) e `aturpo_win/Output/` (instalador).

## Documentação da API

A documentação completa da API REST externa está em [API_DOCS.md](API_DOCS.md).

Autenticação via header `x-api-key: at_XXXXXXXXX` ou `Authorization: Bearer at_XXXXXXXXX`.

## Licença

Software proprietário. Todos os direitos reservados.
