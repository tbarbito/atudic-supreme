// =====================================================================
// INTEGRATION-DATABASE.JS
// Browser/explorador de banco de dados: conexões, schema, consultas SQL
// =====================================================================

// =====================================================================
// ESTADO LOCAL DO MÓDULO
// =====================================================================
let dbConnections = [];
let dbDrivers = [];
let dbSelectedConnId = null;
let dbTables = [];
let dbSelectedTable = null;
let dbColumns = [];
let dbQueryResult = null;
let dbTableDetails = null;  // indexes, triggers, constraints da tabela selecionada
let dbActiveTab = 'connections';

// Cache de histórico de consultas
let dbQueryHistory = [];

// Estado do módulo Dicionário (Compare + Integridade)
let dictCompareResult = _dictRestoreState('dictCompareResult');
let dictIntegrityResult = _dictRestoreState('dictIntegrityResult');
let dictCompaniesCache = {}; // {connId: [{code, name}]}

function _dictSaveState(key, value) {
    try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
}
function _dictRestoreState(key) {
    try {
        const raw = sessionStorage.getItem(key);
        return raw ? JSON.parse(raw) : null;
    } catch (_) { return null; }
}

// Mapa de drivers com ícones e portas padrão
const DB_DRIVER_META = {
    'mssql':      { label: 'SQL Server',  icon: 'fa-server',        port: 1433, color: 'text-warning' },
    'postgresql': { label: 'PostgreSQL',  icon: 'fa-database',      port: 5432, color: 'text-info'    },
    'mysql':      { label: 'MySQL',       icon: 'fa-leaf',          port: 3306, color: 'text-success'  },
    'oracle':     { label: 'Oracle',      icon: 'fa-circle-dot',    port: 1521, color: 'text-danger'   },
};

// =====================================================================
// PONTO DE ENTRADA PRINCIPAL
// =====================================================================

/**
 * Carrega dados iniciais e renderiza a página de banco de dados.
 * Chamada pelo router ao navegar para o hash #database.
 */
async function showDatabase() {
    const contentArea = document.getElementById('content-area');
    if (!contentArea) return;

    // Spinner enquanto carrega
    contentArea.innerHTML = `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Carregando...</span>
            </div>
            <span class="ms-3 text-muted">Carregando módulo de banco de dados...</span>
        </div>`;

    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const [driversRes, connsRes] = await Promise.allSettled([
            apiRequest('/db-drivers'),
            apiRequest(`/db-connections${envId ? '?environment_id=' + envId : ''}`)
        ]);

        dbDrivers = driversRes.status === 'fulfilled' ? (driversRes.value.drivers || driversRes.value || []) : [];
        dbConnections = connsRes.status === 'fulfilled' ? (connsRes.value.connections || connsRes.value || []) : [];

        contentArea.innerHTML = _renderDatabasePage();
        // Renderiza a aba ativa (pode ser qualquer uma, não apenas connections)
        dbSwitchTab(dbActiveTab);

        // Seleciona automaticamente a primeira conexão disponível para o explorador
        if (dbConnections.length > 0 && !dbSelectedConnId) {
            // Não auto-seleciona: usuário escolhe explicitamente
        }
    } catch (error) {
        contentArea.innerHTML = `
            <div class="alert alert-danger m-4">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Erro ao carregar o módulo de banco de dados: ${escapeHtml(error.message)}
            </div>`;
    }
}

// =====================================================================
// RENDERIZAÇÃO DA ESTRUTURA DA PÁGINA
// =====================================================================

function _renderDatabasePage() {
    return `
        <div class="content-header d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2><i class="fas fa-database me-2"></i>Banco de Dados</h2>
                <p class="text-muted mb-0">Gerencie conexões, explore o schema e execute consultas SQL.</p>
            </div>
            <div>
                <button class="btn btn-outline-primary btn-sm me-2" data-action="dbRefresh">
                    <i class="fas fa-sync-alt me-1"></i>Atualizar
                </button>
                ${isAdmin() ? `
                <button class="btn btn-primary btn-sm" data-action="dbShowCreateConn">
                    <i class="fas fa-plus me-1"></i>Nova Conexão
                </button>` : ''}
            </div>
        </div>

        <!-- Tabs de navegação -->
        <ul class="nav nav-tabs mb-3" role="tablist" id="db-tabs">
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'connections' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"connections"}'>
                    <i class="fas fa-plug me-2"></i>Conexões
                    <span class="badge bg-secondary ms-1">${dbConnections.length}</span>
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'explorer' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"explorer"}'>
                    <i class="fas fa-sitemap me-2"></i>Explorador
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'queries' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"queries"}'>
                    <i class="fas fa-terminal me-2"></i>Consultas
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'compare' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"compare"}'>
                    <i class="fas fa-columns me-2"></i>Comparar Dicionário
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'equalize' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"equalize"}'>
                    <i class="fas fa-sync me-2"></i>Equalização
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'integrity' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"integrity"}'>
                    <i class="fas fa-shield-alt me-2"></i>Integridade
                </button>
            </li>
            <li class="nav-item">
                <button class="nav-link ${dbActiveTab === 'ingestor' ? 'active' : ''}"
                    data-action="dbSwitchTab" data-params='{"tab":"ingestor"}'>
                    <i class="fas fa-file-import me-2"></i>Ingestor
                </button>
            </li>
        </ul>

        <!-- Painéis das tabs -->
        <div id="db-tab-connections" class="db-tab-panel ${dbActiveTab === 'connections' ? '' : 'd-none'}">
            <div id="db-connections-content">
                <!-- Preenchido por _renderConnectionsTab() -->
            </div>
        </div>

        <div id="db-tab-explorer" class="db-tab-panel ${dbActiveTab === 'explorer' ? '' : 'd-none'}">
            <div id="db-explorer-content">
                <!-- Preenchido por _renderExplorerTab() -->
            </div>
        </div>

        <div id="db-tab-queries" class="db-tab-panel ${dbActiveTab === 'queries' ? '' : 'd-none'}">
            <div id="db-queries-content">
                <!-- Preenchido por _renderQueriesTab() -->
            </div>
        </div>

        <div id="db-tab-compare" class="db-tab-panel ${dbActiveTab === 'compare' ? '' : 'd-none'}">
            <div id="db-compare-content">
                <!-- Preenchido por _renderCompareTab() -->
            </div>
        </div>

        <div id="db-tab-integrity" class="db-tab-panel ${dbActiveTab === 'integrity' ? '' : 'd-none'}">
            <div id="db-integrity-content">
                <!-- Preenchido por _renderIntegrityTab() -->
            </div>
        </div>

        <div id="db-tab-equalize" class="db-tab-panel ${dbActiveTab === 'equalize' ? '' : 'd-none'}">
            <div id="db-equalize-content">
                <!-- Preenchido por _renderEqualizeTab() -->
            </div>
        </div>

        <div id="db-tab-ingestor" class="db-tab-panel ${dbActiveTab === 'ingestor' ? '' : 'd-none'}">
            <div id="db-ingestor-content">
                <!-- Preenchido por _renderIngestorTab() -->
            </div>
        </div>

        <!-- Modal de criar/editar conexão -->
        ${_renderConnModal()}
    `;
}

// =====================================================================
// ABA: CONEXÕES
// =====================================================================

function _renderConnectionsTab() {
    const container = document.getElementById('db-connections-content');
    if (!container) return;

    if (dbConnections.length === 0) {
        container.innerHTML = `
            <div class="card text-center p-5">
                <i class="fas fa-database fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">Nenhuma conexão cadastrada</h5>
                <p class="text-muted small">Configure uma conexão de banco de dados para começar a explorar schemas e executar consultas.</p>
                ${isAdmin() ? `
                <button class="btn btn-primary mt-2" data-action="dbShowCreateConn">
                    <i class="fas fa-plus me-2"></i>Criar Primeira Conexão
                </button>` : ''}
            </div>`;
        return;
    }

    const cards = dbConnections.map(conn => _renderConnCard(conn)).join('');
    container.innerHTML = `<div class="row">${cards}</div>`;
}

function _renderConnCard(conn) {
    const meta = DB_DRIVER_META[conn.driver] || { label: conn.driver, icon: 'fa-database', port: '', color: 'text-secondary' };

    // Status visual
    let statusBadge = '';
    let statusDot = '';
    if (conn.last_error) {
        statusBadge = `<span class="badge bg-danger"><i class="fas fa-times me-1"></i>Erro</span>`;
        statusDot = 'bg-danger';
    } else if (conn.last_connected_at) {
        statusBadge = `<span class="badge bg-success"><i class="fas fa-check me-1"></i>Conectado</span>`;
        statusDot = 'bg-success';
    } else {
        statusBadge = `<span class="badge bg-secondary"><i class="fas fa-minus me-1"></i>Nunca conectado</span>`;
        statusDot = 'bg-secondary';
    }

    const lastConn = conn.last_connected_at
        ? `<small class="text-muted">Últ. conexão: ${_formatDateTime(conn.last_connected_at)}</small>`
        : `<small class="text-muted fst-italic">Nunca conectado</small>`;

    const envBadge = conn.environment_name
        ? `<span class="badge bg-secondary text-white ms-1">${escapeHtml(conn.environment_name)}</span>`
        : '';

    return `
    <div class="col-md-6 col-lg-4 mb-4">
        <div class="card h-100 ${dbSelectedConnId === conn.id ? 'border-primary' : ''}">
            <div class="card-header d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2">
                    <span class="badge rounded-pill ${statusDot}" style="width:10px;height:10px;padding:0;">&nbsp;</span>
                    <i class="fas ${meta.icon} ${meta.color}"></i>
                    <strong class="text-truncate" style="max-width:140px;" title="${escapeHtml(conn.name)}">${escapeHtml(conn.name)}</strong>
                </div>
                <div class="dropdown">
                    <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown">
                        <i class="fas fa-ellipsis-v"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end">
                        <li>
                            <a class="dropdown-item" href="#"
                               data-action="dbSelectConn" data-params='{"id":${conn.id}}'>
                                <i class="fas fa-check-circle me-2 text-primary"></i>Selecionar
                            </a>
                        </li>
                        <li>
                            <a class="dropdown-item" href="#"
                               data-action="dbTestConn" data-params='{"id":${conn.id}}'>
                                <i class="fas fa-plug me-2 text-success"></i>Testar Conexão
                            </a>
                        </li>
                        ${isOperator() || isAdmin() ? `
                        <li>
                            <a class="dropdown-item" href="#"
                               data-action="dbDiscover" data-params='{"id":${conn.id}}'>
                                <i class="fas fa-search me-2 text-info"></i>Descobrir Schema
                            </a>
                        </li>` : ''}
                        ${isAdmin() ? `
                        <li><hr class="dropdown-divider"></li>
                        <li>
                            <a class="dropdown-item" href="#"
                               data-action="dbEditConn" data-params='{"id":${conn.id}}'>
                                <i class="fas fa-edit me-2"></i>Editar
                            </a>
                        </li>
                        <li>
                            <a class="dropdown-item text-danger" href="#"
                               data-action="dbDeleteConn" data-params='{"id":${conn.id}}'>
                                <i class="fas fa-trash me-2"></i>Excluir
                            </a>
                        </li>` : ''}
                    </ul>
                </div>
            </div>
            <div class="card-body">
                <div class="mb-2">
                    <span class="badge bg-secondary me-1">${escapeHtml(meta.label)}</span>
                    ${envBadge}
                    ${conn.ref_environment_name && conn.ref_environment_name !== conn.environment_name
                        ? `<span class="badge bg-info text-dark ms-1" title="Ambiente de referência"><i class="fas fa-link me-1"></i>${escapeHtml(conn.ref_environment_name)}</span>`
                        : ''}
                    ${conn.connection_role
                        ? `<span class="badge bg-light text-dark border ms-1">${escapeHtml(conn.connection_role)}</span>`
                        : ''}
                    ${conn.rest_url
                        ? `<span class="badge bg-info text-white ms-1" title="REST: ${escapeHtml(conn.rest_url)}"><i class="fas fa-plug me-1"></i>REST</span>`
                        : ''}
                </div>
                <p class="small text-muted mb-1">
                    <i class="fas fa-server me-1"></i>
                    ${escapeHtml(conn.host || '')}${conn.port ? ':' + conn.port : ''}
                </p>
                <p class="small text-muted mb-2">
                    <i class="fas fa-folder me-1"></i>
                    ${escapeHtml(conn.database_name || conn.database || '')}
                </p>
                ${conn.last_error ? `
                <div class="alert alert-danger py-1 px-2 small mb-2">
                    <i class="fas fa-exclamation-circle me-1"></i>
                    ${escapeHtml(truncate(conn.last_error, 80))}
                </div>` : ''}
                ${lastConn}
            </div>
            <div class="card-footer d-flex justify-content-between align-items-center">
                ${statusBadge}
                <button class="btn btn-sm btn-outline-primary"
                    data-action="dbSelectConn" data-params='{"id":${conn.id}}'>
                    <i class="fas fa-compass me-1"></i>Explorar
                </button>
            </div>
        </div>
    </div>`;
}

// =====================================================================
// ABA: EXPLORADOR DE SCHEMA
// =====================================================================

