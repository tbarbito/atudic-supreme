// =====================================================================
// INTEGRATION-OBSERVABILITY.JS
// Monitoramento: Dashboard de alertas, monitors de log do Protheus
// =====================================================================

// =====================================================================
// ESTADO LOCAL DO MÓDULO
// =====================================================================
let obsMonitors = [];
let obsAlerts = [];
let obsSummary = {};
let obsCurrentPage = 1;
let obsFilters = { severity: '', category: '', acknowledged: '', config_id: '' };
const OBS_PER_PAGE = 25;

// =====================================================================
// CARREGAMENTO DE DADOS
// =====================================================================
async function loadObsMonitors() {
    try {
        obsMonitors = await apiRequest('/log-monitors');
    } catch (e) {
        obsMonitors = [];
        console.error('Erro ao carregar monitors:', e);
    }
}

async function loadObsSummary() {
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const params = envId ? `?environment_id=${envId}` : '';
        obsSummary = await apiRequest(`/log-alerts/summary${params}`);
    } catch (e) {
        obsSummary = {};
        console.error('Erro ao carregar summary:', e);
    }
}

async function loadObsAlerts(page = 1) {
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const params = new URLSearchParams();
        if (envId) params.set('environment_id', envId);
        if (obsFilters.severity) params.set('severity', obsFilters.severity);
        if (obsFilters.category) params.set('category', obsFilters.category);
        if (obsFilters.acknowledged !== '') params.set('acknowledged', obsFilters.acknowledged);
        if (obsFilters.config_id) params.set('config_id', obsFilters.config_id);
        params.set('limit', OBS_PER_PAGE);
        params.set('offset', (page - 1) * OBS_PER_PAGE);

        const result = await apiRequest(`/log-alerts?${params.toString()}`);
        obsAlerts = result.alerts || [];
        obsCurrentPage = page;
        obsSummary._alertsTotal = result.total || 0;
    } catch (e) {
        obsAlerts = [];
        console.error('Erro ao carregar alertas:', e);
    }
}

// =====================================================================
// RENDERIZAÇÃO PRINCIPAL
// =====================================================================
async function showObservability() {
    try {
        await Promise.allSettled([loadObsMonitors(), loadObsSummary()]);
        document.getElementById('content-area').innerHTML = renderObsPage();
        // Carrega alertas na aba ativa
        await loadAndRenderAlerts(1);
    } catch (error) {
        console.error('Erro ao renderizar monitoramento:', error);
        document.getElementById('content-area').innerHTML =
            `<div class="alert alert-danger m-4">Erro ao carregar módulo de monitoramento: ${error.message}</div>`;
    }
}

function renderObsPage() {
    return `
        <div class="content-header d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2><i class="fas fa-satellite-dish me-2"></i>${t('observability.title')}</h2>
                <p class="text-muted mb-0">${t('observability.subtitle')}</p>
            </div>
            <div>
                <button class="btn btn-outline-primary btn-sm me-2" data-action="obsRefresh">
                    <i class="fas fa-sync-alt me-1"></i>${t('common.refresh')}
                </button>
                <button class="btn btn-primary btn-sm" data-action="obsShowCreateMonitor">
                    <i class="fas fa-plus me-1"></i>${t('observability.newMonitor')}
                </button>
            </div>
        </div>

        <!-- Cards de resumo -->
        ${renderObsSummaryCards()}

        <!-- Tabs -->
        <ul class="nav nav-tabs mb-3" role="tablist">
            <li class="nav-item">
                <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#obs-alerts-tab" type="button">
                    <i class="fas fa-bell me-1"></i>${t('observability.alerts')}
                    ${(obsSummary.unacknowledged?.critical || 0) > 0 ? `<span class="badge bg-danger ms-1">${obsSummary.unacknowledged.critical}</span>` : ''}
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" data-bs-toggle="tab" data-bs-target="#obs-monitors-tab" type="button">
                    <i class="fas fa-desktop me-1"></i>${t('observability.monitors')}
                    <span class="badge bg-secondary ms-1">${obsMonitors.length}</span>
                </button>
            </li>
        </ul>

        <div class="tab-content">
            <div class="tab-pane fade show active" id="obs-alerts-tab" role="tabpanel">
                ${renderObsAlertsFilters()}
                <div id="obs-alerts-container">
                    <div class="text-center p-4"><div class="spinner-border text-primary"></div></div>
                </div>
            </div>
            <div class="tab-pane fade" id="obs-monitors-tab" role="tabpanel">
                ${renderObsMonitorsList()}
            </div>
        </div>
    `;
}

