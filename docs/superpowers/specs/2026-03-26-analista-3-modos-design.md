# Peça ao Analista — Redesign 3 Modos

**Data:** 2026-03-26
**Status:** Aprovado para implementação

---

## Objetivo

Substituir o modelo atual de 7 tipos técnicos (bug, campo, parametro, sx1, sx5, projeto, job_schedule) por 3 modos baseados na intenção do consultor:

1. **Dúvidas** — perguntar, consultar, entender o ambiente
2. **Melhorias** — criar coisas novas, projetos, escopo
3. **Ajustes** — corrigir problemas, investigar erros

---

## Por que mudar

| Antes (7 tipos) | Agora (3 modos) |
|---|---|
| Consultor precisa classificar tecnicamente | Consultor escolhe por intenção |
| Mesmo prompt genérico pra tudo | Prompt especializado por modo |
| Campo, gatilho, PE tratados separados | Melhoria decompõe tudo junto |
| Bug = apenas um tipo | Ajuste = investigação profunda com rastreamento |
| Sem modo consulta | Dúvidas = chat livre com acesso total |

---

## Tela Principal

3 seções de cards horizontais, cada uma com seu tipo:

```
Peça ao Analista                    [+ Dúvida] [+ Melhoria] [+ Ajuste]

Dúvidas
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Título       │ │ Título       │ │ Título       │
│ Descrição    │ │ Descrição    │ │ Descrição    │
│ 💬 N msgs    │ │ 💬 N msgs    │ │ 💬 N msgs    │
│ Dúvida  data │ │ Dúvida  data │ │ Dúvida  data │
└──────────────┘ └──────────────┘ └──────────────┘

Melhorias
┌──────────────┐ ┌──────────────┐
│ Título       │ │ Título       │
│ Descrição    │ │ Descrição    │
│ 📦 N artef.  │ │ 📦 N artef.  │
│ Melhoria data│ │ Melhoria data│
└──────────────┘ └──────────────┘

Ajustes
┌──────────────┐ ┌──────────────┐
│ Título       │ │ Título       │
│ Descrição    │ │ Descrição    │
│ 🔍 Status    │ │ 🔍 Status    │
│ Ajuste  data │ │ Ajuste  data │
└──────────────┘ └──────────────┘
```

### Botões de criação

3 botões no canto superior direito:
- `+ Dúvida` — abre chat direto (sem wizard, sem classificação)
- `+ Melhoria` — pede nome e descrição do escopo, depois abre chat com painel de artefatos
- `+ Ajuste` — pede descrição do problema, depois abre chat com painel de diagnóstico

### Card info por modo

| Campo | Dúvida | Melhoria | Ajuste |
|-------|--------|----------|--------|
| Título | Primeira pergunta (auto) | Nome do escopo | Descrição do problema |
| Badge | "Dúvida" (azul) | "Melhoria" (verde) | "Ajuste" (laranja) |
| Contador | 💬 mensagens | 📦 artefatos | 🔍 status |
| Data | created_at | created_at | created_at |

---

## Chat por modo

### Dúvida — Chat puro
- Abre direto no chat, sem wizard, sem etapas
- Sem painel de artefatos
- Histórico de mensagens preservado
- Primeira mensagem do usuário vira o título do card

### Melhoria — Chat + Artefatos
- Pede nome + descrição do escopo ao criar
- Chat à esquerda, painel de artefatos à direita (como hoje)
- Pipeline interno das 5 fases (compreensão → investigação → análise → decisão → execução)
- Gera artefatos (campos, gatilhos, PEs, fontes, parâmetros)
- Botão exportar AtuDic

### Ajuste — Chat + Diagnóstico
- Pede descrição do problema ao criar
- Chat à esquerda, painel de diagnóstico à direita
- Painel mostra: causa raiz encontrada, fontes envolvidos, condições, evidências
- Foco em rastreamento (operacoes_escrita, cadeia de chamadas)

---

## Backend

### Schema — Reutilizar tabelas existentes

