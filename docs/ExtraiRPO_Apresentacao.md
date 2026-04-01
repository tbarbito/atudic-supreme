# ExtraiRPO — Plataforma de Engenharia Reversa para TOTVS Protheus

> Ferramenta de análise, documentação e consultoria para ambientes Protheus customizados.
> Desenvolvida com FastAPI + Vue 3 + PrimeVue + SQLite + LLM (Claude/GPT)

---

## O Problema

Quando um consultor Protheus chega num cliente, ele encontra:
- Milhares de tabelas, campos, gatilhos e índices customizados
- Centenas de fontes .prw sem documentação
- Nenhuma visão clara do que foi alterado vs o que é padrão
- Risco de quebrar integrações ao fazer qualquer alteração

**ExtraiRPO resolve isso** — em minutos, não semanas.

---

## Como Funciona

```
CSVs das SXs + Fontes .prw + CSVs Padrão
              ↓
    ┌─────────────────────┐
    │   INGESTÃO (3s)     │  Parser memory-safe, 44MB RAM máx
    │   1987 fontes       │  187K campos, 26K índices, 18K gatilhos
    └────────┬────────────┘
             ↓
    ┌─────────────────────┐
    │   DIFF AUTOMÁTICO   │  Compara padrão × cliente campo a campo
    │   31.768 diferenças │  13K adicionados, 16K alterados
    └────────┬────────────┘
             ↓
    ┌─────────────────────┐
    │   EXPLORER          │  Árvore interativa com drill-down
    │   Análise de Impacto│  Identifica riscos antes de alterar
    │   Resumos por IA    │  Documenta funções automaticamente
    └─────────────────────┘
```

---

## Funcionalidades

### 1. Ingestão de Dados

| Fonte de Dados | O que extrai | Registros |
|---|---|---|
| SX2 (tabelas) | Nome, modo, módulo | 11.264 |
| SX3 (campos) | Tipo, tamanho, validação, F3, VLDUSER, obrigatório | 187.633 |
| SIX (índices) | Chave, descrição, proprietário | 26.486 |
| SX7 (gatilhos) | Regra, condição, alias, proprietário | 18.051 |
| SX6 (parâmetros) | Valor, descrição, proprietário | 18.435 |
| SX9 (relacionamentos) | Expressões entre tabelas | 25.930 |
| Fontes .prw/.tlpp | Funções, tabelas, campos, call graph | 1.987 arquivos |
| Menus (mpmenu) | Módulo → rotina → nome → caminho | 45.023 itens |
| Record counts | Registros por tabela (filtrado BKP/TMP) | 923 tabelas |
| SXs padrão | Base de referência para comparação | 174.358 campos |

**Performance:** 1.987 fontes parseados em 2.8 segundos, 44MB de RAM máxima. Técnica de commit por arquivo + gc.collect + fast path encoding (cp1252).

---

### 2. Explorer — Navegação Interativa

Interface em 3 colunas: Filtros | Árvore | Detalhe

**Árvore lazy por módulo:**
- Carga inicial instantânea (só módulos)
- Expande sob demanda (~0.5s por módulo)
- Cache de navegação (segunda visita = instantâneo)

**Dentro de cada módulo:**
- Tabelas (com badges: +adicionados, ~alterados, score)
- Pontos de Entrada
- Itens de Menu (classificados padrão/custom/ambos)
- Fontes Custom

**Detalhe de Tabela (5 abas):**

| Aba | Conteúdo |
|---|---|
| Campos | Status colorido (azul=padrão, laranja=adicionado, amarelo=alterado), filtro, legenda |
| Gatilhos | Regra, condição, flag custom |
| Índices | Chave, descrição, flag custom |
| Fontes | Lista de programas que leem/escrevem com modo, funções, LOC, propósito |
| Diff | Comparação campo a campo: padrão vs cliente |

