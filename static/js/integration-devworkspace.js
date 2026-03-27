// =====================================================================
// INTEGRATION-DEVWORKSPACE.JS
// Modulo de Desenvolvimento Assistido (Dev Workspace)
// 4 abas: Navegador de Fontes, Analise de Impacto, Compilacao, Politicas
// =====================================================================

// ===== ESTADO LOCAL DO MODULO =====
let dwActiveTab = 'browser';
let dwCurrentPath = '';
let dwBrowseItems = [];
let dwFileContent = null;
let dwSearchResults = null;
let dwImpactResult = null;
let dwDiffResult = null;
let dwPolicies = [];
let dwRepos = [];
let dwBranches = [];

// Keywords AdvPL para syntax highlight basico
const ADVPL_KEYWORDS = [
    'Function', 'Static', 'User', 'Return', 'Local', 'Private', 'Public',
    'Default', 'If', 'ElseIf', 'Else', 'EndIf', 'Do', 'While', 'EndDo',
    'For', 'To', 'Next', 'Do Case', 'Case', 'Otherwise', 'EndCase',
    'Begin Sequence', 'End Sequence', 'Recover', 'Using',
    'Class', 'EndClass', 'Method', 'Data', 'From',
    '#include', '#define', '#ifdef', '#ifndef', '#endif',
    'DbSelectArea', 'DbSetOrder', 'DbSeek', 'DbSkip', 'DbGoTop',
    'MsExecAuto', 'Processa', 'ProcRegua', 'IncProc',
    '.T.', '.F.', 'NIL', '.And.', '.Or.', '.Not.'
];

// =====================================================================
// CARREGAMENTO DE DADOS
// =====================================================================

function _dwGetEnvId() {
    return parseInt(sessionStorage.getItem('active_environment_id')) || null;
}

async function dwLoadFontes(envId) {
    try {
        return await apiRequest(`/devworkspace/fontes?environment_id=${envId}`);
    } catch (e) {
        return [];
    }
}

async function dwBrowse(envId, path) {
    try {
        const resp = await apiRequest(`/devworkspace/browse?environment_id=${envId}&path=${encodeURIComponent(path || '')}`);
        return resp;
    } catch (e) {
        console.error('Erro ao navegar:', e);
        return null;
    }
}

async function dwReadFile(envId, path) {
    try {
        return await apiRequest(`/devworkspace/file?environment_id=${envId}&path=${encodeURIComponent(path)}`);
    } catch (e) {
        console.error('Erro ao ler arquivo:', e);
        return null;
    }
}

async function dwLoadRepos() {
    try {
        dwRepos = await apiRequest('/repositories');
    } catch (e) {
        dwRepos = [];
    }
}

async function dwLoadBranches(repoId) {
    try {
        dwBranches = await apiRequest(`/repositories/${repoId}/branches`);
    } catch (e) {
        dwBranches = [];
    }
}

async function dwLoadPolicies(envId) {
    try {
        const url = envId ? `/devworkspace/policies?environment_id=${envId}` : '/devworkspace/policies';
        dwPolicies = await apiRequest(url);
    } catch (e) {
        dwPolicies = [];
    }
}

// =====================================================================
// ENTRY POINT
// =====================================================================

async function showDevWorkspace() {
    // Estado do workspace
    if (!window._wsState) {
        window._wsState = { activeTab: 'setup', activeSlug: null, tabelas: [] };
    }

    document.getElementById('content-area').innerHTML =
        '<div class="content-header mb-4">' +
            '<div>' +
                '<h2><i class="fas fa-code me-2"></i>Workspace</h2>' +
                '<p class="text-muted mb-0">Engenharia reversa de ambientes Protheus (ExtraiRPO)</p>' +
            '</div>' +
        '</div>' +
        '<ul class="nav nav-tabs mb-3" id="ws-tabs">' +
            '<li class="nav-item">' +
                '<button class="nav-link active" data-action="wsSwitchTab" data-params=\'{"tab":"setup"}\'>' +
                    '<i class="fas fa-cog me-1"></i>Setup' +
                '</button>' +
            '</li>' +
            '<li class="nav-item">' +
                '<button class="nav-link" data-action="wsSwitchTab" data-params=\'{"tab":"dashboard"}\'>' +
                    '<i class="fas fa-chart-bar me-1"></i>Dashboard' +
                '</button>' +
            '</li>' +
            '<li class="nav-item">' +
                '<button class="nav-link" data-action="wsSwitchTab" data-params=\'{"tab":"explorer"}\'>' +
                    '<i class="fas fa-search me-1"></i>Explorer' +
                '</button>' +
            '</li>' +
        '</ul>' +
        '<div id="ws-tab-content"></div>';

    await wsSwitchTab({ tab: window._wsState.activeTab });
}

// =====================================================================
// WORKSPACE — TAB SWITCHING
// =====================================================================

async function wsSwitchTab(params) {
    var tab = typeof params === 'string' ? params : (params && params.tab) || 'setup';
    window._wsState.activeTab = tab;

    document.querySelectorAll('#ws-tabs .nav-link').forEach(function(el) { el.classList.remove('active'); });
    document.querySelectorAll('#ws-tabs .nav-link').forEach(function(el) {
        try {
            var p = JSON.parse(el.getAttribute('data-params') || '{}');
            if (p.tab === tab) el.classList.add('active');
        } catch(e) {}
    });

    var container = document.getElementById('ws-tab-content');
    if (!container) return;

    if (tab === 'setup') await wsRenderSetup(container);
    else if (tab === 'dashboard') await wsRenderDashboard(container);
    else if (tab === 'explorer') await wsRenderExplorer(container);
}

// =====================================================================
// WORKSPACE — SETUP TAB
// =====================================================================