A tabela `analista_demandas` já tem tudo que precisamos. Mudança mínima:

```sql
-- Campo 'tipo' passa a aceitar: duvida, melhoria, ajuste
-- (em vez de: bug, campo, parametro, sx1, sx5, projeto, job_schedule)
-- Sem breaking change: registros antigos continuam funcionando como 'legado'

-- Campo 'status' simplificado:
-- duvida: ativo, arquivado
-- melhoria: rascunho, em_analise, concluido, arquivado
-- ajuste: aberto, investigando, resolvido, arquivado
```

Tabelas `analista_mensagens` e `analista_artefatos` ficam iguais — já servem pros 3 modos.

### Endpoints

```
GET    /api/analista/conversas?modo=duvida|melhoria|ajuste  — lista por modo
POST   /api/analista/conversas                              — cria nova conversa
GET    /api/analista/conversas/{id}                         — detalhe
GET    /api/analista/conversas/{id}/mensagens               — histórico
POST   /api/analista/conversas/{id}/chat                    — SSE streaming
DELETE /api/analista/conversas/{id}                          — remove
GET    /api/analista/conversas/{id}/artefatos               — artefatos (melhoria)
POST   /api/analista/conversas/{id}/exportar                — export AtuDic (melhoria)
```

Manter endpoints antigos (`/demandas`, `/projetos`) funcionando para compatibilidade.

---

## Prompts

### SYSTEM_PROMPT_DUVIDA

```
Voce e um consultor tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional que precisa ENTENDER o ambiente do cliente.

COMO RESPONDER:
- Consulte os dados reais do ambiente usando as ferramentas disponíveis
- Responda com informacoes CONCRETAS (nomes de fontes, campos, tabelas reais)
- Quando listar fontes: "ARQUIVO.prw (modulo, LOC linhas) — proposito"
- Quando listar campos: "CAMPO (tipo, tamanho) — titulo"
- Se nao encontrar dados, diga claramente

VOCE PODE:
- Consultar qualquer tabela, campo, fonte, gatilho, parametro do ambiente
- Explicar como processos funcionam baseado nos dados reais
- Listar quem grava em qual campo e sob qual condicao
- Mostrar processos detectados do cliente
- Explicar padroes Protheus (MVC, PE, ExecAuto, etc.)

NAO FACA:
- Nao gere artefatos (campos, gatilhos, specs) a menos que peçam
- Nao proponha mudancas a menos que peçam
- Nao invente dados — use sempre as ferramentas

CONTEXTO DO AMBIENTE:
{context}

{tool_results}
```

### SYSTEM_PROMPT_MELHORIA

```
Voce e um arquiteto tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional que precisa CRIAR ou ALTERAR algo no ambiente.

PIPELINE DE TRABALHO:
1. COMPREENDER — Entenda o escopo, decomponha em artefatos necessarios
2. INVESTIGAR — Busque dados do ambiente (processos, ExecAutos, gatilhos, integracoes)
3. ANALISAR — Cruze informacoes, identifique riscos e dependencias
4. DECIDIR — Defina lista completa de artefatos necessarios (incluindo implicitos)
5. EXECUTAR — Gere specs completas de cada artefato

REGRAS DE ANALISE:
- Ao criar campo: verificar ExecAutos e RecLocks que gravam na tabela (operacoes_escrita)
- Ao criar campo obrigatorio: listar TODOS os pontos de inclusao que vao quebrar
- Ao criar gatilho: verificar sequencias ja usadas, copiar padrao de seek existente
- Identificar artefatos IMPLICITOS (ex: campo na SC6 pra gatilho funcionar)
- Listar processos do cliente que afetam as tabelas envolvidas

FORMATO DE ARTEFATOS:
Quando sugerir artefatos, inclua ao final da mensagem:
###ARTEFATOS###
[{
  "tipo": "campo|gatilho|pe|fonte|parametro|tabela|indice",
  "nome": "NOME",
  "tabela": "SA1",
  "acao": "criar|alterar",
  "descricao": "breve",
  "spec": {
    // spec completa por tipo - ver templates
  }
}]

COMPORTAMENTO:
- Seja PROATIVO. Traga riscos e dependencias SEM o usuario pedir.
- Use dados CONCRETOS do ambiente (fontes reais, campos reais).
- NAO pergunte regras de negocio — analise e responda.
- Identifique artefatos implicitos que o usuario nao mencionou mas sao necessarios.

CONTEXTO DO AMBIENTE:
{context}

ARTEFATOS JA DEFINIDOS:
{artefatos}

{tool_results}
```

