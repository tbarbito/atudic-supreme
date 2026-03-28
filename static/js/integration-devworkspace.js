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
    if (!window._wsState) {
        window._wsState = { activeTab: 'dashboard', activeSlug: null, tabelas: [] };
    }

    // Se activeTab era 'setup', redirecionar para dashboard
    if (window._wsState.activeTab === 'setup') {
        window._wsState.activeTab = 'dashboard';
    }

    document.getElementById('content-area').innerHTML =
        '<div class="content-header mb-4">' +
            '<h2><i class="fas fa-code me-2"></i>Workspace</h2>' +
            '<p class="text-muted mb-0">Engenharia reversa de ambientes Protheus</p>' +
        '</div>' +
        '<ul class="nav nav-tabs mb-3" id="ws-tabs">' +
            '<li class="nav-item">' +
                '<button class="nav-link active" data-action="wsSwitchTab" data-params=\'{"tab":"dashboard"}\'>' +
                    '<i class="fas fa-chart-bar me-1"></i>Dashboard' +
                '</button>' +
            '</li>' +
            '<li class="nav-item">' +
                '<button class="nav-link" data-action="wsSwitchTab" data-params=\'{"tab":"explorer"}\'>' +
                    '<i class="fas fa-sitemap me-1"></i>Explorer' +
                '</button>' +
            '</li>' +
            '<li class="nav-item">' +
                '<button class="nav-link" data-action="wsSwitchTab" data-params=\'{"tab":"processos"}\'>' +
                    '<i class="fas fa-project-diagram me-1"></i>Processos' +
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
    else if (tab === 'processos') await wsRenderProcessos(container);
}

// =====================================================================
// WORKSPACE — SETUP TAB
// =====================================================================

