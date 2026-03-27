# AtuDIC Supreme

Plataforma unificada de inteligencia Protheus — DevOps, Engenharia Reversa e Agente IA.

## Origem

Merge de dois projetos complementares:

- **AtuDIC** (Barbito) — DevOps, dicionario Protheus, agente GolIAs com 59 tools e 389K chunks TDN
- **ExtraiRPO** (Joni) — Engenharia reversa, parser de fontes ADVPL/TLPP, grafo de vinculos, docs IA

## O que faz

```
1. DESCOBRIR   -> Workspace analisa fontes + dicionario (offline CSV ou live DB)
2. COMPARAR    -> Dictionary compare/validate (19 camadas de integridade)
3. ENTENDER    -> GolIAs Supreme com grafos + analise de impacto + TDN
4. DOCUMENTAR  -> Pipeline 3 agentes gera docs automaticas (19 secoes + Mermaid)
5. CORRIGIR    -> Equalize aplica no banco com rollback atomico
6. MONITORAR   -> Alertas + pipelines CI/CD + proactive agent
```

## Arquitetura Hibrida

| Camada | Banco | Uso |
|--------|-------|-----|
| Plataforma | PostgreSQL | Config, users, historico, TDN, alertas |
| Workspace | SQLite (por workspace) | Dicionario, fontes, vinculos, chunks |
| Protheus | Conexao direta (MSSQL/Oracle/PG) | Compare, validate, equalize |

## Stack

- **Backend:** Python 3.12+ / Flask
- **Frontend:** HTML/CSS/JS vanilla (lazy-loaded)
- **Agente IA:** 63+ tools, 15 specialists, 10+ LLM providers
- **Deploy:** PyInstaller + Inno Setup (Windows), Docker (Linux)

## Quick Start

```bash
# Clonar
git clone https://github.com/tbarbito/atudic-supreme.git
cd atudic-supreme

# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Rodar
python run.py  # http://localhost:5000
```

## Desenvolvedores

- **Barbito** (Tiago Barbieri) — [@tbarbito](https://github.com/tbarbito)
- **Joni** (Joni Praia) — [@JoniPraia](https://github.com/JoniPraia)

## Licenca

Proprietario — Normatel / Todimo
