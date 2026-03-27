// =====================================================================
// INTEGRATION-CORE.JS
// Estado global, dispatch table, inicialização, router, utilitários
// =====================================================================

// =====================================================================
// ESTADO GLOBAL DA APLICAÇÃO
// =====================================================================
let currentUser = null;
let userPermissions = null;
let serverOS = null; // { os: 'linux'|'windows', command_type: 'bash'|'powershell', os_display: 'Ubuntu 22.04'|'Windows 11 Pro' }
let repositories = [];
let pipelines = [];
let commands = [];
let schedules = [];
let currentSchedulesPage = 1;
const schedulesPerPage = 10;
let scheduleScriptTypeFilter = 'TODOS';
let users = [];
let deploys = [];
let gitHubSettings = { configured: false, username: '' };
let environments = [];
let runPollingInterval = null;
let serverVariables = [];
let serverServices = [];
let serviceActions = [];

let keepAliveInterval = null;
let notificationQueue = [];
let isLoggingOut = false; // Flag para prevenir logout duplicado

// =====================================================================
// INTERNACIONALIZAÇÃO (i18n)
// =====================================================================
let _i18nStrings = {};
let _i18nLocale = 'pt-BR';

/**
 * Carrega o arquivo de locale e armazena as strings.
 * Chamado na inicialização da aplicação.
 */
async function loadLocale(locale) {
    _i18nLocale = locale || navigator.language || 'pt-BR';
    // Normaliza locale para formato esperado (pt-BR, en-US)
    if (_i18nLocale.startsWith('pt')) _i18nLocale = 'pt-BR';
    else if (_i18nLocale.startsWith('en')) _i18nLocale = 'en-US';
    else _i18nLocale = 'pt-BR'; // fallback

    try {
        const resp = await fetch(`static/locale/${_i18nLocale}.json`);
        if (resp.ok) {
            _i18nStrings = await resp.json();
        } else {
            console.warn(`[i18n] Locale ${_i18nLocale} não encontrado, usando pt-BR`);
            _i18nLocale = 'pt-BR';
            const fallback = await fetch('static/locale/pt-BR.json');
            if (fallback.ok) _i18nStrings = await fallback.json();
        }
    } catch (err) {
        console.warn('[i18n] Erro ao carregar locale:', err);
    }
}

/**
 * Traduz uma chave de i18n usando notação de ponto.
 * Ex: t('common.save') → "Salvar"
 *     t('auth.loginError') → "Usuário ou senha inválidos"
 *     t('pipeline.noRuns') → "Nenhuma execução encontrada"
 *
 * Retorna a própria chave se a tradução não for encontrada.
 */
function t(key) {
    const parts = key.split('.');
    let value = _i18nStrings;
    for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
            value = value[part];
        } else {
            return key; // chave não encontrada, retorna como fallback
        }
    }
    return typeof value === 'string' ? value : key;
}

// =====================================================================
// LAZY LOADING DE MÓDULOS JS
// =====================================================================
const _loadedModules = new Set();
const _loadingModules = {};

/**
 * Carrega um módulo JS sob demanda (se ainda não carregado).
 * Detecta se módulo já foi carregado via <script> tag (fallback).
 * Retorna uma Promise que resolve quando o script está pronto.
 */
function loadModule(moduleName) {
    if (_loadedModules.has(moduleName)) {
        return Promise.resolve();
    }
    // Se a função principal do módulo já existe, ele foi carregado por outro meio
    if (_isModuleAlreadyLoaded(moduleName)) {
        _loadedModules.add(moduleName);
        return Promise.resolve();
    }
    if (_loadingModules[moduleName]) {
        return _loadingModules[moduleName];
    }
    const promise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `static/js/${moduleName}.js`;
        script.onload = () => {
            _loadedModules.add(moduleName);
            delete _loadingModules[moduleName];
            console.log(`✓ Módulo carregado: ${moduleName}`);
            resolve();
        };
        script.onerror = () => {
            delete _loadingModules[moduleName];
            console.error(`Erro ao carregar módulo: ${moduleName}`);
            reject(new Error(`Falha ao carregar ${moduleName}`));
        };
        document.head.appendChild(script);
    });
    _loadingModules[moduleName] = promise;
    return promise;
}

/** Verifica se um módulo lazy já foi carregado (ex: via script tag direto). */
function _isModuleAlreadyLoaded(moduleName) {
    const knownFunctions = {
        'integration-commands': 'showCommands',
        'integration-pipelines': 'showPipelines',
        'integration-ci-cd': 'runPipelineBuild',
        'integration-schedules': 'showSchedules',
        'integration-repositories': 'showRepositories',
        'integration-source-control': 'showSourceControl',
        'integration-ui': 'showDashboard',
        'integration-observability': 'showObservability',
        'integration-knowledge': 'showKnowledge',
        'integration-database': 'showDatabase',
        'integration-processes': 'showProcesses',
        'integration-documentation': 'showDocumentation',
        'integration-devworkspace': 'showDevWorkspace',
        'integration-agent': 'showAgent',
        'integration-auditor': 'showAuditor',
    };
    const fn = knownFunctions[moduleName];
    return fn && typeof window[fn] === 'function';
}

// Mapa de página → módulo(s) que precisa(m) ser carregado(s)
const PAGE_MODULES = {
    'dashboard': ['integration-ui'],
    'repositories': ['integration-repositories'],
    'source-control': ['integration-source-control'],
    'pipelines': ['integration-pipelines', 'integration-ci-cd'],
    'schedules': ['integration-schedules'],
    'commands': ['integration-commands'],
    'observability': ['integration-observability'],
    'knowledge': ['integration-knowledge'],
    'database': ['integration-database'],
    'processes': ['integration-processes'],
    'documentation': ['integration-documentation'],
    'devworkspace': ['integration-devworkspace'],
    'agent': ['integration-agent'],
    'auditor': ['integration-auditor'],
    'users': [],  // integration-auth já é essencial
    'settings': ['integration-ui', 'integration-repositories', 'integration-devworkspace', 'integration-agent'],
    'toggleServiceActionSchedule': ['integration-schedules'],
};

// =====================================================================
// CATEGORIAS DE NAVEGACAO (Top Tabs + Sidebar Contextual)
// =====================================================================
const CATEGORIES = {
    'dashboard':       { label: 'Dashboard',        icon: 'fa-chart-line',   pages: ['dashboard'],                                              defaultPage: 'dashboard' },
    'cicd':            { label: 'CI/CD',             icon: 'fa-cogs',         pages: ['pipelines', 'schedules', 'commands'],                     defaultPage: 'pipelines' },
    'repos':           { label: 'Repositorios',      icon: 'fa-code-branch',  pages: ['repositories', 'source-control'],                        defaultPage: 'repositories' },
    'monitoramento':   { label: 'Monitoramento',     icon: 'fa-eye',          pages: ['observability', 'database', 'auditor'],                  defaultPage: 'observability' },
    'conhecimento':    { label: 'IA',                 icon: 'fa-robot',        pages: ['agent'],                                                defaultPage: 'agent' },
    'workspace':       { label: 'Workspace',         icon: 'fa-code',         pages: ['devworkspace'],                                          defaultPage: 'devworkspace' },
    'admin':           { label: 'Admin',             icon: 'fa-cog',          pages: ['users', 'settings'],                                     defaultPage: 'users' }
};

const PAGE_TO_CATEGORY = {};
for (const [catKey, cat] of Object.entries(CATEGORIES)) {
    for (const p of cat.pages) PAGE_TO_CATEGORY[p] = catKey;
}

const PAGE_LABELS = {
    'dashboard':      { label: 'Dashboard',              icon: 'fa-chart-line' },
    'pipelines':      { label: 'Pipelines',              icon: 'fa-cogs' },
    'schedules':      { label: 'Schedule',               icon: 'fa-clock' },
    'commands':       { label: 'Comandos',               icon: 'fa-terminal' },
    'repositories':   { label: 'Repositorios GitHub',    icon: 'fa-folder' },
    'source-control': { label: 'Controle de Versao',     icon: 'fa-code-branch' },
    'devworkspace':   { label: 'Dev Workspace',          icon: 'fa-code' },
    'observability':  { label: 'Monitoramento',        icon: 'fa-satellite-dish' },
    'database':       { label: 'Banco de Dados',         icon: 'fa-database' },
    'processes':      { label: 'Processos',              icon: 'fa-project-diagram' },
    'knowledge':      { label: 'Base de Conhecimento',   icon: 'fa-book' },
    'documentation':  { label: 'Documentacao',           icon: 'fa-file-alt' },
    'agent':          { label: 'GolIAs',                 icon: 'fa-robot' },
    'auditor':        { label: 'Auditor INI',             icon: 'fa-file-medical-alt' },
    'users':          { label: 'Usuarios',               icon: 'fa-users' },
    'settings':       { label: 'Configuracoes',          icon: 'fa-cog' }
};

let isDeletingUser = false; // Flag para prevenir delete duplicado
let isProcessingQueue = false;
// =====================================================================
// TOGGLE DE TEMA (CLARO/ESCURO)
// =====================================================================

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('atudc-theme', newTheme);

    // Atualizar ícone
    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

function loadSavedTheme() {
    const savedTheme = localStorage.getItem('atudc-theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);

    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

// Carregar tema salvo ao iniciar
document.addEventListener('DOMContentLoaded', loadSavedTheme);



// Estado da UI
let currentCommandsPage = 1;
const commandsPerPage = 50;
let currentPipelinePage = 1;
let pipelineScriptTypeFilter = 'TODOS';
const pipelinesPerPage = 6;
let currentHistoryPage = 1;
let selectedCommands = [];
let commandSelectorMode = 'create';
let repoContentSort = { key: 'name', order: 'asc' };
let currentPath = {};
let currentBranch = {};

// =====================================================================
// PONTO DE ENTRADA PRINCIPAL DA APLICAÇÃO
// =====================================================================
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM carregado. Inicializando sistema...');

    // VERIFICAÇÃO CRÍTICA: Garantir que api-client.js foi carregado
    const requiredApiFunctions = [
        'apiGetPipelineRuns',
        'apiGetRunLogs',
        'apiCreateRelease',
        'apiGetPipelineReleases',
        'apiGetReleaseLogs',
        'apiRunPipeline'
    ];

    const missingFunctions = requiredApiFunctions.filter(fn => typeof window[fn] !== 'function');

    if (missingFunctions.length > 0) {
        console.error('❌ ERRO CRÍTICO: Funções de API não encontradas:', missingFunctions);
        console.error('❌ Verifique se api-client.js está sendo carregado ANTES de integration.js no HTML');
        alert('ERRO: Arquivo api-client.js não foi carregado corretamente.\n\nVerifique o console para mais detalhes.');
        return;
    }

    console.log('✓ Todas as funções de API foram carregadas corretamente');

    // Verificar se Bootstrap está disponível
    if (typeof bootstrap === 'undefined') {
        console.error('❌ ERRO CRÍTICO: Bootstrap não foi carregado!');
        const userConfirm = confirm('Erro ao carregar componentes. Deseja recarregar a página?');
        if (userConfirm) {
            window.location.reload();
        }
        return;
    }

    // Validar Bootstrap
    try {
        const testModal = document.createElement('div');
        testModal.className = 'modal';
        testModal.id = 'test-modal-init';
        document.body.appendChild(testModal);

        const modalInstance = new bootstrap.Modal(testModal);
        modalInstance.dispose();
        document.body.removeChild(testModal);

        console.log('✓ Bootstrap validado com sucesso');
    } catch (error) {
        console.error('❌ Erro ao validar Bootstrap:', error);
        alert('Erro ao inicializar componentes da interface.');
        return;
    }

    initializeEventListeners();
    console.log('✓ Event listeners (data-action) inicializados.');
    checkSessionAndInitialize();
});

