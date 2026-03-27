# Dashboard Redesign Plan — AtuDIC Command Center

> **Data:** 2026-03-19
> **Autor:** TobIAs + Barbito
> **Status:** Aguardando aprovacao

---

## 1. Diagnostico do Estado Atual

### 1.1 Layout Atual (Descricao Visual)

```
+------------------------------------------------------------------+
| HEADER: AtuDIC logo | Nav tabs | Ambiente selector | User menu   |
+------------------------------------------------------------------+
| Dashboard (titulo)          | "Atualizado agora" | [Atualizar]   |
| Visao geral do ambiente: Homologacao                              |
+------------------------------------------------------------------+
| [badge] Exibindo dados de Windows 10 Pro                          |
+------------------------------------------------------------------+
| Quick Actions (admin/operator only):                              |
| [Executar Pipeline] [Comandos] [Repositorios] [Agendamentos]     |
| [Configuracoes]                                                   |
+------------------------------------------------------------------+
| GRID: 5 cards iguais (auto-fit, minmax 280px)                     |
|                                                                   |
| +-------------+ +-------------+ +-------------+ +-------------+  |
| | 9            | | 5            | | 6            | | 2            |  |
| | Execucoes    | | Releases     | | Pipelines    | | Acoes de     |  |
| | de Pipeline  | | (Deploys)    | | Configuradas | | Servico      |  |
| |   [play]     | |   [rocket]   | |   [cogs]     | |   [server]   |  |
| | ---bar 89%-- | | ---bar 100%- | | 3 COMANDOS   | | 0 ATIVAS     |  |
| | 8  1  0      | | 5  0         | |              | |              |  |
| | SUC FAL EXE  | | SUC FAL      | |              | |              |  |
| +-------------+ +-------------+ +-------------+ +-------------+  |
|                                                                   |
| +-------------+                                                   |
| | 6            |                                                   |
| | Alertas      |                                                   |
| | Criticos     |                                                   |
| | Pendentes    |                                                   |
| |   [satellite]|                                                   |
| | 6  0  0  0   |                                                   |
| | CRI WAR INF  |                                                   |
| +-------------+                                                   |
+------------------------------------------------------------------+
| Repositorios GitHub                          [Ver todos]          |
| protheus  [HOMOLOG] [MASTER]                        (2)           |
+------------------------------------------------------------------+
| Saude do Sistema                                                  |
| [heart] Todos os servicos operacionais                            |
| [Conectado] DB  |  [2] Usuarios  |  [Windows 10 Pro] Sistema     |
+------------------------------------------------------------------+
| COL 50%                    | COL 50%                              |
| Ultimas Execucoes          | Proximas Execucoes Agendadas         |
| (lista max 5 items)        | (lista max 5 items)                  |
+------------------------------------------------------------------+
```

### 1.2 Componentes CSS Atuais

| Classe | Funcao | Estado |
|--------|--------|--------|
| `.dashboard-grid` | Grid auto-fit minmax(280px, 1fr) | Funcional |
| `.dashboard-card` | Card base: surface bg, 12px radius, shadow-sm, hover lift | Funcional |
| `.dashboard-card-header` | Flexbox: stat value + icon circle | Funcional |
| `.dashboard-stat-value` | Numero grande (24px desktop, 20px mobile) | Funcional |
| `.dashboard-stat-row` | Flex row para sub-metricas | Funcional |
| `.dashboard-progress-bar` | Container da barra de progresso | CSS incompleto |
| `.dashboard-pulse` | Animacao de pulso para items running | CSS ausente |
| `.dashboard-list` | Lista sem estilo para recent runs | Funcional |
| `.dashboard-repos-card` | Wrapper repositorios | CSS ausente |
| `.dashboard-health-card` | Wrapper saude do sistema | CSS ausente |
| `.dashboard-quick-actions` | Flex wrap para botoes de acao | Funcional |

### 1.3 Variaveis de Design Existentes

