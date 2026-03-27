---
name: error_diagnosis
description: Playbook de diagnostico passo a passo para erros Protheus
intents: [error_analysis, alert_recurrence]
keywords: [erro, error, falha, crash, bug, problema, travando, travou, caiu, parou, lento, timeout, ORA, TOPCONN, thread, lock, deadlock, memory, segfault, stack]
priority: 90
max_tokens: 600
specialist: "diagnostico"
---

## PLAYBOOK DE DIAGNOSTICO DE ERROS

### Fluxo obrigatorio (SEMPRE seguir nesta ordem)

```
1. IDENTIFICAR → Qual erro exato? (codigo, mensagem, categoria)
2. LOCALIZAR   → Onde ocorreu? (ambiente, servidor, thread, horario)
3. QUANTIFICAR → Quantas vezes? Desde quando? Tendencia?
4. CORRELACIONAR → Outros erros no mesmo periodo? Mudancas recentes?
5. DIAGNOSTICAR → Causa raiz mais provavel
6. RECOMENDAR  → Acao especifica + como verificar se resolveu
```

### Ferramentas a usar por etapa

| Etapa | Tool | Params |
|-------|------|--------|
| Identificar | `get_alerts` | severity, category, limit=20 |
| Quantificar | `get_alert_summary` | days=7 |
| Recorrencia | `get_recurring_errors` | min_count=3, days=7 |
| Conhecimento | `search_knowledge` | query=mensagem do erro |
| Dados brutos | `query_database` | query SQL especifica |

### Categorias de erro e acao imediata

| Categoria | Exemplo | Acao |
|-----------|---------|------|
| `database` | ORA-00060 (deadlock) | Verificar locks ativos, indices missing |
| `thread_error` | Thread XX terminated | Checar memory leak, stack overflow |
| `network` | Connection refused | Verificar servicos (AppServer, DbAccess) |
| `license` | License expired | Checar data de validade no License Server |
| `compilation` | Compile error in XXX | Verificar fonte no DevWorkspace |
| `lock_timeout` | Lock timeout on SA1 | Identificar usuarios/processos concorrentes |
| `memory` | Out of memory | Checar TopMem, RPO size, conexoes abertas |
| `ssl` | SSL handshake failed | Certificado expirado ou incompativel |

### Formato da resposta de diagnostico

```
**Erro:** [codigo] — [mensagem resumida]
**Ambiente:** [nome] | **Frequencia:** [N vezes em X dias] | **Tendencia:** [subindo/estavel/descendo]

| Causa provavel | Evidencia | Acao |
|----------------|-----------|------|
| [causa 1] | [dado que sustenta] | [o que fazer] |
| [causa 2] | [dado que sustenta] | [o que fazer] |

**Proximo passo:** [acao mais urgente com comando/tool especifico]
```

### Inferencia de contexto para erros
- Se o usuario colou uma mensagem de erro → extrair codigo, categoria e ambiente automaticamente
- Se enviou screenshot → analisar o conteudo visualmente e agir
- Se diz "deu erro no SPED" → buscar alertas de categoria fiscal + KB de SPED
- Se diz "ta travando" → buscar lock_timeout + thread_error nos alertas recentes
- Usar o environment_id do contexto — NUNCA perguntar qual ambiente
- Se o erro menciona arquivo (.ini, .log) → usar read_file para buscar o conteudo

### Regras
- NUNCA diga "pode ser varias coisas" — priorize a causa mais provavel com base nos dados
- Se nao tem dados suficientes, USE ferramentas para coletar (nao peca ao usuario)
- Sempre cheque a KB (search_knowledge) antes de dar diagnostico generico
- Correlacione com deploys recentes (get_pipeline_status) se o erro e novo
- Se o usuario pede "veja a configuracao" → use read_file nos paths do ambiente

### Categorias de erro AppServer/TOTVSTEC (referencia TDN)

A base de conhecimento TDN indexou 15+ categorias de erros do AppServer e TOTVSTEC. Use-as para diagnostico mais preciso:

| Categoria | Subcategorias / Exemplos | Onde investigar |
|-----------|--------------------------|-----------------|
| **DBAccess / TopConnect** | Conexao recusada, timeout, pool esgotado, ORA-*, SQL Server errors | Logs do DBAccess, servico dbaccess, porta 7890 |
| **SmartClient** | Falha de conexao, SSL handshake, versao incompativel, crash na UI | Logs do SmartClient, certificados, versao do build |
| **AppServer** | Thread terminated, out of memory, stack overflow, RPO corrompido | Console log, TopMem, quantidade de threads |
| **License Server** | Licenca expirada, slots esgotados, hardlock nao encontrado | License Server, data de validade, hardlock USB |
| **Compilacao** | Compile error, funcao nao encontrada, include missing | DevWorkspace, RPO, fontes no repositorio |
| **REST/SOAP** | Timeout, 401/403/500, certificado SSL, CORS | Configuracao REST no appserver.ini, certificados |
| **Lock/Deadlock** | Lock timeout, deadlock detected, registro travado | Usuarios conectados, processos concorrentes, indices |
| **Rede / Conexao** | Connection refused, DNS resolution failed, port blocked | Firewall, servicos ativos, portas |
| **Criptografia / SSL** | Certificate expired, handshake failed, cipher mismatch | Certificados .pem/.pfx, configuracao SSL no .ini |
| **RPO** | RPO corrompido, funcao duplicada, patch incompativel | Versao do RPO, ultimo patch aplicado, rebuild |
| **Job/Schedule** | Job nao executou, onstart failed, schedule travado | appserver.ini [ONSTART], logs de agendamento |
| **Impressao** | Impressora nao encontrada, spool cheio, PDF generation error | Configuracao de impressoras, servico de spool |
| **Integracao** | WebService timeout, EDI falha, API terceiros erro | Endpoints configurados, logs de integracao |
| **Performance** | Lentidao, query lenta, indice missing, cache cheio | Indices SIX, plano de execucao SQL, TopMem |
| **Fiscal/SPED** | Validacao fiscal falhou, XML rejeitado, SPED inconsistente | Regras fiscais, TES (SF4), NCM, CFOP |
| **Backup/Recovery** | Backup falhou, restore incompleto, snapshot erro | Agendamento de backup, espaco em disco |

### Dica de diagnostico com base TDN
Ao encontrar um erro desconhecido, busque na base TDN indexada (`search_knowledge` com a mensagem de erro) antes de responder. A base contem 10.307 itens entre funcoes, classes e documentacao tecnica que podem conter a solucao ou workaround oficial da TOTVS.