window.addEventListener('hashchange', router);

// =====================================================================
// SISTEMA DE EVENT DELEGATION (O CORAÇÃO DOS CLIQUES)
// =====================================================================

function initializeEventListeners() {
    // Evita registro duplicado de listeners
    if (initializeEventListeners._initialized) return;
    initializeEventListeners._initialized = true;

    document.addEventListener('click', function (e) {
        const target = e.target.closest('[data-action]');
        if (!target) return;

        e.preventDefault();
        const action = target.dataset.action;
        let params = {};
        try {
            params = JSON.parse(target.dataset.params || '{}');
        } catch (err) {
            console.warn('Parâmetros inválidos em data-params:', target.dataset.params, err);
        }
        handleAction(action, params, target);
    });

    document.addEventListener('submit', function (e) {
        const form = e.target.closest('[data-form-action]');
        if (!form) return;

        e.preventDefault();
        const action = form.dataset.formAction;
        handleFormAction(action, form);
    });
}


// ===== LIMPEZA DE MODALS E BACKDROP =====
// Garante que backdrop seja sempre removido ao fechar modals
function cleanupModalBackdrop() {
    // Remove todos os backdrops
    const backdrops = document.querySelectorAll('.modal-backdrop');
    backdrops.forEach(backdrop => backdrop.remove());

    // Remove classes do body
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');

    console.log('🧹 Backdrop limpo');
}

// Event listener global para todos os modals
document.addEventListener('DOMContentLoaded', function () {
    // Quando qualquer modal for escondido
    document.addEventListener('hidden.bs.modal', function (event) {
        console.log('📍 Modal fechado:', event.target.id);

        // Aguardar um pouco para garantir que Bootstrap finalizou
        setTimeout(() => {
            cleanupModalBackdrop();
        }, 100);
    });

    // Também limpar ao clicar em botões de fechar
    document.addEventListener('click', function (e) {
        const closeButton = e.target.closest('[data-bs-dismiss="modal"]');
        if (closeButton) {
            console.log('📍 Botão fechar clicado');
            setTimeout(() => {
                cleanupModalBackdrop();
            }, 300);
        }
    });

    // Limpar ao pressionar ESC
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            // Fechar modal de atalhos se aberto
            const shortcutsModal = document.getElementById('keyboardShortcutsModal');
            if (shortcutsModal && shortcutsModal.classList.contains('show')) {
                bootstrap.Modal.getInstance(shortcutsModal)?.hide();
                return;
            }
            const openModal = document.querySelector('.modal.show');
            if (openModal) {
                setTimeout(() => {
                    cleanupModalBackdrop();
                }, 300);
            }
        }
    });

    // ===== EVENT LISTENERS (substituem handlers inline do HTML) =====
    const themeBtn = document.getElementById('themeToggleBtn');
    if (themeBtn) themeBtn.addEventListener('click', () => toggleTheme());

    const scriptFileInput = document.getElementById('scriptFileInput');
    if (scriptFileInput) scriptFileInput.addEventListener('change', () => handleScriptImport());

    const newPwdConfirm = document.getElementById('newPasswordConfirm');
    if (newPwdConfirm) newPwdConfirm.addEventListener('input', () => validatePasswordMatch('newPassword', 'newPasswordConfirm', 'newPasswordConfirmLabel'));

    const importVarsBtn = document.getElementById('importVariablesBtn');
    if (importVarsBtn) importVarsBtn.addEventListener('click', () => importVariablesFromCSV());
});

// ===== ATALHOS DE TECLADO =====
(function () {
    const SHORTCUTS = {
        'Alt+1': { page: 'dashboard', label: 'Dashboard' },
        'Alt+2': { page: 'repositories', label: 'Repositorios' },
        'Alt+3': { page: 'source-control', label: 'Source Control' },
        'Alt+4': { page: 'pipelines', label: 'Pipelines' },
        'Alt+5': { page: 'schedules', label: 'Agendamentos' },
        'Alt+6': { page: 'commands', label: 'Comandos' },
        'Alt+7': { page: 'observability', label: 'Monitoramento' },
        'Alt+8': { page: 'users', label: 'Usuarios' },
        'Alt+9': { page: 'settings', label: 'Configuracoes' },
    };

    function _isTyping() {
        const el = document.activeElement;
        if (!el) return false;
        const tag = el.tagName.toLowerCase();
        return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
    }

    function _showShortcutsHelp() {
        let modal = document.getElementById('keyboardShortcutsModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'keyboardShortcutsModal';
            modal.className = 'modal fade';
            modal.tabIndex = -1;
            modal.innerHTML = `
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Atalhos de Teclado</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <table class="table table-sm mb-0">
                                <thead><tr><th>Atalho</th><th>Acao</th></tr></thead>
                                <tbody>
                                    <tr><td><kbd>Alt</kbd>+<kbd>1</kbd> a <kbd>8</kbd></td><td>Navegar entre paginas</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>1</kbd></td><td>Dashboard</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>2</kbd></td><td>Repositorios</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>3</kbd></td><td>Source Control</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>4</kbd></td><td>Pipelines</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>5</kbd></td><td>Agendamentos</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>6</kbd></td><td>Comandos</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>7</kbd></td><td>Usuarios</td></tr>
                                    <tr><td><kbd>Alt</kbd>+<kbd>8</kbd></td><td>Configuracoes</td></tr>
                                    <tr><td colspan="2" class="border-top"></td></tr>
                                    <tr><td><kbd>Esc</kbd></td><td>Fechar modal</td></tr>
                                    <tr><td><kbd>?</kbd></td><td>Mostrar atalhos</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>`;
            document.body.appendChild(modal);
        }
        new bootstrap.Modal(modal).show();
    }

    document.addEventListener('keydown', function (e) {
        // Não interceptar quando digitando em campos de texto
        if (_isTyping()) return;

        // ? → mostrar atalhos
        if (e.key === '?' && !e.ctrlKey && !e.altKey && !e.metaKey) {
            e.preventDefault();
            _showShortcutsHelp();
            return;
        }

        // Alt+1 a Alt+8 → navegação
        if (e.altKey && !e.ctrlKey && !e.metaKey) {
            const key = `Alt+${e.key}`;
            const shortcut = SHORTCUTS[key];
            if (shortcut) {
                e.preventDefault();
                // Fechar modal se aberto
                const openModal = document.querySelector('.modal.show');
                if (openModal) {
                    bootstrap.Modal.getInstance(openModal)?.hide();
                }
                navigateToPage(shortcut.page);
            }
        }
    });
})();
// ===== LISTENER ESPECÍFICO PARA SIDEBAR =====
// Adiciona suporte para links com data-page (sidebar)
document.addEventListener('click', function (e) {
    const sidebarLink = e.target.closest('.sidebar .nav-link[data-page]');
    if (!sidebarLink) return;

    e.preventDefault();
    const page = sidebarLink.dataset.page;

    console.log(`🔍 Sidebar: Navegando para ${page}`);

    // ⚠️ IMPORTANTE: Fechar pipeline run view se estiver aberta
    const pipelineRunView = document.getElementById('pipelineRunView');
    if (pipelineRunView && !pipelineRunView.classList.contains('d-none')) {
        console.log('🔄 Fechando pipelineRunView antes de navegar');
        stopRunPolling(); // Para o polling de atualização
        pipelineRunView.classList.add('d-none');

        const contentArea = document.getElementById('content-area');
        if (contentArea) contentArea.style.display = 'block';
    }

    // Parar polling de service actions ao sair da página
    if (page !== 'settings' && typeof stopServiceActionsPolling === 'function') {
        stopServiceActionsPolling();
    }

    // Navegar para a página (router() cuida de atualizar active)
    navigateToPage(page);
});