// =====================================================================
// CARDS DE RESUMO (DASHBOARD)
// =====================================================================
function renderObsSummaryCards() {
    const critical = obsSummary.unacknowledged?.critical || 0;
    const warning = obsSummary.unacknowledged?.warning || 0;
    const totalAll = (obsSummary.by_severity?.critical || 0) + (obsSummary.by_severity?.warning || 0) + (obsSummary.by_severity?.info || 0);
    const activeMonitors = obsMonitors.filter(m => m.is_active).length;

    return `
        <div class="row mb-4">
            <div class="col-md-3 mb-3">
                <div class="card border-danger h-100">
                    <div class="card-body text-center">
                        <h3 class="text-danger mb-1">${critical}</h3>
                        <small class="text-muted">${t('observability.criticalPending')}</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card border-warning h-100">
                    <div class="card-body text-center">
                        <h3 class="text-warning mb-1">${warning}</h3>
                        <small class="text-muted">${t('observability.warningPending')}</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <h3 class="mb-1">${totalAll}</h3>
                        <small class="text-muted">${t('observability.totalAlerts')}</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card border-success h-100">
                    <div class="card-body text-center">
                        <h3 class="text-success mb-1">${activeMonitors}</h3>
                        <small class="text-muted">${t('observability.activeMonitors')}</small>
                    </div>
                </div>
            </div>
        </div>

    `;
}