function _renderExplorerTab() {
    const container = document.getElementById('db-explorer-content');
    if (!container) return;

    if (!dbSelectedConnId) {
        if (dbConnections.length > 0) {
            container.innerHTML = `
                <div class="card text-center p-5">
                    <i class="fas fa-sitemap fa-3x text-muted mb-3"></i>
                    <h5 class="text-muted">Selecione uma conexão</h5>
                    <p class="text-muted small mb-3">Escolha uma conexão para explorar o schema.</p>
                    ${_renderConnSelector('dbExplorerConnSelect')}
                </div>`;
        } else {
            container.innerHTML = `
                <div class="card text-center p-5">
                    <i class="fas fa-sitemap fa-3x text-muted mb-3"></i>
                    <h5 class="text-muted">Nenhuma conexão cadastrada</h5>
                    <p class="text-muted small">Cadastre uma conexão na aba <strong>Conexões</strong> para começar.</p>
                </div>`;
        }
        return;
    }

    const conn = dbConnections.find(c => c.id === dbSelectedConnId);
    const connName = conn ? escapeHtml(conn.name) : `Conexão #${dbSelectedConnId}`;
    const meta = conn ? (DB_DRIVER_META[conn.driver] || { label: conn.driver, icon: 'fa-database', color: 'text-secondary' }) : {};

    container.innerHTML = `
        <div class="row g-3">
            <!-- Painel esquerdo: lista de tabelas -->
            <div class="col-md-4 col-lg-3">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center gap-2">
                            <i class="fas ${meta.icon || 'fa-database'} ${meta.color || ''}"></i>
                            ${dbConnections.length > 1
                                ? `<select class="form-select form-select-sm" style="max-width:200px;font-size:.8rem"
                                    onchange="_dbQuickSelectConn(this.value)">
                                    ${dbConnections.map(c => `<option value="${c.id}" ${c.id === dbSelectedConnId ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}
                                  </select>`
                                : `<strong class="small">${connName}</strong>`}
                        </div>
                        <button class="btn btn-sm btn-outline-secondary" title="Descobrir/Atualizar schema"
                            data-action="dbDiscover" data-params='{"id":${dbSelectedConnId}}'>
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                    <div class="card-body p-2">
                        <div class="input-group input-group-sm mb-2">
                            <span class="input-group-text"><i class="fas fa-search"></i></span>
                            <input type="text" class="form-control" id="db-table-search"
                                placeholder="Filtrar tabelas..."
                                oninput="_dbFilterTables(this.value)">
                        </div>
                        <div id="db-table-list" style="max-height:calc(100vh - 380px); overflow-y:auto;">
                            ${_renderTableList()}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Painel direito: detalhes da tabela -->
            <div class="col-md-8 col-lg-9">
                <div id="db-columns-panel" style="max-height:calc(100vh - 300px); overflow-y:auto;">
                    ${_renderColumnsPanel()}
                </div>
            </div>
        </div>`;
}

function _renderTableList() {
    if (dbTables.length === 0) {
        return `
            <div class="text-center py-4">
                <p class="text-muted small">Nenhuma tabela encontrada.</p>
                <button class="btn btn-sm btn-outline-info" data-action="dbDiscover"
                    data-params='{"id":${dbSelectedConnId}}'>
                    <i class="fas fa-search me-1"></i>Descobrir Schema
                </button>
            </div>`;
    }

    return dbTables.map(tbl => {
        const name = typeof tbl === 'string' ? tbl : (tbl.table_name || tbl.name || '');
        const isActive = name === dbSelectedTable;
        return `
        <button type="button"
            class="list-group-item list-group-item-action d-flex align-items-center py-2 px-2 ${isActive ? 'active' : ''}"
            data-action="dbSelectTable" data-params='{"name":"${escapeHtml(name)}"}'>
            <i class="fas fa-table me-2 ${isActive ? '' : 'text-muted'}" style="font-size:.75rem;"></i>
            <span class="small text-truncate">${escapeHtml(name)}</span>
        </button>`;
    }).join('');
}

function _renderColumnsPanel() {
    if (!dbSelectedTable) {
        return `
            <div class="card text-center p-5">
                <i class="fas fa-table fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">Selecione uma tabela</h5>
                <p class="text-muted small">Clique em uma tabela na lista ao lado para ver seus campos e metadados.</p>
            </div>`;
    }

    const indexes = dbTableDetails ? (dbTableDetails.indexes || []) : [];
    const triggers = dbTableDetails ? (dbTableDetails.triggers || []) : [];
    const constraints = dbTableDetails ? (dbTableDetails.constraints || []) : [];

    return `
        <!-- Header da tabela -->
        <div class="card mb-2">
            <div class="card-header d-flex justify-content-between align-items-center py-2">
                <div>
                    <i class="fas fa-table me-2 text-info"></i>
                    <strong>${escapeHtml(dbSelectedTable)}</strong>
                    <span class="badge bg-secondary ms-2">${dbColumns.length} campos</span>
                    ${indexes.length ? `<span class="badge bg-info ms-1">${indexes.length} idx</span>` : ''}
                    ${triggers.length ? `<span class="badge bg-warning text-dark ms-1">${triggers.length} trg</span>` : ''}
                    ${constraints.length ? `<span class="badge bg-primary ms-1">${constraints.length} cst</span>` : ''}
                </div>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary" title="Atualizar"
                        data-action="dbSelectTable" data-params='{"name":"${escapeHtml(dbSelectedTable)}"}'>
                        <i class="fas fa-sync-alt"></i>
                    </button>
                    <button class="btn btn-outline-primary"
                        data-action="dbViewSample" data-params='{"name":"${escapeHtml(dbSelectedTable)}"}'>
                        <i class="fas fa-eye me-1"></i>Amostra
                    </button>
                    <button class="btn btn-outline-success"
                        data-action="dbSwitchTab" data-params='{"tab":"queries","table":"${escapeHtml(dbSelectedTable)}"}'>
                        <i class="fas fa-terminal me-1"></i>SQL
                    </button>
                </div>
            </div>
        </div>

        <!-- Card: Campos (aberto por padrão) -->
        <div class="card mb-2">
            <div class="card-header py-2 d-flex align-items-center" style="cursor:pointer"
                data-action="dbToggleCard" data-params='{"id":"db-card-fields"}'>
                <i class="fas fa-columns me-2 text-primary"></i>
                <strong class="small">Campos</strong>
                <span class="badge bg-secondary ms-2">${dbColumns.length}</span>
                <i class="fas fa-chevron-up ms-auto small" id="db-card-fields-icon"></i>
            </div>
            <div class="card-body p-0" id="db-card-fields">
                ${_renderColumnsTable()}
            </div>
        </div>

        <!-- Card: Indexes -->
        <div class="card mb-2">
            <div class="card-header py-2 d-flex align-items-center" style="cursor:pointer"
                data-action="dbToggleCard" data-params='{"id":"db-card-indexes"}'>
                <i class="fas fa-list-ol me-2 text-info"></i>
                <strong class="small">Indexes</strong>
                <span class="badge ${indexes.length ? 'bg-info' : 'bg-secondary'} ms-2">${indexes.length}</span>
                <i class="fas fa-chevron-down ms-auto small" id="db-card-indexes-icon"></i>
            </div>
            <div class="card-body p-0" id="db-card-indexes" style="display:none">
                ${_renderIndexesTable(indexes)}
            </div>
        </div>

        <!-- Card: Triggers -->
        <div class="card mb-2">
            <div class="card-header py-2 d-flex align-items-center" style="cursor:pointer"
                data-action="dbToggleCard" data-params='{"id":"db-card-triggers"}'>
                <i class="fas fa-bolt me-2 text-warning"></i>
                <strong class="small">Triggers</strong>
                <span class="badge ${triggers.length ? 'bg-warning text-dark' : 'bg-secondary'} ms-2">${triggers.length}</span>
                <i class="fas fa-chevron-down ms-auto small" id="db-card-triggers-icon"></i>
            </div>
            <div class="card-body p-0" id="db-card-triggers" style="display:none">
                ${_renderTriggersTable(triggers)}
            </div>
        </div>

        <!-- Card: Constraints -->
        <div class="card mb-2">
            <div class="card-header py-2 d-flex align-items-center" style="cursor:pointer"
                data-action="dbToggleCard" data-params='{"id":"db-card-constraints"}'>
                <i class="fas fa-lock me-2 text-danger"></i>
                <strong class="small">Constraints</strong>
                <span class="badge ${constraints.length ? 'bg-primary' : 'bg-secondary'} ms-2">${constraints.length}</span>
                <i class="fas fa-chevron-down ms-auto small" id="db-card-constraints-icon"></i>
            </div>
            <div class="card-body p-0" id="db-card-constraints" style="display:none">
                ${_renderConstraintsTable(constraints)}
            </div>
        </div>`;
}

function dbToggleCard(params) {
    const cardId = params.id;
    const body = document.getElementById(cardId);
    const icon = document.getElementById(cardId + '-icon');
    if (!body) return;
    const isHidden = body.style.display === 'none';
    body.style.display = isHidden ? '' : 'none';
    if (icon) {
        icon.className = isHidden ? 'fas fa-chevron-up ms-auto small' : 'fas fa-chevron-down ms-auto small';
    }
}

function _renderColumnsTable() {
    if (dbColumns.length === 0) {
        return `<p class="text-muted text-center py-3 small mb-0">Nenhum campo encontrado.</p>`;
    }

    const rows = dbColumns.map(col => {
        const colName = col.column_name || col.name || '';
        const colType = col.column_type || col.type || '';
        const colSize = col.column_size ? `(${col.column_size}${col.column_decimal ? ',' + col.column_decimal : ''})` : '';
        const isNullable = col.is_nullable !== undefined ? col.is_nullable : (col.nullable !== false);
        const nullable = isNullable
            ? '<span class="badge bg-secondary">NULL</span>'
            : '<span class="badge bg-warning text-dark">NOT NULL</span>';
        const pk = (col.is_key || col.primary_key)
            ? '<i class="fas fa-key text-warning ms-1" title="Chave Primaria"></i>'
            : '';
        const fk = col.foreign_key
            ? '<i class="fas fa-link text-info ms-1" title="Chave Estrangeira"></i>'
            : '';

        return `
        <tr>
            <td class="fw-bold small">${escapeHtml(colName)}${pk}${fk}</td>
            <td><span class="badge bg-dark border border-secondary font-monospace">${escapeHtml(colType)}${colSize}</span></td>
            <td>${nullable}</td>
            <td class="text-muted small">${escapeHtml(col.column_order != null ? String(col.column_order) : '')}</td>
        </tr>`;
    }).join('');

    return `
    <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
            <thead class="table-dark">
                <tr>
                    <th>Campo</th>
                    <th>Tipo</th>
                    <th>Nulavel</th>
                    <th>Ordem</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function _renderIndexesTable(indexes) {
    if (!indexes || indexes.length === 0) {
        return `<p class="text-muted text-center py-3 small mb-0">Nenhum index encontrado.</p>`;
    }

    const rows = indexes.map(idx => {
        const pkBadge = idx.primary_key ? '<span class="badge bg-warning text-dark me-1">PK</span>' : '';
        const uqBadge = idx.unique && !idx.primary_key ? '<span class="badge bg-info me-1">UNIQUE</span>' : '';
        return `
        <tr>
            <td class="fw-bold small">${pkBadge}${uqBadge}${escapeHtml(idx.name || '')}</td>
            <td><span class="badge bg-dark border border-secondary font-monospace">${escapeHtml(idx.type || '')}</span></td>
            <td class="small">${escapeHtml(idx.columns || '')}</td>
        </tr>`;
    }).join('');

    return `
    <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
            <thead class="table-dark">
                <tr>
                    <th>Nome</th>
                    <th>Tipo</th>
                    <th>Colunas</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function _renderTriggersTable(triggers) {
    if (!triggers || triggers.length === 0) {
        return `<p class="text-muted text-center py-3 small mb-0">Nenhuma trigger encontrada.</p>`;
    }

    const rows = triggers.map(trg => {
        const statusBadge = trg.enabled !== false
            ? '<span class="badge bg-success me-1">ON</span>'
            : '<span class="badge bg-danger me-1">OFF</span>';
        return `
        <tr>
            <td class="fw-bold small">${statusBadge}${escapeHtml(trg.name || '')}</td>
            <td><span class="badge bg-dark border border-secondary font-monospace">${escapeHtml(trg.timing || '')}</span></td>
            <td class="small">${escapeHtml(trg.event || '')}</td>
            <td class="text-muted small text-truncate" style="max-width:200px" title="${escapeHtml(trg.action || '')}">${escapeHtml(trg.action || '')}</td>
        </tr>`;
    }).join('');

    return `
    <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
            <thead class="table-dark">
                <tr>
                    <th>Nome</th>
                    <th>Timing</th>
                    <th>Evento</th>
                    <th>Acao</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function _renderConstraintsTable(constraints) {
    if (!constraints || constraints.length === 0) {
        return `<p class="text-muted text-center py-3 small mb-0">Nenhuma constraint encontrada.</p>`;
    }

    const typeColors = {
        'PRIMARY KEY': 'bg-warning text-dark',
        'FOREIGN KEY': 'bg-info',
        'UNIQUE': 'bg-primary',
        'CHECK': 'bg-secondary',
    };

    const rows = constraints.map(cst => {
        const typeBadge = `<span class="badge ${typeColors[cst.type] || 'bg-secondary'} me-1">${escapeHtml(cst.type || '')}</span>`;
        let extra = '';
        if (cst.ref_table) extra = `<i class="fas fa-arrow-right text-muted mx-1"></i><span class="small text-info">${escapeHtml(cst.ref_table)}</span>`;
        if (cst.definition) extra = `<span class="text-muted small font-monospace ms-1">${escapeHtml(cst.definition.substring(0, 100))}</span>`;
        return `
        <tr>
            <td class="fw-bold small">${typeBadge}${escapeHtml(cst.name || '')}</td>
            <td class="small">${escapeHtml(cst.columns || '')}</td>
            <td class="small">${extra}</td>
        </tr>`;
    }).join('');

    return `
    <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
            <thead class="table-dark">
                <tr>
                    <th>Nome</th>
                    <th>Colunas</th>
                    <th>Detalhes</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

// Filtro em tempo real da lista de tabelas
function _dbFilterTables(term) {
    const list = document.getElementById('db-table-list');
    if (!list) return;

    const lower = term.toLowerCase().trim();
    const filtered = lower
        ? dbTables.filter(t => (typeof t === 'string' ? t : (t.table_name || t.name || '')).toLowerCase().includes(lower))
        : dbTables;

    // Re-renderiza apenas os botões da lista
    list.innerHTML = filtered.length > 0
        ? filtered.map(tbl => {
            const name = typeof tbl === 'string' ? tbl : (tbl.table_name || tbl.name || '');
            const isActive = name === dbSelectedTable;
            return `
            <button type="button"
                class="list-group-item list-group-item-action d-flex align-items-center py-2 px-2 ${isActive ? 'active' : ''}"
                data-action="dbSelectTable" data-params='{"name":"${escapeHtml(name)}"}'>
                <i class="fas fa-table me-2 ${isActive ? '' : 'text-muted'}" style="font-size:.75rem;"></i>
                <span class="small text-truncate">${escapeHtml(name)}</span>
            </button>`;
        }).join('')
        : `<p class="text-muted text-center small py-3">Nenhuma tabela encontrada para "<em>${escapeHtml(term)}</em>".</p>`;
}

// =====================================================================
// ABA: CONSULTAS SQL
// =====================================================================

function _renderQueriesTab(preloadTable = null) {
    const container = document.getElementById('db-queries-content');
    if (!container) return;

    if (!dbSelectedConnId) {
        if (dbConnections.length > 0) {
            container.innerHTML = `
                <div class="card text-center p-5">
                    <i class="fas fa-terminal fa-3x text-muted mb-3"></i>
                    <h5 class="text-muted">Selecione uma conexão</h5>
                    <p class="text-muted small mb-3">Escolha uma conexão para executar consultas SQL.</p>
                    ${_renderConnSelector('dbQueriesConnSelect')}
                </div>`;
        } else {
            container.innerHTML = `
                <div class="card text-center p-5">
                    <i class="fas fa-terminal fa-3x text-muted mb-3"></i>
                    <h5 class="text-muted">Nenhuma conexão cadastrada</h5>
                    <p class="text-muted small">Cadastre uma conexão na aba <strong>Conexões</strong> para começar.</p>
                </div>`;
        }
        return;
    }

    const conn = dbConnections.find(c => c.id === dbSelectedConnId);
    const connName = conn ? escapeHtml(conn.name) : `Conexão #${dbSelectedConnId}`;

    const driver = conn ? conn.driver : '';
    const limitHint = driver === 'mssql' ? 'SELECT TOP 100 * FROM tabela;'
        : driver === 'oracle' ? 'SELECT * FROM tabela WHERE ROWNUM <= 100;'
        : 'SELECT * FROM tabela LIMIT 100;';
    const defaultQuery = preloadTable
        ? (driver === 'mssql' ? `SELECT TOP 100 *\nFROM ${preloadTable};`
            : driver === 'oracle' ? `SELECT * FROM ${preloadTable}\nWHERE ROWNUM <= 100;`
            : `SELECT *\nFROM ${preloadTable}\nLIMIT 100;`)
        : (dbQueryResult ? '' : limitHint);

    container.innerHTML = `
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2">
                    <i class="fas fa-terminal"></i>
                    <strong>Editor SQL</strong>
                    ${dbConnections.length > 1
                        ? `<select class="form-select form-select-sm" style="max-width:220px;font-size:.8rem"
                            onchange="_dbQuickSelectConn(this.value)">
                            ${dbConnections.map(c => `<option value="${c.id}" ${c.id === dbSelectedConnId ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}
                          </select>`
                        : `<span class="badge bg-secondary">${connName}</span>`}
                </div>
                <div class="d-flex align-items-center gap-2">
                    <small class="text-muted d-none d-md-inline">Somente SELECT permitido</small>
                    <button class="btn btn-primary btn-sm" data-action="dbExecuteQuery">
                        <i class="fas fa-play me-1"></i>Executar
                    </button>
                </div>
            </div>
            <div class="card-body p-2">
                <textarea id="db-query-input"
                    class="form-control font-monospace"
                    rows="7"
                    placeholder="${escapeHtml(limitHint)}"
                    spellcheck="false"
                    style="resize:vertical; font-size:.85rem; background:var(--bs-dark,#1a1a1a); color:var(--bs-light,#f8f9fa);"
                >${escapeHtml(defaultQuery)}</textarea>
            </div>
            <div class="card-footer d-flex justify-content-between align-items-center">
                <small class="text-muted">
                    <kbd>Ctrl+Enter</kbd> para executar
                </small>
                <div class="d-flex gap-2">
                    <button class="btn btn-sm btn-outline-info" onclick="_dbShowHistoryModal()" title="Histórico de consultas">
                        <i class="fas fa-history me-1"></i>Histórico
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="document.getElementById('db-query-input').value=''">
                        <i class="fas fa-eraser me-1"></i>Limpar
                    </button>
                </div>
            </div>
        </div>

        <!-- Resultados -->
        <div id="db-query-results">
            ${_renderQueryResults()}
        </div>`;

    // Atalho Ctrl+Enter para executar
    const textarea = document.getElementById('db-query-input');
    if (textarea) {
        textarea.addEventListener('keydown', function (e) {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                dbExecuteQuery();
            }
        });
    }

}

function _renderQueryResults() {
    if (!dbQueryResult) {
        return `
            <div class="card text-center py-5">
                <i class="fas fa-table fa-2x text-muted mb-2"></i>
                <p class="text-muted small mb-0">Execute uma consulta para ver os resultados aqui.</p>
            </div>`;
    }

    if (dbQueryResult.error) {
        return `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Erro na consulta:</strong> ${escapeHtml(dbQueryResult.error)}
            </div>`;
    }

    const { columns, rows, rowcount, duration_ms, truncated } = dbQueryResult;

    if (!rows || rows.length === 0) {
        return `
            <div class="alert alert-info">
                <i class="fas fa-info-circle me-2"></i>
                Consulta executada com sucesso. Nenhuma linha retornada.
                ${duration_ms != null ? `<span class="ms-2 text-muted small">(${duration_ms}ms)</span>` : ''}
            </div>`;
    }

    const stickyCol = 'position:sticky; left:0; z-index:1; background:inherit;';
    const stickyCorner = 'position:sticky; left:0; top:0; z-index:3; background:#212529;';
    const stickyHead = 'position:sticky; top:0; z-index:2; background:#212529;';

    const headerCells = `<th class="text-nowrap text-center" style="font-size:.7rem; width:40px; ${stickyCorner}">#</th>`
        + columns.map(c => `<th class="text-nowrap" style="font-size:.75rem; ${stickyHead}">${escapeHtml(c)}</th>`).join('');

    const bodyRows = rows.map((row, i) => {
        const rowNum = `<td class="text-muted text-center" style="font-size:.7rem; width:40px; ${stickyCol}">${i + 1}</td>`;
        const cells = columns.map(col => {
            const val = row[col];
            const display = val === null ? '<em class="text-muted">NULL</em>' : escapeHtml(String(val));
            return `<td class="text-nowrap" style="font-size:.75rem; cursor:cell; user-select:text;">${display}</td>`;
        }).join('');
        const rowBg = i % 2 === 0 ? '#1a1d21' : '#212529';
        return `<tr style="background:${rowBg};">${rowNum}${cells}</tr>`;
    }).join('');

    return `
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <strong class="small">
                    <i class="fas fa-table me-2 text-success"></i>Resultado
                </strong>
                <div class="d-flex align-items-center gap-2">
                    <span class="badge bg-success">${rowcount != null ? rowcount : rows.length} linhas</span>
                    ${truncated ? '<span class="badge bg-warning text-dark" title="Resultado truncado. Use CSV para exportar todas as linhas.">truncado</span>' : ''}
                    ${duration_ms != null ? `<span class="badge bg-secondary">${duration_ms}ms</span>` : ''}
                    <button class="btn btn-sm btn-outline-success" onclick="_dbExportCsv()" title="Exportar resultado para CSV">
                        <i class="fas fa-file-csv me-1"></i>CSV
                    </button>
                </div>
            </div>
            <div class="card-body p-0" style="max-height:50vh; overflow:auto;">
                <table class="table table-sm table-hover table-bordered mb-0">
                    <thead>
                        <tr>${headerCells}</tr>
                    </thead>
                    <tbody>${bodyRows}</tbody>
                </table>
            </div>
        </div>`;
}

function _renderHistoryList() {
    if (dbQueryHistory.length === 0) {
        return `<p class="text-muted text-center small py-4">Nenhuma consulta no histórico.</p>`;
    }

    return dbQueryHistory.map((item, idx) => {
        const preview = truncate(item.query || '', 60);
        const ts = item.executed_at ? _formatDateTime(item.executed_at) : '';
        const statusIcon = item.success === false
            ? '<i class="fas fa-times-circle text-danger me-1"></i>'
            : '<i class="fas fa-check-circle text-success me-1"></i>';

        return `
        <div class="border-bottom p-2">
            <div class="d-flex align-items-start justify-content-between">
                ${statusIcon}
                <button class="btn btn-link btn-sm p-0 text-start flex-grow-1"
                    onclick="dbLoadHistoryQuery(${idx})"
                    title="${escapeHtml(item.query || '')}">
                    <code class="small text-wrap">${escapeHtml(preview)}</code>
                </button>
            </div>
            <small class="text-muted">${ts}</small>
        </div>`;
    }).join('');
}

// =====================================================================
// MODAL DE CRIAR / EDITAR CONEXÃO
// =====================================================================

function _renderConnModal() {
    const driverOptions = dbDrivers.length > 0
        ? dbDrivers.map(d => {
            const meta = DB_DRIVER_META[d.id || d] || { label: d.label || d };
            const id = d.id || d;
            return `<option value="${escapeHtml(id)}">${escapeHtml(meta.label || d.label || id)}</option>`;
        }).join('')
        : Object.entries(DB_DRIVER_META).map(([id, m]) =>
            `<option value="${id}">${m.label}</option>`
        ).join('');

    return `
    <div class="modal fade" id="dbConnModal" tabindex="-1" aria-labelledby="dbConnModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="dbConnModalLabel">
                        <i class="fas fa-database me-2"></i>
                        <span id="dbConnModalTitle">Nova Conexão</span>
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                </div>
                <div class="modal-body">
                    <input type="hidden" id="dbConnId">

                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnName">Nome da Conexão <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" id="dbConnName"
                                placeholder="Ex: Protheus PRD" maxlength="100" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnDriver">Driver <span class="text-danger">*</span></label>
                            <select class="form-select" id="dbConnDriver" onchange="_dbDriverChanged(this.value)">
                                <option value="">Selecione o driver...</option>
                                ${driverOptions}
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnHost">Host / IP <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" id="dbConnHost"
                                placeholder="Ex: 192.168.1.100 ou servidor.empresa.com.br" maxlength="200">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label" for="dbConnPort">Porta <span class="text-danger">*</span></label>
                            <input type="number" class="form-control" id="dbConnPort"
                                placeholder="1433" min="1" max="65535">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label" for="dbConnDatabase">Database <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" id="dbConnDatabase"
                                placeholder="Ex: PROTHEUS_P12" maxlength="200">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnUser">Usuário <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" id="dbConnUser"
                                placeholder="Ex: sa" autocomplete="off" maxlength="100">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnPassword">
                                Senha
                                <span id="dbConnPasswordHint" class="text-muted small"></span>
                            </label>
                            <div class="input-group">
                                <input type="password" class="form-control" id="dbConnPassword"
                                    autocomplete="new-password" maxlength="256">
                                <button type="button" class="btn btn-outline-secondary"
                                    onclick="_dbTogglePassword()">
                                    <i class="fas fa-eye" id="dbConnPasswordEyeIcon"></i>
                                </button>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnRefEnv">Ambiente de Referência</label>
                            <select class="form-select" id="dbConnRefEnv">
                                <option value="">(mesmo do ambiente ativo)</option>
                            </select>
                            <div class="form-text">Ambiente BiizHubOps que esta conexão representa. Permite cadastrar conexões de outros ambientes para consulta/comparação.</div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label" for="dbConnRole">Papel da Conexão</label>
                            <input type="text" class="form-control" id="dbConnRole"
                                placeholder="Ex: Protheus, BI, Legado" maxlength="50" value="Protheus">
                            <div class="form-text">Label livre para identificar a finalidade (Protheus, BI, Legado, etc.).</div>
                        </div>
                        <div class="col-12">
                            <label class="form-label" for="dbConnRestUrl">
                                <i class="fas fa-plug me-1 text-info"></i>REST URL do AppServer (opcional)
                            </label>
                            <input type="text" class="form-control" id="dbConnRestUrl"
                                placeholder="Ex: http://192.168.1.100:8080/rest"
                                maxlength="500">
                            <div class="form-text">URL base REST do Protheus AppServer. Usada pelo equalizador para forçar TcRefresh após criar campos, garantindo que o DBAccess reconheça as alterações imediatamente.</div>
                        </div>
                        <div class="col-12">
                            <label class="form-label" for="dbConnExtraOpts">Opções Extras (opcional)</label>
                            <input type="text" class="form-control" id="dbConnExtraOpts"
                                placeholder='Ex: {"schema":"dbo","timeout":30}'
                                maxlength="500">
                            <div class="form-text">JSON com opções adicionais específicas do driver.</div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                    <button type="button" class="btn btn-primary" data-action="dbSaveConn">
                        <i class="fas fa-save me-2"></i>Salvar
                    </button>
                </div>
            </div>
        </div>
    </div>`;
}

// Preenchimento automático de porta ao trocar driver
function _dbDriverChanged(driverKey) {
    const meta = DB_DRIVER_META[driverKey];
    if (meta && meta.port) {
        const portField = document.getElementById('dbConnPort');
        if (portField && !portField.value) {
            portField.value = meta.port;
        }
    }
}

// Toggle visibilidade da senha no modal
function _dbTogglePassword() {
    const input = document.getElementById('dbConnPassword');
    const icon = document.getElementById('dbConnPasswordEyeIcon');
    if (!input) return;
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) { icon.className = 'fas fa-eye-slash'; }
    } else {
        input.type = 'password';
        if (icon) { icon.className = 'fas fa-eye'; }
    }
}

// =====================================================================
// FUNÇÕES PÚBLICAS (chamadas do actionHandlers em integration-core.js)
// =====================================================================

/**
 * Alterna entre as abas: connections, explorer, queries.
 */
function dbSwitchTab(tab, extra = {}) {
    dbActiveTab = tab;

    // Atualiza classes dos botões da nav
    document.querySelectorAll('#db-tabs .nav-link').forEach(btn => {
        const btnParams = JSON.parse(btn.dataset.params || '{}');
        btn.classList.toggle('active', btnParams.tab === tab);
    });

    // Esconde todos os painéis
    document.querySelectorAll('.db-tab-panel').forEach(p => p.classList.add('d-none'));

    const panel = document.getElementById(`db-tab-${tab}`);
    if (panel) panel.classList.remove('d-none');

    // Renderiza o conteúdo da aba selecionada
    if (tab === 'connections') {
        _renderConnectionsTab();
    } else if (tab === 'explorer') {
        _renderExplorerTab();
    } else if (tab === 'queries') {
        _renderQueriesTab(extra.table || null);
    } else if (tab === 'compare') {
        _renderCompareTab();
    } else if (tab === 'integrity') {
        _renderIntegrityTab();
    } else if (tab === 'equalize') {
        _renderEqualizeTab();
    } else if (tab === 'ingestor') {
        _renderIngestorTab();
    }
}

/**
 * Abre o modal para criar nova conexão.
 */
function dbShowCreateConn() {
    if (!isAdmin()) {
        showNotification('Apenas administradores podem criar conexões.', 'error');
        return;
    }

    // Limpa o formulário
    _dbResetConnForm();
    document.getElementById('dbConnModalTitle').textContent = 'Nova Conexão';
    document.getElementById('dbConnPasswordHint').textContent = '';

    // Popula select de ambiente de referência
    const refEnvSelect = document.getElementById('dbConnRefEnv');
    if (refEnvSelect) _dbPopulateRefEnvSelect(refEnvSelect);

    _dbGetOrCreateModal().show();
}

/**
 * Abre o modal para editar uma conexão existente.
 */
function dbEditConn(id) {
    if (!isAdmin()) {
        showNotification('Apenas administradores podem editar conexões.', 'error');
        return;
    }

    const conn = dbConnections.find(c => c.id === id);
    if (!conn) {
        showNotification('Conexão não encontrada.', 'error');
        return;
    }

    _dbResetConnForm();
    document.getElementById('dbConnModalTitle').textContent = 'Editar Conexão';
    document.getElementById('dbConnId').value = conn.id;
    document.getElementById('dbConnName').value = conn.name || '';
    document.getElementById('dbConnDriver').value = conn.driver || '';
    document.getElementById('dbConnHost').value = conn.host || '';
    document.getElementById('dbConnPort').value = conn.port || '';
    document.getElementById('dbConnDatabase').value = conn.database_name || conn.database || '';
    document.getElementById('dbConnUser').value = conn.username || '';
    // Senha nunca é pré-preenchida — apenas placeholder informativo
    document.getElementById('dbConnPassword').value = '';
    document.getElementById('dbConnPassword').placeholder = '(deixe em branco para manter a atual)';
    document.getElementById('dbConnPasswordHint').textContent = '— deixe em branco para manter';
    const extraVal = conn.extra_params || conn.extra_options || '';
    document.getElementById('dbConnExtraOpts').value = extraVal
        ? (typeof extraVal === 'string' ? extraVal : JSON.stringify(extraVal))
        : '';

    // Campos ref_environment_id e connection_role
    const refEnvSelect = document.getElementById('dbConnRefEnv');
    if (refEnvSelect) {
        _dbPopulateRefEnvSelect(refEnvSelect, conn.ref_environment_id);
    }
    const roleField = document.getElementById('dbConnRole');
    if (roleField) roleField.value = conn.connection_role || 'Protheus';

    const restUrlField = document.getElementById('dbConnRestUrl');
    if (restUrlField) restUrlField.value = conn.rest_url || '';

    _dbGetOrCreateModal().show();
}

/**
 * Salva a conexão (cria nova ou atualiza existente).
 */
async function dbSaveConn() {
    if (!isAdmin()) {
        showNotification('Apenas administradores podem salvar conexões.', 'error');
        return;
    }

    const id = document.getElementById('dbConnId').value;
    const name = document.getElementById('dbConnName').value.trim();
    const driver = document.getElementById('dbConnDriver').value;
    const host = document.getElementById('dbConnHost').value.trim();
    const port = parseInt(document.getElementById('dbConnPort').value, 10);
    const database = document.getElementById('dbConnDatabase').value.trim();
    const username = document.getElementById('dbConnUser').value.trim();
    const password = document.getElementById('dbConnPassword').value;
    const extraOptsRaw = document.getElementById('dbConnExtraOpts').value.trim();

    // Validações básicas
    if (!name) return showNotification('O nome da conexão é obrigatório.', 'error');
    if (!driver) return showNotification('Selecione um driver.', 'error');
    if (!host) return showNotification('O host/IP é obrigatório.', 'error');
    if (!port || port < 1 || port > 65535) return showNotification('Informe uma porta válida (1-65535).', 'error');
    if (!database) return showNotification('O nome do database é obrigatório.', 'error');
    if (!username) return showNotification('O usuário é obrigatório.', 'error');
    if (!id && !password) return showNotification('A senha é obrigatória para novas conexões.', 'error');

    let extra_options = null;
    if (extraOptsRaw) {
        try {
            extra_options = JSON.parse(extraOptsRaw);
        } catch {
            return showNotification('Opções extras devem ser um JSON válido.', 'error');
        }
    }

    const refEnvId = document.getElementById('dbConnRefEnv')?.value;
    const connectionRole = document.getElementById('dbConnRole')?.value?.trim() || 'Protheus';

    const restUrl = document.getElementById('dbConnRestUrl')?.value?.trim() || '';

    const payload = { name, driver, host, port, database_name: database, username, extra_params: extra_options ? JSON.stringify(extra_options) : '', connection_role: connectionRole, rest_url: restUrl };
    if (password) payload.password = password;
    if (refEnvId) payload.ref_environment_id = parseInt(refEnvId, 10);

    const envId = sessionStorage.getItem('active_environment_id');
    if (envId) payload.environment_id = parseInt(envId, 10);

    const saveBtn = document.querySelector('#dbConnModal .btn-primary[data-action="dbSaveConn"]');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Salvando...';
    }

    try {
        if (id) {
            await apiRequest(`/db-connections/${id}`, 'PUT', payload);
            showNotification('Conexão atualizada com sucesso!', 'success');
        } else {
            await apiRequest('/db-connections', 'POST', payload);
            showNotification('Conexão criada com sucesso!', 'success');
        }

        bootstrap.Modal.getInstance(document.getElementById('dbConnModal'))?.hide();

        // Recarrega a lista de conexões
        const connsResp = await apiRequest(`/db-connections${envId ? '?environment_id=' + envId : ''}`);
        dbConnections = connsResp.connections || connsResp || [];
        dbSwitchTab('connections');
    } catch (error) {
        showNotification(error.message || 'Erro ao salvar conexão.', 'error');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Salvar';
        }
    }
}