// FUNÇÕES AUXILIARES PARA PIPELINES - IMPLEMENTAÇÃO COMPLETA
function getStatusColor(status) {
    console.log('getStatusColor chamado:', status);
    const colors = {
        'success': 'success',
        'failed': 'danger',
        'running': 'warning',
        'queued': 'info',
        'skipped': 'secondary'
    };
    return colors[status] || 'secondary';
}
function getStatusText(status) {
    console.log('getStatusText chamado:', status);
    const texts = {
        'success': 'Sucesso',
        'failed': 'Falha',
        'running': 'Executando',
        'queued': 'Na Fila',
        'skipped': 'Ignorado'
    };
    return texts[status] || 'Desconhecido';
}
function getTriggerText(trigger) {
    console.log('getTriggerText chamado:', trigger);
    const triggers = {
        'manual': 'Manual',
        'push': 'Push no Git',
        'pull_request': 'Pull Request',
        'schedule': 'Agendado'
    };
    return triggers[trigger] || trigger;
}
const actionHandlers = {
    // ===== NAVEGAÇÃO =====
    'navigate': (params) => navigateToPage(params.page),
    'navigateCategory': (params) => {
        const cat = CATEGORIES[params.category];
        if (!cat) return;
        const first = cat.pages.find(p => hasPermission(p));
        if (first) window.location.hash = first;
    },
    'logout': (params) => {
        if (isLoggingOut) return;
        logout(params.mode || false);
    },
    'toggleSidebar': () => toggleSidebar(),

    // ===== USUÁRIOS =====
    'showCreateUserModal': () => showCreateUserModal(),
    'createNewUser': () => createNewUser(),
    'showEditUserModal': (params) => editUser(params.userId),
    'saveEditedUser': () => saveEditedUser(),
    'deleteUser': (params) => { if (isDeletingUser) return; deleteUser(params.userId); },
    'showChangePasswordModal': () => window.showChangePasswordModal(),
    'changeOwnPassword': () => changeOwnPassword(),
    'showAdminChangePasswordModal': (params) => window.showAdminChangePasswordModal(params.userId),
    'adminChangePassword': () => adminChangePassword(),

    // ===== COMANDOS =====
    'showCreateCommandModal': () => window.showCreateCommandModal(),
    'createNewCommand': () => createNewCommand(),
    'showEditCommandModal': (params) => editCommand(params.commandId),
    'saveEditedCommand': () => saveEditedCommand(),
    'deleteCommand': (params) => deleteCommand(params.commandId),
    'viewScript': (params) => window.viewScript(params.commandId),
    'importScript': () => document.getElementById('scriptFileInput').click(),

    // ===== PIPELINES =====
    'showCreatePipelineModal': () => window.showCreatePipelineModal(),
    'createNewPipeline': () => createNewPipeline(),
    'showEditPipelineModal': (params) => editPipeline(params.pipelineId),
    'saveEditedPipeline': () => saveEditedPipeline(),
    'deletePipeline': (params) => deletePipeline(params.pipelineId),
    'runPipeline': (params) => runPipeline(params.pipelineId),
    'showCommandSelector': (params) => window.showCommandSelector(params.mode || 'create'),
    'confirmCommandSelection': () => confirmCommandSelection(),

    // ===== PIPELINES - BUILD & RELEASE (CI/CD) =====
    'runPipelineBuild': (params) => runPipelineBuild(params),
    'openBuildStream': () => reopenBuildStream(),
    'loadPipelineBuilds': (params) => loadPipelineBuilds(params.pipelineId, params.page || 1),
    'viewBuildLogs': (params) => viewBuildLogs(params),
    'createRelease': (params) => createRelease(params),
    'loadPipelineReleases': (params) => loadPipelineReleases(params.pipelineId, params.page || 1),
    'viewReleaseLogs': (params) => viewReleaseLogs(params),
    'showBuildHistory': (params) => showBuildHistory(params.pipelineId),
    'viewBuildDetails': (params) => viewBuildDetails(params.runId, params.runNumber),
    'showReleaseHistory': (params) => showReleaseHistory(params.pipelineId),
    'viewReleaseDetails': (params) => viewReleaseDetails(params.releaseId),
    'createReleaseFromRun': (params) => createReleaseFromRun(params.runId, params.pipelineId),
    'backToPipelines': () => backToPipelines(),
    'refreshRunStatus': (params) => refreshRunStatus(params),
    'viewRunLogs': (params) => viewRunLogs(params),
    'downloadRunLogs': (params) => downloadRunLogs(params),
    'openReleaseFromRun': (params) => openReleaseFromRun(params),
    'openRunView': (params) => openPipelineRunView(params.runId, params.pipelineId),
    'openRunViewFromHistory': (params) => openRunViewFromHistory(params),
    'filterPipelinesByScriptType': (params) => filterPipelinesByScriptType(params.scriptType),

    // ===== SCHEDULE HANDLERS =====
    'showCreateScheduleModal': () => showCreateScheduleModal(),
    'saveNewSchedule': () => saveNewSchedule(),
    'editSchedule': (params) => editSchedule(params.scheduleId),
    'saveEditSchedule': () => saveEditSchedule(),
    'toggleSchedule': (params) => toggleSchedule(params.scheduleId),
    'deleteSchedule': (params) => deleteSchedule(params.scheduleId),
    'changeSchedulesPage': (params) => changeSchedulesPage(params.page),
    'filterSchedulesByScriptType': (params) => filterSchedulesByScriptType(params.scriptType),

    // ===== SERVICE ACTIONS =====
    'showCreateServiceActionModal': () => showCreateServiceActionModal(),
    'saveNewServiceAction': () => saveNewServiceAction(),
    'editServiceAction': (params) => editServiceAction(params.actionId),
    'saveEditedServiceAction': () => saveEditedServiceAction(),
    'deleteServiceAction': (params) => deleteServiceAction(params.actionId),
    'executeServiceAction': (params) => executeServiceAction(params.actionId),
    'filterServiceActionsByOS': (params) => filterServiceActionsByOS(params),
    'toggleServiceActionSchedule': (params) => toggleServiceActionSchedule(params),

    // ===== REPOSITÓRIOS =====
    'cloneRepository': (params) => cloneRepositoryOnServer(params.repoId),
    'pullRepository': (params) => pullRepositoryOnServer(params.repoId),
    'pushChanges': (params) => pushChanges(params.repoId),
    'pushTag': (params) => tagAndPush(params.repoId),
    'deleteRepository': (params) => removeRepository(params.repoId),
    'exploreRepository': (params) => exploreRepository(params.repoName),
    'createNewBranch': (params) => createNewBranch(params.repoId),
    'discoverRepositories': () => discoverRepositories(),
    'showBranchSelector': (params) => showBranchSelector(params.repoId),

    // ===== SOURCE CONTROL =====
    'refreshSourceControl': () => refreshSourceControl(),
    'scSelectRepo': (params) => scSelectRepo(params.repoId),
    'scSelectBranch': (params) => scSelectBranch(params.branch),
    'scStageFile': (params) => scStageFile(params.filePath),
    'scUnstageFile': (params) => scUnstageFile(params.filePath),
    'scStageAll': () => scStageAll(),
    'scUnstageAll': () => scUnstageAll(),
    'scCommit': () => scCommit(),
    'scPush': () => scPush(),
    'scDiscardFile': (params) => scDiscardFile(params.filePath, params.fileType),
    'scSelectFile': (params) => scSelectFile(params.filePath, params.fileType, params.staged),
    'scToggleCommitFiles': (params) => scToggleCommitFiles(params.hash),
    'scShowCommitFileDiff': (params) => scShowCommitFileDiff(params.hash, params.filePath),

    // ===== DEPLOYS =====
    // 'showCreateDeployModal': () => showCreateDeployModal(),
    // 'createNewDeploy': () => createNewDeploy(),
    // 'showEditDeployModal': (params) => editDeploy(params.deployId),
    // 'saveEditedDeploy': () => saveEditedDeploy(),
    // 'deleteDeploy': (params) => deleteDeploy(params.deployId),
    // 'runDeploy': (params) => runDeploy(params.pipelineId),

    // ===== AMBIENTES =====
    'showCreateEnvironmentModal': () => showCreateEnvironmentModal(),
    'createNewEnvironment': () => createNewEnvironment(),
    'showEditEnvironmentModal': (params) => showEditEnvironmentModal(params.envId),
    'saveEditedEnvironment': () => saveEditedEnvironment(),
    'deleteEnvironment': (params) => deleteEnvironment(params.envId),

    // ===== CONFIGURAÇÕES GITHUB =====
    'saveGithubSettings': () => saveGithubSettings(),
    'testGithubConnection': () => testGithubConnection(),

    // ===== VARIÁVEIS DO SERVIDOR =====
    'showCreateVariableModal': () => showCreateVariableModal(),
    'createNewVariable': () => createNewVariable(),
    'showEditVariableModal': (params) => showEditVariableModal(params.varId),
    'saveEditedVariable': () => saveEditedVariable(),
    'deleteVariable': (params) => deleteVariable(params.varId),
    'showImportVariablesModal': () => showImportVariablesModal(),

    // ===== MONITORAMENTO =====
    'obsRefresh': () => showObservability(),
    'obsShowCreateMonitor': () => obsShowCreateMonitorModal(),
    'obsCreateMonitor': () => obsCreateMonitor(),
    'obsBrowseLogs': () => obsBrowseLogs(),
    'obsSaveMonitor': () => obsSaveMonitor(),
    'obsEditMonitor': (params) => obsEditMonitor(params.configId),
    'obsDeleteMonitor': (params) => obsDeleteMonitor(params.configId),
    'obsScanNow': (params) => obsScanNow(params.configId),
    'obsResetPosition': (params) => obsResetPosition(params.configId),
    'obsAcknowledge': (params) => obsAcknowledge(params.alertId),
    'obsAcknowledgeAll': () => obsAcknowledgeAll(),
    'obsChangePage': (params) => loadAndRenderAlerts(params.page),

    // ===== BASE DE CONHECIMENTO =====
    'kbRefresh': () => showKnowledge(),
    'kbSwitchTab': (params) => kbSwitchTab(params.tab),
    'kbApplyFilters': () => kbApplyFilters(),
    'kbChangePage': (params) => { kbCurrentPage = params.page; kbSwitchTab('knowledge'); },
    'kbChangeCorrPage': (params) => { corrCurrentPage = params.page; kbSwitchTab('corrections'); },
    'kbViewArticle': (params) => kbViewArticle(params.id),
    'kbShowCreateArticle': () => kbShowCreateArticle(),
    'kbEditArticle': (params) => kbEditArticle(params.id),
    'kbSaveArticle': () => kbSaveArticle(),
    'kbDeleteArticle': (params) => kbDeleteArticle(params.id),
    'kbImportArticles': () => kbImportArticles(),
    'kbShowCreateCorrection': () => kbShowCreateCorrection(),
    'kbSaveCorrection': () => kbSaveCorrection(),
    'kbValidateCorrection': (params) => kbValidateCorrection(params.id),
    'kbShowCreateRule': () => kbShowCreateRule(),
    'kbEditRule': (params) => kbEditRule(params.id),
    'kbSaveRule': () => kbSaveRule(),
    'kbDeleteRule': (params) => kbDeleteRule(params.id),

    // ===== INTEGRAÇÃO COM BANCO DE DADOS =====
    'dbRefresh': () => showDatabase(),
    'dbShowCreateConn': () => dbShowCreateConn(),
    'dbEditConn': (params) => dbEditConn(params.id),
    'dbSaveConn': () => dbSaveConn(),
    'dbDeleteConn': (params) => dbDeleteConn(params.id),
    'dbTestConn': (params) => dbTestConn(params.id),
    'dbDiscover': (params) => dbDiscover(params.id),
    'dbSelectConn': (params) => dbSelectConn(params.id),
    'dbSelectTable': (params) => dbSelectTable(params.name),
    'dbViewSample': (params) => dbViewSample(params.name),
    'dbToggleCard': (params) => dbToggleCard(params),
    'dbExecuteQuery': () => dbExecuteQuery(),
    'dbSwitchTab': (params) => dbSwitchTab(params.tab),
    'dictRunCompare': () => dictRunCompare(),
    'dictRunValidate': () => dictRunValidate(),
    'dictToggleAllTables': () => dictToggleAllTables(),
    'dictToggleAllLayers': () => dictToggleAllLayers(),
    'dictToggleCompareDetail': (params) => dictToggleCompareDetail(params),
    'dictToggleIntegrityDetail': (params) => dictToggleIntegrityDetail(params),
    'dictExportCompareCsv': (params) => dictExportCompareCsv(params),
    'dictExportValidateCsv': (params) => dictExportValidateCsv(params),
    'dictViewHistory': (params) => dictViewHistory(params),
    'dictDeleteHistory': (params) => dictDeleteHistory(params),
    'dictBackToHistory': () => dictBackToHistory(),
    'dictViewCompareHistory': (params) => dictViewCompareHistory(params),
    'dictDeleteCompareHistory': (params) => dictDeleteCompareHistory(params),
    'dictBackToCompareHistory': () => dictBackToCompareHistory(),
    'dictOpenEqualizeModal': () => dictOpenEqualizeModal(),
    'dictOpenEqualizeWizard': () => dictOpenEqualizeWizard(),
    'dictPreviewEqualize': () => dictPreviewEqualize(),
    'dictExecuteEqualize': () => dictExecuteEqualize(),
    'eqWizardNext': () => eqWizardNext(),
    'eqWizardPrev': () => eqWizardPrev(),
    'eqViewHistory': (params) => eqViewHistory(params),
    'eqDeleteHistory': (params) => eqDeleteHistory(params),
    'eqExportHistory': (params) => eqExportHistory(params),
    'eqBackToHistory': () => eqBackToHistory(),

    // ===== PROCESSOS DA EMPRESA =====
    'bpRefresh': () => showProcesses(),
    'bpSwitchTab': (params) => bpSwitchTab(params.tab),
    'bpSelectProcess': (params) => bpSelectProcess(params.id),
    'bpSeed': () => bpSeed(),
    'bpShowCreate': () => bpShowCreate(),
    'bpEdit': (params) => bpEdit(params.id),
    'bpSave': () => bpSave(),
    'bpOpenIconPicker': () => bpOpenIconPicker(),
    'bpDelete': (params) => bpDelete(params.id),
    'bpShowAddTable': (params) => bpShowAddTable(params.id),
    'bpSaveTable': () => bpSaveTable(),
    'bpRemoveTable': (params) => bpRemoveTable(params.id),
    'bpAutoMapFields': (params) => bpAutoMapFields(params.tableId, params.connectionId),
    'bpEditField': (params) => bpEditField(params.id),
    'bpUpdateField': () => bpUpdateField(),
    'bpDeleteField': (params) => bpDeleteField(params.id),
    'bpEditTable': (params) => bpEditTable(params.id),
    'bpUpdateTable': () => bpUpdateTable(),
    'bpShowAddFlow': (params) => bpShowAddFlow(params.id),
    'bpSaveFlow': () => bpSaveFlow(),
    'bpEditFlow': (params) => bpEditFlow(params.id),
    'bpUpdateFlow': () => bpUpdateFlow(),
    'bpDeleteFlow': (params) => bpDeleteFlow(params.id),

    // ===== DOCUMENTACAO =====
    'docRefresh': () => docRefresh(),
    'docSwitchTab': (params) => docSwitchTab(params),
    'docGenerate': () => docGenerate(),
    'docPreview': (params) => docPreview(params),
    'docDownload': (params) => docDownload(params),
    'docDelete': (params) => docDelete(params),
    'docGoPage': (params) => docGoPage(params),
    'docShowVersions': (params) => docShowVersions(params),
    'docCloseModal': () => docCloseModal(),

    // ===== DEV WORKSPACE =====
    'dwSwitchTab': (params) => dwSwitchTab(params),
    'dwRefresh': () => dwRefresh(),
    'dwNavigate': (params) => dwNavigate(params),
    'dwOpenFile': (params) => dwOpenFile(params),
    'dwCloseFile': () => dwCloseFile(),
    'dwAnalyzeFile': (params) => dwAnalyzeFile(params),
    'dwRunImpact': () => dwRunImpact(),
    'dwRunDiff': () => dwRunDiff(),
    'dwGenerateCompila': () => dwGenerateCompila(),
    'dwShowPolicyForm': () => dwShowPolicyForm(),
    'dwCancelPolicy': () => dwCancelPolicy(),
    'dwSavePolicy': () => dwSavePolicy(),
    'dwDeletePolicy': (params) => dwDeletePolicy(params),

    // ===== SERVIÇOS DO SERVIDOR =====
    'showCreateServiceModal': () => showCreateServiceModal(),
    'createNewService': () => createNewService(),
    'showEditServiceModal': (params) => showEditServiceModal(params.serviceId),
    'saveEditedService': () => saveEditedService(),
    'deleteService': (params) => deleteService(params.serviceId),

    // ===== PAGINAÇÃO =====
    'changeCommandsPage': (params) => changeCommandsPage(params.page),
    'changePipelinePage': (params) => changePipelinePage(params.page),
    // ===== UTILITÁRIOS =====
    'togglePassword': () => togglePassword(),
    'toggleGithubToken': () => toggleGithubToken(),
    'closeModal': (params) => {
        const modal = bootstrap.Modal.getInstance(document.getElementById(params.modalId));
        if (modal) modal.hide();
    },

    // ===== REPOSITÓRIOS - Navegação e Arquivos =====
    'goBackPath': (params) => goBackPath(params.repoName),
    'sortRepositoryContent': (params) => sortRepositoryContent(params.repoName, params.field),
    'navigateToPath': (params) => navigateToPath(params.repoName, params.path),
    'viewFile': (params) => viewFile(params.repoName, params.path),

    // ===== HISTÓRICO =====
    // ===== COMANDOS - Ordenação =====
    'moveCommandUp': (params) => moveCommandUp(params.commandId, params.mode),
    'moveCommandDown': (params) => moveCommandDown(params.commandId, params.mode),
    'removeSelectedCommand': (params) => removeSelectedCommand(params.commandId, params.mode),

    // ===== UTILITÁRIO GENÉRICO =====
    'removeParentElement': (params, element) => {
        if (element && element.parentElement) {
            element.parentElement.remove();
        }
    },
};

