// =====================================================================
// INTEGRATION-DOCUMENTATION.JS
// Geracao Automatica de Documentacao Tecnica
// =====================================================================

// ===== ESTADO LOCAL DO MODULO =====
let docList = [];
let docTotal = 0;
let docCurrentPage = 1;
let docActiveTab = 'list';
let docPreviewData = null;
let docConnections = [];
let docCategories = [];
let docModules = [];
const DOC_PER_PAGE = 20;

const DOC_TYPE_LABELS = {
    dicionario_dados: 'Dicionario de Dados',
    mapa_processos: 'Mapa de Processos',
    guia_erros: 'Guia de Erros',
    combinado: 'Documentacao Combinada'
};

const DOC_TYPE_ICONS = {
    dicionario_dados: 'fa-database',
    mapa_processos: 'fa-project-diagram',
    guia_erros: 'fa-exclamation-triangle',
    combinado: 'fa-layer-group'
};

// =====================================================================
// CARREGAMENTO DE DADOS
// =====================================================================

async function loadDocList(page) {
    page = page || 1;
    docCurrentPage = page;
    const offset = (page - 1) * DOC_PER_PAGE;
    try {
        const resp = await apiRequest(`/docs?limit=${DOC_PER_PAGE}&offset=${offset}`);
        docList = resp.docs || [];
        docTotal = resp.total || 0;
    } catch (e) {
        docList = [];
        docTotal = 0;
        console.error('Erro ao carregar documentos:', e);
    }
}

async function loadDocConnections() {
    try {
        docConnections = await apiRequest('/docs/connections');
    } catch (e) {
        docConnections = [];
    }
}

async function loadDocCategories() {
    try {
        docCategories = await apiRequest('/docs/categories');
    } catch (e) {
        docCategories = [];
    }
}

async function loadDocModules() {
    try {
        docModules = await apiRequest('/protheus-modules');
    } catch (e) {
        docModules = [];
    }
}

// =====================================================================
// ENTRY POINT
// =====================================================================

async function showDocumentation() {
    try {
        document.getElementById('content-area').innerHTML = `
            <div class="text-center p-5"><div class="spinner-border"></div></div>`;
        await loadDocList(1);
        document.getElementById('content-area').innerHTML = renderDocPage();
        docSwitchTab('list');
    } catch (error) {
        console.error('Erro ao renderizar documentacao:', error);
        document.getElementById('content-area').innerHTML =
            `<div class="alert alert-danger m-4">Erro ao carregar modulo: ${error.message}</div>`;
    }
}

// =====================================================================
// RENDERIZACAO PRINCIPAL
// =====================================================================

function renderDocPage() {
    return `
        <div class="content-header d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2><i class="fas fa-file-alt me-2"></i>Documentacao</h2>
                <p class="text-muted mb-0">Geracao automatica de documentacao tecnica</p>
            </div>
            <button class="btn btn-outline-secondary btn-sm" data-action="docRefresh">
                <i class="fas fa-sync-alt me-1"></i>Atualizar
            </button>
        </div>

        <ul class="nav nav-tabs mb-3" id="doc-tabs">
            <li class="nav-item">
                <button class="nav-link active" id="doc-tab-list"
                    data-action="docSwitchTab" data-params='{"tab":"list"}'>
                    <i class="fas fa-list me-1"></i>Documentos Gerados
                    <span class="badge bg-secondary ms-1">${docTotal}</span>
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link" id="doc-tab-generate"
                    data-action="docSwitchTab" data-params='{"tab":"generate"}'>
                    <i class="fas fa-magic me-1"></i>Gerar Nova
                </button>
            </li>
            <li class="nav-item" id="doc-tab-preview-li" style="display:none">
                <button class="nav-link" id="doc-tab-preview"
                    data-action="docSwitchTab" data-params='{"tab":"preview"}'>
                    <i class="fas fa-eye me-1"></i>Visualizar
                </button>
            </li>
        </ul>

        <div id="doc-tab-content"></div>
    `;
}

// =====================================================================
// ABAS
// =====================================================================