async function wsRenderSetup(container) {
    // Carregar conexoes disponiveis
    var connections = [];
    try { connections = await apiRequest('/workspace/connections'); } catch(e) {}

    var connOptions = '<option value="">-- Selecione uma conexao --</option>';
    connections.forEach(function(c) {
        connOptions += '<option value="' + c.id + '">' + c.name + ' (' + c.driver + ' - ' + c.host + ':' + c.port + '/' + c.database_name + ')</option>';
    });

    container.innerHTML =
        '<div class="row g-3">' +
            '<div class="col-md-7">' +
                '<div class="card">' +
                    '<div class="card-header d-flex justify-content-between align-items-center">' +
                        '<span><i class="fas fa-plus-circle me-2"></i>Criar / Configurar Workspace</span>' +
                    '</div>' +
                    '<div class="card-body">' +
                        '<div class="mb-3">' +
                            '<label class="form-label fw-semibold">Nome do workspace</label>' +
                            '<input type="text" class="form-control" id="ws-slug" placeholder="ex: marfrig-alimentos" value="' + (window._wsState.activeSlug || '') + '">' +
                        '</div>' +

                        // Modo de ingestao
                        '<div class="mb-3">' +
                            '<label class="form-label fw-semibold">Modo de ingestao</label>' +
                            '<div class="btn-group w-100" role="group">' +
                                '<input type="radio" class="btn-check" name="ws-mode" id="ws-mode-csv" value="csv" checked>' +
                                '<label class="btn btn-outline-primary" for="ws-mode-csv"><i class="fas fa-file-csv me-1"></i>CSV (Offline)</label>' +
                                '<input type="radio" class="btn-check" name="ws-mode" id="ws-mode-live" value="live">' +
                                '<label class="btn btn-outline-success" for="ws-mode-live"><i class="fas fa-database me-1"></i>Live (DB)</label>' +
                                '<input type="radio" class="btn-check" name="ws-mode" id="ws-mode-hybrid" value="hybrid">' +
                                '<label class="btn btn-outline-warning" for="ws-mode-hybrid"><i class="fas fa-random me-1"></i>Hibrido</label>' +
                            '</div>' +
                        '</div>' +

                        // Campos Live/Hibrido (conexao DB)
                        '<div id="ws-live-fields" style="display:none">' +
                            '<div class="mb-3">' +
                                '<label class="form-label fw-semibold">Conexao ao banco Protheus</label>' +
                                '<select class="form-select" id="ws-conn-id">' + connOptions + '</select>' +
                                (connections.length === 0 ? '<small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>Nenhuma conexao configurada. Cadastre em <strong>Banco de Dados > Conexoes</strong>.</small>' : '') +
                            '</div>' +
                            '<div class="mb-3">' +
                                '<label class="form-label fw-semibold">Codigo da empresa (M0_CODIGO)</label>' +
                                '<input type="text" class="form-control" id="ws-company" value="01" placeholder="01">' +
                            '</div>' +
                        '</div>' +

                        // Campos CSV (diretorio)
                        '<div id="ws-csv-fields">' +
                            '<div class="mb-3">' +
                                '<label class="form-label fw-semibold">Diretorio dos CSVs SX</label>' +
                                '<div class="input-group">' +
                                    '<input type="text" class="form-control" id="ws-csv-dir" placeholder="C:\\caminho\\para\\csvs">' +
                                    '<button class="btn btn-outline-secondary" type="button" onclick="document.getElementById(\'ws-csv-dir-picker\').click()">' +
                                        '<i class="fas fa-folder-open"></i>' +
                                    '</button>' +
                                '</div>' +
                                '<input type="file" id="ws-csv-dir-picker" webkitdirectory style="display:none" onchange="document.getElementById(\'ws-csv-dir\').value=this.files[0]?this.files[0].webkitRelativePath.split(\'/\')[0]:\'\'">' +
                            '</div>' +
                        '</div>' +

                        // Diretorio CSV SX padrao (sempre visivel — para comparacao diff)
                        '<div id="ws-padrao-fields">' +
                            '<div class="mb-3">' +
                                '<label class="form-label fw-semibold">Diretorio dos CSVs SX padrao <small class="text-muted">(para comparacao)</small></label>' +
                                '<div class="input-group">' +
                                    '<input type="text" class="form-control" id="ws-padrao-dir" placeholder="C:\\caminho\\para\\csvs_padrao">' +
                                    '<button class="btn btn-outline-secondary" type="button" onclick="document.getElementById(\'ws-padrao-dir-picker\').click()">' +
                                        '<i class="fas fa-folder-open"></i>' +
                                    '</button>' +
                                '</div>' +
                                '<input type="file" id="ws-padrao-dir-picker" webkitdirectory style="display:none" onchange="document.getElementById(\'ws-padrao-dir\').value=this.files[0]?this.files[0].webkitRelativePath.split(\'/\')[0]:\'\'">' +
                                '<small class="text-muted"><i class="fas fa-info-circle me-1"></i>CSVs do dicionario padrao TOTVS para gerar diff (padrao x cliente).</small>' +
                            '</div>' +
                        '</div>' +

                        // Campos Fontes (hibrido + CSV)
                        '<div id="ws-fontes-fields">' +
                            '<div class="mb-3">' +
                                '<label class="form-label fw-semibold">Diretorio dos fontes .prw/.tlpp <small class="text-muted">(opcional)</small></label>' +
                                '<div class="input-group">' +
                                    '<input type="text" class="form-control" id="ws-fontes-dir" placeholder="C:\\caminho\\para\\fontes">' +
                                    '<button class="btn btn-outline-secondary" type="button" onclick="document.getElementById(\'ws-fontes-dir-picker\').click()">' +
                                        '<i class="fas fa-folder-open"></i>' +
                                    '</button>' +
                                '</div>' +
                                '<input type="file" id="ws-fontes-dir-picker" webkitdirectory style="display:none" onchange="document.getElementById(\'ws-fontes-dir\').value=this.files[0]?this.files[0].webkitRelativePath.split(\'/\')[0]:\'\'">' +
                                '<small class="text-muted"><i class="fas fa-info-circle me-1"></i>Mapa de modulos Protheus carregado automaticamente do banco.</small>' +
                            '</div>' +
                        '</div>' +

                        // Botoes de acao
                        '<div class="d-flex gap-2" id="ws-action-buttons">' +
                            '<button class="btn btn-primary" data-action="wsIngestCSV" id="ws-btn-csv">' +
                                '<i class="fas fa-upload me-1"></i>Ingerir CSVs' +
                            '</button>' +
                            '<button class="btn btn-success" data-action="wsIngestLive" id="ws-btn-live" style="display:none">' +
                                '<i class="fas fa-database me-1"></i>Importar do Banco' +
                            '</button>' +
                            '<button class="btn btn-warning" data-action="wsIngestHybrid" id="ws-btn-hybrid" style="display:none">' +
                                '<i class="fas fa-random me-1"></i>Importar Hibrido' +
                            '</button>' +
                            '<button class="btn btn-outline-primary" data-action="wsIngestFontes">' +
                                '<i class="fas fa-file-code me-1"></i>Parsear Fontes' +
                            '</button>' +
                        '</div>' +

                        '<div id="ws-progress" class="mt-3" style="display:none">' +
                            '<div class="progress mb-2"><div class="progress-bar progress-bar-striped progress-bar-animated" id="ws-progress-bar" style="width:0%"></div></div>' +
                            '<small class="text-muted" id="ws-progress-text">Aguardando...</small>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="col-md-5">' +
                '<div class="card">' +
                    '<div class="card-header d-flex justify-content-between align-items-center">' +
                        '<span><i class="fas fa-list me-2"></i>Workspaces existentes</span>' +
                        '<button class="btn btn-outline-secondary btn-sm" data-action="wsRefreshList">' +
                            '<i class="fas fa-sync-alt"></i>' +
                        '</button>' +
                    '</div>' +
                    '<div class="card-body p-0">' +
                        '<div id="ws-list" class="list-group list-group-flush">' +
                            '<div class="text-muted p-3">Carregando...</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
        '</div>';

    // Mode switcher
    document.querySelectorAll('input[name="ws-mode"]').forEach(function(radio) {
        radio.addEventListener('change', function() { wsUpdateModeUI(this.value); });
    });

    await wsLoadWorkspaces();
}

function wsUpdateModeUI(mode) {
    var csvFields = document.getElementById('ws-csv-fields');
    var liveFields = document.getElementById('ws-live-fields');
    var fontesFields = document.getElementById('ws-fontes-fields');
    var btnCsv = document.getElementById('ws-btn-csv');
    var btnLive = document.getElementById('ws-btn-live');
    var btnHybrid = document.getElementById('ws-btn-hybrid');

    // Reset
    csvFields.style.display = 'none';
    liveFields.style.display = 'none';
    fontesFields.style.display = 'none';
    btnCsv.style.display = 'none';
    btnLive.style.display = 'none';
    btnHybrid.style.display = 'none';

    if (mode === 'csv') {
        csvFields.style.display = 'block';
        fontesFields.style.display = 'block';
        btnCsv.style.display = 'inline-block';
    } else if (mode === 'live') {
        liveFields.style.display = 'block';
        btnLive.style.display = 'inline-block';
    } else if (mode === 'hybrid') {
        liveFields.style.display = 'block';
        fontesFields.style.display = 'block';
        btnHybrid.style.display = 'inline-block';
    }
}

async function wsRefreshList() {
    await wsLoadWorkspaces();
}