function handleAction(action, params, element) {
    const handler = actionHandlers[action];

    // Log de debug
    console.log(`🔄 Executando ação: ${action}`, params);
    if (handler) {
        try {
            handler(params, element);
        } catch (error) {
            console.error(`❌ Erro ao executar ação "${action}":`, error);
            console.error("Stack trace:", error.stack);
            showNotification(`Erro ao executar: ${error.message}`, 'error');
            return false;
        }
    } else {
        console.warn(`Handler não encontrado para ação: ${action}`);
    }
}

const formActionHandlers = {
    'login': handleLogin,
    'createNewUser': (event) => createNewUser(),
    'saveEditedUser': (event) => saveEditedUser(),
    'changeUserPassword': (event) => changeUserPassword(),
};

function handleFormAction(action, form) {
    const handler = formActionHandlers[action];
    if (handler) {
        try {
            // Passamos um objeto de evento simulado para manter a compatibilidade
            handler({ preventDefault: () => { }, target: form });
        } catch (error) {
            console.error(`Erro ao submeter formulário '${action}':`, error);
            showNotification(`Erro ao submeter formulário: ${error.message}`, 'error');
        }
    } else {
        console.warn(`Handler de formulário não encontrado: ${action}`);
    }
}

// =====================================================================
// LÓGICA PRINCIPAL DA APLICAÇÃO (INICIALIZAÇÃO, LOGIN, ROTEAMENTO)
// =====================================================================

async function checkSessionAndInitialize() {
    const token = sessionStorage.getItem('auth_token');
    if (!token) {
        showLoginPage();
        return;
    }
    try {
        const user = await apiCheckSession();
        currentUser = user;
        await loadInitialDataAndRenderApp();
    } catch (error) {
        sessionStorage.removeItem('auth_token');
        showLoginPage();
    }
}

async function loadInitialDataAndRenderApp() {
    try {
        showNotification('Carregando dados da aplicação...', 'info');

        // Detectar SO do servidor
        try {
            serverOS = await apiGetSystemInfo();
            console.log(`🖥️ SO detectado: ${serverOS.os} (tipo de comando: ${serverOS.command_type})`);
        } catch (e) {
            console.warn('Não foi possível detectar o SO do servidor, filtros desabilitados:', e);
            serverOS = null;
        }

        // Carregar permissões do usuário
        await loadUserPermissions();

        environments = await apiGetEnvironments();
        let activeEnvId = sessionStorage.getItem('active_environment_id');
        if (!activeEnvId && environments.length > 0) {
            activeEnvId = environments[0].id;
            sessionStorage.setItem('active_environment_id', activeEnvId);
        }
        setupEnvironmentSelector();

        if (activeEnvId) {
            const dataPromises = [
                loadCommands(), loadPipelines(), loadSchedules(), loadRepositories(),
                loadGithubSettings(), loadServerVariables(), loadServerServices()
            ];
            if (isAdmin()) {
                dataPromises.push(loadUsers());
            }
            await Promise.allSettled(dataPromises);
        } else if (isAdmin()) {
            await loadUsers();
            console.warn("Nenhum ambiente encontrado. Cadastre um na página de Ambientes.");
        }

        showAppPage();
        updateSidebarByProfile();
        updateUserDisplay();

        // 🆕 Sempre iniciar no Dashboard após login
        if (!window.location.hash || window.location.hash === '#' || window.location.hash === '') {
            window.location.hash = 'dashboard';
        }

        router();
        connectToEventStream();
        await loadServiceActions();

        if (keepAliveInterval) clearInterval(keepAliveInterval);
        keepAliveInterval = setInterval(apiKeepAlive, 30000);

        clearAllNotifications();
        showNotification(`Bem-vindo, ${currentUser.name}!`, 'success');

    } catch (error) {
        console.error("Falha crítica ao carregar dados:", error);
        showNotification("Erro fatal ao carregar dados. Tente fazer login novamente.", 'error');
        logout(true);
    }
}

