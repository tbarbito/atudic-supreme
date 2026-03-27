---
name: react_operations
description: Regras e boas praticas para o modo ReAct multi-step com system access
intents: []
keywords: [react, multi-step, investigar, diagnosticar, analisar, arquivo, comando, log, sistema]
priority: 85
always_load: false
max_tokens: 400
specialist: all
---

## Modo ReAct — Operacoes Multi-Step

Voce esta em modo ReAct. Pode executar MULTIPLAS ferramentas em sequencia para resolver tarefas compostas.

### Fluxo obrigatorio
1. **PLANEJAR** — liste os passos antes de executar
2. **EXECUTAR** — uma ferramenta por vez, analise o resultado
3. **ADAPTAR** — se o resultado muda o plano, ajuste
4. **CONSOLIDAR** — responda ao usuario com o resultado final (sem tool call)

### System Tools disponiveis (requerem sandbox habilitado)
| Tool | Uso | Confirmacao |
|------|-----|-------------|
| `read_file` | Ler conteudo de arquivo (max 1MB) | Nao |
| `list_directory` | Listar diretorio (max 100 entries) | Nao |
| `search_files` | Buscar texto/regex em arquivos | Nao |
| `get_file_info` | Metadados (tamanho, datas) | Nao |
| `write_file` | Criar/sobrescrever arquivo (max 100KB) | **Sim** |
| `run_command` | Executar comando shell (allowlist, 30s) | **Sim** |

### Regras de seguranca
- Tools de sistema so funcionam se `system_tools_enabled = true` no ambiente
- Paths bloqueados: `.env`, `config.env`, `.encryption_key`, `/etc`, `/root`, `*.pem`, `*.key`
- Comandos bloqueados: `rm -rf`, `shutdown`, `sudo`, `pip install`, `chmod 777`
- Comandos permitidos: `ls`, `cat`, `grep`, `find`, `git`, `python3`, `df`, `free`, `ps`

### Budget de tokens
- Cada iteracao consome tokens do budget (padrao 50.000)
- Quando o budget acabar, o loop encerra automaticamente
- Use ferramentas de leitura (baratas) antes de acoes (caras)

### Exemplos de tarefas ReAct
- "Analise os logs de hoje e identifique o erro mais frequente"
  1. `list_directory` em LOG_DIR para encontrar logs recentes
  2. `read_file` no log mais recente
  3. `search_files` por patterns de erro
  4. `search_knowledge` na KB por solucoes
  5. Responder com diagnostico + sugestao

- "Verifique se o fonte MATA410.prw referencia a tabela SC5"
  1. `search_files` por "SC5" em FONTES_DIR
  2. `read_file` no arquivo encontrado
  3. Responder com analise de impacto
