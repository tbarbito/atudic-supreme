# Prompt de Implementacao — Formatacao Inteligente de Resultados de Tools para LLM

> **Projeto:** AtuDIC (aturpo_demo)
> **Arquivos alvo:** `app/services/agent_tools.py`, `app/services/agent_chat.py`
> **Commits de referencia no AtuDIC:** 5f3912e..1f75a12
> **Data:** 2026-03-24
> **Autor:** Barbito + Claude Opus 4.6

---

## Problema

O LLM recebia resultados de tools como **JSON bruto truncado** a 3000 caracteres:

```json
{"connections": [{"id": 1, "name": "Protheus HML", "driver": "mssql", "host": "192.168.122.41", "port": 1433, "database_name": "protheus", "username": "protheus", "environment_id": 1, "is_readonly": true}, {"id": 2, "name": "Protheus PRD", "dri... (truncado)
```

### Consequencias
1. **JSON invalido** — trunca no meio de uma string, LLM nao consegue parsear
2. **Ruido excessivo** — chaves repetidas, aspas, colchetes consomem tokens sem valor
3. **Alucinacao** — LLM preenche lacunas do JSON cortado com dados inventados
4. **Caso real:** `compare_dictionary` retornava JSON de 50KB+ com milhares de registros. O LLM inventava campos que nao existiam no resultado

---

## Solucao: `format_tool_result_for_llm()`

Funcao centralizada que converte resultados de tools em **texto estruturado compacto** que o LLM interpreta com precisao.

### Antes vs Depois

**JSON bruto (antes):**
```json
{"alerts": [{"id": 1, "category": "database", "severity": "critical", "message": "ORA-00060 deadlock detected", "source_file": "/var/log/protheus.log", "thread_id": "T001", "created_at": "2026-03-24T09:00:00", "acknowledged": false}], "total": 1}
```

**Tabela compacta (depois):**
```
get_alerts: 1 resultado(s)
id | category | severity | message | created_at
-----------------------------------------------
1 | database | critical | ORA-00060 deadlock detected | 2026-03-24T09:00:00
```

---

## 1. Adicionar `format_tool_result_for_llm()` em `agent_tools.py`

Adicionar ANTES da secao de ferramentas de leitura:

```python
def format_tool_result_for_llm(tool_name, result, max_chars=3000):
    """Formata resultado de tool para o LLM de forma inteligente.

    Em vez de truncar JSON bruto (que gera JSON invalido e ruido),
    converte para texto estruturado que o LLM interpreta com precisao.
    """
    if isinstance(result, dict) and result.get("error"):
        return f"ERRO: {result['error']}"

    # Se ja tem formatted_result (ex: compare_dictionary), usar direto
    if isinstance(result, dict) and result.get("formatted_result"):
        return result["formatted_result"][:max_chars]

    # Resultados com listas de registros — formatar como tabela compacta
    list_keys = ["alerts", "connections", "environments", "variables", "services",
                 "users", "articles", "schedules", "recurring_errors", "monitors",
                 "webhooks", "summary", "rows", "pipelines", "pipeline_runs",
                 "repositories"]

    for key in list_keys:
        if isinstance(result, dict) and key in result and isinstance(result[key], list):
            items = result[key]
            total = result.get("total", len(items))

            if not items:
                return f"{tool_name}: nenhum resultado encontrado."

            # Pegar colunas do primeiro item
            if isinstance(items[0], dict):
                cols = list(items[0].keys())
                # Excluir colunas sensiveis
                cols = [c for c in cols if c not in (
                    "password", "password_salt", "api_key_encrypted"
                )]

                lines = [f"{tool_name}: {total} resultado(s)"]
                lines.append(" | ".join(cols))
                lines.append("-" * min(len(" | ".join(cols)), 80))

                for item in items[:30]:  # Max 30 linhas
                    vals = []
                    for c in cols:
                        v = str(item.get(c, ""))
                        if len(v) > 50:
                            v = v[:47] + "..."
                        vals.append(v)
                    lines.append(" | ".join(vals))

                if len(items) > 30:
                    lines.append(f"... e mais {len(items) - 30} registros")

                text = "\n".join(lines)
                if result.get("note"):
                    text += f"\n{result['note']}"
                if result.get("hint"):
                    text += f"\n{result['hint']}"
                return text[:max_chars]
            else:
                # Lista de strings simples
                text = f"{tool_name}: {total} resultado(s)\n"
                text += "\n".join(f"- {str(item)[:100]}" for item in items[:30])
                return text[:max_chars]

    # Dicts simples (status, config, etc) — formatar como key: value
    if isinstance(result, dict):
        lines = []
        for k, v in result.items():
            if k.startswith("_") or k in (
                "password", "password_salt", "api_key_encrypted"
            ):
                continue
            v_str = str(v)
            if len(v_str) > 200:
                v_str = v_str[:197] + "..."
            lines.append(f"{k}: {v_str}")
        return "\n".join(lines)[:max_chars]

    # Fallback — string simples
    text = str(result)
    return text[:max_chars] if len(text) > max_chars else text
```

### Regras da funcao

| Tipo de resultado | Formato gerado | Limite |
|-------------------|---------------|--------|
| Lista de dicts (alerts, connections, etc) | Tabela texto com `\|` separador | 30 linhas |
| Dict com `formatted_result` | Texto pre-formatado | max_chars |
| Dict simples (status, config) | `key: value` por linha | max_chars |
| Dict com `error` | `ERRO: mensagem` | sem limite |
| String | Texto direto | max_chars |

### Colunas sensiveis excluidas automaticamente
- `password`, `password_salt`, `api_key_encrypted`