// =====================================================================
// FILTROS DE ALERTAS
// =====================================================================
function renderObsAlertsFilters() {
    return `
        <div class="card mb-3">
            <div class="card-body py-2">
                <div class="row g-2 align-items-center">
                    <div class="col-auto">
                        <select class="form-select form-select-sm" id="obs-filter-severity" onchange="obsApplyFilters()">
                            <option value="">${t('observability.allSeverities')}</option>
                            <option value="critical" ${obsFilters.severity === 'critical' ? 'selected' : ''}>Critical</option>
                            <option value="warning" ${obsFilters.severity === 'warning' ? 'selected' : ''}>Warning</option>
                            <option value="info" ${obsFilters.severity === 'info' ? 'selected' : ''}>Info</option>
                        </select>
                    </div>
                    <div class="col-auto">
                        <select class="form-select form-select-sm" id="obs-filter-category" onchange="obsApplyFilters()">
                            <option value="">${t('observability.allCategories')}</option>
                            <option value="database">Database</option>
                            <option value="thread_error">Thread Error</option>
                            <option value="rpo">RPO</option>
                            <option value="service">Service</option>
                            <option value="rest_api">REST API</option>
                            <option value="authentication">Authentication</option>
                            <option value="network">Network</option>
                            <option value="connection">Connection</option>
                            <option value="lifecycle">Lifecycle</option>
                            <option value="compilation">Compilation</option>
                            <option value="shutdown">Shutdown</option>
                            <option value="application">Application</option>
                        </select>
                    </div>
                    <div class="col-auto">
                        <select class="form-select form-select-sm" id="obs-filter-monitor" onchange="obsApplyFilters()">
                            <option value="">${t('observability.allMonitors')}</option>
                            ${obsMonitors.map(m => `<option value="${m.id}" ${obsFilters.config_id === String(m.id) ? 'selected' : ''}>${escapeHtml(m.name)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-auto">
                        <select class="form-select form-select-sm" id="obs-filter-ack" onchange="obsApplyFilters()">
                            <option value="">${t('observability.allStatus')}</option>
                            <option value="false" ${obsFilters.acknowledged === 'false' ? 'selected' : ''}>${t('observability.pending')}</option>
                            <option value="true" ${obsFilters.acknowledged === 'true' ? 'selected' : ''}>${t('observability.acknowledged')}</option>
                        </select>
                    </div>
                    <div class="col-auto">
                        <button class="btn btn-outline-success btn-sm" data-action="obsAcknowledgeAll">
                            <i class="fas fa-check-double me-1"></i>${t('observability.ackAll')}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

window.obsApplyFilters = function () {
    obsFilters.severity = document.getElementById('obs-filter-severity')?.value || '';
    obsFilters.category = document.getElementById('obs-filter-category')?.value || '';
    obsFilters.acknowledged = document.getElementById('obs-filter-ack')?.value || '';
    obsFilters.config_id = document.getElementById('obs-filter-monitor')?.value || '';
    loadAndRenderAlerts(1);
};

// =====================================================================
// LISTA DE ALERTAS
// =====================================================================
async function loadAndRenderAlerts(page) {
    const container = document.getElementById('obs-alerts-container');
    if (!container) return;
    container.innerHTML = `<div class="text-center p-4"><div class="spinner-border text-primary"></div></div>`;

    await loadObsAlerts(page);
    container.innerHTML = renderObsAlertsList();
}

function renderObsAlertsList() {
    if (obsAlerts.length === 0) {
        return `<div class="card text-center p-5"><p class="text-muted mb-0">${t('observability.noAlerts')}</p></div>`;
    }

    const total = obsSummary._alertsTotal || 0;
    const totalPages = Math.ceil(total / OBS_PER_PAGE);

    return `
        <div class="list-group mb-3">
            ${obsAlerts.map(a => `
                <div class="list-group-item ${a.acknowledged ? 'opacity-50' : ''}">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <div class="mb-1">
                                ${getSeverityBadge(a.severity)}
                                <span class="badge bg-secondary me-1">${escapeHtml(a.category)}</span>
                                <small class="text-muted">${escapeHtml(a.environment_name || '')} - ${escapeHtml(a.monitor_name || a.source_file || '')}</small>
                            </div>
                            <p class="mb-1">${escapeHtml(a.message)}</p>
                            <div class="d-flex gap-3 flex-wrap">
                                ${a.raw_line ? `<details><summary class="text-muted small">${t('observability.rawLine')}</summary><pre class="code-viewer code-sm code-scroll-sm code-wrap mt-1 mb-0">${escapeHtml(a.raw_line)}</pre></details>` : ''}
                                ${a.details?.correction_tip ? `<details><summary class="text-info small"><i class="fas fa-lightbulb me-1"></i>${t('observability.correctionTip')}</summary><pre class="code-viewer code-sm code-scroll-sm code-wrap mt-1 mb-0" style="color:#98c379"><i class="fas fa-tools me-1"></i>${escapeHtml(a.details.correction_tip)}</pre></details>` : ''}
                            </div>
                        </div>
                        <div class="text-end text-nowrap ms-3">
                            <small class="text-muted d-block">${a.occurred_at ? new Date(a.occurred_at).toLocaleString('pt-BR') : ''}</small>
                            ${a.thread_id ? `<small class="text-muted d-block">Thread: ${a.thread_id}</small>` : ''}
                            ${a.username ? `<small class="text-muted d-block">${a.username}</small>` : ''}
                            ${!a.acknowledged ? `
                                <button class="btn btn-outline-success btn-sm mt-1" data-action="obsAcknowledge" data-params='{"alertId": ${a.id}}'>
                                    <i class="fas fa-check"></i>
                                </button>
                            ` : `<span class="badge bg-success mt-1"><i class="fas fa-check me-1"></i>OK</span>`}
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>

        ${totalPages > 1 ? renderObsPagination(obsCurrentPage, totalPages) : ''}
        <small class="text-muted">${total} alerta(s) encontrado(s)</small>
    `;
}

function getSeverityBadge(severity) {
    const map = {
        'critical': '<span class="badge bg-danger me-1">CRITICAL</span>',
        'warning': '<span class="badge bg-warning text-dark me-1">WARNING</span>',
        'info': '<span class="badge bg-info text-dark me-1">INFO</span>',
    };
    return map[severity] || `<span class="badge bg-secondary me-1">${severity}</span>`;
}

function renderObsPagination(current, total) {
    let pages = '';
    const start = Math.max(1, current - 2);
    const end = Math.min(total, current + 2);

    if (current > 1) {
        pages += `<li class="page-item"><a class="page-link" href="#" data-action="obsChangePage" data-params='{"page":${current - 1}}'>&laquo;</a></li>`;
    }
    for (let i = start; i <= end; i++) {
        pages += `<li class="page-item ${i === current ? 'active' : ''}"><a class="page-link" href="#" data-action="obsChangePage" data-params='{"page":${i}}'>${i}</a></li>`;
    }
    if (current < total) {
        pages += `<li class="page-item"><a class="page-link" href="#" data-action="obsChangePage" data-params='{"page":${current + 1}}'>&raquo;</a></li>`;
    }

    return `<nav><ul class="pagination pagination-sm justify-content-center">${pages}</ul></nav>`;
}

// =====================================================================
// LISTA DE MONITORS
// =====================================================================
function renderObsMonitorsList() {
    if (obsMonitors.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted mb-2">${t('observability.noMonitors')}</p>
                <div>
                    <button class="btn btn-primary btn-sm" data-action="obsShowCreateMonitor">
                        <i class="fas fa-plus me-1"></i>${t('observability.createFirst')}
                    </button>
                </div>
            </div>
        `;
    }

    return `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>${t('observability.monitorName')}</th>
                        <th>${t('observability.environment')}</th>
                        <th>${t('observability.logPath')}</th>
                        <th>${t('observability.type')}</th>
                        <th>${t('observability.interval')}</th>
                        <th>${t('observability.lastRead')}</th>
                        <th>${t('observability.position')}</th>
                        <th>${t('common.status')}</th>
                        <th>${t('common.actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${obsMonitors.map(m => `
                        <tr>
                            <td><strong>${escapeHtml(m.name)}</strong></td>
                            <td>${escapeHtml(m.environment_name || '')}</td>
                            <td><code class="small">${escapeHtml(m.log_path)}</code></td>
                            <td><span class="badge bg-secondary">${m.log_type || 'console'}</span></td>
                            <td>${m.check_interval_seconds}s</td>
                            <td><small>${m.last_read_at ? new Date(m.last_read_at).toLocaleString('pt-BR') : '-'}</small></td>
                            <td><small>${m.last_read_position || 0}</small></td>
                            <td>
                                ${m.is_active
                                    ? '<span class="badge bg-success">Ativo</span>'
                                    : '<span class="badge bg-secondary">Inativo</span>'}
                            </td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    <button class="btn btn-outline-primary" data-action="obsScanNow" data-params='{"configId": ${m.id}}' title="${t('observability.scanNow')}">
                                        <i class="fas fa-search"></i>
                                    </button>
                                    <button class="btn btn-outline-warning" data-action="obsEditMonitor" data-params='{"configId": ${m.id}}' title="${t('common.edit')}">
                                        <i class="fas fa-edit"></i>
                                    </button>
                                    <button class="btn btn-outline-secondary" data-action="obsResetPosition" data-params='{"configId": ${m.id}}' title="${t('observability.resetPosition')}">
                                        <i class="fas fa-undo"></i>
                                    </button>
                                    <button class="btn btn-outline-danger" data-action="obsDeleteMonitor" data-params='{"configId": ${m.id}}' title="${t('common.delete')}">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// =====================================================================
// MODAIS: CRIAR/EDITAR MONITOR
// =====================================================================
function obsShowCreateMonitorModal() {
    let modal = document.getElementById('obsMonitorModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'obsMonitorModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        document.body.appendChild(modal);
    }

    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-plus me-2"></i>${t('observability.newMonitor')}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">${t('observability.monitorName')}</label>
                        <input type="text" class="form-control" id="obs-mon-name" placeholder="Ex: Slave 02 - Console">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('observability.logPath')}</label>
                        <div class="input-group">
                            <input type="text" class="form-control" id="obs-mon-path" placeholder="console.log">
                            <button class="btn btn-outline-secondary" type="button" data-action="obsBrowseLogs" title="Buscar arquivos .log no LOG_DIR do ambiente">
                                <i class="fas fa-folder-open"></i>
                            </button>
                        </div>
                        <div id="obs-log-files-list" class="d-none mt-1"></div>
                        <small class="form-text text-muted">${t('observability.logPathHelp')}</small>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">${t('observability.logType')}</label>
                            <select class="form-select" id="obs-mon-type">
                                <option value="console">Console Log</option>
                                <option value="error">Error Log</option>
                            </select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">${t('observability.osType')}</label>
                            <select class="form-select" id="obs-mon-os">
                                <option value="windows">Windows</option>
                                <option value="linux">Linux</option>
                            </select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('observability.interval')}</label>
                        <select class="form-select" id="obs-mon-interval">
                            <option value="30">30 segundos</option>
                            <option value="60" selected>1 minuto</option>
                            <option value="120">2 minutos</option>
                            <option value="300">5 minutos</option>
                            <option value="600">10 minutos</option>
                        </select>
                    </div>
                    <hr class="my-3">
                    <div class="mb-3">
                        <h6 class="mb-2"><i class="fas fa-bell me-1"></i>Notificacoes (Opcional)</h6>
                        <label class="form-label text-muted small mb-1">E-mails (separados por virgula)</label>
                        <input type="text" class="form-control form-control-sm" id="obs-mon-notify-emails"
                            placeholder="exemplo@empresa.com, admin@empresa.com">
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="obs-mon-active" checked>
                        <label class="form-check-label" for="obs-mon-active">${t('observability.monitorActive')}</label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-bs-dismiss="modal">${t('common.cancel')}</button>
                    <button class="btn btn-primary" data-action="obsCreateMonitor">
                        <i class="fas fa-save me-1"></i>${t('common.save')}
                    </button>
                </div>
            </div>
        </div>
    `;

    new bootstrap.Modal(modal).show();
}

async function obsCreateMonitor() {
    const data = {
        name: document.getElementById('obs-mon-name')?.value,
        environment_id: parseInt(sessionStorage.getItem('active_environment_id')),
        log_path: document.getElementById('obs-mon-path')?.value,
        log_type: document.getElementById('obs-mon-type')?.value || 'console',
        os_type: document.getElementById('obs-mon-os')?.value || 'windows',
        check_interval_seconds: parseInt(document.getElementById('obs-mon-interval')?.value || '60'),
        is_active: document.getElementById('obs-mon-active')?.checked,
        notify_emails: document.getElementById('obs-mon-notify-emails')?.value.trim() || null,
    };

    if (!data.name || !data.log_path) {
        showNotification('Preencha nome e caminho do log', 'error');
        return;
    }

    try {
        await apiRequest('/log-monitors', 'POST', data);
        showNotification(t('observability.monitorCreated'), 'success');
        bootstrap.Modal.getInstance(document.getElementById('obsMonitorModal'))?.hide();
        showObservability();
    } catch (e) {
        showNotification('Erro ao criar monitor: ' + e.message, 'error');
    }
}

async function obsEditMonitor(configId) {
    const monitor = obsMonitors.find(m => m.id === configId);
    if (!monitor) return;

    let modal = document.getElementById('obsMonitorModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'obsMonitorModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        document.body.appendChild(modal);
    }

    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-edit me-2"></i>${t('observability.editMonitor')}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <input type="hidden" id="obs-edit-id" value="${monitor.id}">
                    <div class="mb-3">
                        <label class="form-label">${t('observability.monitorName')}</label>
                        <input type="text" class="form-control" id="obs-mon-name" value="${escapeHtml(monitor.name)}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('observability.logPath')}</label>
                        <div class="input-group">
                            <input type="text" class="form-control" id="obs-mon-path" value="${escapeHtml(monitor.log_path)}">
                            <button class="btn btn-outline-secondary" type="button" data-action="obsBrowseLogs" title="Buscar arquivos .log no LOG_DIR do ambiente">
                                <i class="fas fa-folder-open"></i>
                            </button>
                        </div>
                        <div id="obs-log-files-list" class="d-none mt-1"></div>
                        <small class="form-text text-muted">${t('observability.logPathHelp')}</small>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">${t('observability.logType')}</label>
                            <select class="form-select" id="obs-mon-type">
                                <option value="console" ${monitor.log_type === 'console' ? 'selected' : ''}>Console Log</option>
                                <option value="error" ${monitor.log_type === 'error' ? 'selected' : ''}>Error Log</option>
                            </select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">${t('observability.osType')}</label>
                            <select class="form-select" id="obs-mon-os">
                                <option value="windows" ${monitor.os_type === 'windows' ? 'selected' : ''}>Windows</option>
                                <option value="linux" ${monitor.os_type === 'linux' ? 'selected' : ''}>Linux</option>
                            </select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('observability.interval')}</label>
                        <select class="form-select" id="obs-mon-interval">
                            <option value="30" ${monitor.check_interval_seconds == 30 ? 'selected' : ''}>30 segundos</option>
                            <option value="60" ${monitor.check_interval_seconds == 60 ? 'selected' : ''}>1 minuto</option>
                            <option value="120" ${monitor.check_interval_seconds == 120 ? 'selected' : ''}>2 minutos</option>
                            <option value="300" ${monitor.check_interval_seconds == 300 ? 'selected' : ''}>5 minutos</option>
                            <option value="600" ${monitor.check_interval_seconds == 600 ? 'selected' : ''}>10 minutos</option>
                        </select>
                    </div>
                    <hr class="my-3">
                    <div class="mb-3">
                        <h6 class="mb-2"><i class="fas fa-bell me-1"></i>Notificacoes (Opcional)</h6>
                        <label class="form-label text-muted small mb-1">E-mails (separados por virgula)</label>
                        <input type="text" class="form-control form-control-sm" id="obs-mon-notify-emails"
                            value="${escapeHtml(monitor.notify_emails || '')}"
                            placeholder="exemplo@empresa.com, admin@empresa.com">
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="obs-mon-active" ${monitor.is_active ? 'checked' : ''}>
                        <label class="form-check-label" for="obs-mon-active">${t('observability.monitorActive')}</label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-bs-dismiss="modal">${t('common.cancel')}</button>
                    <button class="btn btn-primary" data-action="obsSaveMonitor">
                        <i class="fas fa-save me-1"></i>${t('common.save')}
                    </button>
                </div>
            </div>
        </div>
    `;

    new bootstrap.Modal(modal).show();
}