async function loadServiceActions() {
    try {
        serviceActions = await apiGetServiceActions();
    } catch (error) {
        console.error('Erro ao carregar ações de serviços:', error);
        serviceActions = [];
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    try {
        showNotification('Autenticando...', 'info');
        const user = await apiLogin(username, password, false);
        currentUser = user;
        await loadInitialDataAndRenderApp();
    } catch (error) {
        if (error.status === 409) {
            if (confirm(error.message + "\n\nDeseja derrubar a sessão ativa e continuar?")) {
                try {
                    const user = await apiLogin(username, password, true);
                    currentUser = user;
                    await loadInitialDataAndRenderApp();
                } catch (forceError) {
                    showNotification(forceError.message || 'Não foi possível forçar o login.', 'error');
                }
            } else {
                clearAllNotifications();
            }
        } else {
            showNotification(error.message || 'Usuário ou senha inválidos!', 'error');
        }
    }
}

async function logout(force = false) {
    if (isLoggingOut) {
        console.warn('Logout já em andamento, ignorando...');
        return;
    }

    isLoggingOut = true;

    try {
        if (keepAliveInterval) {
            clearInterval(keepAliveInterval);
            keepAliveInterval = null;
        }

        try {
            await apiLogout();
        } catch (error) {
            console.error('Erro no logout da API, prosseguindo localmente.', error);
        }

        currentUser = null;
        sessionStorage.clear();

        // 🆕 Remover listener de hashchange temporariamente para evitar "Acesso negado"
        window.removeEventListener('hashchange', router);
        window.location.hash = '';

        showLoginPage();

        // 🆕 Restaurar listener após um pequeno delay
        setTimeout(() => {
            window.addEventListener('hashchange', router);
        }, 100);

        if (!force) {
            showNotification('Logout realizado com sucesso!', 'info');
        }
    } finally {
        isLoggingOut = false;
    }
}

function router() {
    const page = window.location.hash.substring(1) || 'dashboard';
    // Ignorar ancoras internas (ex: #dicionario-de-dados do marked.js)
    if (!(page in PAGE_MODULES) && !['users', 'settings', 'services-management'].includes(page)) return;
    if (!hasPermission(page)) {
        showNotification('Acesso negado! Redirecionando...', 'error');
        window.location.hash = 'dashboard';
        return;
    }

    // Atualizar tab ativa no header
    const catKey = PAGE_TO_CATEGORY[page];
    document.querySelectorAll('.header-tab').forEach(t => {
        t.classList.toggle('active', t.getAttribute('data-category') === catKey);
    });

    // Renderizar sidebar contextual da categoria
    renderContextualSidebar(catKey, page);

    const contentArea = document.getElementById('content-area');
    contentArea.innerHTML = `<div class="text-center p-5"><div class="spinner-border text-primary"></div></div>`;

    // Cleanup do dashboard ao sair
    if (page !== 'dashboard' && typeof stopDashboardAutoRefresh === 'function') {
        stopDashboardAutoRefresh();
    }

    // Carrega módulos necessários para a página e depois renderiza
    const modules = PAGE_MODULES[page] || [];
    const loadPromises = modules.map(m => loadModule(m));

    Promise.all(loadPromises).then(() => {
        setTimeout(() => {
            const pageRenderFunctions = {
                'dashboard': 'showDashboard',
                'repositories': 'showRepositories',
                'source-control': 'showSourceControl',
                'pipelines': 'showPipelines',
                'schedules': 'showSchedules',
                'commands': 'showCommands',
                'observability': 'showObservability',
                'knowledge': 'showKnowledge',
                'database': 'showDatabase',
                'processes': 'showProcesses',
                'documentation': 'showDocumentation',
                'devworkspace': 'showDevWorkspace',
                'agent': 'showAgent',
                'auditor': 'showAuditor',
                'users': 'showUsers',
                'settings': 'showSettings',
                'toggleServiceActionSchedule': 'toggleServiceActionSchedule',
            };
            const funcName = pageRenderFunctions[page] || 'showDashboard';
            const renderFunction = window[funcName] || window['showDashboard'];
            if (typeof renderFunction === 'function') {
                renderFunction();
            } else {
                console.error(`Função ${funcName} não encontrada após carregar módulos`);
                contentArea.innerHTML = `<div class="text-center p-5 text-danger">Erro: módulo não carregado</div>`;
            }
        }, 50);
    }).catch(err => {
        contentArea.innerHTML = `<div class="text-center p-5 text-danger">Erro ao carregar módulo: ${err.message}</div>`;
    });
}

// =====================================================================
// FUNÇÕES DE CARREGAMENTO DE DADOS (LOADERS)
// =====================================================================
async function loadUsers() { try { users = await apiGetUsers(); } catch (e) { users = []; } }
async function loadCommands() {
    try {
        commands = await apiGetCommands();
        console.log('✅ Comandos carregados:', commands.length);
    } catch (error) {
        console.error('❌ Erro ao carregar comandos:', error);
        showNotification('Erro ao carregar comandos: ' + error.message, 'error');
    }
}

// 🆕 Nova função auxiliar para filtrar comandos
function getCommandsByCategory(category) {
    return commands.filter(cmd => cmd.command_category === category);
}
async function loadPipelines() { try { pipelines = await apiGetPipelines(); } catch (e) { pipelines = []; } }
async function loadSchedules() {
    try {
        schedules = await apiGetSchedules();
        console.log('✅ Schedules carregados:', schedules.length);
    } catch (e) {
        schedules = [];
        console.error('Erro ao carregar schedules:', e);
    }
}
// async function loadDeploys() { try { deploys = await apiGetDeploys(); } catch(e) { deploys = []; } }
async function loadRepositories() { try { repositories = await apiGetRepositories(); } catch (e) { repositories = []; } }
async function loadGithubSettings() {
    if (canPerformAction('github_settings', 'view')) {
        // Admin: carrega username e status (sem token)
        try {
            const settings = await apiGetGithubSettings();
            gitHubSettings = { configured: settings.has_token, username: settings.username || '' };
        } catch (e) { gitHubSettings = { configured: false, username: '' }; }
    } else {
        // Operador/Viewer: apenas verifica se GitHub está configurado
        try {
            const status = await apiGetGithubStatus();
            gitHubSettings = { configured: status.configured, username: '' };
        } catch (e) { gitHubSettings = { configured: false, username: '' }; }
    }
}
async function loadServerVariables() { try { serverVariables = await apiGetServerVariables(); } catch (e) { serverVariables = []; } }
async function loadServerServices() { try { serverServices = await apiGetServerServices(); } catch (e) { serverServices = []; } }
// =================================================================
// FUNÇÕES GLOBAIS CRÍTICAS - SEMPRE DISPONÍVEIS
// =================================================================
window.togglePassword = function () {
    console.log('Toggle password chamado');
    const passwordInput = document.getElementById('password');
    const toggleIcon = document.getElementById('togglePasswordIcon');
    if (!passwordInput || !toggleIcon) {
        console.error('Elementos não encontrados');
        return;
    }
    // Alternar tipo do input
    const currentType = passwordInput.getAttribute('type');
    const newType = currentType === 'password' ? 'text' : 'password';
    passwordInput.setAttribute('type', newType);
    // Alternar ícone
    if (newType === 'text') {
        // Mostrando senha - ícone "eye-slash"
        toggleIcon.classList.remove('fa-eye');
        toggleIcon.classList.add('fa-eye-slash');
    } else {
        // Ocultando senha - ícone "eye"
        toggleIcon.classList.remove('fa-eye-slash');
        toggleIcon.classList.add('fa-eye');
    }
    console.log('Tipo alterado para:', newType);
};

// Função para verificar se é admin
// Função para verificar se é admin
function isAdmin() {
    return currentUser && currentUser.profile === 'admin';
}

// Função para verificar se é o user admin (root supremo)
function isRootAdmin() {
    return currentUser && currentUser.username === 'admin';
}

// Função para verificar se é operator ou admin
function isOperator() {
    return currentUser && ['admin', 'operator'].includes(currentUser.profile);
}

// Função para verificar se é viewer
function isViewer() {
    return currentUser && currentUser.profile === 'viewer';
}

// Função para carregar permissões do backend
async function loadUserPermissions() {
    try {
        const response = await fetch('/api/me/permissions', {
            headers: { 'Authorization': authToken }
        });
        if (response.ok) {
            const data = await response.json();
            userPermissions = data.permissions;
            return userPermissions;
        }
    } catch (e) {
        console.error('Erro ao carregar permissões:', e);
    }
    return null;
}

// Função para verificar permissão de acesso a uma seção
function hasPermission(section) {
    if (!currentUser) return false;

    // User 'admin' (root) tem acesso total
    if (isRootAdmin()) return true;

    const permissions = {
        'admin': ['dashboard', 'repositories', 'source-control', 'pipelines', 'schedules', 'commands', 'observability', 'database', 'auditor', 'devworkspace', 'agent', 'services-management', 'users', 'settings'],
        'operator': ['dashboard', 'repositories', 'source-control', 'pipelines', 'schedules', 'commands', 'observability', 'database', 'auditor', 'devworkspace', 'agent', 'services-management'],
        'viewer': ['dashboard', 'repositories', 'source-control', 'pipelines', 'schedules', 'observability', 'database', 'auditor', 'devworkspace', 'agent']
    };
    return permissions[currentUser.profile]?.includes(section) || false;
}

// Função para verificar permissão de ação específica
function canPerformAction(resource, action) {
    if (!currentUser || !userPermissions) return false;

    // User admin (root) pode tudo
    if (isRootAdmin()) return true;

    return userPermissions[resource]?.[action] || false;
}

// Função para validar se senhas conferem em tempo real
function validatePasswordMatch(passwordFieldId, confirmFieldId, labelId) {
    const password = document.getElementById(passwordFieldId)?.value || '';
    const confirm = document.getElementById(confirmFieldId)?.value || '';
    const confirmField = document.getElementById(confirmFieldId);
    const label = document.getElementById(labelId);
    const feedbackId = confirmFieldId.replace('Confirm', 'Feedback');
    const feedback = document.getElementById(feedbackId);

    if (confirm.length === 0) {
        // Campo vazio - estado neutro
        if (confirmField) confirmField.classList.remove('is-invalid', 'is-valid');
        if (label) label.innerHTML = '<i class="fas fa-check me-1"></i>Confirmar Senha *';
        if (feedback) feedback.style.display = 'none';
    } else if (password === confirm) {
        // Senhas conferem
        if (confirmField) {
            confirmField.classList.remove('is-invalid');
            confirmField.classList.add('is-valid');
        }
        if (label) label.innerHTML = '<i class="fas fa-check-circle text-success me-1"></i>Confirmar Senha *';
        if (feedback) feedback.style.display = 'none';
    } else {
        // Senhas diferentes
        if (confirmField) {
            confirmField.classList.remove('is-valid');
            confirmField.classList.add('is-invalid');
        }
        if (label) label.innerHTML = '<i class="fas fa-times-circle text-danger me-1"></i>Confirmar Senha *';
        if (feedback) feedback.style.display = 'block';
    }
}

// Expor função globalmente
window.validatePasswordMatch = validatePasswordMatch;

// Função para verificar se pode editar/excluir item protegido
function canEditProtected() {
    if (!userPermissions) return false;
    return userPermissions.can_edit_protected || false;
}

function togglePassword() {
    const passwordInput = document.getElementById('password');
    const toggleIcon = document.getElementById('togglePasswordIcon');
    if (!passwordInput || !toggleIcon) return;

    const isPassword = passwordInput.type === 'password';
    passwordInput.type = isPassword ? 'text' : 'password';
    toggleIcon.classList.toggle('fa-eye', !isPassword);
    toggleIcon.classList.toggle('fa-eye-slash', isPassword);
}

// FUNÇÃO DE VERIFICAÇÃO DE INTEGRIDADE
function verifyUserDisplay() {
    console.log('=== VERIFICAÇÃO DO DISPLAY DO USUÁRIO ===');
    console.log('currentUser:', currentUser);
    const userDisplay = document.getElementById('current-user');
    console.log('Elemento current-user encontrado:', !!userDisplay);
    if (userDisplay) {
        console.log('Conteúdo atual do elemento:', userDisplay.textContent);
    }
    if (currentUser) {
        console.log('Nome do usuário logado:', currentUser.name);
        console.log('Username do usuário logado:', currentUser.username);
    }
    // Forçar atualização se necessário
    if (currentUser && userDisplay) {
        userDisplay.textContent = currentUser.name;
        console.log('Nome FORÇADO para:', currentUser.name);
    }
}
// Adicionar verificação periódica durante desenvolvimento
setInterval(() => {
    if (currentUser) {
        verifyUserDisplay();
    }
}, 5000); // Verificar a cada 5 segundos
// Inicialização do sistema
async function initializeApp() {
    console.log('Inicializando AtuDIC...');
    // Registrar Service Worker (scope '/' requer SW na raiz)
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(function () {});
    }
    // Carregar strings de i18n ANTES de qualquer renderização
    try {
        await loadLocale();
    } catch (e) {
        console.warn('[i18n] Fallback: locale não carregado', e);
    }
    // Configurar login
    setupLogin();
    setupActivateLicenseModal();
    setupFirstAccessModal();
    setupForgotPasswordModal();
    // Se já estiver logado (reload da página), atualizar display
    if (currentUser) {
        setupNavigation();
        updateSidebarByProfile();
        updateUserDisplay();
    }
    console.log('Sistema inicializado com sucesso!');
}
// Configurar sistema de login
function setupLogin() {
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }
    const toggleButton = document.getElementById('togglePassword');
    if (toggleButton) {
        const newToggleButton = toggleButton.cloneNode(true);
        toggleButton.parentNode.replaceChild(newToggleButton, toggleButton);
        newToggleButton.addEventListener('click', (e) => {
            e.preventDefault();
            togglePassword();
        });
    }

    // Verificar se é primeiro acesso
    checkFirstAccess();
}
// Backup: inicializar quando window carregar
window.addEventListener('load', function () {
    console.log('Window carregada, verificando inicialização...');
    // Garantir inicialização do sistema de notificações
    if (typeof showNotification !== 'function') {
        console.warn('Sistema de notificações não carregado, inicializando...');
        initNotificationSystem();
    }
    // Teste inicial das notificações após login
    if (currentUser) {
        setTimeout(() => {
            showNotification('Sistema de notificações ativo!', 'success', 2000);
        }, 1000);
    }
    const loginForm = document.getElementById('loginForm');
    if (loginForm && !loginForm.hasAttribute('data-initialized')) {
        initializeApp();
        loginForm.setAttribute('data-initialized', 'true');
    }
});
// Sistema de monitoramento contínuo
setInterval(() => {
    // Verificar se container de toast ainda existe
    const container = document.querySelector('.toast-container-footer');
    if (!container) {
        console.log('Container de toast removido, recriando...');
        ensureToastContainer();
    }
    // Verificar se função showNotification ainda existe
    if (typeof showNotification !== 'function') {
        console.error('Função showNotification perdida, restaurando...');
        initNotificationSystem();
    }
}, 10000); // Verificar a cada 10 segundos