/**
 * Exclui uma conexão com confirmação.
 */
async function dbDeleteConn(id) {
    if (!isAdmin()) {
        showNotification('Apenas administradores podem excluir conexões.', 'error');
        return;
    }

    const conn = dbConnections.find(c => c.id === id);
    if (!conn) return;

    if (!confirm(`Tem certeza que deseja excluir a conexão "${conn.name}"?\n\nEssa ação não pode ser desfeita.`)) {
        return;
    }

    try {
        await apiRequest(`/db-connections/${id}`, 'DELETE');
        showNotification(`Conexão "${conn.name}" excluída.`, 'warning');

        // Se era a conexão selecionada, limpa o estado
        if (dbSelectedConnId === id) {
            dbSelectedConnId = null;
            dbTables = [];
            dbSelectedTable = null;
            dbColumns = [];
        }

        const envId = sessionStorage.getItem('active_environment_id');
        const connsResp = await apiRequest(`/db-connections${envId ? '?environment_id=' + envId : ''}`);
        dbConnections = connsResp.connections || connsResp || [];
        _renderConnectionsTab();
    } catch (error) {
        showNotification(error.message || 'Erro ao excluir conexão.', 'error');
    }
}

/**
 * Testa a conectividade de uma conexão.
 */
async function dbTestConn(id) {
    const conn = dbConnections.find(c => c.id === id);
    if (!conn) return;

    showNotification(`Testando conexão "${conn.name}"...`, 'info');

    try {
        const result = await apiRequest(`/db-connections/${id}/test`, 'POST');
        if (result.success) {
            showNotification(`Conexão "${conn.name}" OK! (${result.duration_ms || '?'}ms)`, 'success');
            // Atualiza o objeto local com o novo status
            conn.last_connected_at = new Date().toISOString();
            conn.last_error = null;
        } else {
            conn.last_error = result.error || 'Falha desconhecida';
            showNotification(`Falha na conexão: ${result.error || 'Erro desconhecido'}`, 'error');
        }
        _renderConnectionsTab();
    } catch (error) {
        conn.last_error = error.message;
        showNotification(error.message || 'Erro ao testar conexão.', 'error');
        _renderConnectionsTab();
    }
}

/**
 * Dispara a descoberta de schema (tabelas e colunas) em background.
 */
async function dbDiscover(id) {
    console.log('[dbDiscover] chamado com id:', id);
    if (!id) {
        showNotification('Nenhuma conexão selecionada para descobrir schema.', 'warning');
        return;
    }
    const conn = dbConnections.find(c => c.id === id) || { name: `#${id}` };

    showNotification(`Descobrindo schema de "${conn.name}"... Isso pode levar alguns segundos.`, 'info');

    try {
        const result = await apiRequest(`/db-connections/${id}/discover`, 'POST');
        showNotification(
            `Schema descoberto: ${result.table_count || '?'} tabelas encontradas em "${conn.name}".`,
            'success'
        );

        // Recarrega a lista de tabelas e re-renderiza o explorador
        if (dbSelectedConnId === id) {
            await _dbLoadTables(id);
            dbSwitchTab('explorer');
        }
    } catch (error) {
        showNotification(error.message || 'Erro ao descobrir schema.', 'error');
    }
}

/**
 * Seleciona uma conexão como ativa e navega para o explorador.
 */
async function dbSelectConn(id) {
    dbSelectedConnId = id;
    dbSelectedTable = null;
    dbColumns = [];
    dbTables = [];

    showNotification('Carregando tabelas...', 'info');

    try {
        await _dbLoadTables(id);
        dbSwitchTab('explorer');
    } catch (error) {
        showNotification(error.message || 'Erro ao carregar tabelas.', 'error');
        dbSwitchTab('explorer');
    }
}

/**
 * Seleciona uma tabela e carrega suas colunas.
 */
async function dbSelectTable(name) {
    if (!dbSelectedConnId) return;

    dbSelectedTable = name;
    dbColumns = [];
    dbTableDetails = null;

    // Atualiza visualmente a seleção na lista sem re-renderizar tudo
    const panel = document.getElementById('db-columns-panel');
    if (panel) {
        panel.innerHTML = `
            <div class="card text-center p-4">
                <div class="spinner-border spinner-border-sm text-primary mx-auto mb-2"></div>
                <p class="text-muted small">Carregando detalhes de <strong>${escapeHtml(name)}</strong>...</p>
            </div>`;
    }

    // Marca o item ativo na lista
    document.querySelectorAll('#db-table-list .list-group-item').forEach(btn => {
        const p = JSON.parse(btn.dataset.params || '{}');
        btn.classList.toggle('active', p.name === name);
    });

    try {
        // Buscar colunas e detalhes em paralelo
        const encodedName = encodeURIComponent(name);
        const [colResult, detailResult] = await Promise.all([
            apiRequest(`/db-connections/${dbSelectedConnId}/tables/${encodedName}/columns`),
            apiRequest(`/db-connections/${dbSelectedConnId}/tables/${encodedName}/details`).catch(() => null),
        ]);
        dbColumns = colResult.columns || colResult || [];
        dbTableDetails = detailResult;

        if (panel) panel.innerHTML = _renderColumnsPanel();
    } catch (error) {
        dbColumns = [];
        dbTableDetails = null;
        if (panel) {
            panel.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Erro ao carregar colunas: ${escapeHtml(error.message)}
                </div>`;
        }
    }
}

/**
 * Mostra dados de amostra de uma tabela em um modal.
 */
async function dbViewSample(name) {
    if (!dbSelectedConnId) return;

    // Cria modal de amostra dinamicamente
    const modalId = 'dbSampleModal';
    let modal = document.getElementById(modalId);
    if (modal) modal.remove();

    const modalHtml = `
    <div class="modal fade" id="${modalId}" tabindex="-1">
        <div class="modal-dialog modal-xl modal-dialog-scrollable">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">
                        <i class="fas fa-eye me-2"></i>Amostra: <code>${escapeHtml(name)}</code>
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body" id="${modalId}-body">
                    <div class="text-center py-4">
                        <div class="spinner-border text-primary"></div>
                        <p class="text-muted mt-2">Carregando amostra...</p>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
                    <button type="button" class="btn btn-outline-success"
                        data-action="dbSwitchTab" data-params='{"tab":"queries","table":"${escapeHtml(name)}"}'>
                        <i class="fas fa-terminal me-1"></i>Abrir no Editor SQL
                    </button>
                </div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const bsModal = new bootstrap.Modal(document.getElementById(modalId));
    bsModal.show();

    try {
        const result = await apiRequest(
            `/db-connections/${dbSelectedConnId}/tables/${encodeURIComponent(name)}/sample?limit=50`
        );

        const { columns, rows } = result;
        const bodyEl = document.getElementById(`${modalId}-body`);
        if (!bodyEl) return;

        if (!rows || rows.length === 0) {
            bodyEl.innerHTML = `<p class="text-muted text-center py-4">Tabela vazia ou sem dados de amostra.</p>`;
            return;
        }

        const headerCells = columns.map(c => `<th class="small text-nowrap">${escapeHtml(c)}</th>`).join('');
        const bodyRows = rows.map(row => {
            const cells = columns.map(col => {
                const val = row[col];
                const display = val === null ? '<em class="text-muted">NULL</em>' : escapeHtml(String(val));
                return `<td class="small">${display}</td>`;
            }).join('');
            return `<tr>${cells}</tr>`;
        }).join('');

        bodyEl.innerHTML = `
            <p class="text-muted small mb-2">Exibindo ${rows.length} linhas de amostra.</p>
            <div class="table-responsive">
                <table class="table table-sm table-bordered table-hover">
                    <thead class="table-dark sticky-top"><tr>${headerCells}</tr></thead>
                    <tbody>${bodyRows}</tbody>
                </table>
            </div>`;
    } catch (error) {
        const bodyEl = document.getElementById(`${modalId}-body`);
        if (bodyEl) {
            bodyEl.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Erro ao carregar amostra: ${escapeHtml(error.message)}
                </div>`;
        }
    }
}

/**
 * Executa a consulta SQL digitada no editor.
 */
async function dbExecuteQuery() {
    if (!dbSelectedConnId) {
        showNotification('Selecione uma conexão antes de executar consultas.', 'warning');
        return;
    }

    const textarea = document.getElementById('db-query-input');
    if (!textarea) return;

    const query = textarea.value.trim();
    if (!query) {
        showNotification('Digite uma consulta SQL para executar.', 'warning');
        return;
    }

    // Validação client-side: só permite SELECT
    const firstWord = query.replace(/\s+/g, ' ').split(' ')[0].toUpperCase();
    if (firstWord !== 'SELECT' && firstWord !== 'WITH') {
        showNotification('Apenas consultas SELECT são permitidas por segurança.', 'error');
        return;
    }

    // Exibe spinner nos resultados
    const resultsEl = document.getElementById('db-query-results');
    if (resultsEl) {
        resultsEl.innerHTML = `
            <div class="card text-center p-4">
                <div class="spinner-border text-primary mx-auto mb-2"></div>
                <p class="text-muted small">Executando consulta...</p>
            </div>`;
    }

    const execBtn = document.querySelector('[data-action="dbExecuteQuery"]');
    if (execBtn) {
        execBtn.disabled = true;
        execBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Executando...';
    }

    try {
        const result = await apiRequest(`/db-connections/${dbSelectedConnId}/query`, 'POST', { query });
        dbQueryResult = result;

        if (resultsEl) {
            resultsEl.innerHTML = _renderQueryResults();
            _dbBindCellSelect(resultsEl);
        }

        const rowCount = result.rowcount != null ? result.rowcount : (result.rows || []).length;
        showNotification(`Consulta executada: ${rowCount} linha(s) retornada(s).`, 'success');

        // Atualiza o histórico
        await dbLoadHistory();
    } catch (error) {
        dbQueryResult = { error: error.message };
        if (resultsEl) resultsEl.innerHTML = _renderQueryResults();
        showNotification(error.message || 'Erro ao executar consulta.', 'error');
    } finally {
        if (execBtn) {
            execBtn.disabled = false;
            execBtn.innerHTML = '<i class="fas fa-play me-1"></i>Executar';
        }
    }
}

/**
 * Carrega o histórico de consultas do servidor.
 */
async function dbLoadHistory() {
    if (!dbSelectedConnId) return;

    try {
        const result = await apiRequest(`/db-connections/${dbSelectedConnId}/history?limit=50`);
        dbQueryHistory = result.history || result || [];

        const historyEl = document.getElementById('db-history-list');
        if (historyEl) historyEl.innerHTML = _renderHistoryList();
    } catch {
        // Falha silenciosa no histórico — não crítico
    }
}

function _dbShowHistoryModal() {
    dbLoadHistory().then(() => {
        let modal = document.getElementById('dbHistoryModal');
        if (!modal) {
            document.body.insertAdjacentHTML('beforeend', `
                <div class="modal fade" id="dbHistoryModal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog modal-lg modal-dialog-scrollable">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title"><i class="fas fa-history me-2"></i>Histórico de Consultas</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
                            </div>
                            <div class="modal-body p-0" id="db-history-list"></div>
                        </div>
                    </div>
                </div>`);
            modal = document.getElementById('dbHistoryModal');
        }
        const listEl = modal.querySelector('#db-history-list');
        if (listEl) listEl.innerHTML = _renderHistoryList();
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    });
}

/**
 * Carrega uma consulta do histórico no editor.
 */
function dbLoadHistoryQuery(idx) {
    const item = dbQueryHistory[idx];
    if (!item) return;

    const textarea = document.getElementById('db-query-input');
    if (textarea) {
        textarea.value = item.query || '';
        textarea.focus();
    }

    // Fecha o modal do histórico
    const modal = document.getElementById('dbHistoryModal');
    if (modal) {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) bsModal.hide();
    }
}

// =====================================================================
// FUNÇÕES INTERNAS AUXILIARES
// =====================================================================

async function _dbLoadTables(connId) {
    const result = await apiRequest(`/db-connections/${connId}/tables`);
    dbTables = result.tables || result || [];
}

function _dbResetConnForm() {
    const fields = ['dbConnId', 'dbConnName', 'dbConnHost', 'dbConnPort',
                    'dbConnDatabase', 'dbConnUser', 'dbConnPassword', 'dbConnExtraOpts', 'dbConnRefEnv',
                    'dbConnRestUrl'];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const driverEl = document.getElementById('dbConnDriver');
    if (driverEl) driverEl.value = '';

    const passInput = document.getElementById('dbConnPassword');
    if (passInput) {
        passInput.type = 'password';
        passInput.placeholder = '';
    }

    const eyeIcon = document.getElementById('dbConnPasswordEyeIcon');
    if (eyeIcon) eyeIcon.className = 'fas fa-eye';

    const roleField = document.getElementById('dbConnRole');
    if (roleField) roleField.value = 'Protheus';
}

/**
 * Popula o select de Ambiente de Referência com todos os ambientes cadastrados.
 */
async function _dbPopulateRefEnvSelect(selectEl, selectedId) {
    if (!selectEl) return;
    try {
        const envs = await apiRequest('/environments');
        const envList = Array.isArray(envs) ? envs : (envs.environments || []);
        let html = '<option value="">(mesmo do ambiente ativo)</option>';
        envList.forEach(env => {
            const sel = (selectedId && env.id == selectedId) ? 'selected' : '';
            html += `<option value="${env.id}" ${sel}>${escapeHtml(env.name)}</option>`;
        });
        selectEl.innerHTML = html;
    } catch (e) {
        console.warn('Erro ao carregar ambientes para ref_environment_id:', e);
    }
}

function _renderConnSelector(selectId) {
    const options = dbConnections.map(c => {
        const meta = DB_DRIVER_META[c.driver] || { label: c.driver };
        return `<option value="${c.id}">${escapeHtml(c.name)} (${meta.label} — ${escapeHtml(c.host || '')}:${c.port || ''})</option>`;
    }).join('');

    return `
        <div class="d-inline-block" style="min-width:300px;">
            <select class="form-select" id="${selectId}" onchange="_dbQuickSelectConn(this.value)">
                <option value="">-- Selecione a conexão --</option>
                ${options}
            </select>
        </div>`;
}

function _dbQuickSelectConn(idStr) {
    if (!idStr) return;
    dbSelectConn(parseInt(idStr, 10));
}

async function _dbExportCsv() {
    // Pega a query do editor (exporta sem limite via backend)
    const textarea = document.getElementById('db-query-input');
    const query = textarea ? textarea.value.trim() : '';
    if (!query || !dbSelectedConnId) {
        showNotification('Nenhuma consulta para exportar.', 'warning');
        return;
    }

    showNotification('Gerando CSV completo (sem limite de linhas)...', 'info');

    try {
        const resp = await apiStreamRequest(`/db-connections/${dbSelectedConnId}/query/csv`, { query });
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `query_export_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        showNotification('CSV exportado com sucesso (todas as linhas).', 'success');
    } catch (e) {
        showNotification(e.message || 'Erro ao exportar CSV.', 'error');
    }
}

function _dbBindCellSelect(container) {
    container.querySelectorAll('td').forEach(td => {
        td.addEventListener('click', () => {
            // Seleciona o texto da célula
            const range = document.createRange();
            range.selectNodeContents(td);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);

            // Copia para clipboard
            const text = td.innerText;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(() => {
                    td.style.outline = '2px solid var(--bs-success)';
                    setTimeout(() => { td.style.outline = ''; }, 400);
                });
            }
        });
    });
}

function _dbGetOrCreateModal() {
    const el = document.getElementById('dbConnModal');
    if (!el) {
        // O modal é injetado pelo _renderDatabasePage(). Se não existir, recria.
        document.body.insertAdjacentHTML('beforeend', _renderConnModal());
    }
    return new bootstrap.Modal(document.getElementById('dbConnModal'));
}

function _formatDateTime(isoString) {
    if (!isoString) return '-';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch {
        return isoString;
    }
}


// =====================================================================
// ABA: COMPARAR DICIONÁRIO
// =====================================================================

const METADATA_TABLES = ['SIX','SX1','SX2','SX3','SX5','SX6','SX7','SX9','SXA','SXB','XXA','XAM','XAL'];
const METADATA_TABLE_NAMES = {
    'SIX': 'Índices',
    'SX1': 'Perguntas',
    'SX2': 'Tabelas',
    'SX3': 'Campos',
    'SX5': 'Tabelas Genéricas',
    'SX6': 'Parâmetros',
    'SX7': 'Gatilhos',
    'SX9': 'Relacionamentos',
    'SXA': 'Pastas Campos',
    'SXB': 'Consultas',
    'XXA': 'Regras de Preenchimento',
    'XAM': 'Campos da LGPD',
    'XAL': 'Grupos da LGPD',
};

// Estado local: comparação em progresso
let _dictCompareRunning = false;
let _dictCompareProgress = null; // {tables, stepStatuses, interval}

function _renderCompareTab() {
    const container = document.getElementById('db-compare-content');
    if (!container) return;

    if (dbConnections.length < 2) {
        container.innerHTML = `
            <div class="card text-center p-5">
                <i class="fas fa-columns fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">Necessário ao menos 2 conexões</h5>
                <p class="text-muted small">Cadastre pelo menos duas conexões de banco de dados para comparar dicionários.</p>
            </div>`;
        return;
    }

    const connOptions = dbConnections.map(c => `<option value="${c.id}">${escapeHtml(c.name)} (${c.host}/${c.database_name})</option>`).join('');

    const tableChecks = METADATA_TABLES.map(t =>
        `<div class="form-check form-check-inline">
            <input class="form-check-input dict-table-check" type="checkbox" value="${t}" id="dict-chk-${t}" checked onchange="_dictSyncAllTablesCheckbox()">
            <label class="form-check-label small" for="dict-chk-${t}" title="${METADATA_TABLE_NAMES[t] || t}">${t} <span class="text-muted" style="font-size:.7rem">${METADATA_TABLE_NAMES[t] || ''}</span></label>
        </div>`
    ).join('');

    container.innerHTML = `
        <div class="card mb-3">
            <div class="card-body">
                <h6 class="card-title"><i class="fas fa-columns me-2"></i>Comparar Dicionário Protheus</h6>
                <p class="text-muted small mb-3">Compare as tabelas de metadados (SX*) entre dois bancos para identificar divergências.</p>

                <div class="row g-3 align-items-end">
                    <div class="col-md-3">
                        <label class="form-label small fw-bold">Conexão A (Origem)</label>
                        <select class="form-select form-select-sm" id="dict-conn-a">${connOptions}</select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Empresa A</label>
                        <select class="form-select form-select-sm" id="dict-company-a">
                            <option value="">Selecione conexão...</option>
                        </select>
                    </div>
                    <div class="col-md-1 text-center">
                        <span class="badge bg-primary fs-6">vs</span>
                    </div>
                    <div class="col-md-3">
                        <label class="form-label small fw-bold">Conexão B (Destino)</label>
                        <select class="form-select form-select-sm" id="dict-conn-b">
                            ${dbConnections.length > 1 ? dbConnections.map((c, i) => `<option value="${c.id}" ${i === 1 ? 'selected' : ''}>${escapeHtml(c.name)} (${c.host}/${c.database_name})</option>`).join('') : connOptions}
                        </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Empresa B</label>
                        <select class="form-select form-select-sm" id="dict-company-b">
                            <option value="">Selecione conexão...</option>
                        </select>
                    </div>
                </div>

                <div class="mt-3">
                    <label class="form-label small fw-bold">Tabelas para comparar:</label>
                    <div class="d-flex flex-wrap gap-1 align-items-center">
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" id="dict-chk-all" checked onchange="dictToggleAllTables()">
                            <label class="form-check-label small fw-bold" for="dict-chk-all">Todas</label>
                        </div>
                        ${tableChecks}
                    </div>
                </div>

                <div class="mt-2">
                    <div class="form-check form-check-inline">
                        <input class="form-check-input" type="checkbox" id="dict-include-deleted">
                        <label class="form-check-label small" for="dict-include-deleted">
                            <i class="fas fa-trash-alt me-1 text-muted"></i>Incluir registros deletados (D_E_L_E_T_ = '*')
                        </label>
                    </div>
                </div>

                <div class="mt-2">
                    <label class="form-label small fw-bold"><i class="fas fa-filter me-1"></i>Filtrar por alias (opcional):</label>
                    <input type="text" class="form-control form-control-sm" id="dict-alias-filter"
                        placeholder="Ex: SA1, SA2, SB1 — vazio = compara tudo"
                        title="Aliases Protheus separados por vírgula. Filtra SX2, SX3, SIX e demais tabelas pela coluna de alias.">
                </div>

                <div class="mt-3">
                    <button class="btn btn-primary btn-sm" data-action="dictRunCompare" id="dict-compare-btn"
                        ${_dictCompareRunning ? 'disabled' : ''}>
                        ${_dictCompareRunning
                            ? '<i class="fas fa-spinner fa-spin me-1"></i>Comparando...'
                            : '<i class="fas fa-search me-1"></i>Comparar'}
                    </button>
                </div>
            </div>
        </div>

        <!-- Progress (visível durante comparação) -->
        <div id="dict-compare-progress" class="${_dictCompareRunning ? '' : 'd-none'}"></div>

        <!-- Histórico de comparações -->
        <div id="dict-compare-history">
            <div class="d-flex justify-content-center py-3">
                <div class="spinner-border spinner-border-sm text-muted"></div>
                <span class="text-muted ms-2 small">Carregando histórico...</span>
            </div>
        </div>
    `;

    // Carregar empresas ao mudar conexão
    const connA = document.getElementById('dict-conn-a');
    const connB = document.getElementById('dict-conn-b');
    if (connA) {
        connA.addEventListener('change', () => _dictLoadCompanies(connA.value, document.getElementById('dict-company-a')));
        _dictLoadCompanies(connA.value, document.getElementById('dict-company-a'));
    }
    if (connB) {
        connB.addEventListener('change', () => _dictLoadCompanies(connB.value, document.getElementById('dict-company-b')));
        _dictLoadCompanies(connB.value, document.getElementById('dict-company-b'));
    }

    // Restaurar progress se estiver rodando
    if (_dictCompareRunning && _dictCompareProgress) {
        const progressDiv = document.getElementById('dict-compare-progress');
        if (progressDiv) {
            const tables = _dictCompareProgress.tables || [];
            let stepsHtml = tables.map(t => `
                <div class="d-flex align-items-center mb-1" id="cmp-step-${t}">
                    <span class="me-2" style="width:18px;text-align:center"><i class="far fa-circle text-muted" style="font-size:.7rem"></i></span>
                    <span class="small fw-bold">${t}</span>
                    <span class="ms-auto badge bg-secondary" style="font-size:.65rem">AGUARDANDO</span>
                </div>`).join('');
            progressDiv.innerHTML = `
                <div class="card mb-3"><div class="card-body py-3">
                    <h6 class="mb-3"><i class="fas fa-spinner fa-spin me-2"></i>Comparando ${tables.length} tabelas...</h6>
                    ${stepsHtml}
                </div></div>`;
            progressDiv.classList.remove('d-none');
            // Restaurar status de cada step
            for (const [t, info] of Object.entries(_dictCompareProgress.stepStatuses || {})) {
                const el = document.getElementById(`cmp-step-${t}`);
                if (!el) continue;
                const icon = info.status === 'running' ? '<i class="fas fa-spinner fa-spin text-primary" style="font-size:.7rem"></i>'
                    : info.status === 'done' ? '<i class="fas fa-check-circle text-success" style="font-size:.7rem"></i>'
                    : '<i class="fas fa-times-circle text-danger" style="font-size:.7rem"></i>';
                const badge = info.status === 'running' ? 'bg-primary' : info.status === 'done' ? 'bg-success' : 'bg-danger';
                el.querySelector('span').innerHTML = icon;
                el.querySelector('.badge').className = `ms-auto badge ${badge}`;
                el.querySelector('.badge').style.fontSize = '.65rem';
                el.querySelector('.badge').textContent = info.label || 'EXECUTANDO...';
            }
            // Esconder histórico durante execução
            const histDiv = document.getElementById('dict-compare-history');
            if (histDiv) histDiv.classList.add('d-none');
        }
    }

    // Carregar histórico
    _dictLoadCompareHistory();
}

async function _dictLoadCompanies(connId, selectEl) {
    if (!connId || !selectEl) return;

    // Usar cache se disponível
    if (dictCompaniesCache[connId]) {
        _dictPopulateCompanySelect(selectEl, dictCompaniesCache[connId]);
        return;
    }

    selectEl.innerHTML = '<option value="">Carregando...</option>';
    selectEl.disabled = true;

    try {
        const resp = await apiRequest(`/dictionary/companies/${connId}`);
        const companies = resp.companies || [];
        dictCompaniesCache[connId] = companies;
        _dictPopulateCompanySelect(selectEl, companies);
    } catch (e) {
        selectEl.innerHTML = `<option value="">Erro: ${escapeHtml(e.message)}</option>`;
    } finally {
        selectEl.disabled = false;
    }
}

function _dictPopulateCompanySelect(selectEl, companies) {
    if (companies.length === 0) {
        selectEl.innerHTML = '<option value="">Nenhuma empresa encontrada</option>';
        return;
    }
    selectEl.innerHTML = companies.map(c =>
        `<option value="${escapeHtml(c.code)}">${escapeHtml(c.code)} - ${escapeHtml(c.name)}</option>`
    ).join('');
}

async function _dictLoadCompareHistory() {
    const histDiv = document.getElementById('dict-compare-history');
    if (!histDiv) return;

    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const resp = await apiRequest(`/dictionary/history?environment_id=${envId || ''}&limit=20`);
        const items = (resp.history || []).filter(h => h.operation_type === 'compare');
        _dictRenderCompareHistoryList(histDiv, items);
    } catch (e) {
        histDiv.innerHTML = `<div class="alert alert-warning small"><i class="fas fa-exclamation-triangle me-1"></i>Erro ao carregar histórico: ${escapeHtml(e.message)}</div>`;
    }
}

