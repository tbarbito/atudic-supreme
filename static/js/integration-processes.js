/**
 * Módulo de Processos da Empresa — BiizHubOps
 *
 * Gerencia processos de negócio do ERP Protheus:
 * - Lista de processos (por módulo)
 * - Detalhe com tabelas, campos e fluxos
 * - Mapa de fluxos entre processos
 * - Seed de processos padrão
 */

/* global apiRequest, showNotification, getSelectedEnvironment, currentUser */

// =====================================================================
// ESTADO LOCAL
// =====================================================================
let bpProcesses = [];
let bpSelectedProcess = null;
let bpActiveTab = 'list'; // 'list', 'detail', 'flows'
let bpModules = [];
let bpFilterModule = '';
let bpFilterSearch = '';

// =====================================================================
// PONTO DE ENTRADA
// =====================================================================

async function showProcesses() {
    const container = document.getElementById('content-area');
    if (!container) return;

    container.innerHTML = `
        <div class="container-fluid py-4">
            <!-- Cabeçalho -->
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2 class="mb-1"><i class="fas fa-project-diagram me-2"></i>Processos da Empresa</h2>
                    <p class="text-muted mb-0">Mapeamento de processos de negócio do ERP Protheus</p>
                </div>
                <div class="d-flex gap-2">
                    <button class="btn btn-outline-primary" data-action="bpRefresh">
                        <i class="fas fa-sync-alt me-1"></i> Atualizar
                    </button>
                    <button class="btn btn-outline-success" data-action="bpSeed">
                        <i class="fas fa-seedling me-1"></i> Carregar Padrão
                    </button>
                    <button class="btn btn-primary" data-action="bpShowCreate">
                        <i class="fas fa-plus me-1"></i> Novo Processo
                    </button>
                </div>
            </div>

            <!-- Abas -->
            <ul class="nav nav-tabs mb-3" id="bpTabs">
                <li class="nav-item">
                    <a class="nav-link ${bpActiveTab === 'list' ? 'active' : ''}" href="#"
                       data-action="bpSwitchTab" data-params='{"tab":"list"}'>
                        <i class="fas fa-list me-1"></i> Processos
                        <span class="badge bg-secondary ms-1" id="bpCount">0</span>
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link ${bpActiveTab === 'detail' ? 'active' : ''}" href="#"
                       data-action="bpSwitchTab" data-params='{"tab":"detail"}' id="bpTabDetail" style="display:${bpSelectedProcess ? 'block' : 'none'}">
                        <i class="fas fa-info-circle me-1"></i> Detalhe
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link ${bpActiveTab === 'flows' ? 'active' : ''}" href="#"
                       data-action="bpSwitchTab" data-params='{"tab":"flows"}'>
                        <i class="fas fa-sitemap me-1"></i> Mapa de Fluxos
                    </a>
                </li>
            </ul>

            <!-- Conteúdo da aba -->
            <div id="bpTabContent"></div>
        </div>
    `;

    // Carrega módulos e processos
    try {
        const mods = await apiRequest('/protheus-modules');
        bpModules = mods || [];
    } catch (e) {
        bpModules = [];
    }

    await _bpLoadProcesses();
    _bpRenderTab();
}

// =====================================================================
// CARREGAMENTO DE DADOS
// =====================================================================

async function _bpLoadProcesses() {
    try {
        const params = new URLSearchParams();
        if (bpFilterModule) params.append('module', bpFilterModule);
        if (bpFilterSearch) params.append('search', bpFilterSearch);
        const qs = params.toString() ? `?${params.toString()}` : '';
        bpProcesses = await apiRequest(`/processes${qs}`);
        const badge = document.getElementById('bpCount');
        if (badge) badge.textContent = bpProcesses.length;
    } catch (e) {
        bpProcesses = [];
        showNotification('Erro ao carregar processos: ' + e.message, 'error');
    }
}

async function _bpLoadDetail(processId) {
    try {
        bpSelectedProcess = await apiRequest(`/processes/${processId}`);
    } catch (e) {
        showNotification('Erro ao carregar detalhes: ' + e.message, 'error');
    }
}

// =====================================================================
// RENDERIZAÇÃO DE ABAS
// =====================================================================

async function _bpRenderTab() {
    const content = document.getElementById('bpTabContent');
    if (!content) return;

    // Atualiza abas ativas
    document.querySelectorAll('#bpTabs .nav-link').forEach(link => {
        const tabParam = link.dataset.params ? JSON.parse(link.dataset.params).tab : null;
        link.classList.toggle('active', tabParam === bpActiveTab);
    });

    switch (bpActiveTab) {
        case 'list': _bpRenderList(content); break;
        case 'detail': _bpRenderDetail(content); break;
        case 'flows': await _bpRenderFlows(content); break;
    }
}

// =====================================================================
// ABA: LISTA DE PROCESSOS
// =====================================================================

function _bpRenderList(container) {
    // Agrupar por módulo
    const grouped = {};
    bpProcesses.forEach(p => {
        const mod = p.module_label || p.module || 'Outros';
        if (!grouped[mod]) grouped[mod] = [];
        grouped[mod].push(p);
    });

    // Filtros
    let moduleOptions = bpModules.map(m =>
        `<option value="${m.code}" ${bpFilterModule === m.code ? 'selected' : ''}>${m.label}</option>`
    ).join('');

    let html = `
        <div class="row mb-3">
            <div class="col-md-4">
                <div class="input-group">
                    <span class="input-group-text"><i class="fas fa-search"></i></span>
                    <input type="text" class="form-control" placeholder="Buscar processo..."
                           value="${bpFilterSearch}" id="bpSearchInput">
                </div>
            </div>
            <div class="col-md-3">
                <select class="form-select" id="bpModuleFilter">
                    <option value="">Todos os módulos</option>
                    ${moduleOptions}
                </select>
            </div>
        </div>
    `;

    if (bpProcesses.length === 0) {
        html += `
            <div class="text-center py-5">
                <i class="fas fa-project-diagram fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">Nenhum processo cadastrado</h5>
                <p class="text-muted">Clique em "Carregar Padrão" para importar os processos do Protheus.</p>
            </div>
        `;
    } else {
        for (const [modLabel, procs] of Object.entries(grouped)) {
            const firstProc = procs[0];
            const modIcon = firstProc.icon || 'fa-cogs';
            const modColor = firstProc.color || '#007bff';

            html += `
                <div class="mb-4">
                    <h5 class="mb-3">
                        <i class="fas ${modIcon} me-2" style="color:${modColor}"></i>
                        ${modLabel}
                        <span class="badge bg-secondary">${procs.length}</span>
                    </h5>
                    <div class="row g-3">
            `;

            for (const p of procs) {
                const statusBadge = p.status === 'active'
                    ? '<span class="badge bg-success">Ativo</span>'
                    : p.status === 'draft'
                    ? '<span class="badge bg-warning">Rascunho</span>'
                    : '<span class="badge bg-secondary">Arquivado</span>';

                html += `
                    <div class="col-md-6 col-lg-4">
                        <div class="card h-100 border-start border-3" style="border-color:${p.color || '#007bff'} !important; cursor:pointer;"
                             data-action="bpSelectProcess" data-params='{"id":${p.id}}'>
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-start mb-2">
                                    <h6 class="card-title mb-0">
                                        <i class="fas ${p.icon || 'fa-cogs'} me-1" style="color:${p.color}"></i>
                                        ${p.name}
                                    </h6>
                                    ${statusBadge}
                                </div>
                                <p class="card-text text-muted small mb-2">${p.description || 'Sem descrição'}</p>
                                <div class="d-flex gap-2">
                                    <span class="badge bg-dark"><i class="fas fa-table me-1"></i>${p.table_count || 0} tabelas</span>
                                    <span class="badge bg-dark"><i class="fas fa-exchange-alt me-1"></i>${p.flow_count || 0} fluxos</span>
                                    ${p.is_system ? '<span class="badge bg-info">Sistema</span>' : ''}
                                </div>
                            </div>
                            <div class="card-footer bg-transparent d-flex justify-content-end gap-1">
                                <button class="btn btn-sm btn-outline-primary" data-action="bpEdit" data-params='{"id":${p.id}}' title="Editar">
                                    <i class="fas fa-edit"></i>
                                </button>
                                ${!p.is_system ? `<button class="btn btn-sm btn-outline-danger" data-action="bpDelete" data-params='{"id":${p.id}}' title="Excluir">
                                    <i class="fas fa-trash"></i>
                                </button>` : ''}
                            </div>
                        </div>
                    </div>
                `;
            }

            html += `</div></div>`;
        }
    }

    container.innerHTML = html;

    // Bind filtros
    const searchInput = document.getElementById('bpSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', _bpDebounce(async () => {
            bpFilterSearch = searchInput.value.trim();
            await _bpLoadProcesses();
            _bpRenderList(container);
        }, 400));
    }

    const moduleFilter = document.getElementById('bpModuleFilter');
    if (moduleFilter) {
        moduleFilter.addEventListener('change', async () => {
            bpFilterModule = moduleFilter.value;
            await _bpLoadProcesses();
            _bpRenderList(container);
        });
    }
}

