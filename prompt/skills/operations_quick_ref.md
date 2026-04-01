---
name: operations_quick_ref
description: Mapa de decisao de tools — qual ferramenta usar para cada situacao
intents: []
keywords: []
priority: 98
always_load: true
max_tokens: 400
specialist: "all"
---

## MAPA DE DECISAO DE TOOLS (use SEMPRE como referencia)

| Pedido do usuario | Tool correta | NAO usar |
|---|---|---|
| "compara dicionario HML x PRD" | `compare_dictionary` (conn_id_a, conn_id_b) | query_database |
| "compara SX3 entre bancos" | `compare_dictionary` (tables: ["SX3"]) | query_database |
| "conteudo do MV_ESTNEG" | `query_database` template=parametro | SQL bruto |
| "parametros de Compras" | `query_database` template=parametros_modulo | get_db_connections |
| "campos da SA1" | `query_database` template=campos_tabela | SQL bruto |
| "equaliza campo X de HML→PRD" | `equalize_field` (field_name, source=HML, target=PRD) | preview_equalization |
| "erro ORA-12154 no log" | `get_alerts` → `get_recurring_errors` → `search_knowledge` | query_database |
| "roda pipeline de deploy" | `get_pipelines` → `run_pipeline` | — |
| "status dos servicos" | `get_services` | get_pipelines |
| "cria release" | `get_pipeline_status` → `create_release` (confirmacao) | — |
| "analisa impacto do campo X" | `analyze_impact` → `list_vinculos` | query_database |
| "como configurar broker" | `search_tdn` (query: "configurar broker webservice") | search_knowledge |
| "funcao MsExecAuto" | `search_tdn` (query: "MsExecAuto", source: "protheus12") | search_knowledge |
| "como incluir pedido" | `search_tdn` (query: "incluir pedido venda MATA410") | query_database |
| "erro ORA-12154" | `search_knowledge` (KB erros) + `search_tdn` (config Oracle) | — |
| "visao geral" | `get_system_overview` | get_environments |

### REGRA — search_tdn vs search_knowledge
- `search_tdn`: documentacao oficial TDN — funcoes, configuracoes, APIs, procedures, como fazer
- `search_knowledge`: KB interna de erros — diagnostico, solucoes de erros conhecidos
- Na duvida, use AMBAS. Sao complementares.

### REGRA DE OURO — Conexoes
- As conexoes de banco estao listadas no contexto com IDs. USE-OS DIRETAMENTE.
- Se o usuario diz "HML" ou "PRD", resolva pelo nome da conexao no contexto.
- Se so existem 2 conexoes, use: primeira=A, segunda=B.
- NUNCA chame `get_db_connections` se as conexoes ja estao no contexto.

### CHAINS — Sequencias automaticas
| Trigger | Sequencia |
|---|---|
| Diagnostico de erro | get_alerts → get_recurring_errors → search_knowledge |
| Saude do ambiente | get_services → get_alert_summary → get_db_connections |
| Comparar e equalizar | compare_dictionary → preview_equalization → execute_equalization |