function _dictRenderCompareHistoryList(container, items) {
    if (items.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-3">
                <i class="fas fa-history fa-2x mb-2 d-block opacity-50"></i>
                <small>Nenhuma comparação realizada ainda.</small>
            </div>`;
        return;
    }

    let html = '<h6 class="mb-3"><i class="fas fa-history me-2"></i>Histórico de Comparações</h6>';
    for (const item of items) {
        const summary = item.summary || {};
        const totalDiffs = summary.total_diffs || 0;
        const tablesWithDiffs = summary.tables_with_diffs || 0;
        const tablesCompared = summary.tables_compared || 0;
        const color = totalDiffs > 0 ? 'warning' : 'success';
        const icon = totalDiffs > 0 ? 'fa-exclamation-triangle' : 'fa-check-circle';

        const connA = item.conn_a_name || `Conexão #${item.connection_a_id}`;
        const connB = item.conn_b_name || `Conexão #${item.connection_b_id}`;
        const dt = item.executed_at ? _dictFormatDate(item.executed_at) : '---';
        const duration = summary.duration_ms ? `${(summary.duration_ms / 1000).toFixed(1)}s` : '';
        const user = item.executed_by_name || '';

        html += `
            <div class="card mb-2">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center gap-3">
                            <div>
                                <span class="badge bg-${color}"><i class="fas ${icon} me-1"></i>${totalDiffs > 0 ? totalDiffs + ' div.' : 'OK'}</span>
                            </div>
                            <div>
                                <div class="fw-bold small">${escapeHtml(connA)} <i class="fas fa-arrows-alt-h text-primary mx-1"></i> ${escapeHtml(connB)}</div>
                                <div class="text-muted" style="font-size:0.75rem">
                                    Emp. ${escapeHtml(item.company_code || '')}
                                    <span class="ms-2"><i class="fas fa-table me-1"></i>${tablesCompared} tabelas (${tablesWithDiffs} com dif.)</span>
                                    <span class="ms-2"><i class="fas fa-calendar me-1"></i>${dt}</span>
                                    ${duration ? `<span class="ms-2"><i class="fas fa-clock me-1"></i>${duration}</span>` : ''}
                                    ${user ? `<span class="ms-2"><i class="fas fa-user me-1"></i>${escapeHtml(user)}</span>` : ''}
                                </div>
                            </div>
                        </div>
                        <div class="d-flex gap-1">
                            <button class="btn btn-outline-primary btn-sm" data-action="dictViewCompareHistory" data-params='{"id":${item.id}}' title="Visualizar">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" data-action="dictExportCompareCsv" data-params='{"historyId":${item.id}}' title="Exportar CSV">
                                <i class="fas fa-file-csv"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm" data-action="dictDeleteCompareHistory" data-params='{"id":${item.id}}' title="Excluir">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`;
    }

    container.innerHTML = html;
}

async function dictViewCompareHistory(params) {
    const historyId = params?.id;
    if (!historyId) return;

    const container = document.getElementById('db-compare-content');
    if (!container) return;

    container.innerHTML = `
        <div class="d-flex justify-content-center py-5">
            <div class="spinner-border text-primary"></div>
            <span class="ms-3">Carregando resultado...</span>
        </div>`;

    try {
        const resp = await apiRequest(`/dictionary/history/${historyId}`);
        const summary = resp.summary || {};
        const details = resp.details || {};

        // Verificar se este registro é a última comparação executada nesta sessão.
        // Se for, permitir equalização (não é histórico antigo).
        const lastExecHistoryId = dictCompareResult?._historyId;
        const isCurrentCompare = lastExecHistoryId && lastExecHistoryId === historyId;

        dictCompareResult = {
            summary, results: details,
            _connAId: resp.connection_a_id,
            _connBId: resp.connection_b_id,
            _companyCode: resp.company_code,
            _connAName: resp.conn_a_name || '',
            _connBName: resp.conn_b_name || '',
            _historyId: historyId,
            _fromHistory: !isCurrentCompare,
        };
        _dictSaveState('dictCompareResult', dictCompareResult);

        const connA = resp.conn_a_name || `Conexão #${resp.connection_a_id}`;
        const connB = resp.conn_b_name || `Conexão #${resp.connection_b_id}`;
        const dt = resp.executed_at ? _dictFormatDate(resp.executed_at) : '';

        let html = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <button class="btn btn-outline-secondary btn-sm me-2" data-action="dictBackToCompareHistory">
                        <i class="fas fa-arrow-left me-1"></i>Voltar
                    </button>
                    <strong>${escapeHtml(connA)}</strong>
                    <i class="fas fa-arrows-alt-h text-primary mx-2"></i>
                    <strong>${escapeHtml(connB)}</strong>
                    <span class="text-muted ms-2">Emp. ${escapeHtml(resp.company_code || '')}</span>
                    <small class="text-muted ms-2">${dt}</small>
                </div>
                ${dictCompareResult._fromHistory
                    ? `<span class="badge bg-secondary py-2 me-2"><i class="fas fa-lock me-1"></i>Resultado do histórico — execute nova comparação para equalizar</span>`
                    : ''}
                <button class="btn btn-outline-secondary btn-sm" data-action="dictExportCompareCsv" data-params='{"historyId":${historyId}}'>
                    <i class="fas fa-file-csv me-1"></i>Exportar CSV
                </button>
            </div>
            <div id="dict-compare-result"></div>`;

        container.innerHTML = html;
        _dictRenderCompareResult({ summary, results: details });

    } catch (e) {
        container.innerHTML = `
            <div class="mb-3">
                <button class="btn btn-outline-secondary btn-sm" data-action="dictBackToCompareHistory">
                    <i class="fas fa-arrow-left me-1"></i>Voltar
                </button>
            </div>
            <div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i>Erro: ${escapeHtml(e.message)}</div>`;
    }
}

function dictBackToCompareHistory() {
    _renderCompareTab();
}

async function dictDeleteCompareHistory(params) {
    const historyId = params?.id;
    if (!historyId) return;

    if (!confirm('Excluir este registro de comparação?')) return;

    try {
        await apiRequest(`/dictionary/history/${historyId}`, 'DELETE');
        showNotification('Registro excluído.', 'success');
        _dictLoadCompareHistory();
    } catch (e) {
        showNotification('Erro ao excluir: ' + e.message, 'error');
    }
}

async function dictRunCompare() {
    const connA = document.getElementById('dict-conn-a')?.value;
    const connB = document.getElementById('dict-conn-b')?.value;
    const companyA = document.getElementById('dict-company-a')?.value;
    const companyB = document.getElementById('dict-company-b')?.value;

    if (!connA || !connB) {
        showNotification('Selecione as duas conexões.', 'warning');
        return;
    }
    if (!companyA || !companyB) {
        showNotification('Selecione a empresa em ambas as conexões.', 'warning');
        return;
    }
    if (connA === connB && companyA === companyB) {
        showNotification('Selecione conexões ou empresas diferentes para comparar.', 'warning');
        return;
    }

    // Tabelas selecionadas
    const checkedTables = [];
    document.querySelectorAll('.dict-table-check:checked').forEach(chk => checkedTables.push(chk.value));
    if (checkedTables.length === 0) {
        showNotification('Selecione ao menos uma tabela.', 'warning');
        return;
    }

    const btn = document.getElementById('dict-compare-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Comparando...';
    }

    // Estado de running para persistência
    _dictCompareRunning = true;
    _dictCompareProgress = { tables: checkedTables, stepStatuses: {} };

    // Esconder histórico e mostrar progress
    const histDiv = document.getElementById('dict-compare-history');
    if (histDiv) histDiv.classList.add('d-none');
    const progressDiv = document.getElementById('dict-compare-progress');
    if (progressDiv) {
        let stepsHtml = checkedTables.map(t => `
            <div class="d-flex align-items-center mb-1" id="cmp-step-${t}">
                <span class="me-2" style="width:18px;text-align:center"><i class="far fa-circle text-muted" style="font-size:.7rem"></i></span>
                <span class="small fw-bold">${t}</span>
                <span class="ms-auto badge bg-secondary" style="font-size:.65rem">AGUARDANDO</span>
            </div>`).join('');
        progressDiv.innerHTML = `
            <div class="card mb-3"><div class="card-body py-3">
                <h6 class="mb-3"><i class="fas fa-spinner fa-spin me-2"></i>Comparando ${checkedTables.length} tabelas...</h6>
                ${stepsHtml}
            </div></div>`;
        progressDiv.classList.remove('d-none');
    }

    // Simular progresso ciclando pelas tabelas
    let _cmpIdx = 0;
    const _cmpUpdateStep = (table, status, label) => {
        // Salvar status para restauração ao trocar de aba
        if (_dictCompareProgress) {
            _dictCompareProgress.stepStatuses[table] = { status, label: label || (status === 'running' ? 'EXECUTANDO...' : 'OK') };
        }
        const el = document.getElementById(`cmp-step-${table}`);
        if (!el) return;
        const icon = status === 'running' ? '<i class="fas fa-spinner fa-spin text-primary" style="font-size:.7rem"></i>'
            : status === 'done' ? '<i class="fas fa-check-circle text-success" style="font-size:.7rem"></i>'
            : '<i class="fas fa-times-circle text-danger" style="font-size:.7rem"></i>';
        const badge = status === 'running' ? 'bg-primary' : status === 'done' ? 'bg-success' : 'bg-danger';
        el.querySelector('span').innerHTML = icon;
        el.querySelector('.badge').className = `ms-auto badge ${badge}`;
        el.querySelector('.badge').style.fontSize = '.65rem';
        el.querySelector('.badge').textContent = label || (status === 'running' ? 'EXECUTANDO...' : 'OK');
    };
    if (checkedTables.length > 0) _cmpUpdateStep(checkedTables[0], 'running');
    const _cmpInterval = setInterval(() => {
        _cmpIdx++;
        if (_cmpIdx >= checkedTables.length) _cmpIdx = 0;
        // Só atualiza DOM se o elemento existir (aba pode ter trocado)
        for (let i = 0; i < checkedTables.length; i++) {
            const el = document.getElementById(`cmp-step-${checkedTables[i]}`);
            if (!el) continue;
            if (i === _cmpIdx) {
                _cmpUpdateStep(checkedTables[i], 'running');
            } else {
                el.querySelector('span').innerHTML = '<i class="far fa-circle text-muted" style="font-size:.7rem"></i>';
                el.querySelector('.badge').className = 'ms-auto badge bg-secondary';
                el.querySelector('.badge').style.fontSize = '.65rem';
                el.querySelector('.badge').textContent = 'AGUARDANDO';
            }
        }
    }, 600);

    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const includeDeleted = document.getElementById('dict-include-deleted')?.checked || false;
        const resp = await apiRequest('/dictionary/compare', 'POST', {
            conn_id_a: parseInt(connA),
            conn_id_b: parseInt(connB),
            company_code: companyA,
            tables: checkedTables.length < METADATA_TABLES.length ? checkedTables : null,
            alias_filter: document.getElementById('dict-alias-filter')?.value?.trim() || null,
            include_deleted: includeDeleted,
            environment_id: envId ? parseInt(envId) : null,
        });

        clearInterval(_cmpInterval);

        // Animar resultado final por tabela
        const results = resp.results || {};
        for (let i = 0; i < checkedTables.length; i++) {
            const t = checkedTables[i];
            const info = results[t] || results[`${t}${companyA}0`];
            const diffs = info ? (info.only_a?.length || 0) + (info.only_b?.length || 0) + (info.different?.length || 0) : 0;
            _cmpUpdateStep(t, diffs > 0 ? 'error' : 'done', diffs > 0 ? `${diffs} dif.` : 'OK');
            if (i < checkedTables.length - 1) await new Promise(r => setTimeout(r, 60));
        }

        await new Promise(r => setTimeout(r, 1200));

        // Guardar IDs e nomes das conexoes para uso no equalizador
        resp._connAId = parseInt(connA);
        resp._connBId = parseInt(connB);
        resp._companyCode = companyA;
        const _caEl = document.getElementById('dict-conn-a');
        const _cbEl = document.getElementById('dict-conn-b');
        resp._connAName = _caEl ? _caEl.options[_caEl.selectedIndex]?.text : '';
        resp._connBName = _cbEl ? _cbEl.options[_cbEl.selectedIndex]?.text : '';
        // Rastrear o history_id para permitir equalização ao visualizar este resultado no histórico
        resp._historyId = resp.summary?.history_id || null;

        dictCompareResult = resp;
        _dictSaveState('dictCompareResult', resp);

        _dictCompareRunning = false;
        _dictCompareProgress = null;
        if (progressDiv) progressDiv.classList.add('d-none');
        if (histDiv) histDiv.classList.remove('d-none');

        // Recarregar histórico (agora inclui o novo item)
        await _dictLoadCompareHistory();

        showNotification('Comparação concluída!', 'success');

    } catch (e) {
        clearInterval(_cmpInterval);
        _dictCompareRunning = false;
        _dictCompareProgress = null;
        if (progressDiv) {
            progressDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>Erro ao comparar: ${escapeHtml(e.message)}
                </div>`;
        }
        await new Promise(r => setTimeout(r, 3000));
        if (progressDiv) progressDiv.classList.add('d-none');
        if (histDiv) histDiv.classList.remove('d-none');
    } finally {
        const btnRestore = document.getElementById('dict-compare-btn');
        if (btnRestore) {
            btnRestore.disabled = false;
            btnRestore.innerHTML = '<i class="fas fa-search me-1"></i>Comparar';
        }
    }
}

function _dictRenderCompareResult(resp) {
    const resultDiv = document.getElementById('dict-compare-result');
    if (!resultDiv) return;

    const summary = resp.summary || {};
    const results = resp.results || {};

    const tableNames = Object.keys(results).sort();
    if (tableNames.length === 0) {
        resultDiv.innerHTML = '<div class="alert alert-info">Nenhuma tabela comparada.</div>';
        return;
    }

    const summaryColor = summary.tables_with_diffs > 0 ? 'warning' : 'success';
    const summaryIcon = summary.tables_with_diffs > 0 ? 'fa-exclamation-triangle' : 'fa-check-circle';

    // Contar itens equalizaveis (only_a + only_b + different de todas as tabelas)
    let _eqCount = 0;
    for (const tn of tableNames) {
        const inf = results[tn];
        _eqCount += (inf.only_a || []).length + (inf.only_b || []).length;
        _eqCount += (inf.different || []).length;
    }

    let html = `
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-${summaryColor} fs-6 me-2">
                            <i class="fas ${summaryIcon} me-1"></i>
                            ${summary.tables_compared} tabelas | ${summary.tables_with_diffs} com diferenças | ${summary.total_diffs} divergência(s)
                        </span>
                        <small class="text-muted ms-2">${summary.duration_ms}ms</small>
                    </div>
                    ${_eqCount > 0 && !dictCompareResult?._fromHistory
                        ? `<button class="btn btn-warning btn-sm" onclick="dbSwitchTab('equalize')">
                            <i class="fas fa-sync me-1"></i>Equalização (${_eqCount}) <i class="fas fa-arrow-right ms-1"></i>
                          </button>`
                        : _eqCount > 0 && dictCompareResult?._fromHistory
                            ? `<span class="badge bg-secondary"><i class="fas fa-lock me-1"></i>Resultado do histórico — execute nova comparação para equalizar</span>`
                            : ''}
                </div>
            </div>
        </div>`;

    html += `<div class="table-responsive"><table class="table table-sm table-hover">
        <thead><tr>
            <th>Tabela</th><th>Prefixo</th><th class="text-center">Base A</th><th class="text-center">Base B</th>
            <th class="text-center">Apenas A</th><th class="text-center">Apenas B</th><th class="text-center">Diferentes</th><th>Status</th>
        </tr></thead><tbody>`;

    for (const tname of tableNames) {
        const info = results[tname];
        const onlyA = (info.only_a || []).length;
        const onlyB = (info.only_b || []).length;
        const diffs = (info.different || []).length;
        const hasDiffs = onlyA > 0 || onlyB > 0 || diffs > 0;
        const hasError = !!info.error;

        let statusBadge;
        if (hasError) {
            statusBadge = `<span class="badge bg-secondary"><i class="fas fa-minus me-1"></i>${escapeHtml(info.error)}</span>`;
        } else if (hasDiffs) {
            statusBadge = `<span class="badge bg-danger"><i class="fas fa-times me-1"></i>${onlyA + onlyB + diffs} divergência(s)</span>`;
        } else {
            statusBadge = `<span class="badge bg-success"><i class="fas fa-check me-1"></i>OK</span>`;
        }

        html += `<tr class="${hasDiffs ? 'table-warning' : ''}" style="cursor:${hasDiffs ? 'pointer' : 'default'}"
                     ${hasDiffs ? `data-action="dictToggleCompareDetail" data-params='{"table":"${escapeHtml(tname)}"}'` : ''}>
            <td class="fw-bold">${escapeHtml(tname)}</td>
            <td><small class="text-muted">${escapeHtml(info.prefix || '')}</small></td>
            <td class="text-center">${info.total_a}</td>
            <td class="text-center">${info.total_b}</td>
            <td class="text-center">${onlyA > 0 ? `<span class="text-danger fw-bold">${onlyA}</span>` : '-'}</td>
            <td class="text-center">${onlyB > 0 ? `<span class="text-danger fw-bold">${onlyB}</span>` : '-'}</td>
            <td class="text-center">${diffs > 0 ? `<span class="text-warning fw-bold">${diffs}</span>` : '-'}</td>
            <td>${statusBadge}</td>
        </tr>
        <tr class="d-none" id="dict-detail-${escapeHtml(tname)}"><td colspan="8" class="p-0"><div class="p-3 bg-light"></div></td></tr>`;
    }

    html += '</tbody></table></div>';
    resultDiv.innerHTML = html;
}