// =====================================================================
// ABA: DETALHE DO PROCESSO
// =====================================================================

function _bpRenderDetail(container) {
    if (!bpSelectedProcess) {
        container.innerHTML = `
            <div class="text-center py-5">
                <i class="fas fa-hand-pointer fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">Selecione um processo para ver detalhes</h5>
            </div>
        `;
        return;
    }

    const p = bpSelectedProcess;
    const tables = p.tables || [];
    const flows = p.flows || [];

    let tablesHtml = '';
    if (tables.length === 0) {
        tablesHtml = '<p class="text-muted">Nenhuma tabela vinculada.</p>';
    } else {
        for (const tbl of tables) {
            const fields = tbl.fields || [];
            const roleBadge = tbl.table_role === 'principal'
                ? '<span class="badge bg-primary">Principal</span>'
                : tbl.table_role === 'auxiliar'
                ? '<span class="badge bg-warning">Auxiliar</span>'
                : '<span class="badge bg-secondary">Relacionada</span>';

            let fieldsHtml = '';
            if (fields.length > 0) {
                fieldsHtml = `
                    <table class="table table-sm table-hover mb-0" style="font-size:0.85rem">
                        <thead><tr>
                            <th>Campo</th><th>Descricao</th><th>Chave</th><th>Regra</th><th style="width:60px"></th>
                        </tr></thead>
                        <tbody>
                            ${fields.map(f => `
                                <tr>
                                    <td><code>${f.column_name}</code></td>
                                    <td>${f.column_label || ''}</td>
                                    <td>${f.is_key ? '<i class="fas fa-key text-warning"></i>' : ''}</td>
                                    <td class="text-muted small">${f.business_rule || ''}</td>
                                    <td>
                                        <div class="d-flex gap-1">
                                            <button class="btn btn-sm btn-outline-primary py-0 px-1" data-action="bpEditField" data-params='{"id":${f.id}}' title="Editar campo">
                                                <i class="fas fa-pen" style="font-size:0.7rem"></i>
                                            </button>
                                            <button class="btn btn-sm btn-outline-danger py-0 px-1" data-action="bpDeleteField" data-params='{"id":${f.id}}' title="Remover campo">
                                                <i class="fas fa-times" style="font-size:0.7rem"></i>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } else {
                fieldsHtml = '<p class="text-muted small mb-0">Nenhum campo mapeado</p>';
            }

            tablesHtml += `
                <div class="card mb-3">
                    <div class="card-header d-flex justify-content-between align-items-center py-2">
                        <div>
                            <strong><code>${tbl.table_name}</code></strong>
                            <span class="text-muted ms-2">${tbl.table_alias || ''}</span>
                            ${roleBadge}
                        </div>
                        <div class="d-flex gap-1">
                            <button class="btn btn-sm btn-outline-primary" data-action="bpEditTable" data-params='{"id":${tbl.id}}' title="Editar tabela">
                                <i class="fas fa-pen"></i>
                            </button>
                            ${tbl.connection_id ? `<button class="btn btn-sm btn-outline-info" data-action="bpAutoMapFields" data-params='{"tableId":${tbl.id},"connectionId":${tbl.connection_id}}' title="Auto-importar campos">
                                <i class="fas fa-magic"></i>
                            </button>` : ''}
                            <button class="btn btn-sm btn-outline-danger" data-action="bpRemoveTable" data-params='{"id":${tbl.id}}' title="Remover tabela">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="card-body p-0">
                        ${fieldsHtml}
                    </div>
                </div>
            `;
        }
    }

    // Fluxos
    let flowsHtml = '';
    if (flows.length > 0) {
        flowsHtml = flows.map(f => {
            const isSource = f.source_process_id === p.id;
            const otherName = isSource ? f.target_name : f.source_name;
            const direction = isSource ? 'fa-arrow-right text-success' : 'fa-arrow-left text-info';
            const typeBadge = f.flow_type === 'trigger'
                ? '<span class="badge bg-warning">Trigger</span>'
                : f.flow_type === 'dependency'
                ? '<span class="badge bg-danger">Dependência</span>'
                : '<span class="badge bg-info">Dados</span>';
            return `
                <div class="d-flex align-items-center gap-2 mb-2 p-2 border rounded">
                    <i class="fas ${direction}"></i>
                    <div class="flex-grow-1">
                        <strong>${otherName}</strong>
                        ${typeBadge}
                        <div class="text-muted small">${f.description || ''}</div>
                        ${f.source_table ? `<code class="small">${f.source_table} → ${f.target_table}</code>` : ''}
                    </div>
                    <div class="d-flex gap-1">
                        <button class="btn btn-sm btn-outline-primary" data-action="bpEditFlow" data-params='{"id":${f.id}}' title="Editar fluxo">
                            <i class="fas fa-pen"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" data-action="bpDeleteFlow" data-params='{"id":${f.id}}' title="Excluir fluxo">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    } else {
        flowsHtml = '<p class="text-muted">Nenhum fluxo conectado.</p>';
    }

    container.innerHTML = `
        <div class="row">
            <!-- Info do processo -->
            <div class="col-12 mb-3">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas ${p.icon || 'fa-cogs'} me-2" style="color:${p.color}"></i>
                            <strong>${p.name}</strong>
                            <span class="badge bg-secondary ms-2">${p.module_label || p.module}</span>
                            ${p.is_system ? '<span class="badge bg-info ms-1">Sistema</span>' : ''}
                        </div>
                        <button class="btn btn-sm btn-outline-secondary" data-action="bpSwitchTab" data-params='{"tab":"list"}'>
                            <i class="fas fa-arrow-left me-1"></i> Voltar
                        </button>
                    </div>
                    <div class="card-body">
                        <p class="mb-0">${p.description || 'Sem descrição'}</p>
                    </div>
                </div>
            </div>

            <!-- Tabelas -->
            <div class="col-lg-8">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h5><i class="fas fa-table me-2"></i>Tabelas Vinculadas (${tables.length})</h5>
                    <button class="btn btn-sm btn-outline-primary" data-action="bpShowAddTable" data-params='{"id":${p.id}}'>
                        <i class="fas fa-plus me-1"></i> Vincular Tabela
                    </button>
                </div>
                ${tablesHtml}
            </div>

            <!-- Fluxos -->
            <div class="col-lg-4">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h5 class="mb-0"><i class="fas fa-exchange-alt me-2"></i>Fluxos (${flows.length})</h5>
                    <button class="btn btn-sm btn-outline-primary" data-action="bpShowAddFlow" data-params='{"id":${p.id}}'>
                        <i class="fas fa-plus me-1"></i> Novo Fluxo
                    </button>
                </div>
                ${flowsHtml}
            </div>
        </div>
    `;
}

// =====================================================================
// ABA: MAPA DE FLUXOS
// =====================================================================

async function _bpRenderFlows(container) {
    container.innerHTML = '<div class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x"></i></div>';

    try {
        const data = await apiRequest('/processes/flow-map');
        const nodes = data.nodes || [];
        const edges = data.edges || [];

        if (nodes.length === 0) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-sitemap fa-3x text-muted mb-3"></i>
                    <h5 class="text-muted">Nenhum processo cadastrado</h5>
                    <p class="text-muted">Carregue os processos padrão para visualizar o mapa de fluxos.</p>
                </div>
            `;
            return;
        }

        // Dimensões dos nodos
        const nodeW = 210;
        const nodeH = 60;
        const pad = 30;

        // --- Dagre: layout automático do grafo ---
        const g = new dagre.graphlib.Graph();
        g.setGraph({
            rankdir: 'LR',      // esquerda → direita
            nodesep: 40,         // espaço vertical entre nodos
            ranksep: 80,         // espaço horizontal entre ranks
            marginx: pad,
            marginy: pad,
        });
        g.setDefaultEdgeLabel(() => ({}));

        // Mapa id → node data
        const nodeMap = {};
        nodes.forEach(n => {
            nodeMap[n.id] = n;
            g.setNode(String(n.id), { width: nodeW, height: nodeH });
        });

        edges.forEach(e => {
            g.setEdge(String(e.source_process_id), String(e.target_process_id), {
                flow_type: e.flow_type,
                source_table: e.source_table,
                target_table: e.target_table,
            });
        });

        dagre.layout(g);

        // Extrair posições calculadas pelo dagre (centro do nodo)
        const nodePositions = {};
        g.nodes().forEach(id => {
            const pos = g.node(id);
            nodePositions[id] = {
                x: pos.x - nodeW / 2,  // dagre retorna centro, converter para top-left
                y: pos.y - nodeH / 2,
                cx: pos.x,
                cy: pos.y,
                node: nodeMap[id],
            };
        });

        // Calcular dimensões do SVG
        let maxX = 0, maxY = 0;
        Object.values(nodePositions).forEach(p => {
            maxX = Math.max(maxX, p.x + nodeW);
            maxY = Math.max(maxY, p.y + nodeH);
        });
        const svgWidth = Math.max(960, maxX + pad * 2);
        const svgHeight = Math.max(400, maxY + pad * 2);

        // --- Desenhar arestas com pontos do dagre ---
        let svgEdges = '';
        g.edges().forEach(edgeObj => {
            const edgeData = g.edge(edgeObj);
            const points = edgeData.points || [];
            if (points.length < 2) return;

            const color = edgeData.flow_type === 'trigger' ? '#f59e0b' : '#06b6d4';
            const colorLight = edgeData.flow_type === 'trigger' ? '#fbbf24' : '#22d3ee';

            // Path suave pelos pontos do dagre
            let d = `M ${points[0].x} ${points[0].y}`;
            if (points.length === 2) {
                d += ` L ${points[1].x} ${points[1].y}`;
            } else {
                // Curva suave passando pelos pontos intermediários
                for (let i = 1; i < points.length - 1; i++) {
                    const curr = points[i];
                    const next = points[i + 1];
                    const midX = (curr.x + next.x) / 2;
                    const midY = (curr.y + next.y) / 2;
                    d += ` Q ${curr.x} ${curr.y}, ${midX} ${midY}`;
                }
                const last = points[points.length - 1];
                d += ` L ${last.x} ${last.y}`;
            }

            // Label com tabelas
            const mid = points[Math.floor(points.length / 2)];
            const label = edgeData.source_table && edgeData.target_table
                ? `${edgeData.source_table} → ${edgeData.target_table}` : '';

            svgEdges += `
                <path d="${d}" fill="none" stroke="${color}" stroke-width="2.5"
                      marker-end="url(#arrow-${edgeData.flow_type})" opacity="0.55"
                      stroke-linecap="round" stroke-linejoin="round"/>
            `;
            if (label) {
                svgEdges += `
                    <rect x="${mid.x - 36}" y="${mid.y - 18}" width="72" height="14" rx="3"
                          fill="var(--bs-body-bg, #fff)" opacity="0.85" style="pointer-events:none"/>
                    <text x="${mid.x}" y="${mid.y - 8}" text-anchor="middle"
                          fill="${color}" font-size="9" font-weight="600"
                          style="pointer-events:none">${label}</text>
                `;
            }
        });

        // --- Desenhar nodos ---
        let svgNodes = '';
        Object.values(nodePositions).forEach(pos => {
            const n = pos.node;
            const c = n.color || '#007bff';
            svgNodes += `
                <g transform="translate(${pos.x}, ${pos.y})" style="cursor:pointer"
                   data-action="bpSelectProcess" data-params='{"id":${n.id}}'>
                    <rect width="${nodeW}" height="${nodeH}" rx="10"
                          fill="${c}" opacity="0.1"
                          stroke="${c}" stroke-width="2"/>
                    <rect x="0" y="0" width="5" height="${nodeH}" rx="2.5"
                          fill="${c}" opacity="0.8"/>
                    <text x="${nodeW / 2 + 2}" y="${nodeH / 2 - 6}" text-anchor="middle"
                          fill="currentColor" font-size="12" font-weight="600">
                        ${n.name.length > 24 ? n.name.substring(0, 24) + '…' : n.name}
                    </text>
                    <text x="${nodeW / 2 + 2}" y="${nodeH / 2 + 10}" text-anchor="middle"
                          fill="currentColor" font-size="10" opacity="0.55">
                        ${n.module_label || n.module} · ${n.table_count || 0} tab.
                    </text>
                </g>
            `;
        });

        container.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-sitemap me-2"></i>Mapa de Fluxos do ERP</h5>
                    <div class="d-flex align-items-center gap-3">
                        <span class="d-flex align-items-center gap-1">
                            <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#f59e0b" stroke-width="2.5"/></svg>
                            <small class="text-muted">Trigger</small>
                        </span>
                        <span class="d-flex align-items-center gap-1">
                            <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#06b6d4" stroke-width="2.5"/></svg>
                            <small class="text-muted">Dados</small>
                        </span>
                    </div>
                </div>
                <div class="card-body p-2" style="overflow:auto; max-height:calc(100vh - 300px)">
                    <svg width="${svgWidth}" height="${svgHeight}" xmlns="http://www.w3.org/2000/svg"
                         style="font-family: system-ui, -apple-system, sans-serif">
                        <defs>
                            <marker id="arrow-trigger" markerWidth="8" markerHeight="6"
                                    refX="7" refY="3" orient="auto">
                                <polygon points="0 0, 8 3, 0 6" fill="#f59e0b"/>
                            </marker>
                            <marker id="arrow-data" markerWidth="8" markerHeight="6"
                                    refX="7" refY="3" orient="auto">
                                <polygon points="0 0, 8 3, 0 6" fill="#06b6d4"/>
                            </marker>
                        </defs>
                        ${svgEdges}
                        ${svgNodes}
                    </svg>
                </div>
            </div>
        `;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Erro ao carregar mapa de fluxos: ${e.message}</div>`;
    }
}

// =====================================================================
// AÇÕES (DISPATCHERS)
// =====================================================================

async function bpSwitchTab(tab) {
    bpActiveTab = tab;
    const detailTab = document.getElementById('bpTabDetail');
    if (detailTab && tab === 'detail') detailTab.style.display = 'block';
    await _bpRenderTab();
}

async function bpSelectProcess(id) {
    await _bpLoadDetail(id);
    const detailTab = document.getElementById('bpTabDetail');
    if (detailTab) detailTab.style.display = 'block';
    bpActiveTab = 'detail';
    await _bpRenderTab();
}

async function bpSeed() {
    if (!confirm('Carregar processos padrão do Protheus?\nProcessos já existentes serão ignorados.')) return;
    try {
        const result = await apiRequest('/processes/seed', 'POST');
        showNotification(result.message || 'Seed concluído', 'success');
        await showProcesses();
    } catch (e) {
        showNotification('Erro no seed: ' + e.message, 'error');
    }
}

function bpShowCreate() {
    _bpShowFormModal(null);
}

async function bpEdit(id) {
    try {
        const proc = await apiRequest(`/processes/${id}`);
        _bpShowFormModal(proc);
    } catch (e) {
        showNotification('Erro ao carregar processo: ' + e.message, 'error');
    }
}

async function bpSave() {
    const form = document.getElementById('bpForm');
    if (!form) return;

    const id = form.dataset.processId;
    const data = {
        name: document.getElementById('bpFormName').value.trim(),
        description: document.getElementById('bpFormDesc').value.trim(),
        module: document.getElementById('bpFormModule').value,
        module_label: document.getElementById('bpFormModule').selectedOptions[0]?.text || '',
        icon: document.getElementById('bpFormIcon').value || 'fa-cogs',
        color: document.getElementById('bpFormColor').value || '#007bff',
        status: document.getElementById('bpFormStatus').value,
    };

    if (!data.name || !data.module) {
        showNotification('Nome e módulo são obrigatórios', 'error');
        return;
    }

    try {
        if (id) {
            await apiRequest(`/processes/${id}`, 'PUT', data);
            showNotification('Processo atualizado!', 'success');
            _bpCloseModal();
            await showProcesses();
        } else {
            var result = await apiRequest('/processes', 'POST', data);
            showNotification('Processo criado! Vincule tabelas e fluxos.', 'success');
            _bpCloseModal();
            await showProcesses();
            // Redirecionar para detalhe do processo recem-criado
            if (result && result.id) {
                bpSelectProcess(result.id);
            }
        }
    } catch (e) {
        showNotification('Erro ao salvar: ' + e.message, 'error');
    }
}

async function bpDelete(id) {
    if (!confirm('Tem certeza que deseja excluir este processo?')) return;
    try {
        await apiRequest(`/processes/${id}`, 'DELETE');
        showNotification('Processo removido!', 'success');
        if (bpSelectedProcess && bpSelectedProcess.id == id) {
            bpSelectedProcess = null;
            bpActiveTab = 'list';
        }
        await showProcesses();
    } catch (e) {
        showNotification('Erro ao excluir: ' + e.message, 'error');
    }
}

async function bpAutoMapFields(tableId, connectionId) {
    try {
        const result = await apiRequest(`/process-tables/${tableId}/fields/auto-map`, 'POST', {
            connection_id: connectionId,
        });
        showNotification(result.message || 'Campos importados!', 'success');
        if (bpSelectedProcess) {
            await _bpLoadDetail(bpSelectedProcess.id);
            await _bpRenderTab();
        }
    } catch (e) {
        showNotification('Erro ao importar campos: ' + e.message, 'error');
    }
}

async function bpRemoveTable(tableId) {
    if (!bpSelectedProcess) return;
    if (!confirm('Remover esta tabela do processo?')) return;
    try {
        await apiRequest(`/processes/${bpSelectedProcess.id}/tables/${tableId}`, 'DELETE');
        showNotification('Tabela removida!', 'success');
        await _bpLoadDetail(bpSelectedProcess.id);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

function bpShowAddTable(processId) {
    _bpShowAddTableModal(processId);
}

async function bpShowAddFlow(processId) {
    // Buscar lista de todos os processos para o dropdown de destino/origem
    var allProcesses = [];
    try {
        allProcesses = await apiRequest('/processes');
    } catch (e) { /* sem processos */ }

    var processOptions = allProcesses
        .filter(function(p) { return p.id !== processId; })
        .map(function(p) {
            return '<option value="' + p.id + '">' + escapeHtml(p.name) + ' (' + (p.module_label || p.module) + ')</option>';
        }).join('');

    var currentProcess = allProcesses.find(function(p) { return p.id === processId; });
    var currentName = currentProcess ? currentProcess.name : 'Processo #' + processId;

    // Tabelas do processo atual para dropdown de tabela origem
    var tables = (bpSelectedProcess && bpSelectedProcess.tables) || [];
    var tableOptions = tables.map(function(t) {
        return '<option value="' + escapeHtml(t.table_name) + '">' + escapeHtml(t.table_name) + '</option>';
    }).join('');

    var modalHtml = `
        <div class="modal fade" id="bpModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-exchange-alt me-2"></i>Novo Fluxo</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="bpAddFlowForm" data-process-id="${processId}">
                            <div class="mb-3">
                                <label class="form-label">Direcao do fluxo *</label>
                                <select class="form-select" id="bpFlowDirection">
                                    <option value="outgoing">Saida: ${escapeHtml(currentName)} → outro processo</option>
                                    <option value="incoming">Entrada: outro processo → ${escapeHtml(currentName)}</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Processo conectado *</label>
                                <select class="form-select" id="bpFlowTargetProcess">
                                    <option value="">Selecione...</option>
                                    ${processOptions}
                                </select>
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Tabela origem</label>
                                    <input type="text" class="form-control" id="bpFlowSourceTable" placeholder="Ex: SC7" list="bpFlowTableList">
                                    <datalist id="bpFlowTableList">
                                        ${tableOptions}
                                    </datalist>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Tabela destino</label>
                                    <input type="text" class="form-control" id="bpFlowTargetTable" placeholder="Ex: SF1">
                                </div>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Tipo de fluxo</label>
                                <select class="form-select" id="bpFlowType">
                                    <option value="data">Dados</option>
                                    <option value="trigger">Trigger</option>
                                    <option value="dependency">Dependencia</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Descricao</label>
                                <input type="text" class="form-control" id="bpFlowDesc" placeholder="Ex: Pedido de compra gera nota de entrada">
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="bpSaveFlow">
                            <i class="fas fa-link me-1"></i> Criar Fluxo
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    _bpInjectModal(modalHtml);
}

async function bpSaveFlow() {
    var form = document.getElementById('bpAddFlowForm');
    if (!form) return;

    var processId = parseInt(form.dataset.processId);
    var direction = document.getElementById('bpFlowDirection').value;
    var targetProcessId = parseInt(document.getElementById('bpFlowTargetProcess').value);
    var sourceTable = document.getElementById('bpFlowSourceTable').value.trim();
    var targetTable = document.getElementById('bpFlowTargetTable').value.trim();
    var flowType = document.getElementById('bpFlowType').value;
    var description = document.getElementById('bpFlowDesc').value.trim();

    if (!targetProcessId) {
        showNotification('Selecione o processo conectado', 'error');
        return;
    }

    var data = {
        source_process_id: direction === 'outgoing' ? processId : targetProcessId,
        target_process_id: direction === 'outgoing' ? targetProcessId : processId,
        source_table: sourceTable,
        target_table: targetTable,
        flow_type: flowType,
        description: description,
    };

    try {
        await apiRequest('/process-flows', 'POST', data);
        showNotification('Fluxo criado!', 'success');
        _bpCloseModal();
        await _bpLoadDetail(processId);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function bpEditField(fieldId) {
    if (!bpSelectedProcess) return;
    // Buscar o campo nos dados carregados
    var field = null;
    for (var t of (bpSelectedProcess.tables || [])) {
        for (var f of (t.fields || [])) {
            if (f.id === fieldId) { field = f; break; }
        }
        if (field) break;
    }
    if (!field) return;

    var modalHtml = `
        <div class="modal fade" id="bpModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-pen me-2"></i>Editar Campo</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="bpEditFieldForm" data-field-id="${field.id}">
                            <div class="mb-3">
                                <label class="form-label">Campo</label>
                                <input type="text" class="form-control" value="${escapeHtml(field.column_name)}" disabled>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Descricao</label>
                                <input type="text" class="form-control" id="bpEditFieldLabel" value="${escapeHtml(field.column_label || '')}" placeholder="Ex: Numero da NF">
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="bpEditFieldKey" ${field.is_key ? 'checked' : ''}>
                                        <label class="form-check-label" for="bpEditFieldKey">
                                            <i class="fas fa-key text-warning me-1"></i>Campo chave do fluxo
                                        </label>
                                    </div>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="bpEditFieldRequired" ${field.is_required ? 'checked' : ''}>
                                        <label class="form-check-label" for="bpEditFieldRequired">
                                            <i class="fas fa-asterisk text-danger me-1"></i>Obrigatorio
                                        </label>
                                    </div>
                                </div>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Regra de Negocio</label>
                                <textarea class="form-control" id="bpEditFieldRule" rows="2" placeholder="Ex: Validado contra SA2 (fornecedor)">${escapeHtml(field.business_rule || '')}</textarea>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="bpUpdateField">
                            <i class="fas fa-save me-1"></i> Salvar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    _bpInjectModal(modalHtml);
}

async function bpUpdateField() {
    var form = document.getElementById('bpEditFieldForm');
    if (!form) return;
    var fieldId = form.dataset.fieldId;

    var data = {
        column_label: document.getElementById('bpEditFieldLabel').value.trim(),
        is_key: document.getElementById('bpEditFieldKey').checked,
        is_required: document.getElementById('bpEditFieldRequired').checked,
        business_rule: document.getElementById('bpEditFieldRule').value.trim(),
    };

    try {
        await apiRequest('/process-fields/' + fieldId, 'PUT', data);
        showNotification('Campo atualizado!', 'success');
        _bpCloseModal();
        await _bpLoadDetail(bpSelectedProcess.id);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function bpDeleteField(fieldId) {
    if (!confirm('Remover este campo do processo?')) return;
    try {
        await apiRequest('/process-fields/' + fieldId, 'DELETE');
        showNotification('Campo removido!', 'success');
        await _bpLoadDetail(bpSelectedProcess.id);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function bpEditTable(tableId) {
    if (!bpSelectedProcess) return;
    var tbl = (bpSelectedProcess.tables || []).find(function(t) { return t.id === tableId; });
    if (!tbl) return;

    var modalHtml = `
        <div class="modal fade" id="bpModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-pen me-2"></i>Editar Tabela Vinculada</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="bpEditTableForm" data-table-id="${tbl.id}" data-process-id="${bpSelectedProcess.id}">
                            <div class="mb-3">
                                <label class="form-label">Tabela</label>
                                <input type="text" class="form-control" value="${escapeHtml(tbl.table_name)}" disabled>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Descricao</label>
                                <input type="text" class="form-control" id="bpEditTableAlias" value="${escapeHtml(tbl.table_alias || '')}">
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Papel no Processo</label>
                                <select class="form-select" id="bpEditTableRole">
                                    <option value="principal" ${tbl.table_role === 'principal' ? 'selected' : ''}>Principal</option>
                                    <option value="auxiliar" ${tbl.table_role === 'auxiliar' ? 'selected' : ''}>Auxiliar</option>
                                    <option value="relacionada" ${tbl.table_role === 'relacionada' ? 'selected' : ''}>Relacionada</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Observacao</label>
                                <input type="text" class="form-control" id="bpEditTableDesc" value="${escapeHtml(tbl.description || '')}">
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="bpUpdateTable">
                            <i class="fas fa-save me-1"></i> Salvar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    _bpInjectModal(modalHtml);
}

async function bpUpdateTable() {
    var form = document.getElementById('bpEditTableForm');
    if (!form) return;
    var tableId = form.dataset.tableId;
    var processId = form.dataset.processId;

    var data = {
        table_alias: document.getElementById('bpEditTableAlias').value.trim(),
        table_role: document.getElementById('bpEditTableRole').value,
        description: document.getElementById('bpEditTableDesc').value.trim(),
    };

    try {
        await apiRequest('/processes/' + processId + '/tables/' + tableId, 'PUT', data);
        showNotification('Tabela atualizada!', 'success');
        _bpCloseModal();
        await _bpLoadDetail(parseInt(processId));
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function bpEditFlow(flowId) {
    if (!bpSelectedProcess) return;
    var flow = (bpSelectedProcess.flows || []).find(function(f) { return f.id === flowId; });
    if (!flow) return;

    var modalHtml = `
        <div class="modal fade" id="bpModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-pen me-2"></i>Editar Fluxo</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="bpEditFlowForm" data-flow-id="${flow.id}">
                            <div class="mb-3">
                                <label class="form-label">Conexao</label>
                                <input type="text" class="form-control" value="${escapeHtml(flow.source_name || '')} → ${escapeHtml(flow.target_name || '')}" disabled>
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Tabela origem</label>
                                    <input type="text" class="form-control" id="bpEditFlowSourceTable" value="${escapeHtml(flow.source_table || '')}">
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Tabela destino</label>
                                    <input type="text" class="form-control" id="bpEditFlowTargetTable" value="${escapeHtml(flow.target_table || '')}">
                                </div>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Tipo de fluxo</label>
                                <select class="form-select" id="bpEditFlowType">
                                    <option value="data" ${flow.flow_type === 'data' ? 'selected' : ''}>Dados</option>
                                    <option value="trigger" ${flow.flow_type === 'trigger' ? 'selected' : ''}>Trigger</option>
                                    <option value="dependency" ${flow.flow_type === 'dependency' ? 'selected' : ''}>Dependencia</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Descricao</label>
                                <input type="text" class="form-control" id="bpEditFlowDesc" value="${escapeHtml(flow.description || '')}">
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="bpUpdateFlow">
                            <i class="fas fa-save me-1"></i> Salvar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    _bpInjectModal(modalHtml);
}

async function bpUpdateFlow() {
    var form = document.getElementById('bpEditFlowForm');
    if (!form) return;
    var flowId = form.dataset.flowId;

    var data = {
        source_table: document.getElementById('bpEditFlowSourceTable').value.trim(),
        target_table: document.getElementById('bpEditFlowTargetTable').value.trim(),
        flow_type: document.getElementById('bpEditFlowType').value,
        description: document.getElementById('bpEditFlowDesc').value.trim(),
    };

    try {
        await apiRequest('/process-flows/' + flowId, 'PUT', data);
        showNotification('Fluxo atualizado!', 'success');
        _bpCloseModal();
        await _bpLoadDetail(bpSelectedProcess.id);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function bpDeleteFlow(flowId) {
    if (!confirm('Remover este fluxo?')) return;
    try {
        await apiRequest('/process-flows/' + flowId, 'DELETE');
        showNotification('Fluxo removido!', 'success');
        await _bpLoadDetail(bpSelectedProcess.id);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function bpSaveTable() {
    const processId = document.getElementById('bpAddTableForm')?.dataset.processId;
    if (!processId) return;

    const connId = document.getElementById('bpTableConnId')?.value;
    const tableName = document.getElementById('bpTableName')?.value.trim();

    const data = {
        table_name: tableName,
        table_alias: document.getElementById('bpTableAlias').value.trim(),
        table_role: document.getElementById('bpTableRole').value,
        description: document.getElementById('bpTableDesc')?.value.trim() || '',
        connection_id: connId ? parseInt(connId) : null,
    };

    if (!data.table_name) {
        showNotification('Selecione uma tabela', 'error');
        return;
    }

    // Coletar campos selecionados
    var selectedFields = [];
    document.querySelectorAll('.bp-field-check:checked').forEach(function(cb) {
        selectedFields.push(cb.value);
    });

    try {
        var result = await apiRequest(`/processes/${processId}/tables`, 'POST', data);
        showNotification('Tabela vinculada!', 'success');

        // Importar apenas os campos selecionados
        if (selectedFields.length > 0 && result && result.id) {
            var imported = 0;
            for (var i = 0; i < selectedFields.length; i++) {
                try {
                    await apiRequest(`/process-tables/${result.id}/fields`, 'POST', {
                        column_name: selectedFields[i],
                        column_label: selectedFields[i],
                        sort_order: i,
                    });
                    imported++;
                } catch (e2) { /* campo duplicado ou erro, ignora */ }
            }
            showNotification(imported + ' campo(s) vinculado(s)', 'success');
        }

        _bpCloseModal();
        await _bpLoadDetail(processId);
        await _bpRenderTab();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// MODAIS
// =====================================================================

function _bpShowFormModal(proc) {
    const isEdit = !!proc;
    const moduleOptions = bpModules.map(m =>
        `<option value="${m.code}" ${proc && proc.module === m.code ? 'selected' : ''}>${m.label}</option>`
    ).join('');

    const modalHtml = `
        <div class="modal fade" id="bpModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${isEdit ? 'Editar' : 'Novo'} Processo</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="bpForm" data-process-id="${proc ? proc.id : ''}">
                            <div class="mb-3">
                                <label class="form-label">Nome *</label>
                                <input type="text" class="form-control" id="bpFormName" value="${proc ? proc.name : ''}" required>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Descrição</label>
                                <textarea class="form-control" id="bpFormDesc" rows="3">${proc ? proc.description || '' : ''}</textarea>
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Módulo *</label>
                                    <select class="form-select" id="bpFormModule" required>
                                        <option value="">Selecione...</option>
                                        ${moduleOptions}
                                    </select>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Status</label>
                                    <select class="form-select" id="bpFormStatus">
                                        <option value="active" ${proc && proc.status === 'active' ? 'selected' : ''}>Ativo</option>
                                        <option value="draft" ${proc && proc.status === 'draft' ? 'selected' : ''}>Rascunho</option>
                                        <option value="archived" ${proc && proc.status === 'archived' ? 'selected' : ''}>Arquivado</option>
                                    </select>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Icone</label>
                                    <div class="input-group">
                                        <span class="input-group-text" id="bpFormIconPreview" style="min-width:42px;justify-content:center;">
                                            <i class="fas ${proc ? proc.icon || 'fa-cogs' : 'fa-cogs'}"></i>
                                        </span>
                                        <input type="text" class="form-control" id="bpFormIcon" value="${proc ? proc.icon || 'fa-cogs' : 'fa-cogs'}" placeholder="fa-cogs" readonly>
                                        <button class="btn btn-outline-secondary" type="button" data-action="bpOpenIconPicker" title="Selecionar icone">
                                            <i class="fas fa-th"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Cor</label>
                                    <input type="color" class="form-control form-control-color" id="bpFormColor" value="${proc ? proc.color || '#007bff' : '#007bff'}">
                                </div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="bpSave">
                            <i class="fas fa-save me-1"></i> Salvar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    _bpInjectModal(modalHtml);
}

async function _bpShowAddTableModal(processId) {
    // Buscar conexoes do ambiente ativo
    var envId = sessionStorage.getItem('active_environment_id');
    var connections = [];
    try {
        connections = await apiRequest('/db-connections?environment_id=' + (envId || ''));
    } catch (e) { /* sem conexoes */ }

    var connOptions = connections.map(function(c) {
        return '<option value="' + c.id + '">' + escapeHtml(c.name) + ' (' + c.driver + ')</option>';
    }).join('');

    var modalHtml = `
        <div class="modal fade" id="bpModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Vincular Tabela ao Processo</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="bpAddTableForm" data-process-id="${processId}">
                            <div class="mb-3">
                                <label class="form-label">Conexao do Banco *</label>
                                <select class="form-select" id="bpTableConnId">
                                    <option value="">Selecione uma conexao...</option>
                                    ${connOptions}
                                </select>
                                <small class="form-text text-muted">Selecione a conexao para buscar as tabelas do schema_cache</small>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Tabela *</label>
                                <div class="input-group">
                                    <input type="text" class="form-control" id="bpTableSearch" placeholder="Digite para buscar tabelas..." disabled>
                                    <button class="btn btn-outline-secondary" type="button" id="bpTableSearchBtn" disabled>
                                        <i class="fas fa-search"></i>
                                    </button>
                                </div>
                                <div id="bpTableResults" class="d-none mt-1" style="max-height:200px;overflow-y:auto;"></div>
                                <input type="hidden" id="bpTableName">
                                <input type="hidden" id="bpTableFullName">
                            </div>
                            <div id="bpTableSelectedInfo" class="d-none mb-3">
                                <div class="alert alert-info py-2 mb-0">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <div>
                                            <i class="fas fa-table me-1"></i>
                                            <strong id="bpTableSelectedAlias"></strong>
                                            <span class="text-muted ms-2" id="bpTableSelectedFull"></span>
                                        </div>
                                        <button type="button" class="btn btn-sm btn-outline-danger" id="bpTableClearBtn">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Descricao da Tabela</label>
                                <input type="text" class="form-control" id="bpTableAlias" placeholder="Ex: Pedidos de Venda">
                            </div>
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Papel no Processo</label>
                                    <select class="form-select" id="bpTableRole">
                                        <option value="principal">Principal</option>
                                        <option value="auxiliar">Auxiliar</option>
                                        <option value="relacionada">Relacionada</option>
                                    </select>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Observacao</label>
                                    <input type="text" class="form-control" id="bpTableDesc" placeholder="Opcional">
                                </div>
                            </div>
                            <div id="bpFieldsSection" class="d-none">
                                <label class="form-label"><i class="fas fa-columns me-1"></i>Campos a vincular</label>
                                <div class="input-group input-group-sm mb-1">
                                    <input type="text" class="form-control" id="bpFieldSearch" placeholder="Filtrar campos...">
                                    <button class="btn btn-outline-secondary" type="button" id="bpFieldSelectAll" title="Selecionar todos">
                                        <i class="fas fa-check-double"></i>
                                    </button>
                                    <button class="btn btn-outline-secondary" type="button" id="bpFieldSelectNone" title="Limpar selecao">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                                <div id="bpFieldsList" style="max-height:180px;overflow-y:auto;border:1px solid #dee2e6;border-radius:4px;padding:4px;"></div>
                                <small class="form-text text-muted" id="bpFieldsCount"></small>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="bpSaveTable">
                            <i class="fas fa-link me-1"></i> Vincular
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    _bpInjectModal(modalHtml);

    // Ao selecionar conexao, habilitar busca
    var connSelect = document.getElementById('bpTableConnId');
    var searchInput = document.getElementById('bpTableSearch');
    var searchBtn = document.getElementById('bpTableSearchBtn');
    var resultsDiv = document.getElementById('bpTableResults');

    connSelect.addEventListener('change', function() {
        var enabled = !!this.value;
        searchInput.disabled = !enabled;
        searchBtn.disabled = !enabled;
        if (enabled) {
            searchInput.focus();
            searchInput.value = '';
            _bpClearTableSelection();
        }
    });

    // Busca de tabelas ao digitar (debounce)
    var searchTimer = null;
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimer);
        var q = this.value.trim();
        if (q.length < 2) { resultsDiv.className = 'd-none'; return; }
        searchTimer = setTimeout(function() { _bpSearchTables(connSelect.value, q); }, 300);
    });

    searchBtn.addEventListener('click', function() {
        var q = searchInput.value.trim();
        if (q.length >= 1) _bpSearchTables(connSelect.value, q);
    });

    // Limpar selecao
    document.getElementById('bpTableClearBtn')?.addEventListener('click', _bpClearTableSelection);

    // Auto-selecionar primeira conexao se so tem uma
    if (connections.length === 1) {
        connSelect.value = connections[0].id;
        connSelect.dispatchEvent(new Event('change'));
    }
}

function _bpClearTableSelection() {
    document.getElementById('bpTableName').value = '';
    document.getElementById('bpTableFullName').value = '';
    document.getElementById('bpTableAlias').value = '';
    document.getElementById('bpTableSelectedInfo').className = 'd-none mb-3';
    document.getElementById('bpTableSearch').value = '';
    document.getElementById('bpTableSearch').disabled = false;
    document.getElementById('bpTableResults').className = 'd-none';
    document.getElementById('bpFieldsSection').className = 'd-none';
}

async function _bpSearchTables(connId, search) {
    var resultsDiv = document.getElementById('bpTableResults');
    if (!connId || !search) return;

    try {
        var tables = await apiRequest('/db-connections/' + connId + '/tables?search=' + encodeURIComponent(search));
        if (!tables || tables.length === 0) {
            resultsDiv.className = 'mt-1';
            resultsDiv.innerHTML = '<small class="text-muted p-2 d-block">Nenhuma tabela encontrada. Execute "Descobrir Tabelas" no modulo Banco de Dados primeiro.</small>';
            return;
        }

        var html = '<div class="list-group list-group-flush">';
        for (var i = 0; i < Math.min(tables.length, 50); i++) {
            var t = tables[i];
            // Extrair alias sem sufixo de empresa (ex: SC7010 -> SC7)
            var alias = t.table_alias || _bpExtractAlias(t.table_name);
            html += '<button type="button" class="list-group-item list-group-item-action py-1 px-2 bp-table-option" '
                + 'data-table-full="' + escapeHtml(t.table_name) + '" '
                + 'data-table-alias="' + escapeHtml(alias) + '">'
                + '<code class="text-primary me-2">' + escapeHtml(alias) + '</code>'
                + '<small class="text-muted">' + escapeHtml(t.table_name) + '</small>'
                + '</button>';
        }
        if (tables.length > 50) {
            html += '<small class="text-muted p-2 d-block">Mostrando 50 de ' + tables.length + ' resultados. Refine a busca.</small>';
        }
        html += '</div>';
        resultsDiv.className = 'mt-1 border rounded';
        resultsDiv.style.maxHeight = '200px';
        resultsDiv.style.overflowY = 'auto';
        resultsDiv.innerHTML = html;

        // Click handler nas opcoes
        resultsDiv.querySelectorAll('.bp-table-option').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var fullName = this.dataset.tableFull;
                var alias = this.dataset.tableAlias;
                var connId = document.getElementById('bpTableConnId').value;
                document.getElementById('bpTableName').value = alias;
                document.getElementById('bpTableFullName').value = fullName;
                document.getElementById('bpTableSelectedAlias').textContent = alias;
                document.getElementById('bpTableSelectedFull').textContent = '(' + fullName + ')';
                document.getElementById('bpTableSelectedInfo').className = 'mb-3';
                resultsDiv.className = 'd-none';
                document.getElementById('bpTableSearch').disabled = true;

                // Buscar descricao na SX2 do banco
                _bpFetchSX2Description(connId, alias);
                // Carregar campos da tabela para selecao
                _bpLoadFieldsForSelection(connId, fullName);
            });
        });
    } catch (e) {
        resultsDiv.className = 'mt-1';
        resultsDiv.innerHTML = '<small class="text-danger p-2 d-block">Erro: ' + escapeHtml(e.message) + '</small>';
    }
}

async function _bpFetchSX2Description(connId, alias) {
    var descInput = document.getElementById('bpTableAlias');
    if (!connId || !alias) return;
    descInput.placeholder = 'Buscando na SX2...';
    try {
        var resp = await apiRequest('/processes/sx2-lookup?connection_id=' + connId + '&alias=' + encodeURIComponent(alias));
        if (resp.description) {
            descInput.value = resp.description;
            descInput.placeholder = 'Ex: Pedidos de Venda';
        } else {
            descInput.placeholder = 'SX2: nao encontrado. Digite manualmente.';
            console.warn('SX2 lookup sem resultado:', resp);
        }
    } catch (e) {
        descInput.placeholder = 'Erro ao buscar SX2. Digite manualmente.';
        console.error('SX2 lookup erro:', e);
    }
}

async function _bpLoadFieldsForSelection(connId, tableName) {
    var section = document.getElementById('bpFieldsSection');
    var listDiv = document.getElementById('bpFieldsList');
    var countSpan = document.getElementById('bpFieldsCount');
    if (!section || !listDiv) return;

    section.className = '';
    listDiv.innerHTML = '<small class="text-muted"><i class="fas fa-spinner fa-spin me-1"></i>Carregando campos...</small>';

    try {
        var columns = await apiRequest('/db-connections/' + connId + '/tables/' + encodeURIComponent(tableName) + '/columns');
        if (!columns || columns.length === 0) {
            listDiv.innerHTML = '<small class="text-muted">Nenhum campo encontrado no cache. Execute "Descobrir Tabelas" primeiro.</small>';
            return;
        }

        var html = '';
        for (var i = 0; i < columns.length; i++) {
            var col = columns[i];
            var isKey = col.is_key ? ' <i class="fas fa-key text-warning" title="Chave"></i>' : '';
            var typeInfo = col.column_type || '';
            if (col.column_size) typeInfo += '(' + col.column_size + ')';
            html += '<div class="form-check py-0 bp-field-item" data-field="' + escapeHtml(col.column_name) + '">'
                + '<input class="form-check-input bp-field-check" type="checkbox" value="' + escapeHtml(col.column_name) + '" id="bpField_' + i + '">'
                + '<label class="form-check-label small" for="bpField_' + i + '">'
                + '<code>' + escapeHtml(col.column_name) + '</code>'
                + isKey
                + ' <span class="text-muted">' + escapeHtml(typeInfo) + '</span>'
                + '</label></div>';
        }
        listDiv.innerHTML = html;
        _bpUpdateFieldCount();

        // Filtro de campos
        document.getElementById('bpFieldSearch')?.addEventListener('input', function() {
            var q = this.value.toLowerCase();
            listDiv.querySelectorAll('.bp-field-item').forEach(function(item) {
                item.style.display = item.dataset.field.toLowerCase().includes(q) ? '' : 'none';
            });
        });

        // Selecionar todos / nenhum
        document.getElementById('bpFieldSelectAll')?.addEventListener('click', function() {
            listDiv.querySelectorAll('.bp-field-check').forEach(function(cb) {
                if (cb.closest('.bp-field-item').style.display !== 'none') cb.checked = true;
            });
            _bpUpdateFieldCount();
        });
        document.getElementById('bpFieldSelectNone')?.addEventListener('click', function() {
            listDiv.querySelectorAll('.bp-field-check').forEach(function(cb) { cb.checked = false; });
            _bpUpdateFieldCount();
        });

        // Atualizar contador ao clicar
        listDiv.addEventListener('change', _bpUpdateFieldCount);
    } catch (e) {
        listDiv.innerHTML = '<small class="text-danger">Erro: ' + escapeHtml(e.message) + '</small>';
    }
}

function _bpUpdateFieldCount() {
    var checks = document.querySelectorAll('.bp-field-check');
    var selected = document.querySelectorAll('.bp-field-check:checked');
    var countSpan = document.getElementById('bpFieldsCount');
    if (countSpan) countSpan.textContent = selected.length + ' de ' + checks.length + ' campos selecionados';
}

function _bpExtractAlias(tableName) {
    // Extrai alias Protheus removendo sufixo de empresa (digitos no final)
    // SC7010 -> SC7, SA1010 -> SA1, ZZ4010 -> ZZ4, MYTABLE123 -> MYTABLE123
    // Padrao Protheus: 3 chars (letra+letra+alfanum) + sufixo numerico (3+ digitos)
    var match = tableName.match(/^([A-Z][A-Z0-9][A-Z0-9])\d{3,}$/i);
    if (match) return match[1].toUpperCase();
    return tableName;
}

function _bpInjectModal(html) {
    // Remove modal anterior se existir
    const old = document.getElementById('bpModal');
    if (old) old.remove();

    document.body.insertAdjacentHTML('beforeend', html);
    const modal = new bootstrap.Modal(document.getElementById('bpModal'));
    modal.show();

    // Preview do icone ao digitar
    var iconInput = document.getElementById('bpFormIcon');
    var iconPreview = document.getElementById('bpFormIconPreview');
    if (iconInput && iconPreview) {
        iconInput.addEventListener('input', function() {
            iconPreview.innerHTML = '<i class="fas ' + this.value + '"></i>';
        });
    }
}

// Catalogo de icones organizados por categoria (FontAwesome 5 Free)
var _bpIconCatalog = {
    'Financeiro': ['fa-dollar-sign','fa-money-bill-wave','fa-credit-card','fa-receipt','fa-file-invoice-dollar','fa-coins','fa-piggy-bank','fa-wallet','fa-hand-holding-usd','fa-chart-line','fa-percentage','fa-calculator','fa-balance-scale','fa-university','fa-landmark'],
    'Compras': ['fa-shopping-cart','fa-truck','fa-boxes','fa-clipboard-list','fa-file-contract','fa-handshake','fa-store','fa-shipping-fast','fa-dolly','fa-pallet','fa-warehouse','fa-barcode'],
    'Vendas': ['fa-cash-register','fa-tags','fa-shopping-bag','fa-cart-plus','fa-store-alt','fa-chart-bar','fa-funnel-dollar','fa-file-invoice','fa-user-tie','fa-bullhorn','fa-percentage','fa-medal'],
    'Estoque': ['fa-box','fa-box-open','fa-cubes','fa-archive','fa-weight','fa-clipboard-check','fa-exchange-alt','fa-layer-group','fa-th-list','fa-qrcode','fa-pallet','fa-dolly-flatbed'],
    'Fiscal': ['fa-file-alt','fa-stamp','fa-gavel','fa-balance-scale-right','fa-book','fa-scroll','fa-paste','fa-tasks','fa-check-double','fa-file-signature','fa-certificate','fa-shield-alt'],
    'Producao': ['fa-industry','fa-hard-hat','fa-tools','fa-wrench','fa-cog','fa-cogs','fa-hammer','fa-screwdriver','fa-drafting-compass','fa-ruler','fa-project-diagram','fa-sitemap'],
    'RH': ['fa-users','fa-user','fa-user-plus','fa-id-card','fa-id-badge','fa-user-clock','fa-user-shield','fa-people-carry','fa-user-graduate','fa-briefcase','fa-building','fa-calendar-alt'],
    'TI / Sistema': ['fa-server','fa-database','fa-hdd','fa-network-wired','fa-code','fa-terminal','fa-laptop-code','fa-bug','fa-shield-alt','fa-lock','fa-key','fa-cloud','fa-sync-alt','fa-plug','fa-microchip','fa-robot'],
    'Documentos': ['fa-file','fa-folder','fa-folder-open','fa-file-pdf','fa-file-excel','fa-file-word','fa-file-csv','fa-file-code','fa-file-archive','fa-paperclip','fa-print','fa-envelope'],
    'Geral': ['fa-home','fa-star','fa-heart','fa-flag','fa-bell','fa-globe','fa-map-marker-alt','fa-phone','fa-comment','fa-info-circle','fa-question-circle','fa-exclamation-triangle','fa-check-circle','fa-times-circle','fa-search','fa-eye'],
};

function bpOpenIconPicker() {
    var old = document.getElementById('bpIconPickerModal');
    if (old) old.remove();

    var categoriesHtml = '';
    for (var cat in _bpIconCatalog) {
        var iconsHtml = _bpIconCatalog[cat].map(function(icon) {
            return '<button type="button" class="btn btn-outline-secondary m-1 bp-icon-btn" data-icon="' + icon + '" style="width:44px;height:44px;padding:0;" title="' + icon + '"><i class="fas ' + icon + '" style="font-size:18px;"></i></button>';
        }).join('');
        categoriesHtml += '<div class="mb-2"><small class="text-muted fw-bold">' + cat + '</small><div class="d-flex flex-wrap">' + iconsHtml + '</div></div>';
    }

    var html = '<div class="modal fade" id="bpIconPickerModal" tabindex="-1">'
        + '<div class="modal-dialog modal-lg">'
        + '<div class="modal-content">'
        + '<div class="modal-header py-2">'
        + '<h6 class="modal-title"><i class="fas fa-th me-2"></i>Selecionar Icone</h6>'
        + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>'
        + '</div>'
        + '<div class="modal-body" style="max-height:60vh;overflow-y:auto;">'
        + '<input type="text" class="form-control form-control-sm mb-3" id="bpIconSearch" placeholder="Buscar icone...">'
        + '<div id="bpIconGrid">' + categoriesHtml + '</div>'
        + '</div>'
        + '</div></div></div>';

    document.body.insertAdjacentHTML('beforeend', html);
    var pickerModal = new bootstrap.Modal(document.getElementById('bpIconPickerModal'));
    pickerModal.show();

    // Busca
    document.getElementById('bpIconSearch').addEventListener('input', function() {
        var q = this.value.toLowerCase();
        var btns = document.querySelectorAll('.bp-icon-btn');
        btns.forEach(function(btn) {
            var iconName = btn.getAttribute('data-icon');
            btn.style.display = iconName.includes(q) ? '' : 'none';
        });
    });

    // Selecao do icone
    document.getElementById('bpIconGrid').addEventListener('click', function(e) {
        var btn = e.target.closest('.bp-icon-btn');
        if (!btn) return;
        var icon = btn.getAttribute('data-icon');
        var input = document.getElementById('bpFormIcon');
        var preview = document.getElementById('bpFormIconPreview');
        if (input) input.value = icon;
        if (preview) preview.innerHTML = '<i class="fas ' + icon + '"></i>';
        pickerModal.hide();
    });
}

function _bpCloseModal() {
    const el = document.getElementById('bpModal');
    if (el) {
        const modal = bootstrap.Modal.getInstance(el);
        if (modal) modal.hide();
    }
}

// =====================================================================
// UTILITÁRIOS
// =====================================================================

function _bpDebounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}