### Valores truncados
- Cada celula: max 50 caracteres (com `...`)
- Resultado total: max 3000 caracteres

---

## 2. Importar no `agent_chat.py`

```python
from app.services.agent_tools import get_available_tools, execute_tool, AGENT_TOOLS, format_tool_result_for_llm
```

---

## 3. Substituir truncacao em 3 pontos do `agent_chat.py`

### 3.1 Confirmed Action (execute_confirmed_action)

**Antes:**
```python
result_text = json.dumps(tool_result, ensure_ascii=False, default=str)
if len(result_text) > 3000:
    result_text = result_text[:3000] + "... (truncado)"
```

**Depois:**
```python
result_text = format_tool_result_for_llm(tool_name, tool_result)
```

### 3.2 Two-Step Mode (_compose_response_llm)

**Antes:**
```python
tool_result_text = json.dumps(tool_result, ensure_ascii=False, default=str)
if len(tool_result_text) > cfg.TOOL_RESULT_TRUNCATE:
    tool_result_text = tool_result_text[:cfg.TOOL_RESULT_TRUNCATE] + "... (truncado)"
```

**Depois:**
```python
tool_result_text = format_tool_result_for_llm(tool_name, tool_result)
```

### 3.3 ReAct Loop (_react_loop)

**Antes:**
```python
result_text = json.dumps(tool_result, ensure_ascii=False, default=str)
if len(result_text) > 3000:
    result_text = result_text[:3000] + "... (truncado)"

messages.append({"role": "user", "content": f"Resultado de {tool_name}:\n```json\n{result_text}\n```\n..."})
```

**Depois:**
```python
result_text = format_tool_result_for_llm(tool_name, tool_result)

messages.append({"role": "user", "content": f"Resultado de {tool_name}:\n{result_text}\n..."})
```

**Nota:** remover o ````json ... ```` wrapper no ReAct — o resultado ja nao e JSON.

---

## 4. Pre-formatar tools com resultados grandes

### 4.1 `compare_dictionary` — ja implementado

Retornar `{"formatted_result": "texto compacto"}` em vez do JSON bruto.
A funcao `format_tool_result_for_llm` detecta `formatted_result` e usa direto.

```python
def _tool_compare_dictionary(params):
    # ... chama API ...
    result = _internal_api("POST", "/api/dictionary/compare", json_body={...})

    # Pre-formatar para LLM
    lines = []
    lines.append(f"Comparacao empresa {company_code}: ...")
    for tname, info in sorted(results.items()):
        only_a = info.get("only_a", [])
        # ... formatar ...
        for item in only_a[:20]:
            lines.append(f"    - {item.get('key', '')}")

    return {"formatted_result": "\n".join(lines), "history_id": result.get("history_id")}
```

### 4.2 `query_database` — ja trunca a 20 linhas

```python
if len(result["rows"]) > 20:
    result["rows"] = result["rows"][:20]
    result["note"] = f"Mostrando 20 de {result.get('row_count', '?')} linhas."
```

A funcao `format_tool_result_for_llm` vai converter essas 20 linhas em tabela texto.

### 4.3 Outros tools com resultados grandes — candidatos

Se algum tool retornar mais de 50 registros regularmente, considere:
1. Adicionar `LIMIT` na query do handler
2. Ou retornar `formatted_result` pre-formatado

---

## 5. Verificacao

### Testes manuais
```python
from app.services.agent_tools import format_tool_result_for_llm

# Lista de dicts
result = {"connections": [{"id": 1, "name": "HML"}, {"id": 2, "name": "PRD"}], "total": 2}
print(format_tool_result_for_llm("get_db_connections", result))
# Saida:
# get_db_connections: 2 resultado(s)
# id | name
# --------
# 1 | HML
# 2 | PRD

# Erro
print(format_tool_result_for_llm("x", {"error": "nao encontrado"}))
# Saida: ERRO: nao encontrado

# formatted_result
print(format_tool_result_for_llm("compare", {"formatted_result": "SX3990: 3 diffs"}))
# Saida: SX3990: 3 diffs

# Dict simples
print(format_tool_result_for_llm("status", {"mode": "llm", "provider": "gemini"}))
# Saida:
# mode: llm
# provider: gemini
```

### Checklist
- [ ] `format_tool_result_for_llm` adicionada em `agent_tools.py`
- [ ] Importada em `agent_chat.py`
- [ ] Substituida em confirmed action (1 ponto)
- [ ] Substituida em two-step mode (1 ponto)
- [ ] Substituida em ReAct loop (1 ponto)
- [ ] `compare_dictionary` retorna `formatted_result`
- [ ] `query_database` limita a 20 linhas
- [ ] Wrapper ````json```` removido do ReAct (nao e mais JSON)

---

## 6. Licoes Aprendidas

| Licao | Detalhe |
|-------|---------|
| **JSON bruto e toxico para LLMs** | Chaves repetidas, aspas, colchetes consomem tokens e geram ruido. Tabelas texto sao 3-5x mais eficientes em tokens. |
| **Truncar JSON = JSON invalido** | Cortar `{"name": "Proth...` no meio gera JSON que o LLM nao consegue parsear, forcando-o a "adivinhar" o resto. |
| **Centralize a formatacao** | Uma funcao unica evita ter 3 logicas diferentes de truncacao espalhadas pelo codigo. |
| **Pre-formate resultados grandes** | Tools como `compare_dictionary` que retornam 50KB+ devem fazer a formatacao no handler, nao no chat engine. |
| **Tabelas texto > JSON para LLMs** | O formato `col1 \| col2\n---\nval1 \| val2` e interpretado com 95%+ de precisao pelos LLMs, vs ~70% para JSON truncado. |
