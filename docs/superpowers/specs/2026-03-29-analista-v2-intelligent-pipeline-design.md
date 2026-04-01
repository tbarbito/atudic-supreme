# Analista V2 — Pipeline Inteligente de Investigação

## Resumo

Redesign do pipeline do "Peça ao Analista" para substituir o modelo atual de "busca tudo de uma vez" por um pipeline de 5 fases: Compreensão → Resolução Semântica → Decisão de Rota → Investigação Iterativa → Resposta/Código.

## Motivação

O pipeline atual tem limitações fundamentais:

1. **Resolução por sinônimos hardcoded** — apenas ~15 termos mapeados; termos como "distribuição" (que é rateio) não são encontrados
2. **Busca tudo para todas as tabelas** — se acha SC5 e SC6, puxa impacto, operações, PEs, parâmetros de AMBAS mesmo que o problema seja só na SC6
3. **Contexto cortado em 8000 chars** — informação crítica pode ser perdida
4. **LLM não pode pedir mais dados** — uma chamada única, sem iteração
5. **Não consulta padrao.db** — ignora 24.906 fontes padrão com 13.908 PEs
6. **Não lê código real** — não pode diagnosticar bugs em fonte nem gerar correções

## Arquitetura: 5 Fases

### Fase 1 — Compreensão (sem LLM pesado)

**Input:** Mensagem do usuário em linguagem natural
**Output:** `{tipo, ação, termos, entidades_explícitas}`

O classificador existente (LLM leve + regex) se mantém. Detecta tipo (bug, campo, projeto), ação (não_salva, erro, etc.) e extrai entidades explícitas (tabelas, campos, parâmetros mencionados diretamente).

**Sem mudança significativa nesta fase.**

### Fase 2 — Resolução Semântica (NOVO)

**Input:** `{termos, entidades_explícitas}` da Fase 1
**Output:** Lista de candidatos com confiança: `[{tabela, campo, rotina, fontes, confiança, descrição}]`

Quando o usuário NÃO menciona entidades explícitas (ex: "problema na aprovação do pedido"), o sistema busca candidatos em 5 fontes de dados do ambiente do cliente:

1. **Menus** — busca textual em `menus.nome` e `menus.menu` (43.934 menus)
2. **Propósitos dos fontes** — busca semântica nos 8.766 propósitos gerados por IA
3. **Processos detectados** — match nos processos catalogados
4. **Campos por título/descrição** — busca em `campos.titulo` e `campos.descricao`
5. **Padrão (padrao.db)** — rotinas padrão conhecidas por nome/módulo

Cada fonte retorna candidatos com score. Candidatos de fontes diferentes que apontam para a mesma tabela/rotina ganham boost de confiança.

**Substitui o `SINONIMOS` dict hardcoded por busca real nos dados.**

### Fase 3 — Decisão de Rota

**Input:** Lista de candidatos da Fase 2
**Output:** Uma das 3 decisões:

- **1 candidato claro** (confiança > 0.8) → Segue direto para investigação
- **N candidatos** → Pergunta inteligente mostrando opções reais do ambiente:
  ```
  "Encontrei 3 processos de aprovação no seu ambiente:
   1. Motor de Regras (FATA210) — bloqueio automático por critério
   2. Workflow Fluig (MGFCOM10) — aprovação por alçada
   3. Liberação manual (MATA440)
   Qual desses?"
  ```
- **0 candidatos** → Pergunta aberta com sugestões contextuais

**Substitui o `avaliar_ambiguidade` que agrupa por blocos de escrita, por uma decisão baseada nos candidatos semânticos.** O avaliar_ambiguidade atual pode ser mantido como fallback quando a resolução semântica encontra tabelas mas muitos caminhos dentro da mesma tabela.

### Fase 4 — Investigação Iterativa (NOVO)

**Input:** Entidades confirmadas (tabela, campo, rotina, fontes)
**Output:** Contexto acumulado com evidências

O LLM recebe contexto mínimo inicial e pode solicitar ferramentas específicas em um loop (max 5 passos):

```
Loop:
  LLM analisa contexto atual
  LLM decide: {tool: "operacoes_escrita", args: {tabela: "SC6", campo: "C6_DESCONT"}}
  Sistema executa tool, retorna resultado
  Contexto acumula APENAS o resultado pedido
  LLM decide: precisa de mais? → continua loop
                pronto? → sai do loop
```

**Ferramentas disponíveis no loop:**

| Tool | Fonte | Quando usar |
|------|-------|-------------|
| `quem_grava(tab, campo)` | cliente | Investigar pontos de escrita |
| `rastrear_condicao(arq, func, var)` | cliente | Seguir cadeia de condições |
| `ver_parametro(nome)` | cliente | Consultar valor de parâmetro |
| `ver_fonte_cliente(arq, func)` | cliente | Ler código real do chunk |
| `info_tabela(tab)` | cliente | Metadata básica |
| `buscar_pes_cliente(rotina)` | cliente | PEs implementados |
| `mapear_processo(tab, campo)` | cliente | Varredura completa do ecossistema |
| `fonte_padrao(arquivo)` | padrão | Entender rotina padrão |
| `pes_disponiveis(rotina)` | padrão | PEs com parâmetros reais |
| `codigo_pe(nome_pe)` | padrão | Trecho do fonte onde PE é chamado |
| `buscar_funcao_padrao(nome)` | padrão | Assinatura e contexto da função |
| `pronto` | — | Sai do loop, gera resposta |