async function obsSaveMonitor() {
    const id = document.getElementById('obs-edit-id')?.value;
    const data = {
        name: document.getElementById('obs-mon-name')?.value,
        log_path: document.getElementById('obs-mon-path')?.value,
        log_type: document.getElementById('obs-mon-type')?.value,
        os_type: document.getElementById('obs-mon-os')?.value,
        check_interval_seconds: parseInt(document.getElementById('obs-mon-interval')?.value || '60'),
        is_active: document.getElementById('obs-mon-active')?.checked,
        notify_emails: document.getElementById('obs-mon-notify-emails')?.value.trim() || null,
    };

    try {
        await apiRequest(`/log-monitors/${id}`, 'PUT', data);
        showNotification(t('observability.monitorUpdated'), 'success');
        bootstrap.Modal.getInstance(document.getElementById('obsMonitorModal'))?.hide();
        showObservability();
    } catch (e) {
        showNotification('Erro ao atualizar monitor: ' + e.message, 'error');
    }
}

async function obsBrowseLogs() {
    var envId = sessionStorage.getItem('active_environment_id');
    if (!envId) {
        showNotification('Selecione um ambiente primeiro', 'error');
        return;
    }

    var container = document.getElementById('obs-log-files-list');
    if (!container) return;

    container.className = 'mt-1';
    container.innerHTML = '<small class="text-muted"><i class="fas fa-spinner fa-spin me-1"></i>Buscando arquivos .log...</small>';

    try {
        var resp = await apiRequest('/log-monitors/browse-logs?environment_id=' + envId);

        if (resp.error) {
            container.innerHTML = '<small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>' + escapeHtml(resp.error) + '</small>';
            return;
        }

        if (!resp.files || resp.files.length === 0) {
            container.innerHTML = '<small class="text-muted"><i class="fas fa-info-circle me-1"></i>Nenhum arquivo .log encontrado em ' + escapeHtml(resp.log_dir) + '</small>';
            return;
        }

        var html = '<select class="form-select form-select-sm" id="obs-log-file-select">';
        html += '<option value="">Selecione um arquivo .log (' + resp.files.length + ' encontrados em ' + escapeHtml(resp.log_dir_var) + ')</option>';
        for (var i = 0; i < resp.files.length; i++) {
            var f = resp.files[i];
            var sizeStr = f.size > 1048576 ? (f.size / 1048576).toFixed(1) + ' MB' : f.size > 1024 ? (f.size / 1024).toFixed(1) + ' KB' : f.size + ' B';
            html += '<option value="' + escapeHtml(f.name) + '">' + escapeHtml(f.name) + ' (' + sizeStr + ')</option>';
        }
        html += '</select>';
        container.innerHTML = html;

        document.getElementById('obs-log-file-select').addEventListener('change', function() {
            if (this.value) {
                document.getElementById('obs-mon-path').value = this.value;
                container.className = 'd-none';
            }
        });
    } catch (e) {
        container.innerHTML = '<small class="text-danger"><i class="fas fa-times me-1"></i>Erro: ' + escapeHtml(e.message) + '</small>';
    }
}