function dictToggleCompareDetail(params) {
    const tname = params.table;
    const detailRow = document.getElementById(`dict-detail-${tname}`);
    if (!detailRow) return;

    if (!detailRow.classList.contains('d-none')) {
        detailRow.classList.add('d-none');
        return;
    }

    // Preencher detalhes
    const info = (dictCompareResult?.results || {})[tname];
    if (!info) return;

    let detailHtml = '';

    if ((info.only_a || []).length > 0) {
        detailHtml += `<h6 class="text-danger"><i class="fas fa-arrow-left me-1"></i>Apenas na Base A (${info.only_a.length})</h6>
            <div class="mb-3" style="max-height:200px;overflow-y:auto">
            <table class="table table-sm table-bordered mb-0"><thead><tr><th>Chave</th></tr></thead><tbody>`;
        for (const item of info.only_a.slice(0, 100)) {
            detailHtml += `<tr><td><code>${escapeHtml(item.key)}</code></td></tr>`;
        }
        if (info.only_a.length > 100) detailHtml += `<tr><td class="text-muted">... e mais ${info.only_a.length - 100}</td></tr>`;
        detailHtml += '</tbody></table></div>';
    }

    if ((info.only_b || []).length > 0) {
        detailHtml += `<h6 class="text-primary"><i class="fas fa-arrow-right me-1"></i>Apenas na Base B (${info.only_b.length})</h6>
            <div class="mb-3" style="max-height:200px;overflow-y:auto">
            <table class="table table-sm table-bordered mb-0"><thead><tr><th>Chave</th></tr></thead><tbody>`;
        for (const item of info.only_b.slice(0, 100)) {
            detailHtml += `<tr><td><code>${escapeHtml(item.key)}</code></td></tr>`;
        }
        if (info.only_b.length > 100) detailHtml += `<tr><td class="text-muted">... e mais ${info.only_b.length - 100}</td></tr>`;
        detailHtml += '</tbody></table></div>';
    }

    if ((info.different || []).length > 0) {
        detailHtml += `<h6 class="text-warning"><i class="fas fa-exchange-alt me-1"></i>Registros Diferentes (${info.different.length})</h6>
            <div style="max-height:300px;overflow-y:auto">
            <table class="table table-sm table-bordered mb-0"><thead><tr><th>Chave</th><th>Campo</th><th>Valor A</th><th>Valor B</th></tr></thead><tbody>`;
        let shown = 0;
        for (const item of info.different) {
            for (const f of item.fields) {
                if (shown >= 200) break;
                detailHtml += `<tr>
                    <td><code>${escapeHtml(item.key)}</code></td>
                    <td>${escapeHtml(f.field)}</td>
                    <td><small>${escapeHtml(String(f.val_a))}</small></td>
                    <td><small>${escapeHtml(String(f.val_b))}</small></td>
                </tr>`;
                shown++;
            }
            if (shown >= 200) break;
        }
        const totalFields = info.different.reduce((acc, d) => acc + d.fields.length, 0);
        if (totalFields > 200) detailHtml += `<tr><td colspan="4" class="text-muted">... e mais ${totalFields - 200} diferenças</td></tr>`;
        detailHtml += '</tbody></table></div>';
    }

    if (!detailHtml) detailHtml = '<p class="text-muted">Sem detalhes disponíveis.</p>';

    detailRow.querySelector('div').innerHTML = detailHtml;
    detailRow.classList.remove('d-none');
}

function dictToggleAllTables() {
    const allCheck = document.getElementById('dict-chk-all');
    const checked = allCheck?.checked ?? true;
    document.querySelectorAll('.dict-table-check').forEach(chk => { chk.checked = checked; });
}

function _dictSyncAllTablesCheckbox() {
    const allCheck = document.getElementById('dict-chk-all');
    if (!allCheck) return;
    const all = document.querySelectorAll('.dict-table-check');
    const checked = document.querySelectorAll('.dict-table-check:checked');
    allCheck.checked = all.length > 0 && all.length === checked.length;
}

async function dictExportCompareCsv(params) {
    const historyId = params?.historyId;
    if (!historyId) return;
    try {
        const response = await apiDownload(`/dictionary/export/compare/${historyId}`);
        const blob = await response.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `compare_${historyId}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (e) {
        showNotification('Erro ao exportar CSV: ' + e.message, 'error');
    }
}


// =====================================================================
// ABA: INTEGRIDADE
// =====================================================================

const INTEGRITY_LAYERS = {
    'sx2_schema':        { label: 'SX2 vs Schema (tabelas)',       icon: 'fa-table',            desc: 'Tabelas do dicionário vs tabelas físicas' },
    'sx3_schema':        { label: 'SX3 vs Schema (campos)',        icon: 'fa-columns',          desc: 'Campos do dicionário vs colunas físicas' },
    'sx3_topfield':      { label: 'SX3 vs TOP_FIELD',              icon: 'fa-exchange-alt',     desc: 'Campos D/N/M vs registros TOP_FIELD' },
    'six_indexes':       { label: 'SIX vs Indices Fisicos',        icon: 'fa-key',              desc: 'Indices do dicionário vs indices físicos' },
    'schema_sx3':        { label: 'Schema vs SX3 (campos orfaos)', icon: 'fa-unlink',           desc: 'Colunas físicas sem definição no SX3' },
    'sx3_field_size':    { label: 'SX3 vs Schema (tamanhos)',      icon: 'fa-ruler',            desc: 'Tamanho dos campos SX3 vs tamanho físico' },
    'virtual_in_schema': { label: 'Campos virtuais na base',       icon: 'fa-ghost',            desc: 'Campos virtuais que existem na tabela física' },
    'sx2_unique_fields': { label: 'Chave unica SX2 sem SX3',      icon: 'fa-fingerprint',      desc: 'Campos da chave única SX2 sem definição SX3' },
    'sx2_unique_virtual':{ label: 'Chave unica SX2 com virtual',  icon: 'fa-eye-slash',        desc: 'Campos virtuais usados em chave única SX2' },
    'sx2_no_sx3':        { label: 'SX2 sem estrutura SX3',        icon: 'fa-table',            desc: 'Tabelas SX2 sem campos definidos no SX3' },
    'sx3_no_sx2':        { label: 'SX3 sem definicao SX2',        icon: 'fa-columns',          desc: 'Campos SX3 sem tabela correspondente no SX2' },
    'sx2_no_six':        { label: 'SX2 sem indice SIX',           icon: 'fa-ban',              desc: 'Tabelas SX2 sem nenhum indice no SIX' },
    'six_no_sx2':        { label: 'SIX sem tabela SX2',           icon: 'fa-question-circle',  desc: 'Indices SIX para tabelas inexistentes no SX2' },
    'six_fields_sx3':    { label: 'Campos de indice sem SX3',     icon: 'fa-search',           desc: 'Campos usados em indices sem definição SX3' },
    'six_virtual_memo':  { label: 'Virtual/Memo em indice',       icon: 'fa-exclamation',      desc: 'Campos virtuais ou memo usados em indices' },
    'duplicates':        { label: 'Registros duplicados',         icon: 'fa-clone',            desc: 'Registros duplicados nos dicionários' },
    'sx2_sharing':       { label: 'Compartilhamento SX2',         icon: 'fa-share-alt',        desc: 'Verificação do modo de compartilhamento SX2' },
    'sx3_ref_sxg':       { label: 'Ref. grupo SXG inexistente',   icon: 'fa-layer-group',      desc: 'Campos SX3 referenciando grupos SXG inexistentes' },
    'sx3_ref_sxa':       { label: 'Ref. pasta SXA inexistente',   icon: 'fa-folder-open',      desc: 'Campos SX3 referenciando pastas SXA inexistentes' },
    'sx3_ref_sxb':       { label: 'Ref. consulta SXB inexistente',icon: 'fa-search-plus',      desc: 'Campos SX3 referenciando consultas SXB inexistentes' },
};

// Estado local: validação em progresso
let _dictValidateRunning = false;
let _dictValidateProgress = null; // {layers, stepStatuses}

function _renderIntegrityTab() {
    const container = document.getElementById('db-integrity-content');
    if (!container) return;

    if (dbConnections.length === 0) {
        container.innerHTML = `
            <div class="card text-center p-5">
                <i class="fas fa-shield-alt fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">Nenhuma conexão cadastrada</h5>
                <p class="text-muted small">Cadastre uma conexão de banco de dados para validar a integridade do dicionário.</p>
            </div>`;
        return;
    }

    const connOptions = dbConnections.map(c => `<option value="${c.id}">${escapeHtml(c.name)} (${c.host}/${c.database_name})</option>`).join('');

    const layerChecks = Object.entries(INTEGRITY_LAYERS).map(([key, meta]) =>
        `<div class="form-check form-check-inline">
            <input class="form-check-input integ-layer-check" type="checkbox" value="${key}" id="integ-chk-${key}" checked onchange="_dictSyncAllLayersCheckbox()">
            <label class="form-check-label small" for="integ-chk-${key}">
                <i class="fas ${meta.icon} me-1"></i>${meta.label}
            </label>
        </div>`
    ).join('');

    container.innerHTML = `
        <div class="card mb-3">
            <div class="card-body">
                <h6 class="card-title"><i class="fas fa-shield-alt me-2"></i>Validar Integridade do Dicionário</h6>
                <p class="text-muted small mb-3">Verifica a consistência entre metadados Protheus (SX2, SX3, SIX) e o schema físico do banco, incluindo TOP_FIELD.</p>

                <div class="row g-3 align-items-end">
                    <div class="col-md-4">
                        <label class="form-label small fw-bold">Conexão</label>
                        <select class="form-select form-select-sm" id="dict-integ-conn">${connOptions}</select>
                    </div>
                    <div class="col-md-3">
                        <label class="form-label small fw-bold">Empresa</label>
                        <select class="form-select form-select-sm" id="dict-integ-company">
                            <option value="">Selecione conexão...</option>
                        </select>
                    </div>
                </div>

                <div class="mt-3">
                    <label class="form-label small fw-bold">Verificações:</label>
                    <div class="d-flex flex-wrap gap-1 align-items-center">
                        <div class="form-check form-check-inline">
                            <input class="form-check-input" type="checkbox" id="integ-chk-all" checked onchange="dictToggleAllLayers()">
                            <label class="form-check-label small fw-bold" for="integ-chk-all">Todas</label>
                        </div>
                        ${layerChecks}
                    </div>
                </div>

                <div class="mt-3">
                    <button class="btn btn-primary btn-sm" data-action="dictRunValidate" id="dict-validate-btn"
                        ${_dictValidateRunning ? 'disabled' : ''}>
                        ${_dictValidateRunning
                            ? '<i class="fas fa-spinner fa-spin me-1"></i>Validando...'
                            : '<i class="fas fa-check-double me-1"></i>Validar'}
                    </button>
                </div>
            </div>
        </div>

        <!-- Progress steps (visível durante validação ou com status salvo) -->
        <div id="dict-integrity-progress" class="${_dictValidateRunning ? '' : 'd-none'}"></div>

        <!-- Histórico de validações -->
        <div id="dict-integrity-history">
            <div class="d-flex justify-content-center py-3">
                <div class="spinner-border spinner-border-sm text-muted"></div>
                <span class="text-muted ms-2 small">Carregando histórico...</span>
            </div>
        </div>
    `;

    // Carregar empresas ao mudar conexão
    const connEl = document.getElementById('dict-integ-conn');
    if (connEl) {
        connEl.addEventListener('change', () => _dictLoadCompanies(connEl.value, document.getElementById('dict-integ-company')));
        _dictLoadCompanies(connEl.value, document.getElementById('dict-integ-company'));
    }

    // Restaurar progress se estiver rodando
    if (_dictValidateRunning && _dictValidateProgress) {
        _dictShowProgress(_dictValidateProgress.layers);
        for (const [k, v] of Object.entries(_dictValidateProgress.stepStatuses || {})) {
            _dictUpdateStep(k, v.status, v.detail);
        }
    }

    // Carregar histórico
    _dictLoadHistory();
}

async function _dictLoadHistory() {
    const histDiv = document.getElementById('dict-integrity-history');
    if (!histDiv) return;

    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const resp = await apiRequest(`/dictionary/history?environment_id=${envId || ''}&limit=20`);
        const items = (resp.history || []).filter(h => h.operation_type === 'validate');
        _dictRenderHistoryList(histDiv, items);
    } catch (e) {
        histDiv.innerHTML = `<div class="alert alert-warning small"><i class="fas fa-exclamation-triangle me-1"></i>Erro ao carregar histórico: ${escapeHtml(e.message)}</div>`;
    }
}

function _dictRenderHistoryList(container, items) {
    if (items.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-3">
                <i class="fas fa-history fa-2x mb-2 d-block opacity-50"></i>
                <small>Nenhuma validação realizada ainda.</small>
            </div>`;
        return;
    }

    let html = '<h6 class="mb-3"><i class="fas fa-history me-2"></i>Histórico de Validações</h6>';
    for (const item of items) {
        const summary = item.summary || {};
        const checks = summary.checks || {};
        const totalChecks = Object.keys(checks).length;
        const checksOk = Object.values(checks).filter(c => c.issues === 0 && !c.has_error).length;
        const color = checksOk === totalChecks ? 'success' : (checksOk >= totalChecks / 2 ? 'warning' : 'danger');
        const icon = checksOk === totalChecks ? 'fa-check-circle' : 'fa-exclamation-triangle';

        const connName = item.conn_a_name || `Conexão #${item.connection_a_id}`;
        const dt = item.executed_at ? _dictFormatDate(item.executed_at) : '---';
        const duration = summary.duration_ms ? `${(summary.duration_ms / 1000).toFixed(1)}s` : '';
        const user = item.executed_by_name || '';

        // Layers badges (suporta N camadas dinamicamente)
        let layersBadges = '';
        for (const [k, v] of Object.entries(checks)) {
            const meta = INTEGRITY_LAYERS[k] || { label: k, icon: 'fa-cog' };
            const lColor = v.issues > 0 ? 'danger' : (v.has_error ? 'secondary' : 'success');
            layersBadges += `<span class="badge bg-${lColor} me-1" title="${meta.label}"><i class="fas ${meta.icon} me-1"></i>${v.issues > 0 ? v.issues : 'OK'}</span>`;
        }

        html += `
            <div class="card mb-2">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center gap-3">
                            <div>
                                <span class="badge bg-${color}"><i class="fas ${icon} me-1"></i>${checksOk}/${totalChecks} OK</span>
                            </div>
                            <div>
                                <div class="fw-bold small">${escapeHtml(connName)} - Emp. ${escapeHtml(item.company_code || '')}</div>
                                <div class="text-muted" style="font-size:0.75rem">
                                    <i class="fas fa-calendar me-1"></i>${dt}
                                    ${duration ? `<span class="ms-2"><i class="fas fa-clock me-1"></i>${duration}</span>` : ''}
                                    ${user ? `<span class="ms-2"><i class="fas fa-user me-1"></i>${escapeHtml(user)}</span>` : ''}
                                </div>
                            </div>
                            <div>${layersBadges}</div>
                        </div>
                        <div class="d-flex gap-1">
                            <button class="btn btn-outline-primary btn-sm" data-action="dictViewHistory" data-params='{"id":${item.id}}' title="Visualizar">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" data-action="dictExportValidateCsv" data-params='{"historyId":${item.id}}' title="Exportar CSV">
                                <i class="fas fa-file-csv"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm" data-action="dictDeleteHistory" data-params='{"id":${item.id}}' title="Excluir">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`;
    }

    container.innerHTML = html;
}