function docSwitchTab(params) {
    const tab = typeof params === 'string' ? params : (params && params.tab) || 'list';
    docActiveTab = tab;

    document.querySelectorAll('#doc-tabs .nav-link').forEach(el => el.classList.remove('active'));
    const activeBtn = document.getElementById(`doc-tab-${tab}`);
    if (activeBtn) activeBtn.classList.add('active');

    const container = document.getElementById('doc-tab-content');
    if (!container) return;

    if (tab === 'list') {
        container.innerHTML = renderDocList();
    } else if (tab === 'generate') {
        docLoadGenerateForm();
    } else if (tab === 'preview') {
        container.innerHTML = renderDocPreview();
    }
}

// =====================================================================
// ABA 1: LISTA DE DOCUMENTOS
// =====================================================================

function renderDocList() {
    if (!docList.length) {
        return `
            <div class="text-center text-muted p-5">
                <i class="fas fa-file-alt fa-3x mb-3 opacity-50"></i>
                <p>Nenhum documento gerado ainda.</p>
                <button class="btn btn-primary" data-action="docSwitchTab" data-params='{"tab":"generate"}'>
                    <i class="fas fa-magic me-1"></i>Gerar Primeiro Documento
                </button>
            </div>
        `;
    }

    const rows = docList.map(doc => {
        const icon = DOC_TYPE_ICONS[doc.doc_type] || 'fa-file';
        const label = DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type;
        const date = doc.generated_at ? new Date(doc.generated_at).toLocaleString('pt-BR') : '-';
        const size = doc.file_size ? _docFormatSize(doc.file_size) : '-';
        const admin = typeof isAdmin === 'function' ? isAdmin() : false;

        return `
            <tr>
                <td>
                    <i class="fas ${icon} me-2 text-primary"></i>
                    <strong>${_docEscape(doc.title)}</strong>
                </td>
                <td><span class="badge bg-info">${label}</span></td>
                <td class="text-center">v${doc.version}</td>
                <td>${_docEscape(doc.generated_by_name || '-')}</td>
                <td>${date}</td>
                <td>${size}</td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-primary me-1"
                        data-action="docPreview" data-params='{"id":${doc.id}}' title="Visualizar">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-success me-1"
                        data-action="docDownload" data-params='{"id":${doc.id}}' title="Download .md">
                        <i class="fas fa-download"></i>
                    </button>
                    ${admin ? `
                    <button class="btn btn-sm btn-outline-danger"
                        data-action="docDelete" data-params='{"id":${doc.id}}' title="Excluir">
                        <i class="fas fa-trash"></i>
                    </button>` : ''}
                </td>
            </tr>
        `;
    }).join('');

    const totalPages = Math.ceil(docTotal / DOC_PER_PAGE);
    const pagination = totalPages > 1 ? _docRenderPagination(docCurrentPage, totalPages) : '';

    return `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Titulo</th>
                        <th>Tipo</th>
                        <th class="text-center">Versao</th>
                        <th>Gerado por</th>
                        <th>Data</th>
                        <th>Tamanho</th>
                        <th class="text-end">Acoes</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        ${pagination}
    `;
}

function _docRenderPagination(current, totalPages) {
    let pages = '';
    for (let i = 1; i <= totalPages; i++) {
        const active = i === current ? 'active' : '';
        pages += `
            <li class="page-item ${active}">
                <button class="page-link" data-action="docGoPage" data-params='{"page":${i}}'>${i}</button>
            </li>`;
    }
    return `<nav><ul class="pagination justify-content-center">${pages}</ul></nav>`;
}

async function docGoPage(params) {
    const page = params && params.page ? params.page : 1;
    await loadDocList(page);
    const container = document.getElementById('doc-tab-content');
    if (container) container.innerHTML = renderDocList();
}

// =====================================================================
// ABA 2: GERAR NOVA DOCUMENTACAO
// =====================================================================

async function docLoadGenerateForm() {
    const container = document.getElementById('doc-tab-content');
    if (!container) return;
    container.innerHTML = `<div class="text-center p-4"><div class="spinner-border"></div></div>`;
    await Promise.all([loadDocConnections(), loadDocCategories(), loadDocModules()]);
    container.innerHTML = renderGenerateForm();
}

