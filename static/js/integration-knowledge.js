// =====================================================================
// INTEGRATION-KNOWLEDGE.JS
// Base de Conhecimento, Analise Inteligente, Correcoes e Notificacoes
// =====================================================================

// ===== ESTADO LOCAL DO MODULO =====
let kbArticles = [];
let kbCategories = [];
let kbTotal = 0;
let kbCurrentPage = 1;
let kbFilters = { q: '', category: '' };
const KB_PER_PAGE = 20;

let anaRecurring = [];
let anaOverview = {};

let corrList = [];
let corrTotal = 0;
let corrCurrentPage = 1;

let nrRules = [];

let kbActiveTab = 'knowledge';

// =====================================================================
// CARREGAMENTO DE DADOS
// =====================================================================

async function loadKbArticles(page) {
    page = page || 1;
    kbCurrentPage = page;
    const offset = (page - 1) * KB_PER_PAGE;
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        let qs = `?limit=${KB_PER_PAGE}&offset=${offset}`;
        if (kbFilters.q) qs += `&q=${encodeURIComponent(kbFilters.q)}`;
        if (kbFilters.category) qs += `&category=${encodeURIComponent(kbFilters.category)}`;
        const resp = await apiRequest(`/knowledge${qs}`);
        kbArticles = resp.articles || [];
        kbTotal = resp.total || 0;
    } catch (e) {
        kbArticles = [];
        kbTotal = 0;
        console.error('Erro ao carregar artigos:', e);
    }
}

async function loadKbCategories() {
    try {
        kbCategories = await apiRequest('/knowledge/categories');
    } catch (e) {
        kbCategories = [];
    }
}

async function loadAnaRecurring() {
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        let qs = '?min_count=2&days=7&limit=20';
        if (envId) qs += `&environment_id=${envId}`;
        anaRecurring = await apiRequest(`/analysis/recurring${qs}`);
    } catch (e) {
        anaRecurring = [];
    }
}

async function loadAnaOverview() {
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        let qs = '?days=7';
        if (envId) qs += `&environment_id=${envId}`;
        anaOverview = await apiRequest(`/analysis/overview${qs}`);
    } catch (e) {
        anaOverview = {};
    }
}

async function loadCorrections(page) {
    page = page || 1;
    corrCurrentPage = page;
    const offset = (page - 1) * KB_PER_PAGE;
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        let qs = `?limit=${KB_PER_PAGE}&offset=${offset}`;
        if (envId) qs += `&environment_id=${envId}`;
        const resp = await apiRequest(`/corrections${qs}`);
        corrList = resp.corrections || [];
        corrTotal = resp.total || 0;
    } catch (e) {
        corrList = [];
        corrTotal = 0;
    }
}

async function loadNrRules() {
    try {
        const envId = sessionStorage.getItem('active_environment_id');
        let qs = envId ? `?environment_id=${envId}` : '';
        nrRules = await apiRequest(`/notification-rules${qs}`);
    } catch (e) {
        nrRules = [];
    }
}

// =====================================================================
// RENDERIZACAO PRINCIPAL
// =====================================================================

async function showKnowledge() {
    try {
        document.getElementById('content-area').innerHTML = `
            <div class="text-center p-5"><div class="spinner-border"></div></div>`;
        await Promise.allSettled([loadKbArticles(1), loadKbCategories()]);
        document.getElementById('content-area').innerHTML = renderKbPage();
        kbSwitchTab('knowledge');
    } catch (error) {
        console.error('Erro ao renderizar knowledge:', error);
        document.getElementById('content-area').innerHTML =
            `<div class="alert alert-danger m-4">Erro ao carregar modulo: ${error.message}</div>`;
    }
}

function renderKbPage() {
    return `
        <div class="content-header d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2><i class="fas fa-book me-2"></i>${t('knowledge.title')}</h2>
                <p class="text-muted mb-0">${t('knowledge.subtitle')}</p>
            </div>
            <div>
                <button class="btn btn-outline-primary btn-sm me-2" data-action="kbRefresh">
                    <i class="fas fa-sync-alt me-1"></i>${t('common.refresh')}
                </button>
            </div>
        </div>

        <ul class="nav nav-tabs mb-3" role="tablist">
            <li class="nav-item">
                <button class="nav-link active" id="kb-tab-knowledge" data-action="kbSwitchTab" data-params='{"tab":"knowledge"}'>
                    <i class="fas fa-book me-1"></i>${t('knowledge.title')}
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" id="kb-tab-analysis" data-action="kbSwitchTab" data-params='{"tab":"analysis"}'>
                    <i class="fas fa-chart-bar me-1"></i>${t('analysis.title')}
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" id="kb-tab-corrections" data-action="kbSwitchTab" data-params='{"tab":"corrections"}'>
                    <i class="fas fa-wrench me-1"></i>${t('corrections.title')}
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" id="kb-tab-notifications" data-action="kbSwitchTab" data-params='{"tab":"notifications"}'>
                    <i class="fas fa-bell me-1"></i>${t('notificationRules.title')}
                </button>
            </li>
        </ul>

        <div id="kb-tab-content">
            <!-- Conteudo carregado dinamicamente -->
        </div>
    `;
}