function _dictFormatDate(isoString) {
    try {
        return new Date(isoString).toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch { return isoString; }
}

async function dictViewHistory(params) {
    const historyId = params?.id;
    if (!historyId) return;

    const container = document.getElementById('db-integrity-content');
    if (!container) return;

    container.innerHTML = `
        <div class="d-flex justify-content-center py-5">
            <div class="spinner-border text-primary"></div>
            <span class="ms-3">Carregando resultado...</span>
        </div>`;

    try {
        const resp = await apiRequest(`/dictionary/history/${historyId}`);
        const summary = resp.summary || {};
        const details = resp.details || {};

        // Montar formato compativel com _dictRenderIntegrityResult
        dictIntegrityResult = { summary, results: details };
        _dictSaveState('dictIntegrityResult', dictIntegrityResult);

        // Renderizar view de detalhes
        const connName = resp.conn_a_name || `Conexão #${resp.connection_a_id}`;
        const dt = resp.executed_at ? _dictFormatDate(resp.executed_at) : '';

        let html = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <button class="btn btn-outline-secondary btn-sm me-2" data-action="dictBackToHistory">
                        <i class="fas fa-arrow-left me-1"></i>Voltar
                    </button>
                    <strong>${escapeHtml(connName)}</strong>
                    <span class="text-muted ms-2">Emp. ${escapeHtml(resp.company_code || '')}</span>
                    <small class="text-muted ms-2">${dt}</small>
                </div>
                <button class="btn btn-outline-secondary btn-sm" data-action="dictExportValidateCsv" data-params='{"historyId":${historyId}}'>
                    <i class="fas fa-file-csv me-1"></i>Exportar CSV
                </button>
            </div>
            <div id="dict-integrity-result"></div>`;

        container.innerHTML = html;
        _dictRenderIntegrityResult({ summary, results: details });

    } catch (e) {
        container.innerHTML = `
            <div class="mb-3">
                <button class="btn btn-outline-secondary btn-sm" data-action="dictBackToHistory">
                    <i class="fas fa-arrow-left me-1"></i>Voltar
                </button>
            </div>
            <div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i>Erro: ${escapeHtml(e.message)}</div>`;
    }
}

function dictBackToHistory() {
    _renderIntegrityTab();
}

async function dictDeleteHistory(params) {
    const historyId = params?.id;
    if (!historyId) return;

    if (!confirm('Excluir este registro de validação?')) return;

    try {
        await apiRequest(`/dictionary/history/${historyId}`, 'DELETE');
        showNotification('Registro excluído.', 'success');
        _dictLoadHistory();
    } catch (e) {
        showNotification('Erro ao excluir: ' + e.message, 'error');
    }
}

function dictToggleAllLayers() {
    const allCheck = document.getElementById('integ-chk-all');
    const checked = allCheck?.checked ?? true;
    document.querySelectorAll('.integ-layer-check').forEach(chk => { chk.checked = checked; });
}

function _dictSyncAllLayersCheckbox() {
    const allCheck = document.getElementById('integ-chk-all');
    if (!allCheck) return;
    const all = document.querySelectorAll('.integ-layer-check');
    const checked = document.querySelectorAll('.integ-layer-check:checked');
    allCheck.checked = all.length > 0 && all.length === checked.length;
}

function _dictShowProgress(layers) {
    const container = document.getElementById('dict-integrity-progress');
    if (!container) return;

    let html = '<div class="card mb-3"><div class="card-body py-3">';
    html += '<h6 class="mb-3"><i class="fas fa-spinner fa-spin me-2"></i>Validando integridade...</h6>';
    for (const key of layers) {
        const meta = INTEGRITY_LAYERS[key] || { label: key, icon: 'fa-cog', desc: '' };
        html += `<div class="d-flex align-items-center mb-2" id="integ-step-${key}">
            <div class="me-3" style="width:24px;text-align:center">
                <i class="fas fa-circle-notch fa-spin text-muted" id="integ-step-icon-${key}"></i>
            </div>
            <div>
                <span class="fw-bold">${meta.label}</span>
                <small class="text-muted ms-2">${meta.desc}</small>
            </div>
            <div class="ms-auto" id="integ-step-status-${key}">
                <span class="badge bg-light text-muted">Aguardando</span>
            </div>
        </div>`;
    }
    html += '</div></div>';
    container.innerHTML = html;
    container.classList.remove('d-none');
}

function _dictUpdateStep(key, status, detail) {
    const icon = document.getElementById(`integ-step-icon-${key}`);
    const statusEl = document.getElementById(`integ-step-status-${key}`);
    if (!icon || !statusEl) return;

    // Salvar estado para restauração
    if (_dictValidateProgress) {
        if (!_dictValidateProgress.stepStatuses) _dictValidateProgress.stepStatuses = {};
        _dictValidateProgress.stepStatuses[key] = { status, detail };
    }

    if (status === 'pending') {
        icon.className = 'far fa-circle text-muted';
        statusEl.innerHTML = '<span class="badge bg-secondary" style="font-size:.65rem">AGUARDANDO</span>';
        return;
    } else if (status === 'running') {
        icon.className = 'fas fa-spinner fa-spin text-primary';
        statusEl.innerHTML = '<span class="badge bg-primary" style="font-size:.65rem">EXECUTANDO...</span>';
    } else if (status === 'done') {
        icon.className = 'fas fa-check-circle text-success';
        statusEl.innerHTML = `<span class="badge bg-success">${escapeHtml(detail || 'OK')}</span>`;
    } else if (status === 'error') {
        icon.className = 'fas fa-times-circle text-danger';
        statusEl.innerHTML = `<span class="badge bg-danger">${escapeHtml(detail || 'Erro')}</span>`;
    } else if (status === 'warning') {
        icon.className = 'fas fa-exclamation-triangle text-warning';
        statusEl.innerHTML = `<span class="badge bg-warning text-dark">${escapeHtml(detail || 'Problemas')}</span>`;
    }
}

async function dictRunValidate() {
    const connId = document.getElementById('dict-integ-conn')?.value;
    const company = document.getElementById('dict-integ-company')?.value;

    if (!connId) {
        showNotification('Selecione uma conexão.', 'warning');
        return;
    }
    if (!company) {
        showNotification('Selecione a empresa.', 'warning');
        return;
    }

    // Camadas selecionadas
    const selectedLayers = [];
    document.querySelectorAll('.integ-layer-check:checked').forEach(chk => selectedLayers.push(chk.value));
    if (selectedLayers.length === 0) {
        showNotification('Selecione ao menos uma verificação.', 'warning');
        return;
    }

    const btn = document.getElementById('dict-validate-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Validando...';
    }

    // Estado de running para persistência
    _dictValidateRunning = true;
    _dictValidateProgress = { layers: selectedLayers, stepStatuses: {} };

    // Esconder histórico e mostrar progress
    const histDiv = document.getElementById('dict-integrity-history');
    if (histDiv) histDiv.classList.add('d-none');
    _dictShowProgress(selectedLayers);

    // Ciclar spinner pelas camadas durante a espera (sem marcar resultado)
    let _progressIdx = 0;
    _dictUpdateStep(selectedLayers[0], 'running');
    const _progressInterval = setInterval(() => {
        _progressIdx++;
        if (_progressIdx >= selectedLayers.length) _progressIdx = 0;
        // Resetar todas para aguardando, marcar apenas a atual como running
        for (let i = 0; i < selectedLayers.length; i++) {
            if (i === _progressIdx) {
                _dictUpdateStep(selectedLayers[i], 'running');
            } else {
                _dictUpdateStep(selectedLayers[i], 'pending');
            }
        }
    }, 600);

    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const resp = await apiRequest('/dictionary/validate', 'POST', {
            connection_id: parseInt(connId),
            company_code: company,
            layers: selectedLayers,
            environment_id: envId ? parseInt(envId) : null,
        });

        // Parar simulação de progresso
        clearInterval(_progressInterval);

        // Atualizar steps com resultado real (animar sequencialmente)
        const checks = resp.summary?.checks || {};
        for (let i = 0; i < selectedLayers.length; i++) {
            const key = selectedLayers[i];
            const check = checks[key];
            if (!check) {
                _dictUpdateStep(key, 'done', 'OK');
            } else if (check.has_error) {
                _dictUpdateStep(key, 'error', 'Erro');
            } else if (check.issues > 0) {
                _dictUpdateStep(key, 'warning', `${check.issues} problema(s)`);
            } else {
                _dictUpdateStep(key, 'done', `${check.ok} OK`);
            }
            if (i < selectedLayers.length - 1) {
                await new Promise(r => setTimeout(r, 80));
            }
        }

        // Aguardar para o user ver o resultado final
        await new Promise(r => setTimeout(r, 1200));

        dictIntegrityResult = resp;
        _dictSaveState('dictIntegrityResult', resp);

        // Esconder progress, mostrar histórico atualizado
        _dictValidateRunning = false;
        _dictValidateProgress = null;
        const progressDiv = document.getElementById('dict-integrity-progress');
        if (progressDiv) progressDiv.classList.add('d-none');
        if (histDiv) histDiv.classList.remove('d-none');

        // Recarregar histórico (agora inclui o novo item)
        await _dictLoadHistory();

        showNotification('Validação concluída!', 'success');

    } catch (e) {
        clearInterval(_progressInterval);
        // Marcar todas como erro
        for (const key of selectedLayers) {
            _dictUpdateStep(key, 'error', 'Falha');
        }
        _dictValidateRunning = false;
        _dictValidateProgress = null;

        // Aguardar para o user ver o erro, depois restaurar
        await new Promise(r => setTimeout(r, 2000));
        const progressDiv = document.getElementById('dict-integrity-progress');
        if (progressDiv) progressDiv.classList.add('d-none');
        if (histDiv) histDiv.classList.remove('d-none');

        showNotification('Erro ao validar: ' + e.message, 'error');
    } finally {
        const btnRestore = document.getElementById('dict-validate-btn');
        if (btnRestore) {
            btnRestore.disabled = false;
            btnRestore.innerHTML = '<i class="fas fa-check-double me-1"></i>Validar';
        }
    }
}

function _dictRenderIntegrityResult(resp) {
    const resultDiv = document.getElementById('dict-integrity-result');
    if (!resultDiv) return;

    const summary = resp.summary || {};
    const results = resp.results || {};
    const checks = summary.checks || {};

    const totalChecks = Object.keys(checks).length;
    const checksOk = Object.values(checks).filter(c => c.issues === 0 && !c.has_error).length;
    const summaryColor = checksOk === totalChecks ? 'success' : (checksOk >= totalChecks / 2 ? 'warning' : 'danger');

    let html = `
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="badge bg-${summaryColor} fs-6 me-2">
                            <i class="fas ${checksOk === totalChecks ? 'fa-check-circle' : 'fa-exclamation-triangle'} me-1"></i>
                            ${checksOk} de ${totalChecks} verificações OK | ${summary.total_issues} problema(s) encontrado(s)
                        </span>
                        <small class="text-muted ms-2">${summary.duration_ms}ms</small>
                    </div>
                </div>
            </div>
        </div>`;

    // Iterar TODAS as camadas presentes no resultado (suporta N camadas dinamicamente)
    const allLayerKeys = Object.keys(results);
    for (const layerKey of allLayerKeys) {
        const meta = INTEGRITY_LAYERS[layerKey] || { label: layerKey, icon: 'fa-cog', desc: '' };
        const layerResult = results[layerKey] || {};
        if (!layerResult || Object.keys(layerResult).length === 0) continue;

        const check = checks[layerKey] || {};
        const hasIssues = check.issues > 0;
        const hasError = !!layerResult.error;
        const total = layerResult.total || (check.ok + (check.issues || 0));
        const skipped = layerResult.skipped || 0;
        const virtualSkipped = layerResult.virtual_skipped || 0;
        const totalBypass = skipped + virtualSkipped;

        let statusBadge;
        if (hasError) {
            statusBadge = `<span class="badge bg-secondary"><i class="fas fa-minus me-1"></i>${escapeHtml(layerResult.error)}</span>`;
        } else if (hasIssues) {
            statusBadge = `<span class="badge bg-danger"><i class="fas fa-times me-1"></i>${check.issues} problema(s)</span>`;
        } else {
            statusBadge = `<span class="badge bg-success"><i class="fas fa-check me-1"></i>OK</span>`;
        }

        let bypassParts = [];
        if (skipped > 0) bypassParts.push(`${skipped} tabelas`);
        if (virtualSkipped > 0) bypassParts.push(`${virtualSkipped} virtuais`);
        const skippedInfo = totalBypass > 0 ? `<span class="badge bg-light text-muted ms-1" title="Bypass: ${bypassParts.join(', ')}">${totalBypass} BYPASS</span>` : '';

        html += `
            <div class="card mb-2">
                <div class="card-header d-flex justify-content-between align-items-center py-2"
                     style="cursor:pointer"
                     data-action="dictToggleIntegrityDetail" data-params='{"layer":"${layerKey}"}'>
                    <div>
                        <i class="fas ${meta.icon} me-2"></i>
                        <strong>${meta.label}</strong>
                        <small class="text-muted ms-2">${meta.desc}</small>
                    </div>
                    <div class="d-flex align-items-center gap-2">
                        <span>${check.ok || 0}/${total}</span>
                        ${skippedInfo}
                        ${statusBadge}
                        <i class="fas fa-chevron-down text-muted"></i>
                    </div>
                </div>
                <div class="card-body d-none p-0" id="dict-integ-detail-${layerKey}">
                    <!-- Preenchido ao expandir -->
                </div>
            </div>`;
    }

    resultDiv.innerHTML = html;
}

function dictToggleIntegrityDetail(params) {
    const layerKey = params.layer;
    const detailDiv = document.getElementById(`dict-integ-detail-${layerKey}`);
    if (!detailDiv) return;

    if (!detailDiv.classList.contains('d-none')) {
        detailDiv.classList.add('d-none');
        return;
    }

    const layerResult = (dictIntegrityResult?.results || {})[layerKey] || {};
    let html = '<div class="p-3" style="max-height:400px;overflow-y:auto">';

    // Chaves que nao sao listas de issues
    const skipKeys = ['ok', 'total', 'skipped', 'virtual_skipped', 'error', 'existing_tables'];

    // Coletar todas as listas de issues desta camada
    const issueLists = [];
    for (const [key, val] of Object.entries(layerResult)) {
        if (Array.isArray(val) && !skipKeys.includes(key) && val.length > 0) {
            issueLists.push({ key, items: val });
        }
    }

    if (issueLists.length === 0) {
        html += '<p class="text-muted small mb-0">Nenhum problema encontrado nesta camada.</p>';
    } else {
        for (const { key, items } of issueLists) {
            const maxShow = 200;
            html += `<h6 class="text-danger mb-2">${escapeHtml(key)} (${items.length})</h6>`;

            // Descobrir colunas dinamicamente a partir do primeiro item
            const sampleKeys = Object.keys(items[0]).filter(k => typeof items[0][k] !== 'object' || items[0][k] === null);
            const objKeys = Object.keys(items[0]).filter(k => typeof items[0][k] === 'object' && items[0][k] !== null);

            // Detectar se é o padrão actual/expected → duas colunas separadas
            const hasActualExpected = objKeys.includes('actual') && objKeys.includes('expected');
            const otherObjKeys = objKeys.filter(k => k !== 'actual' && k !== 'expected');

            html += '<table class="table table-sm table-bordered mb-3"><thead><tr>';
            for (const col of sampleKeys) html += `<th>${escapeHtml(col.toUpperCase())}</th>`;
            if (hasActualExpected) {
                html += '<th class="text-warning">TOP_FIELD (atual)</th>';
                html += '<th class="text-info">SX3 (esperado)</th>';
            }
            if (otherObjKeys.length > 0) html += '<th>Detalhe</th>';
            html += '</tr></thead><tbody>';

            const _fmtTopField = (ov) => {
                if (!ov || typeof ov !== 'object') return '';
                const parts = [];
                if (ov.type !== undefined && ov.type !== '') parts.push(`Tipo: <strong>${escapeHtml(String(ov.type))}</strong>`);
                if (ov.prec !== undefined && ov.prec !== '') parts.push(`Precisão: <strong>${escapeHtml(String(ov.prec))}</strong>`);
                if (ov.dec  !== undefined && ov.dec  !== '') parts.push(`Decimais: <strong>${escapeHtml(String(ov.dec))}</strong>`);
                return parts.join('<br>');
            };

            for (const item of items.slice(0, maxShow)) {
                html += '<tr>';
                for (const col of sampleKeys) {
                    const v = item[col];
                    html += `<td><small>${escapeHtml(String(v ?? ''))}</small></td>`;
                }
                if (hasActualExpected) {
                    html += `<td><small class="text-warning">${_fmtTopField(item.actual)}</small></td>`;
                    html += `<td><small class="text-info">${_fmtTopField(item.expected)}</small></td>`;
                }
                if (otherObjKeys.length > 0) {
                    const parts = [];
                    for (const ok of otherObjKeys) {
                        const ov = item[ok];
                        if (ov) parts.push(`${ok}: ${JSON.stringify(ov)}`);
                    }
                    html += `<td><small>${escapeHtml(parts.join('; '))}</small></td>`;
                }
                html += '</tr>';
            }
            if (items.length > maxShow) {
                const colspan = sampleKeys.length + (hasActualExpected ? 2 : 0) + (otherObjKeys.length > 0 ? 1 : 0);
                html += `<tr><td colspan="${colspan}" class="text-muted">... e mais ${items.length - maxShow}</td></tr>`;
            }
            html += '</tbody></table>';
        }
    }

    html += '</div>';
    detailDiv.innerHTML = html;
    detailDiv.classList.remove('d-none');
}

async function dictExportValidateCsv(params) {
    const historyId = params?.historyId;
    if (!historyId) return;
    try {
        const response = await apiDownload(`/dictionary/export/validate/${historyId}`);
        const blob = await response.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `integrity_${historyId}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (e) {
        showNotification('Erro ao exportar CSV: ' + e.message, 'error');
    }
}


// =====================================================================
// EQUALIZADOR DE DICIONARIO
// =====================================================================

// Estado do equalizador
let _eqItems = [];       // itens selecionaveis [{type, checked, label, ...}]
let _eqDirection = 'a2b'; // 'a2b' ou 'b2a'
let _eqPreviewData = null; // resultado do preview
let _eqConnA = null;
let _eqConnB = null;
let _eqCompanyCode = null;
let _eqWizardStep = 1;    // passo atual do wizard (1=selecionar, 2=preview, 3=executar)
let _eqConnAName = '';
let _eqConnBName = '';

// =====================================================================
// ABA EQUALIZAR — Historico + Nova Equalizacao
// =====================================================================

function _renderEqualizeTab() {
    const container = document.getElementById('db-equalize-content');
    if (!container) return;

    const hasCompareResult = dictCompareResult && dictCompareResult.results;

    // Contar itens equalizaveis do ultimo Compare
    let eqCount = 0;
    if (hasCompareResult) {
        for (const tn of Object.keys(dictCompareResult.results)) {
            const inf = dictCompareResult.results[tn];
            eqCount += (inf.only_a || []).length + (inf.only_b || []).length;
        }
    }

    container.innerHTML = `
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="card-title mb-1"><i class="fas fa-sync me-2"></i>Equalização Dicionário Protheus</h6>
                        <p class="text-muted small mb-0">Sincronize seletivamente tabelas, campos e indices entre dois bancos Protheus.</p>
                    </div>
                    <div>
                        ${hasCompareResult && eqCount > 0 && !dictCompareResult._fromHistory
                            ? `<button class="btn btn-warning btn-sm" data-action="dictOpenEqualizeWizard">
                                   <i class="fas fa-bolt me-1"></i>Nova Equalização (${eqCount} itens)
                               </button>`
                            : hasCompareResult && dictCompareResult._fromHistory
                                ? `<span class="badge bg-secondary py-2"><i class="fas fa-lock me-1"></i>Resultado do histórico — execute nova comparação</span>`
                                : `<button class="btn btn-outline-secondary btn-sm" disabled title="Execute um Compare primeiro para identificar divergências">
                                       <i class="fas fa-bolt me-1"></i>Nova Equalização
                                   </button>`
                        }
                    </div>
                </div>
                ${!hasCompareResult ? `
                <div class="alert alert-info py-2 mt-3 mb-0 small">
                    <i class="fas fa-info-circle me-1"></i>
                    Execute uma <strong>Comparação de Dicionário</strong> na aba <a href="#" onclick="dbSwitchTab('compare'); return false;" class="alert-link">Comparar Dicionário</a> primeiro para identificar as divergências equalizáveis.
                </div>` : ''}
                ${hasCompareResult && eqCount === 0 ? `
                <div class="alert alert-success py-2 mt-3 mb-0 small">
                    <i class="fas fa-check-circle me-1"></i>
                    A última comparação não encontrou itens equalizáveis (apenas A / apenas B). Os dicionários estão sincronizados!
                </div>` : ''}
            </div>
        </div>

        <!-- Historico de equalizações -->
        <div id="eq-history-container">
            <div class="d-flex justify-content-center py-3">
                <div class="spinner-border spinner-border-sm text-muted"></div>
                <span class="text-muted ms-2 small">Carregando histórico...</span>
            </div>
        </div>
    `;

    _eqLoadHistory();
}

async function _eqLoadHistory() {
    const histDiv = document.getElementById('eq-history-container');
    if (!histDiv) return;

    try {
        const envId = sessionStorage.getItem('active_environment_id');
        const resp = await apiRequest(`/dictionary/history?environment_id=${envId || ''}&limit=20`);
        const items = (resp.history || []).filter(h => h.operation_type === 'equalize');
        _eqRenderHistoryList(histDiv, items);
    } catch (e) {
        histDiv.innerHTML = `<div class="alert alert-warning small"><i class="fas fa-exclamation-triangle me-1"></i>Erro ao carregar histórico: ${escapeHtml(e.message)}</div>`;
    }
}

function _eqRenderHistoryList(container, items) {
    if (items.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-3">
                <i class="fas fa-history fa-2x mb-2 d-block opacity-50"></i>
                <small>Nenhuma equalização realizada ainda.</small>
            </div>`;
        return;
    }

    let html = '<h6 class="mb-3"><i class="fas fa-history me-2"></i>Histórico de Equalizações</h6>';
    for (const item of items) {
        const summary = item.summary || {};
        const executed = summary.executed || 0;
        const ddlCount = summary.ddl_count || 0;
        const dmlCount = summary.dml_count || 0;
        const durationMs = summary.duration_ms || 0;

        const connA = item.conn_a_name || `Conexão #${item.connection_a_id}`;
        const connB = item.conn_b_name || `Conexão #${item.connection_b_id}`;
        const dt = item.executed_at ? _dictFormatDate(item.executed_at) : '---';
        const user = item.executed_by_name || '';

        html += `
            <div class="card mb-2">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center gap-3">
                            <div>
                                <span class="badge bg-success">
                                    <i class="fas fa-check-circle me-1"></i>${executed} stmt(s)
                                </span>
                            </div>
                            <div>
                                <div class="fw-bold small">
                                    ${escapeHtml(connA)}
                                    <i class="fas fa-arrow-right text-warning mx-1"></i>
                                    ${escapeHtml(connB)}
                                </div>
                                <div class="text-muted" style="font-size:0.75rem">
                                    Emp. ${escapeHtml(item.company_code || '')}
                                    <span class="ms-2"><i class="fas fa-wrench me-1"></i>${ddlCount} DDL + ${dmlCount} DML</span>
                                    <span class="ms-2"><i class="fas fa-calendar me-1"></i>${dt}</span>
                                    ${durationMs ? `<span class="ms-2"><i class="fas fa-clock me-1"></i>${(durationMs / 1000).toFixed(1)}s</span>` : ''}
                                    ${user ? `<span class="ms-2"><i class="fas fa-user me-1"></i>${escapeHtml(user)}</span>` : ''}
                                </div>
                            </div>
                        </div>
                        <div class="d-flex gap-1">
                            <button class="btn btn-outline-primary btn-sm"
                                data-action="eqViewHistory" data-params='{"id":${item.id}}'
                                title="Visualizar SQL executado">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn btn-outline-secondary btn-sm"
                                data-action="eqExportHistory" data-params='{"historyId":${item.id}}'
                                title="Exportar CSV">
                                <i class="fas fa-file-csv"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm"
                                data-action="eqDeleteHistory" data-params='{"id":${item.id}}'
                                title="Excluir">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`;
    }
    container.innerHTML = html;
}

async function eqViewHistory(params) {
    const id = params.id;
    if (!id) return;

    const container = document.getElementById('db-equalize-content');
    if (!container) return;

    container.innerHTML = `<div class="d-flex justify-content-center py-5"><div class="spinner-border text-primary"></div></div>`;

    try {
        const item = await apiRequest(`/dictionary/history/${id}`);
        const summary = item.summary || {};
        const details = item.details || {};
        const statements = details.statements || [];

        const connA = item.conn_a_name || `Conexão #${item.connection_a_id}`;
        const connB = item.conn_b_name || `Conexão #${item.connection_b_id}`;
        const dt = item.executed_at ? _dictFormatDate(item.executed_at) : '---';

        const phase1 = statements.filter(s => s.phase === 1);
        const phase2 = statements.filter(s => s.phase === 2);

        let html = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <button class="btn btn-outline-secondary btn-sm" data-action="eqBackToHistory">
                    <i class="fas fa-arrow-left me-1"></i>Voltar
                </button>
                <span class="badge bg-secondary">${dt}</span>
            </div>

            <div class="card mb-3">
                <div class="card-header bg-warning bg-opacity-10">
                    <h6 class="mb-0"><i class="fas fa-sync me-2"></i>Equalização #${id}</h6>
                </div>
                <div class="card-body">
                    <div class="row g-3">
                        <div class="col-md-4">
                            <small class="text-muted d-block">Origem → Destino</small>
                            <strong>${escapeHtml(connA)} <i class="fas fa-arrow-right text-warning mx-1"></i> ${escapeHtml(connB)}</strong>
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted d-block">Empresa</small>
                            <strong>${escapeHtml(item.company_code || '---')}</strong>
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted d-block">Statements</small>
                            <strong>${summary.executed || 0}</strong> <small class="text-muted">(${summary.ddl_count || 0} DDL + ${summary.dml_count || 0} DML)</small>
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted d-block">Duração</small>
                            <strong>${summary.duration_ms ? (summary.duration_ms / 1000).toFixed(1) + 's' : '---'}</strong>
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted d-block">Executado por</small>
                            <strong>${escapeHtml(item.executed_by_name || '---')}</strong>
                        </div>
                    </div>
                </div>
            </div>`;

        // SQL executado
        if (statements.length > 0) {
            html += `<div class="card"><div class="card-header py-2"><h6 class="mb-0 small"><i class="fas fa-code me-2"></i>SQL Executado (${statements.length})</h6></div>
                <div class="card-body p-0">
                    <div class="border rounded m-2 p-2" style="max-height:500px;overflow-y:auto;background:#1e1e1e;color:#d4d4d4;font-size:.75rem">`;

            if (phase1.length > 0) {
                html += `<div class="text-info mb-1">-- FASE 1: DDL Físico (${phase1.length})</div>`;
                for (const st of phase1) {
                    html += `<div class="mb-1"><span class="text-muted">-- ${escapeHtml(st.description || '')}</span><br><code class="hl-string">${escapeHtml(st.sql)};</code></div>`;
                }
            }
            if (phase2.length > 0) {
                html += `<div class="text-success mt-2 mb-1">-- FASE 2: Metadados DML (${phase2.length})</div>`;
                for (const st of phase2) {
                    html += `<div class="mb-1"><span class="text-muted">-- ${escapeHtml(st.description || '')}</span><br><code class="hl-string">${escapeHtml(st.sql)};</code></div>`;
                }
            }

            html += `</div></div></div>`;
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-1"></i>${escapeHtml(e.message)}</div>`;
    }
}

function eqBackToHistory() {
    _renderEqualizeTab();
}

async function eqDeleteHistory(params) {
    const id = params.id;
    if (!id) return;
    if (!confirm('Excluir este registro de equalização?')) return;

    try {
        await apiRequest(`/dictionary/history/${id}`, 'DELETE');
        showNotification('Registro excluído.', 'success');
        _eqLoadHistory();
    } catch (e) {
        showNotification('Erro ao excluir: ' + e.message, 'error');
    }
}

async function eqExportHistory(params) {
    const historyId = params.historyId;
    if (!historyId) return;
    try {
        const response = await apiDownload(`/dictionary/export/equalize/${historyId}`);
        const blob = await response.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `equalize_${historyId}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (e) {
        showNotification('Erro ao exportar CSV: ' + e.message, 'error');
    }
}

// =====================================================================
// WIZARD DE EQUALIZACAO (Modal 3 passos)
// =====================================================================

/**
 * Abre o wizard de equalizacao extraindo itens do resultado do Compare.
 * Pode ser chamado da aba Equalização ou da aba Compare.
 */
function dictOpenEqualizeWizard() {
    if (!dictCompareResult || !dictCompareResult.results) {
        showNotification('Execute uma comparação primeiro.', 'warning');
        return;
    }
    if (dictCompareResult._fromHistory) {
        showNotification('Este resultado é do histórico. Execute uma nova comparação para equalizar.', 'warning');
        return;
    }

    // Capturar conexoes e empresa
    _eqConnA = document.getElementById('dict-conn-a')?.value || dictCompareResult._connAId;
    _eqConnB = document.getElementById('dict-conn-b')?.value || dictCompareResult._connBId;
    _eqCompanyCode = document.getElementById('dict-company-a')?.value || dictCompareResult._companyCode;

    const connAEl = document.getElementById('dict-conn-a');
    const connBEl = document.getElementById('dict-conn-b');
    _eqConnAName = connAEl ? connAEl.options[connAEl.selectedIndex]?.text : (dictCompareResult._connAName || `Conexão #${_eqConnA}`);
    _eqConnBName = connBEl ? connBEl.options[connBEl.selectedIndex]?.text : (dictCompareResult._connBName || `Conexão #${_eqConnB}`);

    _eqDirection = 'a2b';
    _eqPreviewData = null;
    _eqWizardStep = 1;
    _eqItems = [];

    const results = dictCompareResult.results;

    // Categorizar itens equalizaveis
    for (const tname of Object.keys(results).sort()) {
        const info = results[tname];
        const prefix = info.prefix || tname.replace(/\d+$/, '');

        _eqExtractItems(info.only_a || [], 'a', tname, prefix);
        _eqExtractItems(info.only_b || [], 'b', tname, prefix);

        // Registros diferentes — equalizaveis via UPDATE (bidirecional)
        if ((info.different || []).length > 0) {
            if (prefix === 'SX3') {
                _eqExtractDiffItems(info.different, tname, prefix);
            } else {
                _eqExtractMetadataDiffItems(info.different, tname, prefix);
            }
        }
    }

    if (_eqItems.length === 0) {
        showNotification('Nenhum item equalizável encontrado.', 'info');
        return;
    }

    _eqShowWizardModal();
}

// Alias para manter compatibilidade com botao na aba Compare
function dictOpenEqualizeModal() {
    dictOpenEqualizeWizard();
}

function _eqExtractItems(onlyList, source, tname, prefix) {
    for (const item of onlyList) {
        let itemType = 'metadata';
        let label = `${tname} → ${item.key}`;
        let extraData = { meta_table: prefix, values: item.values || {} };

        if (prefix === 'SX2') {
            itemType = 'full_table';
            label = `${item.key} — Tabela completa`;
            extraData.table_alias = item.key;
            extraData.sx2_values = item.values || {};
            extraData.sx3_list = item.sx3_list || [];
            extraData.six_list = item.six_list || [];
        } else if (prefix === 'SX3') {
            itemType = 'field';
            const parts = (item.key || '').split('|');
            const tableAlias = parts[0] || '';
            const fieldName = parts[1] || parts[0] || '';
            label = `${tableAlias} → ${fieldName}`;
            const x3Tipo = _eqGetVal(item.values, 'X3_TIPO');
            const x3Tam = _eqGetVal(item.values, 'X3_TAMANHO');
            if (x3Tipo || x3Tam) label += ` (${x3Tipo}/${x3Tam})`;
            extraData.table_alias = tableAlias;
            extraData.field_name = fieldName;
        } else if (prefix === 'SIX') {
            itemType = 'index';
            const parts = (item.key || '').split('|');
            const indice = parts[0] || '';
            const ordem = parts[1] || '';
            const chave = _eqGetVal(item.values, 'CHAVE');
            label = `${indice} Ordem ${ordem}`;
            if (chave) label += ` — ${chave}`;
            extraData.indice = indice;
            extraData.ordem = ordem;
        }

        _eqItems.push({
            type: itemType, source, checked: false, label, tname, prefix,
            key: item.key, ...extraData,
        });
    }
}

function _eqExtractDiffItems(diffList, tname, prefix) {
    // Cada item em diffList: {key: "ALIAS|CAMPO", fields: [{field, val_a, val_b}]}
    // Gera dois itens (A→B e B→A) para permitir escolha de direcao
    for (const item of diffList) {
        const parts = (item.key || '').split('|');
        const tableAlias = parts[0] || '';
        const fieldName = parts[1] || parts[0] || '';
        const diffCols = (item.fields || []).map(f => f.field).join(', ');

        // Item para direcao A→B (source='a': aplica valores de A no B)
        _eqItems.push({
            type: 'field_diff', source: 'a', checked: false,
            label: `${tableAlias} → ${fieldName} (${diffCols})`,
            tname, prefix, key: item.key,
            table_alias: tableAlias,
            field_name: fieldName,
            diff_fields: item.fields,
        });

        // Item para direcao B→A (source='b': aplica valores de B no A)
        _eqItems.push({
            type: 'field_diff', source: 'b', checked: false,
            label: `${tableAlias} → ${fieldName} (${diffCols})`,
            tname, prefix, key: item.key,
            table_alias: tableAlias,
            field_name: fieldName,
            diff_fields: item.fields.map(f => ({ field: f.field, val_a: f.val_b, val_b: f.val_a })),
        });
    }
}

function _eqExtractMetadataDiffItems(diffList, tname, prefix) {
    // Registros diferentes em tabelas de metadado (exceto SX3 que tem tratamento especial)
    // Gera dois itens (A→B e B→A) para permitir escolha de direcao
    for (const item of diffList) {
        const diffCols = (item.fields || []).map(f => f.field).join(', ');

        // Item para direcao A→B
        _eqItems.push({
            type: 'metadata_diff', source: 'a', checked: false,
            label: `${tname} → ${item.key} (${diffCols})`,
            tname, prefix, key: item.key,
            meta_table: prefix,
            diff_fields: item.fields,
        });

        // Item para direcao B→A (inverte val_a/val_b)
        _eqItems.push({
            type: 'metadata_diff', source: 'b', checked: false,
            label: `${tname} → ${item.key} (${diffCols})`,
            tname, prefix, key: item.key,
            meta_table: prefix,
            diff_fields: item.fields.map(f => ({ field: f.field, val_a: f.val_b, val_b: f.val_a })),
        });
    }
}

function _eqGetVal(data, field) {
    if (!data) return '';
    return String(data[field] || data[field.toLowerCase()] || '').trim();
}

function _eqShowWizardModal() {
    const old = document.getElementById('dictEqualizeModal');
    if (old) old.remove();

    const modalHtml = `
    <div class="modal fade" id="dictEqualizeModal" tabindex="-1" data-bs-backdrop="static">
        <div class="modal-dialog modal-xl modal-dialog-scrollable">
            <div class="modal-content">
                <div class="modal-header bg-warning bg-opacity-25 py-2">
                    <div class="d-flex align-items-center gap-3 w-100">
                        <h6 class="modal-title mb-0"><i class="fas fa-sync me-2"></i>Equalização Dicionário</h6>
                        <div class="d-flex gap-2 ms-auto me-3" id="eq-wizard-stepper">
                            ${_eqRenderStepper()}
                        </div>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                </div>
                <div class="modal-body" id="eq-modal-body">
                    ${_eqRenderWizardContent()}
                </div>
                <div class="modal-footer py-2" id="eq-modal-footer">
                    ${_eqRenderWizardFooter()}
                </div>
            </div>
        </div>
    </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('dictEqualizeModal'));
    modal.show();

    document.getElementById('dictEqualizeModal').addEventListener('hidden.bs.modal', () => {
        document.getElementById('dictEqualizeModal')?.remove();
    });
}

function _eqRenderStepper() {
    const steps = [
        { num: 1, label: 'Selecionar', icon: 'fa-check-square' },
        { num: 2, label: 'Preview SQL', icon: 'fa-eye' },
        { num: 3, label: 'Executar', icon: 'fa-bolt' },
    ];
    return steps.map(s => {
        let cls = 'text-muted';
        let bg = 'bg-secondary bg-opacity-25';
        if (s.num === _eqWizardStep) { cls = 'text-dark fw-bold'; bg = 'bg-warning bg-opacity-50'; }
        else if (s.num < _eqWizardStep) { cls = 'text-success'; bg = 'bg-success bg-opacity-10'; }
        return `<span class="badge ${bg} ${cls} px-2 py-1" style="font-size:.75rem">
            <i class="fas ${s.icon} me-1"></i>${s.num}. ${s.label}
        </span>`;
    }).join('<i class="fas fa-chevron-right text-muted" style="font-size:.6rem"></i>');
}

function _eqRefreshWizard() {
    const stepper = document.getElementById('eq-wizard-stepper');
    if (stepper) stepper.innerHTML = _eqRenderStepper();
    const body = document.getElementById('eq-modal-body');
    if (body) body.innerHTML = _eqRenderWizardContent();
    const footer = document.getElementById('eq-modal-footer');
    if (footer) footer.innerHTML = _eqRenderWizardFooter();
}

function _eqRenderWizardContent() {
    if (_eqWizardStep === 1) return _eqRenderStep1();
    if (_eqWizardStep === 2) return _eqRenderStep2();
    if (_eqWizardStep === 3) return _eqRenderStep3();
    return '';
}

function _eqRenderWizardFooter() {
    let html = '<div id="eq-status" class="me-auto"></div>';

    if (_eqWizardStep === 1) {
        html += `
            <button class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancelar</button>
            <button class="btn btn-info btn-sm" data-action="eqWizardNext" id="eq-next-btn">
                <i class="fas fa-eye me-1"></i>Gerar Preview SQL <i class="fas fa-arrow-right ms-1"></i>
            </button>`;
    } else if (_eqWizardStep === 2) {
        html += `
            <button class="btn btn-outline-secondary btn-sm" data-action="eqWizardPrev">
                <i class="fas fa-arrow-left me-1"></i>Voltar
            </button>
            <button class="btn btn-warning btn-sm" data-action="eqWizardNext" id="eq-execute-btn">
                <i class="fas fa-bolt me-1"></i>Executar Equalização <i class="fas fa-arrow-right ms-1"></i>
            </button>`;
    } else if (_eqWizardStep === 3) {
        html += `
            <button class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Fechar</button>`;
    }

    return html;
}

// --- PASSO 1: Selecionar Itens ---

function _eqRenderStep1() {
    let html = `
        <div class="mb-3">
            <label class="form-label fw-bold small">Direção da equalização:</label>
            <div class="form-check">
                <input class="form-check-input" type="radio" name="eq-direction" id="eq-dir-a2b" value="a2b"
                    ${_eqDirection === 'a2b' ? 'checked' : ''} onchange="_eqChangeDirection('a2b')">
                <label class="form-check-label" for="eq-dir-a2b">
                    <strong>A → B</strong> <small class="text-muted">(${escapeHtml(_eqConnAName)} → ${escapeHtml(_eqConnBName)})</small>
                </label>
            </div>
            <div class="form-check">
                <input class="form-check-input" type="radio" name="eq-direction" id="eq-dir-b2a" value="b2a"
                    ${_eqDirection === 'b2a' ? 'checked' : ''} onchange="_eqChangeDirection('b2a')">
                <label class="form-check-label" for="eq-dir-b2a">
                    <strong>B → A</strong> <small class="text-muted">(${escapeHtml(_eqConnBName)} → ${escapeHtml(_eqConnAName)})</small>
                </label>
            </div>
        </div>`;

    const dirSource = _eqDirection === 'a2b' ? 'a' : 'b';
    const dirItems = _eqItems.filter(it => it.source === dirSource);

    if (dirItems.length === 0) {
        html += `<div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>Nenhum item para equalizar nesta direção.</div>`;
        return html;
    }

    const groups = {
        full_table: { label: 'Tabelas Novas (SX2)', icon: 'fa-table', color: 'danger', items: [] },
        field: { label: 'Campos Faltantes (SX3)', icon: 'fa-columns', color: 'warning', items: [] },
        field_diff: { label: 'Campos Diferentes (SX3)', icon: 'fa-exchange-alt', color: 'purple', items: [] },
        index: { label: 'Índices Faltantes (SIX)', icon: 'fa-key', color: 'info', items: [] },
        metadata: { label: 'Metadados Faltantes', icon: 'fa-database', color: 'secondary', items: [] },
        metadata_diff: { label: 'Metadados Diferentes', icon: 'fa-not-equal', color: 'dark', items: [] },
    };

    for (const it of dirItems) {
        (groups[it.type] || groups.metadata).items.push(it);
    }

    for (const [gtype, g] of Object.entries(groups)) {
        if (g.items.length === 0) continue;

        const allChecked = g.items.every(it => it.checked);
        html += `
        <div class="card mb-2">
            <div class="card-header py-2 bg-${g.color} bg-opacity-10">
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="eq-grp-${gtype}"
                        ${allChecked ? 'checked' : ''} onchange="_eqToggleGroup('${gtype}')">
                    <label class="form-check-label fw-bold small" for="eq-grp-${gtype}">
                        <i class="fas ${g.icon} me-1"></i>${g.label} (${g.items.length})
                    </label>
                </div>
            </div>
            <div class="card-body py-2" style="max-height:200px;overflow-y:auto">`;

        for (let i = 0; i < g.items.length; i++) {
            const it = g.items[i];
            const globalIdx = _eqItems.indexOf(it);
            html += `
                <div class="form-check">
                    <input class="form-check-input eq-item-chk" type="checkbox" id="eq-item-${globalIdx}"
                        data-idx="${globalIdx}" ${it.checked ? 'checked' : ''} onchange="_eqToggleItem(${globalIdx})">
                    <label class="form-check-label small" for="eq-item-${globalIdx}">
                        <code>${escapeHtml(it.label)}</code>
                    </label>
                </div>`;
        }

        html += `</div></div>`;
    }

    // Aviso das 3 fases
    html += `
        <div class="alert alert-secondary py-2 mt-3 mb-0" style="font-size:.8rem">
            <i class="fas fa-info-circle me-1 text-primary"></i><strong>Como funciona:</strong>
            <div class="mt-1 ms-3">
                <div><span class="badge bg-info text-dark me-1">Fase 1</span> DDL Físico — ALTER TABLE, CREATE TABLE, CREATE INDEX</div>
                <div class="mt-1"><span class="badge bg-success me-1">Fase 2</span> Metadados DML — INSERT/UPDATE em SX2, SX3, SIX, TOP_FIELD</div>
                <div class="mt-1"><span class="badge bg-secondary me-1">Fase 3</span> Auditoria — Registro no histórico</div>
            </div>
            <div class="mt-2 text-muted"><i class="fas fa-shield-alt me-1"></i>Transação atômica: qualquer erro = ROLLBACK completo.</div>
        </div>`;

    return html;
}

// --- PASSO 2: Preview SQL ---

function _eqRenderStep2() {
    if (!_eqPreviewData) {
        return `<div class="d-flex justify-content-center py-5">
            <div class="spinner-border text-warning"></div>
            <span class="ms-3 text-muted">Gerando preview SQL...</span>
        </div>`;
    }

    const resp = _eqPreviewData;
    const s = resp.summary || {};
    let html = '';

    // Resumo
    html += `<div class="alert alert-info py-2 mb-3">
        <i class="fas fa-list-ol me-1"></i><strong>Resumo:</strong>
        ${s.tables ? `${s.tables} tabela(s)` : ''}
        ${s.fields ? `${s.fields} campo(s) novo(s)` : ''}
        ${s.field_diffs ? `${s.field_diffs} campo(s) atualizado(s)` : ''}
        ${s.indexes ? `${s.indexes} índice(s)` : ''}
        ${s.metadata ? `${s.metadata} metadado(s) novo(s)` : ''}
        ${s.metadata_diffs ? `${s.metadata_diffs} metadado(s) atualizado(s)` : ''}
        — Total: <strong>${s.total_statements || 0}</strong> SQL (${s.ddl_count || 0} DDL + ${s.dml_count || 0} DML)
    </div>`;

    // Warnings — separar integridade (criticos) de avisos normais
    if ((resp.warnings || []).length > 0) {
        const integrityWarnings = resp.warnings.filter(w =>
            w.startsWith('ATENCAO:') || w.startsWith('[SOURCE]') || w.startsWith('[TARGET]')
        );
        const normalWarnings = resp.warnings.filter(w =>
            !w.startsWith('ATENCAO:') && !w.startsWith('[SOURCE]') && !w.startsWith('[TARGET]')
        );

        if (integrityWarnings.length > 0) {
            html += `<div class="alert alert-danger py-2 mb-3"><i class="fas fa-shield-alt me-1"></i>
                <strong>Integridade:</strong><ul class="mb-0 mt-1">`;
            for (const w of integrityWarnings) {
                html += `<li class="small">${escapeHtml(w)}</li>`;
            }
            html += '</ul></div>';
        }
        if (normalWarnings.length > 0) {
            html += `<div class="alert alert-warning py-2 mb-3"><i class="fas fa-exclamation-triangle me-1"></i>
                <strong>${normalWarnings.length} aviso(s):</strong><ul class="mb-0 mt-1">`;
            for (const w of normalWarnings) {
                html += `<li class="small">${escapeHtml(w)}</li>`;
            }
            html += '</ul></div>';
        }
    }

    // SQL
    const phase1 = resp.phase1_ddl || [];
    const phase2 = resp.phase2_dml || [];

    if (phase1.length + phase2.length > 0) {
        html += `<div class="border rounded p-2" style="max-height:400px;overflow-y:auto;background:#1e1e1e;color:#d4d4d4;font-size:.75rem">`;
        if (phase1.length > 0) {
            html += `<div class="text-info mb-1">-- FASE 1: DDL Físico (${phase1.length})</div>`;
            for (const st of phase1) {
                html += `<div class="mb-1"><span class="text-muted">-- ${escapeHtml(st.description)}</span><br><code class="hl-string">${escapeHtml(st.sql)};</code></div>`;
            }
        }
        if (phase2.length > 0) {
            html += `<div class="text-success mt-2 mb-1">-- FASE 2: Metadados DML (${phase2.length})</div>`;
            for (const st of phase2) {
                html += `<div class="mb-1"><span class="text-muted">-- ${escapeHtml(st.description)}</span><br><code class="hl-string">${escapeHtml(st.sql)};</code></div>`;
            }
        }
        html += '</div>';
    }

    if (phase1.length + phase2.length === 0) {
        html += `<div class="alert alert-secondary">Nenhum SQL gerado. Verifique os itens selecionados.</div>`;
    }

    return html;
}

// --- PASSO 3: Resultado da Execução ---

function _eqRenderStep3() {
    return `<div id="eq-exec-result" class="d-flex justify-content-center py-5">
        <div class="spinner-border text-warning"></div>
        <span class="ms-3 text-muted">Executando equalização...</span>
    </div>`;
}

// =====================================================================
// WIZARD: Navegação entre passos
// =====================================================================

async function eqWizardNext() {
    if (_eqWizardStep === 1) {
        // Passo 1 → 2: Gerar preview
        const dirSource = _eqDirection === 'a2b' ? 'a' : 'b';

        // Re-sincronizar estado a partir do DOM (source of truth visual)
        for (let i = 0; i < _eqItems.length; i++) {
            const el = document.getElementById(`eq-item-${i}`);
            if (el) _eqItems[i].checked = el.checked;
        }

        const selected = _eqItems.filter(it => it.source === dirSource && it.checked);

        if (selected.length === 0) {
            showNotification('Selecione ao menos um item para equalizar.', 'warning');
            return;
        }

        _eqWizardStep = 2;
        _eqPreviewData = null;
        _eqRefreshWizard();

        // Chamar API de preview
        await _eqFetchPreview(selected);

    } else if (_eqWizardStep === 2) {
        // Passo 2 → 3: Executar
        if (!_eqPreviewData) {
            showNotification('Aguarde o preview ser gerado.', 'warning');
            return;
        }

        const allStmts = [...(_eqPreviewData.phase1_ddl || []), ...(_eqPreviewData.phase2_dml || [])];
        if (allStmts.length === 0) {
            showNotification('Nenhum SQL para executar.', 'info');
            return;
        }

        if (!confirm(`Confirma a execução de ${allStmts.length} statement(s) SQL no banco de destino?\n\nEsta operação será em transação atômica (tudo ou nada).`)) {
            return;
        }

        _eqWizardStep = 3;
        _eqRefreshWizard();

        await _eqExecute(allStmts);
    }
}

function eqWizardPrev() {
    if (_eqWizardStep === 2) {
        _eqWizardStep = 1;
        _eqPreviewData = null;
        _eqRefreshWizard();
    }
}

async function _eqFetchPreview(selected) {
    const sourceId = _eqDirection === 'a2b' ? _eqConnA : _eqConnB;
    const targetId = _eqDirection === 'a2b' ? _eqConnB : _eqConnA;

    const apiItems = selected.map(it => {
        const base = { type: it.type, meta_table: it.meta_table || it.prefix, key: it.key || '' };
        if (it.type === 'field') { base.table_alias = it.table_alias; base.field_name = it.field_name; }
        else if (it.type === 'field_diff') {
            base.table_alias = it.table_alias;
            base.field_name = it.field_name;
            base.diff_fields = it.diff_fields;
        }
        else if (it.type === 'metadata_diff') {
            base.diff_fields = it.diff_fields;
        }
        else if (it.type === 'index') { base.indice = it.indice; base.ordem = it.ordem; }
        else if (it.type === 'full_table') { base.table_alias = it.table_alias; }
        return base;
    });

    try {
        const resp = await apiRequest('/dictionary/equalize/preview', 'POST', {
            source_conn_id: parseInt(sourceId),
            target_conn_id: parseInt(targetId),
            company_code: _eqCompanyCode,
            items: apiItems,
        });
        _eqPreviewData = resp;
        _eqRefreshWizard();
    } catch (e) {
        showNotification('Erro ao gerar preview: ' + e.message, 'error');
        // Voltar para passo 1
        _eqWizardStep = 1;
        _eqRefreshWizard();
    }
}

async function _eqExecute(allStmts) {
    const sourceId = _eqDirection === 'a2b' ? _eqConnA : _eqConnB;
    const targetId = _eqDirection === 'a2b' ? _eqConnB : _eqConnA;
    const envId = sessionStorage.getItem('active_environment_id');

    try {
        const resp = await apiRequest('/dictionary/equalize/execute', 'POST', {
            target_conn_id: parseInt(targetId),
            source_conn_id: parseInt(sourceId),
            company_code: _eqCompanyCode,
            sql_statements: allStmts,
            confirmation_token: _eqPreviewData.confirmation_token,
            environment_id: envId ? parseInt(envId) : null,
        });

        const resultDiv = document.getElementById('eq-exec-result');
        if (resp.success) {
            const isPartial = resp.status === 'partial';
            const tcr = resp.tcrefresh || {};
            const failedTables = (tcr.errors || []).map(e => e.table).join(', ');

            if (resultDiv) {
                // Bloco de sucesso ou parcial
                const icon = isPartial
                    ? '<i class="fas fa-exclamation-triangle text-warning fa-3x"></i>'
                    : '<i class="fas fa-check-circle text-success fa-3x"></i>';
                const title = isPartial
                    ? '<h5 class="text-warning">Equalização parcial</h5>'
                    : '<h5 class="text-success">Equalização concluída!</h5>';

                let partialAlert = '';
                if (isPartial) {
                    partialAlert = `
                        <div class="alert alert-warning small mt-3 text-start">
                            <i class="fas fa-info-circle me-1"></i>
                            <strong>DDL + metadados aplicados com sucesso</strong>, porém o TcRefresh falhou
                            para: <strong>${escapeHtml(failedTables)}</strong>
                            <br><small class="text-muted">O campo foi criado no banco e no dicionário, mas o DBAccess ainda não reconhece.
                            Reinicie o AppServer ou abra a tabela pelo APSDU para ativar.</small>
                        </div>`;
                }

                resultDiv.innerHTML = `
                    <div class="text-center w-100">
                        <div class="mb-3">${icon}</div>
                        ${title}
                        <p class="text-muted mb-2">${resp.executed} statement(s) executado(s) em ${resp.duration_ms}ms</p>
                        <div class="d-flex justify-content-center gap-2 mt-3">
                            <span class="badge bg-info">${(_eqPreviewData?.summary?.ddl_count || 0)} DDL</span>
                            <span class="badge bg-success">${(_eqPreviewData?.summary?.dml_count || 0)} DML</span>
                            ${isPartial
                                ? '<span class="badge bg-warning text-dark">TcRefresh pendente</span>'
                                : '<span class="badge bg-primary">TcRefresh OK</span>'}
                        </div>
                        ${partialAlert}
                        <p class="text-muted small mt-3">Execute um novo Compare para verificar a sincronização.</p>
                    </div>`;
            }

            if (isPartial) {
                showNotification(
                    `Equalização parcial: ${resp.executed} statement(s) OK, TcRefresh falhou para ${failedTables}. Reinicie o AppServer ou use o APSDU.`,
                    'warning'
                );
            } else {
                showNotification(`Equalização concluída! ${resp.executed} statement(s) em ${resp.duration_ms}ms.`, 'success');
            }

            // Invalidar Compare anterior
            dictCompareResult = null;
            _dictSaveState('dictCompareResult', null);
        } else {
            const errMsg = resp.error || 'Erro desconhecido';
            if (resultDiv) {
                resultDiv.innerHTML = `
                    <div class="text-center w-100">
                        <div class="mb-3"><i class="fas fa-times-circle text-danger fa-3x"></i></div>
                        <h5 class="text-danger">Falha — ROLLBACK</h5>
                        <p class="text-muted mb-2">${resp.executed_before_error || 0} statement(s) executado(s) antes do erro</p>
                        <div class="alert alert-danger small mt-3">${escapeHtml(errMsg)}</div>
                        <p class="text-muted small">Todas as alterações foram desfeitas (ROLLBACK). Nenhuma modificação persistiu.</p>
                    </div>`;
            }
            showNotification(`Falha na equalização (ROLLBACK): ${errMsg}`, 'error');
        }
    } catch (e) {
        const resultDiv = document.getElementById('eq-exec-result');
        if (resultDiv) {
            resultDiv.innerHTML = `
                <div class="text-center w-100">
                    <div class="mb-3"><i class="fas fa-exclamation-triangle text-danger fa-3x"></i></div>
                    <h5 class="text-danger">Erro de comunicação</h5>
                    <div class="alert alert-danger small mt-3">${escapeHtml(e.message)}</div>
                </div>`;
        }
        showNotification('Erro ao executar equalização: ' + e.message, 'error');
    }
}

// --- Helpers reutilizados pelo wizard ---

function _eqChangeDirection(dir) {
    _eqDirection = dir;
    _eqPreviewData = null;
    const body = document.getElementById('eq-modal-body');
    if (body) body.innerHTML = _eqRenderStep1();
}

function _eqToggleGroup(gtype) {
    const grpChk = document.getElementById(`eq-grp-${gtype}`);
    if (!grpChk) return;
    const checked = grpChk.checked;

    const dirSource = _eqDirection === 'a2b' ? 'a' : 'b';
    for (let i = 0; i < _eqItems.length; i++) {
        const it = _eqItems[i];
        if (it.source === dirSource && it.type === gtype) {
            it.checked = checked;
            const el = document.getElementById(`eq-item-${i}`);
            if (el) el.checked = checked;
        }
    }
}

function _eqToggleItem(idx) {
    const el = document.getElementById(`eq-item-${idx}`);
    if (!el) return;
    _eqItems[idx].checked = el.checked;
}

// Aliases para manter compatibilidade com actions existentes
function dictPreviewEqualize() { eqWizardNext(); }
function dictExecuteEqualize() { eqWizardNext(); }


// =====================================================================
// ABA: INGESTOR DE DICIONARIO
// =====================================================================

let _ingWizardStep = 1;  // 1=upload, 2=select, 3=preview, 4=execute
let _ingParsedData = null;
let _ingTargetConn = null;
let _ingCompanyCode = '';
let _ingPreviewData = null;
let _ingUploadedItems = [];
let _ingExecutionResult = null;  // Salva resultado da execucao para re-render

function _renderIngestorTab() {
    const container = document.getElementById('db-ingestor-content');
    if (!container) return;

    // Conexoes ativas para dropdown
    const activeConns = dbConnections.filter(c => c.is_active);

    container.innerHTML = `
        <div class="card border-0 shadow-sm">
            <div class="card-header bg-white border-bottom">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="card-title mb-1"><i class="fas fa-file-import me-2"></i>Ingestor de Dicionario Protheus</h6>
                        <p class="text-muted small mb-0">Importe definicoes de dicionario a partir de arquivo externo (JSON ou Markdown).</p>
                    </div>
                    <div>
                        <span class="badge bg-info">Etapa ${_ingWizardStep}/4</span>
                    </div>
                </div>
            </div>
            <div class="card-body">
                ${_ingWizardStep === 1 ? _renderIngStep1(activeConns) : ''}
                ${_ingWizardStep === 2 ? _renderIngStep2() : ''}
                ${_ingWizardStep === 3 ? _renderIngStep3() : ''}
                ${_ingWizardStep === 4 ? _renderIngStep4() : ''}
            </div>
        </div>
    `;

    // Carregar empresas se conexao ja selecionada
    if (_ingWizardStep === 1 && _ingTargetConn) {
        setTimeout(() => _ingLoadCompanies(), 50);
    }
}

function _renderIngStep1(conns) {
    return `
        <h6 class="mb-3"><i class="fas fa-upload me-2"></i>1. Upload do Arquivo</h6>
        <div class="row g-3">
            <div class="col-md-5">
                <label class="form-label fw-bold">Conexao de Destino</label>
                <select id="ing-target-conn" class="form-select" onchange="_ingLoadCompanies()">
                    <option value="">Selecione...</option>
                    ${conns.map(c => `<option value="${c.id}" ${_ingTargetConn == c.id ? 'selected' : ''}>${c.name} (${c.driver})</option>`).join('')}
                </select>
            </div>
            <div class="col-md-4">
                <label class="form-label fw-bold">Empresa</label>
                <select id="ing-company-code" class="form-select">
                    <option value="">Selecione a conexao primeiro</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label fw-bold">Formato</label>
                <div class="form-text">JSON ou Markdown — auto-detectado</div>
            </div>
        </div>
        <div class="mt-3">
            <label class="form-label fw-bold">Arquivo de Ingestao</label>
            <div class="border rounded p-4 text-center bg-light" id="ing-dropzone"
                 ondragover="event.preventDefault(); this.classList.add('border-primary')"
                 ondragleave="this.classList.remove('border-primary')"
                 ondrop="event.preventDefault(); this.classList.remove('border-primary'); ingHandleDrop(event)">
                <i class="fas fa-cloud-upload-alt fa-3x text-muted mb-2"></i>
                <p class="mb-1">Arraste o arquivo aqui ou</p>
                <input type="file" id="ing-file-input" accept=".json,.md,.markdown" class="d-none" onchange="ingHandleFileSelect(event)">
                <button class="btn btn-outline-primary btn-sm" onclick="document.getElementById('ing-file-input').click()">
                    <i class="fas fa-folder-open me-1"></i>Selecionar Arquivo
                </button>
                <div id="ing-file-info" class="mt-2 text-muted small"></div>
            </div>
        </div>
        <div class="mt-3">
            <details>
                <summary class="text-muted small cursor-pointer">Ou cole o conteudo diretamente</summary>
                <textarea id="ing-paste-content" class="form-control mt-2 font-monospace" rows="8"
                    placeholder='Cole aqui o conteudo JSON ou Markdown...'></textarea>
                <button class="btn btn-outline-secondary btn-sm mt-2" onclick="ingParsePasted()">
                    <i class="fas fa-check me-1"></i>Processar Conteudo
                </button>
            </details>
        </div>
        <div id="ing-upload-result" class="mt-3"></div>
    `;
}

function _renderIngStep2() {
    if (!_ingParsedData || !_ingUploadedItems.length) {
        return '<div class="alert alert-warning">Nenhum item carregado. Volte ao passo 1.</div>';
    }

    const meta = _ingParsedData.metadata || {};
    let itemsHtml = '';

    _ingUploadedItems.forEach((item, idx) => {
        const t = item.type;
        let label = '';
        let icon = '';
        if (t === 'field') {
            label = `Campo ${item.table_alias}.${item.field_name}`;
            icon = 'fa-columns';
        } else if (t === 'field_diff') {
            label = `Atualizar ${item.table_alias}.${item.field_name}`;
            icon = 'fa-edit';
        } else if (t === 'index') {
            label = `Indice ${item.indice} Ordem ${item.ordem}`;
            icon = 'fa-sort-amount-down';
        } else if (t === 'full_table') {
            label = `Tabela ${item.table_alias} (completa)`;
            icon = 'fa-table';
        } else if (t === 'metadata') {
            label = `Metadado ${item.meta_table}: ${item.key || ''}`;
            icon = 'fa-database';
        } else if (t === 'metadata_diff') {
            label = `Atualizar ${item.meta_table}: ${item.key || ''}`;
            icon = 'fa-edit';
        }

        itemsHtml += `
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="ing-item-${idx}" checked
                    onchange="_ingUploadedItems[${idx}]._selected = this.checked">
                <label class="form-check-label" for="ing-item-${idx}">
                    <i class="fas ${icon} me-1 text-primary"></i>${label}
                </label>
            </div>
        `;
    });

    return `
        <h6 class="mb-3"><i class="fas fa-check-square me-2"></i>2. Selecionar Itens</h6>
        ${meta.source_environment ? `<div class="alert alert-info small"><strong>Origem:</strong> ${meta.source_environment} | <strong>Driver:</strong> ${meta.source_driver || '?'} | <strong>Empresa no arquivo:</strong> ${meta.company_code || '?'}</div>` : ''}
        <div class="mb-2">
            <button class="btn btn-outline-secondary btn-sm me-1" onclick="ingSelectAll(true)">Marcar Todos</button>
            <button class="btn btn-outline-secondary btn-sm" onclick="ingSelectAll(false)">Desmarcar Todos</button>
        </div>
        <div class="border rounded p-3" style="max-height: 400px; overflow-y: auto;">
            ${itemsHtml}
        </div>
        <div class="mt-3 d-flex justify-content-between">
            <button class="btn btn-secondary" onclick="ingWizardBack()">
                <i class="fas fa-arrow-left me-1"></i>Voltar
            </button>
            <button class="btn btn-primary" onclick="ingWizardPreview()">
                <i class="fas fa-eye me-1"></i>Gerar Preview
            </button>
        </div>
    `;
}

function _renderIngStep3() {
    if (!_ingPreviewData) {
        return '<div class="alert alert-warning">Preview nao gerado. Volte ao passo 2.</div>';
    }

    const p = _ingPreviewData;
    const summary = p.summary || {};
    const warns = p.warnings || [];
    const ddl = p.phase1_ddl || [];
    const dml = p.phase2_dml || [];

    let summaryHtml = `
        <div class="row g-2 mb-3">
            ${summary.fields ? `<div class="col"><span class="badge bg-primary">${summary.fields} campos</span></div>` : ''}
            ${summary.indexes ? `<div class="col"><span class="badge bg-success">${summary.indexes} indices</span></div>` : ''}
            ${summary.tables ? `<div class="col"><span class="badge bg-info">${summary.tables} tabelas</span></div>` : ''}
            ${summary.metadata ? `<div class="col"><span class="badge bg-secondary">${summary.metadata} metadados</span></div>` : ''}
            ${summary.skipped_duplicates ? `<div class="col"><span class="badge bg-warning text-dark">${summary.skipped_duplicates} ignorados (duplicatas)</span></div>` : ''}
        </div>
    `;

    let warnsHtml = '';
    if (warns.length > 0) {
        warnsHtml = `<div class="alert alert-warning small"><strong>Avisos (${warns.length}):</strong><ul class="mb-0 mt-1">${warns.map(w => `<li>${w}</li>`).join('')}</ul></div>`;
    }

    let sqlHtml = '';
    const allStmts = [...ddl, ...dml];
    if (allStmts.length > 0) {
        sqlHtml = `
            <div class="accordion" id="ing-sql-accordion">
                <div class="accordion-item">
                    <h2 class="accordion-header">
                        <button class="accordion-button collapsed small" type="button" data-bs-toggle="collapse" data-bs-target="#ing-sql-body">
                            <i class="fas fa-code me-2"></i>SQLs a executar (${allStmts.length})
                        </button>
                    </h2>
                    <div id="ing-sql-body" class="accordion-collapse collapse">
                        <div class="accordion-body p-2" style="max-height: 400px; overflow-y: auto;">
                            <table class="table table-sm table-hover small">
                                <thead><tr><th>Fase</th><th>Descricao</th><th>SQL</th></tr></thead>
                                <tbody>
                                    ${allStmts.map(s => `<tr><td><span class="badge bg-${s.phase === 1 ? 'primary' : 'success'}">F${s.phase}</span></td><td>${s.description}</td><td class="font-monospace text-break" style="max-width:400px; white-space: pre-wrap;">${s.sql}</td></tr>`).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    return `
        <h6 class="mb-3"><i class="fas fa-eye me-2"></i>3. Preview</h6>
        ${summaryHtml}
        ${warnsHtml}
        ${sqlHtml}
        ${allStmts.length === 0 ? '<div class="alert alert-info">Nenhum SQL gerado — todos os itens ja existem no destino ou foram ignorados.</div>' : ''}
        <div class="mt-3 d-flex justify-content-between">
            <button class="btn btn-secondary" onclick="ingWizardBack()">
                <i class="fas fa-arrow-left me-1"></i>Voltar
            </button>
            ${allStmts.length > 0 ? `
                <button class="btn btn-danger" onclick="ingExecute()">
                    <i class="fas fa-play me-1"></i>Executar Ingestao (${allStmts.length} SQLs)
                </button>
            ` : ''}
        </div>
    `;
}

function _renderIngStep4() {
    // Se ja tem resultado salvo (re-render apos navegacao), mostra ele
    if (_ingExecutionResult) {
        return `
            <h6 class="mb-3"><i class="fas fa-check-circle me-2 text-success"></i>4. Resultado</h6>
            <div id="ing-result-content">${_ingExecutionResult}</div>
        `;
    }
    return `
        <h6 class="mb-3"><i class="fas fa-check-circle me-2 text-success"></i>4. Resultado</h6>
        <div id="ing-result-content">
            <div class="text-center py-4">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-2">Executando ingestao...</p>
            </div>
        </div>
    `;
}

// --- Carregar empresas (reutiliza _dictLoadCompanies/_dictPopulateCompanySelect) ---

function _ingLoadCompanies() {
    const connId = document.getElementById('ing-target-conn')?.value;
    const selectEl = document.getElementById('ing-company-code');
    if (!connId || !selectEl) {
        if (selectEl) selectEl.innerHTML = '<option value="">Selecione a conexao primeiro</option>';
        return;
    }
    _dictLoadCompanies(connId, selectEl);
}

// --- Upload handlers ---

async function ingHandleDrop(event) {
    const files = event.dataTransfer.files;
    if (files.length > 0) await ingProcessFile(files[0]);
}

async function ingHandleFileSelect(event) {
    const files = event.target.files;
    if (files.length > 0) await ingProcessFile(files[0]);
}

async function ingProcessFile(file) {
    const infoEl = document.getElementById('ing-file-info');
    const resultEl = document.getElementById('ing-upload-result');
    if (infoEl) infoEl.innerHTML = `<i class="fas fa-file me-1"></i>${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

    try {
        // Ler arquivo como texto e enviar via apiRequest (evita problemas de auth com FormData)
        const content = await file.text();

        const data = await apiRequest('/dictionary/ingest/upload', 'POST', {
            content: content,
            filename: file.name,
        });

        if (data.error) {
            if (resultEl) resultEl.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
            return;
        }

        _ingParsedData = data;
        _ingUploadedItems = (data.items || []).map(it => ({ ...it, _selected: true }));

        const types = data.item_types || {};
        let typesStr = Object.entries(types).map(([k, v]) => `${v} ${k}`).join(', ');

        if (resultEl) {
            resultEl.innerHTML = `
                <div class="alert alert-success">
                    <strong>Arquivo processado:</strong> ${data.item_count} itens (${typesStr})
                    ${data.parse_warnings?.length ? `<br><small class="text-warning">${data.parse_warnings.length} avisos de parse</small>` : ''}
                </div>
                <button class="btn btn-primary" onclick="ingWizardNext()">
                    <i class="fas fa-arrow-right me-1"></i>Selecionar Itens
                </button>
            `;
        }
    } catch (e) {
        if (resultEl) resultEl.innerHTML = `<div class="alert alert-danger">Erro: ${e.message}</div>`;
    }
}

async function ingParsePasted() {
    const content = document.getElementById('ing-paste-content')?.value || '';
    if (!content.trim()) {
        showNotification('Cole o conteudo do arquivo primeiro.', 'warning');
        return;
    }

    const resultEl = document.getElementById('ing-upload-result');
    try {
        const resp = await apiRequest('/dictionary/ingest/upload', 'POST', {
            content: content,
            filename: content.trim().startsWith('{') ? 'paste.json' : 'paste.md',
        });

        if (resp.error) {
            if (resultEl) resultEl.innerHTML = `<div class="alert alert-danger">${resp.error}</div>`;
            return;
        }

        _ingParsedData = resp;
        _ingUploadedItems = (resp.items || []).map(it => ({ ...it, _selected: true }));

        const types = resp.item_types || {};
        let typesStr = Object.entries(types).map(([k, v]) => `${v} ${k}`).join(', ');

        if (resultEl) {
            resultEl.innerHTML = `
                <div class="alert alert-success">
                    <strong>Conteudo processado:</strong> ${resp.item_count} itens (${typesStr})
                </div>
                <button class="btn btn-primary" onclick="ingWizardNext()">
                    <i class="fas fa-arrow-right me-1"></i>Selecionar Itens
                </button>
            `;
        }
    } catch (e) {
        if (resultEl) resultEl.innerHTML = `<div class="alert alert-danger">Erro: ${e.message}</div>`;
    }
}

// --- Wizard navigation ---

function ingWizardNext() {
    // Validar conexao e empresa no step 1
    if (_ingWizardStep === 1) {
        _ingTargetConn = document.getElementById('ing-target-conn')?.value;
        _ingCompanyCode = document.getElementById('ing-company-code')?.value;
        if (!_ingTargetConn) {
            showNotification('Selecione a conexao de destino.', 'warning');
            return;
        }
        if (!_ingCompanyCode) {
            showNotification('Selecione a empresa.', 'warning');
            return;
        }
        if (!_ingParsedData || !_ingUploadedItems.length) {
            showNotification('Faca upload do arquivo primeiro.', 'warning');
            return;
        }
    }
    _ingWizardStep++;
    _renderIngestorTab();
}

function ingWizardBack() {
    if (_ingWizardStep > 1) {
        _ingWizardStep--;
        _renderIngestorTab();
    }
}

function ingSelectAll(checked) {
    _ingUploadedItems.forEach((it, idx) => {
        it._selected = checked;
        const el = document.getElementById(`ing-item-${idx}`);
        if (el) el.checked = checked;
    });
}

async function ingWizardPreview() {
    const selectedItems = _ingUploadedItems.filter(it => it._selected !== false);
    if (selectedItems.length === 0) {
        showNotification('Selecione ao menos um item.', 'warning');
        return;
    }

    showNotification('Gerando preview...', 'info');

    try {
        const resp = await apiRequest('/dictionary/ingest/preview', 'POST', {
            target_conn_id: parseInt(_ingTargetConn),
            company_code: _ingCompanyCode,
            items: selectedItems,
            metadata: _ingParsedData?.metadata || {},
        });

        if (resp.error) {
            showNotification(resp.error, 'error');
            return;
        }

        _ingPreviewData = resp;
        _ingWizardStep = 3;
        _renderIngestorTab();
    } catch (e) {
        showNotification(`Erro ao gerar preview: ${e.message}`, 'error');
    }
}

async function ingExecute() {
    if (!_ingPreviewData || !_ingPreviewData.confirmation_token) {
        showNotification('Preview invalido. Gere novamente.', 'error');
        return;
    }

    if (!confirm('Confirma a execucao da ingestao? Esta operacao ira modificar o banco de destino.')) {
        return;
    }

    _ingWizardStep = 4;
    _renderIngestorTab();

    const allStmts = [...(_ingPreviewData.phase1_ddl || []), ...(_ingPreviewData.phase2_dml || [])];

    try {
        const resp = await apiRequest('/dictionary/ingest/execute', 'POST', {
            target_conn_id: parseInt(_ingTargetConn),
            company_code: _ingCompanyCode,
            sql_statements: allStmts,
            confirmation_token: _ingPreviewData.confirmation_token,
            file_metadata: _ingParsedData?.metadata || {},
        });

        const resultEl = document.getElementById('ing-result-content');
        if (!resultEl) return;

        if (resp.success) {
            const status = resp.status === 'partial' ? 'warning' : 'success';
            const statusText = resp.status === 'partial' ? 'Parcial (TcRefresh falhou)' : 'Sucesso';
            const tcr = resp.tcrefresh || {};

            const html = `
                <div class="alert alert-${status}">
                    <h6><i class="fas fa-check-circle me-2"></i>Ingestao executada: ${statusText}</h6>
                    <ul class="mb-0">
                        <li><strong>${resp.executed}</strong> statements executados</li>
                        <li>Duracao: <strong>${resp.duration_ms}ms</strong></li>
                        ${resp.history_id ? `<li>Historico: #${resp.history_id}</li>` : ''}
                        ${tcr.called ? `<li>TcRefresh: ${tcr.success ? 'OK' : 'Falhou'} (${(tcr.tables || []).length} tabelas)</li>` : ''}
                    </ul>
                </div>
                <button class="btn btn-secondary" onclick="_ingResetWizard()">
                    <i class="fas fa-redo me-1"></i>Nova Ingestao
                </button>
            `;
            _ingExecutionResult = html;
            resultEl.innerHTML = html;
        } else {
            const html = `
                <div class="alert alert-danger">
                    <h6><i class="fas fa-times-circle me-2"></i>Erro na Ingestao</h6>
                    <p>${resp.error || 'Erro desconhecido'}</p>
                    ${resp.executed_before_error ? `<p>${resp.executed_before_error} statements executados antes do erro (ROLLBACK aplicado).</p>` : ''}
                </div>
                <button class="btn btn-secondary" onclick="ingWizardBack()">
                    <i class="fas fa-arrow-left me-1"></i>Voltar ao Preview
                </button>
            `;
            _ingExecutionResult = html;
            resultEl.innerHTML = html;
        }
    } catch (e) {
        const resultEl = document.getElementById('ing-result-content');
        if (resultEl) {
            const html = `<div class="alert alert-danger">Erro: ${e.message}</div>
                <button class="btn btn-secondary" onclick="ingWizardBack()"><i class="fas fa-arrow-left me-1"></i>Voltar</button>`;
            _ingExecutionResult = html;
            resultEl.innerHTML = html;
        }
    }
}

function _ingResetWizard() {
    _ingWizardStep = 1;
    _ingParsedData = null;
    _ingUploadedItems = [];
    _ingPreviewData = null;
    _ingExecutionResult = null;
    _renderIngestorTab();
}