async function wsRenderSetup(container) {
    container.innerHTML =
        '<div class="card">' +
            '<div class="card-body">' +
                '<h5 class="card-title mb-3">Criar / Selecionar Workspace</h5>' +
                '<div class="mb-3">' +
                    '<label class="form-label">Nome do workspace</label>' +
                    '<input type="text" class="form-control" id="ws-slug" placeholder="ex: marfrig-alimentos" value="' + (window._wsState.activeSlug || '') + '">' +
                '</div>' +
                '<div class="mb-3">' +
                    '<label class="form-label">Diretorio dos CSVs SX</label>' +
                    '<input type="text" class="form-control" id="ws-csv-dir" placeholder="C:\\caminho\\para\\csvs">' +
                '</div>' +
                '<div class="mb-3">' +
                    '<label class="form-label">Diretorio dos fontes .prw/.tlpp (opcional)</label>' +
                    '<input type="text" class="form-control" id="ws-fontes-dir" placeholder="C:\\caminho\\para\\fontes">' +
                '</div>' +
                '<div class="mb-3">' +
                    '<label class="form-label">Mapa de modulos JSON (opcional)</label>' +
                    '<input type="text" class="form-control" id="ws-mapa" placeholder="C:\\caminho\\para\\mapa-modulos.json">' +
                '</div>' +
                '<div class="d-flex gap-2 mb-3">' +
                    '<button class="btn btn-primary" data-action="wsIngestCSV">' +
                        '<i class="fas fa-upload me-1"></i>Ingerir CSVs' +
                    '</button>' +
                    '<button class="btn btn-outline-primary" data-action="wsIngestFontes">' +
                        '<i class="fas fa-file-code me-1"></i>Parsear Fontes' +
                    '</button>' +
                '</div>' +
                '<div id="ws-progress" style="display:none">' +
                    '<div class="progress mb-2"><div class="progress-bar" id="ws-progress-bar" style="width:0%"></div></div>' +
                    '<small class="text-muted" id="ws-progress-text">Aguardando...</small>' +
                '</div>' +
            '</div>' +
        '</div>' +
        '<div class="card mt-3">' +
            '<div class="card-body">' +
                '<h5 class="card-title mb-3">Workspaces existentes</h5>' +
                '<div id="ws-list"><div class="text-muted">Carregando...</div></div>' +
            '</div>' +
        '</div>';

    await wsLoadWorkspaces();
}

async function wsLoadWorkspaces() {
    try {
        var workspaces = await apiRequest('/workspace/workspaces');
        var container = document.getElementById('ws-list');
        if (!workspaces || !workspaces.length) {
            container.innerHTML = '<p class="text-muted">Nenhum workspace encontrado. Crie um acima.</p>';
            return;
        }
        container.innerHTML = workspaces.map(function(ws) {
            return '<div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" ' +
                'style="cursor:pointer" data-action="wsSelectWorkspace" data-params=\'{"slug":"' + ws.slug + '"}\'>' +
                '<div>' +
                    '<strong>' + ws.slug + '</strong><br>' +
                    '<small class="text-muted">' +
                        (ws.stats.tabelas || 0) + ' tabelas | ' +
                        (ws.stats.campos || 0) + ' campos | ' +
                        (ws.stats.fontes || 0) + ' fontes | ' +
                        (ws.stats.vinculos || 0) + ' vinculos' +
                    '</small>' +
                '</div>' +
                '<span class="badge bg-primary">' + (ws.stats.vinculos || 0) + '</span>' +
            '</div>';
        }).join('');
    } catch (e) {
        document.getElementById('ws-list').innerHTML = '<p class="text-danger">Erro ao carregar: ' + e.message + '</p>';
    }
}

async function wsSelectWorkspace(params) {
    window._wsState.activeSlug = params.slug;
    document.getElementById('ws-slug').value = params.slug;
    showToast('Workspace "' + params.slug + '" selecionado', 'success');
    await wsSwitchTab({ tab: 'dashboard' });
}

async function wsIngestCSV() {
    var slug = document.getElementById('ws-slug').value.trim();
    var csvDir = document.getElementById('ws-csv-dir').value.trim();
    if (!slug) return showToast('Informe o nome do workspace', 'warning');
    if (!csvDir) return showToast('Informe o diretorio dos CSVs', 'warning');

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '30%';
    document.getElementById('ws-progress-text').textContent = 'Ingerindo CSVs...';

    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/csv', 'POST', { csv_dir: csvDir });
        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + JSON.stringify(result.stats);
        showToast('Ingestao CSV concluida!', 'success');
        window._wsState.activeSlug = slug;
        await wsLoadWorkspaces();
    } catch (e) {
        document.getElementById('ws-progress-text').textContent = 'Erro: ' + e.message;
        showToast('Erro: ' + e.message, 'danger');
    }
}

async function wsIngestFontes() {
    var slug = document.getElementById('ws-slug').value.trim();
    var fontesDir = document.getElementById('ws-fontes-dir').value.trim();
    if (!slug) return showToast('Informe o nome do workspace', 'warning');
    if (!fontesDir) return showToast('Informe o diretorio dos fontes', 'warning');

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '20%';
    document.getElementById('ws-progress-text').textContent = 'Parseando fontes ADVPL/TLPP...';

    try {
        var data = { fontes_dir: fontesDir };
        var mapa = document.getElementById('ws-mapa').value.trim();
        if (mapa) data.mapa_modulos = mapa;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/fontes', 'POST', data);
        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent =
            'Concluido! ' + result.stats.fontes + ' fontes, ' + result.stats.chunks + ' chunks';
        showToast('Parse de fontes concluido!', 'success');
        await wsLoadWorkspaces();
    } catch (e) {
        document.getElementById('ws-progress-text').textContent = 'Erro: ' + e.message;
        showToast('Erro: ' + e.message, 'danger');
    }
}

// =====================================================================
// WORKSPACE — DASHBOARD TAB
// =====================================================================

async function wsRenderDashboard(container) {
    var slug = window._wsState.activeSlug;
    if (!slug) {
        container.innerHTML = '<div class="alert alert-info">Selecione um workspace na aba Setup.</div>';
        return;
    }

    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border spinner-border-sm"></div> Carregando...</div>';

    try {
        var stats = await apiRequest('/workspace/workspaces/' + slug + '/stats');
        var summary = await apiRequest('/workspace/workspaces/' + slug + '/explorer/summary');

        container.innerHTML =
            '<h5 class="mb-3">Workspace: <strong>' + slug + '</strong></h5>' +
            '<div class="row g-3 mb-4">' +
                wsStatCard(stats.tabelas, 'Tabelas', 'fa-table', 'primary') +
                wsStatCard(stats.campos, 'Campos', 'fa-columns', 'primary') +
                wsStatCard(stats.indices, 'Indices', 'fa-sort-amount-down', 'primary') +
                wsStatCard(stats.gatilhos, 'Gatilhos', 'fa-bolt', 'primary') +
                wsStatCard(stats.fontes, 'Fontes', 'fa-file-code', 'info') +
                wsStatCard(stats.fonte_chunks, 'Chunks', 'fa-puzzle-piece', 'info') +
                wsStatCard(stats.vinculos, 'Vinculos', 'fa-project-diagram', 'info') +
                wsStatCard(stats.menus, 'Menus', 'fa-bars', 'secondary') +
            '</div>' +
            '<div class="card">' +
                '<div class="card-body">' +
                    '<h5 class="card-title">Customizacoes</h5>' +
                    '<div class="row g-3">' +
                        wsStatCard(summary.tabelas_custom, 'Tabelas Custom', 'fa-table', 'warning') +
                        wsStatCard(summary.campos_custom, 'Campos Custom', 'fa-columns', 'warning') +
                        wsStatCard(summary.gatilhos_custom, 'Gatilhos Custom', 'fa-bolt', 'warning') +
                        wsStatCard(summary.fontes_custom, 'Fontes Custom', 'fa-file-code', 'warning') +
                        wsStatCard(summary.parametros_custom, 'Params Custom', 'fa-sliders-h', 'warning') +
                    '</div>' +
                '</div>' +
            '</div>';
    } catch (e) {
        container.innerHTML = '<div class="alert alert-danger">Erro: ' + e.message + '</div>';
    }
}

