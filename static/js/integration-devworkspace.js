// =====================================================================
// INTEGRATION-DEVWORKSPACE.JS
// Modulo Workspace — Engenharia Reversa de ambientes Protheus
// Abas: Dashboard, Explorer, Processos
// Setup vive em Admin > Configuracoes > Workspace
// =====================================================================

// ===== Funcoes auxiliares usadas pelo tab Politicas de Branch (Settings) =====
let dwPolicies = [];
let dwRepos = [];

async function dwLoadPolicies(envId) {
    try {
        var url = envId ? '/devworkspace/policies?environment_id=' + envId : '/devworkspace/policies';
        dwPolicies = await apiRequest(url);
    } catch (e) { dwPolicies = []; }
}

async function dwLoadRepos() {
    try { dwRepos = await apiRequest('/repositories'); } catch (e) { dwRepos = []; }
}

function dwEscapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function dwPolicyBadge(allowed) {
    return allowed ? '<span class="badge bg-success">Sim</span>' : '<span class="badge bg-danger">Nao</span>';
}

function dwShowPolicyForm() { var el = document.getElementById('dw-policy-form'); if (el) el.style.display = 'block'; }
function dwCancelPolicy() { var el = document.getElementById('dw-policy-form'); if (el) el.style.display = 'none'; }

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
    var fontesDir = document.getElementById('ws-fontes-dir').value.trim();
    if (!slug) return showNotification('Informe o nome do workspace', 'warning');
    if (!connId) return showNotification('Selecione uma conexao', 'warning');

    var envId = parseInt(sessionStorage.getItem('active_environment_id')) || null;

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '20%';
    document.getElementById('ws-progress-text').textContent = 'Fase 1: Importando dicionario do banco...';

    try {
        var data = {
            connection_id: parseInt(connId), company_code: company, environment_id: envId
        };
        if (padraoDir) data.padrao_csv_dir = padraoDir;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/live', 'POST', data);
        var statsText = (result.stats.tabelas || 0) + ' tabelas, ' + (result.stats.campos || 0) + ' campos';

        // Fase 2: Parsear fontes se informado
        if (fontesDir) {
            document.getElementById('ws-progress-bar').style.width = '60%';
            document.getElementById('ws-progress-text').textContent = 'Fase 2: Parseando fontes ADVPL/TLPP...';
            try {
                var fontesResult = await apiRequest('/workspace/workspaces/' + slug + '/ingest/fontes', 'POST', { fontes_dir: fontesDir });
                statsText += ', ' + (fontesResult.stats.fontes || 0) + ' fontes';
            } catch (fe) {
                statsText += ' (fontes erro: ' + fe.message + ')';
            }
        }

        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + statsText;
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
    document.getElementById('ws-progress-text').textContent = 'Fase 1: Importando dicionario do banco...';

    try {
        var data = {
            connection_id: parseInt(connId), company_code: company,
            fontes_dir: fontesDir, environment_id: envId
        };
        if (padraoDir) data.padrao_csv_dir = padraoDir;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/hybrid', 'POST', data);
        var statsText = (result.stats.tabelas || 0) + ' tabelas, ' + (result.stats.campos || 0) + ' campos';
        statsText += ', ' + (result.stats.fontes || 0) + ' fontes';

        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + statsText;
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
    var fontesDir = document.getElementById('ws-fontes-dir').value.trim();
    if (!slug) return showNotification('Informe o nome do workspace', 'warning');
    if (!csvDir) return showNotification('Informe o diretorio dos CSVs', 'warning');

    document.getElementById('ws-progress').style.display = 'block';
    document.getElementById('ws-progress-bar').style.width = '20%';
    document.getElementById('ws-progress-text').textContent = 'Fase 1/3: Ingerindo CSVs do cliente...';

    try {
        var data = { csv_dir: csvDir };
        if (padraoDir) data.padrao_csv_dir = padraoDir;
        var result = await apiRequest('/workspace/workspaces/' + slug + '/ingest/csv', 'POST', data);
        var statsText = (result.stats.tabelas || 0) + ' tabelas, ' + (result.stats.campos || 0) + ' campos';

        // Fase 2: Parsear fontes se diretorio informado
        if (fontesDir) {
            document.getElementById('ws-progress-bar').style.width = '50%';
            document.getElementById('ws-progress-text').textContent = 'Fase 2/3: Parseando fontes ADVPL/TLPP...';
            try {
                var fontesResult = await apiRequest('/workspace/workspaces/' + slug + '/ingest/fontes', 'POST', { fontes_dir: fontesDir });
                statsText += ', ' + (fontesResult.stats.fontes || 0) + ' fontes, ' + (fontesResult.stats.chunks || 0) + ' chunks';
            } catch (fe) {
                statsText += ' (fontes erro: ' + fe.message + ')';
            }
        }

        // Fase 3: Diff (ja calculado no backend se padrao fornecido)
        if (result.stats.diff) {
            var d = result.stats.diff.campos || {};
            statsText += ', diff: +' + (d.adicionado || 0) + ' ~' + (d.alterado || 0) + ' -' + (d.removido || 0);
        }

        document.getElementById('ws-progress-bar').style.width = '100%';
        document.getElementById('ws-progress-text').textContent = 'Concluido! ' + statsText;
        showNotification('Ingestao concluida!', 'success');
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

        // Alerta se vinculos = 0 e fontes > 0
        if (r.vinculos === 0 && r.fontes_total > 0) {
            html += '<div class="alert alert-warning d-flex align-items-center mb-3">' +
                '<i class="fas fa-exclamation-triangle me-2"></i>' +
                '<span>Vinculos nao construidos. </span>' +
                '<button class="btn btn-warning btn-sm ms-2" data-action="wsBuildVinculos">' +
                    '<i class="fas fa-project-diagram me-1"></i>Construir Vinculos' +
                '</button>' +
            '</div>';
        }

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

        // Top 10 Fontes (maiores por LOC)
        if (data.top_fontes && data.top_fontes.length) {
            html += '<div class="card mb-4"><div class="card-body">' +
                '<h6 class="card-title">Top 10 Fontes (por linhas de codigo)</h6>' +
                '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
                '<th>Arquivo</th><th>Modulo</th><th>Funcoes</th><th>LOC</th>' +
                '</tr></thead><tbody>';
            data.top_fontes.forEach(function(f) {
                html += '<tr style="cursor:pointer" data-action="wsOpenFonte" data-params=\'{"arquivo":"' + f.arquivo + '"}\'>' +
                    '<td><code class="fw-bold">' + f.arquivo + '</code></td>' +
                    '<td>' + (f.modulo || '') + '</td>' +
                    '<td>' + f.funcoes + '</td>' +
                    '<td class="fw-bold">' + f.loc + '</td></tr>';
            });
            html += '</tbody></table></div></div></div>';
        }

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

async function wsBuildVinculos() {
    var slug = window._wsState.activeSlug;
    if (!slug) return;
    showNotification('Construindo vinculos...', 'info');
    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/build-vinculos', 'POST');
        showNotification('Vinculos construidos: ' + result.total + ' relacionamentos', 'success');
        await wsRenderDashboard(document.getElementById('ws-tab-content'));
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// Helper para navegar do dashboard para explorer
async function wsGoToTable(params) {
    window._wsState.activeTab = 'explorer';
    window._wsState._pendingTable = params.codigo;
    await wsSwitchTab({ tab: 'explorer' });
}

// =====================================================================
// WORKSPACE — EXPLORER TAB (estilo ExtraiRPO — tree hierarquica)
// =====================================================================

async function wsRenderExplorer(container) {
    var slug = window._wsState.activeSlug;
    if (!slug) {
        container.innerHTML = '<div class="alert alert-info">Configure um workspace em Admin > Configuracoes > Workspace.</div>';
        return;
    }

    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border spinner-border-sm"></div> Carregando explorer...</div>';

    try {
        // Carregar stats e tree em paralelo
        var statsP = apiRequest('/workspace/workspaces/' + slug + '/explorer/stats');
        var treeP = apiRequest('/workspace/workspaces/' + slug + '/explorer/tree');
        var stats = await statsP;
        var tree = await treeP;
        window._wsState._tree = tree;

        // Stats bar
        var statsHtml = '<div class="d-flex flex-wrap gap-2 mb-3">' +
            '<span class="badge bg-info">' + (stats.tabelas.total || 0) + ' Tabelas</span>' +
            '<span class="badge bg-info">' + (stats.fontes.total || 0) + ' Fontes</span>' +
            '<span class="badge bg-info">' + (stats.menus.total || 0) + ' Menus</span>' +
            '<span class="badge bg-success">+' + (stats.diff.adicionados || 0) + ' Add</span>' +
            '<span class="badge bg-warning text-dark">~' + (stats.diff.alterados || 0) + ' Alt</span>' +
        '</div>';

        container.innerHTML = statsHtml +
        '<div class="row">' +
            '<div class="col-md-3">' +
                '<div class="card" style="max-height:75vh;overflow-y:auto">' +
                    '<div class="card-body p-2">' +
                        '<input type="text" class="form-control form-control-sm mb-2" ' +
                            'placeholder="Buscar tabela, fonte, rotina..." id="ws-search" ' +
                            'oninput="wsFilterTree(this.value)" onkeydown="if(event.key===\'Enter\')wsDoSearch()">' +
                        '<div id="ws-tree"></div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="col-md-9">' +
                '<div id="ws-detail-panel">' +
                    '<div class="card"><div class="card-body text-muted text-center py-5">' +
                        '<i class="fas fa-sitemap fa-3x mb-3 text-muted"></i>' +
                        '<p>Selecione um item na arvore para visualizar.</p>' +
                    '</div></div>' +
                '</div>' +
            '</div>' +
        '</div>';

        _wsRenderTree(tree);

        // Se veio do dashboard com tabela pendente
        if (window._wsState._pendingTable) {
            var codigo = window._wsState._pendingTable;
            delete window._wsState._pendingTable;
            await wsSelectTable({ codigo: codigo });
        }
    } catch (e) {
        container.innerHTML = '<div class="alert alert-danger">Erro: ' + e.message + '</div>';
    }
}

function _wsRenderTree(tree) {
    var el = document.getElementById('ws-tree');
    if (!tree || !tree.length) { el.innerHTML = '<p class="text-muted p-2">Nenhum modulo.</p>'; return; }

    var html = '';
    tree.forEach(function(node) {
        if (node.type === 'modulo') {
            var icon = '<i class="fas fa-folder text-warning me-1" style="font-size:0.75rem"></i>';
            html += '<div class="ws-tree-module" style="margin-bottom:2px">' +
                '<div class="d-flex align-items-center py-1 px-1" style="cursor:pointer;font-size:0.82rem" ' +
                    'onclick="wsToggleModule(this,\'' + node.key + '\')">' +
                    '<i class="fas fa-chevron-right me-1 ws-tree-arrow" style="font-size:0.6rem;transition:transform 0.15s"></i>' +
                    icon + '<strong>' + node.label + '</strong>' +
                '</div>' +
                '<div class="ws-tree-children" style="display:none;padding-left:16px">';
            if (node.children && node.children.length) {
                node.children.forEach(function(cat) {
                    var catIcon = _wsCatIcon(cat.data.cat);
                    html += '<div class="d-flex align-items-center py-1 px-1" style="cursor:pointer;font-size:0.8rem" ' +
                        'data-action="wsLoadCategory" data-params=\'' + JSON.stringify({modulo: cat.data.modulo, cat: cat.data.cat}) + '\'>' +
                        catIcon + ' ' + cat.label +
                        ' <span class="badge bg-secondary ms-auto" style="font-size:0.65rem">' + cat.data.count + '</span>' +
                    '</div>';
                });
            }
            html += '</div></div>';
        } else if (node.type === 'leaf_category') {
            // Jobs, Schedules (root level)
            var leafIcon = node.data.cat === 'jobs' ? '<i class="fas fa-clock text-info me-1" style="font-size:0.7rem"></i>' : '<i class="fas fa-calendar text-info me-1" style="font-size:0.7rem"></i>';
            html += '<div class="d-flex align-items-center py-1 px-1" style="cursor:pointer;font-size:0.8rem" ' +
                'data-action="wsLoadCategory" data-params=\'' + JSON.stringify({modulo: "_root", cat: node.data.cat}) + '\'>' +
                leafIcon + node.label +
            '</div>';
        }
    });
    el.innerHTML = html;
}

function _wsCatIcon(cat) {
    var icons = {
        tabelas: '<i class="fas fa-table text-primary me-1" style="font-size:0.7rem"></i>',
        pes: '<i class="fas fa-sign-in-alt text-success me-1" style="font-size:0.7rem"></i>',
        menus_cliente: '<i class="fas fa-bars text-info me-1" style="font-size:0.7rem"></i>',
        fontes: '<i class="fas fa-file-code text-warning me-1" style="font-size:0.7rem"></i>',
        jobs: '<i class="fas fa-clock text-info me-1" style="font-size:0.7rem"></i>',
        schedules: '<i class="fas fa-calendar text-info me-1" style="font-size:0.7rem"></i>',
    };
    return icons[cat] || '<i class="fas fa-circle me-1" style="font-size:0.5rem"></i>';
}

function wsToggleModule(el, key) {
    var children = el.parentElement.querySelector('.ws-tree-children');
    var arrow = el.querySelector('.ws-tree-arrow');
    if (children.style.display === 'none') {
        children.style.display = 'block';
        arrow.style.transform = 'rotate(90deg)';
    } else {
        children.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

function wsFilterTree(query) {
    var q = query.toLowerCase();
    if (!q) { _wsRenderTree(window._wsState._tree); return; }
    // Filtro: mostrar modulos que contenham o termo no nome ou nos filhos
    var filtered = (window._wsState._tree || []).filter(function(node) {
        if (node.label.toLowerCase().indexOf(q) >= 0) return true;
        if (node.children) return node.children.some(function(c) { return c.label.toLowerCase().indexOf(q) >= 0; });
        return false;
    });
    _wsRenderTree(filtered);
}

// Carregar itens de uma categoria (tabelas, PEs, menus, fontes, jobs, schedules)
async function wsLoadCategory(params) {
    var slug = window._wsState.activeSlug;
    var panel = document.getElementById('ws-detail-panel');
    panel.innerHTML = '<div class="card"><div class="card-body text-center"><div class="spinner-border spinner-border-sm"></div> Carregando...</div></div>';

    try {
        var items = await apiRequest('/workspace/workspaces/' + slug + '/explorer/category/' + params.modulo + '/' + params.cat);
        panel.innerHTML = _wsRenderCategoryList(params.cat, params.modulo, items);
    } catch (e) {
        panel.innerHTML = '<div class="card"><div class="card-body text-danger">Erro: ' + e.message + '</div></div>';
    }
}

function _wsRenderCategoryList(cat, modulo, items) {
    var title = {tabelas:'Tabelas',pes:'Pontos de Entrada',menus_cliente:'Menus Cliente',fontes:'Fontes Custom',jobs:'Jobs',schedules:'Schedules'}[cat] || cat;
    var html = '<div class="card"><div class="card-body">' +
        '<h5>' + title + ' <span class="badge bg-info">' + items.length + ' itens</span></h5>';

    if (cat === 'tabelas') {
        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
            '<thead class="table-light"><tr><th>Codigo</th><th>Nome</th><th class="text-success">Custom</th><th class="text-warning">Alter.</th><th></th></tr></thead><tbody>';
        items.forEach(function(t) {
            var badge = t.custom ? '<span class="badge bg-warning text-dark" style="font-size:0.6rem">C</span>' : '';
            html += '<tr style="cursor:pointer" data-action="wsSelectTable" data-params=\'{"codigo":"' + t.codigo + '"}\'>' +
                '<td><code class="text-primary">' + t.codigo + '</code></td>' +
                '<td>' + (t.nome || '') + '</td>' +
                '<td>' + (t.campos_add > 0 ? '<span class="text-success fw-bold">+' + t.campos_add + '</span>' : '') + '</td>' +
                '<td>' + (t.campos_alt > 0 ? '<span class="text-warning fw-bold">~' + t.campos_alt + '</span>' : '') + '</td>' +
                '<td>' + badge + '</td></tr>';
        });
        html += '</tbody></table></div>';

    } else if (cat === 'pes') {
        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
            '<thead class="table-light"><tr><th>Ponto de Entrada</th><th>Fonte</th></tr></thead><tbody>';
        items.forEach(function(p) {
            html += '<tr><td><code class="text-primary fw-bold">' + p.pe + '</code></td>' +
                '<td><code>' + (p.fonte || '') + '</code></td></tr>';
        });
        html += '</tbody></table></div>';

    } else if (cat === 'menus_cliente') {
        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
            '<thead class="table-light"><tr><th>Rotina</th><th>Nome</th><th>Fonte</th></tr></thead><tbody>';
        items.forEach(function(m) {
            html += '<tr><td><code class="fw-bold">' + m.rotina + '</code></td>' +
                '<td>' + (m.nome || '') + '</td>' +
                '<td>' + (m.fonte ? '<code class="text-success">' + m.fonte + '</code>' : '') + '</td></tr>';
        });
        html += '</tbody></table></div>';

    } else if (cat === 'fontes') {
        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
            '<thead class="table-light"><tr><th>Fonte</th><th>Funcoes</th><th>LOC</th></tr></thead><tbody>';
        items.forEach(function(f) {
            html += '<tr style="cursor:pointer" data-action="wsOpenFonte" data-params=\'{"arquivo":"' + f.arquivo + '"}\'>' +
                '<td><code class="fw-bold">' + f.arquivo + '</code></td>' +
                '<td>' + f.funcoes + '</td><td>' + f.loc + '</td></tr>';
        });
        html += '</tbody></table></div>';

    } else if (cat === 'jobs') {
        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
            '<thead class="table-light"><tr><th>Rotina</th><th>Sessao</th><th>Refresh (s)</th><th>Arquivo INI</th></tr></thead><tbody>';
        items.forEach(function(j) {
            html += '<tr><td><code class="fw-bold">' + j.rotina + '</code></td>' +
                '<td>' + (j.sessao || '') + '</td>' +
                '<td>' + (j.refresh_rate || '') + '</td>' +
                '<td>' + (j.arquivo || '') + '</td></tr>';
        });
        html += '</tbody></table></div>';

    } else if (cat === 'schedules') {
        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
            '<thead class="table-light"><tr><th>Rotina</th><th>Empresa/Filial</th><th>Status</th><th>Recorrencia</th><th>Exec/Dia</th></tr></thead><tbody>';
        items.forEach(function(s) {
            var statusBadge = s.status === 'Ativo' ? 'bg-success' : 'bg-secondary';
            html += '<tr><td><code class="fw-bold">' + s.rotina + '</code></td>' +
                '<td>' + (s.empresa_filial || '') + '</td>' +
                '<td><span class="badge ' + statusBadge + '">' + (s.status || '') + '</span></td>' +
                '<td>' + (s.tipo_recorrencia || '') + '</td>' +
                '<td>' + (s.execucoes_dia || '') + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    html += '</div></div>';
    return html;
}

async function wsSelectTable(params) {
    var slug = window._wsState.activeSlug;
    var detail = document.getElementById('ws-detail-panel');
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
            '<div class="d-flex gap-1">' +
                '<button class="btn btn-outline-danger btn-sm" data-action="wsImpactAnalysis" data-params=\'{"tabela":"' + info.codigo + '"}\'>' +
                    '<i class="fas fa-exclamation-triangle me-1"></i>Analise de Impacto' +
                '</button>' +
                '<button class="btn btn-outline-secondary btn-sm" data-action="wsExportTable" data-params=\'{"tabela":"' + info.codigo + '"}\'>' +
                    '<i class="fas fa-download me-1"></i>Exportar' +
                '</button>' +
                '<button class="btn btn-outline-info btn-sm" data-action="wsAnotar" data-params=\'{"tipo":"tabela","chave":"' + info.codigo + '"}\'>' +
                    '<i class="fas fa-comment me-1"></i>Anotar' +
                '</button>' +
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
        '<li class="nav-item"><button class="nav-link" onclick="wsDetailTab(\'diff\')">Diff</button></li>' +
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
    else if (tab === 'diff') wsLoadDiffTab(info.codigo);
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
        html += '<tr style="cursor:pointer" data-action="wsOpenFonte" data-params=\'{"arquivo":"' + f.arquivo + '"}\'>' +
            '<td><code style="font-weight:600">' + f.arquivo + '</code></td>' +
            '<td>' + (f.modulo || '') + '</td>' +
            '<td>' + (f.loc || 0) + '</td>' +
            '<td><i class="fas fa-circle ' + modoColor + '" style="font-size:0.5rem"></i> ' + f.modo + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

// =====================================================================
// WORKSPACE — ANALISE DE IMPACTO + EXPORTAR
// =====================================================================

async function wsImpactAnalysis(params) {
    var slug = window._wsState.activeSlug;
    var panel = document.getElementById('ws-detail-panel');
    panel.innerHTML = '<div class="card"><div class="card-body text-center"><div class="spinner-border spinner-border-sm"></div> Analisando impacto de ' + params.tabela + '...</div></div>';

    try {
        // Usar agent_tools analyze_impact via endpoint existente
        var info = await apiRequest('/workspace/workspaces/' + slug + '/explorer/tabela/' + params.tabela);
        var fontes_esc = info.fontes_vinculados ? info.fontes_vinculados.filter(function(f) { return f.modo === 'Leitura/Escrita'; }) : [];
        var fontes_leit = info.fontes_vinculados ? info.fontes_vinculados.filter(function(f) { return f.modo === 'Leitura'; }) : [];
        var gatilhos = info.gatilhos || [];
        var gatilhos_custom = gatilhos.filter(function(g) { return g.custom; });

        var risco = fontes_esc.length > 5 || gatilhos_custom.length > 3 ? 'ALTO' : fontes_esc.length > 2 || gatilhos_custom.length > 0 ? 'MEDIO' : 'BAIXO';
        var riscoCor = risco === 'ALTO' ? 'danger' : risco === 'MEDIO' ? 'warning' : 'success';

        var html = '<div class="card"><div class="card-body">' +
            '<div class="d-flex justify-content-between align-items-center mb-3">' +
                '<h5 class="mb-0"><i class="fas fa-exclamation-triangle text-danger me-2"></i>Analise de Impacto — ' + params.tabela + '</h5>' +
                '<span class="badge bg-' + riscoCor + ' fs-6">' + risco + '</span>' +
            '</div>';

        // Resumo
        html += '<div class="row g-3 mb-3">' +
            '<div class="col-3 text-center"><h4 class="text-primary mb-0">' + fontes_leit.length + '</h4><small>Fontes Leitura</small></div>' +
            '<div class="col-3 text-center"><h4 class="text-warning mb-0">' + fontes_esc.length + '</h4><small>Fontes Escrita</small></div>' +
            '<div class="col-3 text-center"><h4 class="text-danger mb-0">' + gatilhos_custom.length + '</h4><small>Gatilhos Custom</small></div>' +
            '<div class="col-3 text-center"><h4 class="text-info mb-0">' + (info.campos_custom ? info.campos_custom.length : 0) + '</h4><small>Campos Custom</small></div>' +
        '</div>';

        // Fontes que ESCREVEM (risco real)
        if (fontes_esc.length) {
            html += '<h6 class="text-warning mt-3">Fontes que ESCREVEM nesta tabela (' + fontes_esc.length + ')</h6>' +
                '<div class="table-responsive"><table class="table table-sm mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
                '<th>Arquivo</th><th>Modulo</th><th>LOC</th></tr></thead><tbody>';
            fontes_esc.forEach(function(f) {
                html += '<tr style="cursor:pointer" data-action="wsOpenFonte" data-params=\'{"arquivo":"' + f.arquivo + '"}\'>' +
                    '<td><code class="fw-bold text-warning">' + f.arquivo + '</code></td>' +
                    '<td>' + (f.modulo || '') + '</td><td>' + f.loc + '</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Gatilhos custom
        if (gatilhos_custom.length) {
            html += '<h6 class="text-danger mt-3">Gatilhos Custom (' + gatilhos_custom.length + ')</h6>' +
                '<div class="table-responsive"><table class="table table-sm mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
                '<th>Origem</th><th>Destino</th><th>Regra</th></tr></thead><tbody>';
            gatilhos_custom.forEach(function(g) {
                html += '<tr><td><code>' + g.campo_origem + '</code></td><td><code>' + g.campo_destino + '</code></td>' +
                    '<td style="max-width:200px" class="text-truncate">' + (g.regra || '') + '</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Botao voltar
        html += '<div class="mt-3"><button class="btn btn-outline-secondary btn-sm" data-action="wsSelectTable" data-params=\'{"codigo":"' + params.tabela + '"}\'>' +
            '<i class="fas fa-arrow-left me-1"></i>Voltar para ' + params.tabela + '</button></div>';

        html += '</div></div>';
        panel.innerHTML = html;
    } catch (e) {
        panel.innerHTML = '<div class="card"><div class="card-body text-danger">Erro: ' + e.message + '</div></div>';
    }
}

async function wsExportTable(params) {
    var slug = window._wsState.activeSlug;
    try {
        showNotification('Exportando ' + params.tabela + '...', 'info');
        var data = await apiRequest('/workspace/workspaces/' + slug + '/export/atudic?tabela=' + params.tabela);
        // Download como JSON
        var blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = params.tabela + '_export.json';
        a.click();
        URL.revokeObjectURL(url);
        showNotification('Exportado!', 'success');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// WORKSPACE — FONTE DETAIL (estilo ExtraiRPO)
// =====================================================================

async function wsOpenFonte(params) {
    var slug = window._wsState.activeSlug;
    var panel = document.getElementById('ws-detail-panel');
    if (!panel) panel = document.getElementById('ws-tab-content');
    panel.innerHTML = '<div class="card"><div class="card-body text-center"><div class="spinner-border spinner-border-sm"></div> Carregando fonte...</div></div>';

    try {
        var f = await apiRequest('/workspace/workspaces/' + slug + '/explorer/fonte/' + encodeURIComponent(params.arquivo));
        panel.innerHTML = _wsRenderFonteDetail(f);
    } catch (e) {
        panel.innerHTML = '<div class="card"><div class="card-body text-danger">Erro: ' + e.message + '</div></div>';
    }
}

function _wsRenderFonteDetail(f) {
    var html = '<div class="card"><div class="card-body">';

    // Header
    html += '<div class="d-flex justify-content-between align-items-start mb-3">' +
        '<div>' +
            '<h5 class="mb-1"><i class="fas fa-file-code text-primary me-2"></i><code>' + f.arquivo + '</code></h5>' +
            '<div class="d-flex flex-wrap gap-1">' +
                '<span class="badge bg-secondary">' + (f.tipo || 'fonte') + '</span>' +
                '<span class="badge bg-info">' + (f.modulo || '') + '</span>' +
                '<span class="badge bg-primary">' + f.lines_of_code + ' LOC</span>' +
            '</div>' +
        '</div>' +
        '<div class="d-flex gap-1">' +
            '<button class="btn btn-success btn-sm" data-action="wsFonteOverview" data-params=\'{"arquivo":"' + f.arquivo + '"}\'>' +
                '<i class="fas fa-search me-1"></i>Overview' +
            '</button>' +
            '<button class="btn btn-info btn-sm text-white" data-action="wsFonteResumirTodas" data-params=\'{"arquivo":"' + f.arquivo + '"}\'>' +
                '<i class="fas fa-magic me-1"></i>Resumir Todas' +
            '</button>' +
            '<button class="btn btn-outline-secondary btn-sm" data-action="wsAnotar" data-params=\'{"tipo":"fonte","chave":"' + f.arquivo + '"}\'>' +
                '<i class="fas fa-comment me-1"></i>Anotar' +
            '</button>' +
        '</div>' +
    '</div>';

    // Tags: PEs, tabelas leitura, tabelas escrita
    if (f.pontos_entrada && f.pontos_entrada.length) {
        html += '<div class="mb-2"><small class="text-muted fw-bold">Pontos de Entrada:</small> ' +
            f.pontos_entrada.map(function(pe) { return '<span class="badge bg-success me-1">' + pe + '</span>'; }).join('') + '</div>';
    }
    if (f.tabelas_ref && f.tabelas_ref.length) {
        html += '<div class="mb-2"><small class="text-muted fw-bold">Tabelas leitura:</small> ' +
            f.tabelas_ref.map(function(t) { return '<span class="badge bg-light text-dark border me-1" style="cursor:pointer" data-action="wsSelectTable" data-params=\'{"codigo":"' + t + '"}\'>' + t + '</span>'; }).join('') + '</div>';
    }
    if (f.write_tables && f.write_tables.length) {
        html += '<div class="mb-2"><small class="text-muted fw-bold">Tabelas escrita:</small> ' +
            f.write_tables.map(function(t) { return '<span class="badge bg-warning text-dark me-1" style="cursor:pointer" data-action="wsSelectTable" data-params=\'{"codigo":"' + t + '"}\'>' + t + '</span>'; }).join('') + '</div>';
    }
    if (f.calls_u && f.calls_u.length) {
        html += '<div class="mb-2"><small class="text-muted fw-bold">Chama:</small> ' +
            f.calls_u.map(function(c) { return '<span class="badge bg-light text-dark border me-1">' + c + '</span>'; }).join('') + '</div>';
    }
    if (f.includes && f.includes.length) {
        html += '<div class="mb-2"><small class="text-muted fw-bold">Includes:</small> ' +
            f.includes.map(function(i) { return '<span class="badge bg-secondary me-1">' + i + '</span>'; }).join('') + '</div>';
    }

    // Tabs: Funcoes | Operacoes de Escrita | Vinculos
    var funcCount = f.funcoes ? f.funcoes.length : 0;
    var opsCount = f.operacoes_escrita ? f.operacoes_escrita.length : 0;
    var vincCount = f.vinculos ? f.vinculos.length : 0;
    var docsCount = f.funcao_docs ? f.funcao_docs.length : 0;

    html += '<ul class="nav nav-tabs mt-3 mb-3" id="ws-fonte-tabs">' +
        '<li class="nav-item"><button class="nav-link active" onclick="wsFonteTab(\'funcoes\')">Funcoes <span class="badge bg-secondary">' + funcCount + '</span></button></li>' +
        (docsCount > 0 ? '<li class="nav-item"><button class="nav-link" onclick="wsFonteTab(\'docs\')">Resumos <span class="badge bg-secondary">' + docsCount + '</span></button></li>' : '') +
        '<li class="nav-item"><button class="nav-link" onclick="wsFonteTab(\'ops\')">Operacoes Escrita <span class="badge bg-secondary">' + opsCount + '</span></button></li>' +
        '<li class="nav-item"><button class="nav-link" onclick="wsFonteTab(\'vinculos\')">Vinculos <span class="badge bg-secondary">' + vincCount + '</span></button></li>' +
    '</ul>';

    html += '<div id="ws-fonte-tab-content">' + _wsFonteTabFuncoes(f) + '</div>';
    html += '</div></div>';

    // Guardar dados para troca de tab
    window._wsState._currentFonte = f;
    return html;
}

function wsFonteTab(tab) {
    document.querySelectorAll('#ws-fonte-tabs .nav-link').forEach(function(b) { b.classList.remove('active'); });
    event.target.classList.add('active');
    var f = window._wsState._currentFonte;
    var c = document.getElementById('ws-fonte-tab-content');
    if (tab === 'funcoes') c.innerHTML = _wsFonteTabFuncoes(f);
    else if (tab === 'docs') c.innerHTML = _wsFonteTabDocs(f);
    else if (tab === 'ops') c.innerHTML = _wsFonteTabOps(f);
    else if (tab === 'vinculos') c.innerHTML = _wsFonteTabVinculos(f);
}

function _wsFonteTabFuncoes(f) {
    if (!f.funcoes || !f.funcoes.length) return '<p class="text-muted">Nenhuma funcao.</p>';
    var isUF = new Set(f.user_funcs || []);
    // Mapa de docs ja existentes
    var docsMap = {};
    if (f.funcao_docs) f.funcao_docs.forEach(function(d) { docsMap[d.funcao] = d; });

    var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
        '<thead class="table-light"><tr><th></th><th>Funcao</th><th>Tipo</th><th>Resumo</th><th>Acoes</th></tr></thead><tbody>';
    f.funcoes.forEach(function(fn, idx) {
        var tipo = isUF.has(fn) ? '<span class="badge bg-info">User Function</span>' : '<span class="badge bg-secondary">Static/Local</span>';
        var doc = docsMap[fn];
        var resumo = doc && doc.resumo ? '<span style="font-size:0.78rem">' + doc.resumo.substring(0, 80) + (doc.resumo.length > 80 ? '...' : '') + '</span>' : '<span class="text-muted" style="font-size:0.78rem">-</span>';
        html += '<tr>' +
            '<td><i class="fas fa-chevron-right" style="cursor:pointer;font-size:0.6rem" onclick="wsToggleFuncRow(this,' + idx + ')"></i></td>' +
            '<td><code class="fw-bold">' + fn + '</code></td><td>' + tipo + '</td>' +
            '<td>' + resumo + '</td>' +
            '<td class="text-nowrap">' +
                '<button class="btn btn-outline-info btn-sm py-0 px-1 me-1" style="font-size:0.7rem" ' +
                    'data-action="wsFonteResumirFuncao" data-params=\'' + JSON.stringify({arquivo: f.arquivo, funcao: fn}) + '\'>' +
                    '<i class="fas fa-magic"></i>' +
                '</button>' +
                '<button class="btn btn-outline-secondary btn-sm py-0 px-1" style="font-size:0.7rem" ' +
                    'data-action="wsFonteVerCodigo" data-params=\'' + JSON.stringify({arquivo: f.arquivo, funcao: fn}) + '\'>' +
                    '<i class="fas fa-code"></i>' +
                '</button>' +
            '</td></tr>';
        // Row expansion (hidden)
        var expandHtml = '';
        if (doc) {
            if (doc.assinatura) expandHtml += '<div><small class="text-muted">Assinatura:</small> <code>' + doc.assinatura + '</code></div>';
            if (doc.chama) expandHtml += '<div><small class="text-muted">Chama:</small> ' + doc.chama + '</div>';
            if (doc.chamada_por) expandHtml += '<div><small class="text-muted">Chamada por:</small> ' + doc.chamada_por + '</div>';
            if (doc.tabelas_ref) expandHtml += '<div><small class="text-muted">Tabelas:</small> ' + doc.tabelas_ref + '</div>';
            if (doc.retorno) expandHtml += '<div><small class="text-muted">Retorno:</small> ' + doc.retorno + '</div>';
        }
        html += '<tr id="ws-func-exp-' + idx + '" style="display:none"><td colspan="5" class="bg-light px-3 py-2" style="font-size:0.78rem">' +
            (expandHtml || '<span class="text-muted">Sem detalhes. Clique em <i class="fas fa-magic"></i> para resumir.</span>') +
            '<div id="ws-func-code-' + idx + '"></div>' +
        '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

function wsToggleFuncRow(el, idx) {
    var row = document.getElementById('ws-func-exp-' + idx);
    if (row.style.display === 'none') {
        row.style.display = '';
        el.classList.replace('fa-chevron-right', 'fa-chevron-down');
    } else {
        row.style.display = 'none';
        el.classList.replace('fa-chevron-down', 'fa-chevron-right');
    }
}

function _wsFonteTabDocs(f) {
    if (!f.funcao_docs || !f.funcao_docs.length) return '<p class="text-muted">Nenhum resumo gerado.</p>';
    var html = '';
    f.funcao_docs.forEach(function(d) {
        html += '<div class="card mb-2"><div class="card-body py-2 px-3">' +
            '<div class="d-flex justify-content-between">' +
                '<code class="fw-bold">' + d.funcao + '</code>' +
                '<span class="badge bg-secondary">' + (d.tipo || '') + '</span>' +
            '</div>' +
            (d.assinatura ? '<div style="font-size:0.78rem" class="text-muted mt-1"><code>' + d.assinatura + '</code></div>' : '') +
            (d.resumo ? '<div class="mt-1 ws-markdown" style="font-size:0.82rem">' + _wsRenderMarkdown(d.resumo) + '</div>' : '') +
            (d.chama ? '<div class="mt-1" style="font-size:0.78rem"><strong>Chama:</strong> ' + d.chama + '</div>' : '') +
            (d.chamada_por ? '<div style="font-size:0.78rem"><strong>Chamada por:</strong> ' + d.chamada_por + '</div>' : '') +
        '</div></div>';
    });
    return html;
}

function _wsFonteTabOps(f) {
    if (!f.operacoes_escrita || !f.operacoes_escrita.length) return '<p class="text-muted">Nenhuma operacao de escrita.</p>';
    var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
        '<thead class="table-light"><tr><th>Funcao</th><th>Tipo</th><th>Tabela</th><th>Campos</th><th>Condicao</th><th>Linha</th></tr></thead><tbody>';
    f.operacoes_escrita.forEach(function(o) {
        var campos = (o.campos || []).slice(0, 5).join(', ');
        if ((o.campos || []).length > 5) campos += ' +' + (o.campos.length - 5);
        html += '<tr><td><code>' + o.funcao + '</code></td>' +
            '<td><span class="badge bg-' + (o.tipo === 'insert' || o.tipo === 'INCLUSAO' ? 'success' : o.tipo === 'delete' ? 'danger' : 'warning') + '">' + o.tipo + '</span></td>' +
            '<td><code class="text-primary" style="cursor:pointer" data-action="wsSelectTable" data-params=\'{"codigo":"' + o.tabela + '"}\'>' + o.tabela + '</code></td>' +
            '<td style="max-width:150px" class="text-truncate">' + campos + '</td>' +
            '<td style="max-width:120px" class="text-truncate">' + (o.condicao || '') + '</td>' +
            '<td>' + (o.linha || '') + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

function _wsFonteTabVinculos(f) {
    if (!f.vinculos || !f.vinculos.length) return '<p class="text-muted">Nenhum vinculo.</p>';
    var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0" style="font-size:0.82rem">' +
        '<thead class="table-light"><tr><th>Tipo</th><th>Origem</th><th>Destino</th><th>Contexto</th></tr></thead><tbody>';
    f.vinculos.forEach(function(v) {
        html += '<tr><td><span class="badge bg-secondary">' + v.tipo + '</span></td>' +
            '<td><code>' + v.origem + '</code></td>' +
            '<td><code>' + v.destino + '</code></td>' +
            '<td style="max-width:150px" class="text-truncate">' + (v.contexto || '') + '</td></tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

// =====================================================================
// WORKSPACE — ACOES IA (Overview, Resumir, Ver Codigo, Anotar)
// =====================================================================

async function wsFonteOverview(params) {
    var slug = window._wsState.activeSlug;
    showNotification('Gerando overview de ' + params.arquivo + '...', 'info');
    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/explorer/fonte/' + encodeURIComponent(params.arquivo) + '/overview', 'POST');
        // Mostrar overview num card acima das tabs
        var panel = document.getElementById('ws-detail-panel');
        if (!panel) return;
        var existingCard = document.getElementById('ws-fonte-overview-card');
        if (existingCard) existingCard.remove();
        var card = document.createElement('div');
        card.id = 'ws-fonte-overview-card';
        card.className = 'card mb-3 border-success';
        card.innerHTML = '<div class="card-body">' +
            '<div class="d-flex justify-content-between align-items-center mb-2">' +
                '<h6 class="mb-0 text-success"><i class="fas fa-search me-1"></i>Overview — ' + params.arquivo + '</h6>' +
                '<button class="btn btn-sm btn-outline-secondary" onclick="this.closest(\'.card\').remove()"><i class="fas fa-times"></i></button>' +
            '</div>' +
            '<div class="ws-markdown" style="font-size:0.85rem">' + _wsRenderMarkdown(result.overview || '') + '</div>' +
            (result.cached ? '<small class="text-muted"><i class="fas fa-database me-1"></i>Cache</small>' : '') +
        '</div>';
        var firstCard = panel.querySelector('.card');
        if (firstCard) panel.insertBefore(card, firstCard);
        else panel.appendChild(card);
        showNotification('Overview gerado!', 'success');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function wsFonteResumirTodas(params) {
    var slug = window._wsState.activeSlug;
    var f = window._wsState._currentFonte;
    if (!f || !f.funcoes || !f.funcoes.length) return showNotification('Nenhuma funcao para resumir', 'warning');

    showNotification('Resumindo ' + f.funcoes.length + ' funcoes...', 'info');
    var done = 0;
    for (var i = 0; i < f.funcoes.length; i++) {
        try {
            await apiRequest('/workspace/workspaces/' + slug + '/explorer/funcao/' + encodeURIComponent(params.arquivo) + '/' + encodeURIComponent(f.funcoes[i]) + '/resumir', 'POST');
            done++;
        } catch (e) { /* skip */ }
    }
    showNotification(done + '/' + f.funcoes.length + ' funcoes resumidas!', 'success');
    // Recarregar fonte para pegar resumos
    await wsOpenFonte(params);
}

async function wsFonteResumirFuncao(params) {
    showNotification('Resumindo ' + params.funcao + '...', 'info');
    var slug = window._wsState.activeSlug;
    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/explorer/funcao/' + encodeURIComponent(params.arquivo) + '/' + encodeURIComponent(params.funcao) + '/resumir', 'POST');
        showNotification('Resumido!', 'success');
        // Recarregar fonte para atualizar resumo na tabela
        await wsOpenFonte({arquivo: params.arquivo});
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function wsFonteVerCodigo(params) {
    var slug = window._wsState.activeSlug;
    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/explorer/funcao/' + encodeURIComponent(params.arquivo) + '/' + encodeURIComponent(params.funcao) + '/codigo');
        // Encontrar o row expansion correspondente e mostrar codigo
        var funcoes = window._wsState._currentFonte ? window._wsState._currentFonte.funcoes : [];
        var idx = funcoes.indexOf(params.funcao);
        if (idx >= 0) {
            var codeEl = document.getElementById('ws-func-code-' + idx);
            if (codeEl) {
                codeEl.innerHTML = '<div class="mt-2"><strong>Codigo:</strong>' +
                    '<pre class="bg-dark text-light p-2 rounded mt-1" style="font-size:0.75rem;max-height:400px;overflow:auto"><code>' +
                    (result.codigo || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') +
                    '</code></pre></div>';
            }
            // Expandir row se estiver fechado
            var row = document.getElementById('ws-func-exp-' + idx);
            if (row && row.style.display === 'none') {
                row.style.display = '';
            }
        }
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// WORKSPACE — ANOTACOES
// =====================================================================

async function wsAnotar(params) {
    var texto = prompt('Anotacao para ' + params.tipo + ' ' + params.chave + ':');
    if (!texto) return;

    var slug = window._wsState.activeSlug;
    try {
        await apiRequest('/workspace/workspaces/' + slug + '/explorer/anotacoes', 'POST', {
            tipo: params.tipo, chave: params.chave, texto: texto
        });
        showNotification('Anotacao salva!', 'success');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// WORKSPACE — TAB DIFF (padrao vs cliente)
// =====================================================================

async function wsLoadDiffTab(tabela) {
    var slug = window._wsState.activeSlug;
    var c = document.getElementById('ws-detail-tab-content');
    c.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm"></div> Carregando diff...</div>';

    try {
        var diff = await apiRequest('/workspace/workspaces/' + slug + '/explorer/diff/' + tabela);
        if (!diff.available) {
            c.innerHTML = '<div class="alert alert-info">' + (diff.message || 'Dados padrao nao disponiveis.') + '</div>';
            return;
        }
        c.innerHTML = _wsRenderDiffContent(diff);
    } catch (e) {
        c.innerHTML = '<div class="text-danger">Erro: ' + e.message + '</div>';
    }
}

function _wsRenderDiffContent(diff) {
    var html = '<div class="d-flex gap-3 mb-3">' +
        '<span class="badge bg-success">' + diff.resumo.adicionados + ' adicionados</span>' +
        '<span class="badge bg-warning text-dark">' + diff.resumo.alterados + ' alterados</span>' +
        '<span class="badge bg-danger">' + diff.resumo.removidos + ' removidos</span>' +
    '</div>';

    // Adicionados
    if (diff.adicionados.length) {
        html += '<h6 class="text-success mt-3">Adicionados (nao existem no padrao)</h6>' +
            '<div class="table-responsive"><table class="table table-sm mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
            '<th>Campo</th><th>Tipo</th><th>Tam</th><th>Titulo</th></tr></thead><tbody>';
        diff.adicionados.forEach(function(c) {
            html += '<tr class="table-success"><td><code>' + c.campo + '</code></td><td>' + (c.tipo||'') + '</td><td>' + (c.tamanho||'') + '</td><td>' + (c.titulo||'') + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    // Alterados
    if (diff.alterados.length) {
        html += '<h6 class="text-warning mt-3">Alterados (diferem do padrao)</h6>' +
            '<div class="table-responsive"><table class="table table-sm mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
            '<th>Campo</th><th>Propriedade</th><th>Padrao</th><th>Cliente</th></tr></thead><tbody>';
        diff.alterados.forEach(function(c) {
            var diffs = c.diferencas || {};
            for (var prop in diffs) {
                html += '<tr class="table-warning"><td><code>' + c.campo + '</code></td><td>' + prop + '</td>' +
                    '<td class="text-muted">' + (diffs[prop].padrao || '') + '</td>' +
                    '<td class="fw-bold">' + (diffs[prop].cliente || '') + '</td></tr>';
            }
        });
        html += '</tbody></table></div>';
    }

    // Removidos
    if (diff.removidos.length) {
        html += '<h6 class="text-danger mt-3">Removidos (existem no padrao mas nao no cliente)</h6>' +
            '<div class="table-responsive"><table class="table table-sm mb-0" style="font-size:0.82rem"><thead class="table-light"><tr>' +
            '<th>Campo</th><th>Tipo</th><th>Tam</th><th>Titulo</th></tr></thead><tbody>';
        diff.removidos.forEach(function(c) {
            html += '<tr class="table-danger"><td><code>' + c.campo + '</code></td><td>' + (c.tipo||'') + '</td><td>' + (c.tamanho||'') + '</td><td>' + (c.titulo||'') + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    if (!diff.adicionados.length && !diff.alterados.length && !diff.removidos.length) {
        html += '<div class="alert alert-success">Nenhuma diferenca encontrada — tabela identica ao padrao.</div>';
    }

    return html;
}

// =====================================================================
// WORKSPACE — BUSCA GLOBAL
// =====================================================================

async function wsDoSearch() {
    var slug = window._wsState.activeSlug;
    var input = document.getElementById('ws-search');
    var q = input ? input.value.trim() : '';
    if (q.length < 2) return;

    var panel = document.getElementById('ws-detail-panel');
    panel.innerHTML = '<div class="card"><div class="card-body text-center"><div class="spinner-border spinner-border-sm"></div> Buscando...</div></div>';

    try {
        var data = await apiRequest('/workspace/workspaces/' + slug + '/explorer/search?q=' + encodeURIComponent(q));
        if (!data.results || !data.results.length) {
            panel.innerHTML = '<div class="card"><div class="card-body text-muted">Nenhum resultado para "' + q + '".</div></div>';
            return;
        }
        var html = '<div class="card"><div class="card-body">' +
            '<h6>Resultados para "' + q + '" <span class="badge bg-info">' + data.results.length + '</span></h6>' +
            '<div class="list-group list-group-flush">';
        data.results.forEach(function(r) {
            var icon = {tabela:'fa-table text-primary', fonte:'fa-file-code text-warning', menu:'fa-bars text-info', campo:'fa-columns text-success'}[r.type] || 'fa-circle';
            var actionAttr = r.action ? 'data-action="' + r.action + '" data-params=\'' + JSON.stringify(r.params || {}) + '\'' : '';
            html += '<div class="list-group-item list-group-item-action py-1" style="cursor:pointer;font-size:0.82rem" ' + actionAttr + '>' +
                '<i class="fas ' + icon + ' me-2" style="font-size:0.7rem"></i>' +
                '<span class="badge bg-light text-dark border me-1">' + r.type + '</span> ' + r.label + '</div>';
        });
        html += '</div></div></div>';
        panel.innerHTML = html;
    } catch (e) {
        panel.innerHTML = '<div class="card"><div class="card-body text-danger">Erro: ' + e.message + '</div></div>';
    }
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

        // Guardar para filtros
        window._wsState._processos = processos;

        var html = '<div class="d-flex justify-content-between align-items-center mb-3">' +
            '<div>' +
                '<h5 class="mb-0">Processos do Cliente <span class="badge bg-primary">' + processos.length + '</span></h5>' +
            '</div>' +
            '<div class="d-flex gap-2 align-items-center">' +
                '<select class="form-select form-select-sm" style="width:auto" onchange="wsFiltrarProcessos()"  id="ws-proc-tipo">' +
                    '<option value="">Todos os tipos</option>' +
                    '<option value="workflow">Workflow</option><option value="integracao">Integracao</option>' +
                    '<option value="logistica">Logistica</option><option value="fiscal">Fiscal</option>' +
                    '<option value="automacao">Automacao</option><option value="qualidade">Qualidade</option>' +
                    '<option value="outro">Outro</option>' +
                '</select>' +
                '<select class="form-select form-select-sm" style="width:auto" onchange="wsFiltrarProcessos()" id="ws-proc-crit">' +
                    '<option value="">Criticidade</option>' +
                    '<option value="alta">Alta</option><option value="media">Media</option><option value="baixa">Baixa</option>' +
                '</select>' +
                '<button class="btn btn-outline-secondary btn-sm" data-action="wsRedescobrir">' +
                    '<i class="fas fa-sync-alt me-1"></i>Redescobrir' +
                '</button>' +
                '<button class="btn btn-outline-primary btn-sm" data-action="wsIncluirProcesso">' +
                    '<i class="fas fa-plus me-1"></i>Incluir Processo' +
                '</button>' +
            '</div>' +
        '</div>';

        if (!processos.length) {
            html += '<div class="alert alert-secondary">' +
                '<i class="fas fa-info-circle me-2"></i>Nenhum processo detectado. ' +
                'Clique em <strong>Redescobrir</strong> para rodar o pipeline de deteccao automatica, ' +
                'ou <strong>Incluir Processo</strong> para registrar manualmente.' +
            '</div>';
        } else {
            html += '<div class="table-responsive"><table class="table table-hover mb-0" style="font-size:0.85rem">' +
                '<thead class="table-light"><tr>' +
                '<th>Nome</th><th>Tipo</th><th>Criticidade</th><th>Score</th><th>Tabelas</th>' +
                '</tr></thead><tbody id="ws-proc-tbody">' +
                _wsRenderProcessoRows(processos) +
                '</tbody></table></div>';
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="alert alert-danger">Erro: ' + e.message + '</div>';
    }
}

function wsFiltrarProcessos() {
    var tipo = document.getElementById('ws-proc-tipo').value;
    var crit = document.getElementById('ws-proc-crit').value;
    var all = window._wsState._processos || [];
    var filtered = all.filter(function(p) {
        if (tipo && p.tipo !== tipo) return false;
        if (crit && p.criticidade !== crit) return false;
        return true;
    });
    var tbody = document.getElementById('ws-proc-tbody');
    if (tbody) tbody.innerHTML = _wsRenderProcessoRows(filtered);
}

function _wsRenderProcessoRows(processos) {
    if (!processos.length) return '<tr><td colspan="5" class="text-muted text-center">Nenhum processo.</td></tr>';
    return processos.map(function(p) {
        var tipoBadge = _wsTipoBadge(p.tipo);
        var critBadge = _wsCritBadge(p.criticidade);
        var scoreBadge = _wsScoreBadge(p.score);
        var tabChips = (p.tabelas || []).slice(0, 4).map(function(t) {
            return '<span class="badge bg-light text-dark border me-1" style="font-size:0.7rem">' + t + '</span>';
        }).join('');
        if ((p.tabelas || []).length > 4) tabChips += '<span class="text-muted" style="font-size:0.7rem">+' + (p.tabelas.length - 4) + '</span>';
        return '<tr style="cursor:pointer" data-action="wsOpenProcesso" data-params=\'{"id":' + p.id + '}\'>' +
            '<td class="fw-semibold text-primary">' + p.nome + '</td>' +
            '<td>' + tipoBadge + '</td><td>' + critBadge + '</td><td>' + scoreBadge + '</td>' +
            '<td>' + tabChips + '</td></tr>';
    }).join('');
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

async function wsRedescobrir() {
    var slug = window._wsState.activeSlug;
    if (!slug) return;

    var container = document.getElementById('ws-tab-content');
    container.innerHTML =
        '<div class="text-center p-5">' +
            '<div class="spinner-border text-primary mb-3"></div>' +
            '<p class="text-muted">Rodando pipeline de descoberta de processos...</p>' +
            '<small class="text-muted">Isso pode levar ate 2 minutos (analise SQL + classificacao LLM)</small>' +
        '</div>';

    try {
        var result = await apiRequest('/workspace/workspaces/' + slug + '/processos/descobrir', 'POST', { force: true });
        showNotification('Descoberta concluida! ' + (result.total || 0) + ' processos detectados.', 'success');
        await wsRenderProcessos(container);
    } catch (e) {
        showNotification('Erro na descoberta: ' + e.message, 'error');
        await wsRenderProcessos(container);
    }
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
        el.innerHTML = '<div class="ws-markdown" style="font-size:0.85rem;max-height:400px;overflow:auto">' + _wsRenderMarkdown(result.analise_markdown || '') + '</div>';
    } catch (e) {
        el.innerHTML = '<div class="text-danger">Erro: ' + e.message + '</div>';
    }
}

// Renderizacao simples de markdown para HTML (sem dependencia externa)
function _wsRenderMarkdown(md) {
    if (!md) return '';
    return md
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-dark text-light p-2 rounded" style="font-size:0.78rem"><code>$2</code></pre>')
        .replace(/^### (.+)$/gm, '<h6 class="mt-3 mb-1 fw-bold">$1</h6>')
        .replace(/^## (.+)$/gm, '<h5 class="mt-3 mb-2 fw-bold text-primary">$1</h5>')
        .replace(/^# (.+)$/gm, '<h4 class="mt-3 mb-2 fw-bold">$1</h4>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code class="bg-light px-1 rounded">$1</code>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>');
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
            if (streamEl) streamEl.innerHTML = '<span class="d-inline-block p-2 rounded bg-light ws-markdown" style="max-width:80%;font-size:0.85rem;text-align:left">' + _wsRenderMarkdown(fullText) + '</span>';
        }
        msgsEl.scrollTop = msgsEl.scrollHeight;
    } catch (e) {
        var streamEl2 = document.getElementById('ws-proc-streaming');
        if (streamEl2) streamEl2.innerHTML = '<span class="d-inline-block p-2 rounded bg-danger text-white" style="font-size:0.85rem">Erro: ' + e.message + '</span>';
    }
}