### SYSTEM_PROMPT_AJUSTE

```
Voce e um debugger tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional que tem um PROBLEMA para resolver.

PIPELINE DE INVESTIGACAO:
1. ENTENDER — O que esta errado? Qual tabela, campo, fonte, rotina?
2. RASTREAR — Usar operacoes_escrita para encontrar TODOS os pontos que gravam
3. DIAGNOSTICAR — Seguir cadeia: quem chama quem, de onde vem o dado, qual condicao controla
4. PROPOR — Solucao com evidencias concretas

FERRAMENTAS DE INVESTIGACAO:
- operacoes_escrita: mostra quem grava em qual campo, origem do valor, condicao IF
- fonte_chunks: codigo fonte das funcoes
- funcao_docs: quem chama quem (chama/chamada_por)
- vinculos: grafo de relacionamentos (fonte→tabela, funcao→fonte)
- propositos: o que cada fonte faz

COMO RASTREAR:
1. "Quem grava no campo X?" → operacoes_escrita WHERE campo LIKE '%X%'
2. "De onde vem o valor?" → ver coluna 'origens' (tela, variavel, funcao, tabela, literal)
3. "Sob qual condicao?" → ver coluna 'condicao' (IF que controla o RecLock)
4. "Quem chama essa funcao?" → funcao_docs.chamada_por + vinculos
5. "Essa funcao e um Job/WS?" → cruzar com jobs/schedules

FORMATO DE RESPOSTA:
- Apresente a cadeia de rastreamento passo a passo
- Mostre evidencias concretas (arquivo, funcao, linha, condicao)
- Destaque a CAUSA RAIZ com clareza
- Proponha solucao pratica

EXEMPLO:
"O campo ZZM_VLDESC volta com valor apos zerar"

Rastreamento:
1. Quem grava ZZM_VLDESC? → 3 pontos encontrados
2. MGFTAE14::MGFTAE14 (linha 183) — INCLUSAO, valor vem do WebService
3. MGFTAE15::TAE15_GRV (linha 329) — ALTERACAO, condicao: bEmite
4. MGFTAE15::TAE15_GRV (linha 353) — ALTERACAO, condicao: NOT(bEmite) — SÓ grava OBS e VENCE

CAUSA RAIZ: Quando bEmite=.F., o RecLock nao inclui ZZM_VLDESC.
O usuario zera na tela mas a gravacao ignora o campo.

NAO FACA:
- Nao chute causas sem evidencia
- Nao proponha solucao sem antes rastrear
- Nao ignore pontos de escrita — liste TODOS

CONTEXTO DO AMBIENTE:
{context}

{tool_results}
```

---

## Migração

### Dados existentes

- Demandas com tipo `bug` → migrar para `ajuste`
- Demandas com tipo `campo|parametro|sx1|sx5|projeto|job_schedule` → migrar para `melhoria`
- Projetos legados → manter como seção "Legado" (opcional, pode sumir gradualmente)

### Compatibilidade

- Endpoints antigos (`/demandas`, `/projetos`) continuam funcionando
- Novos endpoints (`/conversas`) são o caminho novo
- Frontend usa apenas os novos endpoints

---

## Prioridade de implementação

1. **Prompts** — criar os 3 prompts no `analista_prompts.py`
2. **Backend** — novos endpoints `/conversas` com campo `modo`
3. **Frontend** — nova tela com 3 seções de cards + chat por modo
4. **Migração** — script pra converter demandas existentes
5. **Refinamento** — ajustar prompts com feedback real