**Implementação técnica:** O loop usa LLM com function calling (ou prompt estruturado que retorna JSON com tool_call). Cada iteração é uma chamada ao LLM com contexto acumulado. O frontend mostra status de cada passo via SSE.

**Nota sobre `mapear_processo`:** Esta ferramenta já existe e faz varredura completa (estados, campos companheiros, tabelas satélite, fontes no fluxo). No modelo iterativo, o LLM pode invocá-la quando percebe que o problema é complexo — ela retorna o ecossistema completo de uma vez. Isso é intencional: processos complexos precisam da visão completa.

### Fase 5 — Resposta (ou Especialista em Código)

**Input:** Contexto acumulado da investigação
**Output:** Resposta ao usuário OU código ADVPL

Se o problema é de dados/configuração → resposta direta (como hoje, com Resumo Executivo + Análise Técnica).

Se precisa mexer em código → invoca o **Especialista em Código** como ferramenta adicional:

```
Dossiê para o Especialista:
- Rotina, fonte, função, diagnóstico
- Chunks relevantes (cliente + padrão)
- Docs ADVPL aplicáveis (do skill)
- Exemplos de código (few-shot)

Especialista retorna:
- Código ADVPL gerado/corrigido
- Artefato tipo "fonte" salvo no projeto
```

O Especialista em Código é um serviço com prompt especializado (system prompt dedicado com conhecimento ADVPL dos docs da skill). Não é um 4o modo do analista — é uma ferramenta que os modos melhoria e ajuste podem invocar.

---

## Pool de Ferramentas Unificado

### Ferramentas do Cliente (extrairpo.db) — existentes

- `tool_info_tabela(tabela)` — metadata básica
- `tool_analise_impacto(tabela, campo, alteracao)` — impacto completo
- `tool_operacoes_tabela(tabela)` — resumo de operações
- `tool_quem_grava_campo(tabela, campo)` — pontos de escrita por campo
- `tool_investigar_condicao(arquivo, funcao, variavel)` — backward trace
- `tool_buscar_pes(rotina, modulo)` — PEs do catálogo
- `tool_buscar_fontes_tabela(tabela, modo)` — fontes por tabela
- `tool_buscar_parametros(termo, tabela)` — parâmetros SX6
- `tool_buscar_perguntas(grupo, termo)` — perguntas SX1
- `tool_buscar_tabela_generica(tabela, termo)` — SX5
- `tool_buscar_jobs(rotina, arquivo_ini)` — jobs
- `tool_buscar_schedules(rotina, status, codigo)` — schedules
- `tool_mapear_processo(tabela, campo)` — varredura de processo
- `tool_processos_cliente(tabelas)` — processos detectados
- `tool_registrar_processo(...)` — registrar processo novo

### Ferramentas do Cliente — NOVAS

- `tool_buscar_menus(termo)` — busca em menus por texto
- `tool_buscar_propositos(termo)` — busca em propósitos dos fontes
- `tool_ler_fonte_cliente(arquivo, funcao)` — lê chunk de código real

### Ferramentas do Padrão (padrao.db) — NOVAS

- `tool_fonte_padrao(arquivo)` — metadata + funções do fonte padrão
- `tool_pes_disponiveis(rotina)` — ExecBlocks com parâmetros reais
- `tool_codigo_pe(nome_pe)` — trecho do fonte onde PE é chamado
- `tool_buscar_funcao_padrao(nome)` — busca funções no padrão

### Especialista em Código — NOVO

- `tool_analisar_fonte(codigo, problema)` — diagnóstico profundo de código
- `tool_gerar_correcao(codigo, diagnostico)` — gerar fix
- `tool_gerar_fonte(spec, tipo)` — gerar fonte novo (PE, User Function, MVC)

---

## Mudanças no Frontend

O frontend já suporta SSE com eventos `status`, `token`, `done`. A mudança principal é que a fase de investigação iterativa emite mais eventos de status:

```
event: status  → "Classificando sua pergunta..."
event: status  → "Buscando no ambiente do cliente..."
event: status  → "Encontrei 3 possibilidades, perguntando..."
  (ou)
event: status  → "Investigando operações de escrita na SC6..."
event: status  → "Rastreando condição bEmite..."
event: status  → "Consultando parâmetro MGF_TAE15A..."
event: status  → "Gerando resposta..."
event: token   → streaming da resposta
event: done    → fim
```

**Sem mudança estrutural no frontend.** Os novos status messages aparecem naturalmente.

---

## Compatibilidade

- Os 3 modos (dúvida, melhoria, ajuste) se mantêm
- Os system prompts por modo se mantêm
- O sistema de artefatos do melhoria se mantém
- O fluxo de follow-up (mensagens subsequentes) se mantém
- Toda a base de dados existente (extrairpo.db) se mantém intacta

As mudanças são:
1. Novo módulo `semantic_resolver.py` para Fase 2
2. Novo módulo `padrao_tools.py` para ferramentas do padrão
3. Novo módulo `code_specialist.py` para o especialista em código
4. Refatoração do trecho de investigação em `analista.py` para loop iterativo
5. Novas ferramentas em `analista_tools.py`

---

## Fora de Escopo (V2)

- Mudanças no frontend além de status messages
- Mudanças no sistema de artefatos
- Mudanças na criação/listagem de conversas
- Geração de documentação (doc_pipeline)
- Explorer view
- Ingestão de dados