function wsStatCard(value, label, icon, color) {
    return '<div class="col-6 col-md-3">' +
        '<div class="card text-center">' +
            '<div class="card-body py-3">' +
                '<i class="fas ' + icon + ' fa-lg text-' + color + ' mb-2"></i>' +
                '<h3 class="mb-0 text-' + color + '">' + ((value || 0).toLocaleString ? (value || 0).toLocaleString() : (value || 0)) + '</h3>' +
                '<small class="text-muted">' + label + '</small>' +
            '</div>' +
        '</div>' +
    '</div>';
}

// =====================================================================
// WORKSPACE — EXPLORER TAB
// =====================================================================

async function wsRenderExplorer(container) {
    var slug = window._wsState.activeSlug;
    if (!slug) {
        container.innerHTML = '<div class="alert alert-info">Selecione um workspace na aba Setup.</div>';
        return;
    }

    container.innerHTML =
        '<div class="row">' +
            '<div class="col-md-4">' +
                '<div class="card" style="max-height:70vh;overflow-y:auto">' +
                    '<div class="card-body p-2">' +
                        '<input type="text" class="form-control form-control-sm mb-2" ' +
                            'placeholder="Buscar tabela..." id="ws-search" oninput="wsFilterTables(this.value)">' +
                        '<div id="ws-table-tree"><div class="text-muted p-2">Carregando...</div></div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="col-md-8">' +
                '<div id="ws-table-detail">' +
                    '<div class="card"><div class="card-body text-muted">Selecione uma tabela.</div></div>' +
                '</div>' +
            '</div>' +
        '</div>';

    try {
        window._wsState.tabelas = await apiRequest('/workspace/workspaces/' + slug + '/explorer/tabelas');
        wsRenderTableTree(window._wsState.tabelas);
    } catch (e) {
        document.getElementById('ws-table-tree').innerHTML = '<p class="text-danger p-2">Erro: ' + e.message + '</p>';
    }
}

function wsRenderTableTree(tabelas) {
    var tree = document.getElementById('ws-table-tree');
    if (!tabelas || !tabelas.length) {
        tree.innerHTML = '<p class="text-muted p-2">Nenhuma tabela.</p>';
        return;
    }
    tree.innerHTML = tabelas.map(function(t) {
        var badge = t.custom ? '<span class="badge bg-warning text-dark ms-1">C</span>' : '';
        return '<div class="list-group-item list-group-item-action py-1 px-2 d-flex align-items-center" ' +
            'style="cursor:pointer;font-size:0.85rem" data-action="wsSelectTable" data-params=\'{"codigo":"' + t.codigo + '"}\'>' +
            '<code class="me-2">' + t.codigo + '</code>' +
            '<span class="text-muted text-truncate" style="flex:1">' + (t.nome || '').substring(0, 25) + '</span>' +
            badge +
        '</div>';
    }).join('');
}

function wsFilterTables(query) {
    var q = query.toUpperCase();
    var filtered = window._wsState.tabelas.filter(function(t) {
        return t.codigo.toUpperCase().indexOf(q) >= 0 || (t.nome || '').toUpperCase().indexOf(q) >= 0;
    });
    wsRenderTableTree(filtered);
}

async function wsSelectTable(params) {
    var slug = window._wsState.activeSlug;
    var detail = document.getElementById('ws-table-detail');
    detail.innerHTML = '<div class="card"><div class="card-body text-center"><div class="spinner-border spinner-border-sm"></div></div></div>';

    try {
        var info = await apiRequest('/workspace/workspaces/' + slug + '/explorer/tabela/' + params.codigo);
        detail.innerHTML = wsRenderTableDetail(info);
    } catch (e) {
        detail.innerHTML = '<div class="card"><div class="card-body text-danger">Erro: ' + e.message + '</div></div>';
    }
}

