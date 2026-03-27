// =====================================================================
// INTEGRATION-AUDITOR.JS
// Auditor de INI Protheus — Upload, Análise e Histórico
// =====================================================================

// ===== ESTADO LOCAL DO MÓDULO =====
let auditorHistory = [];
let auditorHistoryTotal = 0;
let auditorCurrentPage = 1;
const AUDITOR_PER_PAGE = 15;
let auditorCurrentResult = null;
let auditorBestPractices = [];
let auditorActiveTab = 'upload';
let auditorBpType = 'appserver';
let auditorBpCollapsed = false;

// =====================================================================
// CARREGAMENTO DE DADOS
// =====================================================================

async function loadAuditorHistory(page) {
    page = page || 1;
    auditorCurrentPage = page;
    const offset = (page - 1) * AUDITOR_PER_PAGE;
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        let qs = `?limit=${AUDITOR_PER_PAGE}&offset=${offset}`;
        if (envId) qs += `&environment_id=${envId}`;
        const resp = await apiRequest(`/auditor/history${qs}`);
        auditorHistory = resp.audits || [];
        auditorHistoryTotal = resp.total || 0;
    } catch (e) {
        auditorHistory = [];
        auditorHistoryTotal = 0;
        console.error('Erro ao carregar historico:', e);
    }
}

async function loadAuditorBestPractices(iniType) {
    try {
        const type = iniType || 'appserver';
        const resp = await apiRequest(`/auditor/best-practices?ini_type=${type}`);
        auditorBestPractices = resp.practices || [];
    } catch (e) {
        auditorBestPractices = [];
        console.error('Erro ao carregar boas praticas:', e);
    }
}

async function loadAuditDetail(auditId) {
    try {
        auditorCurrentResult = await apiRequest(`/auditor/audit/${auditId}`);
    } catch (e) {
        auditorCurrentResult = null;
        console.error('Erro ao carregar detalhe:', e);
    }
}

// =====================================================================
// PÁGINA PRINCIPAL
// =====================================================================

async function showAuditor() {
    const content = document.getElementById('content-area');
    if (!content) return;

    content.innerHTML = `
        <div class="container-fluid px-3">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="mb-0"><i class="fas fa-file-medical-alt me-2"></i>Auditor de INI Protheus</h4>
            </div>

            <!-- Tabs -->
            <ul class="nav nav-tabs mb-3" id="auditorTabs">
                <li class="nav-item">
                    <a class="nav-link ${auditorActiveTab === 'upload' ? 'active' : ''}" href="#"
                       onclick="auditorSwitchTab('upload'); return false;">
                       <i class="fas fa-upload me-1"></i> Upload &amp; Análise
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link ${auditorActiveTab === 'results' ? 'active' : ''}" href="#"
                       onclick="auditorSwitchTab('results'); return false;">
                       <i class="fas fa-chart-bar me-1"></i> Resultados
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link ${auditorActiveTab === 'history' ? 'active' : ''}" href="#"
                       onclick="auditorSwitchTab('history'); return false;">
                       <i class="fas fa-history me-1"></i> Histórico
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link ${auditorActiveTab === 'best-practices' ? 'active' : ''}" href="#"
                       onclick="auditorSwitchTab('best-practices'); return false;">
                       <i class="fas fa-check-double me-1"></i> Boas Práticas
                    </a>
                </li>
            </ul>

            <div id="auditor-tab-content"></div>
        </div>
    `;

    auditorSwitchTab(auditorActiveTab);
}

async function auditorSwitchTab(tab) {
    auditorActiveTab = tab;
    // Atualizar tabs ativas
    document.querySelectorAll('#auditorTabs .nav-link').forEach(el => el.classList.remove('active'));
    const tabs = document.querySelectorAll('#auditorTabs .nav-link');
    const tabMap = { 'upload': 0, 'results': 1, 'history': 2, 'best-practices': 3 };
    if (tabs[tabMap[tab]]) tabs[tabMap[tab]].classList.add('active');

    const container = document.getElementById('auditor-tab-content');
    if (!container) return;

    switch (tab) {
        case 'upload':
            _renderAuditorUpload(container);
            break;
        case 'results':
            _renderAuditorResults(container);
            break;
        case 'history':
            await loadAuditorHistory(auditorCurrentPage);
            _renderAuditorHistory(container);
            break;
        case 'best-practices':
            await loadAuditorBestPractices();
            _renderAuditorBestPractices(container);
            break;
    }
}

// =====================================================================
// TAB: UPLOAD & ANÁLISE
// =====================================================================