function renderGenerateForm() {
    const connOptions = docConnections.map(c =>
        `<option value="${c.id}">${_docEscape(c.name)} (${c.driver} - ${c.host}/${c.database_name})</option>`
    ).join('');

    const catOptions = docCategories.map(c =>
        `<option value="${_docEscape(c.category)}">${_docEscape(c.category)} (${c.count})</option>`
    ).join('');

    const modOptions = docModules.map(m =>
        `<option value="${_docEscape(m.code)}">${_docEscape(m.label)} (${m.code})</option>`
    ).join('');

    return `
        <div class="card">
            <div class="card-body">
                <h5 class="card-title mb-4"><i class="fas fa-magic me-2"></i>Gerar Nova Documentacao</h5>

                <div class="row g-3">
                    <div class="col-md-6">
                        <label class="form-label fw-bold">Tipo de Documento *</label>
                        <select class="form-select" id="doc-gen-type" onchange="docTypeChanged()">
                            <option value="">Selecione...</option>
                            <option value="dicionario_dados">Dicionario de Dados</option>
                            <option value="mapa_processos">Mapa de Processos</option>
                            <option value="guia_erros">Guia de Erros</option>
                            <option value="combinado">Documentacao Combinada</option>
                        </select>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-bold">Titulo</label>
                        <input type="text" class="form-control" id="doc-gen-title"
                            placeholder="Opcional - sera gerado automaticamente">
                    </div>

                    <!-- Filtro: Conexao BD (dicionario_dados e combinado) -->
                    <div class="col-md-4 doc-filter-connection" style="display:none">
                        <label class="form-label">Conexao de Banco</label>
                        <select class="form-select" id="doc-gen-connection">
                            <option value="">Todas as conexoes</option>
                            ${connOptions}
                        </select>
                        ${!connOptions ? '<small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>Nenhuma conexao cadastrada</small>' : ''}
                    </div>

                    <!-- Filtro: Modulo (mapa_processos e combinado) -->
                    <div class="col-md-4 doc-filter-module" style="display:none">
                        <label class="form-label">Modulo Protheus</label>
                        <select class="form-select" id="doc-gen-module">
                            <option value="">Todos os modulos</option>
                            ${modOptions}
                        </select>
                    </div>

                    <!-- Filtro: Categoria (guia_erros e combinado) -->
                    <div class="col-md-4 doc-filter-category" style="display:none">
                        <label class="form-label">Categoria de Erro</label>
                        <select class="form-select" id="doc-gen-category">
                            <option value="">Todas as categorias</option>
                            ${catOptions}
                        </select>
                    </div>
                </div>

                <div class="mt-4">
                    <button class="btn btn-primary" data-action="docGenerate" id="doc-gen-btn">
                        <i class="fas fa-cogs me-1"></i>Gerar Documentacao
                    </button>
                </div>

                <div id="doc-gen-status" class="mt-3"></div>
            </div>
        </div>
    `;
}

function docTypeChanged() {
    const type = document.getElementById('doc-gen-type').value;

    document.querySelectorAll('.doc-filter-connection').forEach(el => {
        el.style.display = (type === 'dicionario_dados' || type === 'combinado') ? '' : 'none';
    });
    document.querySelectorAll('.doc-filter-module').forEach(el => {
        el.style.display = (type === 'mapa_processos' || type === 'combinado') ? '' : 'none';
    });
    document.querySelectorAll('.doc-filter-category').forEach(el => {
        el.style.display = (type === 'guia_erros' || type === 'combinado') ? '' : 'none';
    });
}