**Detalhe de Fonte:**
- Overview do programa (gerado por IA, formato estruturado)
- Lista de funções com assinatura e resumo
- Expansão: tabelas, call graph (chama/chamada por), retorno, impacto
- Código completo da função (carregado do .prw sob demanda)
- "Resumir Todas" — 5 funções em paralelo via IA
- "Overview do Programa" — resume funções → gera overview consolidado

---

### 3. Diff Padrão × Cliente

Compara **campo a campo** entre as SXs padrão e do cliente:

| Métrica | Quantidade |
|---|---|
| Campos adicionados pelo cliente | 13.278 |
| Campos alterados (validação, tamanho, tipo) | 16.694 |
| Campos removidos | 3 |
| Gatilhos adicionados | 1.713 |
| Gatilhos removidos | 80 |

**Sem depender de X3_PROPRI** — o diff é 100% preciso porque compara registro a registro.

Cada campo alterado mostra **exatamente o que mudou**: validação, tamanho, tipo, com o valor padrão e o valor do cliente lado a lado.

---

### 4. Análise de Impacto

Antes de alterar um campo, o consultor roda a análise:

```
ENTRADA: "Tornar A2_CGC obrigatório na SA2"

RESULTADO:
  Risco: ALTO
  18 fontes gravam SA2
  3 integrações em risco (MsExecAuto/WebService)
  6 fontes médio risco (gravam e referenciam o campo)
  9 gatilhos relacionados

  FONTES EM RISCO:
  🔴 MGFINT02.PRW — Integração que grava SA2 e referencia A2_CGC
  🔴 MGFWSS24.PRW — WebService que grava SA2 sem preencher A2_CGC
  🟡 MGFCOM08.prw — Grava SA2 e referencia A2_CGC
  🟢 AGRMATR.prw — Só leitura, sem impacto
```

Detecta automaticamente:
- Integrações (MsExecAuto, WebService, API)
- Fontes que escrevem vs leem
- Se o campo é referenciado no código
- Gatilhos que preenchem o campo
- Classificação de risco: alto/médio/baixo

**Exporta como markdown** para documentar a análise.

---

### 5. Resumos por IA (Estruturados)

Cada função e programa documentado com formato duplo:

**Para humanos:**
> "O programa MGFCOM08 gerencia pedidos de compra com validação de alçada, filtro de produtos por grupo e integração com workflow de aprovação."

**Para agentes IA:**
```json
{
  "processo": "pedido_compras",
  "tipo_programa": "tela_cadastro",
  "tabelas_escrita": ["SC7", "SC1", "SCR"],
  "funcionalidades": ["validação de alçada", "filtro por grupo", "integração workflow"],
  "complexidade": "alta",
  "fluxo_resumido": "SC1 → cotação → SC7 → aprovação → NF"
}
```

**8.522 funções** documentadas com:
- Assinatura (nome + parâmetros)
- Tabelas referenciadas
- Call graph (chama / chamada por)
- Resumo de negócio
- Tipo de retorno

**Incremental:** cada uso enriquece o catálogo. Da próxima vez, é instantâneo.

---

### 6. Base Padrão

**6 módulos** documentados em template de 14 seções:
- SIGACOM (Compras), SIGAFAT (Faturamento), SIGAFIN (Financeiro)
- SIGAEST (Estoque), SIGAFIS (Fiscal), SIGACTB (Contabilidade)

Cada módulo com: objetivo, parametrização geral, cadastros, rotinas (com MV_, PEs, fluxo Mermaid), contabilização, tabelas, fluxo geral, integrações.

**"Pergunte ao Padrão":** campo de pergunta que pesquisa no TDN + Web, e adiciona a resposta diretamente no markdown do módulo, na seção correta.

**457 Pontos de Entrada** catalogados com:
- PARAMIXB detalhados (tipo e descrição por posição)
- Retorno (tipo e significado)
- Onde é chamado, objetivo, módulo, rotina
- Busca automática no TDN via Playwright (browser headless)
- CRUD: editar, excluir, pesquisar/atualizar