// =====================================================================
// ABAS
// =====================================================================

async function kbSwitchTab(tab) {
    if (typeof tab === 'object' && tab.tab) tab = tab.tab;
    kbActiveTab = tab;

    // Atualizar abas ativas
    document.querySelectorAll('.nav-tabs .nav-link').forEach(el => el.classList.remove('active'));
    const activeEl = document.getElementById(`kb-tab-${tab}`);
    if (activeEl) activeEl.classList.add('active');

    const container = document.getElementById('kb-tab-content');
    if (!container) return;
    container.innerHTML = `<div class="text-center p-4"><div class="spinner-border"></div></div>`;

    if (tab === 'knowledge') {
        await loadKbArticles(kbCurrentPage);
        container.innerHTML = renderKnowledgeTab();
    } else if (tab === 'analysis') {
        await Promise.allSettled([loadAnaRecurring(), loadAnaOverview()]);
        container.innerHTML = renderAnalysisTab();
    } else if (tab === 'corrections') {
        await loadCorrections(corrCurrentPage);
        container.innerHTML = renderCorrectionsTab();
    } else if (tab === 'notifications') {
        await loadNrRules();
        container.innerHTML = renderNotificationsTab();
    }
}

// =====================================================================
// ABA: BASE DE CONHECIMENTO
// =====================================================================

function renderKnowledgeTab() {
    return `
        ${renderKbActions()}
        ${renderKbFilters()}
        <div id="kb-articles-list">
            ${renderKbArticlesList()}
        </div>
    `;
}

function renderKbActions() {
    const importBtn = isAdmin() ? `
        <button class="btn btn-outline-success btn-sm me-2" data-action="kbImportArticles">
            <i class="fas fa-file-import me-1"></i>${t('knowledge.importArticles')}
        </button>` : '';
    const newBtn = isAdmin() ? `
        <button class="btn btn-primary btn-sm" data-action="kbShowCreateArticle">
            <i class="fas fa-plus me-1"></i>${t('knowledge.newArticle')}
        </button>` : '';
    return `<div class="d-flex justify-content-between align-items-center mb-3">
        <span class="text-muted">${kbTotal} artigo(s)</span>
        <div>${importBtn}${newBtn}</div>
    </div>`;
}