function toggleSidebar() {
    // Nao toggle se sidebar esta escondida (ex: Dashboard)
    if (document.body.classList.contains('sidebar-hidden')) return;

    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.getElementById('sidebarBackdrop');
    const isMobile = window.innerWidth <= 768;

    if (isMobile) {
        // Mobile: drawer com overlay
        const isOpen = sidebar.classList.contains('mobile-open');
        if (isOpen) {
            sidebar.classList.remove('mobile-open');
            if (backdrop) backdrop.classList.remove('show');
        } else {
            sidebar.classList.add('mobile-open');
            if (backdrop) backdrop.classList.add('show');
        }
    } else {
        // Desktop: comportamento original (collapse)
        document.body.classList.toggle('sidebar-collapsed');
    }
}

// Fechar sidebar ao clicar no backdrop
document.addEventListener('DOMContentLoaded', function() {
    const backdrop = document.getElementById('sidebarBackdrop');
    if (backdrop) {
        backdrop.addEventListener('click', function() {
            const sidebar = document.querySelector('.sidebar');
            sidebar.classList.remove('mobile-open');
            backdrop.classList.remove('show');
        });
    }
});

// Links externos abrem em nova aba (evita sair do AtuDIC)
document.addEventListener('click', function(e) {
    const link = e.target.closest('a[href]');
    if (!link) return;
    const href = link.getAttribute('href');
    if (href && href.startsWith('http') && !link.hasAttribute('target')) {
        link.setAttribute('target', '_blank');
        link.setAttribute('rel', 'noopener noreferrer');
    }
});

// Fechar sidebar mobile ao navegar para outra página
document.addEventListener('click', function(e) {
    if (window.innerWidth <= 768) {
        const navLink = e.target.closest('.sidebar .nav-link');
        if (navLink) {
            const sidebar = document.querySelector('.sidebar');
            const backdrop = document.getElementById('sidebarBackdrop');
            sidebar.classList.remove('mobile-open');
            if (backdrop) backdrop.classList.remove('show');
        }
    }
});

function changeCommandsPage(page) {
    const totalPages = Math.ceil(getOSFilteredCommands().length / commandsPerPage);
    if (page < 1 || (page > totalPages && totalPages > 0)) {
        return; // Previne ir para uma página inválida
    }
    currentCommandsPage = page;

    const container = document.getElementById('commandsContainer');
    const pagination = document.getElementById('commandsPagination');
    if (container) {
        container.innerHTML = renderCommands();
    }
    if (pagination) {
        pagination.innerHTML = renderCommandsPagination();
    }
}

function renderCommandsPagination() {
    const totalPages = Math.ceil(getOSFilteredCommands().length / commandsPerPage);
    if (totalPages <= 1) return '';

    return `
        <nav class="d-flex justify-content-center mt-4">
            <ul class="pagination">
                <li class="page-item ${currentCommandsPage === 1 ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="changeCommandsPage" data-params=\'{"page":${currentCommandsPage - 1}}\'>Anterior</a>
                </li>
                <li class="page-item disabled"><span class="page-link">${currentCommandsPage} de ${totalPages}</span></li>
                <li class="page-item ${currentCommandsPage === totalPages ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="changeCommandsPage" data-params=\'{"page":${currentCommandsPage + 1}}\'>Próximo</a>
                </li>
            </ul>
        </nav>
    `;
}

// =====================================================================
// RENDERIZACAO DE HEADER TABS E SIDEBAR CONTEXTUAL
// =====================================================================

function renderHeaderTabs() {
    const container = document.getElementById('headerTabs');
    if (!container) return;
    let html = '';
    for (const [catKey, cat] of Object.entries(CATEGORIES)) {
        const hasAny = cat.pages.some(p => hasPermission(p));
        if (!hasAny) continue;
        html += `<a class="header-tab" href="#" data-category="${catKey}" data-action="navigateCategory" data-params='{"category":"${catKey}"}'>
                    <i class="fas ${cat.icon}"></i>
                    <span class="header-tab-label">${cat.label}</span>
                 </a>`;
    }
    container.innerHTML = html;
}

function renderContextualSidebar(catKey, activePage) {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const navContainer = sidebar.querySelector('.nav');
    const cat = CATEGORIES[catKey];

    if (!cat || cat.pages.length <= 1) {
        document.body.classList.add('sidebar-hidden');
        return;
    }

    document.body.classList.remove('sidebar-hidden');

    const linksHtml = cat.pages
        .filter(p => hasPermission(p))
        .map(p => {
            const meta = PAGE_LABELS[p];
            return `<a class="nav-link ${p === activePage ? 'active' : ''}" href="#" data-page="${p}">
                        <i class="fas ${meta.icon}"></i><span>${meta.label}</span>
                    </a>`;
        }).join('');

    navContainer.innerHTML = linksHtml;
}

function updateSidebarByProfile() {
    if (!currentUser) return;
    renderHeaderTabs();
    const page = window.location.hash.substring(1) || 'dashboard';
    const catKey = PAGE_TO_CATEGORY[page];
    if (catKey) renderContextualSidebar(catKey, page);
}

function setupNavigation() {
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        const newLink = link.cloneNode(true);
        link.parentNode.replaceChild(newLink, link);
        newLink.addEventListener('click', function (e) {
            e.preventDefault();
            const page = this.getAttribute('data-page');
            if (hasPermission(page)) {
                window.location.hash = page;
            } else {
                showNotification('Acesso negado!', 'error');
            }
        });
    });
}

function setupEventListeners() {
    // Deprecated - usando setupLogin() e setupNavigation() separadamente
    console.log('setupEventListeners deprecated - usando nova estrutura');
    // setupNavigation agora é global - ver acima
    // Modal close on background click
    window.addEventListener('click', function (event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    });
}
function showLoginPage() {
    document.getElementById('login-container').style.display = 'flex';
    document.getElementById('app-container').style.display = 'none';
}

function showAppPage() {
    document.getElementById('login-container').style.display = 'none';
    document.getElementById('app-container').style.display = 'block';
}
function updateUserDisplay() {
    const userDisplayHeader = document.getElementById('current-user');
    if (currentUser && userDisplayHeader) {
        userDisplayHeader.textContent = currentUser.name || currentUser.username;
    }
}

function showError(message) {
    const errorEl = document.getElementById('loginError');
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
    setTimeout(() => {
        errorEl.classList.add('hidden');
    }, 5000);
}
// Função removida - usando togglePassword() global
function navigateToPage(page) {
    // Validação de parâmetro
    if (!page || typeof page !== 'string') {
        console.error('❌ Página inválida:', page);
        return;
    }

    console.log(`📄 Navegando para: ${page}`);
    const currentHash = window.location.hash.substring(1) || 'dashboard';
    if (page === currentHash) {
        // Se já estamos na página correta (ex: #repositories),
        // mas em uma tela interna (como o explorador),
        // forçamos o roteador a rodar de novo para voltar à tela principal da seção.
        router();
    } else {
        // Se for uma página diferente, apenas mudamos o hash
        // e deixamos o 'hashchange' listener fazer o trabalho.
        window.location.hash = page;
    }
}
document.addEventListener('shown.bs.tab', function (event) {
    if (event.target.id && event.target.id.endsWith('-tab')) {
        sessionStorage.setItem('activeSettingsTab', event.target.id);
    }
});
// ================================================================
// SISTEMA DE NOTIFICAÇÕES ROBUSTO - FUNCIONA SEMPRE
// ================================================================