function _renderAuditorUpload(container) {
    container.innerHTML = `
        <div class="row">
            <div class="col-lg-8">
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0"><i class="fas fa-file-upload me-2"></i>Upload de arquivo INI</h6>
                    </div>
                    <div class="card-body">
                        <!-- Drag & Drop Zone -->
                        <div id="auditor-drop-zone" class="border border-2 border-dashed rounded p-5 text-center"
                             style="cursor: pointer; transition: all 0.2s;"
                             ondragover="_auditorDragOver(event)"
                             ondragleave="_auditorDragLeave(event)"
                             ondrop="_auditorDrop(event)"
                             onclick="document.getElementById('auditor-file-input').click()">
                            <i class="fas fa-cloud-upload-alt fa-3x text-muted mb-3"></i>
                            <p class="text-muted mb-1">Arraste e solte seu arquivo <strong>.ini</strong> aqui</p>
                            <p class="text-muted small">ou clique para selecionar</p>
                            <input type="file" id="auditor-file-input" accept=".ini" class="d-none"
                                   onchange="_auditorFileSelected(this)">
                        </div>

                        <!-- Arquivo selecionado -->
                        <div id="auditor-file-info" class="d-none mt-3">
                            <div class="alert alert-info d-flex align-items-center">
                                <i class="fas fa-file-code fa-2x me-3"></i>
                                <div>
                                    <strong id="auditor-file-name"></strong><br>
                                    <small id="auditor-file-size" class="text-muted"></small>
                                </div>
                                <button class="btn btn-sm btn-outline-danger ms-auto" onclick="_auditorClearFile()">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                        </div>

                        <!-- Botão Analisar -->
                        <div class="mt-3 d-flex justify-content-end">
                            <button id="auditor-analyze-btn" class="btn btn-primary" onclick="_auditorAnalyze()" disabled>
                                <i class="fas fa-search-plus me-1"></i> Analisar INI
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Resultado Rápido (aparece após análise) -->
                <div id="auditor-quick-result" class="d-none mt-3"></div>
            </div>

            <div class="col-lg-4">
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0"><i class="fas fa-info-circle me-2"></i>Como funciona</h6>
                    </div>
                    <div class="card-body">
                        <ol class="mb-0" style="padding-left: 1.2rem;">
                            <li class="mb-2">Faça upload do seu <code>appserver.ini</code>, <code>dbaccess.ini</code> ou outro INI Protheus</li>
                            <li class="mb-2">O sistema compara automaticamente contra <strong>boas práticas</strong> da TDN TOTVS</li>
                            <li class="mb-2">Veja o <strong>score</strong> e as recomendações detalhadas</li>
                            <li class="mb-2">Se um LLM estiver configurado, insights extras serão gerados</li>
                        </ol>
                        <hr>
                        <p class="text-muted small mb-0">
                            <i class="fas fa-shield-alt me-1"></i>
                            O conteúdo do arquivo é processado localmente. Apenas o delta de problemas
                            é enviado ao LLM (se configurado).
                        </p>
                    </div>
                </div>

                <div class="card mt-3">
                    <div class="card-header">
                        <h6 class="mb-0"><i class="fas fa-file-alt me-2"></i>Tipos suportados</h6>
                    </div>
                    <div class="card-body p-0">
                        <ul class="list-group list-group-flush">
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <span><i class="fas fa-server me-2 text-primary"></i>appserver.ini</span>
                                <span class="badge bg-success">Completo</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <span><i class="fas fa-database me-2 text-info"></i>dbaccess.ini</span>
                                <span class="badge bg-success">Completo</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <span><i class="fas fa-desktop me-2 text-warning"></i>smartclient.ini</span>
                                <span class="badge bg-secondary">Parcial</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <span><i class="fas fa-cog me-2 text-muted"></i>Outros .ini</span>
                                <span class="badge bg-secondary">Básico</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// ===== Drag & Drop handlers =====
let _auditorSelectedFile = null;

function _auditorDragOver(e) {
    e.preventDefault();
    e.currentTarget.classList.add('border-primary', 'bg-light');
}

function _auditorDragLeave(e) {
    e.currentTarget.classList.remove('border-primary', 'bg-light');
}

function _auditorDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('border-primary', 'bg-light');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        if (file.name.toLowerCase().endsWith('.ini')) {
            _auditorSetFile(file);
        } else {
            showNotification('Apenas arquivos .ini são aceitos', 'warning');
        }
    }
}

function _auditorFileSelected(input) {
    if (input.files.length > 0) {
        _auditorSetFile(input.files[0]);
    }
}

function _auditorSetFile(file) {
    _auditorSelectedFile = file;
    document.getElementById('auditor-file-info').classList.remove('d-none');
    document.getElementById('auditor-file-name').textContent = file.name;
    document.getElementById('auditor-file-size').textContent = _formatFileSize(file.size);
    document.getElementById('auditor-analyze-btn').disabled = false;
}

function _auditorClearFile() {
    _auditorSelectedFile = null;
    document.getElementById('auditor-file-info').classList.add('d-none');
    document.getElementById('auditor-file-input').value = '';
    document.getElementById('auditor-analyze-btn').disabled = true;
    document.getElementById('auditor-quick-result').classList.add('d-none');
}

function _formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// ===== Análise =====
async function _auditorAnalyze() {
    if (!_auditorSelectedFile) return;

    const btn = document.getElementById('auditor-analyze-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Analisando...';

    const formData = new FormData();
    formData.append('ini_file', _auditorSelectedFile);

    const envId = sessionStorage.getItem('active_environment_id');
    if (envId) formData.append('environment_id', envId);

    try {
        const headers = {};
        if (authToken) headers['Authorization'] = authToken;
        const envHeader = sessionStorage.getItem('active_environment_id');
        if (envHeader) headers['X-Environment-Id'] = envHeader;

        const resp = await fetch('/api/auditor/upload', {
            method: 'POST',
            headers: headers,
            body: formData,
        });
        const data = await resp.json();

        if (!resp.ok) {
            showNotification(data.error || 'Erro na analise', 'error');
            return;
        }

        auditorCurrentResult = data;
        showNotification(`Análise concluída! Score: ${data.score}`, 'success');

        // Mostrar resultado rápido
        _renderQuickResult(data);

    } catch (e) {
        showNotification('Erro de conexão ao analisar', 'danger');
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-search-plus me-1"></i> Analisar INI';
    }
}

function _renderQuickResult(data) {
    const container = document.getElementById('auditor-quick-result');
    container.classList.remove('d-none');

    const scoreColor = data.score >= 80 ? 'success' : data.score >= 50 ? 'warning' : 'danger';
    const scoreIcon = data.score >= 80 ? 'check-circle' : data.score >= 50 ? 'exclamation-triangle' : 'times-circle';

    container.innerHTML = `
        <div class="card border-${scoreColor}">
            <div class="card-body">
                <div class="row align-items-center">
                    <div class="col-md-3 text-center">
                        <div class="display-4 text-${scoreColor} fw-bold">${data.score}</div>
                        <div class="text-muted small">/ 100</div>
                        <i class="fas fa-${scoreIcon} fa-2x text-${scoreColor} mt-1"></i>
                    </div>
                    <div class="col-md-5">
                        <h6>${data.filename} <span class="badge bg-secondary">${data.ini_type}</span></h6>
                        <div class="d-flex gap-3 mt-2">
                            <span class="text-success"><i class="fas fa-check me-1"></i>${data.summary.ok} OK</span>
                            <span class="text-warning"><i class="fas fa-exclamation me-1"></i>${data.summary.mismatch} Incorretos</span>
                            <span class="text-danger"><i class="fas fa-question me-1"></i>${data.summary.missing} Ausentes</span>
                            ${data.summary.commented ? `<span class="text-secondary"><i class="fas fa-comment-slash me-1"></i>${data.summary.commented} Comentados</span>` : ''}
                        </div>
                        <div class="text-muted small mt-1">
                            ${data.parsed.total_sections} seções | ${data.parsed.total_keys} chaves${data.parsed.total_commented ? ` | ${data.parsed.total_commented} comentadas` : ''}
                        </div>
                    </div>
                    <div class="col-md-4 text-end">
                        <button class="btn btn-outline-primary btn-sm" onclick="auditorSwitchTab('results')">
                            <i class="fas fa-list me-1"></i> Ver Detalhes
                        </button>
                    </div>
                </div>

                ${data.llm_summary ? `
                <hr>
                <div class="mt-2">
                    <h6><i class="fas fa-robot me-1"></i> Análise IA</h6>
                    <div class="small">${_renderMarkdown(data.llm_summary)}</div>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

// =====================================================================
// TAB: RESULTADOS DETALHADOS
// =====================================================================

function _renderAuditorResults(container) {
    if (!auditorCurrentResult) {
        container.innerHTML = `
            <div class="text-center p-5 text-muted">
                <i class="fas fa-file-medical-alt fa-3x mb-3"></i>
                <p>Nenhuma análise realizada ainda.</p>
                <button class="btn btn-primary btn-sm" onclick="auditorSwitchTab('upload')">
                    <i class="fas fa-upload me-1"></i> Fazer Upload
                </button>
            </div>
        `;
        return;
    }

    const data = auditorCurrentResult;
    const findings = data.findings || data.results || [];
    const scoreColor = (data.score >= 80) ? 'success' : (data.score >= 50) ? 'warning' : 'danger';

    // Agrupar findings por seção
    const grouped = {};
    findings.forEach(f => {
        if (!grouped[f.section]) grouped[f.section] = [];
        grouped[f.section].push(f);
    });

    let findingsHtml = '';
    const sectionEntries = Object.entries(grouped);
    for (let idx = 0; idx < sectionEntries.length; idx++) {
        const [section, items] = sectionEntries[idx];
        const sectionOk = items.filter(f => f.status === 'ok').length;
        const sectionTotal = items.length;
        const hasProblems = items.some(f => f.status !== 'ok');
        const sectionId = section.replace(/[^a-zA-Z0-9]/g, '_');
        // Expandir automaticamente apenas seções com problemas
        const expanded = hasProblems;
        const chevron = expanded ? 'fa-chevron-down' : 'fa-chevron-right';
        findingsHtml += `
            <div class="card mb-2">
                <div class="card-header py-2 d-flex justify-content-between align-items-center"
                     style="cursor: pointer;" data-bs-toggle="collapse"
                     data-bs-target="#section-${sectionId}"
                     aria-expanded="${expanded}">
                    <span>
                        <i class="fas ${chevron} me-2 small" id="chevron-${sectionId}"></i>
                        <strong>[${section}]</strong>
                        ${hasProblems ? '<i class="fas fa-exclamation-triangle text-warning ms-2 small"></i>' : '<i class="fas fa-check text-success ms-2 small"></i>'}
                    </span>
                    <span class="badge bg-${sectionOk === sectionTotal ? 'success' : hasProblems ? 'warning' : 'secondary'}">
                        ${sectionOk}/${sectionTotal}
                    </span>
                </div>
                <div class="collapse ${expanded ? 'show' : ''}" id="section-${sectionId}">
                    <div class="table-responsive" style="max-height: 350px; overflow-y: auto;">
                        <table class="table table-sm table-hover mb-0">
                            <thead class="sticky-top" style="background: var(--bs-body-bg, #fff); z-index: 1;">
                                <tr>
                                    <th style="width:25%">Chave</th>
                                    <th style="width:20%">Valor Atual</th>
                                    <th style="width:20%">Recomendado</th>
                                    <th style="width:10%">Status</th>
                                    <th style="width:10%">Severidade</th>
                                    <th style="width:15%">Ref.</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${items.map(f => _renderFindingRow(f)).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
    }

    container.innerHTML = `
        <!-- Score Header -->
        <div class="card mb-3 border-${scoreColor}">
            <div class="card-body py-3">
                <div class="row align-items-center">
                    <div class="col-auto">
                        <div class="display-5 text-${scoreColor} fw-bold">${data.score}<small class="fs-6 text-muted">/100</small></div>
                    </div>
                    <div class="col">
                        <strong>${data.filename || ''}</strong>
                        <span class="badge bg-secondary ms-1">${data.ini_type || ''}</span>
                        <div class="d-flex gap-3 mt-1 small">
                            <span class="text-success"><i class="fas fa-check"></i> ${data.summary?.ok || 0} OK</span>
                            <span class="text-warning"><i class="fas fa-exclamation"></i> ${data.summary?.mismatch || 0} Incorretos</span>
                            <span class="text-danger"><i class="fas fa-question"></i> ${data.summary?.missing || 0} Ausentes</span>
                            ${data.summary?.commented ? `<span class="text-secondary"><i class="fas fa-comment-slash"></i> ${data.summary.commented} Comentados</span>` : ''}
                        </div>
                    </div>
                    <div class="col-auto d-flex gap-2">
                        ${data.suggested_ini ? `
                        <button class="btn btn-success btn-sm" onclick="_auditorDownloadSuggestedINI()">
                            <i class="fas fa-download me-1"></i> Baixar INI Corrigido
                        </button>
                        ` : ''}
                        <button class="btn btn-outline-secondary btn-sm" onclick="_auditorExportCSV()">
                            <i class="fas fa-file-csv me-1"></i> CSV
                        </button>
                        <button class="btn btn-outline-info btn-sm" onclick="_auditorToggleAllSections(true)">
                            <i class="fas fa-expand-alt me-1"></i>
                        </button>
                        <button class="btn btn-outline-info btn-sm" onclick="_auditorToggleAllSections(false)">
                            <i class="fas fa-compress-alt me-1"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>

        ${_renderEncodingCard(data)}
        ${_renderDirtyLinesCard(data)}
        ${_renderCommentedSectionsCard(data)}

        ${data.suggested_ini ? `
        <!-- INI Sugerido (com correções) -->
        <div class="card mb-3 border-success">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#suggested-ini">
                <h6 class="mb-0"><i class="fas fa-file-code me-2 text-success"></i>INI Sugerido (com correções aplicadas)</h6>
                <div><span class="badge bg-success me-2">Clique para expandir</span><i class="fas fa-chevron-down small text-muted"></i></div>
            </div>
            <div class="collapse" id="suggested-ini">
                <div class="card-body p-0">
                    <pre class="mb-0 p-3" style="max-height: 500px; overflow: auto; font-size: 0.85rem; background: var(--bs-dark, #1e1e1e); color: var(--bs-light, #d4d4d4);">${_escapeHtml(data.suggested_ini)}</pre>
                </div>
            </div>
        </div>
        ` : `
        <div class="alert alert-success py-2 mb-3">
            <i class="fas fa-check-circle me-2"></i>
            <strong>INI OK</strong> — Nenhuma correção crítica necessária. O arquivo está adequado para o papel detectado.
        </div>
        `}

        ${data.llm_summary ? `
        <div class="card mb-3">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#llm-insights">
                <h6 class="mb-0"><i class="fas fa-robot me-2"></i>Análise IA
                    ${data.llm_provider ? `<small class="text-muted ms-2">(${data.llm_provider}/${data.llm_model || ''})</small>` : ''}
                </h6>
                <i class="fas fa-chevron-down small text-muted"></i>
            </div>
            <div class="collapse show" id="llm-insights">
                <div class="card-body" style="max-height: 400px; overflow-y: auto;">${_renderMarkdown(data.llm_summary)}</div>
            </div>
        </div>
        ` : `
        <div class="alert alert-secondary py-2 mb-3">
            <i class="fas fa-robot me-2 opacity-50"></i>
            <strong>Análise IA indisponível</strong> — Ative um modelo LLM na aba
            <a href="#" onclick="event.preventDefault(); document.querySelector('[data-tab=\\'agent\\']')?.click() || (window.location.hash='agent'); setTimeout(() => typeof agSwitchTab === 'function' && agSwitchTab('llm'), 300);" class="alert-link">GolIAs > LLM</a>
            para obter insights detalhados.
        </div>
        `}

        ${(data.commented_findings && data.commented_findings.length) ? `
        <!-- Chaves Comentadas -->
        <div class="card mb-3 border-secondary">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#commented-section">
                <h6 class="mb-0"><i class="fas fa-comment-slash me-2"></i>Chaves Comentadas Detectadas</h6>
                <div><span class="badge bg-secondary me-2">${data.commented_findings.length}</span><i class="fas fa-chevron-down small text-muted"></i></div>
            </div>
            <div class="collapse" id="commented-section">
                <div class="table-responsive" style="max-height: 300px; overflow-y: auto;">
                    <table class="table table-sm mb-0">
                        <thead class="sticky-top" style="background: var(--bs-body-bg, #fff); z-index: 1;">
                            <tr>
                                <th>Seção</th><th>Chave</th><th>Valor Comentado</th>
                                <th>Recomendado</th><th>Severidade</th><th>Por quê?</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.commented_findings.map(cf => `
                                <tr class="table-light">
                                    <td><code>[${cf.section}]</code></td>
                                    <td><strong>;${cf.key_name}</strong></td>
                                    <td><code>${cf.commented_value || ''}</code></td>
                                    <td><code>${cf.recommended_value || '-'}</code></td>
                                    <td><span class="badge ${cf.severity === 'critical' ? 'bg-danger' : cf.severity === 'warning' ? 'bg-warning text-dark' : 'bg-info text-dark'}">${cf.severity}</span></td>
                                    <td class="small">${cf.reason || ''}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        ` : ''}

        <!-- Findings por Seção -->
        <div class="card mb-3">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#findings-detail">
                <h6 class="mb-0"><i class="fas fa-list-alt me-2"></i>Análise Detalhada por Seção</h6>
                <div><span class="badge bg-primary me-2">${Object.keys(grouped).length} seções</span><i class="fas fa-chevron-down small text-muted"></i></div>
            </div>
            <div class="collapse show" id="findings-detail">
                <div class="card-body py-2" style="max-height: 600px; overflow-y: auto;">
                    ${findingsHtml || '<div class="text-center p-4 text-muted">Nenhuma regra avaliada</div>'}
                </div>
            </div>
        </div>
    `;
}

function _renderEncodingCard(data) {
    const enc = data.encoding_info;
    if (!enc) return '';
    const isOk = enc.is_valid;
    const color = isOk ? 'success' : 'danger';
    const icon = isOk ? 'check-circle' : 'exclamation-triangle';
    const issues = enc.issues || [];

    return `
        <div class="card mb-3 border-${color}">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#encoding-card">
                <div class="d-flex align-items-center">
                    <i class="fas fa-${icon} text-${color} me-2"></i>
                    <h6 class="mb-0">Encoding: ${enc.detected || 'N/A'}
                        ${enc.has_bom ? ' <span class="badge bg-danger ms-1">BOM</span>' : ''}
                        ${isOk
                            ? ' <span class="badge bg-success ms-1">Compatível com Protheus</span>'
                            : ' <span class="badge bg-danger ms-1">INCOMPATÍVEL</span>'
                        }
                    </h6>
                </div>
                <i class="fas fa-chevron-down small text-muted"></i>
            </div>
            ${issues.length ? `
            <div class="collapse ${isOk ? '' : 'show'}" id="encoding-card">
                <div class="card-body py-2">
                    ${issues.map(i => `<div class="small text-danger"><i class="fas fa-arrow-right me-1"></i>${i}</div>`).join('')}
                </div>
            </div>
            ` : ''}
        </div>
    `;
}

function _renderDirtyLinesCard(data) {
    const dirty = data.dirty_lines;
    if (!dirty || !dirty.length) return '';

    return `
        <div class="card mb-3 border-warning">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#dirty-lines">
                <h6 class="mb-0"><i class="fas fa-broom me-2 text-warning"></i>Linhas com Sujeira / Malformadas</h6>
                <div><span class="badge bg-warning text-dark me-2">${dirty.length}</span><i class="fas fa-chevron-down small text-muted"></i></div>
            </div>
            <div class="collapse" id="dirty-lines">
                <div class="table-responsive" style="max-height: 250px; overflow-y: auto;">
                    <table class="table table-sm mb-0">
                        <thead class="sticky-top" style="background: var(--bs-body-bg, #fff);">
                            <tr><th style="width:8%">Linha</th><th style="width:40%">Conteúdo</th><th>Motivo</th></tr>
                        </thead>
                        <tbody>
                            ${dirty.map(d => `
                                <tr class="table-warning">
                                    <td><code>${d.line}</code></td>
                                    <td><code class="small">${_escapeHtml(d.content)}</code></td>
                                    <td class="small">${d.reason}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

function _renderCommentedSectionsCard(data) {
    const csections = data.commented_sections;
    if (!csections || !csections.length) return '';

    return `
        <div class="card mb-3 border-info">
            <div class="card-header py-2 d-flex justify-content-between align-items-center"
                 style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#commented-secs">
                <h6 class="mb-0"><i class="fas fa-eye-slash me-2 text-info"></i>Seções Comentadas (desabilitadas)</h6>
                <div><span class="badge bg-info text-dark me-2">${csections.length}</span><i class="fas fa-chevron-down small text-muted"></i></div>
            </div>
            <div class="collapse" id="commented-secs">
                <div class="list-group list-group-flush">
                    ${csections.map(cs => `
                        <div class="list-group-item py-2">
                            <code class="text-muted">;[${cs.section}]</code>
                            <span class="ms-2 small text-muted">linha ${cs.line}</span>
                            <span class="ms-2 small text-warning">
                                <i class="fas fa-info-circle me-1"></i>
                                Seção inteira desabilitada. Se era um environment ou serviço, pode estar faltando funcionalidade.
                            </span>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
}

function _auditorToggleAllSections(expand) {
    document.querySelectorAll('[id^="section-"]').forEach(el => {
        if (expand) {
            el.classList.add('show');
        } else {
            el.classList.remove('show');
        }
    });
}

function _auditorDownloadSuggestedINI() {
    if (!auditorCurrentResult || !auditorCurrentResult.suggested_ini) return;
    const text = auditorCurrentResult.suggested_ini;

    // Converter para ANSI (Windows-1252) — obrigatório para Protheus
    // TextEncoder só suporta UTF-8 no browser, então usamos mapeamento manual
    const ansiBytes = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i++) {
        const code = text.charCodeAt(i);
        // CP1252 é compatível com Latin-1 para a maioria dos caracteres
        ansiBytes[i] = code <= 0xFF ? code : 0x3F; // '?' para caracteres fora do range
    }

    const blob = new Blob([ansiBytes], { type: 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${auditorCurrentResult.ini_type || 'config'}_sugerido.ini`;
    a.click();
    URL.revokeObjectURL(url);
    showNotification('INI baixado em encoding ANSI (CP1252) — pronto para o Protheus', 'success');
}

function _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function _renderFindingRow(f) {
    const statusIcons = {
        'ok': '<i class="fas fa-check-circle text-success"></i>',
        'mismatch': '<i class="fas fa-times-circle text-danger"></i>',
        'missing': '<i class="fas fa-question-circle text-warning"></i>',
        'unknown': '<i class="fas fa-minus-circle text-muted"></i>',
    };
    const severityBadges = {
        'critical': 'bg-danger',
        'warning': 'bg-warning text-dark',
        'info': 'bg-info text-dark',
    };
    const tdnLink = f.tdn_url || f.bp_tdn_url;
    const desc = f.description || f.bp_description || '';

    return `
        <tr class="${f.status === 'ok' ? '' : 'table-' + (f.severity === 'critical' ? 'danger' : f.severity === 'warning' ? 'warning' : '')}">
            <td>
                <strong>${f.key_name}</strong>
                ${desc ? `<br><small class="text-muted">${desc}</small>` : ''}
            </td>
            <td><code>${f.current_value !== null && f.current_value !== undefined ? f.current_value : '<em class="text-muted">não definido</em>'}</code></td>
            <td><code>${f.recommended_value || '<em class="text-muted">-</em>'}</code></td>
            <td>${statusIcons[f.status] || f.status}</td>
            <td><span class="badge ${severityBadges[f.severity] || 'bg-secondary'}">${f.severity}</span></td>
            <td>${tdnLink ? `<a href="${tdnLink}" target="_blank" class="btn btn-outline-info btn-sm py-0 px-1"><i class="fas fa-external-link-alt"></i> TDN</a>` : ''}</td>
        </tr>
    `;
}

function _auditorExportCSV() {
    if (!auditorCurrentResult) return;
    const findings = auditorCurrentResult.findings || auditorCurrentResult.results || [];
    const lines = ['Seção;Chave;Valor Atual;Recomendado;Status;Severidade'];
    findings.forEach(f => {
        lines.push(`${f.section};${f.key_name};${f.current_value || ''};${f.recommended_value || ''};${f.status};${f.severity}`);
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `auditoria_${auditorCurrentResult.ini_type || 'ini'}_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

// =====================================================================
// TAB: HISTÓRICO
// =====================================================================

function _renderAuditorHistory(container) {
    if (!auditorHistory.length) {
        container.innerHTML = `
            <div class="text-center p-5 text-muted">
                <i class="fas fa-history fa-3x mb-3"></i>
                <p>Nenhuma auditoria realizada ainda.</p>
            </div>
        `;
        return;
    }

    const totalPages = Math.ceil(auditorHistoryTotal / AUDITOR_PER_PAGE);

    container.innerHTML = `
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h6 class="mb-0"><i class="fas fa-history me-2"></i>Histórico de Auditorias</h6>
                <span class="badge bg-secondary">${auditorHistoryTotal} total</span>
            </div>
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Arquivo</th>
                            <th>Tipo</th>
                            <th>Score</th>
                            <th>Seções</th>
                            <th>Chaves</th>
                            <th>Status</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${auditorHistory.map(a => `
                            <tr style="cursor: pointer;" onclick="_auditorLoadDetail(${a.id})">
                                <td>${_formatDate(a.created_at)}</td>
                                <td><strong>${a.filename}</strong></td>
                                <td><span class="badge bg-secondary">${a.ini_type}</span></td>
                                <td>
                                    <span class="badge bg-${a.score >= 80 ? 'success' : a.score >= 50 ? 'warning' : 'danger'}">
                                        ${a.score !== null ? a.score : '-'}
                                    </span>
                                </td>
                                <td>${a.total_sections || 0}</td>
                                <td>${a.total_keys || 0}</td>
                                <td>
                                    ${a.status === 'analyzed' ? '<i class="fas fa-check text-success"></i>' :
                                      a.status === 'error' ? '<i class="fas fa-times text-danger"></i>' :
                                      '<i class="fas fa-spinner fa-spin text-muted"></i>'}
                                </td>
                                <td>
                                    <button class="btn btn-outline-primary btn-sm py-0" onclick="event.stopPropagation(); _auditorLoadDetail(${a.id})">
                                        <i class="fas fa-eye"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>

        ${totalPages > 1 ? _renderPagination(auditorCurrentPage, totalPages, '_auditorGoToPage') : ''}
    `;
}

async function _auditorLoadDetail(auditId) {
    await loadAuditDetail(auditId);
    if (auditorCurrentResult) {
        auditorSwitchTab('results');
    }
}

async function _auditorGoToPage(page) {
    await loadAuditorHistory(page);
    const container = document.getElementById('auditor-tab-content');
    if (container) _renderAuditorHistory(container);
}

function _formatDate(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function _renderPagination(current, total, fnName) {
    let pages = '';
    for (let i = 1; i <= total; i++) {
        pages += `
            <li class="page-item ${i === current ? 'active' : ''}">
                <a class="page-link" href="#" onclick="${fnName}(${i}); return false;">${i}</a>
            </li>
        `;
    }
    return `
        <nav class="mt-3">
            <ul class="pagination pagination-sm justify-content-center">${pages}</ul>
        </nav>
    `;
}

// =====================================================================
// TAB: BOAS PRÁTICAS
// =====================================================================

function _renderAuditorBestPractices(container) {
    const isAdmin = isRootAdmin() || (currentUser && currentUser.profile === 'admin');
    const collapseIcon = auditorBpCollapsed ? 'fa-chevron-down' : 'fa-chevron-up';

    container.innerHTML = `
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center"
                 style="cursor:pointer" onclick="_auditorToggleBpCollapse()">
                <div>
                    <h6 class="mb-0">
                        <i class="fas fa-check-double me-2"></i>Boas Práticas Cadastradas
                        <i class="fas ${collapseIcon} ms-2 small text-muted"></i>
                    </h6>
                </div>
                <div class="d-flex gap-2 align-items-center" onclick="event.stopPropagation()">
                    <select id="bp-type-filter" class="form-select form-select-sm" style="width: auto;"
                            onchange="_auditorChangeBpType(this.value)">
                        <option value="appserver" ${auditorBpType === 'appserver' ? 'selected' : ''}>appserver.ini</option>
                        <option value="dbaccess" ${auditorBpType === 'dbaccess' ? 'selected' : ''}>dbaccess.ini</option>
                        <option value="tss" ${auditorBpType === 'tss' ? 'selected' : ''}>TSS appserver.ini</option>
                        <option value="smartclient" ${auditorBpType === 'smartclient' ? 'selected' : ''}>smartclient.ini</option>
                    </select>
                    ${isAdmin ? `
                    <button class="btn btn-outline-success btn-sm" onclick="_auditorSeedBP()">
                        <i class="fas fa-seedling me-1"></i> Seed TDN
                    </button>
                    ` : ''}
                    <span class="badge bg-secondary">${auditorBestPractices.length} REGRAS</span>
                </div>
            </div>

            <div id="bp-collapse-body" style="${auditorBpCollapsed ? 'display:none' : ''}">
            ${auditorBestPractices.length ? `
            <div class="table-responsive" style="max-height: 480px; overflow-y: auto;">
                <table class="table table-sm table-hover mb-0">
                    <thead style="position: sticky; top: 0; z-index: 1; background: var(--bs-table-bg, #fff);">
                        <tr>
                            <th>Seção</th>
                            <th>Chave</th>
                            <th>Valor Recomendado</th>
                            <th>Tipo</th>
                            <th>Severidade</th>
                            <th>Obrigatório</th>
                            <th>Ref.</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${auditorBestPractices.map(bp => `
                            <tr>
                                <td><code>[${bp.section}]</code></td>
                                <td><strong>${bp.key_name}</strong>
                                    ${bp.description ? `<br><small class="text-muted">${bp.description}</small>` : ''}
                                </td>
                                <td><code>${bp.recommended_value || '-'}</code>
                                    ${bp.min_value ? `<br><small>min: ${bp.min_value}</small>` : ''}
                                    ${bp.max_value ? `<br><small>max: ${bp.max_value}</small>` : ''}
                                </td>
                                <td><span class="badge bg-light text-dark">${bp.value_type}</span></td>
                                <td><span class="badge ${bp.severity === 'critical' ? 'bg-danger' : bp.severity === 'warning' ? 'bg-warning text-dark' : 'bg-info text-dark'}">${bp.severity}</span></td>
                                <td>${bp.is_required ? '<i class="fas fa-check text-success"></i>' : ''}</td>
                                <td>${bp.tdn_url ? `<a href="${bp.tdn_url}" target="_blank"><i class="fas fa-external-link-alt"></i></a>` : ''}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            ` : `
            <div class="card-body text-center text-muted">
                <p>Nenhuma boa prática cadastrada para este tipo.</p>
                ${isAdmin ? '<p>Clique em <strong>Seed TDN</strong> para popular automaticamente.</p>' : ''}
            </div>
            `}
            </div>
        </div>
    `;
}

async function _auditorChangeBpType(type) {
    auditorBpType = type;
    await loadAuditorBestPractices(type);
    _renderAuditorBestPractices(document.getElementById('auditor-tab-content'));
}

function _auditorToggleBpCollapse() {
    auditorBpCollapsed = !auditorBpCollapsed;
    const body = document.getElementById('bp-collapse-body');
    if (body) body.style.display = auditorBpCollapsed ? 'none' : '';
    const icon = document.querySelector('.card-header .fa-chevron-up, .card-header .fa-chevron-down');
    if (icon) {
        icon.classList.toggle('fa-chevron-up', !auditorBpCollapsed);
        icon.classList.toggle('fa-chevron-down', auditorBpCollapsed);
    }
}

async function _auditorSeedBP() {
    try {
        const resp = await apiRequest('/auditor/best-practices/seed', 'POST');
        showNotification(`${resp.count} regras inseridas com sucesso!`, 'success');
        await loadAuditorBestPractices();
        _renderAuditorBestPractices(document.getElementById('auditor-tab-content'));
    } catch (e) {
        showNotification('Erro ao popular boas práticas: ' + (e.message || e), 'danger');
    }
}

// =====================================================================
// UTILITÁRIOS
// =====================================================================

function _renderMarkdown(text) {
    if (!text) return '';
    // Markdown simples: negrito, itálico, code, headers, listas
    return text
        .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/^### (.+)$/gm, '<h6>$1</h6>')
        .replace(/^## (.+)$/gm, '<h5>$1</h5>')
        .replace(/^# (.+)$/gm, '<h4>$1</h4>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
        .replace(/\n/g, '<br>');
}