async function docGenerate() {
    const type = document.getElementById('doc-gen-type').value;
    if (!type) {
        _docShowStatus('Selecione o tipo de documento.', 'warning');
        return;
    }

    const title = document.getElementById('doc-gen-title').value.trim();
    const payload = { doc_type: type };
    if (title) payload.title = title;

    const connEl = document.getElementById('doc-gen-connection');
    if (connEl && connEl.value) payload.connection_id = parseInt(connEl.value);

    const modEl = document.getElementById('doc-gen-module');
    if (modEl && modEl.value) payload.module = modEl.value;

    const catEl = document.getElementById('doc-gen-category');
    if (catEl && catEl.value) payload.category = catEl.value;

    const btn = document.getElementById('doc-gen-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Gerando...';
    }
    _docShowStatus('Gerando documentacao, aguarde...', 'info');

    try {
        const resp = await apiRequest('/docs/generate', 'POST', payload);

        if (resp.success) {
            _docShowStatus(
                `<i class="fas fa-check-circle me-1"></i>${resp.message} — ` +
                `<a href="#" data-action="docPreview" data-params='{"id":${resp.id}}'>Visualizar</a>`,
                'success'
            );
            await loadDocList(1);
            // Atualizar badge
            const badge = document.querySelector('#doc-tab-list .badge');
            if (badge) badge.textContent = docTotal;
        } else {
            _docShowStatus(resp.error || 'Erro desconhecido', 'danger');
        }
    } catch (e) {
        _docShowStatus(`Erro: ${e.message || e}`, 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-cogs me-1"></i>Gerar Documentacao';
        }
    }
}

function _docShowStatus(msg, type) {
    const el = document.getElementById('doc-gen-status');
    if (el) el.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
}

// =====================================================================
// ABA 3: PREVIEW
// =====================================================================

