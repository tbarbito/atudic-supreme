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