function renderKbFilters() {
    const catOptions = kbCategories.map(c =>
        `<option value="${escapeHtml(c.category)}" ${kbFilters.category === c.category ? 'selected' : ''}>${escapeHtml(c.category)} (${c.count})</option>`
    ).join('');
    return `
        <div class="card mb-3">
            <div class="card-body py-2">
                <div class="row g-2 align-items-center">
                    <div class="col-md-6 col-12">
                        <div class="input-group input-group-sm">
                            <span class="input-group-text"><i class="fas fa-search"></i></span>
                            <input type="text" class="form-control" id="kb-search-input"
                                   placeholder="${t('knowledge.searchPlaceholder')}"
                                   value="${escapeHtml(kbFilters.q)}"
                                   onkeydown="if(event.key==='Enter') kbApplyFilters()">
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <select class="form-select form-select-sm" id="kb-filter-category" onchange="kbApplyFilters()">
                            <option value="">${t('knowledge.allCategories')}</option>
                            ${catOptions}
                        </select>
                    </div>
                    <div class="col-md-3 col-6">
                        <button class="btn btn-outline-secondary btn-sm w-100" data-action="kbApplyFilters">
                            <i class="fas fa-filter me-1"></i>${t('common.filter')}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderKbArticlesList() {
    if (kbArticles.length === 0) {
        return `<div class="card"><div class="card-body text-center text-muted p-5">
            <i class="fas fa-book-open fa-3x mb-3 d-block"></i>
            ${t('knowledge.noArticles')}
        </div></div>`;
    }

    const totalPages = Math.ceil(kbTotal / KB_PER_PAGE);

    return `
        <div class="row">
            ${kbArticles.map(a => renderKbArticleCard(a)).join('')}
        </div>
        ${totalPages > 1 ? renderKbPagination(kbCurrentPage, totalPages, 'kbChangePage') : ''}
    `;
}

function renderKbArticleCard(article) {
    const catBadge = getCategoryBadge(article.category);
    const sourceIcon = article.source === 'import' ? '<i class="fas fa-file-import text-info" title="Importado"></i>' : '';
    const desc = article.description ? truncate(article.description, 120) : '';
    const deleteBtn = isAdmin() ? `
        <button class="btn btn-sm btn-outline-danger" data-action="kbDeleteArticle" data-params='{"id":${article.id}}' title="${t('common.delete')}">
            <i class="fas fa-trash"></i>
        </button>` : '';
    const editBtn = isAdmin() ? `
        <button class="btn btn-sm btn-outline-primary me-1" data-action="kbEditArticle" data-params='{"id":${article.id}}' title="${t('common.edit')}">
            <i class="fas fa-edit"></i>
        </button>` : '';

    return `
        <div class="col-md-6 col-12 mb-3">
            <div class="card h-100 kb-article-card" style="cursor:pointer" data-action="kbViewArticle" data-params='{"id":${article.id}}'>
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <h6 class="card-title mb-0 text-truncate flex-grow-1" title="${escapeHtml(article.title)}">
                            ${sourceIcon} ${escapeHtml(article.title)}
                        </h6>
                        ${catBadge}
                    </div>
                    <p class="card-text text-muted small mb-2">${escapeHtml(desc)}</p>
                    <div class="d-flex justify-content-between align-items-center">
                        <small class="text-muted">
                            <i class="fas fa-eye me-1"></i>${article.usage_count || 0} ${t('knowledge.usageCount')}
                        </small>
                        <div class="btn-group">
                            ${editBtn}${deleteBtn}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function kbApplyFilters() {
    const searchEl = document.getElementById('kb-search-input');
    const catEl = document.getElementById('kb-filter-category');
    kbFilters.q = searchEl ? searchEl.value : '';
    kbFilters.category = catEl ? catEl.value : '';
    kbCurrentPage = 1;
    kbSwitchTab('knowledge');
}

// =====================================================================
// ABA: ANALISE INTELIGENTE
// =====================================================================

function renderAnalysisTab() {
    return `
        ${renderAnaOverviewCards()}
        <div class="row">
            <div class="col-lg-7 col-12 mb-3">
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0"><i class="fas fa-redo me-2"></i>${t('analysis.recurringErrors')}</h6>
                    </div>
                    <div class="card-body p-0">
                        ${renderAnaRecurringList()}
                    </div>
                </div>
            </div>
            <div class="col-lg-5 col-12 mb-3">
                <div class="card">
                    <div class="card-header">
                        <h6 class="mb-0"><i class="fas fa-chart-line me-2"></i>${t('analysis.trends')}</h6>
                    </div>
                    <div class="card-body p-0">
                        ${renderAnaTrendsList()}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderAnaOverviewCards() {
    const cats = anaOverview.categories || [];
    const totalErrors = cats.reduce((sum, c) => sum + (c.total || 0), 0);
    const increasing = cats.filter(c => c.trend === 'increasing').length;
    const recurringCount = anaRecurring.length;

    return `
        <div class="row mb-4">
            <div class="col-md-4 col-12 mb-3">
                <div class="card border-info h-100">
                    <div class="card-body text-center">
                        <h3 class="text-info">${totalErrors}</h3>
                        <small class="text-muted">Erros (7 ${t('analysis.days')})</small>
                    </div>
                </div>
            </div>
            <div class="col-md-4 col-12 mb-3">
                <div class="card border-warning h-100">
                    <div class="card-body text-center">
                        <h3 class="text-warning">${recurringCount}</h3>
                        <small class="text-muted">${t('analysis.recurringErrors')}</small>
                    </div>
                </div>
            </div>
            <div class="col-md-4 col-12 mb-3">
                <div class="card border-danger h-100">
                    <div class="card-body text-center">
                        <h3 class="text-danger">${increasing}</h3>
                        <small class="text-muted"><i class="fas fa-arrow-up me-1"></i>${t('analysis.increasing')}</small>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderAnaRecurringList() {
    if (anaRecurring.length === 0) {
        return `<div class="text-center text-muted p-4">${t('analysis.noRecurring')}</div>`;
    }
    return `
        <div class="table-responsive">
            <table class="table table-sm table-hover mb-0">
                <thead>
                    <tr>
                        <th>Erro</th>
                        <th class="text-center">${t('analysis.occurrences')}</th>
                        <th>${t('analysis.lastSeen')}</th>
                        <th>${t('analysis.suggestion')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${anaRecurring.map(e => `
                        <tr>
                            <td>
                                <div class="text-truncate" style="max-width:300px" title="${escapeHtml(e.message_pattern || '')}">
                                    ${getCategoryBadge(e.category)}
                                    <small>${escapeHtml(truncate(e.message_pattern || '', 60))}</small>
                                </div>
                            </td>
                            <td class="text-center"><span class="badge bg-secondary">${e.occurrence_count || 0}</span></td>
                            <td><small>${e.last_seen_at ? formatDate(e.last_seen_at) : '-'}</small></td>
                            <td>
                                ${e.article_title
                                    ? `<a href="#" data-action="kbViewArticle" data-params='{"id":${e.article_id}}'><i class="fas fa-lightbulb text-warning me-1"></i>${escapeHtml(truncate(e.article_title, 30))}</a>`
                                    : '<span class="text-muted">-</span>'}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderAnaTrendsList() {
    const cats = anaOverview.categories || [];
    if (cats.length === 0) {
        return `<div class="text-center text-muted p-4">Sem dados no periodo</div>`;
    }
    return `
        <div class="list-group list-group-flush">
            ${cats.map(c => {
                const trendIcon = getTrendIcon(c.trend);
                return `
                    <div class="list-group-item d-flex justify-content-between align-items-center">
                        <div>
                            ${getCategoryBadge(c.category)}
                            <span class="ms-2">${c.total || 0} erros</span>
                        </div>
                        <div>${trendIcon}</div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

// =====================================================================
// ABA: HISTORICO DE CORRECOES
// =====================================================================

function renderCorrectionsTab() {
    const newBtn = isOperator() ? `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="text-muted">${corrTotal} registro(s)</span>
            <button class="btn btn-primary btn-sm" data-action="kbShowCreateCorrection">
                <i class="fas fa-plus me-1"></i>${t('corrections.newCorrection')}
            </button>
        </div>` : '';

    return `
        ${newBtn}
        ${renderCorrectionsList()}
    `;
}

function renderCorrectionsList() {
    if (corrList.length === 0) {
        return `<div class="card"><div class="card-body text-center text-muted p-5">
            <i class="fas fa-wrench fa-3x mb-3 d-block"></i>
            ${t('corrections.noCorrections')}
        </div></div>`;
    }

    const totalPages = Math.ceil(corrTotal / KB_PER_PAGE);

    return `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>${t('corrections.errorCategory')}</th>
                        <th>${t('corrections.errorMessage')}</th>
                        <th>${t('corrections.correctionApplied')}</th>
                        <th>${t('corrections.appliedBy')}</th>
                        <th>${t('common.status')}</th>
                        <th>${t('common.actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${corrList.map(c => `
                        <tr>
                            <td>${getCategoryBadge(c.error_category)}</td>
                            <td><small class="text-truncate d-inline-block" style="max-width:200px" title="${escapeHtml(c.error_message || '')}">${escapeHtml(truncate(c.error_message || '', 50))}</small></td>
                            <td><small class="text-truncate d-inline-block" style="max-width:200px" title="${escapeHtml(c.correction_applied || '')}">${escapeHtml(truncate(c.correction_applied || '', 50))}</small></td>
                            <td><small>${escapeHtml(c.applied_by_username || '-')}</small></td>
                            <td>${c.status === 'validated'
                                ? `<span class="badge bg-success"><i class="fas fa-check me-1"></i>${t('corrections.validated')}</span>`
                                : `<span class="badge bg-warning text-dark">${t('corrections.pending')}</span>`}
                            </td>
                            <td>
                                ${c.status !== 'validated' && isOperator() ? `
                                    <button class="btn btn-sm btn-outline-success" data-action="kbValidateCorrection" data-params='{"id":${c.id}}' title="${t('corrections.validate')}">
                                        <i class="fas fa-check"></i>
                                    </button>` : ''}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        ${totalPages > 1 ? renderKbPagination(corrCurrentPage, totalPages, 'kbChangeCorrPage') : ''}
    `;
}

// =====================================================================
// ABA: REGRAS DE NOTIFICACAO
// =====================================================================

function renderNotificationsTab() {
    const newBtn = isOperator() ? `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <span class="text-muted">${nrRules.length} regra(s)</span>
            <button class="btn btn-primary btn-sm" data-action="kbShowCreateRule">
                <i class="fas fa-plus me-1"></i>${t('notificationRules.newRule')}
            </button>
        </div>` : '';

    return `
        ${newBtn}
        ${renderNrRulesList()}
    `;
}

function renderNrRulesList() {
    if (nrRules.length === 0) {
        return `<div class="card"><div class="card-body text-center text-muted p-5">
            <i class="fas fa-bell-slash fa-3x mb-3 d-block"></i>
            ${t('notificationRules.noRules')}
        </div></div>`;
    }

    return `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>${t('common.name')}</th>
                        <th>Severidade</th>
                        <th>${t('notificationRules.channels')}</th>
                        <th>${t('notificationRules.minOccurrences')}</th>
                        <th>${t('notificationRules.cooldown')}</th>
                        <th>${t('notificationRules.triggerCount')}</th>
                        <th>${t('notificationRules.lastTriggered')}</th>
                        <th>${t('common.actions')}</th>
                    </tr>
                </thead>
                <tbody>
                    ${nrRules.map(r => {
                        const channels = [];
                        if (r.notify_email) channels.push('<i class="fas fa-envelope text-primary" title="Email"></i>');
                        if (r.notify_whatsapp) channels.push('<i class="fab fa-whatsapp text-success" title="WhatsApp"></i>');
                        if (r.notify_webhook) channels.push('<i class="fas fa-plug text-info" title="Webhook"></i>');
                        return `
                            <tr>
                                <td>
                                    <strong>${escapeHtml(r.name)}</strong>
                                    ${r.category ? `<br><small class="text-muted">${escapeHtml(r.category)}</small>` : ''}
                                </td>
                                <td>${getSeverityBadge(r.severity)}</td>
                                <td>${channels.join(' ') || '-'}</td>
                                <td class="text-center">${r.min_occurrences || 1}</td>
                                <td class="text-center">${r.cooldown_minutes || 30}min</td>
                                <td class="text-center"><span class="badge bg-secondary">${r.trigger_count || 0}</span></td>
                                <td><small>${r.last_triggered_at ? formatDate(r.last_triggered_at) : '-'}</small></td>
                                <td>
                                    ${isOperator() ? `
                                        <button class="btn btn-sm btn-outline-primary me-1" data-action="kbEditRule" data-params='{"id":${r.id}}' title="${t('common.edit')}">
                                            <i class="fas fa-edit"></i>
                                        </button>` : ''}
                                    ${isAdmin() ? `
                                        <button class="btn btn-sm btn-outline-danger" data-action="kbDeleteRule" data-params='{"id":${r.id}}' title="${t('common.delete')}">
                                            <i class="fas fa-trash"></i>
                                        </button>` : ''}
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// =====================================================================
// MODAIS
// =====================================================================

async function kbViewArticle(id) {
    try {
        const article = await apiRequest(`/knowledge/${id}`);
        let modal = document.getElementById('kbViewModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'kbViewModal';
            modal.className = 'modal fade';
            modal.tabIndex = -1;
            document.body.appendChild(modal);
        }

        const refLink = article.reference_url
            ? `<a href="${escapeHtml(article.reference_url)}" target="_blank" rel="noopener noreferrer"><i class="fas fa-external-link-alt me-1"></i>${t('knowledge.reference')}</a>`
            : '';

        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            ${getCategoryBadge(article.category)}
                            <span class="ms-2">${escapeHtml(article.title)}</span>
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${article.description ? `<div class="mb-3"><strong>${t('common.description')}:</strong><p>${escapeHtml(article.description)}</p></div>` : ''}
                        ${article.causes ? `<div class="mb-3"><strong>${t('knowledge.causes')}:</strong><pre class="code-viewer code-sm code-wrap">${escapeHtml(article.causes)}</pre></div>` : ''}
                        ${article.solution ? `<div class="mb-3"><strong>${t('knowledge.solution')}:</strong><pre class="code-viewer code-sm code-wrap">${escapeHtml(article.solution)}</pre></div>` : ''}
                        ${article.code_snippet ? `<div class="mb-3"><strong>Code:</strong><pre class="code-viewer code-sm"><code>${escapeHtml(article.code_snippet)}</code></pre></div>` : ''}
                        <div class="d-flex justify-content-between text-muted small">
                            <span>${refLink}</span>
                            <span><i class="fas fa-eye me-1"></i>${article.usage_count || 0} ${t('knowledge.usageCount')}</span>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" data-bs-dismiss="modal">${t('common.close')}</button>
                    </div>
                </div>
            </div>
        `;
        new bootstrap.Modal(modal).show();
    } catch (e) {
        showNotification('Erro ao carregar artigo: ' + e.message, 'error');
    }
}

function kbShowCreateArticle() {
    kbShowArticleModal(null);
}

function kbEditArticle(id) {
    kbShowArticleModal(id);
}

async function kbShowArticleModal(articleId) {
    let article = {};
    if (articleId) {
        try {
            article = await apiRequest(`/knowledge/${articleId}`);
        } catch (e) {
            showNotification('Erro ao carregar artigo', 'error');
            return;
        }
    }

    const title = articleId ? t('common.edit') : t('knowledge.newArticle');
    const catOptions = ['database', 'network', 'thread_error', 'ads_ctree', 'alias_workarea',
        'array_error', 'dbf_file', 'rpo_repository', 'type_variable', 'memory', 'index_key',
        'lock_semaphore', 'string_char', 'general', 'performance']
        .map(c => `<option value="${c}" ${article.category === c ? 'selected' : ''}>${c}</option>`).join('');

    let modal = document.getElementById('kbArticleModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'kbArticleModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        document.body.appendChild(modal);
    }

    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-book me-2"></i>${title}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <input type="hidden" id="kb-article-id" value="${articleId || ''}">
                    <div class="row">
                        <div class="col-md-8 mb-3">
                            <label class="form-label">Titulo *</label>
                            <input type="text" class="form-control" id="kb-article-title" value="${escapeHtml(article.title || '')}">
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">Categoria *</label>
                            <select class="form-select" id="kb-article-category">${catOptions}</select>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Padrao de Erro (regex)</label>
                        <input type="text" class="form-control" id="kb-article-pattern" value="${escapeHtml(article.error_pattern || '')}" placeholder="Ex: ORA-\\d+">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('common.description')}</label>
                        <textarea class="form-control" id="kb-article-desc" rows="2">${escapeHtml(article.description || '')}</textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('knowledge.causes')}</label>
                        <textarea class="form-control" id="kb-article-causes" rows="2">${escapeHtml(article.causes || '')}</textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('knowledge.solution')}</label>
                        <textarea class="form-control" id="kb-article-solution" rows="3">${escapeHtml(article.solution || '')}</textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Code Snippet</label>
                        <textarea class="form-control font-monospace" id="kb-article-code" rows="3">${escapeHtml(article.code_snippet || '')}</textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('knowledge.reference')} (URL)</label>
                        <input type="text" class="form-control" id="kb-article-ref" value="${escapeHtml(article.reference_url || '')}" placeholder="https://tdn.totvs.com/...">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-bs-dismiss="modal">${t('common.cancel')}</button>
                    <button class="btn btn-primary" data-action="kbSaveArticle">
                        <i class="fas fa-save me-1"></i>${t('common.save')}
                    </button>
                </div>
            </div>
        </div>
    `;
    new bootstrap.Modal(modal).show();
}

async function kbSaveArticle() {
    const id = document.getElementById('kb-article-id')?.value;
    const data = {
        title: document.getElementById('kb-article-title')?.value,
        category: document.getElementById('kb-article-category')?.value,
        error_pattern: document.getElementById('kb-article-pattern')?.value,
        description: document.getElementById('kb-article-desc')?.value,
        causes: document.getElementById('kb-article-causes')?.value,
        solution: document.getElementById('kb-article-solution')?.value,
        code_snippet: document.getElementById('kb-article-code')?.value,
        reference_url: document.getElementById('kb-article-ref')?.value,
    };

    if (!data.title || !data.category) {
        showNotification('Titulo e categoria sao obrigatorios', 'error');
        return;
    }

    try {
        if (id) {
            await apiRequest(`/knowledge/${id}`, 'PUT', data);
            showNotification('Artigo atualizado com sucesso', 'success');
        } else {
            await apiRequest('/knowledge', 'POST', data);
            showNotification('Artigo criado com sucesso', 'success');
        }
        bootstrap.Modal.getInstance(document.getElementById('kbArticleModal'))?.hide();
        await loadKbCategories();
        kbSwitchTab('knowledge');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function kbDeleteArticle(id) {
    if (!confirm(t('knowledge.confirmDelete'))) return;
    try {
        await apiRequest(`/knowledge/${id}`, 'DELETE');
        showNotification('Artigo removido', 'success');
        await loadKbCategories();
        kbSwitchTab('knowledge');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

function kbImportArticles() {
    // Cria input de arquivo invisível e dispara seleção
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.md';
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);

    fileInput.addEventListener('change', async () => {
        const file = fileInput.files[0];
        document.body.removeChild(fileInput);
        if (!file) return;

        try {
            showNotification(`Importando ${file.name}...`, 'info');
            const formData = new FormData();
            formData.append('file', file);

            const headers = {};
            if (authToken) headers['Authorization'] = authToken;
            const envId = sessionStorage.getItem('active_environment_id');
            if (envId) headers['X-Environment-Id'] = envId;

            const response = await fetch(`${API_BASE_URL}/knowledge/import`, {
                method: 'POST',
                headers: headers,
                body: formData,
            });

            const result = await response.json();
            if (!response.ok) throw new Error(result.error || `Erro ${response.status}`);

            showNotification(result.message || 'Importacao concluida', 'success');
            await loadKbCategories();
            kbSwitchTab('knowledge');
        } catch (e) {
            showNotification('Erro na importacao: ' + e.message, 'error');
        }
    });

    fileInput.click();
}

// MODAL: CRIAR CORRECAO

function kbShowCreateCorrection() {
    let modal = document.getElementById('kbCorrModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'kbCorrModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        document.body.appendChild(modal);
    }

    const catOptions = ['database', 'network', 'thread_error', 'ads_ctree', 'alias_workarea',
        'array_error', 'dbf_file', 'rpo_repository', 'type_variable', 'memory', 'index_key',
        'lock_semaphore', 'string_char', 'general', 'performance']
        .map(c => `<option value="${c}">${c}</option>`).join('');

    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-wrench me-2"></i>${t('corrections.newCorrection')}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">${t('corrections.errorCategory')} *</label>
                            <select class="form-select" id="corr-category">${catOptions}</select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Arquivo Fonte</label>
                            <input type="text" class="form-control" id="corr-source-file" placeholder="Ex: MATA410.PRW">
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('corrections.errorMessage')} *</label>
                        <textarea class="form-control" id="corr-error-msg" rows="2"></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('corrections.correctionApplied')} *</label>
                        <textarea class="form-control" id="corr-applied" rows="3"></textarea>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('corrections.lessonLearned')}</label>
                        <textarea class="form-control" id="corr-lesson" rows="2"></textarea>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-bs-dismiss="modal">${t('common.cancel')}</button>
                    <button class="btn btn-primary" data-action="kbSaveCorrection">
                        <i class="fas fa-save me-1"></i>${t('common.save')}
                    </button>
                </div>
            </div>
        </div>
    `;
    new bootstrap.Modal(modal).show();
}

async function kbSaveCorrection() {
    const data = {
        error_category: document.getElementById('corr-category')?.value,
        error_message: document.getElementById('corr-error-msg')?.value,
        correction_applied: document.getElementById('corr-applied')?.value,
        source_file: document.getElementById('corr-source-file')?.value,
        lesson_learned: document.getElementById('corr-lesson')?.value,
        environment_id: sessionStorage.getItem('active_environment_id') || null,
    };

    if (!data.error_category || !data.error_message || !data.correction_applied) {
        showNotification('Preencha os campos obrigatorios', 'error');
        return;
    }

    try {
        await apiRequest('/corrections', 'POST', data);
        showNotification('Correcao registrada com sucesso', 'success');
        bootstrap.Modal.getInstance(document.getElementById('kbCorrModal'))?.hide();
        kbSwitchTab('corrections');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function kbValidateCorrection(id) {
    try {
        await apiRequest(`/corrections/${id}/validate`, 'POST');
        showNotification('Correcao validada', 'success');
        kbSwitchTab('corrections');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// MODAL: CRIAR REGRA DE NOTIFICACAO

function kbShowCreateRule() {
    kbShowRuleModal(null);
}

function kbEditRule(id) {
    const rule = nrRules.find(r => r.id === id);
    if (rule) kbShowRuleModal(rule);
}

function kbShowRuleModal(rule) {
    rule = rule || {};
    const title = rule.id ? t('common.edit') : t('notificationRules.newRule');

    let modal = document.getElementById('kbRuleModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'kbRuleModal';
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        document.body.appendChild(modal);
    }

    const sevOptions = ['critical', 'warning', 'info'].map(s =>
        `<option value="${s}" ${rule.severity === s ? 'selected' : ''}>${s}</option>`
    ).join('');

    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-bell me-2"></i>${title}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <input type="hidden" id="nr-rule-id" value="${rule.id || ''}">
                    <div class="mb-3">
                        <label class="form-label">${t('notificationRules.ruleName')} *</label>
                        <input type="text" class="form-control" id="nr-name" value="${escapeHtml(rule.name || '')}">
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Severidade *</label>
                            <select class="form-select" id="nr-severity">${sevOptions}</select>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Categoria</label>
                            <input type="text" class="form-control" id="nr-category" value="${escapeHtml(rule.category || '')}" placeholder="Todas">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-4 mb-3">
                            <label class="form-label">${t('notificationRules.minOccurrences')}</label>
                            <input type="number" class="form-control" id="nr-min-occ" value="${rule.min_occurrences || 1}" min="1">
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">${t('notificationRules.timeWindow')}</label>
                            <input type="number" class="form-control" id="nr-window" value="${rule.time_window_minutes || 5}" min="1">
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">${t('notificationRules.cooldown')}</label>
                            <input type="number" class="form-control" id="nr-cooldown" value="${rule.cooldown_minutes || 30}" min="1">
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('notificationRules.channels')}</label>
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input" id="nr-email" ${rule.notify_email !== false ? 'checked' : ''}>
                            <label class="form-check-label" for="nr-email"><i class="fas fa-envelope me-1"></i>Email</label>
                        </div>
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input" id="nr-whatsapp" ${rule.notify_whatsapp ? 'checked' : ''}>
                            <label class="form-check-label" for="nr-whatsapp"><i class="fab fa-whatsapp me-1"></i>WhatsApp</label>
                        </div>
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input" id="nr-webhook" ${rule.notify_webhook ? 'checked' : ''}>
                            <label class="form-check-label" for="nr-webhook"><i class="fas fa-plug me-1"></i>Webhook</label>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">${t('notificationRules.recipients')}</label>
                        <input type="text" class="form-control" id="nr-recipients" value="${escapeHtml(rule.recipients || '')}" placeholder="email1@example.com, email2@example.com">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" data-bs-dismiss="modal">${t('common.cancel')}</button>
                    <button class="btn btn-primary" data-action="kbSaveRule">
                        <i class="fas fa-save me-1"></i>${t('common.save')}
                    </button>
                </div>
            </div>
        </div>
    `;
    new bootstrap.Modal(modal).show();
}

async function kbSaveRule() {
    const id = document.getElementById('nr-rule-id')?.value;
    const data = {
        name: document.getElementById('nr-name')?.value,
        severity: document.getElementById('nr-severity')?.value,
        category: document.getElementById('nr-category')?.value,
        min_occurrences: parseInt(document.getElementById('nr-min-occ')?.value) || 1,
        time_window_minutes: parseInt(document.getElementById('nr-window')?.value) || 5,
        cooldown_minutes: parseInt(document.getElementById('nr-cooldown')?.value) || 30,
        notify_email: document.getElementById('nr-email')?.checked || false,
        notify_whatsapp: document.getElementById('nr-whatsapp')?.checked || false,
        notify_webhook: document.getElementById('nr-webhook')?.checked || false,
        recipients: document.getElementById('nr-recipients')?.value,
        environment_id: sessionStorage.getItem('active_environment_id') || null,
    };

    if (!data.name || !data.severity) {
        showNotification('Nome e severidade sao obrigatorios', 'error');
        return;
    }

    try {
        if (id) {
            await apiRequest(`/notification-rules/${id}`, 'PUT', data);
            showNotification('Regra atualizada', 'success');
        } else {
            await apiRequest('/notification-rules', 'POST', data);
            showNotification('Regra criada com sucesso', 'success');
        }
        bootstrap.Modal.getInstance(document.getElementById('kbRuleModal'))?.hide();
        kbSwitchTab('notifications');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function kbDeleteRule(id) {
    if (!confirm(t('common.confirmDelete'))) return;
    try {
        await apiRequest(`/notification-rules/${id}`, 'DELETE');
        showNotification('Regra removida', 'success');
        kbSwitchTab('notifications');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// UTILITARIOS
// =====================================================================

function renderKbPagination(current, total, actionName) {
    if (total <= 1) return '';
    const start = Math.max(1, current - 2);
    const end = Math.min(total, current + 2);
    let pages = '';

    if (current > 1) {
        pages += `<li class="page-item"><a class="page-link" data-action="${actionName}" data-params='{"page":${current - 1}}'>&laquo;</a></li>`;
    }
    for (let i = start; i <= end; i++) {
        pages += `<li class="page-item ${i === current ? 'active' : ''}">
            <a class="page-link" data-action="${actionName}" data-params='{"page":${i}}'>${i}</a>
        </li>`;
    }
    if (current < total) {
        pages += `<li class="page-item"><a class="page-link" data-action="${actionName}" data-params='{"page":${current + 1}}'>&raquo;</a></li>`;
    }

    return `<nav><ul class="pagination pagination-sm justify-content-center">${pages}</ul></nav>`;
}

function getCategoryBadge(category) {
    const colors = {
        'database': 'primary', 'network': 'info', 'thread_error': 'danger',
        'ads_ctree': 'warning', 'alias_workarea': 'secondary', 'array_error': 'danger',
        'dbf_file': 'dark', 'rpo_repository': 'success', 'type_variable': 'info',
        'memory': 'danger', 'index_key': 'warning', 'lock_semaphore': 'secondary',
        'string_char': 'primary', 'general': 'light', 'performance': 'warning',
    };
    const color = colors[category] || 'secondary';
    return `<span class="badge bg-${color}">${escapeHtml(category || 'N/A')}</span>`;
}

function getSeverityBadge(severity) {
    const colors = { 'critical': 'danger', 'warning': 'warning', 'info': 'info' };
    const color = colors[severity] || 'secondary';
    return `<span class="badge bg-${color}">${escapeHtml(severity || 'N/A')}</span>`;
}

function getTrendIcon(trend) {
    const icons = {
        'increasing': '<span class="text-danger"><i class="fas fa-arrow-up"></i> Aumentando</span>',
        'decreasing': '<span class="text-success"><i class="fas fa-arrow-down"></i> Diminuindo</span>',
        'stable': '<span class="text-muted"><i class="fas fa-minus"></i> Estavel</span>',
        'new': '<span class="text-info"><i class="fas fa-star"></i> Novo</span>',
    };
    return icons[trend] || `<span class="text-muted">${escapeHtml(trend || '-')}</span>`;
}

function truncate(text, maxLen) {
    if (!text) return '';
    return text.length > maxLen ? text.substring(0, maxLen) + '...' : text;
}

function formatDate(isoStr) {
    if (!isoStr) return '-';
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return isoStr;
    }
}