function wsRenderTableDetail(info) {
    var customBadge = info.custom ? '<span class="badge bg-warning text-dark ms-2">CUSTOM</span>' : '';
    var html = '<div class="card"><div class="card-body">' +
        '<h5><code>' + info.codigo + '</code> — ' + (info.nome || '') + customBadge + '</h5>' +
        '<p class="text-muted">Modo: ' + (info.modo || 'C') + '</p>';

    // Stats
    html += '<div class="row g-2 mb-3">' +
        '<div class="col-3 text-center"><h4 class="text-primary mb-0">' + (info.campos ? info.campos.length : 0) + '</h4><small class="text-muted">Campos</small></div>' +
        '<div class="col-3 text-center"><h4 class="text-warning mb-0">' + (info.campos_custom ? info.campos_custom.length : 0) + '</h4><small class="text-muted">Custom</small></div>' +
        '<div class="col-3 text-center"><h4 class="text-info mb-0">' + (info.indices ? info.indices.length : 0) + '</h4><small class="text-muted">Indices</small></div>' +
        '<div class="col-3 text-center"><h4 class="text-danger mb-0">' + (info.gatilhos ? info.gatilhos.length : 0) + '</h4><small class="text-muted">Gatilhos</small></div>' +
    '</div>';

    // Campos custom
    if (info.campos_custom && info.campos_custom.length) {
        html += '<h6 class="mt-3">Campos Customizados (' + info.campos_custom.length + ')</h6>' +
            '<div class="table-responsive"><table class="table table-sm table-striped"><thead><tr>' +
            '<th>Campo</th><th>Titulo</th><th>Tipo</th><th>Tam</th><th>Obrig</th><th>F3</th></tr></thead><tbody>';
        info.campos_custom.forEach(function(c) {
            html += '<tr><td><code>' + c.campo + '</code></td><td>' + (c.titulo || '') + '</td>' +
                '<td>' + c.tipo + '</td><td>' + c.tamanho + ',' + c.decimal + '</td>' +
                '<td>' + (c.obrigatorio ? 'Sim' : '') + '</td><td>' + (c.f3 || '') + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    // Indices custom
    if (info.indices_custom && info.indices_custom.length) {
        html += '<h6 class="mt-3">Indices Custom (' + info.indices_custom.length + ')</h6>' +
            '<div class="table-responsive"><table class="table table-sm table-striped"><thead><tr>' +
            '<th>Ordem</th><th>Chave</th><th>Descricao</th></tr></thead><tbody>';
        info.indices_custom.forEach(function(i) {
            html += '<tr><td>' + i.ordem + '</td><td><code>' + i.chave + '</code></td><td>' + (i.descricao || '') + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    // Gatilhos custom
    if (info.gatilhos_custom && info.gatilhos_custom.length) {
        html += '<h6 class="mt-3">Gatilhos Custom (' + info.gatilhos_custom.length + ')</h6>' +
            '<div class="table-responsive"><table class="table table-sm table-striped"><thead><tr>' +
            '<th>Origem</th><th>Destino</th><th>Regra</th></tr></thead><tbody>';
        info.gatilhos_custom.forEach(function(g) {
            html += '<tr><td><code>' + g.campo_origem + '</code></td><td><code>' + g.campo_destino + '</code></td>' +
                '<td>' + (g.regra || '').substring(0, 60) + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    html += '</div></div>';
    return html;
}

// =====================================================================
// RENDERIZACAO PRINCIPAL
// =====================================================================

function dwRenderPage() {
    return '<div class="content-header d-flex justify-content-between align-items-center mb-4">' +
        '<div>' +
            '<h2><i class="fas fa-code me-2"></i>Dev Workspace</h2>' +
            '<p class="text-muted mb-0">Desenvolvimento assistido para fontes AdvPL/TLPP</p>' +
        '</div>' +
        '<div class="d-flex gap-2 align-items-center">' +
            '<button class="btn btn-outline-secondary btn-sm" data-action="dwRefresh">' +
                '<i class="fas fa-sync-alt me-1"></i>Atualizar' +
            '</button>' +
        '</div>' +
    '</div>' +
    '<ul class="nav nav-tabs mb-3" id="dw-tabs">' +
        '<li class="nav-item">' +
            '<button class="nav-link active" id="dw-tab-browser" ' +
                'data-action="dwSwitchTab" data-params=\'{"tab":"browser"}\'>' +
                '<i class="fas fa-folder-open me-1"></i>Navegador de Fontes' +
            '</button>' +
        '</li>' +
        '<li class="nav-item">' +
            '<button class="nav-link" id="dw-tab-impact" ' +
                'data-action="dwSwitchTab" data-params=\'{"tab":"impact"}\'>' +
                '<i class="fas fa-project-diagram me-1"></i>Analise de Impacto' +
            '</button>' +
        '</li>' +
        '<li class="nav-item">' +
            '<button class="nav-link" id="dw-tab-compile" ' +
                'data-action="dwSwitchTab" data-params=\'{"tab":"compile"}\'>' +
                '<i class="fas fa-cogs me-1"></i>Compilacao' +
            '</button>' +
        '</li>' +
    '</ul>' +
    '<div id="dw-tab-content"></div>';
}

// =====================================================================
// ABAS
// =====================================================================

async function dwSwitchTab(params) {
    var tab = typeof params === 'string' ? params : (params && params.tab) || 'browser';
    dwActiveTab = tab;

    document.querySelectorAll('#dw-tabs .nav-link').forEach(function(el) {
        el.classList.remove('active');
    });
    var activeBtn = document.getElementById('dw-tab-' + tab);
    if (activeBtn) activeBtn.classList.add('active');

    var container = document.getElementById('dw-tab-content');
    if (!container) return;

    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border spinner-border-sm"></div></div>';

    if (tab === 'browser') {
        await dwLoadBrowserTab();
    } else if (tab === 'impact') {
        dwRenderImpactTab(container);
    } else if (tab === 'compile') {
        await dwLoadCompileTab();
    }
}

// =====================================================================
// ABA 1: NAVEGADOR DE FONTES
// =====================================================================

async function dwLoadBrowserTab() {
    var container = document.getElementById('dw-tab-content');
    if (!_dwGetEnvId()) {
        container.innerHTML = '<div class="alert alert-warning m-2">Selecione um ambiente.</div>';
        return;
    }

    var resp = await dwBrowse(_dwGetEnvId(), dwCurrentPath);
    if (!resp) {
        container.innerHTML = '<div class="alert alert-warning m-2">FONTES_DIR nao configurado ou inacessivel para este ambiente.</div>';
        return;
    }

    dwBrowseItems = resp.items || [];
    container.innerHTML = dwRenderBrowser(resp);
}

function dwRenderBrowser(resp) {
    var pathParts = dwCurrentPath ? dwCurrentPath.split('/') : [];
    var breadcrumb = '<nav aria-label="breadcrumb"><ol class="breadcrumb mb-2">' +
        '<li class="breadcrumb-item"><a href="#" data-action="dwNavigate" data-params=\'{"path":""}\'>' +
        '<i class="fas fa-home"></i> FONTES_DIR</a></li>';
    var accumulated = '';
    for (var i = 0; i < pathParts.length; i++) {
        accumulated += (accumulated ? '/' : '') + pathParts[i];
        var isLast = i === pathParts.length - 1;
        if (isLast) {
            breadcrumb += '<li class="breadcrumb-item active">' + pathParts[i] + '</li>';
        } else {
            breadcrumb += '<li class="breadcrumb-item"><a href="#" data-action="dwNavigate" ' +
                'data-params=\'{"path":"' + accumulated.replace(/'/g, "\\'") + '"}\'>' + pathParts[i] + '</a></li>';
        }
    }
    breadcrumb += '</ol></nav>';

    // Barra de busca
    var searchBar = '<div class="input-group mb-3">' +
        '<input type="text" id="dw-search-input" class="form-control form-control-sm" ' +
            'placeholder="Buscar nos fontes (ex: MATA410, DbSeek, SA1)" onkeydown="if(event.key===\'Enter\')dwDoSearch()">' +
        '<select id="dw-search-filter" class="form-select form-select-sm" style="max-width:150px">' +
            '<option value="*.prw">*.prw</option>' +
            '<option value="*.tlpp">*.tlpp</option>' +
            '<option value="*.prx">*.prx</option>' +
            '<option value="*">Todos</option>' +
        '</select>' +
        '<button class="btn btn-outline-primary btn-sm" onclick="dwDoSearch()">' +
            '<i class="fas fa-search"></i>' +
        '</button>' +
    '</div>';

    // Lista de arquivos/pastas
    var fileList = '';
    if (dwBrowseItems.length === 0) {
        fileList = '<div class="text-muted text-center p-3">Diretorio vazio</div>';
    } else {
        fileList = '<div class="list-group list-group-flush" style="max-height:50vh;overflow-y:auto">';
        for (var j = 0; j < dwBrowseItems.length; j++) {
            var item = dwBrowseItems[j];
            var icon, cls;
            if (item.type === 'dir') {
                icon = 'fa-folder text-warning';
                cls = 'data-action="dwNavigate" data-params=\'{"path":"' + item.path.replace(/'/g, "\\'") + '"}\'';
            } else {
                icon = item.is_advpl ? 'fa-file-code text-primary' : 'fa-file text-muted';
                cls = 'data-action="dwOpenFile" data-params=\'{"path":"' + item.path.replace(/'/g, "\\'") + '"}\'';
            }
            var sizeStr = item.type === 'dir' ? '' : dwFormatSize(item.size);
            fileList += '<a href="#" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" ' + cls + '>' +
                '<span><i class="fas ' + icon + ' me-2"></i>' + item.name + '</span>' +
                '<small class="text-muted">' + sizeStr + '</small>' +
            '</a>';
        }
        fileList += '</div>';
    }

    // Viewer de arquivo (se aberto)
    var viewer = '';
    if (dwFileContent) {
        viewer = dwRenderFileViewer();
    }

    // Resultados de busca
    var searchHtml = '';
    if (dwSearchResults) {
        searchHtml = dwRenderSearchResults();
    }

    return '<div class="row">' +
        '<div class="col-md-' + (dwFileContent ? '5' : '12') + '">' +
            '<div class="card">' +
                '<div class="card-body p-3">' +
                    breadcrumb + searchBar + fileList + searchHtml +
                '</div>' +
            '</div>' +
        '</div>' +
        (dwFileContent ? '<div class="col-md-7">' + viewer + '</div>' : '') +
    '</div>';
}

function dwRenderFileViewer() {
    var ext = dwFileContent.extension || '';
    var content = dwFileContent.content || '';
    var highlighted = highlightCode(dwEscapeHtml(content), ext);

    return '<div class="card">' +
        '<div class="card-header d-flex justify-content-between align-items-center py-2">' +
            '<span><i class="fas fa-file-code me-2"></i><strong>' + dwFileContent.name + '</strong>' +
            ' <small class="text-muted">(' + dwFileContent.lines + ' linhas, ' + dwFormatSize(dwFileContent.size) + ')</small></span>' +
            '<div>' +
                '<button class="btn btn-outline-info btn-sm me-1" data-action="dwAnalyzeFile" ' +
                    'data-params=\'{"path":"' + (dwFileContent.path || '').replace(/'/g, "\\'") + '"}\'>' +
                    '<i class="fas fa-project-diagram me-1"></i>Impacto' +
                '</button>' +
                '<button class="btn btn-outline-secondary btn-sm" data-action="dwCloseFile">' +
                    '<i class="fas fa-times"></i>' +
                '</button>' +
            '</div>' +
        '</div>' +
        '<div class="card-body p-0">' +
            '<pre class="code-viewer code-scroll-lg m-0">' +
                '<code>' + addLineNumbers(highlighted) + '</code>' +
            '</pre>' +
        '</div>' +
    '</div>';
}

function dwRenderSearchResults() {
    if (!dwSearchResults || !dwSearchResults.matches) return '';
    var matches = dwSearchResults.matches;
    var html = '<div class="mt-3"><h6><i class="fas fa-search me-1"></i>Resultados: ' +
        dwSearchResults.total + ' ocorrencias para "' + dwEscapeHtml(dwSearchResults.pattern) + '"</h6>';

    if (matches.length === 0) {
        html += '<div class="text-muted">Nenhum resultado encontrado.</div>';
    } else {
        html += '<div class="list-group list-group-flush" style="max-height:30vh;overflow-y:auto">';
        for (var i = 0; i < matches.length; i++) {
            var m = matches[i];
            html += '<a href="#" class="list-group-item list-group-item-action py-1 px-2" ' +
                'data-action="dwOpenFile" data-params=\'{"path":"' + m.file.replace(/'/g, "\\'") + '"}\'>' +
                '<small><strong>' + dwEscapeHtml(m.file) + '</strong>:' + m.line +
                ' <span class="text-muted">' + dwEscapeHtml(m.content.substring(0, 100)) + '</span></small>' +
            '</a>';
        }
        html += '</div>';
    }
    html += '</div>';
    return html;
}

// =====================================================================
// ABA 2: ANALISE DE IMPACTO
// =====================================================================

function dwRenderImpactTab(container) {
    var html = '<div class="card"><div class="card-body">';

    // Form para selecionar arquivo
    html += '<div class="row mb-3">' +
        '<div class="col-md-8">' +
            '<label class="form-label">Arquivo para analisar</label>' +
            '<div class="input-group">' +
                '<input type="text" id="dw-impact-file" class="form-control" ' +
                    'placeholder="Ex: MATA410.prw" value="' + (dwFileContent ? dwFileContent.path : '') + '">' +
                '<button class="btn btn-primary" data-action="dwRunImpact">' +
                    '<i class="fas fa-search me-1"></i>Analisar' +
                '</button>' +
            '</div>' +
        '</div>' +
    '</div>';

    // Resultado
    if (dwImpactResult) {
        html += dwRenderImpactResult();
    } else {
        html += '<div class="text-center text-muted p-4">' +
            '<i class="fas fa-project-diagram fa-3x mb-3 opacity-50"></i>' +
            '<p>Selecione um arquivo fonte para analisar seu impacto no sistema.</p>' +
            '<p class="small">A analise cruza o codigo com o schema do banco, processos mapeados e base de conhecimento.</p>' +
        '</div>';
    }

    html += '</div></div>';
    container.innerHTML = html;
}

function dwRenderImpactResult() {
    var r = dwImpactResult;
    var riskBadge = {
        'alto': 'bg-danger',
        'medio': 'bg-warning text-dark',
        'baixo': 'bg-success'
    };
    var riskLabel = {
        'alto': 'Alto',
        'medio': 'Medio',
        'baixo': 'Baixo'
    };

    var html = '<div class="mt-3">';

    // Header com risco
    html += '<div class="d-flex justify-content-between align-items-center mb-3">' +
        '<h5 class="mb-0"><i class="fas fa-file-code me-2"></i>' + dwEscapeHtml(r.file) +
        ' <small class="text-muted">(' + r.lines + ' linhas)</small></h5>' +
        '<span class="badge ' + (riskBadge[r.risk_level] || 'bg-secondary') + ' px-3 py-2">' +
            'Risco: ' + (riskLabel[r.risk_level] || r.risk_level) + ' (' + r.risk_score + ')' +
        '</span>' +
    '</div>';

    // Tabelas referenciadas
    html += '<div class="mb-3"><h6><i class="fas fa-database me-1"></i>Tabelas Referenciadas (' + r.tables.length + ')</h6>';
    if (r.tables.length > 0) {
        html += '<div class="table-responsive"><table class="table table-sm table-striped">' +
            '<thead><tr><th>Tabela</th><th>No Schema</th><th>Colunas</th></tr></thead><tbody>';
        for (var i = 0; i < r.tables.length; i++) {
            var t = r.tables[i];
            html += '<tr><td><code>' + t.table_name + '</code></td>' +
                '<td>' + (t.in_schema_cache ? '<i class="fas fa-check text-success"></i>' : '<i class="fas fa-times text-muted"></i>') + '</td>' +
                '<td>' + (t.column_count || '-') + '</td></tr>';
        }
        html += '</tbody></table></div>';
    } else {
        html += '<p class="text-muted small">Nenhuma tabela Protheus identificada.</p>';
    }

    // Funcoes definidas
    html += '<h6><i class="fas fa-code me-1"></i>Funcoes Definidas (' + r.functions.length + ')</h6>';
    if (r.functions.length > 0) {
        html += '<div class="d-flex flex-wrap gap-1 mb-3">';
        for (var f = 0; f < r.functions.length; f++) {
            html += '<span class="badge bg-info text-dark">' + dwEscapeHtml(r.functions[f].name) +
                ' <small>(L' + r.functions[f].line + ')</small></span>';
        }
        html += '</div>';
    }

    // Includes
    if (r.includes && r.includes.length > 0) {
        html += '<h6><i class="fas fa-link me-1"></i>Includes (' + r.includes.length + ')</h6>' +
            '<div class="d-flex flex-wrap gap-1 mb-3">';
        for (var inc = 0; inc < r.includes.length; inc++) {
            html += '<span class="badge bg-secondary">' + dwEscapeHtml(r.includes[inc]) + '</span>';
        }
        html += '</div>';
    }

    // Processos relacionados
    html += '<h6><i class="fas fa-sitemap me-1"></i>Processos Relacionados (' + r.related_processes.length + ')</h6>';
    if (r.related_processes.length > 0) {
        html += '<div class="list-group list-group-flush mb-3">';
        for (var p = 0; p < r.related_processes.length; p++) {
            var proc = r.related_processes[p];
            html += '<div class="list-group-item py-1 px-2">' +
                '<strong>' + dwEscapeHtml(proc.name) + '</strong> ' +
                '<span class="badge bg-light text-dark border">' + (proc.module || '') + '</span> ' +
                '<small class="text-muted">via tabela ' + (proc.table_name || '') + '</small>' +
            '</div>';
        }
        html += '</div>';
    } else {
        html += '<p class="text-muted small mb-3">Nenhum processo mapeado referenciado.</p>';
    }

    // Erros conhecidos
    html += '<h6><i class="fas fa-exclamation-triangle me-1"></i>Erros Conhecidos (' + r.related_errors.length + ')</h6>';
    if (r.related_errors.length > 0) {
        html += '<div class="list-group list-group-flush mb-3">';
        for (var e = 0; e < r.related_errors.length; e++) {
            var err = r.related_errors[e];
            html += '<div class="list-group-item py-1 px-2">' +
                '<strong>' + dwEscapeHtml(err.title) + '</strong> ' +
                '<span class="badge bg-warning text-dark">' + (err.category || '') + '</span>' +
            '</div>';
        }
        html += '</div>';
    } else {
        html += '<p class="text-muted small">Nenhum erro conhecido relacionado.</p>';
    }

    html += '</div>';
    return html;
}

// =====================================================================
// ABA 3: ASSISTENTE DE COMPILACAO
// =====================================================================

async function dwLoadCompileTab() {
    var container = document.getElementById('dw-tab-content');
    if (!_dwGetEnvId()) {
        container.innerHTML = '<div class="alert alert-warning m-2">Selecione um ambiente.</div>';
        return;
    }

    await dwLoadRepos();

    var html = '<div class="card"><div class="card-body">' +
        '<h5><i class="fas fa-cogs me-2"></i>Assistente de Compilacao</h5>' +
        '<p class="text-muted">Compare os fontes do servidor (FONTES_DIR) com o repositorio Git para identificar diferencas.</p>' +
        '<div class="row mb-3">' +
            '<div class="col-md-4">' +
                '<label class="form-label">Repositorio</label>' +
                '<select id="dw-compile-repo" class="form-select" onchange="dwOnRepoChange(this.value)">' +
                    '<option value="">Selecione...</option>' +
                    dwRepos.map(function(r) {
                        return '<option value="' + r.id + '" data-name="' + dwEscapeHtml(r.name) + '">' + dwEscapeHtml(r.name) + '</option>';
                    }).join('') +
                '</select>' +
            '</div>' +
            '<div class="col-md-4">' +
                '<label class="form-label">Branch</label>' +
                '<select id="dw-compile-branch" class="form-select">' +
                    '<option value="">Selecione repo primeiro</option>' +
                '</select>' +
            '</div>' +
            '<div class="col-md-4 d-flex align-items-end">' +
                '<button class="btn btn-primary w-100" data-action="dwRunDiff">' +
                    '<i class="fas fa-exchange-alt me-1"></i>Comparar' +
                '</button>' +
            '</div>' +
        '</div>';

    // Resultado do diff
    if (dwDiffResult) {
        html += dwRenderDiffResult();
    }

    html += '</div></div>';
    container.innerHTML = html;
}

function dwRenderDiffResult() {
    var d = dwDiffResult;
    var s = d.summary;

    var html = '<hr><h6><i class="fas fa-exchange-alt me-2"></i>Resultado da Comparacao</h6>' +
        '<div class="row text-center mb-3">' +
            '<div class="col"><div class="card bg-warning bg-opacity-10 p-2">' +
                '<div class="fs-4 fw-bold text-warning">' + s.modified + '</div>' +
                '<small>Modificados</small></div></div>' +
            '<div class="col"><div class="card bg-success bg-opacity-10 p-2">' +
                '<div class="fs-4 fw-bold text-success">' + s.only_fontes + '</div>' +
                '<small>Somente FONTES</small></div></div>' +
            '<div class="col"><div class="card bg-info bg-opacity-10 p-2">' +
                '<div class="fs-4 fw-bold text-info">' + s.only_repo + '</div>' +
                '<small>Somente Repo</small></div></div>' +
            '<div class="col"><div class="card bg-secondary bg-opacity-10 p-2">' +
                '<div class="fs-4 fw-bold text-secondary">' + s.unchanged + '</div>' +
                '<small>Iguais</small></div></div>' +
        '</div>';

    // Lista de arquivos diferentes
    var allChanged = [].concat(
        d.modified.map(function(f) { return { name: f, status: 'modified' }; }),
        d.only_in_fontes.map(function(f) { return { name: f, status: 'only_fontes' }; }),
        d.only_in_repo.map(function(f) { return { name: f, status: 'only_repo' }; })
    );

    if (allChanged.length > 0) {
        html += '<div class="d-flex justify-content-between align-items-center mb-2">' +
            '<h6 class="mb-0">Arquivos com diferencas (' + allChanged.length + ')</h6>' +
            '<button class="btn btn-success btn-sm" data-action="dwGenerateCompila">' +
                '<i class="fas fa-file-download me-1"></i>Gerar compila.txt' +
            '</button>' +
        '</div>';

        html += '<div class="list-group list-group-flush" style="max-height:40vh;overflow-y:auto">';
        var statusBadge = {
            'modified': '<span class="badge bg-warning text-dark">Modificado</span>',
            'only_fontes': '<span class="badge bg-success">Somente FONTES</span>',
            'only_repo': '<span class="badge bg-info">Somente Repo</span>'
        };
        for (var i = 0; i < allChanged.length; i++) {
            var fc = allChanged[i];
            html += '<div class="list-group-item d-flex justify-content-between align-items-center py-1 px-2">' +
                '<span><input type="checkbox" class="dw-compile-check me-2" value="' + dwEscapeHtml(fc.name) + '" checked>' +
                '<code>' + dwEscapeHtml(fc.name) + '</code></span>' +
                statusBadge[fc.status] +
            '</div>';
        }
        html += '</div>';
    }

    return html;
}

// =====================================================================
// ABA 4: POLITICAS DE BRANCH
// =====================================================================

async function dwLoadPoliciesTab() {
    var container = document.getElementById('dw-tab-content');
    await dwLoadPolicies(_dwGetEnvId());
    await dwLoadRepos();

    var html = '<div class="card"><div class="card-body">' +
        '<div class="d-flex justify-content-between align-items-center mb-3">' +
            '<h5 class="mb-0"><i class="fas fa-shield-alt me-2"></i>Politicas de Branch-Ambiente</h5>' +
            '<button class="btn btn-primary btn-sm" data-action="dwShowPolicyForm">' +
                '<i class="fas fa-plus me-1"></i>Nova Politica' +
            '</button>' +
        '</div>' +
        '<p class="text-muted small">Vincule branches a ambientes com regras de protecao para evitar push, pull ou commit indevido.</p>';

    // Formulario (oculto por padrao)
    html += '<div id="dw-policy-form" style="display:none" class="card bg-light mb-3">' +
        '<div class="card-body">' +
            '<h6>Nova Politica</h6>' +
            '<div class="row g-2 mb-2">' +
                '<div class="col-md-4">' +
                    '<label class="form-label">Repositorio</label>' +
                    '<select id="dw-policy-repo" class="form-select form-select-sm">' +
                        '<option value="">Selecione...</option>' +
                        dwRepos.map(function(r) {
                            return '<option value="' + dwEscapeHtml(r.name) + '">' + dwEscapeHtml(r.name) + '</option>';
                        }).join('') +
                    '</select>' +
                '</div>' +
                '<div class="col-md-4">' +
                    '<label class="form-label">Branch</label>' +
                    '<input type="text" id="dw-policy-branch" class="form-control form-control-sm" placeholder="master">' +
                '</div>' +
            '</div>' +
            '<div class="row g-2 mb-2">' +
                '<div class="col-auto">' +
                    '<div class="form-check form-switch">' +
                        '<input class="form-check-input" type="checkbox" id="dw-pol-push" checked>' +
                        '<label class="form-check-label">Push</label>' +
                    '</div>' +
                '</div>' +
                '<div class="col-auto">' +
                    '<div class="form-check form-switch">' +
                        '<input class="form-check-input" type="checkbox" id="dw-pol-pull" checked>' +
                        '<label class="form-check-label">Pull</label>' +
                    '</div>' +
                '</div>' +
                '<div class="col-auto">' +
                    '<div class="form-check form-switch">' +
                        '<input class="form-check-input" type="checkbox" id="dw-pol-commit" checked>' +
                        '<label class="form-check-label">Commit</label>' +
                    '</div>' +
                '</div>' +
                '<div class="col-auto">' +
                    '<div class="form-check form-switch">' +
                        '<input class="form-check-input" type="checkbox" id="dw-pol-create-branch">' +
                        '<label class="form-check-label">Criar Branch</label>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="d-flex gap-2">' +
                '<button class="btn btn-primary btn-sm" data-action="dwSavePolicy">' +
                    '<i class="fas fa-save me-1"></i>Salvar' +
                '</button>' +
                '<button class="btn btn-outline-secondary btn-sm" data-action="dwCancelPolicy">' +
                    'Cancelar' +
                '</button>' +
            '</div>' +
        '</div>' +
    '</div>';

    // Tabela de politicas existentes
    if (dwPolicies.length === 0) {
        html += '<div class="text-center text-muted p-4">' +
            '<i class="fas fa-shield-alt fa-3x mb-3 opacity-50"></i>' +
            '<p>Nenhuma politica definida. Branches operam sem restricoes.</p>' +
        '</div>';
    } else {
        html += '<div class="table-responsive"><table class="table table-sm table-striped">' +
            '<thead><tr><th>Repositorio</th><th>Branch</th><th>Ambiente</th>' +
            '<th>Push</th><th>Pull</th><th>Commit</th><th>Criar Branch</th><th>Acoes</th></tr></thead><tbody>';
        for (var i = 0; i < dwPolicies.length; i++) {
            var p = dwPolicies[i];
            html += '<tr>' +
                '<td><code>' + dwEscapeHtml(p.repo_name) + '</code></td>' +
                '<td><code>' + dwEscapeHtml(p.branch_name) + '</code></td>' +
                '<td>' + dwEscapeHtml(p.environment_name || '') + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_push) + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_pull) + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_commit) + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_create_branch) + '</td>' +
                '<td>' +
                    '<button class="btn btn-outline-danger btn-sm" data-action="dwDeletePolicy" ' +
                        'data-params=\'{"id":' + p.id + '}\'>' +
                        '<i class="fas fa-trash"></i>' +
                    '</button>' +
                '</td>' +
            '</tr>';
        }
        html += '</tbody></table></div>';
    }

    html += '</div></div>';
    container.innerHTML = html;
}

function dwPolicyBadge(allowed) {
    if (allowed) {
        return '<span class="badge bg-success"><i class="fas fa-check"></i></span>';
    }
    return '<span class="badge bg-danger"><i class="fas fa-ban"></i></span>';
}

// =====================================================================
// ACOES
// =====================================================================

async function dwNavigate(params) {
    dwCurrentPath = params.path || '';
    dwFileContent = null;
    dwSearchResults = null;
    await dwLoadBrowserTab();
}

async function dwOpenFile(params) {
    if (!params.path) return;
    var data = await dwReadFile(_dwGetEnvId(), params.path);
    if (data) {
        dwFileContent = data;
        await dwLoadBrowserTab();
    }
}

function dwCloseFile() {
    dwFileContent = null;
    dwLoadBrowserTab();
}

async function dwDoSearch() {
    var input = document.getElementById('dw-search-input');
    var filter = document.getElementById('dw-search-filter');
    if (!input || !input.value.trim()) return;

    try {
        var resp = await apiRequest('/devworkspace/search', 'POST', {
            environment_id: _dwGetEnvId(),
            pattern: input.value.trim(),
            file_filter: filter ? filter.value : '*.prw'
        });
        dwSearchResults = resp;
        dwLoadBrowserTab();
    } catch (e) {
        showNotification('Erro na busca: ' + e.message, 'error');
    }
}

async function dwAnalyzeFile(params) {
    var filePath = params.path || (dwFileContent ? dwFileContent.path : '');
    if (!filePath) {
        showNotification('Selecione um arquivo primeiro', 'warning');
        return;
    }

    try {
        dwImpactResult = await apiRequest('/devworkspace/impact', 'POST', {
            environment_id: _dwGetEnvId(),
            file_path: filePath
        });
        dwSwitchTab('impact');
    } catch (e) {
        showNotification('Erro na analise: ' + e.message, 'error');
    }
}

async function dwRunImpact() {
    var input = document.getElementById('dw-impact-file');
    if (!input || !input.value.trim()) {
        showNotification('Informe o caminho do arquivo', 'warning');
        return;
    }

    try {
        dwImpactResult = await apiRequest('/devworkspace/impact', 'POST', {
            environment_id: _dwGetEnvId(),
            file_path: input.value.trim()
        });
        var container = document.getElementById('dw-tab-content');
        dwRenderImpactTab(container);
    } catch (e) {
        showNotification('Erro na analise: ' + e.message, 'error');
    }
}

async function dwOnRepoChange(repoId) {
    var branchSelect = document.getElementById('dw-compile-branch');
    if (!branchSelect || !repoId) return;
    branchSelect.innerHTML = '<option value="">Carregando...</option>';
    await dwLoadBranches(repoId);
    branchSelect.innerHTML = '<option value="">Selecione...</option>' +
        dwBranches.map(function(b) {
            return '<option value="' + dwEscapeHtml(b) + '">' + dwEscapeHtml(b) + '</option>';
        }).join('');
}

async function dwRunDiff() {
    var repoSelect = document.getElementById('dw-compile-repo');
    var branchSelect = document.getElementById('dw-compile-branch');
    if (!repoSelect || !branchSelect || !repoSelect.value || !branchSelect.value) {
        showNotification('Selecione repositorio e branch', 'warning');
        return;
    }

    var repoName = repoSelect.options[repoSelect.selectedIndex].getAttribute('data-name') || repoSelect.options[repoSelect.selectedIndex].text;

    try {
        dwDiffResult = await apiRequest('/devworkspace/diff', 'POST', {
            environment_id: _dwGetEnvId(),
            repo_name: repoName,
            branch_name: branchSelect.value
        });
        await dwLoadCompileTab();
    } catch (e) {
        showNotification('Erro na comparacao: ' + e.message, 'error');
    }
}

async function dwGenerateCompila() {
    var checkboxes = document.querySelectorAll('.dw-compile-check:checked');
    var files = [];
    checkboxes.forEach(function(cb) { files.push(cb.value); });

    if (files.length === 0) {
        showNotification('Selecione pelo menos um arquivo', 'warning');
        return;
    }

    try {
        var resp = await apiRequest('/devworkspace/compila', 'POST', {
            environment_id: _dwGetEnvId(),
            files: files
        });

        // Download como arquivo
        var blob = new Blob([resp.content], { type: 'text/plain' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'compila.txt';
        a.click();
        URL.revokeObjectURL(url);
        showNotification('compila.txt gerado com ' + resp.file_count + ' arquivos', 'success');
    } catch (e) {
        showNotification('Erro ao gerar compila.txt: ' + e.message, 'error');
    }
}

function dwShowPolicyForm() {
    var form = document.getElementById('dw-policy-form');
    if (form) form.style.display = 'block';
}

function dwCancelPolicy() {
    var form = document.getElementById('dw-policy-form');
    if (form) form.style.display = 'none';
}

async function dwSavePolicy() {
    var repoName = document.getElementById('dw-policy-repo').value;
    var branchName = document.getElementById('dw-policy-branch').value.trim();
    if (!repoName || !branchName) {
        showNotification('Repositorio e branch obrigatorios', 'warning');
        return;
    }

    try {
        await apiRequest('/devworkspace/policies', 'POST', {
            environment_id: _dwGetEnvId(),
            repo_name: repoName,
            branch_name: branchName,
            allow_push: document.getElementById('dw-pol-push').checked,
            allow_pull: document.getElementById('dw-pol-pull').checked,
            allow_commit: document.getElementById('dw-pol-commit').checked,
            allow_create_branch: document.getElementById('dw-pol-create-branch').checked
        });
        showNotification('Politica criada com sucesso', 'success');
        await dwLoadPoliciesTab();
    } catch (e) {
        showNotification('Erro ao criar politica: ' + e.message, 'error');
    }
}

async function dwDeletePolicy(params) {
    if (!confirm('Remover esta politica?')) return;
    try {
        await apiRequest('/devworkspace/policies/' + params.id, 'DELETE');
        showNotification('Politica removida', 'success');
        await dwLoadPoliciesTab();
    } catch (e) {
        showNotification('Erro ao remover: ' + e.message, 'error');
    }
}

async function dwRefresh() {
    dwSwitchTab(dwActiveTab);
}

// =====================================================================
// UTILITARIOS
// =====================================================================

function dwFormatSize(bytes) {
    if (!bytes || bytes === 0) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

function dwEscapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// dwHighlightAdvpl e dwAddLineNumbers removidos — usar highlightCode() e addLineNumbers() globais de integration-core.js