**Cores semanticas:**
- `--color-primary`: teal-500 (#218085)
- `--color-success`: teal-500 (#218085)
- `--color-error`: red-500 (#c0152f)
- `--color-warning`: orange-500 (#a84b2f)
- `--color-info`: slate-500 (#626c71)

**Espacamento:** `--space-{0,1,2,4,6,8,10,12,16,20,24,32}`
**Tipografia:** `--font-size-{xs,sm,base,md,lg,xl,2xl,3xl}` (11px-24px)
**Raios:** `--radius-{sm,base,md,lg}` (6px-12px)
**Sombras:** `--shadow-{xs,sm,md,lg,inset-sm}`
**Transicoes:** `--duration-fast` (150ms), `--duration-normal` (250ms)

### 1.4 Fluxo de Dados Atual

```
showDashboard()
  ├── GET /api/dashboard/stats   → stats (pipeline_runs, releases, totals, repos, etc.)
  ├── GET /api/health            → health (status, database, stats.users)
  ├── GET /api/log-alerts/summary → obsSummary (by_severity, unacknowledged)
  └── renderDashboard(stats, health, obsSummary)
        ├── Quick Actions (se admin/operator)
        ├── 5 Metric Cards (HTML template literals)
        ├── Repos Card
        ├── Health Card
        └── 2-col: Recent Runs + Schedules
```

---

## 2. Gaps Identificados

### 2.1 Gaps de Dados (modulos sem representacao)

| Modulo | Rota | Dados Disponiveis | Representacao no Dashboard |
|--------|------|-------------------|---------------------------|
| Pipelines | #pipelines | Runs, builds, status | Parcial (so contagem) |
| Observabilidade | #observability | Alertas, monitors, severidade | Parcial (so total critico) |
| Repositorios | #repositories | Repos, branches, sync | Parcial (so listagem) |
| **Database** | #database | Conexoes, drivers, integridade | **NENHUMA** |
| **Processos** | #processes | Mapeamento, modulos, flows | **NENHUMA** |
| **Knowledge Base** | #knowledge | 78 artigos, analise recorrencia | **NENHUMA** |
| **Documentacao** | #documentation | Docs gerados, tipos, tamanhos | **NENHUMA** |
| **Dev Workspace** | #devworkspace | Fontes, impacto, policies | **NENHUMA** |
| **TobIAs Agent** | #agent | Chunks, files, chat, LLM usage | **NENHUMA** |
| Schedules | #schedules | Cron, service actions | Parcial (lista proximos) |

**Resultado:** 5 de 10 modulos nao tem NENHUMA presenca no dashboard.

### 2.2 Gaps Visuais

| Gap | Impacto | Prioridade |
|-----|---------|------------|
| Zero graficos/charts | Impossivel ver tendencias ou evolucao | Critico |
| Sem sparklines nos KPIs | Numeros sem contexto historico | Alto |
| Sem period selector | Preso na visao "agora", sem 24h/7d/30d | Alto |
| Sem loading skeletons | Flash de conteudo vazio durante fetch | Medio |
| Sem empty states com CTA | Tela vazia sem orientacao ao usuario | Medio |
| Sem tooltips informativos | Hover nao adiciona contexto | Baixo |
| Sem animacoes de entrada | Cards aparecem de uma vez sem transicao | Baixo |
| CSS incompleto (pulse, progress, repos, health) | Estilos missing em producao | Alto |

### 2.3 Gaps de Interatividade

| Gap | Estado Atual | Desejado |
|-----|-------------|----------|
| Auto-refresh | Manual (botao "Atualizar") | Polling 30s KPIs, 5min charts |
| Drill-down | Nenhum | Click em card → modulo detalhado |
| Period selector | Inexistente | Toggle 24h / 7d / 30d global |
| Tooltips | Inexistentes | Hover com detalhamento |
| Quick Actions | 5 botoes fixos | Contextuais (baseados no estado) |

### 2.4 Endpoint Existente Subutilizado

**`GET /api/dashboard/metrics`** — Ja existe no backend mas **NAO e chamado** pelo dashboard!

Retorna:
- `daily_runs[]` — runs por dia (sucesso vs falha) → perfeito para bar chart
- `daily_releases[]` — releases por dia → perfeito para line chart
- `pipeline_stats[]` — top 20 pipelines com avg_duration e success_rate → radar/bar chart
- `top_failures[]` — top 5 erros → horizontal bar chart

Parametro `days` (1-90) → suporta period selector nativamente.

---

## 3. Benchmark — Dashboards de Referencia

### Grafana
- **Ponto forte:** Densidade de informacao, panels customizaveis, time range selector global
- **Aplicavel ao AtuDIC:** Period selector global, layout em grid com panels de tamanhos variados, threshold lines em charts

### Vercel Dashboard
- **Ponto forte:** Limpeza visual, hierarchy clara, dark mode elegante, metricas de deploy
- **Aplicavel ao AtuDIC:** KPI cards com sparklines minimalistas, tipografia com contraste forte, status indicators com cores semanticas

### Datadog
- **Ponto forte:** Correlacao de eventos em timeline, alertas em tempo real, top-N charts
- **Aplicavel ao AtuDIC:** Alert timeline por hora, top errors chart, live event feed

### Railway
- **Ponto forte:** Simplicidade, acoes rapidas inline, deploy status claro
- **Aplicavel ao AtuDIC:** Quick actions contextuais, status visual imediato, acoes em 1 click

### Portainer
- **Ponto forte:** Overview de containers/servicos, health grid com semaforo
- **Aplicavel ao AtuDIC:** System health grid, service status com cores, conexoes de banco

### GitHub Actions
- **Ponto forte:** Timeline de runs com status visual, drill-down por click, branch context
- **Aplicavel ao AtuDIC:** Recent runs com timeline vertical, status badges, drill-down para logs

---

## 4. Wireframe do Novo Dashboard

```
+==================================================================+
| HEADER (sem alteracoes)                                           |
+==================================================================+
|                                                                   |
| Dashboard                     [24h|7d|30d]  Atualizado 30s  [R]  |
| Visao geral: Homologacao                                          |
|                                                                   |
+==================================================================+
| TIER 1: KPI CARDS (5 colunas, repeat(5, 1fr) desktop)            |
|                                                                   |
| +----------+ +----------+ +----------+ +----------+ +----------+ |
| | Pipeline | | Deploys  | | Alertas  | | Servicos | | TobIAs   | |
| | Health   | |          | | Ativos   | | Uptime   | | Activity | |
| |          | |          | |          | |          | |          | |
| |   89%    | |    5     | |    6     | |   100%   | |    --    | |
| |  ^+12%   | |  oo 5/0  | | *6 0 0  | |  ====    | |  ||||   | |
| | ~~spark~ | | ~donut~  | | pulse!   | | ~circ~   | | ~bars~  | |
| +----------+ +----------+ +----------+ +----------+ +----------+ |
|                                                                   |
| Legenda visual:                                                   |
|   ^+12% = seta de tendencia                                      |
|   ~~spark~~ = sparkline 7 pontos                                  |
|   oo 5/0 = mini donut (sucesso/falha)                             |
|   *6 = badge pulsante se critico > 0                              |
|   ==== = barra circular de progresso                              |
|   |||| = mini bar chart semanal                                   |
|                                                                   |
+==================================================================+
| TIER 2: CHARTS (2 colunas principais)                            |
|                                                                   |
| +---------------------------+ +---------------------------+       |
| | Pipeline Runs (periodo)   | | Alert Timeline (24h)      |       |
| |                           | |                           |       |
| | [bar chart empilhado]     | | [area chart por nivel]    |       |
| | verde=sucesso             | | vermelho=critical         |       |
| | vermelho=falha            | | amarelo=warning           |       |
| | x=dias, y=count           | | azul=info                 |       |
| |                           | | x=horas, y=count          |       |
| +---------------------------+ +---------------------------+       |
|                                                                   |
| +---------------------------+ +---------------------------+       |
| | Response Time             | | Top Errors                |       |
| |                           | |                           |       |
| | [line chart]              | | [horizontal bar chart]    |       |
| | linha=avg duration        | | top 5 pipelines com mais  |       |
| | linha tracejada=threshold | | falhas, vermelho gradient |       |
| | x=dias, y=segundos        | | label + contagem          |       |
| +---------------------------+ +---------------------------+       |
|                                                                   |
+==================================================================+
| TIER 3: ACTIVITY & STATUS (3 colunas)                            |
|                                                                   |
| +------------------+ +------------------+ +------------------+    |
| | Live Feed        | | Proximos         | | System Health    |    |
| |                  | | Agendamentos     | |                  |    |
| | o 14:32 Pipeline | | countdown 2h30m  | | [x] DB Connected |    |
| |   "Deploy PRD"   | |   Pipeline A     | | [x] AppServer    |    |
| |   sucesso        | | countdown 5h15m  | | [ ] Disco > 90%  |    |
| | o 14:10 Alerta   | |   Service B      | | [x] Licenca OK   |    |
| |   "Lock DB"      | | countdown 1d2h   | | [x] 2 Usuarios   |    |
| |   critico        | |   Pipeline C     | | OS: Win10 Pro    |    |
| | o 13:55 Agent    | |                  | |                  |    |
| |   "Query opt"    | | (max 5 items)    | | Quick Actions:   |    |
| |   sugestao       | |                  | | [Exec Pipeline]  |    |
| | (max 10 items)   | |                  | | [Diagnosticar]*  |    |
| | timeline vertical| |                  | | [Ver Repos]      |    |
| +------------------+ +------------------+ +------------------+    |
|                                                                   |
+==================================================================+
| TIER 4: INSIGHTS (admin only, colapsavel)                        |
|                                                                   |
| +------------------+ +------------------+ +------------------+    |
| | Modulos          | | KB & Docs        | | Repo Activity    |    |
| |                  | |                  | |                  |    |
| | DB: 3 conexoes   | | 78 artigos       | | protheus         |    |
| | Processos: 12    | | 5 docs gerados   | | HOMOLOG: 2d ago  |    |
| | Workspace: OK    | | 3 recorrencias   | | MASTER: 5d ago   |    |
| | Agent: 250 chunks| | ultimo: "MVC"    | | (mini heatmap)   |    |
| +------------------+ +------------------+ +------------------+    |
|                                                                   |
+==================================================================+
```

### Grid Areas (CSS Grid)

```css
.dashboard-v2 {
  display: grid;
  gap: var(--space-20);
  grid-template-areas:
    "kpis"
    "charts"
    "activity"
    "insights";
}

/* KPIs: 5 colunas em desktop, 2+3 em tablet, 1 em mobile */
.dashboard-kpis {
  display: grid;
  grid-template-columns: repeat(5, 1fr);  /* desktop */
  gap: var(--space-16);
}

/* Charts: 2 colunas iguais */
.dashboard-charts {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-16);
}

/* Activity: 3 colunas (feed maior) */
.dashboard-activity {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: var(--space-16);
}

/* Insights: 3 colunas iguais */
.dashboard-insights {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-16);
}
```

### Responsividade

```css
/* Tablet (768px - 1024px) */
@media (max-width: 1024px) {
  .dashboard-kpis { grid-template-columns: repeat(3, 1fr); }
  .dashboard-charts { grid-template-columns: 1fr; }
  .dashboard-activity { grid-template-columns: 1fr 1fr; }
  .dashboard-insights { grid-template-columns: 1fr 1fr; }
}

/* Mobile (< 768px) */
@media (max-width: 768px) {
  .dashboard-kpis { grid-template-columns: repeat(2, 1fr); }
  .dashboard-activity { grid-template-columns: 1fr; }
  .dashboard-insights { grid-template-columns: 1fr; }
}

/* Mobile small (< 480px) */
@media (max-width: 480px) {
  .dashboard-kpis { grid-template-columns: 1fr; }
}
```

---

## 5. Plano de Implementacao

### Fase 1 — Fundacao (sem breaking changes)

**Objetivo:** Integrar Chart.js, criar helpers, modularizar `renderDashboard()`.

#### JS a criar/modificar

| Funcao | Arquivo | Acao |
|--------|---------|------|
| `initChartJS()` | integration-ui.js | Carregar Chart.js 4.x via CDN, registrar defaults (cores, fonte, responsivo, dark mode) |
| `chartColors()` | integration-ui.js | Helper que retorna cores baseadas em CSS variables (`getComputedStyle`) |
| `createChart(canvasId, type, data, options)` | integration-ui.js | Factory de charts com defaults AtuDIC (animations, responsive, tooltip) |
| `destroyCharts()` | integration-ui.js | Cleanup de instancias Chart.js ao sair do dashboard |
| `renderDashboardV2(stats, health, obsSummary, metrics)` | integration-ui.js | Nova funcao modular que chama widget renderers individuais |
| `renderKPICards(stats, obsSummary)` | integration-ui.js | Tier 1: retorna HTML dos 5 KPI cards |
| `renderChartWidgets(metrics)` | integration-ui.js | Tier 2: retorna HTML com `<canvas>` + inicia charts |
| `renderActivityWidgets(stats)` | integration-ui.js | Tier 3: live feed + schedules + health |
| `renderInsightWidgets(moduleStats)` | integration-ui.js | Tier 4: modulos + KB + repos |
| `showDashboard()` | integration-ui.js | Modificar para chamar `/api/dashboard/metrics` alem dos endpoints existentes |

#### CSS a adicionar

| Classe | Descricao |
|--------|-----------|
| `.dashboard-v2` | Container principal com grid areas |
| `.dashboard-kpis` | Grid de KPI cards (5 colunas) |
| `.dashboard-charts` | Grid de charts (2 colunas) |
| `.dashboard-activity` | Grid de atividade (3 colunas) |
| `.dashboard-insights` | Grid de insights (3 colunas) |
| `.dashboard-period-selector` | Toggle buttons 24h/7d/30d |
| `.dashboard-refresh-indicator` | Badge "atualizado ha Xmin" |
| `.dashboard-skeleton` | Loading skeleton animation |
| `.dashboard-chart-container` | Wrapper de canvas com aspect-ratio |

#### Endpoints necessarios

| Endpoint | Status | Notas |
|----------|--------|-------|
| `GET /api/dashboard/stats` | Existente | Sem alteracoes |
| `GET /api/dashboard/metrics?days=N` | **Existente mas nao usado!** | Precisa ser chamado pelo frontend |
| `GET /api/health` | Existente | Sem alteracoes |
| `GET /api/log-alerts/summary` | Existente | Sem alteracoes |

**CDN a adicionar no `index.html`:**
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js" defer></script>
```

**Complexidade:** G (Grande — refatoracao estrutural)

---

### Fase 2 — KPIs Modernos

**Objetivo:** Redesenhar os 5 KPI cards com sparklines, tendencias, e adicionar TobIAs.

#### JS a criar/modificar

| Funcao | Arquivo | Acao |
|--------|---------|------|
| `renderKPIPipelineHealth(stats, metrics)` | integration-ui.js | Card com % sucesso + sparkline de daily_runs + seta tendencia |
| `renderKPIDeploys(stats, metrics)` | integration-ui.js | Card com total + mini donut chart (sucesso/falha) |
| `renderKPIAlerts(obsSummary)` | integration-ui.js | Card com contagem por severidade + pulse se critico > 0 |
| `renderKPIServicesUptime(stats)` | integration-ui.js | Card com % ativas + barra circular |
| `renderKPITobiasActivity(agentStats)` | integration-ui.js | Card com interacoes + mini bar chart semanal |
| `createSparkline(canvasId, dataPoints, color)` | integration-ui.js | Chart.js line chart minimalista sem eixos |
| `createMiniDonut(canvasId, values, colors)` | integration-ui.js | Chart.js doughnut 60px |
| `calcTrend(current, previous)` | integration-ui.js | Retorna {direction: 'up'|'down'|'stable', percentage: N} |
| `renderPeriodSelector(activePeriod)` | integration-ui.js | Botoes 24h/7d/30d com estado ativo |
| `renderLoadingSkeleton(widgetCount)` | integration-ui.js | Placeholder animado durante fetch |

#### CSS a adicionar

| Classe | Descricao |
|--------|-----------|
| `.dashboard-kpi-card` | Card KPI com layout especifico (valor + sparkline) |
| `.dashboard-kpi-value` | Numero principal (32px, bold) |
| `.dashboard-kpi-trend` | Seta + percentual de tendencia |
| `.dashboard-kpi-trend.up` | Verde, seta para cima |
| `.dashboard-kpi-trend.down` | Vermelho, seta para baixo |
| `.dashboard-kpi-trend.stable` | Cinza, seta lateral |
| `.dashboard-kpi-sparkline` | Container do sparkline (height: 40px) |
| `.dashboard-kpi-mini-chart` | Container para mini donut/bar (60x60px) |
| `.dashboard-pulse-dot` | Animacao de pulso para alertas criticos |
| `.dashboard-circular-progress` | SVG circular progress bar |
| `.dashboard-skeleton-line` | Skeleton loading individual (shimmer) |
| `.dashboard-skeleton-card` | Skeleton de card inteiro |

#### Endpoints necessarios

| Endpoint | Status | Notas |
|----------|--------|-------|
| `GET /api/dashboard/metrics?days=1\|7\|30` | Existente | Period selector muda o parametro `days` |
| `GET /api/agent/memory/stats` | Existente | Para TobIAs Activity card |

**Complexidade:** G (Grande — 5 cards complexos + sparklines + skeletons)

---

### Fase 3 — Charts & Visualizacoes

**Objetivo:** Implementar os 4 charts do Tier 2 com dados do `/api/dashboard/metrics`.

#### JS a criar/modificar

| Funcao | Arquivo | Acao |
|--------|---------|------|
| `renderPipelineRunsChart(metrics, period)` | integration-ui.js | Bar chart empilhado: sucesso (verde) + falha (vermelho) por dia |
| `renderAlertTimelineChart(alertData)` | integration-ui.js | Area chart: alertas por hora, 3 areas por severidade |
| `renderResponseTimeChart(metrics)` | integration-ui.js | Line chart: avg_duration_sec dos top pipelines por dia |
| `renderTopErrorsChart(metrics)` | integration-ui.js | Horizontal bar chart: top_failures com gradiente vermelho |
| `configureChartDarkMode()` | integration-ui.js | Listener de tema que atualiza Chart.js defaults |
| `resizeAllCharts()` | integration-ui.js | Handler de resize com debounce |

#### CSS a adicionar

| Classe | Descricao |
|--------|-----------|
| `.dashboard-chart-card` | Card com padding ajustado para chart |
| `.dashboard-chart-header` | Titulo + periodo + legenda inline |
| `.dashboard-chart-canvas` | Canvas com aspect-ratio 2:1 desktop, 1.5:1 mobile |
| `.dashboard-chart-legend` | Legenda custom (nao a nativa do Chart.js) |
| `.dashboard-chart-empty` | Estado vazio com icone + CTA |

#### Endpoints necessarios

| Endpoint | Status | Acao |
|----------|--------|------|
| `GET /api/dashboard/metrics?days=N` | Existente | Fornece `daily_runs`, `pipeline_stats`, `top_failures` |
| **`GET /api/log-alerts/timeline`** | **NOVO** | Alertas agrupados por hora (ultimas 24h) |

**Novo endpoint detalhado na secao 6.**

**Complexidade:** G (Grande — 4 charts com responsividade + dark mode)

---

### Fase 4 — Activity & Intelligence

**Objetivo:** Live Feed, Knowledge Base cards, Quick Actions contextuais, auto-refresh.

#### JS a criar/modificar

| Funcao | Arquivo | Acao |
|--------|---------|------|
| `renderLiveFeed(recentRuns, recentAlerts, recentActions)` | integration-ui.js | Timeline vertical com icones, merge e ordena por timestamp |
| `renderNextSchedules(schedules, serviceSchedules)` | integration-ui.js | Lista com countdown relativo ("em 2h 30min") |
| `renderSystemHealth(health, dbConnections)` | integration-ui.js | Grid semaforo: DB, AppServer, disco, licenca |
| `renderQuickActionsV2(state)` | integration-ui.js | Botoes contextuais baseados no estado (se critico > 0, mostra "Diagnosticar") |
| `renderModuleOverview(moduleStats)` | integration-ui.js | Card Tier 4: resumo de DB, Processos, Workspace, Agent |
| `renderKBDocsCard(kbStats, docStats)` | integration-ui.js | Card Tier 4: artigos + docs gerados + recorrencias |
| `renderRepoActivityCard(repos)` | integration-ui.js | Card Tier 4: repos com ultimo sync |
| `startAutoRefresh(intervalKPI, intervalCharts)` | integration-ui.js | Polling: 30s KPIs, 300s charts. Para ao sair do dashboard |
| `stopAutoRefresh()` | integration-ui.js | Cleanup de intervals |
| `updateRefreshIndicator()` | integration-ui.js | "Atualizado ha X min" com countdown |
| `formatCountdown(targetDate)` | integration-ui.js | "em 2h 30min", "em 15min", "em 3d" |
| `mergeFeedItems(runs, alerts, actions)` | integration-ui.js | Merge arrays por timestamp, limit 10 |

#### CSS a adicionar

| Classe | Descricao |
|--------|-----------|
| `.dashboard-feed` | Container do live feed |
| `.dashboard-feed-item` | Item com icone + texto + timestamp |
| `.dashboard-feed-icon` | Icone circular por tipo (pipeline/alerta/servico) |
| `.dashboard-feed-dot` | Bolinha na timeline vertical |
| `.dashboard-feed-line` | Linha vertical conectando items |
| `.dashboard-countdown` | Badge com tempo restante |
| `.dashboard-health-grid` | Grid 2x3 para status items |
| `.dashboard-health-item` | Item com semaforo + label |
| `.dashboard-health-dot` | Bolinha verde/amarelo/vermelho |
| `.dashboard-quick-actions-v2` | Layout contextual de botoes |
| `.dashboard-module-stat` | Item de stat de modulo inline |
| `.dashboard-insights-section` | Secao colapsavel para Tier 4 |

#### Endpoints necessarios

| Endpoint | Status | Acao |
|----------|--------|------|
| **`GET /api/dashboard/feed`** | **NOVO** | Ultimas 10 acoes de todos os modulos |
| **`GET /api/dashboard/modules-summary`** | **NOVO** | Stats resumidos de todos os modulos |
| `GET /api/knowledge?limit=5` | Existente | Artigos recentes |
| `GET /api/docs?limit=5` | Existente | Docs recentes |
| `GET /api/agent/memory/stats` | Existente | Stats do agente |

**Novos endpoints detalhados na secao 6.**

**Complexidade:** G (Grande — 7 widgets + auto-refresh + feed merging)

---

### Fase 5 — Polish & Personalizacao

**Objetivo:** Animacoes, empty states, drill-down, tooltips, responsividade final.

#### JS a criar/modificar

| Funcao | Arquivo | Acao |
|--------|---------|------|
| `animateCardEntrance(cards)` | integration-ui.js | Stagger animation com IntersectionObserver |
| `renderEmptyState(widgetId, message, ctaText, ctaAction)` | integration-ui.js | Template de empty state com icone + CTA |
| `setupDrillDown()` | integration-ui.js | Event delegation: click em card → `location.hash = '#module'` |
| `createTooltip(element, content)` | integration-ui.js | Tooltip posicionado com conteudo rico |
| `setupKeyboardNav()` | integration-ui.js | Tab navigation entre cards com focus visible |

#### CSS a adicionar

| Classe | Descricao |
|--------|-----------|
| `.dashboard-card-enter` | Animacao: opacity 0 → 1, translateY 20px → 0 |
| `.dashboard-card-stagger-{1-12}` | Delay incremental (50ms * N) |
| `.dashboard-empty-state` | Container centralizado com icone + texto + botao |
| `.dashboard-tooltip` | Tooltip flutuante com seta |
| `.dashboard-card[data-drilldown]` | Cursor pointer + hover state diferenciado |
| `.dashboard-card:focus-visible` | Outline acessivel |

#### Endpoints necessarios

Nenhum novo.

**Complexidade:** M (Media — polish visual, sem logica complexa)

---

## 6. Novos Endpoints Necessarios

### 6.1 `GET /api/log-alerts/timeline`

**Objetivo:** Alimentar o chart "Alert Timeline (24h)" do Tier 2.

**Rota:** `GET /api/log-alerts/timeline`
**Metodo:** GET
**Autenticacao:** Requerida (`@require_auth`)

**Parametros:**
| Param | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `environment_id` | int | Header `X-Environment-Id` | Filtro de ambiente |
| `hours` | int | 24 | Janela de tempo (max 72) |

**Resposta:**
```json
{
  "period_hours": 24,
  "timeline": [
    {
      "hour": "2026-03-19T14:00:00",
      "critical": 2,
      "warning": 1,
      "info": 0
    },
    {
      "hour": "2026-03-19T13:00:00",
      "critical": 0,
      "warning": 3,
      "info": 1
    }
  ]
}
```

**Query SQL:**
```sql
SELECT
  DATE_TRUNC('hour', occurred_at) AS hour,
  COUNT(*) FILTER (WHERE severity = 'critical') AS critical,
  COUNT(*) FILTER (WHERE severity = 'warning') AS warning,
  COUNT(*) FILTER (WHERE severity = 'info') AS info
FROM log_alerts
WHERE environment_id = :env_id
  AND occurred_at >= NOW() - INTERVAL ':hours hours'
  AND acknowledged = FALSE
GROUP BY DATE_TRUNC('hour', occurred_at)
ORDER BY hour ASC
```

**Service:** `app/routes/observability.py` — adicionar ao blueprint existente.

---

### 6.2 `GET /api/dashboard/feed`

**Objetivo:** Alimentar o widget "Live Feed" do Tier 3, mergindo acoes de multiplos modulos.

**Rota:** `GET /api/dashboard/feed`
**Metodo:** GET
**Autenticacao:** Requerida (`@require_auth`)

**Parametros:**
| Param | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `environment_id` | int | Header `X-Environment-Id` | Filtro de ambiente |
| `limit` | int | 10 | Max items (max 20) |

**Resposta:**
```json
{
  "items": [
    {
      "type": "pipeline_run",
      "icon": "fa-play-circle",
      "color": "success",
      "title": "Deploy PRD executado",
      "subtitle": "Pipeline: Deploy Producao",
      "status": "success",
      "timestamp": "2026-03-19T14:32:00",
      "drilldown": "#pipelines"
    },
    {
      "type": "alert",
      "icon": "fa-exclamation-triangle",
      "color": "danger",
      "title": "Lock de tabela detectado",
      "subtitle": "Alerta critico: database",
      "status": "critical",
      "timestamp": "2026-03-19T14:10:00",
      "drilldown": "#observability"
    },
    {
      "type": "service_action",
      "icon": "fa-server",
      "color": "info",
      "title": "Servico reiniciado",
      "subtitle": "AppServer - restart",
      "status": "executed",
      "timestamp": "2026-03-19T13:55:00",
      "drilldown": "#schedules"
    }
  ]
}
```

**Query SQL (UNION ALL):**
```sql
(
  SELECT 'pipeline_run' AS type, pipeline_name AS title, status,
         started_at AS timestamp
  FROM pipeline_runs pr
  JOIN pipelines p ON pr.pipeline_id = p.id
  WHERE pr.environment_id = :env_id
  ORDER BY started_at DESC LIMIT :limit
)
UNION ALL
(
  SELECT 'alert' AS type, message AS title, severity AS status,
         occurred_at AS timestamp
  FROM log_alerts
  WHERE environment_id = :env_id AND acknowledged = FALSE
  ORDER BY occurred_at DESC LIMIT :limit
)
UNION ALL
(
  SELECT 'service_action' AS type, name AS title, action_type AS status,
         last_run_at AS timestamp
  FROM service_actions
  WHERE environment_id = :env_id AND last_run_at IS NOT NULL
  ORDER BY last_run_at DESC LIMIT :limit
)
ORDER BY timestamp DESC
LIMIT :limit
```

**Service:** `app/routes/main.py` — adicionar ao blueprint existente.

---

### 6.3 `GET /api/dashboard/modules-summary`

**Objetivo:** Alimentar o Tier 4 "Module Overview" com stats resumidos de todos os modulos.

**Rota:** `GET /api/dashboard/modules-summary`
**Metodo:** GET
**Autenticacao:** Requerida (`@require_auth`)

**Parametros:**
| Param | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `environment_id` | int | Header `X-Environment-Id` | Filtro de ambiente |

**Resposta:**
```json
{
  "database": {
    "total_connections": 3,
    "connected": 2,
    "error": 1
  },
  "processes": {
    "total": 12,
    "active": 8,
    "draft": 4
  },
  "knowledge": {
    "total_articles": 78,
    "recent_articles": 3,
    "recurring_issues": 2
  },
  "documentation": {
    "total_docs": 5,
    "last_generated": "2026-03-18T10:00:00"
  },
  "devworkspace": {
    "total_fontes": 42,
    "policies_active": 3
  },
  "agent": {
    "total_chunks": 250,
    "total_files": 15,
    "last_updated": "2026-03-19T12:00:00"
  }
}
```

**Implementacao:** Agregar contagens simples de cada tabela/modulo. Queries leves (COUNT only).

**Service:** `app/routes/main.py` — adicionar ao blueprint existente.

---

## 7. Resumo de Complexidade por Fase

| Fase | Descricao | Complexidade | Deps |
|------|-----------|-------------|------|
| **1** | Fundacao (Chart.js + modularizacao) | G | Nenhuma |
| **2** | KPIs Modernos (sparklines, trends) | G | Fase 1 |
| **3** | Charts & Visualizacoes | G | Fase 1 + endpoint timeline |
| **4** | Activity & Intelligence | G | Fase 1 + endpoints feed/modules |
| **5** | Polish & Personalizacao | M | Fases 1-4 |

### Ordem de execucao recomendada

```
Fase 1 (fundacao)
  ├── Fase 2 (KPIs)     ← pode comecar em paralelo apos Chart.js integrado
  ├── Fase 3 (charts)   ← pode comecar em paralelo apos Chart.js integrado
  └── Fase 4 (activity) ← depende de novos endpoints
Fase 5 (polish) ← apos todas as fases anteriores
```

**Fases 2 e 3 podem ser desenvolvidas em paralelo** apos a Fase 1.
**Fase 4 requer 3 novos endpoints** (timeline, feed, modules-summary).
**Fase 5 e incremental** e pode ser feita por widget.

---

## 8. Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| Chart.js CDN fora do ar | Baixa | Alto | Fallback: mostrar dados em tabela se Chart undefined |
| Performance com 10+ charts | Media | Medio | Lazy render com IntersectionObserver; destroy ao sair |
| `/api/dashboard/metrics` lento com 90 dias | Media | Medio | Cache server-side (5min TTL) ou limitar a 30 dias |
| Breaking change no `renderDashboard()` | Alta | Alto | Manter assinatura, criar `renderDashboardV2()` interno |
| Dark mode inconsistente nos charts | Media | Baixo | Listener de tema que recria charts com novas cores |
| Mobile com muitos widgets | Media | Medio | Colapsar Tier 3/4 em accordion no mobile |
| Auto-refresh conflita com interacao | Baixa | Medio | Pausar refresh enquanto usuario interage (hover/click) |

---

## 9. Checklist Pre-Implementacao

- [ ] Aprovar wireframe e layout proposto
- [ ] Confirmar quais widgets do Tier 4 sao obrigatorios vs opcionais
- [ ] Validar que `/api/dashboard/metrics` retorna dados corretos em producao
- [ ] Definir prioridade: comecar por Fase 2 (KPIs) ou Fase 3 (Charts)?
- [ ] Aprovar criacao dos 3 novos endpoints (timeline, feed, modules-summary)
- [ ] Decidir se Quick Actions contextuais substituem ou complementam os atuais
- [ ] Definir se Tier 4 (Insights) e visivel para todos ou apenas admins