async function wsIngestLive() {
    var slug = document.getElementById('ws-slug').value.trim();
    var connId = document.getElementById('ws-conn-id').value;
    var company = document.getElementById('ws-company').value.trim() || '01';
    var padraoDir = document.getElementById('ws-padrao-dir').value.trim();
    if (!slug) return showNotification('Informe o nome do workspace', 'warning');
    if (!connId) return showNotification('Selecione uma conexao', 'warning');

    var envId = parseInt(sessionStorage.getItem('active_environment_id')) || null;

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '30%';
    document.getElementById('ws-progress-text').textContent = 'Conectando ao banco Protheus...';

    try {
        var data = {
            connection_id: parseInt(connId), company_code: company, environment_id: envId
        };
        if (padraoDir) data.padrao_csv_dir = padraoDir;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/live', 'POST', data);
        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + JSON.stringify(result.stats);
        showNotification('Ingestao live concluida!', 'success');
        window._wsState.activeSlug = slug;
        await wsLoadWorkspaces();
    } catch (e) {
        document.getElementById('ws-progress-text').textContent = 'Erro: ' + e.message;
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function wsIngestHybrid() {
    var slug = document.getElementById('ws-slug').value.trim();
    var connId = document.getElementById('ws-conn-id').value;
    var company = document.getElementById('ws-company').value.trim() || '01';
    var fontesDir = document.getElementById('ws-fontes-dir').value.trim();
    var padraoDir = document.getElementById('ws-padrao-dir').value.trim();
    if (!slug) return showNotification('Informe o nome do workspace', 'warning');
    if (!connId) return showNotification('Selecione uma conexao', 'warning');
    if (!fontesDir) return showNotification('Informe o diretorio dos fontes', 'warning');

    var envId = parseInt(sessionStorage.getItem('active_environment_id')) || null;

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '20%';
    document.getElementById('ws-progress-text').textContent = 'Importando dicionario do banco + parseando fontes...';

    try {
        var data = {
            connection_id: parseInt(connId), company_code: company,
            fontes_dir: fontesDir, environment_id: envId
        };
        if (padraoDir) data.padrao_csv_dir = padraoDir;
        var mapa = document.getElementById('ws-mapa').value.trim();
        if (mapa) data.mapa_modulos = mapa;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/hybrid', 'POST', data);
        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + JSON.stringify(result.stats);
        showNotification('Ingestao hibrida concluida!', 'success');
        window._wsState.activeSlug = slug;
        await wsLoadWorkspaces();
    } catch (e) {
        document.getElementById('ws-progress-text').textContent = 'Erro: ' + e.message;
        showNotification('Erro: ' + e.message, 'error');
    }
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
    showNotification('Workspace "' + params.slug + '" selecionado', 'success');
    await wsSwitchTab({ tab: 'dashboard' });
}

async function wsIngestCSV() {
    var slug = document.getElementById('ws-slug').value.trim();
    var csvDir = document.getElementById('ws-csv-dir').value.trim();
    var padraoDir = document.getElementById('ws-padrao-dir').value.trim();
    if (!slug) return showNotification('Informe o nome do workspace', 'warning');
    if (!csvDir) return showNotification('Informe o diretorio dos CSVs', 'warning');

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '30%';
    document.getElementById('ws-progress-text').textContent = 'Ingerindo CSVs...';

    try {
        var data = { csv_dir: csvDir };
        if (padraoDir) data.padrao_csv_dir = padraoDir;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/csv', 'POST', data);
        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + JSON.stringify(result.stats);
        showNotification('Ingestao CSV concluida!', 'success');
        window._wsState.activeSlug = slug;
        await wsLoadWorkspaces();
    } catch (e) {
        document.getElementById('ws-progress-text').textContent = 'Erro: ' + e.message;
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function wsIngestFontes() {
    var slug = document.getElementById('ws-slug').value.trim();
    var fontesDir = document.getElementById('ws-fontes-dir').value.trim();
    if (!slug) return showNotification('Informe o nome do workspace', 'warning');
    if (!fontesDir) return showNotification('Informe o diretorio dos fontes', 'warning');

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
        showNotification('Parse de fontes concluido!', 'success');
        await wsLoadWorkspaces();
    } catch (e) {
        document.getElementById('ws-progress-text').textContent = 'Erro: ' + e.message;
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// WORKSPACE — DASHBOARD TAB (estilo ExtraiRPO)
// =====================================================================

async function wsRenderDashboard(container) {
    var slug = window._wsState.activeSlug;
    if (!slug) {
        container.innerHTML = '<div class="alert alert-info">Configure um workspace em Admin > Configuracoes > Workspace.</div>';
        return;
    }

    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border spinner-border-sm"></div> Carregando dashboard...</div>';

    try {
        var data = await apiRequest('/workspace/workspaces/' + slug + '/dashboard');
        var r = data.resumo;
        var dist = data.distribuicao_risco;

        var html = '<h5 class="mb-3">Dashboard — <strong>' + slug + '</strong></h5>';

        // Cards grandes (numeros principais)
        html += '<div class="row g-3 mb-4">' +
            wsStatCard(r.tabelas_total, 'Tabelas', 'fa-table', 'primary') +
            wsStatCard(r.campos_total, 'Campos', 'fa-columns', 'primary') +
            wsStatCard(r.fontes_total, 'Fontes', 'fa-file-code', 'info') +
            wsStatCard(r.vinculos, 'Vinculos', 'fa-project-diagram', 'info') +
            wsStatCard(r.gatilhos_total, 'Gatilhos', 'fa-bolt', 'primary') +
            wsStatCard(r.indices_total, 'Indices', 'fa-sort-amount-down', 'primary') +
            wsStatCard(r.menus_total, 'Menus', 'fa-bars', 'secondary') +
            wsStatCard(r.jobs_total + r.schedules_total, 'Jobs/Schedules', 'fa-clock', 'secondary') +
        '</div>';

        // Card: Distribuicao de Customizacao
        var totalDist = (dist.campos_so_padrao || 0) + (dist.campos_adicionados || 0) + (dist.campos_alterados || 0) + (dist.campos_removidos || 0);
        if (totalDist > 0) {
            html += '<div class="card mb-4"><div class="card-body">' +
                '<h6 class="card-title mb-3">Customizacao de Campos</h6>' +
                _wsRiskBar('Padrao', dist.campos_so_padrao, totalDist, '#6c757d') +
                _wsRiskBar('Adicionados', dist.campos_adicionados, totalDist, '#28a745') +
                _wsRiskBar('Alterados', dist.campos_alterados, totalDist, '#fd7e14') +
                _wsRiskBar('Removidos', dist.campos_removidos, totalDist, '#dc3545') +
            '</div></div>';
        }

        // Duas colunas: Top Customizadas + Top Interacao
        html += '<div class="row g-3 mb-4">';

        // Top 10 Customizadas
        if (data.top_tabelas && data.top_tabelas.length) {
            html += '<div class="col-md-6"><div class="card"><div class="card-body">' +
                '<h6 class="card-title">Top 10 Mais Customizadas</h6>' +
                '<div class="table-responsive"><table class="table table-sm table-hover mb-0"><thead><tr>' +
                '<th>Tabela</th><th>Nome</th><th class="text-success">+Add</th><th class="text-warning">~Alt</th><th>Score</th>' +
                '</tr></thead><tbody>';
            data.top_tabelas.forEach(function(t) {
                html += '<tr style="cursor:pointer" data-action="wsGoToTable" data-params=\'{"codigo":"' + t.tabela + '"}\'>' +
                    '<td><code>' + t.tabela + '</code></td><td class="text-truncate" style="max-width:150px">' + (t.nome || '') + '</td>' +
                    '<td class="text-success fw-bold">' + t.campos_add + '</td>' +
                    '<td class="text-warning fw-bold">' + t.campos_alt + '</td>' +
                    '<td><span class="badge bg-primary">' + t.score + '</span></td></tr>';
            });
            html += '</tbody></table></div></div></div></div>';
        }

        // Top 10 Interacao
        if (data.top_interacao && data.top_interacao.length) {
            html += '<div class="col-md-6"><div class="card"><div class="card-body">' +
                '<h6 class="card-title">Top 10 Mais Interacao de Fontes</h6>' +
                '<div class="table-responsive"><table class="table table-sm table-hover mb-0"><thead><tr>' +
                '<th>Tabela</th><th class="text-primary">Leitura</th><th class="text-warning">Escrita</th><th>Total</th>' +
                '</tr></thead><tbody>';
            data.top_interacao.forEach(function(t) {
                var maxTotal = data.top_interacao[0].total || 1;
                var lPct = Math.round((t.leitura / maxTotal) * 100);
                var ePct = Math.round((t.escrita / maxTotal) * 100);
                html += '<tr><td><code>' + t.tabela + '</code></td>' +
                    '<td class="text-primary">' + t.leitura + '</td>' +
                    '<td class="text-warning">' + t.escrita + '</td>' +
                    '<td>' +
                        '<div class="progress" style="height:14px">' +
                            '<div class="progress-bar bg-primary" style="width:' + lPct + '%"></div>' +
                            '<div class="progress-bar bg-warning" style="width:' + ePct + '%"></div>' +
                        '</div>' +
                    '</td></tr>';
            });
            html += '</tbody></table></div></div></div></div>';
        }

        html += '</div>'; // row

        // Modulos
        if (data.modulos && data.modulos.length) {
            var maxFontes = data.modulos[0].fontes || 1;
            html += '<div class="card mb-4"><div class="card-body">' +
                '<h6 class="card-title">Modulos</h6>' +
                '<div class="row g-2">';
            data.modulos.forEach(function(m) {
                var pct = Math.round((m.fontes / maxFontes) * 100);
                html += '<div class="col-md-6 col-lg-4">' +
                    '<div class="d-flex justify-content-between align-items-center mb-1">' +
                        '<strong style="font-size:0.85rem">' + m.modulo + '</strong>' +
                        '<small class="text-muted">' + m.fontes + ' fontes, ' + m.tabelas + ' tabelas</small>' +
                    '</div>' +
                    '<div class="progress mb-2" style="height:8px">' +
                        '<div class="progress-bar bg-info" style="width:' + pct + '%"></div>' +
                    '</div>' +
                '</div>';
            });
            html += '</div></div></div>';
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="alert alert-danger">Erro: ' + e.message + '</div>';
    }
}

function _wsRiskBar(label, value, total, color) {
    var pct = total > 0 ? Math.round((value / total) * 100) : 0;
    return '<div class="d-flex align-items-center mb-2">' +
        '<span style="min-width:100px;font-size:0.85rem">' + label + '</span>' +
        '<div class="progress flex-grow-1 mx-2" style="height:16px">' +
            '<div class="progress-bar" style="width:' + pct + '%;background:' + color + '">' + pct + '%</div>' +
        '</div>' +
        '<span class="text-muted" style="min-width:50px;font-size:0.85rem;text-align:right">' + (value || 0).toLocaleString() + '</span>' +
    '</div>';
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

// Helper para navegar do dashboard para explorer
async function wsGoToTable(params) {
    window._wsState.activeTab = 'explorer';
    window._wsState._pendingTable = params.codigo;
    await wsSwitchTab({ tab: 'explorer' });
}

// =====================================================================
// WORKSPACE — EXPLORER TAB (estilo ExtraiRPO)
// =====================================================================

async function wsRenderExplorer(container) {
    var slug = window._wsState.activeSlug;
    if (!slug) {
        container.innerHTML = '<div class="alert alert-info">Configure um workspace em Admin > Configuracoes > Workspace.</div>';
        return;
    }

    container.innerHTML =
        '<div class="row">' +
            '<div class="col-md-3">' +
                '<div class="card" style="max-height:75vh;overflow-y:auto">' +
                    '<div class="card-body p-2">' +
                        '<input type="text" class="form-control form-control-sm mb-2" ' +
                            'placeholder="Buscar tabela..." id="ws-search" oninput="wsFilterTables(this.value)">' +
                        '<div id="ws-table-tree"><div class="text-muted p-2">Carregando...</div></div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="col-md-9">' +
                '<div id="ws-table-detail">' +
                    '<div class="card"><div class="card-body text-muted text-center py-5">' +
                        '<i class="fas fa-sitemap fa-3x mb-3 text-muted"></i>' +
                        '<p>Selecione uma tabela para visualizar detalhes.</p>' +
                    '</div></div>' +
                '</div>' +
            '</div>' +
        '</div>';

    try {
        window._wsState.tabelas = await apiRequest('/workspace/workspaces/' + slug + '/explorer/tabelas');
        wsRenderTableTree(window._wsState.tabelas);
        // Se veio do dashboard com tabela pendente, abrir direto
        if (window._wsState._pendingTable) {
            var codigo = window._wsState._pendingTable;
            delete window._wsState._pendingTable;
            await wsSelectTable({ codigo: codigo });
        }
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
        var badge = t.custom ? '<span class="badge bg-warning text-dark ms-1" style="font-size:0.65rem">C</span>' : '';
        return '<div class="list-group-item list-group-item-action py-1 px-2 d-flex align-items-center" ' +
            'style="cursor:pointer;font-size:0.82rem" data-action="wsSelectTable" data-params=\'{"codigo":"' + t.codigo + '"}\'>' +
            '<code class="me-1 text-primary" style="font-size:0.78rem">' + t.codigo + '</code>' +
            '<span class="text-muted text-truncate" style="flex:1">' + (t.nome || '').substring(0, 22) + '</span>' +
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
    detail.innerHTML = '<div class="card"><div class="card-body text-center"><div class="spinner-border spinner-border-sm"></div> Carregando...</div></div>';

    try {
        var info = await apiRequest('/workspace/workspaces/' + slug + '/explorer/tabela/' + params.codigo);
        window._wsState._currentTable = info;
        detail.innerHTML = wsRenderTableDetail(info);
    } catch (e) {
        detail.innerHTML = '<div class="card"><div class="card-body text-danger">Erro: ' + e.message + '</div></div>';
    }
}

function wsRenderTableDetail(info) {
    var customBadge = info.custom ? '<span class="badge bg-warning text-dark ms-2">CUSTOM</span>' : '';
    var totalCampos = info.campos ? info.campos.length : 0;
    var addCount = info.campos ? info.campos.filter(function(c){ return c.status === 'adicionado'; }).length : 0;
    var altCount = info.campos ? info.campos.filter(function(c){ return c.status === 'alterado'; }).length : 0;

    var html = '<div class="card"><div class="card-body">' +
        '<div class="d-flex justify-content-between align-items-start mb-3">' +
            '<div>' +
                '<h5 class="mb-1"><code>' + info.codigo + '</code> — ' + (info.nome || '') + customBadge + '</h5>' +
                '<div class="d-flex gap-2">' +
                    '<span class="badge bg-primary">' + totalCampos + ' campos</span>' +
                    (addCount > 0 ? '<span class="badge bg-success">+' + addCount + ' add</span>' : '') +
                    (altCount > 0 ? '<span class="badge bg-warning text-dark">~' + altCount + ' alt</span>' : '') +
                '</div>' +
            '</div>' +
        '</div>';

    // Tabs: Campos | Gatilhos | Indices | Fontes
    var gatilhosLen = info.gatilhos ? info.gatilhos.length : 0;
    var indicesLen = info.indices ? info.indices.length : 0;
    var fontesLen = info.fontes_vinculados ? info.fontes_vinculados.length : 0;

    html += '<ul class="nav nav-tabs mb-3" id="ws-detail-tabs">' +
        '<li class="nav-item"><button class="nav-link active" onclick="wsDetailTab(\'campos\')">Campos <span class="badge bg-secondary">' + totalCampos + '</span></button></li>' +
        '<li class="nav-item"><button class="nav-link" onclick="wsDetailTab(\'gatilhos\')">Gatilhos <span class="badge bg-secondary">' + gatilhosLen + '</span></button></li>' +
        '<li class="nav-item"><button class="nav-link" onclick="wsDetailTab(\'indices\')">Indices <span class="badge bg-secondary">' + indicesLen + '</span></button></li>' +
        '<li class="nav-item"><button class="nav-link" onclick="wsDetailTab(\'fontes\')">Fontes <span class="badge bg-secondary">' + fontesLen + '</span></button></li>' +
    '</ul>';

    // Tab content: Campos (default)
    html += '<div id="ws-detail-tab-content">' + _wsRenderCamposTab(info) + '</div>';

    html += '</div></div>';
    return html;
}

function wsDetailTab(tab) {
    document.querySelectorAll('#ws-detail-tabs .nav-link').forEach(function(b){ b.classList.remove('active'); });
    event.target.classList.add('active');
    var info = window._wsState._currentTable;
    var c = document.getElementById('ws-detail-tab-content');
    if (tab === 'campos') c.innerHTML = _wsRenderCamposTab(info);
    else if (tab === 'gatilhos') c.innerHTML = _wsRenderGatilhosTab(info);
    else if (tab === 'indices') c.innerHTML = _wsRenderIndicesTab(info);
    else if (tab === 'fontes') c.innerHTML = _wsRenderFontesTab(info);
}

function _wsRenderCamposTab(info) {
    if (!info.campos || !info.campos.length) return '<p class="text-muted">Nenhum campo.</p>';
    // Legenda
    var html = '<div class="d-flex gap-3 mb-2" style="font-size:0.8rem">' +
        '<span><i class="fas fa-circle text-secondary" style="font-size:0.5rem"></i> Padrao</span>' +
        '<span><i class="fas fa-circle text-success" style="font-size:0.5rem"></i> Adicionado</span>' +
        '<span><i class="fas fa-circle text-warning" style="font-size:0.5rem"></i> Alterado</span>' +
    '</div>';
    html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
        '<th style="width:20px"></th><th>Campo</th><th>Tipo</th><th>Tam</th><th>Titulo</th><th>F3</th><th>Validacao</th><th>Alteracoes</th>' +
        '</tr></thead><tbody>';
    info.campos.forEach(function(c) {
        var dotColor = c.status === 'adicionado' ? 'text-success' : c.status === 'alterado' ? 'text-warning' : 'text-secondary';
        var alterBadges = '';
        if (c.alteracoes && c.alteracoes.length) {
            c.alteracoes.forEach(function(a) {
                alterBadges += '<span class="badge bg-warning text-dark me-1" style="font-size:0.7rem" title="Padrao: ' +
                    (a.valor_padrao || '') + ' → Cliente: ' + (a.valor_cliente || '') + '">' + a.campo_diff + '</span>';
            });
        }
        html += '<tr><td><i class="fas fa-circle ' + dotColor + '" style="font-size:0.5rem"></i></td>' +
            '<td><code style="font-size:0.78rem">' + c.campo + '</code></td>' +
            '<td>' + (c.tipo || '') + '</td><td>' + (c.tamanho || '') + '</td>' +
            '<td>' + (c.titulo || '') + '</td><td>' + (c.f3 || '') + '</td>' +
            '<td style="max-width:150px" class="text-truncate">' + (c.validacao || '') + '</td>' +
            '<td>' + alterBadges + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

function _wsRenderGatilhosTab(info) {
    if (!info.gatilhos || !info.gatilhos.length) return '<p class="text-muted">Nenhum gatilho.</p>';
    var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
        '<th>Origem</th><th>Destino</th><th>Regra</th><th>Condicao</th><th></th></tr></thead><tbody>';
    info.gatilhos.forEach(function(g) {
        var badge = g.custom ? '<span class="badge bg-warning text-dark" style="font-size:0.65rem">C</span>' : '';
        html += '<tr><td><code>' + (g.campo_origem || '') + '</code></td>' +
            '<td><code>' + (g.campo_destino || '') + '</code></td>' +
            '<td style="max-width:200px" class="text-truncate">' + (g.regra || '') + '</td>' +
            '<td style="max-width:150px" class="text-truncate">' + (g.condicao || '') + '</td>' +
            '<td>' + badge + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

function _wsRenderIndicesTab(info) {
    if (!info.indices || !info.indices.length) return '<p class="text-muted">Nenhum indice.</p>';
    var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
        '<th>Ordem</th><th>Chave</th><th>Descricao</th><th></th></tr></thead><tbody>';
    info.indices.forEach(function(i) {
        var badge = i.custom ? '<span class="badge bg-warning text-dark" style="font-size:0.65rem">C</span>' : '';
        html += '<tr><td>' + (i.ordem || '') + '</td>' +
            '<td><code>' + (i.chave || '') + '</code></td>' +
            '<td>' + (i.descricao || '') + '</td>' +
            '<td>' + badge + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

function _wsRenderFontesTab(info) {
    var fontes = info.fontes_vinculados || [];
    if (!fontes.length) return '<p class="text-muted">Nenhum fonte vinculado.</p>';
    // Legenda
    var readCount = fontes.filter(function(f){ return f.modo === 'Leitura'; }).length;
    var writeCount = fontes.filter(function(f){ return f.modo === 'Leitura/Escrita'; }).length;
    var html = '<div class="d-flex gap-3 mb-2" style="font-size:0.8rem">' +
        '<span class="text-muted">' + fontes.length + ' fontes</span>' +
        '<span><i class="fas fa-circle text-primary" style="font-size:0.5rem"></i> Leitura (' + readCount + ')</span>' +
        '<span><i class="fas fa-circle text-warning" style="font-size:0.5rem"></i> Leitura/Escrita (' + writeCount + ')</span>' +
    '</div>';
    html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
        '<th>Arquivo</th><th>Modulo</th><th>LOC</th><th>Modo</th></tr></thead><tbody>';
    fontes.forEach(function(f) {
        var modoColor = f.modo === 'Leitura/Escrita' ? 'text-warning' : 'text-primary';
        html += '<tr><td><code style="font-weight:600">' + f.arquivo + '</code></td>' +
            '<td>' + (f.modulo || '') + '</td>' +
            '<td>' + (f.loc || 0) + '</td>' +
            '<td><i class="fas fa-circle ' + modoColor + '" style="font-size:0.5rem"></i> ' + f.modo + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

// =====================================================================
// WORKSPACE — PROCESSOS TAB (estilo ExtraiRPO)
// =====================================================================

async function wsRenderProcessos(container) {
    var slug = window._wsState.activeSlug;
    if (!slug) {
        container.innerHTML = '<div class="alert alert-info">Configure um workspace em Admin > Configuracoes > Workspace.</div>';
        return;
    }

    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border spinner-border-sm"></div> Carregando processos...</div>';

    try {
        var processos = await apiRequest('/workspace/workspaces/' + slug + '/processos');

        var html = '<div class="d-flex justify-content-between align-items-center mb-3">' +
            '<div>' +
                '<h5 class="mb-0">Processos do Cliente <span class="badge bg-primary">' + processos.length + '</span></h5>' +
            '</div>' +
            '<div class="d-flex gap-2">' +
                '<button class="btn btn-outline-primary btn-sm" data-action="wsIncluirProcesso">' +
                    '<i class="fas fa-plus me-1"></i>Incluir Processo' +
                '</button>' +
            '</div>' +
        '</div>';

        if (!processos.length) {
            html += '<div class="alert alert-secondary">Nenhum processo detectado. Use o agente GolIAs para analisar o ambiente ou inclua manualmente.</div>';
        } else {
            html += '<div class="table-responsive"><table class="table table-hover mb-0" style="font-size:0.85rem">' +
                '<thead class="table-light"><tr>' +
                '<th>Nome</th><th>Tipo</th><th>Criticidade</th><th>Score</th><th>Tabelas</th>' +
                '</tr></thead><tbody>';
            processos.forEach(function(p) {
                var tipoBadge = _wsTipoBadge(p.tipo);
                var critBadge = _wsCritBadge(p.criticidade);
                var scoreBadge = _wsScoreBadge(p.score);
                var tabChips = (p.tabelas || []).slice(0, 4).map(function(t) {
                    return '<span class="badge bg-light text-dark border me-1" style="font-size:0.7rem">' + t + '</span>';
                }).join('');
                if ((p.tabelas || []).length > 4) tabChips += '<span class="text-muted" style="font-size:0.7rem">+' + (p.tabelas.length - 4) + '</span>';

                html += '<tr style="cursor:pointer" data-action="wsOpenProcesso" data-params=\'{"id":' + p.id + '}\'>' +
                    '<td class="fw-semibold text-primary">' + p.nome + '</td>' +
                    '<td>' + tipoBadge + '</td>' +
                    '<td>' + critBadge + '</td>' +
                    '<td>' + scoreBadge + '</td>' +
                    '<td>' + tabChips + '</td>' +
                '</tr>';
            });
            html += '</tbody></table></div>';
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="alert alert-danger">Erro: ' + e.message + '</div>';
    }
}

function _wsTipoBadge(tipo) {
    var colors = { workflow: 'primary', integracao: 'info', logistica: 'success', fiscal: 'danger', automacao: 'warning', qualidade: 'secondary' };
    var color = colors[tipo] || 'secondary';
    return '<span class="badge bg-' + color + '">' + (tipo || 'outro') + '</span>';
}

function _wsCritBadge(crit) {
    var colors = { alta: 'danger', media: 'warning', baixa: 'secondary' };
    return '<span class="badge bg-' + (colors[crit] || 'secondary') + '">' + (crit || 'media') + '</span>';
}

function _wsScoreBadge(score) {
    var s = score || 0;
    var color = s >= 0.85 ? 'success' : s >= 0.7 ? 'warning' : 'danger';
    return '<span class="badge bg-' + color + '">' + s.toFixed(2) + '</span>';
}

async function wsIncluirProcesso() {
    var slug = window._wsState.activeSlug;
    var desc = prompt('Descreva o processo de negocio do cliente:');
    if (!desc) return;

    try {
        showNotification('Registrando processo...', 'info');
        await apiRequest('/workspace/workspaces/' + slug + '/processos/registrar', 'POST', { descricao: desc });
        showNotification('Processo registrado!', 'success');
        await wsRenderProcessos(document.getElementById('ws-tab-content'));
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function wsOpenProcesso(params) {
    var slug = window._wsState.activeSlug;
    var container = document.getElementById('ws-tab-content');
    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border spinner-border-sm"></div></div>';

    try {
        var processos = await apiRequest('/workspace/workspaces/' + slug + '/processos');
        var proc = processos.find(function(p) { return p.id === params.id; });
        if (!proc) { container.innerHTML = '<div class="alert alert-warning">Processo nao encontrado.</div>'; return; }

        var msgs = [];
        try { var mr = await apiRequest('/workspace/workspaces/' + slug + '/processos/' + params.id + '/mensagens'); msgs = mr.mensagens || []; } catch(e){}

        var html = '<div class="mb-3">' +
            '<button class="btn btn-outline-secondary btn-sm me-2" data-action="wsSwitchTab" data-params=\'{"tab":"processos"}\'>' +
                '<i class="fas fa-arrow-left me-1"></i>Voltar' +
            '</button>' +
            '<span class="fw-bold">' + proc.nome + '</span> ' +
            _wsTipoBadge(proc.tipo) + ' ' + _wsCritBadge(proc.criticidade) + ' ' + _wsScoreBadge(proc.score) +
        '</div>';

        // Info
        html += '<div class="card mb-3"><div class="card-body">' +
            '<p>' + (proc.descricao || '') + '</p>' +
            '<div>' + (proc.tabelas || []).map(function(t) { return '<span class="badge bg-light text-dark border me-1">' + t + '</span>'; }).join('') + '</div>' +
        '</div></div>';

        // Fluxo + Analise lado a lado
        html += '<div class="row g-3 mb-3">' +
            '<div class="col-md-6"><div class="card"><div class="card-body">' +
                '<div class="d-flex justify-content-between align-items-center mb-2">' +
                    '<h6 class="mb-0">Fluxo</h6>' +
                    '<button class="btn btn-outline-primary btn-sm" data-action="wsGerarFluxo" data-params=\'{"id":' + params.id + '}\'>' +
                        (proc.fluxo_mermaid ? 'Regenerar' : 'Gerar fluxo') +
                    '</button>' +
                '</div>' +
                '<div id="ws-fluxo-content">' +
                    (proc.fluxo_mermaid ? '<pre class="bg-light p-2 rounded" style="font-size:0.78rem;max-height:300px;overflow:auto">' + proc.fluxo_mermaid + '</pre>' : '<p class="text-muted">Clique em "Gerar fluxo" para criar o diagrama.</p>') +
                '</div>' +
            '</div></div></div>' +
            '<div class="col-md-6"><div class="card"><div class="card-body">' +
                '<div class="d-flex justify-content-between align-items-center mb-2">' +
                    '<h6 class="mb-0">Analise Tecnica</h6>' +
                    '<button class="btn btn-outline-primary btn-sm" data-action="wsGerarAnalise" data-params=\'{"id":' + params.id + '}\'>' +
                        'Gerar Analise' +
                    '</button>' +
                '</div>' +
                '<div id="ws-analise-content"><p class="text-muted">Clique em "Gerar Analise" para investigar.</p></div>' +
            '</div></div></div>' +
        '</div>';

        // Chat
        html += '<div class="card"><div class="card-body">' +
            '<h6 class="mb-3">Chat sobre este processo</h6>' +
            '<div id="ws-proc-msgs" style="max-height:300px;overflow-y:auto;margin-bottom:12px">';
        if (msgs.length) {
            msgs.forEach(function(m) {
                var isUser = m.role === 'user';
                var align = isUser ? 'text-end' : 'text-start';
                var bg = isUser ? 'bg-primary text-white' : 'bg-light';
                html += '<div class="' + align + ' mb-2"><span class="d-inline-block p-2 rounded ' + bg + '" style="max-width:80%;font-size:0.85rem;text-align:left">' + (m.content || '') + '</span></div>';
            });
        } else {
            html += '<p class="text-muted">Nenhuma mensagem.</p>';
        }
        html += '</div>' +
            '<div class="input-group">' +
                '<input type="text" class="form-control" id="ws-proc-chat-input" placeholder="Pergunte sobre este processo...">' +
                '<button class="btn btn-primary" data-action="wsSendProcChat" data-params=\'{"id":' + params.id + '}\'>' +
                    '<i class="fas fa-paper-plane"></i>' +
                '</button>' +
            '</div>' +
        '</div></div>';

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="alert alert-danger">Erro: ' + e.message + '</div>';
    }
}

async function wsGerarFluxo(params) {
    var slug = window._wsState.activeSlug;
    var el = document.getElementById('ws-fluxo-content');
    el.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm"></div> Gerando fluxo...</div>';
    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/processos/' + params.id + '/fluxo?force=true', 'POST');
        el.innerHTML = '<pre class="bg-light p-2 rounded" style="font-size:0.78rem;max-height:300px;overflow:auto">' + (result.fluxo_mermaid || '') + '</pre>';
    } catch (e) {
        el.innerHTML = '<div class="text-danger">Erro: ' + e.message + '</div>';
    }
}

async function wsGerarAnalise(params) {
    var slug = window._wsState.activeSlug;
    var el = document.getElementById('ws-analise-content');
    el.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm"></div> Gerando analise tecnica...</div>';
    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/processos/' + params.id + '/analise?force=true');
        el.innerHTML = '<div style="font-size:0.85rem;max-height:400px;overflow:auto">' + (result.analise_markdown || '').replace(/\n/g, '<br>') + '</div>';
    } catch (e) {
        el.innerHTML = '<div class="text-danger">Erro: ' + e.message + '</div>';
    }
}

async function wsSendProcChat(params) {
    var slug = window._wsState.activeSlug;
    var input = document.getElementById('ws-proc-chat-input');
    var msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    var msgsEl = document.getElementById('ws-proc-msgs');
    msgsEl.innerHTML += '<div class="text-end mb-2"><span class="d-inline-block p-2 rounded bg-primary text-white" style="max-width:80%;font-size:0.85rem;text-align:left">' + msg + '</span></div>';
    msgsEl.innerHTML += '<div class="text-start mb-2" id="ws-proc-streaming"><span class="d-inline-block p-2 rounded bg-light" style="font-size:0.85rem"><i class="fas fa-spinner fa-spin"></i> Pensando...</span></div>';
    msgsEl.scrollTop = msgsEl.scrollHeight;

    try {
        var response = await fetch('/api/workspace/workspaces/' + slug + '/processos/' + params.id + '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + sessionStorage.getItem('auth_token') },
            body: JSON.stringify({ message: msg })
        });
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var fullText = '';
        var streamEl = document.getElementById('ws-proc-streaming');

        while (true) {
            var result = await reader.read();
            if (result.done) break;
            var chunk = decoder.decode(result.value, { stream: true });
            var lines = chunk.split('\n');
            for (var i = 0; i < lines.length; i++) {
                if (lines[i].startsWith('data: ')) {
                    try {
                        var ev = JSON.parse(lines[i].substring(6));
                        if (ev.event === 'content' && ev.text) fullText += ev.text;
                    } catch(e) {}
                }
            }
            if (streamEl) streamEl.innerHTML = '<span class="d-inline-block p-2 rounded bg-light" style="max-width:80%;font-size:0.85rem;text-align:left">' + fullText + '</span>';
        }
        msgsEl.scrollTop = msgsEl.scrollHeight;
    } catch (e) {
        var streamEl2 = document.getElementById('ws-proc-streaming');
        if (streamEl2) streamEl2.innerHTML = '<span class="d-inline-block p-2 rounded bg-danger text-white" style="font-size:0.85rem">Erro: ' + e.message + '</span>';
    }
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