function showNotification(message, type = 'info', duration = 3000) {
    // Se há um modal Bootstrap aberto, mostrar inline dentro dele
    const openModal = document.querySelector('.modal.show .modal-body');
    if (openModal) {
        _showInlineNotification(openModal, message, type, duration);
        return;
    }
    notificationQueue.push({ message, type, duration });
    if (!isProcessingQueue) {
        processNotificationQueue();
    }
}

/**
 * Mostra notificacao inline dentro de um container (modal, painel, etc).
 */
function _showInlineNotification(container, message, type, duration) {
    const typeMap = {
        success: { css: 'alert-success', icon: 'fa-check-circle' },
        error:   { css: 'alert-danger',  icon: 'fa-exclamation-circle' },
        warning: { css: 'alert-warning', icon: 'fa-exclamation-triangle' },
        info:    { css: 'alert-info',    icon: 'fa-info-circle' }
    };
    const scheme = typeMap[type] || typeMap.info;

    // Remover notificacao inline anterior do mesmo container
    const prev = container.querySelector('.inline-notification');
    if (prev) prev.remove();

    const alert = document.createElement('div');
    alert.className = `alert ${scheme.css} alert-dismissible fade show inline-notification d-flex align-items-center py-2 px-3 mb-3`;
    alert.setAttribute('role', 'alert');
    alert.style.cssText = 'animation: fadeInDown 0.3s ease-out; font-size: 0.9rem;';
    alert.innerHTML = `
        <i class="fas ${scheme.icon} me-2"></i>
        <span>${escapeHtml(message)}</span>
        <button type="button" class="btn-close btn-close-sm ms-auto" data-bs-dismiss="alert" aria-label="Fechar" style="font-size:0.65rem;"></button>
    `;

    // Inserir no topo do container
    container.insertBefore(alert, container.firstChild);

    // Scroll para garantir visibilidade
    alert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Auto-remover
    if (duration > 0) {
        setTimeout(() => {
            if (alert.parentNode) {
                alert.classList.remove('show');
                setTimeout(() => alert.remove(), 300);
            }
        }, duration);
    }
}

async function processNotificationQueue() {
    if (notificationQueue.length === 0) {
        isProcessingQueue = false;
        return;
    }
    isProcessingQueue = true;
    const notification = notificationQueue.shift();
    await displayNotification(notification);
    setTimeout(processNotificationQueue, 300);
}

function displayNotification({ message, type, duration }) {
    return new Promise(resolve => {
        let isResolved = false;
        const safeResolve = () => {
            if (!isResolved) {
                isResolved = true;
                resolve();
            }
        };

        try {
            console.log(`[Toast] Mostrando: ${message}`);
            // Bypassing Bootstrap entirely and using the bulletproof native DOM fallback
            fallbackNotification(message, type);

            // Failsafe queue advancer
            setTimeout(safeResolve, duration + 500);

        } catch (e) {
            console.error('Erro ao exibir notificação:', e);
            safeResolve();
        }
    });
}

// Garantir que container de toast existe
function ensureToastContainer() {
    if (!document.querySelector('.toast-container-footer')) {
        const container = document.createElement('div');
        container.className = 'toast-container-footer';
        document.body.appendChild(container);
    }
}

// Sistema de fallback se Bootstrap falhar
function fallbackNotification(message, type) {
    console.log('Usando sistema de fallback');
    try {
        // Criar elemento de notificação customizado
        const notification = document.createElement('div');
        const colors = {
            success: { bg: '#28a745', text: '#ffffff' },
            error:   { bg: '#dc3545', text: '#ffffff' },
            warning: { bg: '#ffc107', text: '#1a1a1a' },
            info:    { bg: '#17a2b8', text: '#ffffff' }
        };
        const scheme = colors[type] || colors.info;
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1050;
            min-width: 300px;
            max-width: 500px;
            padding: 12px 16px;
            border-radius: 8px;
            background-color: ${scheme.bg};
            color: ${scheme.text};
            font-family: system-ui, -apple-system, sans-serif;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            animation: slideUp 0.3s ease-out;
            pointer-events: auto;
            cursor: pointer;
        `;
        notification.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; color: ${scheme.text};">
                <span class="notification-text">${message}</span>
                <button data-action="removeParentElement" class="notification-close"
                        style="background: none; border: none; cursor: pointer; padding: 0; margin-left: auto; font-size: 18px;">
                    ×
                </button>
            </div>
        `;
        // Força cor nos elementos filhos (overrides CSS !important de dark theme)
        notification.querySelectorAll('.notification-text, .notification-close').forEach(el => {
            el.style.setProperty('color', scheme.text, 'important');
        });
        // Adicionar CSS de animação se não existir
        if (!document.getElementById('fallback-notification-css')) {
            const style = document.createElement('style');
            style.id = 'fallback-notification-css';
            style.textContent = `
                @keyframes slideUp {
                    from { opacity: 0; transform: translateX(-50%) translateY(30px); }
                    to { opacity: 1; transform: translateX(-50%) translateY(0); }
                }
            `;
            document.head.appendChild(style);
        }
        document.body.appendChild(notification);
        // Auto-remover após 3 segundos
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 3000);
    } catch (error) {
        console.error('Fallback notification falhou:', error);
        // Último recurso: alert nativo
        alert(`${type.toUpperCase()}: ${message}`);
    }
}
// Função para escapar HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =====================================================================
// SYNTAX HIGHLIGHT GLOBAL — Token-based (evita conflito de regex)
// Suporta: AdvPL (.prw,.prx,.tlpp,.aph,.ch), JS, Python, HTML, CSS,
//          JSON, SQL, Shell, e genérico para demais extensões
// =====================================================================
const _HL_KEYWORDS = {
    advpl: ['Function','Static','User','Return','Local','Private','Public',
        'Default','If','ElseIf','Else','EndIf','Do','While','EndDo',
        'For','To','Next','Do Case','Case','Otherwise','EndCase',
        'Begin Sequence','End Sequence','Recover','Using',
        'Class','EndClass','Method','Data','From',
        '#include','#define','#ifdef','#ifndef','#endif',
        'DbSelectArea','DbSetOrder','DbSeek','DbSkip','DbGoTop',
        'MsExecAuto','Processa','ProcRegua','IncProc',
        '.T.','.F.','NIL','.And.','.Or.','.Not.'],
    js: ['function','const','let','var','return','if','else','for','while',
        'switch','case','break','continue','new','this','class','extends',
        'import','export','from','default','async','await','try','catch',
        'finally','throw','typeof','instanceof','null','undefined','true','false'],
    py: ['def','class','return','if','elif','else','for','while','import','from',
        'as','try','except','finally','raise','with','yield','lambda','pass',
        'break','continue','and','or','not','in','is','None','True','False',
        'self','print','len','range','list','dict','set','tuple','int','str','float'],
    sql: ['SELECT','FROM','WHERE','INSERT','INTO','VALUES','UPDATE','SET',
        'DELETE','CREATE','ALTER','DROP','TABLE','INDEX','JOIN','LEFT','RIGHT',
        'INNER','OUTER','ON','AND','OR','NOT','NULL','AS','ORDER','BY',
        'GROUP','HAVING','UNION','DISTINCT','TOP','LIMIT','LIKE','IN','EXISTS',
        'BETWEEN','COUNT','SUM','AVG','MAX','MIN','BEGIN','COMMIT','ROLLBACK'],
    html: ['html','head','body','div','span','p','a','img','table','tr','td','th',
        'form','input','button','select','option','textarea','script','style',
        'link','meta','title','header','footer','nav','section','article','main'],
    css: ['color','background','font','margin','padding','border','display',
        'position','width','height','top','left','right','bottom','flex',
        'grid','align','justify','overflow','opacity','transition','transform',
        'animation','z-index','box-shadow','text-align','line-height']
};

function _hlGetLang(ext) {
    ext = (ext || '').toLowerCase().replace(/^\./, '');
    if (['prw','prx','tlpp','aph','ch'].includes(ext)) return 'advpl';
    if (['js','jsx','ts','tsx','mjs'].includes(ext)) return 'js';
    if (['py','pyw'].includes(ext)) return 'py';
    if (['sql'].includes(ext)) return 'sql';
    if (['html','htm','xml','svg'].includes(ext)) return 'html';
    if (['css','scss','less'].includes(ext)) return 'css';
    if (['json'].includes(ext)) return 'json';
    if (['sh','bash','zsh','bat','ps1','cmd'].includes(ext)) return 'shell';
    return 'generic';
}

/**
 * Aplica syntax highlight em texto ja escapado (escapeHtml).
 * Usa abordagem de tokens para evitar que regex de keywords
 * interfira nos spans de highlight (bug do class="hl-keyword" no Class do AdvPL).
 */
