---
name: git_ops
description: Operacoes Git — pull, push, status, branches, commits em repositorios configurados
intents: [general]
keywords: [git, pull, push, commit, branch, repositorio, repo, clone, merge, tag, source, fonte, codigo, atualizar, atualiza, sincronizar]
priority: 70
max_tokens: 400
specialist: "devops"
---

## OPERACOES GIT NOS REPOSITORIOS

### Ferramentas disponiveis
- `get_repositories` — listar repos configurados no ambiente
- `git_pull` — atualizar repositorio (pull da branch ativa)

### Inferencia de repositorio
- "atualiza o repo protheus" → inferir repo_id pelo nome
- Se so existe 1 repo no ambiente → usar direto
- Se ja fez pull em um repo na sessao → reutilizar
- NUNCA perguntar qual repo se o nome esta na mensagem

### Fluxo de execucao

**"Atualiza o repo protheus":**
1. `get_repositories` → encontrar o repo pelo nome (inferir, nao perguntar)
2. `git_pull` com repository_id
3. Informar resultado (branch, commits novos)

### Regras
- Cada repo esta vinculado a um environment_id — use o do contexto
- O AtuDIC suporta: clone, pull, push, tag, branch via API
- Repos tem branch ativa e podem ter branch policies (allow_push, require_approval)
- Se branch policy bloqueia a operacao, informar o usuario claramente
- Para operacoes que o agente NAO tem ferramenta (push, commit, branch), orientar via modulo "Controle de Versao"

### Formato de resposta
```
✅ Pull realizado em **protheus** (branch: homolog)
- 3 commits novos recebidos
- Ultimo: "Envio fontes DANA" (tbarbito, 21/02/2026)
```