---

### 7. Catálogo de Menus

| Dados | Padrão | Cliente |
|---|---|---|
| Módulos | 68 | 366 |
| Rotinas | 2.872 | 7.931 |
| Em ambos | — | 2.222 |
| Exclusivas do cliente | — | 5.709 |

Cada rotina classificada como **padrão**, **custom** ou **ambos**. O consultor sabe instantaneamente o que é do Protheus e o que foi criado pelo cliente.

---

### 8. TDN Scraper

Ferramenta que usa **Playwright** (browser headless) para:
1. Buscar um PE no Google
2. Encontrar o link do TDN
3. Abrir a página (contorna o bloqueio 403)
4. Extrair PARAMIXB, retorno, descrição completa
5. Salvar no catálogo automaticamente

Funciona com formato novo e antigo do TDN. Integrado na interface (botão "lupinha" nos PEs).

---

## Stack Técnica

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Frontend | Vue 3 + PrimeVue (tema TOTVS) |
| Banco | SQLite (~107MB) |
| LLM | LiteLLM (Claude Sonnet + GPT-4.1) |
| Scraper | Playwright (Chromium headless) |
| Markdown | markdown-it + Mermaid.js |
| Vector DB | ChromaDB (busca semântica) |

---

## Números do Banco de Dados

| Tabela | Registros | Descrição |
|---|---|---|
| tabelas | 11.264 | Dicionário SX2 |
| campos | 187.633 | Dicionário SX3 |
| indices | 26.486 | Índices SIX |
| gatilhos | 18.051 | Gatilhos SX7 |
| parametros | 18.435 | Parâmetros SX6 |
| fontes | 1.987 | Programas .prw/.tlpp |
| fonte_chunks | 8.555 | Código por função |
| funcao_docs | 8.522 | Documentação de funções |
| vinculos | 19.637 | Conexões campo→função→rotina |
| menus | 45.023 | Menu do cliente |
| padrao_menus | 2.872 | Menu padrão |
| padrao_campos | 174.358 | SX3 padrão |
| padrao_pes | 457 | PEs catalogados |
| diff | 31.768 | Diferenças padrão × cliente |
| record_counts | 923 | Registros por tabela |
| propositos | ~50 | Overviews de programas |

**Total: ~107MB** (SQLite único, portátil)

---

## Casos de Uso

### Consultor chega no cliente
1. Importa CSVs + fontes (3 segundos)
2. Abre Explorer → vê toda a estrutura organizada por módulo
3. Navega: tabelas, campos, gatilhos, fontes, menus
4. Compara com padrão: o que foi adicionado, alterado, removido

### Cliente pede uma alteração
1. Abre Análise de Impacto
2. Seleciona campo e tipo de alteração
3. Sistema identifica todos os fontes em risco
4. Consultor sabe exatamente o que verificar antes de mexer

### Documentar processo customizado
1. Seleciona os fontes do processo
2. "Resumir Todas" → IA documenta cada função
3. "Overview do Programa" → resumo consolidado
4. Tudo salvo e reutilizável

### Pesquisar informação do padrão
1. "Pergunte ao Padrão" → pesquisa TDN + Web
2. Resultado adicionado no markdown do módulo
3. Da próxima vez, a informação já está lá

---

## Roadmap

- [ ] Classificação automática (IA barata) das top 50 tabelas/fontes
- [ ] Template de Projeto (gap analysis: padrão + cliente → spec)
- [ ] Geração de fluxo Mermaid do processo customizado
- [ ] Dashboard com métricas do cliente
- [ ] Multi-cliente (comparar customizações entre clientes)
- [ ] Exportação de documentação completa (PDF/Word)

---

> Desenvolvido com Claude Opus 4.6 + Claude Code
> Stack: Python + FastAPI + Vue 3 + PrimeVue + SQLite + LiteLLM + Playwright