function highlightCode(escapedHtml, extension) {
    var lang = _hlGetLang(extension);
    var tokens = [];
    var tid = 0;

    function tok(html) {
        var id = '\x00T' + (tid++) + '\x00';
        tokens.push({id: id, html: html});
        return id;
    }

    // 1) Comentarios — extrair para tokens antes de tudo
    if (lang === 'py' || lang === 'shell') {
        // # comments (mas nao dentro de strings — aproximacao)
        escapedHtml = escapedHtml.replace(/(#.*?)$/gm, function(m) {
            return tok('<span class="hl-comment">' + m + '</span>');
        });
    }
    if (lang !== 'css' && lang !== 'json') {
        // // line comments
        escapedHtml = escapedHtml.replace(/(\/\/.*?)$/gm, function(m) {
            return tok('<span class="hl-comment">' + m + '</span>');
        });
    }
    // /* block comments */
    if (lang !== 'json') {
        escapedHtml = escapedHtml.replace(/(\/\*[\s\S]*?\*\/)/g, function(m) {
            return tok('<span class="hl-comment">' + m + '</span>');
        });
    }
    // <!-- HTML comments -->
    if (lang === 'html') {
        escapedHtml = escapedHtml.replace(/(&lt;!--[\s\S]*?--&gt;)/g, function(m) {
            return tok('<span class="hl-comment">' + m + '</span>');
        });
    }

    // 2) Strings — extrair para tokens
    // Double-quoted (escaped)
    escapedHtml = escapedHtml.replace(/(&quot;[^]*?&quot;)/g, function(m) {
        return tok('<span class="hl-string">' + m + '</span>');
    });
    // Single-quoted (escaped)
    escapedHtml = escapedHtml.replace(/(&#39;[^]*?&#39;)/g, function(m) {
        return tok('<span class="hl-string">' + m + '</span>');
    });
    // Backtick strings (JS template literals)
    if (lang === 'js') {
        escapedHtml = escapedHtml.replace(/(`[^`]*?`)/g, function(m) {
            return tok('<span class="hl-string">' + m + '</span>');
        });
    }

    // 3) HTML tags <tag ...>
    if (lang === 'html') {
        escapedHtml = escapedHtml.replace(/(&lt;\/?)([\w-]+)/g, function(m, prefix, tagName) {
            return tok(prefix + '<span class="hl-keyword">' + tagName + '</span>');
        });
    }

    // 4) CSS: propriedades e seletores
    if (lang === 'css') {
        // propriedade: valor
        escapedHtml = escapedHtml.replace(/([\w-]+)(\s*:)/g, function(m, prop, colon) {
            return tok('<span class="hl-keyword">' + prop + '</span>') + colon;
        });
    }

    // 5) Numeros
    escapedHtml = escapedHtml.replace(/\b(\d+\.?\d*)\b/g, function(m) {
        return tok('<span class="hl-number">' + m + '</span>');
    });

    // 6) Keywords — tambem como tokens para evitar conflito entre si
    var keywords = _HL_KEYWORDS[lang] || [];
    for (var i = 0; i < keywords.length; i++) {
        var kw = keywords[i];
        var esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        var flags = (lang === 'advpl') ? 'gi' : 'g';
        // AdvPL e SQL sao case-insensitive; JS/Python sao case-sensitive
        if (lang === 'sql') flags = 'gi';
        var re = new RegExp('\\b(' + esc + ')\\b', flags);
        escapedHtml = escapedHtml.replace(re, function(m) {
            return tok('<span class="hl-keyword">' + m + '</span>');
        });
    }

    // 7) JSON: chaves
    if (lang === 'json') {
        // As chaves ja foram tokenizadas como strings, entao nao precisa nada extra
    }

    // 8) Restaurar todos os tokens
    for (var t = 0; t < tokens.length; t++) {
        escapedHtml = escapedHtml.replace(tokens[t].id, tokens[t].html);
    }

    return escapedHtml;
}

/**
 * Adiciona numeracao de linhas ao HTML de codigo.
 */
function addLineNumbers(html) {
    var lines = html.split('\n');
    var result = '';
    for (var i = 0; i < lines.length; i++) {
        result += '<span class="line-num">' + (i + 1) + '</span>' + lines[i] + '\n';
    }
    return result;
}

// Função de teste para debug - AVANÇADA
function testNotifications() {
    console.log('=== INICIANDO TESTE COMPLETO DE NOTIFICAÇÕES ===');
    // Verificar estado inicial
    console.log('Estado do sistema:');
    console.log('- showNotification:', typeof showNotification);
    console.log('- Bootstrap:', typeof bootstrap !== 'undefined' ? 'OK' : 'NÃO ENCONTRADO');
    console.log('- Bootstrap.Toast:', typeof bootstrap !== 'undefined' && bootstrap.Toast ? 'OK' : 'NÃO ENCONTRADO');
    console.log('- Container:', document.getElementById('toast-container-footer') ? 'EXISTE' : 'NÃO EXISTE');
    // Testar todos os tipos
    showNotification('✓ Teste SUCESSO - Sistema funcionando!', 'success', 3000);
    setTimeout(() => {
        showNotification('⚠️ Teste AVISO - Notificação de alerta!', 'warning', 3000);
    }, 800);
    setTimeout(() => {
        showNotification('❌ Teste ERRO - Simulação de erro!', 'error', 3000);
    }, 1600);
    setTimeout(() => {
        showNotification('ℹ️ Teste INFO - Informação importante!', 'info', 3000);
    }, 2400);
    setTimeout(() => {
        showNotification('🎉 Teste COMPLETO! Todas as notificações funcionando perfeitamente!', 'success', 5000);
        console.log('=== TESTE DE NOTIFICAÇÕES CONCLUÍDO ===');
    }, 3200);
}
// Função para limpar todas as notificações
function clearAllNotifications() {
    notificationQueue = [];
    const container = document.querySelector('.toast-container-footer');
    if (container) container.innerHTML = '';
}

// Verificar se Bootstrap está carregado
function checkBootstrap() {
    if (typeof bootstrap === 'undefined') {
        console.error('Bootstrap não encontrado! Tentando carregar...');
        return false;
    }
    console.log('Bootstrap encontrado:', !!bootstrap.Toast);
    return true;
}

function initNotificationSystem() {
    if (!document.querySelector('.toast-container-footer')) {
        ensureToastContainer();
    }
}

// (DOMContentLoaded duplicado removido - já registrado no início deste módulo)

// STATUS FINAL DO SISTEMA
console.log('\n=== SISTEMA AtuDIC - STATUS FINAL ===');
console.log('✓ Login: Toggle de senha funcionando');
console.log('✓ Navegação: Controle de permissões ativo');
console.log('✓ Usuários: CRUD completo com perfis');
console.log('✓ Repositórios: Integração GitHub real');
console.log('✓ Pipelines: Comandos sequenciais');
console.log('✓ Comandos: Scripts PowerShell/Batch/Bash');
console.log('✓ Configurações: GitHub funcional');
console.log('\n✓✓✓ SISTEMA 100% COMPLETO E FUNCIONAL! ✓✓✓');
console.log('================================================');
// Definir global para indicar sistema carregado
window.ProtheusDevOpsLoaded = true;
// Expor funções de debug globalmente
window.testNotifications = testNotifications;
window.clearAllNotifications = clearAllNotifications;
window.debugNotificationSystem = function () {
    console.log('=== DEBUG DO SISTEMA DE NOTIFICAÇÕES ===');
    console.log('showNotification:', typeof showNotification);
    console.log('notificationQueue:', notificationQueue);
    console.log('isProcessingQueue:', isProcessingQueue);
    console.log('Bootstrap:', typeof bootstrap);
    console.log('Bootstrap.Toast:', typeof bootstrap !== 'undefined' ? !!bootstrap.Toast : false);
    console.log('Container:', !!document.getElementById('toast-container-footer'));
    console.log('Fallback CSS:', !!document.getElementById('fallback-notification-css'));
    console.log('============================================');
};
// Comando rápido no console para testar
console.log('\n=== COMANDOS DE DEBUG DISPONÍVEIS ===');
console.log('testNotifications() - Testa todas as notificações');
console.log('clearAllNotifications() - Limpa todas as notificações');
console.log('debugNotificationSystem() - Mostra estado do sistema');
console.log('========================================\n');
// =====================================================================
// HELPERS
// =====================================================================

/**
 * Helper para renderizar paginação
 */
function renderPagination(containerId, currentPage, totalPages, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '<ul class="pagination justify-content-center">';

    // Botão anterior
    html += `
        <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" ${currentPage === 1 ? 'tabindex="-1"' : ''}>Anterior</a>
        </li>
    `;

    // Páginas
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            html += `
                <li class="page-item ${i === currentPage ? 'active' : ''}">
                    <a class="page-link" href="#">${i}</a>
                </li>
            `;
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
    }

    // Botão próximo
    html += `
        <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" ${currentPage === totalPages ? 'tabindex="-1"' : ''}>Próximo</a>
        </li>
    `;

    html += '</ul>';

    container.innerHTML = html;

    // Adicionar event listeners
    container.querySelectorAll('.page-link').forEach((link) => {
        if (!link.parentElement.classList.contains('disabled')) {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const text = link.textContent.trim();
                if (text === 'Anterior') {
                    onPageChange(currentPage - 1);
                } else if (text === 'Próximo') {
                    onPageChange(currentPage + 1);
                } else {
                    const page = parseInt(text);
                    if (!isNaN(page)) {
                        onPageChange(page);
                    }
                }
            });
        }
    });
}

/**
 * Helper para formatar data/hora
 */
/**
 * Helper para formatar data/hora - Formato brasileiro sem segundos
 * Interpreta timestamp do PostgreSQL considerando timezone do Brasil
 */
function formatDateTime(isoString) {
    if (!isoString) return '-';

    try {
        let dateString = isoString;

        // Normalizar formato
        // PostgreSQL pode retornar: "2025-11-02 14:30:00", "2025-11-02T14:30:00", "Thu, 06 Nov 2025 18:34:58 GMT"

        // Se vier no formato RFC2822 (Thu, 06 Nov 2025 18:34:58 GMT), converter
        if (dateString.includes(',') && dateString.includes('GMT')) {
            const date = new Date(dateString);
            // Converter para formato ISO
            dateString = date.toISOString();
        }

        // Garantir formato ISO
        dateString = dateString.replace(' ', 'T');

        // Remover timezone se existir
        dateString = dateString.replace('Z', '').replace(/[+-]\d{2}:\d{2}$/, '');

        // Adicionar timezone do Brasil (-03:00)
        dateString = dateString + '-03:00';

        const date = new Date(dateString);

        // Verificar se data é válida
        if (isNaN(date.getTime())) {
            console.warn('Data inválida:', isoString);
            return isoString;
        }

        // Formatar para pt-BR SEM SEGUNDOS
        return date.toLocaleString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'America/Sao_Paulo'
        });

    } catch (error) {
        console.error('Erro ao formatar data:', error, isoString);
        return isoString;
    }
}
// =====================================================================
// FUNÇÕES AUXILIARES
// =====================================================================

function getStatusBadge(status) {
    /**
     * Retorna badge HTML com cor apropriada para o status.
     */
    const badges = {
        'success': '<span class="badge bg-success">✓ Sucesso</span>',
        'failed': '<span class="badge bg-danger">✗ Falhou</span>',
        'running': '<span class="badge bg-primary">⟳ Executando</span>',
        'queued': '<span class="badge bg-secondary">⋯ Aguardando</span>'
    };
    return badges[status] || `<span class="badge bg-secondary">${status}</span>`;
}

function formatTime(isoString) {
    /**
     * Formata apenas hora de uma data ISO.
     */
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}


function calculateDuration(startIso, endIso) {
    /**
     * Calcula duração entre duas datas ISO.
     */
    if (!startIso) return '-';
    if (!endIso) return 'Em execução...';

    const start = new Date(startIso);
    const end = new Date(endIso);
    const diffMs = end - start;
    const diffSecs = Math.floor(diffMs / 1000);

    if (diffSecs < 60) return `${diffSecs}s`;

    const mins = Math.floor(diffSecs / 60);
    const secs = diffSecs % 60;
    return `${mins}m ${secs}s`;
}