// =====================================================================
// AÇÕES
// =====================================================================
async function obsScanNow(configId) {
    showNotification(t('observability.scanning'), 'info');
    try {
        const result = await apiRequest(`/log-monitors/${configId}/scan`, 'POST');
        if (result.success) {
            showNotification(`Scan completo: ${result.alerts_count} alerta(s), ${result.lines_read} linha(s) lidas`, 'success');
            showObservability();
        } else {
            showNotification('Erro no scan: ' + (result.error || 'desconhecido'), 'error');
        }
    } catch (e) {
        showNotification('Erro ao executar scan: ' + e.message, 'error');
    }
}

async function obsResetPosition(configId) {
    if (!confirm(t('observability.confirmReset'))) return;
    try {
        await apiRequest(`/log-monitors/${configId}/reset`, 'POST');
        showNotification(t('observability.positionReset'), 'success');
        showObservability();
    } catch (e) {
        showNotification('Erro ao resetar: ' + e.message, 'error');
    }
}

async function obsDeleteMonitor(configId) {
    if (!confirm(t('observability.confirmDelete'))) return;
    try {
        await apiRequest(`/log-monitors/${configId}`, 'DELETE');
        showNotification(t('observability.monitorDeleted'), 'success');
        showObservability();
    } catch (e) {
        showNotification('Erro ao remover: ' + e.message, 'error');
    }
}

async function obsAcknowledge(alertId) {
    try {
        await apiRequest(`/log-alerts/${alertId}/acknowledge`, 'POST');
        showNotification(t('observability.alertAcknowledged'), 'success');
        // Atualiza a lista sem recarregar tudo
        await loadObsSummary();
        await loadAndRenderAlerts(obsCurrentPage);
        // Atualiza cards de resumo
        const header = document.querySelector('.content-header');
        if (header) {
            header.parentElement.querySelector('.row.mb-4').outerHTML = renderObsSummaryCards();
        }
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function obsAcknowledgeAll() {
    const visibleIds = obsAlerts.filter(a => !a.acknowledged).map(a => a.id);
    if (visibleIds.length === 0) {
        showNotification(t('observability.noPending'), 'info');
        return;
    }
    if (!confirm(`Reconhecer ${visibleIds.length} alerta(s)?`)) return;

    try {
        await apiRequest('/log-alerts/acknowledge-bulk', 'POST', { alert_ids: visibleIds });
        showNotification(`${visibleIds.length} alerta(s) reconhecido(s)`, 'success');
        showObservability();
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}