async function docPreview(params) {
    const docId = params && params.id;
    if (!docId) return;

    // Mostrar aba de preview
    const previewLi = document.getElementById('doc-tab-preview-li');
    if (previewLi) previewLi.style.display = '';

    docSwitchTab('preview');

    const container = document.getElementById('doc-tab-content');
    if (!container) return;
    container.innerHTML = `<div class="text-center p-5"><div class="spinner-border"></div></div>`;

    try {
        const doc = await apiRequest(`/docs/${docId}`);
        docPreviewData = doc;
        container.innerHTML = renderDocPreview();
        // Interceptar links de ancora interna para scroll dentro do card
        const previewBody = container.querySelector('.doc-preview-content');
        if (previewBody) {
            previewBody.addEventListener('click', function(e) {
                const link = e.target.closest('a[href^="#"]');
                if (!link) return;
                e.preventDefault();
                const targetId = link.getAttribute('href').substring(1);
                const target = previewBody.querySelector('#' + CSS.escape(targetId));
                if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        }
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Erro ao carregar documento: ${e.message}</div>`;
    }
}

function renderDocPreview() {
    if (!docPreviewData) {
        return `<div class="text-center text-muted p-5">Nenhum documento selecionado.</div>`;
    }

    const doc = docPreviewData;
    const label = DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type;
    const date = doc.generated_at ? new Date(doc.generated_at).toLocaleString('pt-BR') : '-';
    const size = doc.file_size ? _docFormatSize(doc.file_size) : '-';

    // Renderizar Markdown -> HTML via marked.js
    let htmlContent = '';
    if (typeof marked !== 'undefined' && marked.parse) {
        htmlContent = marked.parse(doc.content_md || '');
        // marked v15 nao gera IDs nos headings — adicionar via pos-processamento
        htmlContent = htmlContent.replace(/<h([1-6])>(.*?)<\/h\1>/g, function(match, level, text) {
            const slug = text.replace(/<[^>]+>/g, '').trim().toLowerCase()
                .replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
            return '<h' + level + ' id="' + slug + '">' + text + '</h' + level + '>';
        });
    } else {
        htmlContent = `<pre class="code-viewer code-wrap">${_docEscape(doc.content_md || '')}</pre>`;
    }

    return `
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="mb-1">${_docEscape(doc.title)}</h5>
                    <small class="text-muted">
                        <span class="badge bg-info me-2">${label}</span>
                        v${doc.version} | ${_docEscape(doc.generated_by_name || '-')} | ${date} | ${size}
                    </small>
                </div>
                <div>
                    <button class="btn btn-sm btn-outline-success me-1"
                        data-action="docDownload" data-params='{"id":${doc.id}}'>
                        <i class="fas fa-download me-1"></i>Download .md
                    </button>
                    <button class="btn btn-sm btn-outline-secondary"
                        data-action="docShowVersions" data-params='{"id":${doc.id}}'>
                        <i class="fas fa-history me-1"></i>Versoes
                    </button>
                </div>
            </div>
            <div class="card-body doc-preview-content" style="max-height:70vh;overflow-y:auto">
                ${htmlContent}
            </div>
        </div>
    `;
}

// =====================================================================
// ACOES
// =====================================================================

function docDownload(params) {
    const docId = params && params.id;
    if (!docId) return;
    const token = sessionStorage.getItem('auth_token');
    const url = `/api/docs/${docId}/download`;
    // Abrir em nova aba com auth
    fetch(url, { headers: { 'Authorization': token } })
        .then(resp => {
            if (!resp.ok) throw new Error('Erro no download');
            const disp = resp.headers.get('Content-Disposition') || '';
            const match = disp.match(/filename=(.+)/);
            const filename = match ? match[1] : `documento_${docId}.md`;
            return resp.blob().then(blob => ({ blob, filename }));
        })
        .then(({ blob, filename }) => {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = filename;
            a.click();
            URL.revokeObjectURL(a.href);
        })
        .catch(e => alert('Erro ao baixar: ' + e.message));
}

async function docDelete(params) {
    const docId = params && params.id;
    if (!docId) return;
    if (!confirm('Tem certeza que deseja excluir este documento?')) return;

    try {
        await apiRequest(`/docs/${docId}`, 'DELETE');
        await loadDocList(docCurrentPage);
        const container = document.getElementById('doc-tab-content');
        if (container && docActiveTab === 'list') container.innerHTML = renderDocList();
        // Atualizar badge
        const badge = document.querySelector('#doc-tab-list .badge');
        if (badge) badge.textContent = docTotal;
    } catch (e) {
        alert('Erro ao excluir: ' + (e.message || e));
    }
}

async function docShowVersions(params) {
    const docId = params && params.id;
    if (!docId) return;

    try {
        const resp = await apiRequest(`/docs/${docId}/versions`);
        const versions = resp.versions || [];

        if (!versions.length) {
            alert('Nenhuma versao anterior encontrada.');
            return;
        }

        const rows = versions.map(v => {
            const date = v.generated_at ? new Date(v.generated_at).toLocaleString('pt-BR') : '-';
            const size = v.file_size ? _docFormatSize(v.file_size) : '-';
            const isCurrent = v.id === docId ? '<span class="badge bg-success ms-1">atual</span>' : '';
            return `
                <tr>
                    <td>v${v.version} ${isCurrent}</td>
                    <td>${_docEscape(v.generated_by_name || '-')}</td>
                    <td>${date}</td>
                    <td>${size}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary"
                            data-action="docPreview" data-params='{"id":${v.id}}'>
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        // Mostrar modal de versoes
        const modalHtml = `
            <div class="modal fade show" style="display:block;background:rgba(0,0,0,0.5)" id="doc-versions-modal">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title"><i class="fas fa-history me-2"></i>Historico de Versoes</h5>
                            <button type="button" class="btn-close" data-action="docCloseModal"></button>
                        </div>
                        <div class="modal-body">
                            <table class="table table-sm">
                                <thead>
                                    <tr><th>Versao</th><th>Autor</th><th>Data</th><th>Tamanho</th><th></th></tr>
                                </thead>
                                <tbody>${rows}</tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        `;
        const div = document.createElement('div');
        div.id = 'doc-modal-wrapper';
        div.innerHTML = modalHtml;
        document.body.appendChild(div);
    } catch (e) {
        alert('Erro ao carregar versoes: ' + (e.message || e));
    }
}

function docCloseModal() {
    const wrapper = document.getElementById('doc-modal-wrapper');
    if (wrapper) wrapper.remove();
}

async function docRefresh() {
    await loadDocList(1);
    document.getElementById('content-area').innerHTML = renderDocPage();
    docSwitchTab(docActiveTab);
}

// =====================================================================
// HELPERS
// =====================================================================

function _docEscape(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function _docFormatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}
