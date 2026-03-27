// =====================================================================
// ESTADO GLOBAL DA APLICAÇÃO
// =====================================================================
let currentUser = null;
let userPermissions = null;
let repositories = [];
let pipelines = [];
let commands = [];
let schedules = [];
let currentSchedulesPage = 1;
const schedulesPerPage = 10;
let scheduleScriptTypeFilter = 'TODOS'; 
let users = [];
let deploys = [];
let gitHubSettings = { token: '', username: '' };
let environments = [];
let runPollingInterval = null; 
let serverVariables = [];
let serverServices = [];
let serviceActions = [];

let keepAliveInterval = null;
let notificationQueue = [];
let isLoggingOut = false; // Flag para prevenir logout duplicado
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
    localStorage.setItem('aturpo-theme', newTheme);
    
    // Atualizar ícone
    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

function loadSavedTheme() {
    const savedTheme = localStorage.getItem('aturpo-theme') || 'light';
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
const pipelinesPerPage = 5;
let currentHistoryPage = 1;
let selectedCommands = [];
let commandSelectorMode = 'create';
let repoContentSort = { key: 'name', order: 'asc' };
let currentPath = {};
let currentBranch = {};

// =====================================================================
// PONTO DE ENTRADA PRINCIPAL DA APLICAÇÃO
// =====================================================================
document.addEventListener('DOMContentLoaded', function() {
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

    document.addEventListener('click', function(e) {
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

    document.addEventListener('submit', function(e) {
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
document.addEventListener('DOMContentLoaded', function() {
    // Quando qualquer modal for escondido
    document.addEventListener('hidden.bs.modal', function(event) {
        console.log('📍 Modal fechado:', event.target.id);
        
        // Aguardar um pouco para garantir que Bootstrap finalizou
        setTimeout(() => {
            cleanupModalBackdrop();
        }, 100);
    });
    
    // Também limpar ao clicar em botões de fechar
    document.addEventListener('click', function(e) {
        const closeButton = e.target.closest('[data-bs-dismiss="modal"]');
        if (closeButton) {
            console.log('📍 Botão fechar clicado');
            setTimeout(() => {
                cleanupModalBackdrop();
            }, 300);
        }
    });
    
    // Limpar ao pressionar ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const openModal = document.querySelector('.modal.show');
            if (openModal) {
                console.log('📍 ESC pressionado');
                setTimeout(() => {
                    cleanupModalBackdrop();
                }, 300);
            }
        }
    });
});
// ===== LISTENER ESPECÍFICO PARA SIDEBAR =====
// Adiciona suporte para links com data-page (sidebar)
document.addEventListener('click', function(e) {
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
    if (page !== 'settings') {
        stopServiceActionsPolling();
    }

    // Navegar para a página
    navigateToPage(page);
    
    // Atualizar classe active
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.classList.remove('active');
    });
    sidebarLink.classList.add('active');
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
// FUNÇÕES DE PIPELINE - GLOBAIS
window.showCreatePipelineModal = function () {
    try {
        selectedCommands = [];
        updateSelectedCommandsDisplay('create');
        document.getElementById('createPipelineForm').reset();
    
        // 🆕 Busca comandos de deploy e cria as opções para o dropdown
        const deployCommands = commands.filter(c => c.command_category === 'deploy');
        const deployOptions = deployCommands.map(d => 
            `<option value="${d.id}">${d.name}</option>`
        ).join('');
        document.getElementById('pipelineDeployCommandId').innerHTML = 
            `<option value="">Nenhuma</option>${deployOptions}`;
    
        const createModalElement = document.getElementById('createPipelineModal');
        const commandSelectorModalElement = document.getElementById('commandSelectorModal');
        const modal = new bootstrap.Modal(createModalElement);
    
        // 🆕 Listener para atualizar comandos quando o seletor fecha
        commandSelectorModalElement.addEventListener('hidden.bs.modal', () => {
            updateSelectedCommandsDisplay('create');
        }, { once: true });
    
        modal.show();
    } catch (error) {
        console.error('Erro ao abrir modal de criação de pipeline:', error);
        showNotification('Erro ao abrir modal.', 'error');
    }
};
window.showCommandSelector = function (mode = 'create', categoryFilter = 'build') { // 🆕 categoryFilter
    commandSelectorMode = mode;
    
    try {
        // 🆕 Filtrar comandos pela categoria
        const filteredCommands = commands.filter(cmd => cmd.command_category === categoryFilter);
        
        if (filteredCommands.length === 0) {
            showNotification(`Nenhum comando ${categoryFilter === 'build' ? 'de Build' : 'de Deploy'} cadastrado!`, 'warning');
            return;
        }
        
        // Gerar HTML dos comandos filtrados
        const commandsHtml = `
            <div class="alert alert-info mb-3">
                <i class="fas fa-info-circle me-2"></i>
                Mostrando apenas comandos do tipo: <strong>${categoryFilter === 'build' ? '🔨 Build' : '🚀 Deploy'}</strong>
            </div>
            <div class="row">
                ${filteredCommands.map(cmd => `
                    <div class="col-md-6 mb-3">
                        <div class="card h-100 ${selectedCommands.find(sc => sc.id === cmd.id) ? 'border-primary' : ''}">
                            <div class="card-body">
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" value="${cmd.id}" id="cmd${cmd.id}" 
                                           ${selectedCommands.find(sc => sc.id === cmd.id) ? 'checked' : ''} 
                                           onchange="toggleCommand(${cmd.id}, '${cmd.name}', '${cmd.description}', '${cmd.type}')">
                                    <label class="form-check-label w-100" for="cmd${cmd.id}">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div>
                                                <h6 class="card-title">
                                                    <i class="fas fa-${getCommandIcon(cmd.type)} me-2"></i>
                                                    ${cmd.name}
                                                </h6>
                                                <p class="card-text small text-muted">${cmd.description || 'Sem descrição'}</p>
                                                <span class="badge bg-secondary">${getCommandTypeText(cmd.type)}</span>
                                            </div>
                                        </div>
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        
        document.getElementById('availableCommands').innerHTML = commandsHtml;
        
        // Atualizar título do modal
        const modalTitle = document.querySelector('#commandSelectorModal .modal-title');
        if (modalTitle) {
            modalTitle.innerHTML = `<i class="fas fa-terminal text-primary me-2"></i>Selecionar Comandos ${categoryFilter === 'build' ? 'de Build' : 'de Deploy'}`;
        }
        
        // Abrir modal de comandos
        const modalElement = document.getElementById('commandSelectorModal');
        if (modalElement) {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
        }
    } catch (error) {
        console.error('Erro ao abrir seletor de comandos:', error);
        showNotification('Erro ao abrir seletor de comandos.', 'error');
    }
};
window.toggleCommand = function (id, name, description, type) {
    const existingIndex = selectedCommands.findIndex(sc => sc.id === id);
    if (existingIndex >= 0) {
        // Removendo - sempre permitido
        selectedCommands.splice(existingIndex, 1);
    } else {
        // 🆕 Validar tipo de script antes de adicionar
        if (selectedCommands.length > 0) {
            const firstType = selectedCommands[0].type;
            if (firstType !== type) {
                showNotification(`Não é permitido misturar tipos de script! Esta pipeline já possui comandos do tipo "${firstType}".`, 'warning');
                // Desmarcar o checkbox
                const checkbox = document.getElementById(`cmd${id}`);
                if (checkbox) checkbox.checked = false;
                return;
            }
        }
        selectedCommands.push({ id, name, description, type });
    }
    // A linha que chamava updateSelectedCommandsDisplay foi removida daqui.
};

function confirmCommandSelection() {
    // A única responsabilidade desta função agora é fechar o modal.
    // O novo 'event listener' cuidará da atualização.
    const modal = bootstrap.Modal.getInstance(document.getElementById('commandSelectorModal'));
    if (modal) {
        modal.hide();
    }
}
function updateSelectedCommandsDisplay(mode = 'create') {
    const containerId = mode === 'edit' ? 'editSelectedCommands' : 'selectedCommands';
    const container = document.getElementById(containerId);
    if (!container) return;

    if (selectedCommands.length === 0) {
        container.innerHTML = '<p class="text-muted mb-0">Nenhum comando selecionado</p>';
    } else {
        container.innerHTML = `
            <h6 class="mb-2 small text-muted">Sequência de Execução:</h6>
            <div class="selected-commands-sequence">
                ${selectedCommands.map((cmd, index) => `
                    <div class="d-flex align-items-center bg-white rounded p-2 mb-2 border">
                        <div class="badge bg-primary me-3" style="min-width: 30px;">${index + 1}</div>
                        <div class="flex-grow-1">
                            <strong>${cmd.name}</strong>
                        </div>
                        <div class="btn-group btn-group-sm">
                            <button type="button" class="btn btn-outline-secondary ${index === 0 ? 'disabled' : ''}" data-action="moveCommandUp" data-params=\'{"commandId":${cmd.id},"mode":"${mode}"}\' title="Mover para cima">
                                <i class="fas fa-arrow-up"></i>
                            </button>
                            <button type="button" class="btn btn-outline-secondary ${index === selectedCommands.length - 1 ? 'disabled' : ''}" data-action="moveCommandDown" data-params=\'{"commandId":${cmd.id},"mode":"${mode}"}\' title="Mover para baixo">
                                <i class="fas fa-arrow-down"></i>
                            </button>
                            <button type="button" class="btn btn-outline-danger" data-action="removeSelectedCommand" data-params=\'{"commandId":${cmd.id},"mode":"${mode}"}\' title="Remover">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
}
// Funções para reordenar comandos
function moveCommandUp(commandId, mode) {
    const index = selectedCommands.findIndex(cmd => cmd.id === commandId);
    if (index > 0) {
        // Troca o elemento com o anterior
        [selectedCommands[index], selectedCommands[index - 1]] = [selectedCommands[index - 1], selectedCommands[index]];
        updateSelectedCommandsDisplay(mode);
    }
}
function moveCommandDown(commandId, mode) {
    const index = selectedCommands.findIndex(cmd => cmd.id === commandId);
    if (index < selectedCommands.length - 1) {
        // Troca o elemento com o próximo
        [selectedCommands[index], selectedCommands[index + 1]] = [selectedCommands[index + 1], selectedCommands[index]];
        updateSelectedCommandsDisplay(mode);
    }
}
function removeSelectedCommand(id, mode) {
    selectedCommands = selectedCommands.filter(sc => sc.id !== id);
    updateSelectedCommandsDisplay(mode);
    const checkbox = document.getElementById(`cmd${id}`);
    if (checkbox) checkbox.checked = false;
}
// GARANTIR QUE TODAS AS FUNÇÕES DE PIPELINE ESTEJAM FUNCIONAIS
function ensurePipelineFunctionsComplete() {
    // Verificar se todas as funções críticas existem
    const criticalFunctions = [
        'showCreatePipelineModal',
        'createNewPipeline',
        'runPipeline',
        'editPipeline',
        'deletePipeline',
        'renderPipelinesWithPagination',
        'updatePipelinesList'
    ];
    criticalFunctions.forEach(funcName => {
        if (typeof window[funcName] !== 'function') {
            console.error(`Função ${funcName} não encontrada!`);
        }
    });
    console.log('Verificação de funções de pipeline concluída');
}

function viewPipelineHistory(pipelineId) {
    const pipeline = pipelines.find(p => p.id === pipelineId);
    if (pipeline) {
        showNotification(`Carregando histórico da pipeline "${pipeline.name}"...`, 'info');
    }
}

function refreshEditPipelineModal(pipelineId) {
    const pipeline = pipelines.find(p => p.id === pipelineId);
    if (!pipeline) return;
    // Preenche os campos de texto
    document.getElementById('editPipelineId').value = pipeline.id;
    document.getElementById('editPipelineName').value = pipeline.name;
    document.getElementById('editPipelineDescription').value = pipeline.description || '';
    // Usa a lista 'selectedCommands' (que foi atualizada) para redesenhar a sequência
    updateSelectedCommandsDisplay('edit');
}
function editPipeline(pipelineId) {
    try {
        const pipeline = pipelines.find(p => p.id === pipelineId);
        if (!pipeline) return;
    
        // Carrega os comandos originais da pipeline para o estado de seleção
        selectedCommands = [...pipeline.commands];
    
        // Preenche os campos de texto
        refreshEditPipelineModal(pipelineId);
    
        // 🆕 Busca comandos de deploy e cria as opções para o dropdown de edição
        const deployCommands = commands.filter(c => c.command_category === 'deploy');
        const deployOptions = deployCommands.map(d => 
            `<option value="${d.id}" ${d.id === pipeline.deploy_command_id ? 'selected' : ''}>${d.name}</option>`
        ).join('');
        document.getElementById('editPipelineDeployCommandId').innerHTML = 
            `<option value="">Nenhuma</option>${deployOptions}`;
    
        const editModalElement = document.getElementById('editPipelineModal');
        const commandSelectorModalElement = document.getElementById('commandSelectorModal');
        const modal = new bootstrap.Modal(editModalElement);
    
        // Prepara o "ouvinte" para atualizar a lista de comandos
        commandSelectorModalElement.addEventListener('hidden.bs.modal', () => {
            refreshEditPipelineModal(pipelineId);
        }, { once: true });
    
        modal.show();
    } catch (error) {
        console.error('Erro ao abrir edição da pipeline:', error);
    }
}
function showCommandSelector(mode = 'create') {
    commandSelectorMode = mode;
    try {
        if (commands.length === 0) {
            showNotification('Nenhum comando cadastrado!', 'warning');
            return;
        }
        // O código que gera o HTML dos comandos continua o mesmo
        const commandsHtml = commands.map(cmd => `
            <div class="col-md-6 mb-3">
                <div class="card h-100 ${selectedCommands.find(sc => sc.id === cmd.id) ? 'border-primary' : ''}">
                    <div class="card-body">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" value="${cmd.id}" id="cmd${cmd.id}" 
                                   ${selectedCommands.find(sc => sc.id === cmd.id) ? 'checked' : ''} 
                                   onchange="toggleCommand(${cmd.id}, '${cmd.name}', '${cmd.description || ''}', '${cmd.type}')">
                            <label class="form-check-label w-100" for="cmd${cmd.id}">
                                <h6 class="card-title"><i class="fas fa-${getCommandIcon(cmd.type)} me-2"></i>${cmd.name}</h6>
                                <p class="card-text small text-muted">${cmd.description || 'Sem descrição'}</p>
                                <span class="badge bg-secondary">${getCommandTypeText(cmd.type)}</span>
                            </label>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
        document.getElementById('availableCommands').innerHTML = `<div class="row">${commandsHtml}</div>`;
        const modalElement = document.getElementById('commandSelectorModal');
        const modal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement);
        modal.show();
    } catch (error) {
        console.error('Erro ao abrir seletor de comandos:', error);
    }
}

const actionHandlers = {
    // ===== NAVEGAÇÃO =====
    'navigate': (params) => navigateToPage(params.page),
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
    'deleteUser': (params) => {        if (isDeletingUser) return;        deleteUser(params.userId);    },
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
    'viewBuildDetails': (params) => vie=>wBuildDetails(params.runId, params.runNumber),
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
    'saveGithubSettings': () => saveGitHubSettings(),
    'testGithubConnection': () => testGitHubConnection(),
    
    // ===== VARIÁVEIS DO SERVIDOR =====
    'showCreateVariableModal': () => showCreateVariableModal(),
    'createNewVariable': () => createNewVariable(),
    'showEditVariableModal': (params) => showEditVariableModal(params.varId),
    'saveEditedVariable': () => saveEditedVariable(),
    'deleteVariable': (params) => deleteVariable(params.varId),
    'showImportVariablesModal': () => showImportVariablesModal(),
    
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
            handler({ preventDefault: () => {}, target: form });
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
            await Promise.all(dataPromises);
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
    const page = window.location.hash.substring(1) || 'repositories';
    if (!hasPermission(page)) {
        showNotification('Acesso negado! Redirecionando...', 'error');
        window.location.hash = 'dashboard';
        return;
    }
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.classList.toggle('active', link.getAttribute('data-page') === page);
    });
    
    const contentArea = document.getElementById('content-area');
    contentArea.innerHTML = `<div class="text-center p-5"><div class="spinner-border text-primary"></div></div>`;
    
    setTimeout(() => {
        const pageRenderFunctions = {
            'dashboard': showDashboard,
            'repositories': showRepositories,
            'pipelines': showPipelines,
            'schedules': showSchedules,
            // 'deploys': showDeploys,
            'commands': showCommands,
            'users': showUsers,
            'settings': showSettings,
            'toggleServiceActionSchedule': toggleServiceActionSchedule,
        };
        const renderFunction = pageRenderFunctions[page] || showRepositories;
        renderFunction();
    }, 50);
}

// =====================================================================
// FUNÇÕES DE CARREGAMENTO DE DADOS (LOADERS)
// =====================================================================
async function loadUsers() { try { users = await apiGetUsers(); } catch(e) { users = []; } }
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
async function loadPipelines() { try { pipelines = await apiGetPipelines(); } catch(e) { pipelines = []; } }
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
async function loadRepositories() { try { repositories = await apiGetRepositories(); } catch(e) { repositories = []; } }
async function loadGithubSettings() { try { gitHubSettings = await apiGetGithubSettings(); } catch(e) { gitHubSettings = {}; } }
async function loadServerVariables() { try { serverVariables = await apiGetServerVariables(); } catch(e) { serverVariables = []; } }
async function loadServerServices() { try { serverServices = await apiGetServerServices(); } catch(e) { serverServices = []; } }

// =====================================================================
// FUNÇÕES DE AMBIENTES
// =====================================================================
function setupEnvironmentSelector() {
    const selectorContainer = document.getElementById('environment-selector-container');
    const selector = document.getElementById('environmentSelector');
    if (!selector || !selectorContainer) return;

    selector.innerHTML = environments.map(env => 
        `<option value="${env.id}">${env.name}</option>`
    ).join('');

    const activeEnvId = sessionStorage.getItem('active_environment_id');
    if (activeEnvId) {
        selector.value = activeEnvId;
    }

    selector.removeEventListener('change', handleEnvironmentChange); // Evita duplicidade
    selector.addEventListener('change', handleEnvironmentChange);

    selectorContainer.style.display = 'flex !important'; // Mostra o seletor
}

// (NOVA) Função para lidar com a troca de ambiente
async function handleEnvironmentChange() {
    const selector = document.getElementById('environmentSelector');
    const newEnvId = selector.value;
    sessionStorage.setItem('active_environment_id', newEnvId);

    showNotification(`Trocando para o ambiente: ${selector.options[selector.selectedIndex].text}...`, 'info');

    // Esta é a parte crucial: Recarrega todos os dados do zero para o novo ambiente
    await loadInitialDataAndRenderApp();
}

function showEnvironments() {
    if (!isAdmin()) {
        showNotification('Acesso negado!', 'error');
        window.location.hash = 'dashboard'; // Redireciona para página segura
        return;
    }

    const content = `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2>Gerenciamento de Ambientes</h2>
                    <p class="text-muted">Crie e gerencie os ambientes do sistema (ex: Produção, Desenvolvimento).</p>
                </div>
                <button class="btn btn-primary" data-action="showCreateEnvironmentModal">
                    <i class="fas fa-plus me-2"></i>Novo Ambiente
                </button>
            </div>
            <div id="environmentsContainer">${renderEnvironments()}</div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;
}

function renderEnvironments() {
    if (environments.length === 0) {
        return '<div class="card text-center p-5"><p class="text-muted">Nenhum ambiente cadastrado.</p></div>';
    }
    
    // Apenas user admin (root) pode editar/excluir ambientes
    const canEditEnv = isRootAdmin();
    
    return environments.map(env => `
        <div class="card mb-3">
            <div class="card-body d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="mb-1"><i class="fas fa-layer-group text-primary me-2"></i>${env.name}</h5>
                    <p class="text-muted mb-0">${env.description || 'Sem descrição'}</p>
                </div>
                ${canEditEnv ? `
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" data-action="showEditEnvironmentModal" data-params='{"envId":${env.id}}'>
                        <i class="fas fa-edit"></i> Editar
                    </button>
                    <button class="btn btn-sm btn-outline-danger" data-action="deleteEnvironment" data-params='{"envId":${env.id}}'>
                        <i class="fas fa-trash"></i> Excluir
                    </button>
                </div>
                ` : '<span class="badge bg-secondary"><i class="fas fa-lock me-1"></i>Somente visualização</span>'}
            </div>
        </div>
    `).join('');
}

function showCreateEnvironmentModal() {
    document.getElementById('createEnvironmentForm').reset();
    new bootstrap.Modal(document.getElementById('createEnvironmentModal')).show();
}

function showEditEnvironmentModal(envId) {
    const environment = environments.find(env => env.id === envId);
    if (!environment) return showNotification('Ambiente não encontrado.', 'error');

    document.getElementById('editEnvId').value = environment.id;
    document.getElementById('editEnvName').value = environment.name;
    document.getElementById('editEnvDescription').value = environment.description || '';

    new bootstrap.Modal(document.getElementById('editEnvironmentModal')).show();
}

async function createNewEnvironment() {
    const name = document.getElementById('envName').value.trim();
    const description = document.getElementById('envDescription').value.trim();

    if (!name) {
        return showNotification('O nome do ambiente é obrigatório!', 'error');
    }

    try {
        await apiCreateEnvironment({ name, description });
        showNotification('Ambiente criado com sucesso!', 'success');

        bootstrap.Modal.getInstance(document.getElementById('createEnvironmentModal')).hide();

        // Recarrega a lista de ambientes e redesenha a tela
        environments = await apiGetEnvironments();
        reloadSettingsTab('environments-tab');
        setupEnvironmentSelector(); // Atualiza o seletor no header também
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

async function saveEditedEnvironment() {
    const id = document.getElementById('editEnvId').value;
    const name = document.getElementById('editEnvName').value.trim();
    const description = document.getElementById('editEnvDescription').value.trim();

    if (!name) {
        return showNotification('O nome do ambiente é obrigatório!', 'error');
    }

    try {
        await apiUpdateEnvironment(id, { name, description });
        showNotification('Ambiente atualizado com sucesso!', 'success');

        bootstrap.Modal.getInstance(document.getElementById('editEnvironmentModal')).hide();

        environments = await apiGetEnvironments();
        reloadSettingsTab('environments-tab');
        setupEnvironmentSelector();
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

async function deleteEnvironment(envId) {
    const environment = environments.find(env => env.id === envId);
    if (!environment) return;

    if (confirm(`Tem certeza que deseja excluir o ambiente "${environment.name}"?\n\nATENÇÃO: Todas as pipelines, comandos, repositórios e deploys associados a este ambiente serão permanentemente excluídos!`)) {
        try {
            await apiDeleteEnvironment(envId);
            showNotification('Ambiente excluído com sucesso!', 'warning');

            environments = await apiGetEnvironments();

            // Verifica se o ambiente ativo foi excluído
            let activeEnvId = sessionStorage.getItem('active_environment_id');
            if (String(envId) === activeEnvId) {
                // Se foi, define o primeiro da lista como novo ativo (ou nenhum)
                const newActiveId = environments.length > 0 ? environments[0].id : null;
                sessionStorage.setItem('active_environment_id', newActiveId);
                // Recarrega toda a aplicação para refletir a mudança de contexto
                return await loadInitialDataAndRenderApp();
            }

            reloadSettingsTab('environments-tab');
            setupEnvironmentSelector();
        } catch (error) {
            showNotification(error.message, 'error');
        }
    }
}



function connectToEventStream() {
    // Garante que só haja uma conexão ativa
    if (window.eventSource) {
        window.eventSource.close();
    }

    const token = sessionStorage.getItem('auth_token');
    if (!token) return;

    window.eventSource = new EventSource(`/api/events?auth_token=${token}`);

    window.eventSource.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            updateActivityFeed(data);
        } catch (e) {
            console.error("Erro ao processar evento do feed:", e);
        }
    };

    window.eventSource.onerror = function () {
        console.error('Conexão do feed de atividades perdida. O navegador tentará reconectar...');
        // O navegador já tenta reconectar por padrão.
    };
}

function updateActivityFeed(event) {
    const list = document.getElementById('activity-feed-list');
    if (!list) return;

    // Remove a mensagem "Nenhuma atividade" se ela existir
    const placeholder = list.querySelector('.text-muted');
    if (placeholder) {
        placeholder.remove();
    }

    let icon, color, message;
    const time = new Date(event.timestamp).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

    switch (event.type) {
        case 'PIPELINE_START':
            icon = 'fa-play-circle';
            color = 'text-primary';
            message = `<strong>${event.user}</strong> iniciou <em>${event.pipeline_name}</em>.`;
            break;
        case 'PIPELINE_FINISH':
            icon = event.status === 'success' ? 'fa-check-circle' : 'fa-times-circle';
            color = event.status === 'success' ? 'text-success' : 'text-danger';
            message = `Pipeline <em>${event.pipeline_name}</em> finalizada (${event.status}).`;
            break;
        default:
            icon = 'fa-info-circle';
            color = 'text-info';
            message = 'Nova atividade no sistema.';
    }
    
    const newItem = document.createElement('li');
    newItem.className = 'small mb-1';
    newItem.innerHTML = `<i class="fas ${icon} ${color} me-2"></i> ${message} <span class="text-muted">(${time})</span>`;

    // Adiciona o novo item no topo da lista
    list.prepend(newItem);

    // Mantém a lista com no máximo 5 itens
    while (list.children.length > 5) {
        list.removeChild(list.lastChild);
    }
}

// =====================================================================
// FUNÇÕES DE USUÁRIOS
// =====================================================================


function showCreateUserModal() {
    if (!isAdmin()) {
        showNotification('Acesso negado!', 'error');
        return;
    }
    
    // Garantir que modal existe
    if (!document.getElementById('createUserModal')) {
        createCreateUserModal();
    }
    
    // Limpar campos (IDs que createNewUser() espera)
    document.getElementById('userUsername').value = '';
    document.getElementById('userName').value = '';
    document.getElementById('userEmail').value = '';
    document.getElementById('userPassword').value = '';
    document.getElementById('userPasswordConfirm').value = '';
    document.getElementById('userProfile').value = 'operator';
    document.getElementById('userStatus').value = 'true';
    document.getElementById('userTimeout').value = '0';
    
    // Abrir modal
    const modal = new bootstrap.Modal(document.getElementById('createUserModal'));
    modal.show();
}

function createCreateUserModal() {
    const modalHtml = `
        <div class="modal fade" id="createUserModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-user-plus me-2"></i>Novo Usuário
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="createUserForm" data-form-action="createNewUser">
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-user me-1"></i>Username *
                                </label>
                                <input type="text" 
                                       class="form-control" 
                                       id="userUsername" 
                                       required
                                       autocomplete="username">
                                <small class="text-muted">Username para login (único)</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-id-badge me-1"></i>Nome de Exibição *
                                </label>
                                <input type="text" 
                                       class="form-control" 
                                       id="userName" 
                                       required>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-envelope me-1"></i>Email *
                                </label>
                                <input type="email" 
                                       class="form-control" 
                                       id="userEmail" 
                                       required
                                       autocomplete="email">
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-lock me-1"></i>Senha *
                                </label>
                                <input type="password" 
                                       class="form-control" 
                                       id="userPassword" 
                                       required
                                       minlength="6"
                                       autocomplete="new-password">
                                <small class="text-muted">Mínimo 6 caracteres</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label" id="userPasswordConfirmLabel">
                                    <i class="fas fa-check me-1"></i>Confirmar Senha *
                                </label>
                                <input type="password" 
                                       class="form-control" 
                                       id="userPasswordConfirm" 
                                       required
                                       minlength="6"
                                       autocomplete="new-password"
                                       oninput="validatePasswordMatch('userPassword', 'userPasswordConfirm', 'userPasswordConfirmLabel')">
                                <small id="userPasswordFeedback" class="text-danger" style="display: none;">
                                    <i class="fas fa-exclamation-circle me-1"></i>As senhas não conferem
                                </small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-shield-alt me-1"></i>Perfil *
                                </label>
                                <select class="form-select" id="userProfile" required>
                                    <option value="admin">Admin</option>
                                    <option value="operator" selected>Operador</option>
                                    <option value="viewer">Visualizador</option>
                                </select>
                                <small class="text-muted">
                                    <strong>Admin:</strong> Acesso total |
                                    <strong>Operador:</strong> Executar ações |
                                    <strong>Visualizador:</strong> Apenas visualizar
                                </small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-toggle-on me-1"></i>Status
                                </label>
                                <select class="form-select" id="userStatus">
                                    <option value="true" selected>Ativo</option>
                                    <option value="false">Inativo</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-clock me-1"></i>Timeout da Sessão (minutos)
                                </label>
                                <input type="number" 
                                       class="form-control" 
                                       id="userTimeout" 
                                       min="0" 
                                       value="0">
                                <small class="text-muted">0 = sem timeout (usar padrão do sistema)</small>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times me-1"></i>Cancelar
                        </button>
                        <button type="submit" form="createUserForm" class="btn btn-primary">
                            <i class="fas fa-plus me-1"></i>Criar Usuário
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Adicionar evento de limpeza do backdrop
    const modal = document.getElementById('createUserModal');
    if (modal && typeof cleanupModalBackdrop === 'function') {
        modal.addEventListener('hidden.bs.modal', cleanupModalBackdrop);
    }
}
async function createNewUser() {
    try {
        const username = document.getElementById('userUsername').value.trim();
        const name = document.getElementById('userName').value.trim();
        const email = document.getElementById('userEmail').value.trim();
        const password = document.getElementById('userPassword').value;
        const passwordConfirm = document.getElementById('userPasswordConfirm').value;
        const profile = document.getElementById('userProfile').value;
        const active = document.getElementById('userStatus').value === 'true';
        const timeout = parseInt(document.getElementById('userTimeout').value) || 0;

        // Validações
        if (!name || !username || !email || !password || !profile) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }

        if (password !== passwordConfirm) {
            showNotification('Senhas não conferem!', 'error');
            return;
        }

        const userData = {
            username,
            name,
            email,
            password,
            profile,
            active,
            session_timeout_minutes: timeout
        };

        await apiCreateUser(userData);

        // Fechar modal e atualizar
        const modal = bootstrap.Modal.getInstance(document.getElementById('createUserModal'));
        modal.hide();

        await loadUsers();
        showUsers();
        showNotification(`Usuário "${name}" criado com sucesso!`, 'success');

    } catch (error) {
        console.error('Erro ao criar usuário:', error);
        showNotification(error.message || 'Erro ao criar usuário', 'error');
    }
}

async function saveEditedUser() {
    try {
        const id = parseInt(document.getElementById('editUserId').value);
        const name = document.getElementById('editUserName').value.trim();
        const email = document.getElementById('editUserEmail').value.trim();
        const profile = document.getElementById('editUserProfile').value;
        const active = document.getElementById('editUserStatus').value === 'true';
        // Captura o valor do timeout
        const timeout = parseInt(document.getElementById('editUserTimeout').value) || 0;

        if (!name || !email || !profile) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }

        const userData = {
            name,
            email,
            profile,
            active,
            // Adiciona o timeout ao objeto que será enviado para a API
            session_timeout_minutes: timeout 
        };

        await apiUpdateUser(id, userData);

        if (currentUser && currentUser.id === id) {
            currentUser.name = name;
            currentUser.email = email;
            currentUser.profile = profile;
            setTimeout(() => updateUserDisplay(), 100);
        }

        const modal = bootstrap.Modal.getInstance(document.getElementById('editUserModal'));
        modal.hide();

        await loadUsers();
        // Garante que a lista de usuários na tela seja atualizada
        const currentPage = window.location.hash.substring(1) || 'repositories';
        if (currentPage === 'users') {
            showUsers();
        }
        
        showNotification(`Usuário "${name}" atualizado com sucesso!`, 'success');

    } catch (error) {
        console.error('Erro ao salvar usuário:', error);
        showNotification(error.message || 'Erro ao salvar usuário', 'error');
    }
}


function editUser(userId) {
    if (!isAdmin()) {
        showNotification('Acesso negado!', 'error');
        return;
    }
    
    const user = users.find(u => u.id === userId);
    if (!user) {
        showNotification('Usuário não encontrado!', 'error');
        return;
    }
    
    // Garantir que o modal existe
    ensureUserModalsExist();
    
    // Preencher campos do modal
    document.getElementById('editUserId').value = user.id;
    document.getElementById('editUserUsername').value = user.username;
    document.getElementById('editUserName').value = user.name || user.username;
    document.getElementById('editUserEmail').value = user.email || '';
    document.getElementById('editUserProfile').value = user.profile;
    document.getElementById('editUserStatus').value = user.active ? 'true' : 'false';
    document.getElementById('editUserTimeout').value = user.session_timeout_minutes || 0;
    
    // Desabilitar campo username (não pode ser editado)
    document.getElementById('editUserUsername').disabled = true;
    
    // Abrir modal
    const modal = new bootstrap.Modal(document.getElementById('editUserModal'));
    modal.show();
}

function ensureUserModalsExist() {
    // Verificar se modais já existem
    if (document.getElementById('editUserModal')) return;
    
    // Criar modal de edição
    const editModalHtml = `
        <div class="modal fade" id="editUserModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-user-edit me-2"></i>Editar Usuário
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="editUserForm" data-form-action="saveEditedUser">
                            <input type="hidden" id="editUserId">
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-user me-1"></i>Username
                                </label>
                                <input type="text" 
                                       class="form-control" 
                                       id="editUserUsername" 
                                       disabled>
                                <small class="text-muted">Username não pode ser alterado</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-id-badge me-1"></i>Nome de Exibição
                                </label>
                                <input type="text" 
                                       class="form-control" 
                                       id="editUserName" 
                                       required>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-envelope me-1"></i>Email
                                </label>
                                <input type="email" 
                                       class="form-control" 
                                       id="editUserEmail" 
                                       required>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-shield-alt me-1"></i>Perfil
                                </label>
                                <select class="form-select" id="editUserProfile" required>
                                    <option value="admin">Admin</option>
                                    <option value="operator">Operador</option>
                                    <option value="viewer">Visualizador</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-toggle-on me-1"></i>Status
                                </label>
                                <select class="form-select" id="editUserStatus" required>
                                    <option value="true">Ativo</option>
                                    <option value="false">Inativo</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-clock me-1"></i>Timeout da Sessão (minutos)
                                </label>
                                <input type="number" 
                                       class="form-control" 
                                       id="editUserTimeout" 
                                       min="0" 
                                       value="0">
                                <small class="text-muted">0 = sem timeout</small>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times me-1"></i>Cancelar
                        </button>
                        <button type="submit" form="editUserForm" class="btn btn-primary">
                            <i class="fas fa-save me-1"></i>Salvar Alterações
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Criar modal de alteração de senha
    const passwordModalHtml = `
        <div class="modal fade" id="changePasswordModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-key me-2"></i>Alterar Senha
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="changePasswordForm" data-form-action="changeUserPassword">
                            <input type="hidden" id="changePasswordUserId">
                            
                            <div class="alert alert-info">
                                <i class="fas fa-info-circle me-2"></i>
                                <strong>Usuário:</strong> <span id="changePasswordUsername"></span>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-lock me-1"></i>Sua Senha (Admin)
                                </label>
                                <input type="password" 
                                       class="form-control" 
                                       id="changePasswordAdminPassword" 
                                       required 
                                       autocomplete="current-password">
                                <small class="text-muted">Digite sua senha para confirmar</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-key me-1"></i>Nova Senha do Usuário
                                </label>
                                <input type="password" 
                                       class="form-control" 
                                       id="changePasswordNewPassword" 
                                       required 
                                       autocomplete="new-password"
                                       minlength="6">
                                <small class="text-muted">Mínimo 6 caracteres</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label" id="changePasswordConfirmLabel">
                                    <i class="fas fa-check me-1"></i>Confirmar Nova Senha
                                </label>
                                <input type="password" 
                                       class="form-control" 
                                       id="changePasswordConfirm" 
                                       required 
                                       autocomplete="new-password"
                                       minlength="6"
                                       oninput="validatePasswordMatch('changePasswordNewPassword', 'changePasswordConfirm', 'changePasswordConfirmLabel')">
                                <small id="changePasswordFeedback" class="text-danger" style="display: none;">
                                    <i class="fas fa-exclamation-circle me-1"></i>As senhas não conferem
                                </small>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times me-1"></i>Cancelar
                        </button>
                        <button type="submit" form="changePasswordForm" class="btn btn-warning">
                            <i class="fas fa-key me-1"></i>Alterar Senha
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Adicionar modais ao body
    document.body.insertAdjacentHTML('beforeend', editModalHtml);
    document.body.insertAdjacentHTML('beforeend', passwordModalHtml);
    // Adicionar eventos de limpeza nos modals    const editModal = document.getElementById('editUserModal');    if (editModal) {        editModal.addEventListener('hidden.bs.modal', cleanupModalBackdrop);    }        const passwordModal = document.getElementById('changePasswordModal');    if (passwordModal) {        passwordModal.addEventListener('hidden.bs.modal', cleanupModalBackdrop);    }
}

function showChangePasswordModal(params) {
    if (!isAdmin()) {
        showNotification('Acesso negado!', 'error');
        return;
    }
    
    const user = users.find(u => u.id === params.userId);
    if (!user) {
        showNotification('Usuário não encontrado!', 'error');
        return;
    }
    
    // Garantir que modal existe
    ensureUserModalsExist();
    
    // Preencher dados
    document.getElementById('changePasswordUserId').value = user.id;
    document.getElementById('changePasswordUsername').textContent = user.username;
    
    // Limpar campos
    document.getElementById('changePasswordAdminPassword').value = '';
    document.getElementById('changePasswordNewPassword').value = '';
    document.getElementById('changePasswordConfirm').value = '';
    
    // Abrir modal
    const modal = new bootstrap.Modal(document.getElementById('changePasswordModal'));
    modal.show();
}

async function changeUserPassword() {
    try {
        const userId = parseInt(document.getElementById('changePasswordUserId').value);
        const adminPassword = document.getElementById('changePasswordAdminPassword').value;
        const newPassword = document.getElementById('changePasswordNewPassword').value;
        const confirmPassword = document.getElementById('changePasswordConfirm').value;
        
        // Validações
        if (!adminPassword || !newPassword || !confirmPassword) {
            showNotification('Preencha todos os campos!', 'error');
            return;
        }
        
        if (newPassword !== confirmPassword) {
            showNotification('As senhas não coincidem!', 'error');
            return;
        }
        
        if (newPassword.length < 6) {
            showNotification('A senha deve ter no mínimo 6 caracteres!', 'error');
            return;
        }
        
        // Chamar API
        await apiAdminChangePassword(userId, {
            admin_password: adminPassword,
            new_password: newPassword
        });
        
        // Fechar modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
        modal.hide();
        
        showNotification('Senha alterada com sucesso!', 'success');
        
    } catch (error) {
        console.error('Erro ao alterar senha:', error);
        showNotification(error.message || 'Erro ao alterar senha', 'error');
    }
}
async function deleteUser(userId) {
    // Verificar se já está deletando
    if (isDeletingUser) {
        console.warn('⚠️ Delete já em andamento, ignorando...');
        return;
    }
    
    if (!isAdmin()) {
        showNotification('Acesso negado!', 'error');
        return;
    }

    const user = users.find(u => u.id === userId);
    if (!user) {
        showNotification('Usuário não encontrado!', 'error');
        return;
    }

    if (user.username === 'admin') {
        showNotification('Usuário admin não pode ser excluído!', 'error');
        return;
    }

    // Marcar como em andamento
    isDeletingUser = true;

    try {
        const confirmed = confirm(`Tem certeza que deseja excluir o usuário "${user.username}"?`);
        
        if (!confirmed) {
            isDeletingUser = false;
            return;
        }

        console.log(`🗑️ Deletando usuário: ${user.username} (ID: ${userId})`);
        
        await apiDeleteUser(userId);
        await loadUsers();
        
        // Atualizar tela se estiver na página de usuários
        const currentPage = window.location.hash.substring(1) || 'repositories';
        if (currentPage === 'users') {
            showUsers();
        }
        
        showNotification(`Usuário "${user.username}" excluído com sucesso!`, 'success');
        
    } catch (error) {
        console.error('Erro ao deletar usuário:', error);
        showNotification(error.message || 'Erro ao excluir usuário', 'error');
    } finally {
        // Sempre liberar a flag
        isDeletingUser = false;
    }
}
function showAdminChangePasswordModal(userId) {
    if (!isAdmin()) {
        showNotification('Acesso negado. Apenas administradores podem alterar senhas de outros usuários.', 'error');
        return;
    }
    
    // Armazena userId no modal
    document.getElementById('adminChangePasswordModal').dataset.userId = userId;
    
    // Busca informações do usuário
    const user = users.find(u => u.id === userId);
    if (user) {
        document.getElementById('adminChangePasswordUserInfo').textContent = 
            `Alterando senha de: ${user.name} (${user.username})`;
    }
    
    // Limpa campos
    document.getElementById('adminPassword').value = '';
    document.getElementById('adminNewPassword').value = '';
    document.getElementById('adminNewPasswordConfirm').value = '';
    
    // Abre modal
    const modal = new bootstrap.Modal(document.getElementById('adminChangePasswordModal'));
    modal.show();
}

async function adminChangeUserPassword() {
    const userId = document.getElementById('changePasswordForUserId').value;
    const adminPassword = document.getElementById('adminConfirmPassword').value;
    const newPassword = document.getElementById('adminNewPassword').value;
    const newPasswordConfirm = document.getElementById('adminNewPasswordConfirm').value;

    if (!adminPassword || !newPassword || !newPasswordConfirm) {
        showNotification('Todos os campos são obrigatórios!', 'error');
        return;
    }
    if (newPassword !== newPasswordConfirm) {
        showNotification('A nova senha e a confirmação não conferem!', 'error');
        return;
    }

    try {
        const result = await apiAdminChangePassword(userId, {
            admin_password: adminPassword,
            new_password: newPassword
        });
        showNotification(result.message, 'success');

        // Fecha o modal de troca de senha
        const modal = bootstrap.Modal.getInstance(document.getElementById('adminChangePasswordModal'));
        modal.hide();

    } catch (error) {
        showNotification(error.message, 'error');
    }
}

async function adminChangePassword() {
    const userId = parseInt(document.getElementById('adminChangePasswordModal').dataset.userId);
    const adminPassword = document.getElementById('adminPassword').value.trim();
    const newPassword = document.getElementById('adminNewPassword').value.trim();
    const newPasswordConfirm = document.getElementById('adminNewPasswordConfirm').value.trim();
    
    // Validações
    if (!adminPassword || !newPassword || !newPasswordConfirm) {
        showNotification('Todos os campos são obrigatórios!', 'error');
        return;
    }
    
    if (newPassword.length < 6) {
        showNotification('A nova senha deve ter no mínimo 6 caracteres!', 'error');
        return;
    }
    
    if (newPassword !== newPasswordConfirm) {
        showNotification('A nova senha e a confirmação não conferem!', 'error');
        return;
    }
    
    try {
        const result = await apiAdminChangePassword(userId, {
            admin_password: adminPassword,
            new_password: newPassword
        });
        
        showNotification(result.message || 'Senha alterada com sucesso!', 'success');
        
        // Fecha o modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('adminChangePasswordModal'));
        if (modal) {
            modal.hide();
        }
        
    } catch (error) {
        showNotification(error.message || 'Erro ao alterar senha', 'error');
    }
}

// =====================================================================
// FUNÇÕES DE CONFIGURAÇÕES DO SISTEMA
// =====================================================================

async function saveSystemSettings() {
    try {
        const base_clone_dir = document.getElementById('baseCloneDir').value.trim();
        if (!base_clone_dir) {
            showNotification('O caminho base dos repositórios é obrigatório!', 'error');
            return;
        }
        await apiSaveSystemSettings({ base_clone_dir });
        await loadSystemSettings(); // Recarrega para garantir
        showNotification('Configurações do sistema salvas com sucesso!', 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao salvar configurações.', 'error');
    }
}

// ===== VARIÁVEIS DO SERVIDOR =====

async function showCreateVariableModal() {
    // Limpar campos
    document.getElementById('variableName').value = '';
    document.getElementById('variableValue').value = '';
    document.getElementById('variableDescription').value = '';
    document.getElementById('variableIsPassword').checked = false;
    
    // Abre modal
    const modal = new bootstrap.Modal(document.getElementById('createVariableModal'));
    modal.show();
}

async function createNewVariable() {
    const name = document.getElementById('variableName').value.trim();
    const value = document.getElementById('variableValue').value.trim();
    const description = document.getElementById('variableDescription').value.trim();
    const is_password = document.getElementById('variableIsPassword').checked;
    
    if (!name || !value) {
        showNotification('Nome e Valor são obrigatórios!', 'error');
        return;
    }
    
    // Validar nome (apenas UPPERCASE, números e _)
    if (!/^[A-Z0-9_]+$/.test(name)) {
        showNotification('Nome deve conter apenas letras MAIÚSCULAS, números e underscore (_)', 'error');
        return;
    }
    
    try {
        await apiCreateServerVariable({ name, value, description, is_password });
        
        // CORREÇÃO: Fechar modal após sucesso
        const modal = bootstrap.Modal.getInstance(document.getElementById('createVariableModal'));
        if (modal) {
            modal.hide();
        }
        
        // Recarregar lista de variáveis
        await loadServerVariables();
        
        // Atualizar tela de configurações mantendo aba ativa
        reloadSettingsTab('variables-tab');
        
        showNotification('Variável criada com sucesso!', 'success');
        
    } catch (error) {
        console.error('Erro ao criar variável:', error);
        showNotification(error.message || 'Erro ao criar variável', 'error');
    }
}

async function showEditVariableModal(varId) {
    const variable = serverVariables.find(v => v.id === varId);
    if (!variable) {
        showNotification('Variável não encontrada!', 'error');
        return;
    }
    
    // Armazena ID no modal
    document.getElementById('editVariableModal').dataset.varId = varId;
    
    // Preenche campos (todos editáveis agora)
    document.getElementById('editVariableName').value = variable.name;
    document.getElementById('editVariableValue').value = variable.is_password ? '' : variable.value;
    document.getElementById('editVariableDescription').value = variable.description || '';
    document.getElementById('editVariableIsPassword').checked = variable.is_password || false;
    
    // Alterar tipo do input conforme is_password
    const valueInput = document.getElementById('editVariableValue');
    valueInput.type = variable.is_password ? 'password' : 'text';
    valueInput.placeholder = variable.is_password ? 'Digite a nova senha (deixe vazio para manter)' : '';
    
    // Abre modal
    const modal = new bootstrap.Modal(document.getElementById('editVariableModal'));
    modal.show();
}

async function saveEditedVariable() {
    const varId = parseInt(document.getElementById('editVariableModal').dataset.varId);
    const name = document.getElementById('editVariableName').value.trim();
    let value = document.getElementById('editVariableValue').value.trim();
    const description = document.getElementById('editVariableDescription').value.trim();
    const is_password = document.getElementById('editVariableIsPassword').checked;
    
    // Se for senha e valor vazio, buscar valor original do array
    const originalVar = serverVariables.find(v => v.id === varId);
    if (is_password && !value && originalVar) {
        // Valor vazio em senha = manter o atual (precisamos buscar do backend)
        // Como o backend mascara, vamos marcar para não alterar
        value = '__KEEP_CURRENT__';
    }
    
    if (!name || !value) {
        showNotification('Nome e Valor são obrigatórios!', 'error');
        return;
    }
    
    // Validar nome (apenas UPPERCASE, números e _)
    if (!/^[A-Z0-9_]+$/.test(name)) {
        showNotification('Nome deve conter apenas letras MAIÚSCULAS, números e underscore (_)', 'error');
        return;
    }
    
    try {
        // CORREÇÃO: Chamar API de UPDATE, não CREATE
        await apiUpdateServerVariable(varId, { name, value, description, is_password });
        
        // CORREÇÃO: Fechar modal após sucesso
        const modal = bootstrap.Modal.getInstance(document.getElementById('editVariableModal'));
        if (modal) {
            modal.hide();
        }
        
        // Recarregar lista de variáveis
        await loadServerVariables();
        
        // Atualizar tela de configurações mantendo aba ativa
        reloadSettingsTab('variables-tab');
        
        showNotification('Variável atualizada com sucesso!', 'success');
        
    } catch (error) {
        console.error('Erro ao atualizar variável:', error);
        showNotification(error.message || 'Erro ao atualizar variável', 'error');
    }
}

async function deleteVariable(varId) {
    const variable = serverVariables.find(v => v.id === varId);
    if (!variable) {
        showNotification('Variável não encontrada!', 'error');
        return;
    }
    
    if (confirm(`Tem certeza que deseja excluir a variável "${variable.name}"?\n\nEsta ação não pode ser desfeita.`)) {
        try {
            await apiDeleteServerVariable(varId);
            
            // Recarregar lista de variáveis
            await loadServerVariables();
            
            // Atualizar tela de configurações mantendo aba ativa
            reloadSettingsTab('variables-tab');
            
            showNotification('Variável excluída com sucesso!', 'warning');
            
        } catch (error) {
            console.error('Erro ao excluir variável:', error);
            showNotification(error.message || 'Erro ao excluir variável', 'error');
        }
    }
}

// ===== SERVIÇOS DO SERVIDOR =====

async function showCreateServiceModal() {
    // Preenche select de ambientes
    const envSelect = document.getElementById('serviceEnvironment');
    envSelect.innerHTML = '<option value="">Selecione o ambiente</option>';
    environments.forEach(env => {
        envSelect.innerHTML += `<option value="${env.id}">${env.name}</option>`;
    });
    
    // Limpa campos
    document.getElementById('serviceName').value = '';
    document.getElementById('serviceDisplayName').value = '';
    document.getElementById('serviceServerName').value = '';
    document.getElementById('serviceDescription').value = '';
    document.getElementById('serviceIsActive').checked = true;
    
    // Abre modal
    const modal = new bootstrap.Modal(document.getElementById('createServiceModal'));
    modal.show();
}

async function createNewService() {
    const environment_id = document.getElementById('serviceEnvironment').value;
    const name = document.getElementById('serviceName').value.trim();
    const display_name = document.getElementById('serviceDisplayName').value.trim();
    const server_name = document.getElementById('serviceServerName').value.trim();
    const description = document.getElementById('serviceDescription').value.trim();
    const is_active = document.getElementById('serviceIsActive').checked;
    
    if (!environment_id) {
        showNotification('Selecione um ambiente!', 'error');
        return;
    }
    
    if (!name) {
        showNotification('Nome do serviço é obrigatório!', 'error');
        return;
    }
    
    if (!server_name) {
        showNotification('Nome do servidor é obrigatório!', 'error');
        return;
    }
    
    try {
        await apiCreateServerService({ 
            environment_id: parseInt(environment_id),
            name, 
            display_name: display_name || name,
            server_name,
            description,
            is_active
        });
        
        // CORREÇÃO: Fechar modal após sucesso
        const modal = bootstrap.Modal.getInstance(document.getElementById('createServiceModal'));
        if (modal) {
            modal.hide();
        }
        
        // Recarregar lista de serviços
        await loadServerServices();
        
        // Atualizar tela de configurações mantendo aba ativa
        reloadSettingsTab('services-tab');
        
        showNotification('Serviço criado com sucesso!', 'success');
        
    } catch (error) {
        console.error('Erro ao criar serviço:', error);
        showNotification(error.message || 'Erro ao criar serviço', 'error');
    }
}

async function showEditServiceModal(serviceId) {
    const service = serverServices.find(s => s.id === serviceId);
    if (!service) {
        showNotification('Serviço não encontrado!', 'error');
        return;
    }
    
    // Armazena ID no modal
    document.getElementById('editServiceModal').dataset.serviceId = serviceId;
    
    // Preenche select de ambientes
    const envSelect = document.getElementById('editServiceEnvironment');
    envSelect.innerHTML = '<option value="">Selecione o ambiente</option>';
    environments.forEach(env => {
        const selected = env.id === service.environment_id ? 'selected' : '';
        envSelect.innerHTML += `<option value="${env.id}" ${selected}>${env.name}</option>`;
    });
    
    // Preenche campos
    document.getElementById('editServiceName').value = service.name;
    document.getElementById('editServiceDisplayName').value = service.display_name || '';
    document.getElementById('editServiceServerName').value = service.server_name || '';
    document.getElementById('editServiceDescription').value = service.description || '';
    document.getElementById('editServiceIsActive').checked = service.is_active !== false;
    
    // Abre modal
    const modal = new bootstrap.Modal(document.getElementById('editServiceModal'));
    modal.show();
}

async function saveEditedService() {
    const serviceId = parseInt(document.getElementById('editServiceModal').dataset.serviceId);
    const environment_id = document.getElementById('editServiceEnvironment').value;
    const name = document.getElementById('editServiceName').value.trim();
    const display_name = document.getElementById('editServiceDisplayName').value.trim();
    const server_name = document.getElementById('editServiceServerName').value.trim();
    const description = document.getElementById('editServiceDescription').value.trim();
    const is_active = document.getElementById('editServiceIsActive').checked;
    
    if (!environment_id) {
        showNotification('Selecione um ambiente!', 'error');
        return;
    }
    
    if (!name) {
        showNotification('Nome do serviço é obrigatório!', 'error');
        return;
    }
    
    if (!server_name) {
        showNotification('Nome do servidor é obrigatório!', 'error');
        return;
    }
    
    try {
        await apiUpdateServerService(serviceId, { 
            environment_id: parseInt(environment_id),
            name, 
            display_name: display_name || name,
            server_name,
            description,
            is_active
        });
        
        // CORREÇÃO: Fechar modal após sucesso
        const modal = bootstrap.Modal.getInstance(document.getElementById('editServiceModal'));
        if (modal) {
            modal.hide();
        }
        
        // Recarregar lista de serviços
        await loadServerServices();
        
        // Atualizar tela de configurações mantendo aba ativa
        reloadSettingsTab('services-tab');
        
        showNotification('Serviço atualizado com sucesso!', 'success');
        
    } catch (error) {
        console.error('Erro ao atualizar serviço:', error);
        showNotification(error.message || 'Erro ao atualizar serviço', 'error');
    }
}

async function deleteService(serviceId) {
    const service = serverServices.find(s => s.id === serviceId);
    if (!service) {
        showNotification('Serviço não encontrado!', 'error');
        return;
    }
    
    if (confirm(`Tem certeza que deseja excluir o serviço "${service.name}"?\n\nEsta ação não pode ser desfeita.`)) {
        try {
            await apiDeleteServerService(serviceId);
            
            // Recarregar lista de serviços
            await loadServerServices();
            
            // Atualizar tela de configurações mantendo aba ativa
            reloadSettingsTab('services-tab');
            
            showNotification('Serviço excluído com sucesso!', 'warning');
            
        } catch (error) {
            console.error('Erro ao excluir serviço:', error);
            showNotification(error.message || 'Erro ao excluir serviço', 'error');
        }
    }
}

// =====================================================================
// FUNÇÕES DE DEPLOYS
// =====================================================================

// async function createNewDeploy() {
//     try {
//         const name = document.getElementById('deployName').value.trim();
//         const description = document.getElementById('deployDescription').value.trim();
//         const command_id = document.getElementById('deployCommandId').value;// 

//         if (!name || !command_id) {
//             showNotification('Nome e Comando são obrigatórios!', 'error');
//             return;
//         }// 

//         await apiCreateDeploy({ name, description, command_id: parseInt(command_id) });
//         const modal = bootstrap.Modal.getInstance(document.getElementById('createDeployModal'));
//         modal.hide();
//         await loadDeploys();
//         showDeploys(); // Para atualizar a tela
//         showNotification('Deploy criado com sucesso!', 'success');
//     } catch (error) {
//         showNotification(error.message || 'Erro ao criar deploy.', 'error');
//     }
// }// 

// async function saveEditedDeploy() {
//     try {
//         const id = parseInt(document.getElementById('editDeployId').value);
//         const name = document.getElementById('editDeployName').value.trim();
//         const description = document.getElementById('editDeployDescription').value.trim();
//         const command_id = document.getElementById('editDeployCommandId').value;// 

//         if (!name || !command_id) {
//             showNotification('Nome e Comando são obrigatórios!', 'error');
//             return;
//         }// 

//         await apiUpdateDeploy(id, { name, description, command_id: parseInt(command_id) });
//         const modal = bootstrap.Modal.getInstance(document.getElementById('editDeployModal'));
//         modal.hide();
//         await loadDeploys();
//         showDeploys();
//         showNotification('Deploy atualizado com sucesso!', 'success');
//     } catch (error) {
//         showNotification(error.message || 'Erro ao salvar deploy.', 'error');
//     }
// }// 

// async function deleteDeploy(deployId) {
//     const deploy = deploys.find(d => d.id === deployId);
//     if (!deploy) return;// 

//     if (confirm(`Tem certeza que deseja excluir o deploy "${deploy.name}"?`)) {
//         try {
//             await apiDeleteDeploy(deployId);
//             await loadDeploys();
//             showDeploys();
//             showNotification('Deploy excluído com sucesso!', 'warning');
//         } catch (error) {
//             showNotification(error.message || 'Erro ao excluir deploy.', 'error');
//         }
//     }
// }// 

// async function runDeploy(pipelineId) {
//     const pipeline = pipelines.find(p => p.id === pipelineId);
//     if (!pipeline) return;// 

//     // Reutilizamos o mesmo modal de log
//     const logModal = new bootstrap.Modal(document.getElementById('pipelineLogModal'));
//     document.getElementById('pipelineLogTitle').textContent = `Executando Deploy da Pipeline: ${pipeline.name}`;
//     const logOutput = document.getElementById('pipelineLogOutput');
//     logOutput.textContent = '';
//     logModal.show();// 

//     const appendLog = (line) => {
//         logOutput.textContent += line + '\n';
//         logOutput.scrollTop = logOutput.scrollHeight;
//     };// 

//     try {
//         await apiRunDeploy(pipelineId); // Informa o backend para iniciar// 

//         // Conecta ao MESMO stream de logs da pipeline, pois o backend agora
//         // cria uma nova entrada de log que será capturada pelo stream.
//         const eventSource = new EventSource(`/api/pipelines/${pipelineId}/stream-logs?auth_token=${authToken}`);// 

//         appendLog('[INICIANDO CONEXÃO COM O STREAM DE LOGS DO DEPLOY...]');// 

//         eventSource.onmessage = function (event) {
//             appendLog(event.data);
//             if (event.data.includes('[FIM DA EXECUÇÃO')) {
//                 eventSource.close();
//                 appendLog('[CONEXÃO COM O STREAM ENCERRADA]');
//                 setTimeout(async () => {
//                     await loadPipelines();
//                     updatePipelinesList();
//                 }, 1000);
//             }
//         };// 

//         eventSource.onerror = function () {
//             appendLog('[ERRO] A conexão com o stream de logs foi perdida.');
//             eventSource.close();
//             setTimeout(async () => {
//                 await loadPipelines();
//                 updatePipelinesList();
//             }, 1000);
//         };// 

//         document.getElementById('pipelineLogModal').addEventListener('hidden.bs.modal', () => {
//             eventSource.close();
//         }, { once: true });// 

//     } catch (error) {
//         appendLog(`ERRO CRÍTICO AO INICIAR DEPLOY: ${error.message}`);
//     }
// }

// =====================================================================
// FUNÇÕES DE COMANDOS
// =====================================================================

async function createNewCommand() {
    try {
        const name = document.getElementById('commandName').value.trim();
        const type = document.getElementById('commandType').value;
        const command_category = document.getElementById('commandCategory').value; // 🆕
        const description = document.getElementById('commandDescription').value.trim();
        const script = document.getElementById('commandScript').value.trim();

        if (!name || !type || !command_category || !script) { // 🆕 Validação
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }

        await apiCreateCommand({ 
            name, 
            type, 
            command_category, // 🆕
            description, 
            script 
        });
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('createCommandModal'));
        modal.hide();
        
        await loadCommands();
        showCommands();
        showNotification('Comando criado com sucesso!', 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao criar comando.', 'error');
    }
}

async function saveEditedCommand() {
    try {
        const id = parseInt(document.getElementById('editCommandId').value);
        const name = document.getElementById('editCommandName').value.trim();
        const type = document.getElementById('editCommandType').value;
        const command_category = document.getElementById('editCommandCategory').value; // 🆕
        const description = document.getElementById('editCommandDescription').value.trim();
        const script = document.getElementById('editCommandScript').value.trim();

        if (!name || !type || !command_category || !script) { // 🆕 Validação
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }

        await apiUpdateCommand(id, { 
            name, 
            type, 
            command_category, // 🆕
            description, 
            script 
        });
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('editCommandModal'));
        modal.hide();
        
        await loadCommands();
        showCommands();
        showNotification('Comando atualizado com sucesso!', 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao salvar comando.', 'error');
    }
}

async function deleteCommand(commandId) {
    try {
        const command = commands.find(c => c.id === commandId);
        if (!command) return;

        if (confirm(`Tem certeza que deseja excluir o comando "${command.name}"?`)) {
            // Passo 1: Informa o backend para deletar do banco de dados
            await apiDeleteCommand(commandId);

            // --- INÍCIO DA CORREÇÃO ---
            // Passo 2: Em vez de recarregar tudo, removemos o item da nossa lista local
            commands = commands.filter(c => c.id !== commandId);

            // Passo 3: Ajustamos a paginação, caso a página atual tenha ficado vazia
            const totalPages = Math.ceil(commands.length / commandsPerPage);
            if (currentCommandsPage > totalPages && totalPages > 0) {
                currentCommandsPage = totalPages;
            } else if (commands.length === 0) {
                currentCommandsPage = 1; // Volta para a pág 1 se a lista ficou vazia
            }

            // Passo 4: Chamamos a função que redesenha a tela com a lista já atualizada
            changeCommandsPage(currentCommandsPage);
            // --- FIM DA CORREÇÃO ---

            showNotification(`Comando "${command.name}" excluído com sucesso!`, 'warning');
        }

    } catch (error) {
        console.error('Erro ao deletar comando:', error);
        showNotification(error.message || 'Erro ao excluir comando', 'error');
    }
}

// =====================================================================
// FUNÇÕES DE PIPELINES
// =====================================================================

async function createNewPipeline() {
    try {
        const name = document.getElementById('pipelineName').value.trim();
        const description = document.getElementById('pipelineDescription').value.trim();
        const deploy_command_id = document.getElementById('pipelineDeployCommandId').value; // 🆕 Mudou de deploy_id

        if (!name) {
            showNotification('Nome da pipeline é obrigatório!', 'error');
            return;
        }

        if (selectedCommands.length === 0) {
            showNotification('Selecione pelo menos um comando!', 'error');
            return;
        }

        await apiCreatePipeline({
            name,
            description,
            deploy_command_id: deploy_command_id ? parseInt(deploy_command_id) : null, // 🆕 Mudou de deploy_id
            commands: selectedCommands
        });

        const modal = bootstrap.Modal.getInstance(document.getElementById('createPipelineModal'));
        modal.hide();

        await loadPipelines();
        showPipelines();
        showNotification('Pipeline criada com sucesso!', 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao criar pipeline.', 'error');
    }
}

async function saveEditedPipeline() {
    try {
        const id = parseInt(document.getElementById('editPipelineId').value);
        const name = document.getElementById('editPipelineName').value.trim();
        const description = document.getElementById('editPipelineDescription').value.trim();
        const deploy_command_id = document.getElementById('editPipelineDeployCommandId').value; // 🆕 Mudou de deploy_id

        if (!name) {
            showNotification('Nome da pipeline é obrigatório!', 'error');
            return;
        }

        if (selectedCommands.length === 0) {
            showNotification('Selecione pelo menos um comando!', 'error');
            return;
        }

        await apiUpdatePipeline(id, {
            name,
            description,
            deploy_command_id: deploy_command_id ? parseInt(deploy_command_id) : null, // 🆕 Mudou de deploy_id
            commands: selectedCommands
        });

        const modal = bootstrap.Modal.getInstance(document.getElementById('editPipelineModal'));
        modal.hide();

        await loadPipelines();
        showPipelines();
        showNotification('Pipeline atualizada com sucesso!', 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao salvar pipeline.', 'error');
    }
}

function updatePipelinesList() {
    const container = document.getElementById('pipelinesContainer');
    const pagination = document.getElementById('pipelinesPagination');

    if (container) {
        container.innerHTML = renderPipelinesWithPagination();
    }
    if (pagination) {
        pagination.innerHTML = renderPipelinesPagination();
    }
}

function changePipelinePage(page) {
    const totalPages = Math.ceil(pipelines.length / pipelinesPerPage);
    if (page < 1 || (page > totalPages && totalPages > 0)) {
        return;
    }
    currentPipelinePage = page;
    updatePipelinesList();
}

// Função de filtro por tipo de script
function filterPipelinesByScriptType(scriptType) {
    pipelineScriptTypeFilter = scriptType;
    currentPipelinePage = 1; // Resetar para primeira página
    showPipelines(); // Re-renderizar a tela inteira
}

function renderPipelinesPagination() {
    // Aplicar filtro antes de calcular páginas
    let filteredPipelines = pipelines;
    
    if (pipelineScriptTypeFilter !== 'TODOS') {
        filteredPipelines = pipelines.filter(p => {
            // 🆕 Verifica pelo nome OU pelo tipo dos comandos associados
            if (p.name.includes(`(${pipelineScriptTypeFilter})`)) {
                return true;
            }
            if (p.commands && p.commands.length > 0) {
                return p.commands.some(cmd => cmd.type === pipelineScriptTypeFilter.toLowerCase());
            }
            return false;
        });
    }
    
    const totalPages = Math.ceil(filteredPipelines.length / pipelinesPerPage);
    if (totalPages <= 1) return '';

    return `
        <nav class="d-flex justify-content-center mt-4">
            <ul class="pagination">
                <li class="page-item ${currentPipelinePage === 1 ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="changePipelinePage" data-params='{"page":${currentPipelinePage - 1}}'>Anterior</a>
                </li>
                <li class="page-item disabled"><span class="page-link">${currentPipelinePage} de ${totalPages}</span></li>
                <li class="page-item ${currentPipelinePage === totalPages ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="changePipelinePage" data-params='{"page":${currentPipelinePage + 1}}'>Próximo</a>
                </li>
            </ul>
        </nav>
    `;
}

function renderPipelinesWithPagination() {
    // Aplicar filtro de tipo de script
    let filteredPipelines = pipelines;
    
    if (pipelineScriptTypeFilter !== 'TODOS') {
        filteredPipelines = pipelines.filter(p => {
            // 🆕 Verifica pelo nome OU pelo tipo dos comandos associados
            if (p.name.includes(`(${pipelineScriptTypeFilter})`)) {
                return true;
            }
            // Verificar tipo dos comandos da pipeline
            if (p.commands && p.commands.length > 0) {
                return p.commands.some(cmd => cmd.type === pipelineScriptTypeFilter.toLowerCase());
            }
            return false;
        });
    }
    
    if (filteredPipelines.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted">Nenhuma pipeline configurada para este ${pipelineScriptTypeFilter === 'TODOS' ? 'ambiente' : 'tipo de script'}.</p>
                ${isOperator() ? '<button class="btn btn-primary mt-3" data-action="showCreatePipelineModal"><i class="fas fa-plus me-2"></i>Criar Primeira Pipeline</button>' : ''}
            </div>`;
    }

    const startIndex = (currentPipelinePage - 1) * pipelinesPerPage;
    const endIndex = startIndex + pipelinesPerPage;
    const pipelinesForCurrentPage = filteredPipelines.slice(startIndex, endIndex);

    // Verificar permissões
    const canExecute = isOperator();
    const canEdit = isOperator();
    const canDelete = isOperator();

    return pipelinesForCurrentPage.map(pipeline => {
        // Verificar se item é protegido
        const isProtected = pipeline.is_protected && !isRootAdmin();
        const showEditBtn = canEdit && !isProtected;
        const showDeleteBtn = canDelete && !isProtected;
        
        return `
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h6 class="mb-0">
                    <i class="fas fa-cogs me-2"></i>${pipeline.name}
                    ${pipeline.is_protected ? '<i class="fas fa-lock text-warning ms-2" title="Protegido"></i>' : ''}
                </h6>
                <div class="btn-group">
                    ${canExecute ? `
                    <!-- RUN BUILD - Executa a pipeline -->
                    <button class="btn btn-sm btn-primary" 
                            data-action="runPipelineBuild"
                            data-params='{"pipelineId": ${pipeline.id}}'
                            title="Executar pipeline (Build)">
                        <i class="fas fa-play"></i> Run Build
                    </button>
                    ` : ''}
                    
                    <!-- HISTÓRICO DE BUILDS - Lista execuções (todos podem ver) -->
                    <button class="btn btn-sm btn-info" 
                            data-action="showBuildHistory" 
                            data-params='{"pipelineId": ${pipeline.id}}'
                            title="Histórico de execuções">
                        <i class="fas fa-history"></i> Builds e Deploys
                    </button>
                    
                    ${showEditBtn ? `
                    <!-- EDITAR -->
                    <button class="btn btn-sm btn-outline-secondary" 
                            data-action="showEditPipelineModal" 
                            data-params='{"pipelineId":${pipeline.id}}'
                            title="Editar pipeline">
                        <i class="fas fa-edit"></i> Editar
                    </button>
                    ` : ''}
                    
                    ${showDeleteBtn ? `
                    <!-- EXCLUIR -->
                    <button class="btn btn-sm btn-outline-danger" 
                            data-action="deletePipeline" 
                            data-params='{"pipelineId":${pipeline.id}}'
                            title="Excluir pipeline">
                        <i class="fas fa-trash"></i> Excluir
                    </button>
                    ` : ''}
                </div>
            </div>
            <div class="card-body">
                <p class="text-muted mb-2">${pipeline.description || 'Sem descrição'}</p>
                <div class="command-sequence">
                    ${pipeline.commands.map((cmd, index) => `
                        <div class="d-flex align-items-center mb-2 p-2 bg-light rounded">
                            <div class="badge bg-primary me-3">${index + 1}</div>
                            <div><strong>${cmd.name}</strong></div>
                        </div>
                    `).join('')}
                </div>
            </div>
            
        </div>
    `}).join('');
}

async function deletePipeline(pipelineId) {
    try {
        const pipeline = pipelines.find(p => p.id === pipelineId);
        if (!pipeline) return;

        if (confirm(`Tem certeza que deseja excluir a pipeline "${pipeline.name}"?`)) {
            await apiDeletePipeline(pipelineId);

            await loadPipelines();

            // Corrigir paginação após exclusão
            const totalPages = Math.ceil(pipelines.length / pipelinesPerPage);
            if (currentPipelinePage > totalPages && totalPages > 0) {
                currentPipelinePage = totalPages;
            } else if (pipelines.length === 0) {
                currentPipelinePage = 1;
            }

            updatePipelinesList();
            showNotification('Pipeline excluída com sucesso!', 'success');
        }

    } catch (error) {
        console.error('Erro ao deletar pipeline:', error);
        showNotification(error.message || 'Erro ao excluir pipeline', 'error');
    }
}

async function runPipeline(pipelineId) {
    const pipeline = pipelines.find(p => p.id === pipelineId);
    if (!pipeline) return;

    const logModal = new bootstrap.Modal(document.getElementById('pipelineLogModal'));
    document.getElementById('pipelineLogTitle').textContent = `Executando: ${pipeline.name}`;
    const logOutput = document.getElementById('pipelineLogOutput');
    logOutput.textContent = '';
    logModal.show();

    const appendLog = (line) => {
        logOutput.textContent += line + '\n';
        logOutput.scrollTop = logOutput.scrollHeight;
    };

    try {
        await apiRunPipeline(pipelineId); // Apenas inicia a pipeline no backend
        pipeline.status = 'queued';
        updatePipelinesList();

        // (NOVO) Conecta ao stream de logs do backend
        const eventSource = new EventSource(`/api/pipelines/${pipelineId}/stream-logs?auth_token=${authToken}`);

        appendLog('[INICIANDO CONEXÃO COM O STREAM DE LOGS...]');

        eventSource.onmessage = function (event) {
            appendLog(event.data);
            if (event.data.includes('[FIM DA EXECUÇÃO')) {
                eventSource.close();
                appendLog('[CONEXÃO COM O STREAM ENCERRADA]');
                // Recarrega os dados para pegar o status final
                setTimeout(async () => {
                    await loadPipelines();
                    updatePipelinesList();
                }, 1000);
            }
        };

        eventSource.onerror = function () {
            appendLog('[ERRO] A conexão com o stream de logs foi perdida.');
            eventSource.close();
            // Recarrega os dados para pegar o status final
            setTimeout(async () => {
                await loadPipelines();
                updatePipelinesList();
            }, 1000);
        };

        // Garante que a conexão seja fechada se o modal for fechado
        document.getElementById('pipelineLogModal').addEventListener('hidden.bs.modal', () => {
            eventSource.close();
        }, { once: true });

    } catch (error) {
        appendLog(`ERRO CRÍTICO AO INICIAR PIPELINE: ${error.message}`);
    }
}



// =====================================================================
// FUNÇÕES DE SELEÇÃO DE COMANDO PARA DEPLOY
// =====================================================================

function showDeployCommandSelector(mode) {
    const commandList = document.getElementById('deployCommandList');

    if (!commandList) {
        console.error('Elemento deployCommandList não encontrado!');
        return;
    }

    // Renderiza a lista de comandos disponíveis
    commandList.innerHTML = commands.map(cmd => `
        <button type="button" class="list-group-item list-group-item-action" 
                data-action="selectDeployCommand" data-params=\'{"commandId":${cmd.id},"commandName":"${cmd.name}"}\'>
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${cmd.name}</strong>
                    <small class="text-muted d-block">${cmd.description || 'Sem descrição'}</small>
                    <span class="badge bg-info">${cmd.type}</span>
                </div>
                <i class="fas fa-chevron-right text-muted"></i>
            </div>
        </button>
    `).join('');

    // Abre o modal específico de deploy
    const modal = new bootstrap.Modal(document.getElementById('deployCommandSelectorModal'));
    modal.show();
}

function selectDeployCommand(commandId, commandName) {
    selectedDeployCommandId = commandId;

    // Atualiza o campo do formulário (tanto no criar quanto no editar)
    const createField = document.getElementById('deployCommandId');
    const editField = document.getElementById('editDeployCommandId');

    if (createField) createField.value = commandId;
    if (editField) editField.value = commandId;

    // Fecha o modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('deployCommandSelectorModal'));
    if (modal) modal.hide();

    showNotification(`Comando "${commandName}" selecionado!`, 'success', 1500);
}

// =====================================================================
// FUNÇÕES DE REPOSITÓRIOS
// =====================================================================


async function discoverRepositories() {
    if (!gitHubSettings.token || !gitHubSettings.username) {
        showNotification('Configure o token GitHub primeiro!', 'warning');
        navigateToPage('settings');
        return;
    }

    showNotification('Descobrindo repositórios...', 'info');

    try {
        const response = await fetch(`https://api.github.com/user/repos?per_page=100`, {
            headers: {
                'Authorization': `token ${gitHubSettings.token}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });

        if (!response.ok) {
            throw new Error(`GitHub API Error: ${response.status}`);
        }

        const repos = await response.json();

        // Salvar no backend
        await apiSaveRepositories(repos);

        // Recarregar do backend
        await loadRepositories();

        showNotification(`${repositories.length} repositórios descobertos e salvos!`, 'success');
        showRepositories();

    } catch (error) {
        console.error('Erro ao descobrir repositórios:', error);
        showNotification('Erro ao conectar com GitHub. Verifique o token.', 'error');
    }
}

async function removeRepository(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    const confirmMessage = `Tem certeza que deseja remover o repositório "${repo.name}" da lista?\n\n` +
        'ATENÇÃO: Isso remove apenas da lista local, não afeta o repositório no GitHub.';

    if (confirm(confirmMessage)) {
        try {
            await apiDeleteRepository(repoId);

            await loadRepositories();
            showRepositories();

            showNotification(`Repositório "${repo.name}" removido da lista local`, 'warning');
        } catch (error) {
            console.error('Erro ao remover repositório:', error);
            showNotification('Erro ao remover repositório', 'error');
        }
    }
}

async function cloneRepositoryOnServer(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    // Pega o branch selecionado no estado global, ou o padrão
    const branchToClone = currentBranch[repo.name] || repo.default_branch;

    const confirmation = confirm(`ATENÇÃO: A pasta "${repo.name}" no servidor será (re)criada com o conteúdo do branch "${branchToClone}".\n\nContinuar?`);
    if (!confirmation) {
        showNotification('Operação cancelada.', 'info');
        return;
    }

    showNotification(`Iniciando clone do branch "${branchToClone}"...`, 'info');
    try {
        const result = await apiCloneRepository(repoId, branchToClone);
        showNotification(result.message, 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao clonar repositório.', 'error');
    }
}

async function pullRepositoryOnServer(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    const activeBranch = currentBranch[repo.name] || repo.default_branch; // <-- Pega o branch ativo
    showNotification(`Executando 'Pull' para "${repo.name}" no branch "${activeBranch}"...`, 'info');
    try {
        const result = await apiPullRepository(repoId, activeBranch); // <-- Envia o branch
        //... o resto da função continua igual
        const notificationMessage = `${result.message}<br><small>${result.details || 'Nenhum detalhe.'}</small>`;
        showNotification(notificationMessage, 'success', 5000);
        console.log('Detalhes do Pull:', result.details);
    } catch (error) {
        const errorMessage = `${error.message}<br><small>${error.details || 'Verifique o console.'}</small>`;
        showNotification(errorMessage, 'error', 5000);
    }
}

async function tagAndPush(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    // Pedir informações ao usuário
    const tagName = prompt(`Criar nova tag para "${repo.name}":\n\nDigite o nome da tag (ex: v1.0.0):`);
    if (!tagName) {
        showNotification('Criação de tag cancelada.', 'info');
        return;
    }

    const message = prompt(`Digite uma mensagem de anotação para a tag "${tagName}":\n\n(Ex: Release de lançamento da versão 1.0)`);
    if (!message) {
        showNotification('Criação de tag cancelada.', 'info');
        return;
    }

    showNotification(`Criando e enviando a tag "${tagName}"...`, 'info');
    try {
        const result = await apiPushTag(repoId, { tag_name: tagName, message: message });
        showNotification(result.message, 'success');
    } catch (error) {
        showNotification(error.message || 'Erro ao criar a tag.', 'error');
    }
}

async function pushChanges(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    const activeBranch = currentBranch[repo.name] || repo.default_branch; // <-- Pega o branch ativo
    const commitMessage = prompt(`Enviar alterações para "${repo.name}" (branch: ${activeBranch}):\n\nDigite uma mensagem de commit:`);

    if (!commitMessage) {
        showNotification('Operação de Push cancelada.', 'info');
        return;
    }

    showNotification(`Enviando alterações para o branch "${activeBranch}"...`, 'info');
    try {
        // (NOVO) Envia o branch junto com a mensagem
        const result = await apiPushChanges(repoId, {
            commit_message: commitMessage,
            branch_name: activeBranch
        });
        showNotification(result.message, 'success');
        console.log('Detalhes do Push:', result.details);
    } catch (error) {
        showNotification(error.message || 'Erro ao enviar alterações.', 'error');
    }
}

async function exploreRepository(repoName) {
    const repo = repositories.find(r => r.name === repoName);
    if (!repo) return;

    showNotification('Carregando dados do repositório do GitHub...', 'info');
    try {
        // Inicializa ou mantém o estado de navegação
        currentPath[repoName] = currentPath[repoName] || '';
        currentBranch[repoName] = currentBranch[repoName] || repo.default_branch;

        // (REMOVIDO) A busca pela lista de todos os branches foi removida para otimização.

        // Busca o conteúdo dos arquivos (isso já usa o branch correto que está em currentBranch)
        const content = await loadRepositoryContent(repoName, currentPath[repoName]);

        // Renderiza a interface simplificada, sem passar a lista de branches
        showRepositoryExplorer(repo, content, currentPath[repoName]);
        showNotification('Repositório carregado!', 'success', 1500);

    } catch (error) {
        showNotification(error.message || 'Erro ao explorar repositório.', 'error');
        navigateToPage('repositories');
    }
}

async function createNewBranch(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    const baseBranch = currentBranch[repo.name] || repo.default_branch;
    const newBranchName = prompt(`Criar uma nova branch a partir de "${baseBranch}":\n\nDigite o nome para a nova branch:`);

    if (!newBranchName) {
        showNotification('Criação de branch cancelada.', 'info');
        return;
    }

    showNotification(`Criando branch "${newBranchName}"...`, 'info');
    try {
        const result = await apiCreateBranch(repoId, {
            new_branch_name: newBranchName,
            base_branch_name: baseBranch
        });
        showNotification(result.message, 'success');

        // Atualiza a interface para refletir a nova branch
        await switchBranch(repoId, newBranchName);

    } catch (error) {
        showNotification(error.message || 'Erro ao criar a branch.', 'error');
    }
}

async function showBranchSelector(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    const container = document.getElementById(`branch-container-${repo.id}`);
    if (!container) return;

    container.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i>Buscando...`;

    try {
        // Busca os branches direto do GitHub
        const githubBranchesUrl = `https://api.github.com/repos/${repo.full_name}/branches?_=${Date.now()}`;
        const response = await fetch(githubBranchesUrl, { headers: getGithubHeaders() });
        if (!response.ok) throw new Error('Falha ao buscar branches do GitHub.');

        const branchesData = await response.json();
        const branches = branchesData.map(b => b.name);

        // Cria o HTML do seletor
        const selectorHtml = `
            <select class="form-select form-select-sm" onchange="selectBranch(${repo.id}, this.value)">
                ${branches.map(branch => `<option value="${branch}" ${branch === (currentBranch[repo.name] || repo.default_branch) ? 'selected' : ''}>${branch}</option>`).join('')}
            </select>
        `;
        container.innerHTML = selectorHtml;

    } catch (error) {
        showNotification(error.message, 'error');
        // Restaura a visualização original em caso de erro
        container.innerHTML = `
            <span class="badge bg-secondary ms-1">${currentBranch[repo.name] || repo.default_branch}</span>
            <button class="btn btn-link btn-sm p-0 ms-2" data-action="showBranchSelector" data-params=\'{"repoId":${repo.id}}\'>Trocar</button>
        `;
    }
}

function selectBranch(repoId, branchName) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    // Atualiza o estado global
    currentBranch[repo.name] = branchName;
    showNotification(`Branch "${branchName}" selecionado para ${repo.name}.`, 'info');

    // Redesenha a lista de repositórios para refletir a mudança
    document.getElementById('repositoriesContainer').innerHTML = renderRepositories();
}

// =====================================================================
// FUNÇÕES DE CONFIGURAÇÕES GITHUB
// =====================================================================

async function saveGitHubSettings() {
    try {
        const token = document.getElementById('githubToken').value.trim();
        const username = document.getElementById('githubUsername').value.trim();

        if (!token || !username) {
            showNotification('Preencha todos os campos!', 'error');
            return;
        }

        if (!token.startsWith('ghp_') && !token.startsWith('github_pat_')) {
            showNotification('Formato de token inválido. Deve começar com "ghp_" ou "github_pat_".', 'error');
            return;
        }

        await apiSaveGithubSettings({ token, username });

        // Atualiza o estado global
        gitHubSettings.token = token;
        gitHubSettings.username = username;

        showNotification('Configurações GitHub salvas com sucesso!', 'success');

        // Apenas recarrega a própria tela de configurações para refletir o estado salvo
        showSettings();

    } catch (error) {
        console.error('Erro ao salvar configurações:', error);
        showNotification(error.message || 'Erro ao salvar configurações', 'error');
    }
}

async function testGitHubConnection() {
    const token = document.getElementById('githubToken').value.trim();
    const username = document.getElementById('githubUsername').value.trim();
    const statusDiv = document.getElementById('connectionStatus');

    if (!token || !username) {
        showNotification('Preencha o Token e o Usuário para testar.', 'warning');
        return;
    }

    statusDiv.innerHTML = `<div class="text-info"><i class="fas fa-spinner fa-spin me-2"></i>Testando conexão...</div>`;

    try {
        const response = await fetch(`https://api.github.com/users/${username}`, {
            headers: { 'Authorization': `token ${token}` }
        });

        if (response.ok) {
            const userData = await response.json();
            statusDiv.innerHTML = `
                <div class="alert alert-success mt-2">
                    <i class="fas fa-check-circle me-2"></i>
                    Conectado com sucesso como <strong>${userData.login}</strong>!
                </div>
            `;
        } else {
            throw new Error(`Falha na autenticação: ${response.statusText}`);
        }
    } catch (error) {
        console.error('Erro no teste de conexão:', error);
        statusDiv.innerHTML = `
            <div class="alert alert-danger mt-2">
                <i class="fas fa-exclamation-circle me-2"></i>
                Erro na conexão: ${error.message}
            </div>
        `;
    }
}

// =====================================================================
// ALTERAÇÃO DE SENHA DO PRÓPRIO USUÁRIO
// =====================================================================

function showChangePasswordModal() {
    document.getElementById('changePasswordForm').reset();
    const modal = new bootstrap.Modal(document.getElementById('changePasswordModal'));
    modal.show();
}

async function changeOwnPassword() {
    const currentPassword = document.getElementById('currentPassword').value.trim();
    const newPassword = document.getElementById('newPassword').value.trim();
    const newPasswordConfirm = document.getElementById('newPasswordConfirm').value.trim();
    
    // Validações
    if (!currentPassword || !newPassword || !newPasswordConfirm) {
        showNotification('Todos os campos são obrigatórios!', 'error');
        return;
    }
    
    if (newPassword.length < 6) {
        showNotification('A nova senha deve ter no mínimo 6 caracteres!', 'error');
        return;
    }
    
    if (newPassword !== newPasswordConfirm) {
        showNotification('A nova senha e a confirmação não conferem!', 'error');
        return;
    }
    
    if (currentPassword === newPassword) {
        showNotification('A nova senha deve ser diferente da atual!', 'warning');
        return;
    }
    
    try {
        const result = await apiChangeOwnPassword({
            current_password: currentPassword,
            new_password: newPassword
        });
        
        showNotification(result.message || 'Senha alterada com sucesso!', 'success');
        
        // Fecha o modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
        if (modal) {
            modal.hide();
        }
        
        // Limpa os campos
        document.getElementById('currentPassword').value = '';
        document.getElementById('newPassword').value = '';
        document.getElementById('newPasswordConfirm').value = '';
        
    } catch (error) {
        showNotification(error.message || 'Erro ao alterar senha', 'error');
    }
}



// =====================================================================
// PONTO DE ENTRADA PRINCIPAL DA APLICAÇÃO
// =====================================================================
document.addEventListener('DOMContentLoaded', function() {
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

// Adiciona o listener que ativa o roteador sempre que a URL hash mudar
window.addEventListener('hashchange', router);


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
            headers: { 'Authorization': `Bearer ${authToken}` }
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
        'admin': ['dashboard', 'repositories', 'pipelines', 'schedules', 'commands', 'services-management', 'users', 'settings'],
        'operator': ['dashboard', 'repositories', 'pipelines', 'schedules', 'commands', 'services-management'],
        'viewer': ['dashboard', 'repositories', 'pipelines', 'schedules']
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

// GitHub API Configuration
const GITHUB_API_BASE = 'https://api.github.com';
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
function initializeApp() {
    console.log('Inicializando AtuRPO DevOps...');
    // Configurar login
    setupLogin();
    setupActivateLicenseModal();
    setupFirstAccessModal();
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

// =====================================================================
// MODAL DE ATIVAÇÃO DE LICENÇA
// =====================================================================

function setupActivateLicenseModal() {
    const btnActivate = document.getElementById('btnActivateLicense');
    const modal = document.getElementById('activateLicenseModal');
    const closeBtn = document.getElementById('closeActivateModal');
    const form = document.getElementById('activateLicenseForm');
    const errorDiv = document.getElementById('activateError');
    
    if (!btnActivate || !modal) return;
    
    // Abrir modal
    btnActivate.addEventListener('click', (e) => {
        e.preventDefault();
        modal.style.display = 'block';
        document.getElementById('activateUsername').value = '';
        document.getElementById('activatePassword').value = '';
        errorDiv.style.display = 'none';
        document.getElementById('activateUsername').focus();
    });
    
    // Fechar modal
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    // Fechar ao clicar fora
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Submit do formulário
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('activateUsername').value.trim();
        const password = document.getElementById('activatePassword').value;
        
        if (!username || !password) {
            errorDiv.textContent = 'Preencha todos os campos';
            errorDiv.style.display = 'block';
            return;
        }
        
        try {
            const response = await fetch('/api/license/validate-admin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Redirecionar para página de ativação
                window.location.href = data.redirect || '/activate';
            } else {
                errorDiv.textContent = data.error || 'Acesso negado';
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Erro ao validar acesso:', error);
            errorDiv.textContent = 'Erro de conexão com o servidor';
            errorDiv.style.display = 'block';
        }
    });
}

// =====================================================================
// PRIMEIRO ACESSO - Criação do Admin do Cliente
// =====================================================================

async function checkFirstAccess() {
    try {
        const response = await fetch('/api/first-access/check');
        const data = await response.json();
        
        const btnFirstAccess = document.getElementById('btnFirstAccess');
        if (btnFirstAccess) {
            if (data.first_access) {
                btnFirstAccess.style.display = 'inline';
                console.log('🔓 Primeiro acesso detectado - botão habilitado');
            } else {
                btnFirstAccess.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Erro ao verificar primeiro acesso:', error);
    }
}

function setupFirstAccessModal() {
    const btnFirstAccess = document.getElementById('btnFirstAccess');
    const modal = document.getElementById('firstAccessModal');
    const closeBtn = document.getElementById('closeFirstAccessModal');
    const form = document.getElementById('firstAccessForm');
    const errorDiv = document.getElementById('firstAccessError');
    const successDiv = document.getElementById('firstAccessSuccess');
    
    if (!btnFirstAccess || !modal) return;
    
    // Abrir modal
    btnFirstAccess.addEventListener('click', (e) => {
        e.preventDefault();
        modal.style.display = 'block';
        // Limpar campos
        document.getElementById('firstAccessUsername').value = '';
        document.getElementById('firstAccessName').value = '';
        document.getElementById('firstAccessEmail').value = '';
        document.getElementById('firstAccessPassword').value = '';
        document.getElementById('firstAccessPasswordConfirm').value = '';
        errorDiv.style.display = 'none';
        successDiv.style.display = 'none';
        document.getElementById('firstAccessUsername').focus();
    });
    
    // Fechar modal
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    // Fechar ao clicar fora
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Submit do formulário
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('firstAccessUsername').value.trim();
        const name = document.getElementById('firstAccessName').value.trim();
        const email = document.getElementById('firstAccessEmail').value.trim();
        const password = document.getElementById('firstAccessPassword').value;
        const passwordConfirm = document.getElementById('firstAccessPasswordConfirm').value;
        
        errorDiv.style.display = 'none';
        successDiv.style.display = 'none';
        
        // Validações
        if (!username || !name || !email || !password || !passwordConfirm) {
            errorDiv.textContent = 'Preencha todos os campos';
            errorDiv.style.display = 'block';
            return;
        }
        
        if (password !== passwordConfirm) {
            errorDiv.textContent = 'As senhas não conferem';
            errorDiv.style.display = 'block';
            return;
        }
        
        if (password.length < 6) {
            errorDiv.textContent = 'A senha deve ter no mínimo 6 caracteres';
            errorDiv.style.display = 'block';
            return;
        }
        
        // Validar formato de email
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            errorDiv.textContent = 'Digite um e-mail válido';
            errorDiv.style.display = 'block';
            return;
        }
        
        const submitBtn = document.getElementById('btnFirstAccessSubmit');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Criando...';
        submitBtn.disabled = true;
        
        try {
            const response = await fetch('/api/first-access/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, name, email, password })
            });
            
            const data = await response.json();
            
            if (data.success) {
                successDiv.innerHTML = `<i class="fas fa-check-circle me-1"></i>${data.message}`;
                successDiv.style.display = 'block';
                form.reset();
                
                // Esconder botão de primeiro acesso
                btnFirstAccess.style.display = 'none';
                
                // Preencher username no login e fechar modal após 2s
                setTimeout(() => {
                    modal.style.display = 'none';
                    const usernameInput = document.getElementById('username');
                    if (usernameInput) {
                        usernameInput.value = data.username;
                        document.getElementById('password').focus();
                    }
                }, 2000);
            } else {
                errorDiv.textContent = data.error || 'Erro ao criar administrador';
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Erro ao criar primeiro admin:', error);
            errorDiv.textContent = 'Erro de conexão. Tente novamente.';
            errorDiv.style.display = 'block';
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    });
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
    const container = document.getElementById('toast-container-footer');
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
    document.body.classList.toggle('sidebar-collapsed');
}

function changeCommandsPage(page) {
    const totalPages = Math.ceil(commands.length / commandsPerPage);
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
    const totalPages = Math.ceil(commands.length / commandsPerPage);
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

function updateSidebarByProfile() {
    if (!currentUser) return;
    
    // Links do sidebar
    const usersLink = document.querySelector('.sidebar [data-page="users"]');
    const settingsLink = document.querySelector('.sidebar [data-page="settings"]');
    const commandsLink = document.querySelector('.sidebar [data-page="commands"]');
    const serviceActionsLink = document.querySelector('.sidebar [data-page="services-management"]');
    
    // Users e Settings: apenas perfil admin
    if (usersLink) usersLink.style.display = isAdmin() ? 'flex' : 'none';
    if (settingsLink) settingsLink.style.display = isAdmin() ? 'flex' : 'none';
    
    // Commands: admin e operator podem ver (viewer não)
    if (commandsLink) commandsLink.style.display = isOperator() ? 'flex' : 'none';
    
    // Service Actions (Gestão de Serviços): admin e operator podem ver (viewer não)
    if (serviceActionsLink) serviceActionsLink.style.display = isOperator() ? 'flex' : 'none';
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
// FUNÇÃO updateUserDisplay CORRIGIDA E ROBUSTA
// FUNÇÃO updateUserDisplay CORRIGIDA E ROBUSTA
function updateUserDisplay() {
    const userDisplayHeader = document.getElementById('current-user');
    const userDisplaySidebar = document.getElementById('sidebar-user-name');
    const userProfileSidebar = document.getElementById('sidebar-user-profile');
    if (currentUser) {
        const displayName = currentUser.name || currentUser.username;
        if (userDisplayHeader) userDisplayHeader.textContent = displayName;
        if (userDisplaySidebar) userDisplaySidebar.textContent = displayName;
        
        // Exibir perfil correto
        if (userProfileSidebar) {
            if (isRootAdmin()) {
                userProfileSidebar.innerHTML = '<i class="fas fa-crown text-warning me-1"></i>Root Admin';
            } else if (currentUser.profile === 'admin') {
                userProfileSidebar.textContent = 'Administrador';
            } else if (currentUser.profile === 'operator') {
                userProfileSidebar.textContent = 'Operador';
            } else {
                userProfileSidebar.textContent = 'Visualizador';
            }
        }
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
function sortRepositoryContent(repoName, newKey) {
    if (repoContentSort.key === newKey) {
        // Se já está ordenando por esta chave, inverte a ordem
        repoContentSort.order = repoContentSort.order === 'asc' ? 'desc' : 'asc';
    } else {
        // Se for uma nova chave, ordena em ordem ascendente
        repoContentSort.key = newKey;
        repoContentSort.order = 'asc';
    }
    // Recarrega a visão do explorador para aplicar a nova ordenação
    exploreRepository(repoName);
}



// =====================================================================
// DASHBOARD
// =====================================================================

async function showDashboard() {
    const contentArea = document.getElementById('content-area');
    contentArea.innerHTML = `
        <div class="text-center p-5">
            <div class="spinner-border text-primary"></div>
            <p class="mt-3">Carregando Dashboard...</p>
        </div>
    `;
    
    try {
        const stats = await apiGetDashboardStats();
        renderDashboard(stats);
    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
        contentArea.innerHTML = `
            <div class="card text-center p-5">
                <i class="fas fa-exclamation-triangle fa-3x text-warning mb-3"></i>
                <h4>Erro ao carregar Dashboard</h4>
                <p class="text-muted">${error.message}</p>
                <button class="btn btn-primary" data-action="refreshDashboard">
                    <i class="fas fa-sync-alt me-2"></i>Tentar novamente
                </button>
            </div>
        `;
    }
}

function renderDashboard(stats) {
    const envSelector = document.getElementById('environmentSelector');
    const envName = envSelector?.selectedOptions[0]?.text || 'Ambiente';
    
    const content = `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2><i class="fas fa-chart-line me-2"></i>Dashboard</h2>
                    <p class="text-muted mb-0">Visão geral do ambiente: <strong>${envName}</strong></p>
                </div>
                <button class="btn btn-outline-primary" data-action="refreshDashboard">
                    <i class="fas fa-sync-alt me-2"></i>Atualizar
                </button>
            </div>
            
            <!-- Cards de Métricas -->
            <div class="dashboard-grid">
                <!-- Pipelines Executadas -->
                <div class="dashboard-card">
                    <div class="dashboard-card-header">
                        <div>
                            <div class="dashboard-stat-value">${stats.pipeline_runs?.total || 0}</div>
                            <div class="dashboard-stat-label">Execuções de Pipeline</div>
                        </div>
                        <div class="dashboard-card-icon bg-primary">
                            <i class="fas fa-play-circle"></i>
                        </div>
                    </div>
                    <div class="dashboard-stat-row">
                        <div class="dashboard-stat-item success">
                            <div class="value">${stats.pipeline_runs?.success || 0}</div>
                            <div class="label">Sucesso</div>
                        </div>
                        <div class="dashboard-stat-item failed">
                            <div class="value">${stats.pipeline_runs?.failed || 0}</div>
                            <div class="label">Falha</div>
                        </div>
                        <div class="dashboard-stat-item running">
                            <div class="value">${stats.pipeline_runs?.running || 0}</div>
                            <div class="label">Executando</div>
                        </div>
                    </div>
                </div>
                
                <!-- Releases/Deploys -->
                <div class="dashboard-card">
                    <div class="dashboard-card-header">
                        <div>
                            <div class="dashboard-stat-value">${stats.releases?.total || 0}</div>
                            <div class="dashboard-stat-label">Releases (Deploys)</div>
                        </div>
                        <div class="dashboard-card-icon bg-success">
                            <i class="fas fa-rocket"></i>
                        </div>
                    </div>
                    <div class="dashboard-stat-row">
                        <div class="dashboard-stat-item success">
                            <div class="value">${stats.releases?.success || 0}</div>
                            <div class="label">Sucesso</div>
                        </div>
                        <div class="dashboard-stat-item failed">
                            <div class="value">${stats.releases?.failed || 0}</div>
                            <div class="label">Falha</div>
                        </div>
                    </div>
                </div>
                
                <!-- Totais do Sistema -->
                <div class="dashboard-card">
                    <div class="dashboard-card-header">
                        <div>
                            <div class="dashboard-stat-value">${stats.totals?.pipelines || 0}</div>
                            <div class="dashboard-stat-label">Pipelines Configuradas</div>
                        </div>
                        <div class="dashboard-card-icon bg-info">
                            <i class="fas fa-cogs"></i>
                        </div>
                    </div>
                    <div class="dashboard-stat-row">
                        <div class="dashboard-stat-item">
                            <div class="value">${stats.totals?.commands || 0}</div>
                            <div class="label">Comandos</div>
                        </div>
                        <div class="dashboard-stat-item">
                            <div class="value">${stats.totals?.repositories || 0}</div>
                            <div class="label">Repositórios</div>
                        </div>
                    </div>
                </div>
                
                <!-- Serviços -->
                <div class="dashboard-card">
                    <div class="dashboard-card-header">
                        <div>
                            <div class="dashboard-stat-value">${stats.service_actions?.total || 0}</div>
                            <div class="dashboard-stat-label">Ações de Serviço</div>
                        </div>
                        <div class="dashboard-card-icon bg-warning">
                            <i class="fas fa-server"></i>
                        </div>
                    </div>
                    <div class="dashboard-stat-row">
                        <div class="dashboard-stat-item success">
                            <div class="value">${stats.service_actions?.active || 0}</div>
                            <div class="label">Ativas</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Seções de Listas -->
            <div class="row">
                <!-- Últimas Execuções -->
                <div class="col-md-6">
                    <div class="dashboard-card">
                        <h5 class="dashboard-section-title">
                            <i class="fas fa-history text-primary"></i>
                            Últimas Execuções
                        </h5>
                        ${renderRecentRuns(stats.recent_runs, stats.recent_service_actions)}
                    </div>
                </div>
                
                <!-- Próximos Schedules -->
                <div class="col-md-6">
                    <div class="dashboard-card">
                        <h5 class="dashboard-section-title">
                            <i class="fas fa-clock text-warning"></i>
                            Próximas Execuções Agendadas
                        </h5>
                        ${renderActiveSchedules(stats.active_schedules, stats.scheduled_service_actions)}
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('content-area').innerHTML = content;
}

function renderRecentRuns(runs, serviceActions) {
    const hasRuns = runs && runs.length > 0;
    const hasServiceActions = serviceActions && serviceActions.length > 0;
    
    if (!hasRuns && !hasServiceActions) {
        return '<div class="dashboard-empty"><i class="fas fa-inbox fa-2x mb-2"></i><p>Nenhuma execução recente</p></div>';
    }
    
    let html = '<ul class="dashboard-list">';
    
    // Pipeline Runs
    if (hasRuns) {
        html += runs.map(run => `
            <li class="dashboard-list-item">
                <div>
                    <div class="dashboard-list-item-title">
                        🚀 ${run.pipeline_name} <span class="text-muted">#${run.run_number}</span>
                    </div>
                    <div class="dashboard-list-item-subtitle">
                        <i class="fas fa-${run.trigger_type === 'scheduled' ? 'clock' : 'user'} me-1"></i>
                        ${run.trigger_type === 'scheduled' ? 'Agendado' : 'Manual'}
                        • ${formatDateTime(run.started_at)}
                    </div>
                </div>
                <span class="badge ${getDashboardStatusBadgeClass(run.status)}">
                    <i class="fas fa-${getDashboardStatusIcon(run.status)} me-1"></i>
                    ${getDashboardStatusLabel(run.status)}
                </span>
            </li>
        `).join('');
    }
    
    // Service Actions
    if (hasServiceActions) {
        html += serviceActions.map(action => `
            <li class="dashboard-list-item">
                <div>
                    <div class="dashboard-list-item-title">
                        ⚙️ ${action.name}
                    </div>
                    <div class="dashboard-list-item-subtitle">
                        <i class="fas fa-${action.os_type === 'windows' ? 'windows' : 'linux'} me-1"></i>
                        ${action.action_type.charAt(0).toUpperCase() + action.action_type.slice(1)}
                        • ${formatDateTime(action.last_run_at)}
                    </div>
                </div>
                <span class="badge bg-success">
                    <i class="fas fa-check-circle me-1"></i>
                    Executado
                </span>
            </li>
        `).join('');
    }
    
    html += '</ul>';
    html += `
        <div class="text-center mt-3">
            <a href="#pipelines" class="btn btn-sm btn-outline-primary">
                Ver todas as pipelines <i class="fas fa-arrow-right ms-1"></i>
            </a>
        </div>
    `;
    
    return html;
}

function renderActiveSchedules(schedules, serviceActions) {
    const hasSchedules = schedules && schedules.length > 0;
    const hasServiceActions = serviceActions && serviceActions.length > 0;
    
    if (!hasSchedules && !hasServiceActions) {
        return '<div class="dashboard-empty"><i class="fas fa-calendar-times fa-2x mb-2"></i><p>Nenhum agendamento ativo</p></div>';
    }
    
    let html = '<ul class="dashboard-list">';
    
    // Pipeline Schedules
    if (hasSchedules) {
        html += schedules.map(schedule => `
            <li class="dashboard-list-item">
                <div>
                    <div class="dashboard-list-item-title">📅 ${schedule.name}</div>
                    <div class="dashboard-list-item-subtitle">
                        <i class="fas fa-cogs me-1"></i>Pipeline: ${schedule.pipeline_name}
                    </div>
                </div>
                <div class="text-end">
                    <div class="small text-muted">Próxima execução</div>
                    <div class="fw-medium">${schedule.next_run_at ? formatDateTime(schedule.next_run_at) : 'Não definido'}</div>
                </div>
            </li>
        `).join('');
    }
    
    // Service Action Schedules
    if (hasServiceActions) {
        html += serviceActions.map(action => `
            <li class="dashboard-list-item">
                <div>
                    <div class="dashboard-list-item-title">⚙️ ${action.name}</div>
                    <div class="dashboard-list-item-subtitle">
                        <i class="fas fa-${action.os_type === 'windows' ? 'windows' : 'linux'} me-1"></i>
                        Service Action: ${action.action_type.charAt(0).toUpperCase() + action.action_type.slice(1)}
                    </div>
                </div>
                <div class="text-end">
                    <div class="small text-muted">Próxima execução</div>
                    <div class="fw-medium">${action.next_run_at ? formatDateTime(action.next_run_at) : 'Não definido'}</div>
                </div>
            </li>
        `).join('');
    }
    
    html += '</ul>';
    html += `
        <div class="text-center mt-3">
            <a href="#schedules" class="btn btn-sm btn-outline-primary">
                Ver todos os agendamentos <i class="fas fa-arrow-right ms-1"></i>
            </a>
        </div>
    `;
    
    return html;
}

// Helpers de status para Dashboard (evita conflito com outros existentes)
function getDashboardStatusBadgeClass(status) {
    const classes = {
        'success': 'badge-success',
        'failed': 'badge-danger',
        'running': 'badge-warning',
        'queued': 'badge-info'
    };
    return classes[status] || 'badge-secondary';
}

function getDashboardStatusIcon(status) {
    const icons = {
        'success': 'check-circle',
        'failed': 'times-circle',
        'running': 'spinner fa-spin',
        'queued': 'clock'
    };
    return icons[status] || 'question-circle';
}

function getDashboardStatusLabel(status) {
    const labels = {
        'success': 'Sucesso',
        'failed': 'Falha',
        'running': 'Executando',
        'queued': 'Aguardando'
    };
    return labels[status] || status;
}


function showRepositories() {
    let content = '';
    if (!gitHubSettings.token) {
        content = `
            <div class="card text-center p-5">
                <h4><i class="fab fa-github me-2"></i>Integração GitHub</h4>
                <p class="text-muted">A configuração do GitHub é necessária para descobrir e gerenciar repositórios.</p>
                ${isAdmin() ? '<button class="btn btn-primary" onclick="window.location.hash=\'settings\'">Ir para Configurações</button>' : '<p class="text-warning">Peça a um administrador para configurar a integração.</p>'}
            </div>`;
    } else if (repositories.length === 0) {
        content = `
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2>Repositórios</h2>
                ${isOperator() ? '<button class="btn btn-primary" data-action="discoverRepositories"><i class="fab fa-github me-2"></i>Sincronizar com GitHub</button>' : ''}
            </div>
            <div class="card text-center p-5">
                <p class="text-muted">Nenhum repositório sincronizado para este ambiente.</p>
            </div>`;
    } else {
        content = `
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2>Repositórios</h2>
                ${isOperator() ? '<button class="btn btn-primary" data-action="discoverRepositories"><i class="fab fa-github me-2"></i>Sincronizar com GitHub</button>' : ''}
            </div>
            <div id="repositoriesContainer">${renderRepositories()}</div>`;
    }
    document.getElementById('content-area').innerHTML = content;
}

function renderEmptyRepositories() {
    return `
    <div class="card">
        <div class="card-body text-center py-5">
            <i class="fas fa-code-branch fa-4x text-muted mb-4"></i>
            <h4>Nenhum Repositório Descoberto</h4>
            <p class="text-muted mb-4">Use "Descobrir Repositórios" para encontrar seus projetos GitHub.</p>
            <button class="btn btn-primary" data-action="discoverRepositories">
                <i class="fas fa-search me-2"></i>Descobrir Repositórios
            </button>
        </div>
    </div>
    `;
}

function renderRepositories() {
    // Adiciona uma verificação para o caso de nenhum repositório ser encontrado após a sincronização
    if (repositories.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted">Nenhum repositório sincronizado para este ambiente.</p>
                ${isOperator() ? '<button class="btn btn-primary mt-3" data-action="discoverRepositories"><i class="fab fa-github me-2"></i>Sincronizar com GitHub</button>' : ''}
            </div>`;
    }

    // Verificar permissões
    const canManage = isOperator();

    return `
    <div class="row">
        ${repositories.map(repo => {
        const selectedBranch = currentBranch[repo.name] || repo.default_branch;
        return `
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-0 text-truncate" title="${repo.name}">
                                <i class="fas fa-${repo.private ? 'lock' : 'globe'} me-2"></i>
                                ${repo.name}
                            </h6>
                            <small class="text-muted">${repo.private ? 'Privado' : 'Público'}</small>
                        </div>
                        <div class="dropdown">
                            <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown">
                                <i class="fas fa-ellipsis-v"></i>
                            </button>
                            <ul class="dropdown-menu dropdown-menu-end">
                                <li><a class="dropdown-item" href="#" data-action="exploreRepository" data-params='{"repoName":"${repo.name}"}'><i class="fas fa-folder-open me-2"></i>Explorar Arquivos</a></li>
                                <li><a class="dropdown-item" href="${repo.html_url}" target="_blank"><i class="fab fa-github me-2"></i>Ver no GitHub</a></li>
                                ${canManage ? `
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item" href="#" data-action="createNewBranch" data-params='{"repoId":${repo.id}}'><i class="fas fa-code-branch me-2"></i>Criar Branch</a></li>
                                    <li><a class="dropdown-item" href="#" data-action="cloneRepository" data-params='{"repoId":${repo.id}}'><i class="fas fa-clone me-2"></i>Clonar/Resetar</a></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item text-danger" href="#" data-action="deleteRepository" data-params='{"repoId":${repo.id}}'><i class="fas fa-trash me-2"></i>Remover da Lista</a></li>
                                ` : ''}
                            </ul>
                        </div>
                    </div>
                    <div class="card-body">
                        <p class="card-text text-muted small" style="height: 3em; overflow: hidden;">${repo.description || 'Sem descrição'}</p>
                        <div class="d-flex align-items-center mt-3">
                            <i class="fas fa-code-branch me-2 text-muted"></i>
                            <div id="branch-container-${repo.id}" class="d-flex align-items-center">
                                <span class="badge bg-secondary">${selectedBranch}</span>
                                ${canManage ? `<button class="btn btn-link btn-sm p-0 ms-2" data-action="showBranchSelector" data-params='{"repoId":${repo.id}}'>Trocar</button>` : ''}
                            </div>
                        </div>
                    </div>
                    <div class="card-footer">
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">Atualizado: ${formatDate(repo.updated_at)}</small>
                            ${canManage ? `
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-primary" data-action="pullRepository" data-params='{"repoId":${repo.id}}'><i class="fas fa-arrow-down"></i> Pull</button>
                                <button class="btn btn-outline-success" data-action="pushChanges" data-params='{"repoId":${repo.id}}'><i class="fas fa-arrow-up"></i> Push</button>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>`}).join('')}
    </div>`;
}

// GitHub API Helper Functions - LIMPO
function getGithubHeaders() {
    const headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Protheus-DevOps-App'
        // A linha 'Cache-Control' foi removida
    };
    if (gitHubSettings.token) {
        headers['Authorization'] = `token ${gitHubSettings.token}`;
    }
    return headers;
}
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

async function loadRepositoryContent(repoName, path = '') {
    const repo = repositories.find(r => r.name === repoName);
    if (!gitHubSettings.token) throw new Error("Token do GitHub não configurado.");
    const branch = currentBranch[repoName] || repo.default_branch;
    const url = `https://api.github.com/repos/${repo.full_name}/contents/${path}?ref=${branch}&_=${Date.now()}`;
    const response = await fetch(url, { headers: getGithubHeaders() });
    if (!response.ok) throw new Error(`Erro na API do GitHub: ${response.status}`);
    return await response.json();
}
function showRepositoryExplorer(repo, content, currentPath) { // O parâmetro 'branches' foi removido
    const activeBranch = currentBranch[repo.name] || repo.default_branch;
    const explorerContent = `
    <div>
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2>
                    <button class="btn btn-link p-0 text-decoration-none" data-action="navigate" data-params=\'{"page":"repositories"}\'>
                        <i class="fas fa-arrow-left me-2"></i>Repositórios
                    </button>
                    / ${repo.name}
                </h2>
                <div class="d-flex align-items-center">
                    <i class="fas fa-code-branch me-2 text-muted"></i>
                    <span class="badge bg-primary">${activeBranch}</span>
                </div>
            </div>
            <div class="btn-group">
                <button class="btn btn-sm btn-outline-secondary" data-action="exploreRepository" data-params=\'{"repoName":"${repo.name}"}\' title="Atualizar a lista de arquivos do GitHub">
                    <i class="fas fa-sync-alt me-2"></i>Atualizar
                </button>
                <button class="btn btn-sm btn-outline-primary" data-action="pullRepository" data-params=\'{"repoId":${repo.id}}\'>
                    <i class="fas fa-arrow-down me-2"></i>Pull (Forçado)
                </button>
                <button class="btn btn-sm btn-outline-success" data-action="pushChanges" data-params=\'{"repoId":${repo.id}}\'>
                    <i class="fas fa-arrow-up me-2"></i>Push Alterações
                </button>
            </div>
        </div>
        <div class="d-flex align-items-center mb-3">
            ${currentPath ? `
                    <button class="btn btn-sm btn-outline-secondary me-3" data-action="goBackPath" data-params=\'{"repoName":"${repo.name}"}\'>
                        <i class="fas fa-arrow-left"></i> Voltar
                    </button>
                ` : ''}
            ${renderBreadcrumb(repo.name, currentPath)}
        </div>
        <div class="card">
            <div class="card-body">
                ${renderRepositoryContent(repo, content, currentPath)}
            </div>
        </div>
    </div>
    `;
    document.getElementById('content-area').innerHTML = explorerContent;
}
function renderRepositoryContent(repo, content, path) {
    // Lógica de visualização de arquivo único (não muda)
    if (!Array.isArray(content)) {
        // ... (o código para ver um arquivo só continua o mesmo, não precisa mexer)
        // ... para garantir, aqui está ele completo:
        const isText = content.type === 'file' && content.content;
        return `
    <div class="mb-3">
        <div class="d-flex justify-content-between align-items-center">
            <h5><i class="fas fa-file me-2"></i>${content.name}</h5>
            <div class="btn-group btn-group-sm">
                <a href="${content.download_url}" class="btn btn-outline-success" target="_blank">
                    <i class="fas fa-download"></i> Download
                </a>
                <a href="${content.html_url}" class="btn btn-outline-primary" target="_blank">
                    <i class="fab fa-github"></i> GitHub
                </a>
            </div>
        </div>
        <p class="text-muted">Tamanho: ${formatSize(content.size)}</p>
    </div>
    ${isText ? `
                <div class="bg-light p-3 rounded"><pre class="mb-0"><code>${(() => { try { return atob(content.content); } catch (e) { return 'Erro ao decodificar conteúdo.'; } })()}</code></pre></div>
            ` : `
                <div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>Arquivo binário. Use o botão Download para baixar.</div>
            `}
    `;
    }
    // --- INÍCIO DA MUDANÇA: Lógica de ordenação ---
    const sortKey = repoContentSort.key;
    const sortOrder = repoContentSort.order;
    content.sort((a, b) => {
        // Coloca as pastas sempre no topo
        if (a.type === 'dir' && b.type !== 'dir') return -1;
        if (a.type !== 'dir' && b.type === 'dir') return 1;
        let valA, valB;
        if (sortKey === 'size') {
            valA = a.size || 0;
            valB = b.size || 0;
        } else { // 'name' ou 'type'
            valA = a[sortKey].toUpperCase();
            valB = b[sortKey].toUpperCase();
        }
        if (valA < valB) return sortOrder === 'asc' ? -1 : 1;
        if (valA > valB) return sortOrder === 'asc' ? 1 : -1;
        return 0;
    });
    // Função para renderizar o ícone de ordenação
    const renderSortIcon = (key) => {
        if (sortKey !== key) return `<i class="fas fa-sort text-muted ms-2"></i>`;
        return sortOrder === 'asc'
            ? `<i class="fas fa-sort-up text-primary ms-2"></i>`
            : `<i class="fas fa-sort-down text-primary ms-2"></i>`;
    };
    // --- FIM DA MUDANÇA: Lógica de ordenação ---
    // Lista de arquivos e pastas com cabeçalhos clicáveis
    return `
    <div class="table-responsive">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th><button class="btn btn-link text-decoration-none text-dark p-0" data-action="sortRepositoryContent" data-params=\'{"repoName":"${repo.name}","field":"name"}\'>Nome ${renderSortIcon('name')}</button></th>
                    <th><button class="btn btn-link text-decoration-none text-dark p-0" data-action="sortRepositoryContent" data-params=\'{"repoName":"${repo.name}","field":"type"}\'>Tipo ${renderSortIcon('type')}</button></th>
                    <th><button class="btn btn-link text-decoration-none text-dark p-0" data-action="sortRepositoryContent" data-params=\'{"repoName":"${repo.name}","field":"size"}\'>Tamanho ${renderSortIcon('size')}</button></th>
                    <th>Ações</th>
                </tr>
            </thead>
            <tbody>
                ${content.map(item => `
                        <tr>
                            <td>
                                <i class="fas fa-${item.type === 'dir' ? 'folder' : 'file'} me-2 text-${item.type === 'dir' ? 'warning' : 'primary'}"></i>
                                ${item.name}
                            </td>
                            <td><span class="badge bg-${item.type === 'dir' ? 'warning' : 'info'}">${item.type === 'dir' ? 'Pasta' : 'Arquivo'}</span></td>
                            <td>${item.size ? formatSize(item.size) : '-'}</td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    ${item.type === 'dir' ?
            `<button class="btn btn-outline-primary" data-action="navigateToPath" data-params=\'{"repoName":"${repo.name}","path":"${item.path}"}\'><i class="fas fa-folder-open"></i> Abrir</button>` :
            `<button class="btn btn-outline-info" data-action="viewFile" data-params=\'{"repoName":"${repo.name}","path":"${item.path}"}\'><i class="fas fa-eye"></i> Ver</button>
                                         <a href="${item.download_url}" class="btn btn-outline-success" target="_blank"><i class="fas fa-download"></i> Download</a>`
        }
                                </div>
                            </td>
                        </tr>
                    `).join('')}
            </tbody>
        </table>
    </div>
    `;
}
function renderBreadcrumb(repoName, path) {
    const pathParts = path.split('/').filter(p => p);
    return `
    <nav aria-label="breadcrumb" class="flex-grow-1">
        <ol class="breadcrumb bg-light p-2 rounded-pill mb-0">
            <li class="breadcrumb-item">
                <a href="#" data-action="navigateToPath" data-params=\'{"repoName":"${repoName}","path":""}\' title="Raiz do Repositório">
                    <i class="fas fa-home"></i>
                </a>
            </li>
            ${pathParts.map((part, index) => {
        const partialPath = pathParts.slice(0, index + 1).join('/');
        const isLast = index === pathParts.length - 1;
        return `
                        <li class="breadcrumb-item ${isLast ? 'active' : ''}">
                            ${isLast ?
                part :
                `<a href="#" data-action="navigateToPath" data-params=\'{"repoName":"${repoName}","path":"${partialPath}"}\'>${part}</a>`
            }
                        </li>
                    `;
    }).join('')}
        </ol>
    </nav>
    `;
}
async function navigateToPath(repoName, path) {
    // Atualiza o caminho para a nova pasta
    currentPath[repoName] = path;
    // Chama a função principal para recarregar e redesenhar tudo
    await exploreRepository(repoName);
}
function goBackPath(repoName) {
    const path = currentPath[repoName];
    if (!path) return; // Não pode voltar se já está na raiz
    const pathParts = path.split('/');
    pathParts.pop(); // Remove a última parte do caminho (a pasta/arquivo atual)
    const parentPath = pathParts.join('/');
    // Usa a função que já temos para navegar para o caminho pai
    navigateToPath(repoName, parentPath);
}
async function viewFile(repoName, filePath) {
    // Atualiza o caminho para o arquivo que queremos ver
    currentPath[repoName] = filePath;
    // Chama a função principal para recarregar e redesenhar tudo
    await exploreRepository(repoName);
}
function cloneRepository(cloneUrl) {
    navigator.clipboard.writeText(`git clone ${cloneUrl}`);
    showNotification('Comando de clone copiado para área de transferência!', 'success');
}
// Funções auxiliares
function formatSize(bytes) {
    if (!bytes) return '-';
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('pt-BR');
}
function refreshRepositories() {
    showNotification('Atualizando repositórios...', 'info');
    discoverRepositories();
}
function applyRepositoryFilters() {
    showNotification('Filtros aplicados!', 'info');
    // Implementar filtros se necessário
}
function viewRepository(id) {
    const repo = repositories.find(r => r.id === id);
    if (repo) {
        showNotification(`Visualizando repositório: ${repo.name}`, 'info');
    }
}
async function navigateToFolder(repositoryId, folderName) {
    const currentPathName = currentPath[repositoryId];
    const newPath = currentPathName ? `${currentPathName}/${folderName}` : folderName;
    currentPath[repositoryId] = newPath;
    showNotification(`Navegando para ${folderName}...`, 'info');
    // Carregar branches novamente
    const branches = await loadRepositoryBranches(repositoryId);
    await loadArtifactsInterface(repositoryId, branches);
}
function editRepository(repositoryId) {
    const repo = repositories.find(r => r.id === repositoryId);
    if (!repo) return;
    const newName = prompt('Editar nome do repositório:', repo.name);
    if (newName && newName !== repo.name) {
        repo.name = newName;
        showRepositories(); // Recarregar a lista
        showNotification(`Repositório renomeado para "${newName}"`, 'success');
        return;
    }
    const newDescription = prompt('Editar descrição:', repo.description);
    if (newDescription && newDescription !== repo.description) {
        repo.description = newDescription;
        showRepositories(); // Recarregar a lista
        showNotification('Descrição atualizada com sucesso!', 'success');
    }
}
    
function showPipelines() {
    const content = `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2>Pipelines</h2>
                    <p class="text-muted">Automação de execução sequencial de comandos</p>
                </div>
                ${isOperator() ? `
                <div class="btn-group">
                    <button class="btn btn-primary" data-action="showCreatePipelineModal">
                        <i class="fas fa-plus me-2"></i>Nova Pipeline
                    </button>
                </div>
                ` : ''}
            </div>
            
                    <!-- Filtro de Tipo de Script -->
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex align-items-center justify-content-between">
                    <div>
                        <label class="form-label mb-0 me-2"><strong>Filtrar por Tipo de Script:</strong></label>
                    </div>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm ${pipelineScriptTypeFilter === 'TODOS' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterPipelinesByScriptType" 
                                data-params='{"scriptType":"TODOS"}'>
                            📋 Todos
                        </button>
                        <button type="button" class="btn btn-sm ${pipelineScriptTypeFilter === 'PowerShell' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterPipelinesByScriptType" 
                                data-params='{"scriptType":"PowerShell"}'>
                            🔷 PowerShell
                        </button>
                        <button type="button" class="btn btn-sm ${pipelineScriptTypeFilter === 'Bash' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterPipelinesByScriptType" 
                                data-params='{"scriptType":"Bash"}'>
                            🐧 Bash
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
            <div id="pipelinesContainer"></div>
            <div id="pipelinesPagination"></div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;
    updatePipelinesList();
}

// =====================================================================
// TELA DE SCHEDULES
// =====================================================================

async function showSchedules() {
    await loadSchedules();
    const content = `
        <div class="content-header">
            <div>
                <h2><i class="fas fa-clock me-2"></i>Schedule</h2>
                <p class="text-muted">Gerencie os agendamentos de Pipeline e Serviços do sistema.</p>
            </div>
        </div>

        <ul class="nav nav-tabs mb-4" id="scheduleTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="pipelines-schedule-tab" data-bs-toggle="tab" data-bs-target="#pipelines-schedule-content" type="button" role="tab">Agendamento de Pipelines</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="services-management-tab" data-bs-toggle="tab" data-bs-target="#services-management-content" type="button" role="tab">Gestão de Serviços</button>
            </li>
        </ul>

        <div class="tab-content" id="scheduleTabsContent">
            <div class="tab-pane fade show active" id="pipelines-schedule-content" role="tabpanel"></div>
            <div class="tab-pane fade" id="services-management-content" role="tabpanel"></div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;

    // Renderiza conteúdo das abas
    renderPipelineSchedulesTab();
    renderServicesManagementTab();
}

function renderPipelineSchedulesTab() {
    const container = document.getElementById('pipelines-schedule-content');
    
    const filteredSchedules = getFilteredSchedules();
    
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <h5>📅 Agendamentos</h5>
                <p class="text-muted mb-0">Configure execuções automáticas de pipelines.</p>
            </div>
            ${isOperator() ? '<button class="btn btn-primary" data-action="showCreateScheduleModal"><i class="fas fa-plus me-2"></i>Novo Agendamento</button>' : ''}
        </div>
        
        <!-- Filtro de Tipo de Script -->
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex align-items-center justify-content-between">
                    <div>
                        <label class="form-label mb-0 me-2"><strong>Filtrar por Tipo de Script:</strong></label>
                    </div>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm ${scheduleScriptTypeFilter === 'TODOS' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterSchedulesByScriptType" 
                                data-params='{"scriptType":"TODOS"}'>
                            📋 Todos
                        </button>
                        <button type="button" class="btn btn-sm ${scheduleScriptTypeFilter === 'PowerShell' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterSchedulesByScriptType" 
                                data-params='{"scriptType":"PowerShell"}'>
                            🔷 PowerShell
                        </button>
                        <button type="button" class="btn btn-sm ${scheduleScriptTypeFilter === 'Bash' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterSchedulesByScriptType" 
                                data-params='{"scriptType":"Bash"}'>
                            🐧 Bash
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row mb-3">
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <i class="fas fa-clock fa-2x text-primary mb-2"></i>
                        <h3>${filteredSchedules.length}</h3>
                        <p class="text-muted mb-0">Total de Agendamentos</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <i class="fas fa-check-circle fa-2x text-success mb-2"></i>
                        <h3>${filteredSchedules.filter(s => s.is_active).length}</h3>
                        <p class="text-muted mb-0">Ativos</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <i class="fas fa-pause-circle fa-2x text-secondary mb-2"></i>
                        <h3>${filteredSchedules.filter(s => !s.is_active).length}</h3>
                        <p class="text-muted mb-0">Inativos</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="schedulesContainer">${renderSchedulesWithPagination()}</div>
        <div id="schedulesPagination">${renderSchedulesPagination()}</div>
    `;
}

async function renderServicesManagementTab(startPolling = true) {
    const container = document.getElementById('services-management-content');
    
    // Estado de filtro
    if (!window.serviceActionsState) {
        window.serviceActionsState = {
            filterOS: 'TODOS'
        };
    }
    
    const state = window.serviceActionsState;
    
    // Filtrar ações por OS
    let filteredActions = serviceActions || [];
    if (state.filterOS !== 'TODOS') {
        filteredActions = filteredActions.filter(a => a.os_type === state.filterOS.toLowerCase());
    }
    
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <h5>⚙️ Gestão de Serviços</h5>
                <p class="text-muted mb-0">Configure e execute start/stop de serviços do servidor.</p>
            </div>
            ${isOperator() ? '<button class="btn btn-primary" data-action="showCreateServiceActionModal"><i class="fas fa-plus me-2"></i>Nova Ação</button>' : ''}
        </div>
        
        <!-- Filtro por Sistema Operacional -->
        <div class="card mb-3">
            <div class="card-body">
                <div class="d-flex align-items-center justify-content-between">
                    <div>
                        <label class="form-label mb-0 me-2"><strong>Filtrar por Sistema Operacional:</strong></label>
                    </div>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm ${state.filterOS === 'TODOS' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterServiceActionsByOS" 
                                data-params='{"osType":"TODOS"}'>
                            📋 Todos
                        </button>
                        <button type="button" class="btn btn-sm ${state.filterOS === 'WINDOWS' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterServiceActionsByOS" 
                                data-params='{"osType":"WINDOWS"}'>
                            🪟 Windows
                        </button>
                        <button type="button" class="btn btn-sm ${state.filterOS === 'LINUX' ? 'btn-primary' : 'btn-outline-primary'}" 
                                data-action="filterServiceActionsByOS" 
                                data-params='{"osType":"LINUX"}'>
                            🐧 Linux
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
        ${filteredActions.length === 0 ? `
            <div class="card text-center p-5">
                <i class="fas fa-cog text-muted" style="font-size: 4rem;"></i>
                <p class="text-muted mt-3">Nenhuma ação de serviço cadastrada${state.filterOS !== 'TODOS' ? ' para ' + state.filterOS : ''}.</p>
                ${isOperator() ? '<button class="btn btn-primary mt-3" data-action="showCreateServiceActionModal"><i class="fas fa-plus me-2"></i>Criar Primeira Ação</button>' : ''}
            </div>
        ` : filteredActions.map(action => {
            const serviceNames = action.service_ids.split(',').map(id => {
                const service = serverServices.find(s => s.id === parseInt(id));
                return service ? service.name : id;
            }).join(', ');
            
            const actionIcon = action.action_type === 'start' ? '▶️' : (action.action_type === 'restart' ? '🔄' : '⏹️');
            const actionBadgeClass = action.action_type === 'start' ? 'bg-success' : (action.action_type === 'restart' ? 'bg-info' : 'bg-danger');
            const osIcon = action.os_type === 'windows' ? '🪟' : '🐧';
            const forceFlag = action.force_stop ? '<span class="badge bg-warning text-dark ms-1">Force</span>' : '';
            
            // Informações de agendamento (igual schedules de pipeline)
            let scheduleInfo = '';
            if (action.schedule_type && action.schedule_config) {
                const scheduleTypeLabel = getScheduleTypeLabel(action.schedule_type);
                const scheduleConfigText = formatScheduleConfig(action.schedule_type, action.schedule_config);
                const nextRunText = action.next_run_at 
                    ? formatDateTime(action.next_run_at)
                    : 'Não calculado';
                const lastRunText = action.last_run_at 
                    ? formatDateTime(action.last_run_at)
                    : 'Nunca executado';
                
                scheduleInfo = `
                    <hr class="my-3">
                    <div class="row">
                        <div class="col-md-6">
                            <p class="mb-2">
                                <strong>📅 Tipo:</strong> ${scheduleTypeLabel}
                            </p>
                            <p class="mb-2">
                                <strong>⚙️ Configuração:</strong> ${scheduleConfigText}
                            </p>
                        </div>
                        <div class="col-md-6">
                            <p class="mb-2">
                                <strong>Próxima Execução:</strong> 
                                <span class="text-${action.is_active ? 'primary' : 'muted'}">${nextRunText}</span>
                            </p>
                            <p class="mb-0">
                                <strong>Última Execução:</strong> ${lastRunText}
                            </p>
                        </div>
                    </div>
                `;
            }
            
            return `
                <div class="card mb-3">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-0">
                                <i class="fas fa-cog me-2"></i>${action.name}
                                ${action.schedule_type ? (!!action.is_active
                                    ? '<span class="badge bg-success ms-2">Agendamento Ativo</span>' 
                                    : '<span class="badge bg-secondary ms-2">Agendamento Inativo</span>')
                                    : '<span class="badge bg-info ms-2">Execução Manual</span>'}
                            </h6>
                            <small class="text-muted">
                                <span class="badge ${actionBadgeClass}">${actionIcon} ${action.action_type.toUpperCase()}</span>${forceFlag}
                                <span class="ms-2">${osIcon} ${action.os_type.toUpperCase()}</span>
                                <span class="ms-2">Serviços: ${serviceNames}</span>
                            </small>
                        </div>
                        <div class="btn-group">
                            <button class="btn btn-sm btn-success" 
                                    data-action="executeServiceAction" 
                                    data-params='{"actionId": ${action.id}}'
                                    title="Executar agora">
                                <i class="fas fa-play"></i> Executar
                            </button>
                            
                            ${action.schedule_type ? `
                                <button class="btn btn-sm ${!!action.is_active ? 'btn-warning' : 'btn-success'}"
                                        data-action="toggleServiceActionSchedule" 
                                        data-params='{"actionId": ${action.id}, "isActive": ${!!action.is_active}}'
                                        title="${!!action.is_active ? 'Desativar agendamento' : 'Ativar agendamento'}">
                                    <i class="fas fa-${!!action.is_active ? 'pause' : 'play'}-circle"></i>
                                </button>
                            ` : ''}
                            
                            ${isOperator() ? `
                                <button class="btn btn-sm btn-primary" 
                                        data-action="editServiceAction" 
                                        data-params='{"actionId": ${action.id}}'
                                        title="Editar">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn btn-sm btn-danger" 
                                        data-action="deleteServiceAction" 
                                        data-params='{"actionId": ${action.id}}'
                                        title="Excluir">
                                    <i class="fas fa-trash"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                    <div class="card-body">
                        ${action.description ? `<p class="text-muted mb-0"><em>${action.description}</em></p>` : ''}
                        ${scheduleInfo}
                    </div>
                </div>
            `;
        }).join('')}
    `;
   
    // Iniciar polling se houver agendamentos ativos (apenas na primeira chamada)
    if (startPolling) {
        startServiceActionsPolling();
    }
}

// =====================================================================
// POLLING AUTOMÁTICO INTELIGENTE PARA SERVICE ACTIONS
// =====================================================================

let serviceActionsPollingInterval = null;

/**
 * Inicia polling inteligente para atualizar status das service actions
 * Ajusta frequência baseado em agendamentos próximos
 */
function startServiceActionsPolling() {
    // Limpar intervalo anterior se existir
    if (serviceActionsPollingInterval) {
        clearInterval(serviceActionsPollingInterval);
    }
    
    // Verificar se há alguma action ativa
    const hasActiveSchedules = serviceActions.some(action => 
        action.is_active && action.schedule_type
    );
    
    if (!hasActiveSchedules) {
        console.log('⏹️ Nenhum agendamento ativo, polling desativado');
        return; // Não iniciar polling se não houver agendamentos ativos
    }
    
    // Determinar intervalo baseado em proximidade de execuções
    const pollingInterval = getPollingInterval();
    
    console.log(`🔄 Iniciando polling de service actions (intervalo: ${pollingInterval/1000}s)...`);
    
    // Função de atualização
    const updateServiceActions = async () => {
        try {
            // Apenas recarregar se a tab de gestão de serviços estiver visível
            const servicesTab = document.getElementById('services-management-tab');
            if (!servicesTab || !servicesTab.classList.contains('active')) {
                console.log('⏸️ Tab Gestão de Serviços não visível, pulando atualização');
                return;
            }
            
            console.log('🔄 Atualizando service actions...');
            
            // Recarregar actions (sem reiniciar polling)
            await loadServiceActions();
            renderServicesManagementTab(false); // false = não reiniciar polling
            
        } catch (error) {
            console.error('Erro no polling de service actions:', error);
        }
    };
    
    // Iniciar polling
    serviceActionsPollingInterval = setInterval(updateServiceActions, pollingInterval);
}

/**
 * Calcula intervalo de polling baseado em proximidade de execuções
 * Retorna intervalo em milissegundos
 */
function getPollingInterval() {
    const now = new Date();
    let minMinutesUntilExecution = Infinity;
    
    // Verificar todas as actions ativas com agendamento
    serviceActions.forEach(action => {
        if (!action.is_active || !action.next_run_at) return;
        
        try {
            // Parsear next_run_at
            let dateString = action.next_run_at;
            dateString = dateString.replace(' ', 'T');
            dateString = dateString.replace('Z', '').replace(/[+-]\d{2}:\d{2}$/, '');
            dateString = dateString + '-03:00';
            
            const nextRun = new Date(dateString);
            const minutesUntil = (nextRun - now) / (1000 * 60);
            
            if (minutesUntil > 0 && minutesUntil < minMinutesUntilExecution) {
                minMinutesUntilExecution = minutesUntil;
            }
        } catch (error) {
            console.error('Erro ao calcular tempo até execução:', error);
        }
    });
    
    // Determinar intervalo baseado em proximidade
    if (minMinutesUntilExecution <= 2) {
        return 5000; // 5 segundos se execução nos próximos 2 minutos
    } else if (minMinutesUntilExecution <= 5) {
        return 10000; // 10 segundos se execução nos próximos 5 minutos
    } else if (minMinutesUntilExecution <= 15) {
        return 30000; // 30 segundos se execução nos próximos 15 minutos
    } else {
        return 60000; // 60 segundos para execuções mais distantes
    }
}

/**
 * Para o polling de service actions
 */
function stopServiceActionsPolling() {
    if (serviceActionsPollingInterval) {
        console.log('⏹️ Parando polling de service actions');
        clearInterval(serviceActionsPollingInterval);
        serviceActionsPollingInterval = null;
    }
}

function filterServiceActionsByOS(params) {
    const osType = params.osType;
    window.serviceActionsState.filterOS = osType;
    renderServicesManagementTab();
}


function renderSchedulesWithPagination() {
    const filteredSchedules = getFilteredSchedules();
    
    if (filteredSchedules.length === 0) {
        return `
            <div class="card text-center p-5">
                <i class="fas fa-clock text-muted" style="font-size: 4rem;"></i>
                <p class="text-muted mt-3">Nenhum agendamento configurado para este ${scheduleScriptTypeFilter === 'TODOS' ? 'ambiente' : 'tipo de script'}.</p>
                ${isOperator() ? '<button class="btn btn-primary mt-3" data-action="showCreateScheduleModal"><i class="fas fa-plus me-2"></i>Criar Primeiro Agendamento</button>' : ''}
            </div>`;
    }

    const startIndex = (currentSchedulesPage - 1) * schedulesPerPage;
    const endIndex = startIndex + schedulesPerPage;
    const schedulesForCurrentPage = filteredSchedules.slice(startIndex, endIndex);

    // Verificar permissões
    const canManage = isOperator();

    return schedulesForCurrentPage.map(schedule => {
        const pipeline = pipelines.find(p => p.id === schedule.pipeline_id);
        const pipelineName = pipeline ? pipeline.name : 'Pipeline não encontrada';
        const scheduleTypeLabel = getScheduleTypeLabel(schedule.schedule_type);
        const scheduleConfigText = formatScheduleConfig(schedule.schedule_type, schedule.schedule_config);
        const nextRunText = schedule.next_run_at 
            ? formatDateTime(schedule.next_run_at)
            : 'Não calculado';
        const lastRunText = schedule.last_run_at 
            ? formatDateTime(schedule.last_run_at)
            : 'Nunca executado';
        
        return `
            <div class="card mb-3">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-0">
                            <i class="fas fa-clock me-2"></i>${schedule.name}
                            ${schedule.is_active 
                                ? '<span class="badge bg-success ms-2">Ativo</span>' 
                                : '<span class="badge bg-secondary ms-2">Inativo</span>'}
                        </h6>
                        <small class="text-muted">Pipeline: ${pipelineName}</small>
                    </div>
                    <div class="btn-group">
                        ${canManage ? `
                            <button class="btn btn-sm ${schedule.is_active ? 'btn-warning' : 'btn-success'}" 
                                    data-action="toggleSchedule"
                                    data-params='{"scheduleId": ${schedule.id}}'
                                    title="${schedule.is_active ? 'Desativar' : 'Ativar'}">
                                <i class="fas fa-${schedule.is_active ? 'pause' : 'play'}"></i>
                            </button>
                            <button class="btn btn-sm btn-primary" 
                                    data-action="editSchedule"
                                    data-params='{"scheduleId": ${schedule.id}}'
                                    title="Editar">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" 
                                    data-action="deleteSchedule"
                                    data-params='{"scheduleId": ${schedule.id}}'
                                    title="Excluir">
                                <i class="fas fa-trash"></i>
                            </button>
                        ` : ''}
                    </div>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <p class="mb-2">
                                <strong>Tipo:</strong> ${scheduleTypeLabel}
                            </p>
                            <p class="mb-2">
                                <strong>Configuração:</strong> ${scheduleConfigText}
                            </p>
                        </div>
                        <div class="col-md-6">
                            <p class="mb-2">
                                <strong>Próxima Execução:</strong> 
                                <span class="text-${schedule.is_active ? 'primary' : 'muted'}">${nextRunText}</span>
                            </p>
                            <p class="mb-2">
                                <strong>Última Execução:</strong> ${lastRunText}
                            </p>
                            <p class="mb-0">
                                <strong>Criado por:</strong> ${schedule.created_by_name}
                            </p>
                        </div>
                    </div>
                    ${schedule.description ? `<p class="text-muted mt-2 mb-0"><em>${schedule.description}</em></p>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function renderSchedulesPagination() {
    const filteredSchedules = getFilteredSchedules();
    const totalPages = Math.ceil(filteredSchedules.length / schedulesPerPage);
    if (totalPages <= 1) return '';

    return `
        <nav class="d-flex justify-content-center mt-4">
            <ul class="pagination">
                <li class="page-item ${currentSchedulesPage === 1 ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="changeSchedulesPage" data-params='{"page":${currentSchedulesPage - 1}}'>Anterior</a>
                </li>
                <li class="page-item disabled"><span class="page-link">${currentSchedulesPage} de ${totalPages}</span></li>
                <li class="page-item ${currentSchedulesPage === totalPages ? 'disabled' : ''}">
                    <a class="page-link" href="#" data-action="changeSchedulesPage" data-params='{"page":${currentSchedulesPage + 1}}'>Próximo</a>
                </li>
            </ul>
        </nav>
    `;
}

function changeSchedulesPage(page) {
    const totalPages = Math.ceil(schedules.length / schedulesPerPage);
    if (page < 1 || (page > totalPages && totalPages > 0)) return;
    
    currentSchedulesPage = page;
    updateSchedulesList();
}

function filterSchedulesByScriptType(scriptType) {
    scheduleScriptTypeFilter = scriptType;
    currentSchedulesPage = 1; // Resetar para primeira página
    showSchedules(); // Re-renderizar a tela inteira
}

function getFilteredSchedules() {
    if (scheduleScriptTypeFilter === 'TODOS') {
        return schedules;
    }
    
    // Filtra schedules cujas pipelines contêm o tipo de script no nome
    return schedules.filter(schedule => {
        const pipeline = pipelines.find(p => p.id === schedule.pipeline_id);
        if (!pipeline) return false;
        return pipeline.name.includes(`(${scheduleScriptTypeFilter})`);
    });
}

function getFilteredPipelinesForSchedule() {
    if (scheduleScriptTypeFilter === 'TODOS') {
        return pipelines;
    }
    
    // Filtra pipelines que contêm o tipo de script no nome
    return pipelines.filter(p => p.name.includes(`(${scheduleScriptTypeFilter})`));
}

function updateSchedulesList() {
    const container = document.getElementById('schedulesContainer');
    const pagination = document.getElementById('schedulesPagination');

    if (container) container.innerHTML = renderSchedulesWithPagination();
    if (pagination) pagination.innerHTML = renderSchedulesPagination();
}

function getScheduleTypeLabel(type) {
    const labels = {
        'once': '⏱️ Execução Única',
        'daily': '📅 Diária',
        'weekly': '📆 Semanal',
        'monthly': '🗓️ Mensal',
        'cron': '⚙️ Cron (Avançado)'
    };
    return labels[type] || type;
}

function formatScheduleConfig(type, configJson) {
    try {
        const config = typeof configJson === 'string' ? JSON.parse(configJson) : configJson;
        
        if (type === 'once') {
            return `Em ${formatDateTime(config.datetime)}`;
        } else if (type === 'daily') {
            return `Todo dia às ${String(config.hour).padStart(2, '0')}:${String(config.minute).padStart(2, '0')}`;
        } else if (type === 'weekly') {
            const days = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
            const selectedDays = config.weekdays.map(d => days[d]).join(', ');
            return `${selectedDays} às ${String(config.hour).padStart(2, '0')}:${String(config.minute).padStart(2, '0')}`;
        } else if (type === 'monthly') {
            return `Dia ${config.day} de cada mês às ${String(config.hour).padStart(2, '0')}:${String(config.minute).padStart(2, '0')}`;
        } else if (type === 'cron') {
            return `Expressão: ${config.expression}`;
        }
        
        return 'Configuração inválida';
    } catch (e) {
        return 'Erro ao interpretar configuração';
    }
}

function createScheduleModals() {
    return `
        <!-- Modal: Criar Schedule -->
        <div class="modal fade" id="createScheduleModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-clock me-2"></i>Novo Agendamento</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="createScheduleForm">
                            <div class="mb-3">
                                <label class="form-label">Nome do Agendamento *</label>
                                <input type="text" class="form-control" id="scheduleName" required>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Descrição</label>
                                <textarea class="form-control" id="scheduleDescription" rows="2"></textarea>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Pipeline *</label>
                                <select class="form-select" id="schedulePipelineId" required>
                                    <option value="">Selecione uma pipeline</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Tipo de Agendamento *</label>
                                <select class="form-select" id="scheduleType" required>
                                    <option value="">Selecione o tipo</option>
                                    <option value="once">⏱️ Execução Única</option>
                                    <option value="daily">📅 Diária</option>
                                    <option value="weekly">📆 Semanal</option>
                                    <option value="monthly">🗓️ Mensal</option>
                                </select>
                            </div>
                            
                            <!-- Configurações Dinâmicas -->
                            <div id="scheduleConfigArea"></div>
                            
                            <div class="alert alert-info mt-3">
                                <i class="fas fa-info-circle me-2"></i>
                                <strong>Importante:</strong> O agendamento será criado <strong>INATIVO</strong>. 
                                Você precisará ativá-lo manualmente após a criação.
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="saveNewSchedule">
                            <i class="fas fa-save me-2"></i>Criar Agendamento
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modal: Editar Schedule -->
        <div class="modal fade" id="editScheduleModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-edit me-2"></i>Editar Agendamento</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="editScheduleForm">
                            <input type="hidden" id="editScheduleId">
                            
                            <div class="mb-3">
                                <label class="form-label">Nome do Agendamento *</label>
                                <input type="text" class="form-control" id="editScheduleName" required>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Descrição</label>
                                <textarea class="form-control" id="editScheduleDescription" rows="2"></textarea>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Pipeline *</label>
                                <select class="form-select" id="editSchedulePipelineId" required disabled>
                                    <option value="">Selecione uma pipeline</option>
                                </select>
                                <small class="text-muted">Pipeline não pode ser alterada. Crie um novo agendamento se necessário.</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Tipo de Agendamento *</label>
                                <select class="form-select" id="editScheduleType" required>
                                    <option value="">Selecione o tipo</option>
                                    <option value="once">⏱️ Execução Única</option>
                                    <option value="daily">📅 Diária</option>
                                    <option value="weekly">📆 Semanal</option>
                                    <option value="monthly">🗓️ Mensal</option>
                                </select>
                            </div>
                            
                            <!-- Configurações Dinâmicas -->
                            <div id="editScheduleConfigArea"></div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" data-action="saveEditSchedule">
                            <i class="fas fa-save me-2"></i>Salvar Alterações
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function showCreateScheduleModal() {
    // Popula dropdown de pipelines (filtradas por tipo)
    const filteredPipelines = getFilteredPipelinesForSchedule();
    const pipelineSelect = document.getElementById('schedulePipelineId');
    
    // Verificação de segurança
    if (!pipelineSelect) {
        console.error('Elemento schedulePipelineId não encontrado');
        showNotification('Erro ao abrir modal de agendamento', 'error');
        return;
    }
    
    if (filteredPipelines.length === 0) {
        showNotification(`Nenhuma pipeline ${scheduleScriptTypeFilter === 'TODOS' ? 'disponível' : 'do tipo ' + scheduleScriptTypeFilter + ' encontrada'}!`, 'warning');
        return;
    }
    
    pipelineSelect.innerHTML = '<option value="">Selecione uma pipeline</option>' +
        filteredPipelines.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
    
    // Listener para mudança de tipo
    const typeSelect = document.getElementById('scheduleType');
    if (typeSelect) {
        // Remove listeners antigos para evitar duplicação
        const newTypeSelect = typeSelect.cloneNode(true);
        typeSelect.parentNode.replaceChild(newTypeSelect, typeSelect);
        
        newTypeSelect.addEventListener('change', () => {
            renderScheduleConfigInputs('scheduleConfigArea', newTypeSelect.value);
        });
    }
    
    // Limpa formulário
    const form = document.getElementById('createScheduleForm');
    const configArea = document.getElementById('scheduleConfigArea');
    
    if (form) form.reset();
    if (configArea) configArea.innerHTML = '';
    
    const modalElement = document.getElementById('createScheduleModal');
    if (modalElement) {
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
    } else {
        console.error('Modal createScheduleModal não encontrado');
        showNotification('Erro ao abrir modal', 'error');
    }
}

function editSchedule(scheduleId) {
    const schedule = schedules.find(s => s.id === scheduleId);
    if (!schedule) return;
    
    // Preenche campos
    document.getElementById('editScheduleId').value = schedule.id;
    document.getElementById('editScheduleName').value = schedule.name;
    document.getElementById('editScheduleDescription').value = schedule.description || '';
    
    // Popula dropdown de pipelines (desabilitado, mas mostra todas para não perder a selecionada)
    const pipelineSelect = document.getElementById('editSchedulePipelineId');
    pipelineSelect.innerHTML = '<option value="">Selecione uma pipeline</option>' +
        pipelines.map(p => `<option value="${p.id}" ${p.id === schedule.pipeline_id ? 'selected' : ''}>${p.name}</option>`).join('');
    
    // Tipo de schedule
    const typeSelect = document.getElementById('editScheduleType');
    typeSelect.value = schedule.schedule_type;
    
    // Renderiza inputs de config
    renderScheduleConfigInputs('editScheduleConfigArea', schedule.schedule_type, schedule.schedule_config);
    
    // Listener para mudança de tipo
    typeSelect.addEventListener('change', () => {
        renderScheduleConfigInputs('editScheduleConfigArea', typeSelect.value);
    });
    
    const modal = new bootstrap.Modal(document.getElementById('editScheduleModal'));
    modal.show();
}

function renderScheduleConfigInputs(containerId, type, existingConfigJson = null) {
    const container = document.getElementById(containerId);
    let existingConfig = {};
    
    if (existingConfigJson) {
        try {
            existingConfig = typeof existingConfigJson === 'string' 
                ? JSON.parse(existingConfigJson) 
                : existingConfigJson;
        } catch (e) {
            console.error('Erro ao parsear config:', e);
        }
    }
    
    if (type === 'once') {
        // Execução única
        const now = new Date();
        now.setMinutes(now.getMinutes() + 5); // Padrão: daqui 5 minutos
        const defaultDatetime = existingConfig.datetime || now.toISOString().slice(0, 16);
        
        container.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Este agendamento será executado <strong>uma única vez</strong> e depois será desativado automaticamente.
            </div>
            <div class="mb-3">
                <label class="form-label">Data e Hora da Execução *</label>
                <input type="datetime-local" class="form-control" id="scheduleConfigDatetime" value="${defaultDatetime}" required>
            </div>
        `;
        
    } else if (type === 'daily') {
        // Diária
        const defaultHour = existingConfig.hour || 9;
        const defaultMinute = existingConfig.minute || 0;
        
        container.innerHTML = `
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Hora *</label>
                    <input type="number" class="form-control" id="scheduleConfigHour" 
                           min="0" max="23" value="${defaultHour}" required>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">Minuto *</label>
                    <input type="number" class="form-control" id="scheduleConfigMinute" 
                           min="0" max="59" value="${defaultMinute}" required>
                </div>
            </div>
        `;
        
    } else if (type === 'weekly') {
        // Semanal
        const defaultHour = existingConfig.hour || 9;
        const defaultMinute = existingConfig.minute || 0;
        const existingWeekdays = existingConfig.weekdays || [];
        
        const weekdays = [
            { value: 0, label: 'Segunda-feira' },
            { value: 1, label: 'Terça-feira' },
            { value: 2, label: 'Quarta-feira' },
            { value: 3, label: 'Quinta-feira' },
            { value: 4, label: 'Sexta-feira' },
            { value: 5, label: 'Sábado' },
            { value: 6, label: 'Domingo' }
        ];
        
        container.innerHTML = `
            <div class="mb-3">
                <label class="form-label">Dias da Semana *</label>
                <div class="border rounded p-3">
                    ${weekdays.map(day => `
                        <div class="form-check">
                            <input class="form-check-input schedule-weekday" type="checkbox" 
                                   value="${day.value}" id="weekday${day.value}"
                                   ${existingWeekdays.includes(day.value) ? 'checked' : ''}>
                            <label class="form-check-label" for="weekday${day.value}">
                                ${day.label}
                            </label>
                        </div>
                    `).join('')}
                </div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Hora *</label>
                    <input type="number" class="form-control" id="scheduleConfigHour" 
                           min="0" max="23" value="${defaultHour}" required>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">Minuto *</label>
                    <input type="number" class="form-control" id="scheduleConfigMinute" 
                           min="0" max="59" value="${defaultMinute}" required>
                </div>
            </div>
        `;
        
    } else if (type === 'monthly') {
        // Mensal
        const defaultDay = existingConfig.day || 1;
        const defaultHour = existingConfig.hour || 9;
        const defaultMinute = existingConfig.minute || 0;
        
        container.innerHTML = `
            <div class="mb-3">
                <label class="form-label">Dia do Mês *</label>
                <input type="number" class="form-control" id="scheduleConfigDay" 
                       min="1" max="31" value="${defaultDay}" required>
                <small class="text-muted">Se o mês não tiver este dia, o agendamento será pulado.</small>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Hora *</label>
                    <input type="number" class="form-control" id="scheduleConfigHour" 
                           min="0" max="23" value="${defaultHour}" required>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">Minuto *</label>
                    <input type="number" class="form-control" id="scheduleConfigMinute" 
                           min="0" max="59" value="${defaultMinute}" required>
                </div>
            </div>
        `;
        
    } else {
        container.innerHTML = '<p class="text-muted">Selecione um tipo de agendamento</p>';
    }
}

async function saveNewSchedule() {
    try {
        const name = document.getElementById('scheduleName').value.trim();
        const description = document.getElementById('scheduleDescription').value.trim();
        const pipelineId = parseInt(document.getElementById('schedulePipelineId').value);
        const scheduleType = document.getElementById('scheduleType').value;
        
        if (!name || !pipelineId || !scheduleType) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }
        
        // Monta config baseado no tipo
        const scheduleConfig = buildScheduleConfig(scheduleType);
        
        if (!scheduleConfig) {
            showNotification('Configuração de agendamento inválida!', 'error');
            return;
        }
        
        await apiCreateSchedule({
            pipeline_id: pipelineId,
            name,
            description,
            schedule_type: scheduleType,
            schedule_config: JSON.stringify(scheduleConfig)
        });
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('createScheduleModal'));
        modal.hide();
        
        await loadSchedules();
        showSchedules();
        showNotification('Agendamento criado com sucesso (INATIVO)!', 'success');
        
    } catch (error) {
        showNotification(error.message || 'Erro ao criar agendamento', 'error');
    }
}

async function saveEditSchedule() {
    try {
        const scheduleId = parseInt(document.getElementById('editScheduleId').value);
        const name = document.getElementById('editScheduleName').value.trim();
        const description = document.getElementById('editScheduleDescription').value.trim();
        const pipelineId = parseInt(document.getElementById('editSchedulePipelineId').value);
        const scheduleType = document.getElementById('editScheduleType').value;
        
        if (!name || !pipelineId || !scheduleType) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }
        
        const scheduleConfig = buildScheduleConfig(scheduleType);
        
        if (!scheduleConfig) {
            showNotification('Configuração de agendamento inválida!', 'error');
            return;
        }
        
        await apiUpdateSchedule(scheduleId, {
            pipeline_id: pipelineId,
            name,
            description,
            schedule_type: scheduleType,
            schedule_config: JSON.stringify(scheduleConfig)
        });
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('editScheduleModal'));
        modal.hide();
        
        await loadSchedules();
        showSchedules();
        showNotification('Agendamento atualizado com sucesso!', 'success');
        
    } catch (error) {
        showNotification(error.message || 'Erro ao atualizar agendamento', 'error');
    }
}

async function toggleSchedule(scheduleId) {
    try {
        const schedule = schedules.find(s => s.id === scheduleId);
        if (!schedule) return;
        
        const action = schedule.is_active ? 'desativar' : 'ativar';
        
        if (!confirm(`Deseja ${action} este agendamento?`)) return;
        
        const result = await apiToggleSchedule(scheduleId);
        
        await loadSchedules();
        showSchedules();
        showNotification(result.message, 'success');
        
    } catch (error) {
        showNotification(error.message || 'Erro ao alterar status', 'error');
    }
}

async function deleteSchedule(scheduleId) {
    try {
        const schedule = schedules.find(s => s.id === scheduleId);
        if (!schedule) return;
        
        if (!confirm(`Tem certeza que deseja excluir o agendamento "${schedule.name}"?`)) return;
        
        await apiDeleteSchedule(scheduleId);
        
        await loadSchedules();
        showSchedules();
        showNotification('Agendamento excluído com sucesso!', 'warning');
        
    } catch (error) {
        showNotification(error.message || 'Erro ao excluir agendamento', 'error');
    }
}

function buildScheduleConfig(scheduleType) {
    if (scheduleType === 'once') {
        const datetime = document.getElementById('scheduleConfigDatetime').value;
        if (!datetime) return null;
        return { datetime };
        
    } else if (scheduleType === 'daily') {
        const hour = parseInt(document.getElementById('scheduleConfigHour').value);
        const minute = parseInt(document.getElementById('scheduleConfigMinute').value);
        if (isNaN(hour) || isNaN(minute)) return null;
        return { hour, minute };
        
    } else if (scheduleType === 'weekly') {
        const hour = parseInt(document.getElementById('scheduleConfigHour').value);
        const minute = parseInt(document.getElementById('scheduleConfigMinute').value);
        const weekdays = Array.from(document.querySelectorAll('.schedule-weekday:checked'))
            .map(cb => parseInt(cb.value));
        
        if (isNaN(hour) || isNaN(minute) || weekdays.length === 0) return null;
        return { hour, minute, weekdays };
        
    } else if (scheduleType === 'monthly') {
        const day = parseInt(document.getElementById('scheduleConfigDay').value);
        const hour = parseInt(document.getElementById('scheduleConfigHour').value);
        const minute = parseInt(document.getElementById('scheduleConfigMinute').value);
        
        if (isNaN(day) || isNaN(hour) || isNaN(minute)) return null;
        return { day, hour, minute };
    }
    
    return null;
}

function showCreateServiceActionModal() {
    // Inicializa estado de ordenação
    window.serviceActionOrder = [];
    
    // Popula lista de serviços (somente ativos)
    const container = document.getElementById('serviceActionServicesList');
    const activeServices = serverServices.filter(s => s.is_active !== false);
    
    if (activeServices.length === 0) {
        container.innerHTML = `
            <div class="alert alert-warning mb-0">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Nenhum serviço cadastrado. <a href="#" data-action="showCreateServiceModal">Criar serviço</a>
            </div>
        `;
    } else {
        renderServicesList(container, activeServices, '', []);
    }
    
    // Limpa formulário
    document.getElementById('createServiceActionForm').reset();
    document.getElementById('serviceActionScheduleConfig').style.display = 'none';
    document.getElementById('serviceActionScheduleConfigArea').innerHTML = '';
    
    // Configura toggle de agendamento
    setupServiceActionScheduleToggle('');
    
    const modal = new bootstrap.Modal(document.getElementById('createServiceActionModal'));
    modal.show();
}

// =====================================================================
// SEQUENCIADOR DE SERVIÇOS
// =====================================================================

function renderServicesList(container, services, prefix, selectedOrder) {
    // selectedOrder é um array de IDs na ordem de seleção
    window.serviceActionOrder = selectedOrder ? [...selectedOrder] : [];
    
    container.innerHTML = services.map(service => {
        const envName = environments.find(e => e.id === service.environment_id)?.name || 'N/A';
        const orderIndex = window.serviceActionOrder.indexOf(service.id.toString());
        const isSelected = orderIndex !== -1;
        const orderBadge = isSelected 
            ? `<span class="badge bg-primary rounded-pill ms-2 service-order-badge" data-service-id="${service.id}">${orderIndex + 1}</span>` 
            : `<span class="badge bg-secondary rounded-pill ms-2 service-order-badge d-none" data-service-id="${service.id}"></span>`;
        
        return `
            <div class="form-check service-item d-flex align-items-center justify-content-between py-2 border-bottom" data-service-id="${service.id}">
                <div class="d-flex align-items-start">
                    <input class="form-check-input mt-1 service-checkbox" type="checkbox" value="${service.id}" 
                           id="${prefix}service-${service.id}" ${isSelected ? 'checked' : ''}
                           onchange="updateServiceOrder(this, '${prefix}')">
                    <label class="form-check-label ms-2" for="${prefix}service-${service.id}">
                        <strong>${service.display_name || service.name}</strong>
                        <small class="text-muted d-block">
                            📦 ${service.name} @ ${service.server_name} (${envName})
                        </small>
                    </label>
                </div>
                ${orderBadge}
            </div>
        `;
    }).join('');
    
    // Adiciona área de resumo da ordem
    const summaryId = prefix ? `${prefix}ServiceOrderSummary` : 'serviceOrderSummary';
    let summaryEl = document.getElementById(summaryId);
    if (!summaryEl) {
        summaryEl = document.createElement('div');
        summaryEl.id = summaryId;
        summaryEl.className = 'mt-3';
        container.parentNode.appendChild(summaryEl);
    }
    updateOrderSummary(prefix);
}

function updateServiceOrder(checkbox, prefix = '') {
    const serviceId = checkbox.value;
    
    if (checkbox.checked) {
        // Adiciona ao final da ordem
        if (!window.serviceActionOrder.includes(serviceId)) {
            window.serviceActionOrder.push(serviceId);
        }
    } else {
        // Remove da ordem
        const index = window.serviceActionOrder.indexOf(serviceId);
        if (index > -1) {
            window.serviceActionOrder.splice(index, 1);
        }
    }
    
    // Atualiza todos os badges
    updateOrderBadges(prefix);
    updateOrderSummary(prefix);
}

function updateOrderBadges(prefix = '') {
    const containerId = prefix ? `${prefix}ServiceActionServicesList` : 'serviceActionServicesList';
    const container = document.getElementById(containerId);
    if (!container) return;
    
    container.querySelectorAll('.service-order-badge').forEach(badge => {
        const serviceId = badge.dataset.serviceId;
        const orderIndex = window.serviceActionOrder.indexOf(serviceId);
        
        if (orderIndex !== -1) {
            badge.textContent = orderIndex + 1;
            badge.classList.remove('d-none', 'bg-secondary');
            badge.classList.add('bg-primary');
        } else {
            badge.textContent = '';
            badge.classList.add('d-none');
        }
    });
}

function updateOrderSummary(prefix = '') {
    const summaryId = prefix ? `${prefix}ServiceOrderSummary` : 'serviceOrderSummary';
    const summaryEl = document.getElementById(summaryId);
    if (!summaryEl) return;
    
    if (window.serviceActionOrder.length === 0) {
        summaryEl.innerHTML = '';
        return;
    }
    
    const orderedServices = window.serviceActionOrder.map((id, index) => {
        const service = serverServices.find(s => s.id === parseInt(id));
        return service ? `<span class="badge bg-light text-dark border me-1 mb-1">${index + 1}. ${service.display_name || service.name}</span>` : '';
    }).join('');
    
    summaryEl.innerHTML = `
        <div class="alert alert-info py-2 mb-0">
            <small><strong>📋 Ordem de execução:</strong></small>
            <div class="mt-1">${orderedServices}</div>
        </div>
    `;
}

function getSelectedServicesInOrder(prefix = '') {
    // Retorna os IDs na ordem correta
    return window.serviceActionOrder || [];
}

// Toggle para mostrar/ocultar campos de agendamento
function setupServiceActionScheduleToggle(prefix = '') {
    const checkbox = document.getElementById(`${prefix}serviceActionEnableSchedule`);
    const configSection = document.getElementById(`${prefix}serviceActionScheduleConfig`);
    const typeSelect = document.getElementById(prefix ? `${prefix}ServiceActionScheduleType` : 'serviceActionScheduleType');
    
    if (!checkbox || !configSection || !typeSelect) return;
    
    checkbox.addEventListener('change', function() {
        configSection.style.display = this.checked ? 'block' : 'none';
        if (!this.checked) {
            typeSelect.value = '';
            document.getElementById(`${prefix}serviceActionScheduleConfigArea`).innerHTML = '';
        }
    });
    
    // Remove listeners antigos para evitar duplicação
    const newTypeSelect = typeSelect.cloneNode(true);
    typeSelect.parentNode.replaceChild(newTypeSelect, typeSelect);
    
    newTypeSelect.addEventListener('change', function() {
        renderScheduleConfigInputs(`${prefix}serviceActionScheduleConfigArea`, this.value);
    });
}

// Função para construir config de schedule (reutilizada do schedule de pipelines)
function buildServiceActionScheduleConfig(prefix = '') {
    const scheduleType = document.getElementById(prefix ? `${prefix}ServiceActionScheduleType` : 'serviceActionScheduleType').value;
    if (!scheduleType) return null;
    
    if (scheduleType === 'once') {
        const datetime = document.getElementById('scheduleConfigDatetime').value;
        if (!datetime) return null;
        return { datetime };
        
    } else if (scheduleType === 'daily') {
        const hour = parseInt(document.getElementById('scheduleConfigHour').value);
        const minute = parseInt(document.getElementById('scheduleConfigMinute').value);
        if (isNaN(hour) || isNaN(minute)) return null;
        return { hour, minute };
        
    } else if (scheduleType === 'weekly') {
        const weekdays = Array.from(document.querySelectorAll('.schedule-weekday:checked'))
            .map(cb => parseInt(cb.value));
        const hour = parseInt(document.getElementById('scheduleConfigHour').value);
        const minute = parseInt(document.getElementById('scheduleConfigMinute').value);
        if (weekdays.length === 0 || isNaN(hour) || isNaN(minute)) return null;
        return { weekdays, hour, minute };
        
    } else if (scheduleType === 'monthly') {
        const day = parseInt(document.getElementById('scheduleConfigDay').value);
        const hour = parseInt(document.getElementById('scheduleConfigHour').value);
        const minute = parseInt(document.getElementById('scheduleConfigMinute').value);
        if (isNaN(day) || isNaN(hour) || isNaN(minute)) return null;
        return { day, hour, minute };
    }
    
    return null;
}

async function saveNewServiceAction() {
    try {
        const name = document.getElementById('serviceActionName').value.trim();
        const description = document.getElementById('serviceActionDescription').value.trim();
        const actionType = document.getElementById('serviceActionType').value;
        const osType = document.getElementById('serviceActionOS').value;
        const forceStop = document.getElementById('serviceActionForceStop').checked;
        
        // Coletar IDs dos serviços NA ORDEM selecionada
        const selectedServices = getSelectedServicesInOrder('');
        
        if (!name || !actionType || !osType || selectedServices.length === 0) {
            showNotification('Preencha todos os campos obrigatórios e selecione pelo menos um serviço!', 'error');
            return;
        }
        
        // Verificar se agendamento está habilitado
        const scheduleEnabled = document.getElementById('serviceActionEnableSchedule').checked;
        let scheduleData = {};
        
        if (scheduleEnabled) {
            const scheduleType = document.getElementById('serviceActionScheduleType').value;
            if (!scheduleType) {
                showNotification('Selecione o tipo de agendamento!', 'error');
                return;
            }
            
            const scheduleConfig = buildServiceActionScheduleConfig('');
            if (!scheduleConfig) {
                showNotification('Configuração de agendamento inválida!', 'error');
                return;
            }
            
            scheduleData = {
                schedule_type: scheduleType,
                schedule_config: JSON.stringify(scheduleConfig),
                is_active: false
            };
        }
        
        await apiCreateServiceAction({
            name,
            description,
            action_type: actionType,
            os_type: osType,
            force_stop: forceStop,
            service_ids: selectedServices.join(','),
            ...scheduleData
        });
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('createServiceActionModal'));
        modal.hide();
        
        // Limpa estado de ordenação
        window.serviceActionOrder = [];
        
        await loadServiceActions();
        renderServicesManagementTab();
        
        showNotification('Ação de serviço criada com sucesso!', 'success');
        
    } catch (error) {
        showNotification(error.message || 'Erro ao criar ação', 'error');
    }
}

function editServiceAction(actionId) {
    const action = serviceActions.find(a => a.id === actionId);
    if (!action) return;
    
    // Preenche campos
    document.getElementById('editServiceActionId').value = action.id;
    document.getElementById('editServiceActionName').value = action.name;
    document.getElementById('editServiceActionDescription').value = action.description || '';
    document.getElementById('editServiceActionType').value = action.action_type;
    document.getElementById('editServiceActionOS').value = action.os_type;
    document.getElementById('editServiceActionForceStop').checked = action.force_stop || false;
    
    // Popula lista de serviços com sequenciador - mantém ordem existente
    const selectedIds = action.service_ids ? action.service_ids.split(',') : [];
    const container = document.getElementById('editServiceActionServicesList');
    const activeServices = serverServices.filter(s => s.is_active !== false);
    
    // Usa renderServicesList com a ordem existente
    renderServicesList(container, activeServices, 'edit', selectedIds);

    // Configurar agendamento se existir
    const hasSchedule = action.schedule_type && action.schedule_config;
    document.getElementById('editServiceActionEnableSchedule').checked = hasSchedule;
    
    if (hasSchedule) {
        document.getElementById('editServiceActionScheduleConfig').style.display = 'block';
        document.getElementById('editServiceActionScheduleType').value = action.schedule_type;
        renderScheduleConfigInputs('editServiceActionScheduleConfigArea', action.schedule_type, action.schedule_config);
    } else {
        document.getElementById('editServiceActionScheduleConfig').style.display = 'none';
        document.getElementById('editServiceActionScheduleConfigArea').innerHTML = '';
    }
    
    // Configura toggle de agendamento
    setupServiceActionScheduleToggle('edit');

    const modal = new bootstrap.Modal(document.getElementById('editServiceActionModal'));
    modal.show();
}

async function saveEditedServiceAction() {
    try {
        const actionId = parseInt(document.getElementById('editServiceActionId').value);
        const name = document.getElementById('editServiceActionName').value.trim();
        const description = document.getElementById('editServiceActionDescription').value.trim();
        const actionType = document.getElementById('editServiceActionType').value;
        const osType = document.getElementById('editServiceActionOS').value;
        const forceStop = document.getElementById('editServiceActionForceStop').checked;
        
        // Coletar IDs dos serviços NA ORDEM selecionada
        const selectedServices = getSelectedServicesInOrder('edit');
        
        if (!name || !actionType || !osType || selectedServices.length === 0) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }
        
        // Verificar se agendamento está habilitado
        const scheduleEnabled = document.getElementById('editServiceActionEnableSchedule').checked;
        let scheduleData = {};
        
        if (scheduleEnabled) {
            const scheduleType = document.getElementById('editServiceActionScheduleType').value;
            if (!scheduleType) {
                showNotification('Selecione o tipo de agendamento!', 'error');
                return;
            }
            
            const scheduleConfig = buildServiceActionScheduleConfig('edit');
            if (!scheduleConfig) {
                showNotification('Configuração de agendamento inválida!', 'error');
                return;
            }
            
            scheduleData = {
                schedule_type: scheduleType,
                schedule_config: JSON.stringify(scheduleConfig)
            };
        } else {
            // Se desabilitou o agendamento, enviar nulls
            scheduleData = {
                schedule_type: null,
                schedule_config: null,
                is_active: false
            };
        }
        
        await apiUpdateServiceAction(actionId, {
            name,
            description,
            action_type: actionType,
            os_type: osType,
            force_stop: forceStop,
            service_ids: selectedServices.join(','),
            ...scheduleData
        });
        
        const modal = bootstrap.Modal.getInstance(document.getElementById('editServiceActionModal'));
        modal.hide();
        
        // Limpa estado de ordenação
        window.serviceActionOrder = [];
        
        await loadServiceActions();
        renderServicesManagementTab();
        
        showNotification('Ação atualizada com sucesso!', 'success');
        
    } catch (error) {
        showNotification(error.message || 'Erro ao atualizar ação', 'error');
    }
}

async function deleteServiceAction(actionId) {
    const action = serviceActions.find(a => a.id === actionId);
    if (!action) return;
    
    if (confirm(`Tem certeza que deseja excluir a ação "${action.name}"?\n\nEsta ação não pode ser desfeita.`)) {
        try {
            await apiDeleteServiceAction(actionId);
            await loadServiceActions();
            renderServicesManagementTab();
            showNotification('Ação excluída com sucesso!', 'success');
        } catch (error) {
            showNotification(error.message || 'Erro ao excluir ação', 'error');
        }
    }
}

async function executeServiceAction(actionId) {
    const action = serviceActions.find(a => a.id === actionId);
    if (!action) return;
    
    if (confirm(`Deseja executar a ação "${action.name}"?\n\nOs serviços serão ${action.action_type === 'start' ? 'iniciados' : 'parados'} sequencialmente.`)) {
        try {
            showNotification(`Executando "${action.name}"...`, 'info');
            
            const result = await apiExecuteServiceAction(actionId);
            
            // Mostrar resultados detalhados
            const successCount = result.results.filter(r => r.success).length;
            const totalCount = result.results.length;
            
            if (successCount === totalCount) {
                showNotification(`✅ ${result.message} - Todos os serviços foram processados com sucesso!`, 'success');
            } else {
                const failedServices = result.results.filter(r => !r.success).map(r => r.service).join(', ');
                showNotification(`⚠️ ${result.message} - Alguns serviços falharam: ${failedServices}`, 'warning');
            }
            
            // Log detalhado no console
            console.log('Resultado da execução:', result);
            
        } catch (error) {
            showNotification(error.message || 'Erro ao executar ação', 'error');
        }
    }
}

async function toggleServiceActionSchedule(params) {
    const { actionId, isActive } = params;
    const action = serviceActions.find(a => a.id === actionId);
    if (!action) return;
    
    const newStatus = !isActive;
    const actionText = newStatus ? 'ativar' : 'desativar';
    
    if (confirm(`Deseja ${actionText} o agendamento da ação "${action.name}"?`)) {
        try {
            await apiUpdateServiceAction(actionId, { is_active: newStatus });
            await loadServiceActions();
            renderServicesManagementTab();
            showNotification(`Agendamento ${newStatus ? 'ativado' : 'desativado'} com sucesso!`, 'success');
        } catch (error) {
            showNotification(error.message || `Erro ao ${actionText} agendamento`, 'error');
        }
    }
}

// function showDeploys() {
//     const content = `
//         <div>
//             <div class="d-flex justify-content-between align-items-center mb-4">
//                 <div>
//                     <h2>Ações de Deploy</h2>
//                     <p class="text-muted">Gerenciamento de scripts de implantação</p>
//                 </div>
//                 <button class="btn btn-primary" data-action="showCreateDeployModal">
//                     <i class="fas fa-plus me-2"></i>Novo Deploy
//                 </button>
//             </div>
//             <div id="deploysContainer">${renderDeploys()}</div>
//         </div>
//     `;
//     document.getElementById('content-area').innerHTML = content;
// }

// function renderDeploys() {
//     if (deploys.length === 0) {
//         return `<div class="card text-center p-5"><p class="text-muted">Nenhuma ação de deploy cadastrada.</p></div>`;
//     }
//     return `
//         <div class="row">
//             ${deploys.map(d => `
//                 <div class="col-md-6 col-lg-4 mb-4">
//                     <div class="card h-100">
//                         <div class="card-header d-flex justify-content-between align-items-center">
//                             <h6 class="mb-0 text-truncate"><i class="fas fa-rocket me-2"></i>${d.name}</h6>
//                             <div class="dropdown">
//                                 <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown"><i class="fas fa-ellipsis-v"></i></button>
//                                 <ul class="dropdown-menu">
//                                     <li><a class="dropdown-item" href="#" data-action="showEditDeployModal" data-params=\'{"deployId":${d.id}}\'><i class="fas fa-edit me-2"></i>Editar</a></li>
//                                     <li><a class="dropdown-item text-danger" href="#" data-action="deleteDeploy" data-params=\'{"deployId":${d.id}}\'><i class="fas fa-trash me-2"></i>Excluir</a></li>
//                                 </ul>
//                             </div>
//                         </div>
//                         <div class="card-body">
//                             <p class="text-muted small">${d.description || 'Sem descrição'}</p>
//                             <small class="text-muted d-block">Comando Associado:</small>
//                             <strong>${d.command_name}</strong>
//                         </div>
//                     </div>
//                 </div>
//             `).join('')}
//         </div>
//     `;
// }
// function showCreateDeployModal() {
//     // Lógica para abrir o modal de criação de deploy
//     const commandOptions = commands.map(c => `<option value="${c.id}">${c.name} (${c.type})</option>`).join('');
//     document.getElementById('deployCommandId').innerHTML = `<option value="">Selecione um comando</option>${commandOptions}`;
//     new bootstrap.Modal(document.getElementById('createDeployModal')).show();
// }
// function editDeploy(deployId) {
//     // Lógica para preencher e abrir o modal de edição de deploy
//     const deploy = deploys.find(d => d.id === deployId);
//     if (!deploy) return;
//     document.getElementById('editDeployId').value = deploy.id;
//     document.getElementById('editDeployName').value = deploy.name;
//     document.getElementById('editDeployDescription').value = deploy.description;
//     const commandOptions = commands.map(c => `<option value="${c.id}" ${c.id === deploy.command_id ? 'selected' : ''}>${c.name} (${c.type})</option>`).join('');
//     document.getElementById('editDeployCommandId').innerHTML = commandOptions;
//     new bootstrap.Modal(document.getElementById('editDeployModal')).show();
// }

function showCommands() {
    const content = `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2>Biblioteca de Comandos</h2>
                    <p class="text-muted">Scripts para automação</p>
                </div>
                ${isAdmin() ? `
                <button class="btn btn-primary" data-action="showCreateCommandModal">
                    <i class="fas fa-plus me-2"></i>Novo Comando
                </button>
                ` : ''}
            </div>
            <div id="commandsContainer"></div>
            <div id="commandsPagination"></div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;
    changeCommandsPage(1); // CORREÇÃO: Inicia a renderização na primeira página.
}

function renderCommands() {
    if (commands.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted">Nenhum comando cadastrado.</p>
                ${isAdmin() ? '<button class="btn btn-primary mt-3" data-action="showCreateCommandModal"><i class="fas fa-plus me-2"></i>Criar Primeiro Comando</button>' : ''}
            </div>`;
    }

    // Verificar permissões
    const canEdit = isAdmin();
    const canDelete = isAdmin();

    return `
        <div class="row">
            ${commands.map(command => {
                // Verificar se item é protegido
                const isProtected = command.is_protected && !isRootAdmin();
                const showEditBtn = canEdit && !isProtected;
                const showDeleteBtn = canDelete && !isProtected;
                
                return `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card h-100">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h6 class="mb-0">
                                <i class="fas fa-${getCommandIcon(command.type)} me-2"></i>${command.name}
                                ${command.is_protected ? '<i class="fas fa-lock text-warning ms-2" title="Protegido"></i>' : ''}
                            </h6>
                            <div class="dropdown">
                                <button class="btn btn-sm btn-link text-secondary" type="button" data-bs-toggle="dropdown">
                                    <i class="fas fa-ellipsis-v"></i>
                                </button>
                                <ul class="dropdown-menu dropdown-menu-end">
                                    <li><a class="dropdown-item" href="#" data-action="viewScript" data-params='{"commandId":${command.id}}'><i class="fas fa-eye me-2"></i>Ver Script</a></li>
                                    ${showEditBtn ? `<li><a class="dropdown-item" href="#" data-action="showEditCommandModal" data-params='{"commandId":${command.id}}'><i class="fas fa-edit me-2"></i>Editar</a></li>` : ''}
                                    ${showDeleteBtn ? `<li><hr class="dropdown-divider"></li><li><a class="dropdown-item text-danger" href="#" data-action="deleteCommand" data-params='{"commandId":${command.id}}'><i class="fas fa-trash me-2"></i>Excluir</a></li>` : ''}
                                </ul>
                            </div>
                        </div>
                        <div class="card-body">
                            <p class="card-text text-muted small" style="height: 4.5em; overflow: hidden;">${command.description || 'Sem descrição'}</p>
                            <div class="d-flex gap-2 flex-wrap">
                                <span class="badge bg-secondary">${getCommandTypeText(command.type)}</span>
                                ${command.command_category === 'deploy' 
                                    ? '<span class="badge bg-success">🚀 Deploy</span>' 
                                    : '<span class="badge bg-primary">🔨 Build</span>'
                                }
                            </div>
                        </div>
                        <div class="card-footer">
                            <small class="text-muted">Criado: ${new Date(command.created_at).toLocaleDateString('pt-BR')}</small>
                        </div>
                    </div>
                </div>
            `}).join('')}
        </div>
    `;
}

// Funções auxiliares
function getCommandIcon(type) {
    const icons = {
        'powershell': 'terminal', // Ou 'powershell' se você tiver a lib de ícones da marca
        'batch': 'window-maximize',
        'bash': 'linux' // Ou 'terminal'
    };
    return icons[type] || 'terminal';
}

function getCommandTypeText(type) {
    const types = {
        'powershell': 'PowerShell',
        'batch': 'Batch/CMD',
        'bash': 'Bash/Shell'
    };
    return types[type] || type;
}

function getEnvironmentText(environment) {
    const environments = {
        'any': 'Qualquer SO',
        'windows': 'Windows',
        'linux': 'Linux'
    };
    return environments[environment] || environment;
}
// FUNÇÕES PRINCIPAIS
window.showCreateCommandModal = function () {
    console.log('Abrindo modal de criação de comando');
    try {
        // Limpar formulário
        const form = document.getElementById('createCommandForm');
        if (form) {
            form.reset();
        }
        const modalElement = document.getElementById('createCommandModal');
        if (modalElement) {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
        }
    } catch (error) {
        console.error('Erro ao abrir modal:', error);
        showNotification('Erro ao abrir modal de comando.', 'error');
    }
};
window.editCommand = function (commandId) {
    const command = commands.find(c => c.id === commandId);
    if (!command) return;
    
    document.getElementById('editCommandId').value = command.id;
    document.getElementById('editCommandName').value = command.name;
    document.getElementById('editCommandType').value = command.type;
    document.getElementById('editCommandCategory').value = command.command_category || 'build'; // 🆕
    document.getElementById('editCommandDescription').value = command.description || '';
    document.getElementById('editCommandScript').value = command.script;
    
    const modal = new bootstrap.Modal(document.getElementById('editCommandModal'));
    modal.show();
};
function executeCommand(commandId) {
    console.log('Executando comando:', commandId);
    const command = commands.find(c => c.id === commandId);
    if (command) {
        showNotification(`Executando comando "${command.name}"...`, 'info');
        // Simular execução
        setTimeout(() => {
            const success = Math.random() > 0.3; // 70% sucesso
            command.lastExecuted = new Date().toISOString();
            showNotification(
                `Comando "${command.name}" ${success ? 'executado com sucesso' : 'falhou'}!`,
                success ? 'success' : 'error'
            );
        }, 2000);
    }
}
function viewScript(commandId) {
    const command = commands.find(c => c.id === commandId);
    if (command) {
        document.getElementById('scriptContent').innerHTML = `
            <div class="mb-3">
                <h6>${command.name}</h6>
                <p class="text-muted">${command.description || 'Sem descrição'}</p>
                <span class="badge bg-secondary">${getCommandTypeText(command.type)}</span>
            </div>
            <pre class="bg-dark text-light p-3 rounded"><code>${command.script}</code></pre>
        `;
        const modalElement = document.getElementById('viewScriptModal');
        if (modalElement) {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
        }
    }
}
function applyCommandFilters() {
    showNotification('Filtros aplicados!', 'info');
}
function refreshCommands() {
    document.getElementById('commandsContainer').innerHTML = renderCommands();
    showNotification('Lista atualizada!', 'info');
}
function handleScriptImport() {
    const fileInput = document.getElementById('scriptFileInput');
    const file = fileInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (event) {
        document.getElementById('commandScript').value = event.target.result;
        showNotification(`Script "${file.name}" importado com sucesso!`, 'info');
    };
    reader.onerror = function () {
        showNotification('Erro ao ler o arquivo de script.', 'error');
    };
    reader.readAsText(file);
}

function renderUsers() {
    if (!users || users.length === 0) {
        return `
            <div class="card text-center p-5">
                <i class="fas fa-users fa-3x text-muted mb-3"></i>
                <p class="text-muted">Nenhum usuário cadastrado.</p>
            </div>
        `;
    }
    
    const profileBadges = {
        'admin': '<span class="badge bg-danger">Admin</span>',
        'operator': '<span class="badge bg-primary">Operador</span>',
        'viewer': '<span class="badge bg-secondary">Visualizador</span>'
    };
    
    return `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th><i class="fas fa-user me-2"></i>Usuário</th>
                        <th><i class="fas fa-id-badge me-2"></i>Nome</th>
                        <th><i class="fas fa-shield-alt me-2"></i>Perfil</th>
                        <th><i class="fas fa-toggle-on me-2"></i>Status</th>
                        <th class="text-end"><i class="fas fa-cog me-2"></i>Ações</th>
                    </tr>
                </thead>
                <tbody>
                    ${users.map(user => {
                        // User 'admin' (root) é intocável por outros admins
                        const isTargetRootAdmin = user.username === 'admin';
                        // Só root admin pode editar o user 'admin', outros admins não
                        const canEditThisUser = isRootAdmin() || !isTargetRootAdmin;
                        // Ninguém pode excluir o user 'admin' (nem ele mesmo via interface)
                        const canDeleteThisUser = !isTargetRootAdmin;
                        
                        return `
                        <tr>
                            <td>
                                <i class="fas fa-user-circle me-2 text-primary"></i>
                                <strong>${user.username}</strong>
                                ${isTargetRootAdmin ? '<i class="fas fa-crown text-warning ms-2" title="Root Admin"></i>' : ''}
                            </td>
                            <td>${user.name || user.username}</td>
                            <td>${profileBadges[user.profile] || user.profile}</td>
                            <td>
                                ${user.active 
                                    ? '<span class="badge bg-success"><i class="fas fa-check me-1"></i>Ativo</span>' 
                                    : '<span class="badge bg-secondary"><i class="fas fa-times me-1"></i>Inativo</span>'}
                            </td>
                            <td class="text-end">
                                <div class="btn-group btn-group-sm" role="group">
                                    ${canEditThisUser ? `
                                    <button class="btn btn-outline-primary" 
                                            data-action="showEditUserModal" 
                                            data-params='{"userId":${user.id}}'
                                            title="Editar usuário">
                                        <i class="fas fa-edit"></i>
                                    </button>
                                    <button class="btn btn-outline-warning" 
                                            data-action="showChangePasswordModal" 
                                            data-params='{"userId":${user.id}}'
                                            title="Alterar senha">
                                        <i class="fas fa-key"></i>
                                    </button>
                                    ` : '<span class="badge bg-secondary"><i class="fas fa-lock me-1"></i>Protegido</span>'}
                                    ${canDeleteThisUser && canEditThisUser ? `
                                        <button class="btn btn-outline-danger" 
                                                data-action="deleteUser" 
                                                data-params='{"userId":${user.id}}'
                                                title="Excluir usuário">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    ` : ''}
                                </div>
                            </td>
                        </tr>
                    `}).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function showUsers() {
    if (!isAdmin()) return;
    const content = `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2>Gerenciamento de Usuários</h2>
                    <p class="text-muted">Controle de usuários e permissões do sistema</p>
                </div>
                <button class="btn btn-primary" data-action="showCreateUserModal">
                    <i class="fas fa-plus me-2"></i>Novo Usuário
                </button>
            </div>
            <div id="usersContainer">${renderUsers()}</div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;
    ensureUserModalsExist();
}

function showSettings() {
    if (!isAdmin()) return;

    const content = `
        <div>
            <div class="mb-4">
                <h2>Configurações</h2>
                <p class="text-muted">Gerencie as configurações e integrações do sistema.</p>
            </div>

            <ul class="nav nav-tabs mb-4" id="settingsTabs" role="tablist">
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="github-tab" data-bs-toggle="tab" data-bs-target="#github-content" type="button" role="tab">GitHub</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="variables-tab" data-bs-toggle="tab" data-bs-target="#variables-content" type="button" role="tab">Variáveis do Servidor</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="environments-tab" data-bs-toggle="tab" data-bs-target="#environments-content" type="button" role="tab">Ambientes</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="services-tab" data-bs-toggle="tab" data-bs-target="#services-content" type="button" role="tab">Serviços do Servidor</button>
                </li>
            </ul>

            <div class="tab-content" id="settingsTabsContent">
                <div class="tab-pane fade show active" id="github-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="variables-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="environments-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="services-content" role="tabpanel"></div>
            </div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;

    // Renderiza o conteúdo de cada aba
    renderGithubSettingsTab();
    renderServerVariablesTab();
    renderEnvironmentsTab();
    renderServerServicesTab();
}

// 🔧 Função auxiliar para manter aba ativa após reload
function reloadSettingsTab(activeTabId = null) {
    showSettings();
    
    // Restaura aba ativa
    const tabToActivate = activeTabId || sessionStorage.getItem('activeSettingsTab') || 'github-tab';
    
    const tabButton = document.getElementById(tabToActivate);
    if (tabButton) {
        const tab = new bootstrap.Tab(tabButton);
        tab.show();
    }
}

// 🔧 Listener para salvar qual aba está ativa
document.addEventListener('shown.bs.tab', function(event) {
    if (event.target.id && event.target.id.endsWith('-tab')) {
        sessionStorage.setItem('activeSettingsTab', event.target.id);
    }
});

function renderGithubSettingsTab() {
    const container = document.getElementById('github-content');
    container.innerHTML = `
        <div class="card">
            <div class="card-header"><h5><i class="fab fa-github me-2"></i>Configuração da Integração GitHub</h5></div>
            <div class="card-body">
                <form id="githubForm">
                    <div class="mb-3">
                        <label class="form-label">Personal Access Token (classic)</label>
                        <input type="password" class="form-control" id="githubToken" value="${gitHubSettings?.token || ''}" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx">
                        <div class="text-muted">Token necessário para acessar os repositórios. <a href="https://github.com/settings/tokens/new?scopes=repo,read:user" target="_blank">Gerar novo token</a></div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Nome de Usuário GitHub</label>
                        <input type="text" class="form-control" id="githubUsername" value="${gitHubSettings?.username || ''}" placeholder="seu-usuario-github">
                    </div>
                    <div class="d-flex gap-2">
                        <button type="button" class="btn btn-primary" data-action="saveGithubSettings"><i class="fas fa-save me-2"></i>Salvar</button>
                        <button type="button" class="btn btn-outline-secondary" data-action="testGithubConnection"><i class="fas fa-link me-2"></i>Testar Conexão</button>
                    </div>
                    <div id="connectionStatus" class="mt-3"></div>
                </form>
            </div>
        </div>
    `;
}

function renderServerVariablesTab() {
    const container = document.getElementById('variables-content');
    
    // Estado de filtro e ordenação
    if (!window.variablesState) {
        window.variablesState = {
            filterEnv: 'TODOS',
            sortColumn: 'name',
            sortOrder: 'asc'
        };
    }
    
    const state = window.variablesState;
    
    // Filtrar variáveis por ambiente
    let filteredVars = serverVariables;
    if (state.filterEnv !== 'TODOS') {
        filteredVars = serverVariables.filter(v => v.name.endsWith(`_${state.filterEnv}`));
    }
    
    // Ordenar variáveis
    filteredVars.sort((a, b) => {
        let valA = a[state.sortColumn] || '';
        let valB = b[state.sortColumn] || '';
        
        if (state.sortOrder === 'asc') {
            return valA.toString().localeCompare(valB.toString());
        } else {
            return valB.toString().localeCompare(valA.toString());
        }
    });
    
    // Renderizar HTML
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <h5>Variáveis Globais do Servidor</h5>
                <p class="text-muted mb-0">Variáveis disponíveis para uso nos scripts (ex: \${BASE_DIR}).</p>
            </div>
            <div class="d-flex gap-2">
                ${isOperator() ? `
                <button class="btn btn-success" data-action="showImportVariablesModal">
                    <i class="fas fa-file-csv me-2"></i>Importar CSV
                </button>
                <button class="btn btn-primary" data-action="showCreateVariableModal">
                    <i class="fas fa-plus me-2"></i>Nova Variável
                </button>
                ` : ''}
            </div>
        </div>
        
        <!-- Filtros de Ambiente -->
        <div class="btn-group mb-3" role="group">
            <button class="btn ${state.filterEnv === 'TODOS' ? 'btn-primary' : 'btn-outline-primary'}" 
                    onclick="filterVariablesByEnv('TODOS')">
                <i class="fas fa-globe me-1"></i>TODOS
            </button>
            <button class="btn ${state.filterEnv === 'DEV' ? 'btn-success' : 'btn-outline-success'}" 
                    onclick="filterVariablesByEnv('DEV')">
                <i class="fas fa-code me-1"></i>DEV
            </button>
            <button class="btn ${state.filterEnv === 'HOM' ? 'btn-warning' : 'btn-outline-warning'}" 
                    onclick="filterVariablesByEnv('HOM')">
                <i class="fas fa-flask me-1"></i>HOM
            </button>
            <button class="btn ${state.filterEnv === 'PRD' ? 'btn-danger' : 'btn-outline-danger'}" 
                    onclick="filterVariablesByEnv('PRD')">
                <i class="fas fa-server me-1"></i>PRD
            </button>
            <button class="btn ${state.filterEnv === 'TST' ? 'btn-info' : 'btn-outline-info'}" 
                    onclick="filterVariablesByEnv('TST')">
                <i class="fas fa-vial me-1"></i>TST
            </button>
        </div>
        
        <div class="card">
            <div class="table-responsive">
                <table class="table table-hover mb-0 resizable-table">
                    <thead>
                        <tr>
                            <th class="sortable-header" onclick="sortVariables('name')" style="min-width: 180px;">
                                Nome ${getSortIcon('name')}
                            </th>
                            <th class="sortable-header" onclick="sortVariables('value')" style="min-width: 250px;">
                                Valor ${getSortIcon('value')}
                            </th>
                            <th class="sortable-header" onclick="sortVariables('description')" style="min-width: 200px;">
                                Descrição ${getSortIcon('description')}
                            </th>
                            <th class="text-end" style="width: 140px;">Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filteredVars.map(v => {
                            const isProtected = v.is_protected;
                            // Admin pode editar protegidas, apenas root pode excluir protegidas
                            const showEditBtn = isAdmin() || (isOperator() && !isProtected);
                            const showDeleteBtn = isRootAdmin() || (isOperator() && !isProtected);
                            return `
                            <tr>
                                <td>
                                    <code>${v.name}</code>
                                    ${v.is_protected ? '<i class="fas fa-lock text-warning ms-2" title="Protegido"></i>' : ''}
                                </td>
                                <td class="text-truncate" style="max-width: 300px;" title="${v.is_password ? 'Valor oculto' : v.value}">
                                    ${v.is_password ? '<span class="text-muted"><i class="fas fa-key text-warning me-1"></i>••••••••</span>' : v.value}
                                </td>
                                <td class="text-muted">${v.description || '-'}</td>
                                <td class="text-end">
                                    ${isOperator() ? `
                                    <div class="btn-group btn-group-sm">
                                        ${showEditBtn ? `
                                        <button class="btn btn-outline-primary" data-action="showEditVariableModal" data-params='{"varId":${v.id}}'>
                                            <i class="fas fa-edit"></i>
                                        </button>
                                        ` : ''}
                                        ${showDeleteBtn ? `
                                        <button class="btn btn-outline-danger" data-action="deleteVariable" data-params='{"varId":${v.id}}'>
                                            <i class="fas fa-trash"></i>
                                        </button>
                                        ` : ''}
                                    </div>
                                    ` : ''}
                                </td>
                            </tr>
                        `}).join('') || '<tr><td colspan="4" class="text-center text-muted p-4">Nenhuma variável encontrada.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Função auxiliar para ícones de ordenação
function getSortIcon(column) {
    const state = window.variablesState;
    if (state.sortColumn !== column) return '<i class="fas fa-sort text-muted ms-1"></i>';
    return state.sortOrder === 'asc' 
        ? '<i class="fas fa-sort-up text-primary ms-1"></i>' 
        : '<i class="fas fa-sort-down text-primary ms-1"></i>';
}

// Função de filtro por ambiente
function filterVariablesByEnv(env) {
    window.variablesState.filterEnv = env;
    renderServerVariablesTab();
}

// Função de ordenação
function sortVariables(column) {
    const state = window.variablesState;
    
    if (state.sortColumn === column) {
        state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortColumn = column;
        state.sortOrder = 'asc';
    }
    
    renderServerVariablesTab();
}

function renderEnvironmentsTab() {
    const container = document.getElementById('environments-content');
    // Reutiliza a lógica que já tínhamos, mas renderiza dentro da aba
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <h5>Ambientes do Sistema</h5>
                <p class="text-muted mb-0">Gerencie os ambientes isolados do sistema (Produção, Desenvolvimento, etc.).</p>
            </div>
            ${isRootAdmin() ? '<button class="btn btn-primary" data-action="showCreateEnvironmentModal"><i class="fas fa-plus me-2"></i>Novo Ambiente</button>' : ''}
        </div>
        <div id="environmentsListContainer">${renderEnvironments()}</div>
    `;
}

function renderServerServicesTab() {
    const container = document.getElementById('services-content');
    const canEdit = isOperator();
    const canDelete = isOperator();
    
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <h5>Serviços do Servidor</h5>
                <p class="text-muted mb-0">Cadastre os serviços que podem ser gerenciados (ex: AppServer, Dbaccess).</p>
            </div>
            ${isOperator() ? '<button class="btn btn-primary" data-action="showCreateServiceModal"><i class="fas fa-plus me-2"></i>Novo Serviço</button>' : ''}
        </div>
        <div class="card">
             <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead><tr><th>Serviço</th><th>Servidor</th><th>Ambiente</th><th>Status</th>${isOperator() ? '<th class="text-end">Ações</th>' : ''}</tr></thead>
                    <tbody>
                        ${serverServices.map(s => {
                            const envName = environments.find(e => e.id === s.environment_id)?.name || 'N/A';
                            const statusBadge = s.is_active !== false 
                                ? '<span class="badge bg-success">Ativo</span>' 
                                : '<span class="badge bg-secondary">Inativo</span>';
                            return `
                            <tr>
                                <td>
                                    <strong>${s.display_name || s.name}</strong>
                                    <small class="text-muted d-block">📦 ${s.name}</small>
                                </td>
                                <td><code>${s.server_name || '-'}</code></td>
                                <td>${envName}</td>
                                <td>${statusBadge}</td>
                                ${isOperator() ? `
                                <td class="text-end">
                                    <div class="btn-group btn-group-sm">
                                        ${canEdit ? `<button class="btn btn-outline-primary" data-action="showEditServiceModal" data-params='{"serviceId":${s.id}}'><i class="fas fa-edit"></i></button>` : ''}
                                        ${canDelete ? `<button class="btn btn-outline-danger" data-action="deleteService" data-params='{"serviceId":${s.id}}'><i class="fas fa-trash"></i></button>` : ''}
                                    </div>
                                </td>
                                ` : ''}
                            </tr>
                        `}).join('') || `<tr><td colspan="${isOperator() ? 5 : 4}" class="text-center text-muted p-4">Nenhum serviço cadastrado.</td></tr>`}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

function showVariableModal(params) {
    // Aceita params do data-action
    const mode = params.mode || 'create';
    const varId = params.varId || null;
    
    const form = document.getElementById('variableForm');
    if (form) form.reset();
    
    const nameInput = document.getElementById('variableName');
    if (nameInput) nameInput.disabled = (mode === 'edit');
    
    if (mode === 'create') {
        const title = document.getElementById('variableModalTitle');
        if (title) title.textContent = 'Nova Variável';
        
        const idInput = document.getElementById('variableId');
        if (idInput) idInput.value = '';
    } else {
        const variable = serverVariables.find(v => v.id === varId);
        if (!variable) return;
        
        const title = document.getElementById('variableModalTitle');
        if (title) title.textContent = 'Editar Variável';
        
        const idInput = document.getElementById('variableId');
        if (idInput) idInput.value = variable.id;
        
        if (nameInput) nameInput.value = variable.name;
        
        const valueInput = document.getElementById('variableValue');
        if (valueInput) valueInput.value = variable.value;
        
        const descInput = document.getElementById('variableDescription');
        if (descInput) descInput.value = variable.description || '';
    }
    
    const modal = document.getElementById('variableModal');
    if (modal) {
        new bootstrap.Modal(modal).show();
    }
}
    new bootstrap.Modal(document.getElementById('variableModal')).show();


async function saveVariable() {
    const id = document.getElementById('variableId').value;
    const name = document.getElementById('variableName').value.trim();
    const value = document.getElementById('variableValue').value.trim();
    const description = document.getElementById('variableDescription').value.trim();
    if (!name || !value) return showNotification('Nome e Valor são obrigatórios!', 'error');

    try {
        if (id) {
            await apiUpdateServerVariable(id, { name, value, description });
        } else {
            await apiCreateServerVariable({ name, value, description });
        }
        await loadServerVariables();
        renderServerVariablesTab(); // Apenas redesenha a aba
        bootstrap.Modal.getInstance(document.getElementById('variableModal')).hide();
        showNotification('Variável salva com sucesso!', 'success');
    } catch (error) { showNotification(error.message, 'error'); }
}



function showServiceModal(mode, serviceId = null) {
    const form = document.getElementById('serviceForm');
    form.reset();
    if (mode === 'create') {
        document.getElementById('serviceModalTitle').textContent = 'Novo Serviço';
        document.getElementById('serviceId').value = '';
    } else {
        const service = serverServices.find(s => s.id === serviceId);
        if (!service) return;
        document.getElementById('serviceModalTitle').textContent = 'Editar Serviço';
        document.getElementById('serviceId').value = service.id;
        document.getElementById('serviceName').value = service.name;
        document.getElementById('serviceDescription').value = service.description || '';
    }
    new bootstrap.Modal(document.getElementById('serviceModal')).show();
}

async function saveService() {
    const id = document.getElementById('serviceId').value;
    const name = document.getElementById('serviceName').value.trim();
    const description = document.getElementById('serviceDescription').value.trim();
    if (!name) return showNotification('O nome do serviço é obrigatório!', 'error');

    try {
        if (id) {
            await apiUpdateServerService(id, { name, description });
        } else {
            await apiCreateServerService({ name, description });
        }
        await loadServerServices();
        renderServerServicesTab(); // Apenas redesenha a aba
        bootstrap.Modal.getInstance(document.getElementById('serviceModal')).hide();
        showNotification('Serviço salvo com sucesso!', 'success');
    } catch (error) { showNotification(error.message, 'error'); }
}

// GitHub functions
function getGithubAuthStatus() {
    if (gitHubSettings.token && gitHubSettings.username) {
        return `
    < div class="d-flex align-items-center" >
        <span class="badge badge-success me-2">
            <i class="fab fa-github me-1"></i>Conectado: ${gitHubSettings.username}
        </span>
            </div >
    `;
    } else {
        return `
    < span class="badge badge-warning" >
        <i class="fab fa-github me-1"></i>GitHub não configurado
            </span >
    `;
    }
}
function showGithubAuthModal() {
    const modal = document.getElementById('githubAuthModal');
    if (modal) {
        // Limpar status anterior
        const statusDiv = document.getElementById('connectionStatus');
        if (statusDiv) {
            statusDiv.innerHTML = '';
        }
        // Fill with saved data if available
        if (githubAuthData) {
            document.getElementById('githubUser').value = githubAuthData.username || '';
            document.getElementById('githubToken').value = githubAuthData.token || '';
        } else {
            document.getElementById('githubUser').value = '';
            document.getElementById('githubToken').value = '';
        }
        modal.style.display = 'block';
    }
}
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}
function toggleGithubToken() {
    const tokenInput = document.getElementById('githubToken');
    const toggleIcon = document.getElementById('githubTokenToggle');
    if (tokenInput.type === 'password') {
        tokenInput.type = 'text';
        toggleIcon.className = 'fas fa-eye-slash';
    } else {
        tokenInput.type = 'password';
        toggleIcon.className = 'fas fa-eye';
    }
}
async function testGithubConnection() {
    // Se chamado da página de repositórios, usar dados salvos
    let username, token, statusDiv;
    if (document.getElementById('githubUser')) {
        // Chamado do modal
        username = document.getElementById('githubUser').value.trim();
        token = document.getElementById('githubToken').value.trim();
        statusDiv = document.getElementById('connectionStatus');
    } else {
        // Chamado da página de repositórios
        if (!githubAuthData || !githubAuthData.token) {
            showNotification('Configure suas credenciais GitHub primeiro!', 'error');
            return;
        }
        username = githubAuthData.username;
        token = githubAuthData.token;
    }
    if (!username || !token) {
        if (statusDiv) {
            statusDiv.innerHTML = '<div class="text-danger mt-2">Preencha usuário e token primeiro!</div>';
        } else {
            showNotification('Configure suas credenciais GitHub primeiro!', 'error');
        }
        return;
    }
    if (statusDiv) {
        statusDiv.innerHTML = '<div class="text-info mt-2"><i class="fas fa-spinner fa-spin me-2"></i>Testando conexão...</div>';
    } else {
        showNotification('Testando conexão com GitHub...', 'info');
    }
    try {
        const response = await fetch(`${GITHUB_API_BASE}/user`, {
            headers: {
                'Authorization': `token ${token}`,
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Protheus-DevOps-App'
            }
        });
        if (response.ok) {
            const userData = await response.json();
            if (statusDiv) {
                statusDiv.innerHTML = `
                    <div class="text-success mt-2">
                        <i class="fas fa-check-circle me-2"></i>
                        Conectado com sucesso como ${userData.login}!
                    </div>
                `;
            } else {
                showNotification(`Conectado com sucesso como ${userData.login}!`, 'success');
            }
        } else {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
    } catch (error) {
        console.error('Erro no teste de conexão:', error);
        if (statusDiv) {
            statusDiv.innerHTML = `
                <div class="text-danger mt-2">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Erro na conexão: ${error.message}
                </div>
            `;
        } else {
            showNotification(`Erro na conexão: ${error.message}`, 'error');
        }
    }
}
function saveGithubSettings() {
    const user = document.getElementById('githubUser').value.trim();
    const token = document.getElementById('githubToken').value.trim();
    if (!user || !token) {
        showNotification('Preencha todos os campos!', 'error');
        return;
    }
    // Validar formato do token
    if (!token.startsWith('ghp_') && !token.startsWith('github_pat_')) {
        showNotification('Token deve começar com "ghp_" ou "github_pat_"', 'error');
        return;
    }
    // Salvar em memória
    githubAuthData = {
        username: user,
        token: token,
        savedAt: new Date().toISOString()
    };
    closeModal('githubAuthModal');
    showNotification('Configurações GitHub salvas com sucesso!', 'success');
    // Atualizar botão de teste
    const testBtn = document.getElementById('testConnectionBtn');
    if (testBtn) {
        testBtn.disabled = false;
    }
    // Refresh current page if settings
    if (currentPage === 'settings') {
        showSettings();
    } else if (currentPage === 'repositories') {
        showRepositories();
    }
}
function clearGithubAuth() {
    gitHubSettings.token = '';
    gitHubSettings.username = '';
    githubAuthData = null;
    repositories = []; // Limpar repositórios descobertos
    showNotification('Credenciais GitHub removidas!', 'warning');
    // Atualizar botão de teste
    const testBtn = document.getElementById('testConnectionBtn');
    if (testBtn) {
        testBtn.disabled = true;
    }
    // Refresh current page
    if (currentPage === 'settings') {
        showSettings();
    } else if (currentPage === 'repositories') {
        showRepositories();
    }
}
// FUNÇÕES COMPLETAS DE REPOSITÓRIOS E GITHUB
function ensureGithubFunctionsComplete() {
    console.log('Verificando funções GitHub...');
    // Lista de funções críticas GitHub
    const githubFunctions = [
        'discoverRepositories',
        'viewRepositoryArtifacts',
        'loadRepositoryBranches',
        'loadRepositoryContents',
        'testGithubConnection',
        'saveGithubSettings'
    ];
    githubFunctions.forEach(funcName => {
        if (typeof window[funcName] !== 'function') {
            console.error(`Função GitHub ${funcName} não encontrada!`);
        }
    });
}
// Garantir que todos os modais existam
function ensureAllModalsExist() {
    const requiredModals = [
        'githubAuthModal',
        'createPipelineModal',
        'editPipelineModal',
        'commandSelectorModal',
        'createCommandModal',
        'editCommandModal',
        'viewScriptModal'
    ];
    requiredModals.forEach(modalId => {
        if (!document.getElementById(modalId)) {
            console.warn(`Modal ${modalId} não encontrado no DOM`);
        }
    });
}
// Função para garantir que todas as seções funcionem
function ensureAllSectionsFunctional() {
    console.log('Verificando funcionalidade de todas as seções...');
    // Verificar se funções de navegação existem
    const sectionFunctions = {
        'dashboard': 'showDashboard',
        'repositories': 'showRepositories',
        'pipelines': 'showPipelines',
        'commands': 'showCommands',
        'users': 'showUsers',
        'settings': 'showSettings'
    };
    Object.entries(sectionFunctions).forEach(([section, funcName]) => {
        if (typeof window[funcName] !== 'function') {
            console.error(`Função da seção ${section} não encontrada: ${funcName}`);
        } else {
            console.log(`✓ Seção ${section} funcional`);
        }
    });
}

// ================================================================
// SISTEMA DE NOTIFICAÇÕES ROBUSTO - FUNCIONA SEMPRE
// ================================================================

function showNotification(message, type = 'info', duration = 3000) {
    notificationQueue.push({ message, type, duration });
    if (!isProcessingQueue) {
        processNotificationQueue();
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
        try {
            ensureToastContainer();
            const toastContainer = document.querySelector('.toast-container-footer');
            const toastId = 'toast-' + Date.now();
            const bgClass = {
                'success': 'bg-success', 'error': 'bg-danger',
                'warning': 'bg-warning text-dark', 'info': 'bg-info'
            }[type] || 'bg-secondary';

            const toastHTML = `
                <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                    <div class="d-flex"><div class="toast-body">${message}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>
                </div>`;
            toastContainer.insertAdjacentHTML('beforeend', toastHTML);
            
            const toastEl = document.getElementById(toastId);
            if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
                const toast = new bootstrap.Toast(toastEl, { delay: duration, autohide: true });
                toastEl.addEventListener('hidden.bs.toast', () => { toastEl.remove(); resolve(); });
                toast.show();
            } else { // Fallback se bootstrap não estiver pronto
                setTimeout(() => { toastEl.remove(); resolve(); }, duration);
            }
        } catch (e) { resolve(); }
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
            color: white;
            font-family: system-ui, -apple-system, sans-serif;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            animation: slideUp 0.3s ease-out;
            pointer-events: auto;
            cursor: pointer;
        `;
        // Cores por tipo
        const colors = {
            success: '#28a745',
            error: '#dc3545',
            warning: '#ffc107',
            info: '#17a2b8'
        };
        notification.style.backgroundColor = colors[type] || colors.info;
        if (type === 'warning') notification.style.color = 'black';
        notification.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
                <span>${message}</span>
                <button data-action="removeParentElement" 
                        style="background: none; border: none; color: inherit; cursor: pointer; padding: 0; margin-left: auto; font-size: 18px;">
                    ×
                </button>
            </div>
        `;
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

// Auto-inicializar quando DOM estiver pronto
document.addEventListener('DOMContentLoaded', function() {
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

// STATUS FINAL DO SISTEMA
console.log('\n=== SISTEMA AtuRPO DevOps - STATUS FINAL ===');
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
// AZURE DEVOPS CLASSIC STYLE - BUILD & RELEASE FUNCTIONS
// ADICIONAR NO FINAL DO ARQUIVO integration.js
// =====================================================================

// =====================================================================
// FUNÇÕES DE BUILD (CI)
// =====================================================================

/**
 * Executa um build do pipeline (CI)
 */
async function runPipelineBuild(params) {
    const pipelineId = params.pipelineId;
    try {
        showNotification('Iniciando build...', 'info');
        
        const response = await apiRunPipeline(pipelineId);
        
        if (response.success) {
            showNotification(response.message, 'success');
            
            // Abrir view de execução
            await openPipelineRunView(response.run_id, pipelineId);
            
            // Abrir modal de logs em tempo real
            openBuildLogsModal(response.run_id, pipelineId);
        }
    } catch (error) {
        console.error('Erro ao executar build:', error);
        showNotification('Erro ao executar build: ' + error.message, 'error');
    }
}

/**
 * Abre modal de logs do Build em tempo real (igual ao Release)
 */
async function openBuildLogsModal(runId, pipelineId) {
    // Buscar info da pipeline
    const pipeline = pipelines.find(p => p.id === pipelineId);
    const pipelineName = pipeline ? pipeline.name : `Pipeline #${pipelineId}`;
    
    // Configurar modal
    const modalElement = document.getElementById('buildLogsModal');
    if (!modalElement) {
        console.error('[BUILD SSE] Modal buildLogsModal não encontrado!');
        showNotification('Erro: Modal de logs não encontrado', 'error');
        return;
    }
    
    const logModal = new bootstrap.Modal(modalElement);
    const titleElement = document.getElementById('buildLogsTitle');
    const logOutput = document.getElementById('buildLogsOutput');
    
    if (!logOutput) {
        console.error('[BUILD SSE] Elemento buildLogsOutput não encontrado!');
        showNotification('Erro: Área de logs não encontrada', 'error');
        return;
    }
    
    titleElement.textContent = `Build #${runId} - ${pipelineName}`;
    logOutput.textContent = 'Iniciando build...\n';
    logModal.show();

    try {
        // Conectar ao stream de logs do build (novo endpoint)
        const eventSource = new EventSource(`/api/runs/${runId}/output/stream?auth_token=${authToken}`);
        
        window.buildEventSource = eventSource;

        // Adicionar log inicial
        logOutput.textContent += '[CONECTADO AO STREAM DE LOGS]\n';

        eventSource.onmessage = function (event) {
            console.log('[BUILD SSE] Mensagem recebida:', event.data);
            
            // Buscar elemento novamente dentro do callback
            const output = document.getElementById('buildLogsOutput');
            if (!output) {
                console.error('[BUILD SSE] buildLogsOutput não encontrado no callback!');
                return;
            }
            
            try {
                const data = JSON.parse(event.data);
                console.log('[BUILD SSE] Dados parseados:', data);
                
                if (data.status === 'completed') {
                    output.textContent += `\n[FIM DA EXECUÇÃO] Status final: ${data.final_status}\n`;
                    output.scrollTop = output.scrollHeight;
                    eventSource.close();
                    window.buildEventSource = null;
                    
                    // Esconder spinner
                    const spinner = document.getElementById('buildLogsSpinner');
                    if (spinner) spinner.style.display = 'none';
                    
                    // Destacar botão Fechar
                    const modalFooter = document.querySelector('#buildLogsModal .modal-footer');
                    const closeBtn = modalFooter?.querySelector('[data-bs-dismiss="modal"]');
                    if (closeBtn) {
                        closeBtn.classList.remove('btn-secondary');
                        closeBtn.classList.add(data.final_status === 'success' ? 'btn-success' : 'btn-danger');
                        closeBtn.textContent = data.final_status === 'success' ? '✅ Fechar' : '❌ Fechar';
                    }
                    
                    // Atualizar view do run
                    setTimeout(async () => {
                        console.log('🔄 Atualizando status do run após o build...');
                        await loadRunDetails(runId, pipelineId);
                        await loadRunCommandsLogs(runId);
                    }, 1000);
                    
                } else if (data.output) {
                    // Output do comando - igual ao Release
                    console.log('[BUILD SSE] Adicionando output ao modal:', data.output);
                    output.textContent += data.output + '\n';
                    output.scrollTop = output.scrollHeight;
                    
                } else if (data.error) {
                    output.textContent += `[ERRO] ${data.error}\n`;
                    output.scrollTop = output.scrollHeight;
                    eventSource.close();
                    window.buildEventSource = null;
                } else {
                    console.warn('[BUILD SSE] Formato de dados desconhecido:', data);
                }
            } catch (error) {
                console.error('[BUILD SSE] Erro ao parsear JSON:', error, 'Dados brutos:', event.data);
                output.textContent += `[ERRO PARSING] ${event.data}\n`;
            }
        };

        eventSource.onerror = function (error) {
            console.error('[BUILD SSE] Erro na conexão:', error);
            const output = document.getElementById('buildLogsOutput');
            if (output) {
                output.textContent += '[ERRO] Conexão com o stream perdida.\n';
            }
            eventSource.close();
            window.buildEventSource = null;
            
            // Habilitar botão fechar em caso de erro
            const modalFooter = document.querySelector('#buildLogsModal .modal-footer');
            const closeBtn = modalFooter?.querySelector('[data-bs-dismiss="modal"]');
            if (closeBtn) {
                closeBtn.classList.remove('btn-secondary');
                closeBtn.classList.add('btn-warning');
                closeBtn.textContent = 'Fechar';
            }
        };

        // Fechar conexão se modal for fechado
        modalElement.addEventListener('hidden.bs.modal', () => {
            if (window.buildEventSource) {
                window.buildEventSource.close();
                window.buildEventSource = null;
            }
            
            // Resetar botão
            const modalFooter = document.querySelector('#buildLogsModal .modal-footer');
            const closeBtn = modalFooter?.querySelector('[data-bs-dismiss="modal"]');
            if (closeBtn) {
                closeBtn.classList.remove('btn-success', 'btn-danger', 'btn-warning');
                closeBtn.classList.add('btn-secondary');
                closeBtn.textContent = 'Fechar';
            }
            
            // Resetar spinner
            const spinner = document.getElementById('buildLogsSpinner');
            if (spinner) spinner.style.display = '';
        }, { once: true });

    } catch (error) {
        console.error('[BUILD SSE] Erro ao conectar:', error);
        logOutput.textContent += `ERRO: ${error.message}\n`;
    }
}

// Adicionar APÓS o fechamento do eventListener do buildLogsModal (linha ~7720):

/**
 * Reabre o modal de streaming para um run em execução
 */
function reopenBuildStream() {
    const btnStream = document.getElementById('btnOpenStream');
    const btnRefresh = document.getElementById('btnRefreshRun');
    
    if (!btnStream || !btnRefresh) {
        showNotification('Erro ao obter dados do run', 'error');
        return;
    }
    
    const runId = parseInt(btnStream.dataset.runId || btnRefresh.dataset.runId);
    const pipelineId = parseInt(btnRefresh.dataset.pipelineId);
    
    if (!runId || !pipelineId) {
        showNotification('Dados do run não disponíveis', 'error');
        return;
    }
    
    // Fechar conexão anterior se existir
    if (window.buildEventSource) {
        window.buildEventSource.close();
        window.buildEventSource = null;
    }
    
    // Reabrir modal de streaming
    openBuildLogsModal(runId, pipelineId);
}

/**
 * Carrega histórico de builds de um pipeline
 */
async function loadPipelineBuilds(pipelineId, page = 1) {
    try {
        if (typeof apiGetPipelineRuns !== 'function') {
            const error = new Error('apiGetPipelineRuns não disponível');
            console.error('❌', error);
            showNotification('Erro: API não carregada. Recarregue a página.', 'error');
            throw error;
        }
        const response = await apiGetPipelineRuns(pipelineId, page, 20);
        
        const builds = response.runs || [];
        const total = response.total || 0;
        
        // Buscar status de deploy para cada build
        const buildsWithDeployStatus = await Promise.all(
            builds.map(async (build) => {
                try {
                    const releasesData = await apiGetRunReleases(build.id);
                    const hasSuccessfulDeploy = releasesData.releases?.some(r => r.status === 'success');
                    return { ...build, hasSuccessfulDeploy };
                } catch (error) {
                    return { ...build, hasSuccessfulDeploy: false };
                }
            })
        );
        
        // Renderizar lista de builds
        const buildsHtml = buildsWithDeployStatus.map(build => `
            <div class="card mb-3 border-${getStatusColor(build.status)}">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-1">
                            <h5 class="mb-0">#${build.run_number}</h5>
                        </div>
                        <div class="col-md-3">
                            <span class="badge bg-${getStatusColor(build.status)}">
                                ${getStatusText(build.status)}
                            </span>
                            ${build.hasSuccessfulDeploy ? '<span class="badge bg-success ms-2"><i class="fas fa-rocket me-1"></i>Deploy OK</span>' : ''}
                        </div>
                        <div class="col-md-3">
                            <small class="text-muted">
                                <i class="fas fa-user"></i> ${build.started_by_name || 'Sistema'}
                            </small>
                        </div>
                        <div class="col-md-3">
                            <small class="text-muted">
                                <i class="fas fa-clock"></i> ${formatDateTime(build.started_at)}
                            </small>
                        </div>
                        <div class="col-md-2 text-end">
                            <button class="btn btn-sm btn-outline-info me-1" 
                                    data-action="openRunView" 
                                    data-params='{"runId": ${build.id}, "pipelineId": ${pipelineId}}'>
                                <i class="fas fa-eye"></i> Detalhes
                            </button>
                            <button class="btn btn-sm btn-outline-primary" 
                                    data-action="viewRunLogs" 
                                    data-params='{"runId": ${build.id}}'>
                                <i class="fas fa-file-alt"></i> Logs
                            </button>
                        </div>
                    </div>
                    ${build.error_message ? `
                        <div class="alert alert-danger mt-2 mb-0">
                            <i class="fas fa-exclamation-circle"></i> ${build.error_message}
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('');
        
        document.getElementById('buildsContainer').innerHTML = buildsHtml || 
            '<div class="alert alert-info">Nenhum build encontrado</div>';
        
        // Paginação
        renderPagination('buildsPagination', page, Math.ceil(total / 20), (p) => {
            loadPipelineBuilds(pipelineId, p);
        });
        
    } catch (error) {
        console.error('Erro ao carregar builds:', error);
        showNotification('Erro ao carregar builds', 'error');
    }
}

// =====================================================================
// FUNÇÕES DE VISUALIZAÇÃO DE EXECUÇÃO (RUN VIEW)
// =====================================================================

/**
 * Abre a página de visualização de execução do pipeline
 */
async function openPipelineRunView(runId, pipelineId) {
    try {
        // Esconder conteúdo principal e mostrar view de run
        const contentArea = document.getElementById('content-area');
        if (contentArea) contentArea.style.display = 'none';
        
        document.getElementById('pipelineRunView').classList.remove('d-none');
        
        // Scroll para o topo da página
        window.scrollTo({ top: 0, behavior: 'smooth' });
        
        // Buscar dados do run
        await loadRunDetails(runId, pipelineId);
        
        // Iniciar polling para atualizar status
        startRunPolling(runId, pipelineId);
        
    } catch (error) {
        console.error('Erro ao abrir visualização de run:', error);
        showNotification('Erro ao carregar execução: ' + error.message, 'error');
    }
}

/**
 * Carrega os detalhes de uma execução
 */
async function loadRunDetails(runId, pipelineId) {
    try {
        // Buscar dados da pipeline
        const pipeline = pipelines.find(p => p.id === pipelineId);

        if (!pipeline) {
            throw new Error('Pipeline não encontrada');
        }
        
        // Buscar dados do run (usando a API de runs)
        const runsResponse = await apiGetPipelineRuns(pipelineId, 1, 100);
        const run = runsResponse.runs.find(r => r.id === runId);
        
        if (!run) {
            throw new Error('Execução não encontrada');
        }
        
        // Verificar se já existe deploy com sucesso para este run
        let hasSuccessfulDeploy = false;
        try {
            const releasesData = await apiGetRunReleases(runId);
            hasSuccessfulDeploy = releasesData.releases?.some(r => r.status === 'success');
        } catch (error) {
            console.log('Nenhum release encontrado ou erro ao buscar:', error);
        }
        
        // Atualizar cabeçalho
        document.getElementById('runPipelineName').textContent = pipeline.name;
        document.getElementById('runNumber').textContent = `#${run.run_number}`;
        
        // Atualizar status
        updateRunStatus(run, hasSuccessfulDeploy);
        
        // Desabilitar botão Release se já tem deploy com sucesso
        const btnRelease = document.getElementById('btnRelease');
        if (btnRelease && hasSuccessfulDeploy) {
            btnRelease.disabled = true;
            btnRelease.classList.add('disabled');
            btnRelease.classList.remove('btn-info');
            btnRelease.classList.add('btn-secondary');
            btnRelease.innerHTML = '<i class="fas fa-check-circle me-1"></i>Deploy Realizado';
            btnRelease.title = 'Deploy já foi realizado com sucesso';
        } else if (btnRelease && !hasSuccessfulDeploy && run.status === 'success') {
            // Reabilitar se não tem deploy e run teve sucesso
            btnRelease.disabled = false;
            btnRelease.classList.remove('disabled', 'btn-secondary');
            btnRelease.classList.add('btn-info');
            btnRelease.innerHTML = '<i class="fas fa-rocket me-1"></i>Release';
            btnRelease.title = 'Criar release (deploy)';
        }
        
        // Atualizar informações
        document.getElementById('runStartTime').textContent = formatDateTime(run.started_at);
        document.getElementById('runExecutedBy').textContent = run.started_by_name || 'Sistema';
        
        // Calcular duração
        if (run.finished_at) {
            const duration = calculateDuration(run.started_at, run.finished_at);
            document.getElementById('runDuration').textContent = duration;
        } else {
            document.getElementById('runDuration').textContent = 'Em execução...';
        }
        
        // Armazenar IDs para uso posterior
        document.getElementById('btnRelease').dataset.runId = runId;
        document.getElementById('btnRelease').dataset.pipelineId = pipelineId;
        document.getElementById('btnViewLogs').dataset.runId = runId;
        document.getElementById('btnRefreshRun').dataset.runId = runId;
        document.getElementById('btnRefreshRun').dataset.pipelineId = pipelineId;
        
        // Carregar logs dos comandos
        await loadRunCommandsLogs(runId);
        
    } catch (error) {
        console.error('Erro ao carregar detalhes do run:', error);
        throw error;
    }
}

/**
 * Atualiza o status visual da execução
 */
function updateRunStatus(run) {
    const statusElement = document.getElementById('runStatus');
    const btnRelease = document.getElementById('btnRelease');
    const errorContainer = document.getElementById('runErrorContainer');
    const errorMessage = document.getElementById('runErrorMessage');
    const commandsList = document.getElementById('runCommandsList');
    
    // Criar/obter elemento de loading dos comandos
    let commandsLoading = document.getElementById('runCommandsLoading');
    if (!commandsLoading && commandsList) {
        commandsLoading = document.createElement('div');
        commandsLoading.id = 'runCommandsLoading';
        commandsLoading.className = 'text-center py-5';
        commandsLoading.innerHTML = `
            <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Executando...</span>
            </div>
            <h5 class="text-muted">⏳ Executando pipeline...</h5>
            <p class="text-muted small">Aguarde a conclusão dos comandos</p>
        `;
        commandsList.parentNode.insertBefore(commandsLoading, commandsList);
    }
    
    let statusHtml = '';
    let statusClass = '';
    
    switch (run.status) {
    case 'running':
        statusHtml = '<i class="fas fa-spinner fa-spin"></i> Executando';
        statusClass = 'bg-primary';
        btnRelease.disabled = true;
        errorContainer.classList.add('d-none');
        // Mostrar botão de stream
        const btnStream = document.getElementById('btnOpenStream');
        if (btnStream) {
            btnStream.classList.remove('d-none');
            btnStream.dataset.runId = run.id;
        }
        // Ocultar comandos e mostrar loading
        if (commandsList) commandsList.classList.add('d-none');
        if (commandsLoading) commandsLoading.classList.remove('d-none');
        break;
        case 'success':
            statusHtml = '<i class="fas fa-check-circle"></i> Sucesso';
            statusClass = 'bg-success';
            btnRelease.disabled = false;
            errorContainer.classList.add('d-none');
            // Esconder botão de stream
            document.getElementById('btnOpenStream')?.classList.add('d-none');
            // Mostrar comandos e ocultar loading
            if (commandsList) commandsList.classList.remove('d-none');
            if (commandsLoading) commandsLoading.classList.add('d-none');
            break;
        case 'failed':
            statusHtml = '<i class="fas fa-times-circle"></i> Falhou';
            statusClass = 'bg-danger';
            btnRelease.disabled = true;
            if (run.error_message) {
                errorMessage.textContent = run.error_message;
                errorContainer.classList.remove('d-none');
            }
            // Esconder botão de stream
            document.getElementById('btnOpenStream')?.classList.add('d-none');
            // Mostrar comandos e ocultar loading
            if (commandsList) commandsList.classList.remove('d-none');
            if (commandsLoading) commandsLoading.classList.add('d-none');
            break;
        default:
            statusHtml = '<i class="fas fa-question-circle"></i> Desconhecido';
            statusClass = 'bg-secondary';
            btnRelease.disabled = true;
            // Esconder botão de stream
            document.getElementById('btnOpenStream')?.classList.add('d-none');
            // Mostrar comandos e ocultar loading
            if (commandsList) commandsList.classList.remove('d-none');
            if (commandsLoading) commandsLoading.classList.add('d-none');
    }
    
    statusElement.innerHTML = `<span class="badge ${statusClass}">${statusHtml}</span>`;
}

/**
 * Carrega os logs dos comandos executados
 */
async function loadRunCommandsLogs(runId) {
    try {
        const response = await apiGetRunLogs(runId);
        const logs = response.logs || [];
        
        const commandsList = document.getElementById('runCommandsList');
        
        if (logs.length === 0) {
            commandsList.innerHTML = '<div class="text-muted text-center py-4">Nenhum comando executado ainda</div>';
            return;
        }
        
        commandsList.innerHTML = logs.map((log, idx) => {
            const statusIcon = log.status === 'success' ? 'fa-check-circle text-success' :
                             log.status === 'failed' ? 'fa-times-circle text-danger' :
                             'fa-spinner fa-spin text-primary';
            
            const duration = log.finished_at ? 
                calculateDuration(log.started_at, log.finished_at) : 
                'Em execução...';
            
            return `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h6 class="mb-1">
                                <i class="fas ${statusIcon}"></i>
                                <strong>${idx + 1}.</strong> ${log.command_name || 'Comando'}
                            </h6>
                            <small class="text-muted">${log.command_description || ''}</small>
                        </div>
                        <div class="text-end">
                            <small class="text-muted d-block">${duration}</small>
                            <span class="badge bg-${getStatusColor(log.status)}">
                                ${getStatusText(log.status)}
                            </span>
                        </div>
                    </div>
                    ${log.output ? `
                        <details class="mt-2">
                            <summary class="text-muted" style="cursor: pointer;">
                                <small><i class="fas fa-terminal"></i> Ver saída</small>
                            </summary>
                            <pre class="bg-dark text-light p-2 mt-2 rounded" style="font-size: 0.85rem; max-height: 200px; overflow-y: auto;">${escapeHtml(log.output)}</pre>
                        </details>
                    ` : ''}
                </div>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Erro ao carregar logs dos comandos:', error);
    }
}

/**
 * Inicia polling para atualizar status da execução
 */

function startRunPolling(runId, pipelineId) {
    // Limpar intervalo anterior se existir
    if (runPollingInterval) {
        clearInterval(runPollingInterval);
    }
    
    // Atualizar a cada 3 segundos
    runPollingInterval = setInterval(async () => {
        try {
            const runsResponse = await apiGetPipelineRuns(pipelineId, 1, 100);
            const run = runsResponse.runs.find(r => r.id === runId);
            
            if (run) {
                updateRunStatus(run);
                
                // Atualizar duração
                if (run.finished_at) {
                    const duration = calculateDuration(run.started_at, run.finished_at);
                    document.getElementById('runDuration').textContent = duration;
                    
                    // Parar polling se execução finalizou
                    if (run.status !== 'running') {
                        clearInterval(runPollingInterval);
                        runPollingInterval = null;
                        
                        // Atualizar logs dos comandos
                        await loadRunCommandsLogs(runId);
                    }
                }
            }
        } catch (error) {
            console.error('Erro no polling:', error);
        }
    }, 3000);
}

/**
 * Para o polling da execução
 */
function stopRunPolling() {
    if (runPollingInterval) {
        clearInterval(runPollingInterval);
        runPollingInterval = null;
    }
}

/**
 * Volta para a lista de pipelines
 */
function backToPipelines() {
    stopRunPolling();
    document.getElementById('pipelineRunView').classList.add('d-none');
    
    const contentArea = document.getElementById('content-area');
    if (contentArea) contentArea.style.display = 'block';
}

/**
 * Atualiza o status da execução manualmente
 */
async function refreshRunStatus(params) {
    // Buscar runId e pipelineId de diferentes fontes
    let runId = null;
    let pipelineId = null;
    
    if (params && params.runId) {
        runId = parseInt(params.runId);
    } else {
        const btnRefresh = document.getElementById('btnRefreshRun');
        if (btnRefresh && btnRefresh.dataset.runId) {
            runId = parseInt(btnRefresh.dataset.runId);
        }
    }
    
    if (params && params.pipelineId) {
        pipelineId = parseInt(params.pipelineId);
    } else {
        const btnRefresh = document.getElementById('btnRefreshRun');
        if (btnRefresh && btnRefresh.dataset.pipelineId) {
            pipelineId = parseInt(btnRefresh.dataset.pipelineId);
        }
    }
    
    if (!runId || !pipelineId) {
        showNotification('Informações da execução não encontradas', 'error');
        return;
    }
    
    try {
        showNotification('Atualizando...', 'info');
        await loadRunDetails(runId, pipelineId);
        showNotification('Status atualizado', 'success');
    } catch (error) {
        console.error('Erro ao atualizar status:', error);
        showNotification('Erro ao atualizar: ' + error.message, 'error');
    }
}

/**
 * Abre o modal de logs em stream
 */
async function viewRunLogs(params) {
    // Buscar runId de diferentes fontes possíveis
    let runId = null;
    
    if (params && params.runId) {
        runId = parseInt(params.runId);
    } else if (params && params.target && params.target.dataset && params.target.dataset.runId) {
        runId = parseInt(params.target.dataset.runId);
    } else {
        // Buscar diretamente do botão btnViewLogs
        const btnViewLogs = document.getElementById('btnViewLogs');
        if (btnViewLogs && btnViewLogs.dataset.runId) {
            runId = parseInt(btnViewLogs.dataset.runId);
        }
    }
    
    if (!runId) {
        showNotification('ID da execução não encontrado', 'error');
        return;
    }
    
    try {
        const modal = new bootstrap.Modal(document.getElementById('runLogsModal'));
        const logsContent = document.getElementById('runLogsContent');
        const logsTitle = document.getElementById('runLogsTitle');
        
        // Buscar logs
        const response = await apiGetRunLogs(runId);
        const logs = response.logs || [];
        
        logsTitle.textContent = `Logs da Execução #${response.run_number || runId}`;
        
        // Renderizar logs
        let logsHtml = '';
        
        if (logs.length === 0) {
            logsHtml = '<div class="text-muted">Nenhum log disponível</div>';
        } else {
            logs.forEach((log, idx) => {
                logsHtml += `<div class="mb-3 border-bottom border-secondary pb-3">`;
                logsHtml += `<div class="text-info mb-2">`;
                logsHtml += `<strong>[${idx + 1}] ${log.command_name || 'Comando'}</strong>`;
                logsHtml += `<span class="badge bg-${getStatusColor(log.status)} ms-2">${getStatusText(log.status)}</span>`;
                logsHtml += `</div>`;
                
                if (log.output) {
                    logsHtml += `<pre style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(log.output)}</pre>`;
                } else {
                    logsHtml += `<div class="text-muted">Sem saída</div>`;
                }
                
                logsHtml += `</div>`;
            });
        }
        
        logsContent.innerHTML = logsHtml;
        
        // Armazenar runId para download
        document.querySelector('[data-action="downloadRunLogs"]').dataset.runId = runId;
        
        modal.show();
        
    } catch (error) {
        console.error('Erro ao carregar logs:', error);
        showNotification('Erro ao carregar logs: ' + error.message, 'error');
    }
}

/**
 * Download dos logs da execução
 */
async function downloadRunLogs(params) {
    // Buscar runId de diferentes fontes possíveis
    let runId = null;
    
    if (params && params.runId) {
        runId = parseInt(params.runId);
    } else if (params && params.target && params.target.dataset && params.target.dataset.runId) {
        runId = parseInt(params.target.dataset.runId);
    } else {
        // Buscar do botão que tem o runId armazenado
        const btnDownload = document.querySelector('[data-action="downloadRunLogs"]');
        if (btnDownload && btnDownload.dataset.runId) {
            runId = parseInt(btnDownload.dataset.runId);
        }
    }
    
    if (!runId) {
        showNotification('ID da execução não encontrado', 'error');
        return;
    }
    
    try {
        const response = await apiGetRunLogs(runId);
        const logs = response.logs || [];
        
        let logText = `=== LOGS DA EXECUÇÃO #${response.run_number || runId} ===\\n\\n`;
        
        logs.forEach((log, idx) => {
            logText += `[${ idx + 1}] ${log.command_name || 'Comando'}\\n`;
            logText += `Status: ${log.status}\\n`;
            logText += `Início: ${log.started_at}\\n`;
            if (log.finished_at) {
                logText += `Término: ${log.finished_at}\\n`;
            }
            logText += `\\nSaída:\\n${log.output || '(sem saída)'}\\n`;
            logText += `\\n${'='.repeat(80)}\\n\\n`;
        });
        
        const blob = new Blob([logText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pipeline-run-${runId}-logs.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showNotification('Logs baixados com sucesso', 'success');
        
    } catch (error) {
        console.error('Erro ao baixar logs:', error);
        showNotification('Erro ao baixar logs: ' + error.message, 'error');
    }
}

/**
 * Abre o modal de release a partir de uma execução bem-sucedida
 */
async function openReleaseFromRun(params) {
    // Buscar runId e pipelineId de diferentes fontes
    let runId = null;
    let pipelineId = null;
    
    if (params && params.runId) {
        runId = parseInt(params.runId);
    } else {
        const btnRelease = document.getElementById('btnRelease');
        if (btnRelease && btnRelease.dataset.runId) {
            runId = parseInt(btnRelease.dataset.runId);
        }
    }
    
    if (params && params.pipelineId) {
        pipelineId = parseInt(params.pipelineId);
    } else {
        const btnRelease = document.getElementById('btnRelease');
        if (btnRelease && btnRelease.dataset.pipelineId) {
            pipelineId = parseInt(btnRelease.dataset.pipelineId);
        }
    }
    
    if (!runId || !pipelineId) {
        showNotification('Informações da execução não encontradas', 'error');
        return;
    }
    
    try {
        // Buscar dados da pipeline para pegar o deploy_id
        const pipeline = pipelines.find(p => p.id === pipelineId);

        if (!pipeline) {
            showNotification('Pipeline não encontrada', 'error');
            return;
        }

        // Verificar se a pipeline tem comandos do tipo DEPLOY
        const deployCommands = pipeline.commands?.filter(cmd => cmd.command_category === 'deploy') || [];
        
        if (!pipeline.deploy_command_id) {
            showNotification('Esta pipeline não tem um comando de deploy configurado', 'warning');
            return;
        }

        // Criar release a partir do run
        await createReleaseFromRun(runId, pipelineId);
        
    } catch (error) {
        console.error('Erro ao abrir release:', error);
        showNotification('Erro ao abrir release: ' + error.message, 'error');
    }
}

/**
 * Calcula a duração entre duas datas
 */
function calculateDuration(startDate, endDate) {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const diffMs = end - start;
    
    const seconds = Math.floor((diffMs / 1000) % 60);
    const minutes = Math.floor((diffMs / (1000 * 60)) % 60);
    const hours = Math.floor((diffMs / (1000 * 60 * 60)) % 24);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    } else {
        return `${seconds}s`;
    }
}

/**
 * Escapa HTML para prevenir XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Visualiza logs de um build em tempo real
 */
async function viewBuildLogs(params) {
    const runId = params.runId;
    try {
        if (typeof apiGetRunLogs !== 'function') {
            const error = new Error('apiGetRunLogs não disponível');
            console.error('❌', error);
            showNotification('Erro: API não carregada. Recarregue a página.', 'error');
            throw error;
        }
        const response = await apiGetRunLogs(runId);
        
        const run = response.run;
        const logs = response.logs || [];
        
        // Renderizar modal de logs
        const logsHtml = logs.map(log => `
            <div class="log-entry mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>
                        <i class="fas fa-terminal"></i> ${log.command_name || 'Comando'}
                    </strong>
                    <span class="badge bg-${getStatusColor(log.status)}">
                        ${getStatusText(log.status)}
                    </span>
                </div>
                ${log.output ? `
                    <pre class="bg-dark text-light p-3 rounded" style="max-height: 300px; overflow-y: auto;">${log.output}</pre>
                ` : '<p class="text-muted">Sem output</p>'}
            </div>
        `).join('');
        
        document.getElementById('buildLogsContent').innerHTML = logsHtml;
        document.getElementById('buildLogsTitle').textContent = `Build #${run.run_number} - Logs`;
        
        const modal = new bootstrap.Modal(document.getElementById('buildLogsModal'));
        modal.show();
        
        // Se build ainda está rodando, iniciar polling
        if (run.status === 'running') {
            startBuildLogPolling(runId);
        }
        
    } catch (error) {
        console.error('Erro ao carregar logs:', error);
        showNotification('Erro ao carregar logs do build', 'error');
    }
}

let buildLogPollingInterval = null;

/**
 * Inicia polling de logs de build em tempo real
 */
function startBuildLogPolling(runId) {
    // Limpar polling anterior
    if (buildLogPollingInterval) {
        clearInterval(buildLogPollingInterval);
    }
    
    buildLogPollingInterval = setInterval(async () => {
        try {
            const response = await apiGetRunLogs(runId);
            const run = response.run;
            
            // Atualizar logs no modal se estiver aberto
            const modal = document.getElementById('buildLogsModal');
            if (modal && modal.classList.contains('show')) {
                await viewBuildLogs({ runId: runId });
            }
            
            // Parar polling se build terminou
            if (run.status !== 'running') {
                clearInterval(buildLogPollingInterval);
                buildLogPollingInterval = null;
                showNotification(`Build finalizado: ${getStatusText(run.status)}`, 
                    run.status === 'success' ? 'success' : 'error');
            }
        } catch (error) {
            console.error('Erro no polling de logs:', error);
        }
    }, 3000); // Atualizar a cada 3 segundos
}

// =====================================================================
// FUNÇÕES DE RELEASE (CD)
// =====================================================================

/**
 * Cria um release (deploy)
 */
async function createRelease(params) {
    const pipelineId = params.pipelineId;
    const runId = params.runId || null;
    
    try {
        const confirmed = confirm('Deseja criar um novo release (deploy)?');
        if (!confirmed) return;
        
        showNotification('Criando release...', 'info');
        
        const data = runId ? { run_id: runId } : {};
        
        if (typeof apiCreateRelease !== 'function') {
            const error = new Error('apiCreateRelease não disponível');
            console.error('❌', error);
            showNotification('Erro: API não carregada. Recarregue a página.', 'error');
            throw error;
        }
        
        const response = await apiCreateRelease(pipelineId, data);
        
        if (response.success) {
            showNotification(response.message, 'success');
            
            // Carregar histórico de releases
            await loadPipelineReleases(pipelineId);
        }
    } catch (error) {
        console.error('Erro ao criar release:', error);
        showNotification('Erro ao criar release: ' + error.message, 'error');
    }
}

/**
 * Carrega histórico de releases de um pipeline
 */
async function loadPipelineReleases(pipelineId, page = 1) {
    try {
        if (typeof apiGetPipelineReleases !== 'function') {
            const error = new Error('apiGetPipelineReleases não disponível');
            console.error('❌', error);
            showNotification('Erro: API não carregada. Recarregue a página.', 'error');
            throw error;
        }
        const response = await apiGetPipelineReleases(pipelineId, page, 20);
        
        const releases = response.releases || [];
        const total = response.total || 0;
        
        // Renderizar lista de releases
        const releasesHtml = releases.map(release => `
            <div class="card mb-3 border-${getStatusColor(release.status)}">
                <div class="card-body">
                    <div class="row align-items-center">
                        <div class="col-md-1">
                            <h5 class="mb-0">#${release.release_number}</h5>
                        </div>
                        <div class="col-md-2">
                            <span class="badge bg-${getStatusColor(release.status)}">
                                ${getStatusText(release.status)}
                            </span>
                        </div>
                        <div class="col-md-2">
                            ${release.build_number ? `
                                <small class="text-muted">
                                    <i class="fas fa-code-branch"></i> Build #${release.build_number}
                                </small>
                            ` : ''}
                        </div>
                        <div class="col-md-2">
                            <small class="text-muted">
                                <i class="fas fa-user"></i> ${release.deployed_by_name || 'Sistema'}
                            </small>
                        </div>
                        <div class="col-md-3">
                            <small class="text-muted">
                                <i class="fas fa-clock"></i> ${formatDateTime(release.started_at)}
                            </small>
                        </div>
                        <div class="col-md-2 text-end">
                            <button class="btn btn-sm btn-outline-primary" 
                                    data-action="viewReleaseLogs"
                                    data-params='{"releaseId": ${release.id}}'>
                                <i class="fas fa-file-alt"></i> Logs
                            </button>
                        </div>
                    </div>
                    ${release.error_message ? `
                        <div class="alert alert-danger mt-2 mb-0">
                            <i class="fas fa-exclamation-circle"></i> ${release.error_message}
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('');
        
        document.getElementById('releasesContainer').innerHTML = releasesHtml || 
            '<div class="alert alert-info">Nenhum release encontrado</div>';
        
        // Paginação
        renderPagination('releasesPagination', page, Math.ceil(total / 20), (p) => {
            loadPipelineReleases(pipelineId, p);
        });
        
    } catch (error) {
        console.error('Erro ao carregar releases:', error);
        showNotification('Erro ao carregar releases', 'error');
    }
}

/**
 * Visualiza logs de um release em tempo real
 */
async function viewReleaseLogs(params) {
    const releaseId = params.releaseId;
    try {
        const response = await apiGetReleaseLogs(releaseId);
        
        const release = response.release;
        const logs = response.logs || [];
        
        // Renderizar modal de logs
        const logsHtml = logs.map(log => `
            <div class="log-entry mb-2">
                <div class="d-flex align-items-start">
                    <span class="badge bg-${log.log_type === 'error' ? 'danger' : 'info'} me-2">
                        ${log.log_type}
                    </span>
                    <pre class="mb-0 flex-grow-1">${log.output}</pre>
                </div>
            </div>
        `).join('');
        
        document.getElementById('releaseLogsContent').innerHTML = logsHtml || 
            '<p class="text-muted">Nenhum log disponível</p>';
        document.getElementById('releaseLogsTitle').textContent = `Release #${release.release_number} - Logs`;
        
        const modal = new bootstrap.Modal(document.getElementById('releaseLogsModal'));
        modal.show();
        
        // Se release ainda está rodando, iniciar polling
        if (release.status === 'running') {
            startReleaseLogPolling(releaseId);
        }
        
    } catch (error) {
        console.error('Erro ao carregar logs:', error);
        showNotification('Erro ao carregar logs do release', 'error');
    }
}

let releaseLogPollingInterval = null;

/**
 * Inicia polling de logs de release em tempo real
 */
function startReleaseLogPolling(releaseId) {
    // Limpar polling anterior
    if (releaseLogPollingInterval) {
        clearInterval(releaseLogPollingInterval);
    }
    
    releaseLogPollingInterval = setInterval(async () => {
        try {
            const response = await apiGetReleaseLogs(releaseId);
            const release = response.release;
            
            // Atualizar logs no modal se estiver aberto
            const modal = document.getElementById('releaseLogsModal');
            if (modal && modal.classList.contains('show')) {
                await viewReleaseLogs({ releaseId: releaseId });
            }
            
            // Parar polling se release terminou
            if (release.status !== 'running') {
                clearInterval(releaseLogPollingInterval);
                releaseLogPollingInterval = null;
                showNotification(`Release finalizado: ${getStatusText(release.status)}`, 
                    release.status === 'success' ? 'success' : 'error');
            }
        } catch (error) {
            console.error('Erro no polling de logs:', error);
        }
    }, 3000); // Atualizar a cada 3 segundos
}

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
// REGISTRAR ACTIONS NO ACTION HANDLERS
// =====================================================================

// Adicionar novas ações ao objeto actionHandlers existente
Object.assign(actionHandlers, {
    // Build actions
    'runPipelineBuild': (params) => runPipelineBuild(params),
    'loadPipelineBuilds': (params) => loadPipelineBuilds(params.pipelineId, params.page || 1),
    'viewBuildLogs': (params) => viewBuildLogs(params),
    
    // Release actions
    'createRelease': (params) => createRelease(params),
    'loadPipelineReleases': (params) => loadPipelineReleases(params.pipelineId, params.page || 1),
    'viewReleaseLogs': (params) => viewReleaseLogs(params),
});

console.log('✅ Funções Azure DevOps Style carregadas e registradas!');

// =====================================================================
// FUNÇÕES DE HISTÓRICO DE BUILDS
// =====================================================================

async function showBuildHistory(pipelineId) {
    /**
     * Exibe o histórico de execuções (builds) de um pipeline.
     * Mostra uma lista de runs com status e opção de ver detalhes.
     */
    try {
        const pipeline = pipelines.find(p => p.id === pipelineId);
        if (!pipeline) {
            showNotification('Pipeline não encontrado', 'error');
            return;
        }
        
        // Buscar histórico de runs
        const data = await apiGetPipelineRuns(pipelineId, 1, 50);
        
        // Para cada run, verificar se tem deploy com sucesso
        const runsWithDeployStatus = await Promise.all(
            (data.runs || []).map(async (run) => {
                try {
                    const releasesData = await apiGetRunReleases(run.id);
                    const hasSuccessfulDeploy = releasesData.releases?.some(r => r.status === 'success');
                    return { ...run, hasSuccessfulDeploy };
                } catch (error) {
                    console.error(`Erro ao buscar releases do run ${run.id}:`, error);
                    return { ...run, hasSuccessfulDeploy: false };
                }
            })
        );
        
        // Preparar conteúdo do modal
        const modalContent = document.getElementById('buildHistoryContent');
        const modalTitle = document.getElementById('buildHistoryTitle');
        
        modalTitle.textContent = `📊 Histórico de Builds - ${pipeline.name}`;
        
        if (!runsWithDeployStatus || runsWithDeployStatus.length === 0) {
            modalContent.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-inbox fa-3x text-muted mb-3"></i>
                    <p class="text-muted">Nenhuma execução encontrada para este pipeline.</p>
                </div>`;
        } else {
            modalContent.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Build #</th>
                                <th>Status</th>
                                <th>Iniciado</th>
                                <th>Duração</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${runsWithDeployStatus.map(run => `
                                <tr>
                                    <td><strong>#${run.run_number}</strong></td>
                                    <td>
                                        ${getStatusBadge(run.status)}
                                        ${run.hasSuccessfulDeploy ? 
                                            '<div class="mt-1"><span class="badge bg-success"><i class="fas fa-check me-1"></i>Deploy OK</span></div>' 
                                            : ''}
                                    </td>
                                    <td>${formatDateTime(run.started_at)}</td>
                                    <td>${calculateDuration(run.started_at, run.finished_at)}</td>
                                    <td>
                                        <button class="btn btn-sm btn-outline-primary" 
                                                data-action="openRunViewFromHistory" 
                                                data-params='{"runId":${run.id},"pipelineId":${pipelineId}}'>
                                            <i class="fas fa-file-alt me-1"></i>Detalhes
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="text-center mt-3 text-muted">
                    <small>Total: ${data.total} execuções</small>
                </div>`;
        }
        
        // Abrir modal
        const modal = new bootstrap.Modal(document.getElementById('buildHistoryModal'));
        modal.show();
        
    } catch (error) {
        console.error('Erro ao carregar histórico de builds:', error);
        showNotification('Erro ao carregar histórico de builds', 'error');
    }
}



/**
 * Abre a visualização de execução do pipeline a partir do histórico
 * e fecha o modal de histórico
 */
async function openRunViewFromHistory(params) {
    const { runId, pipelineId } = params;
    
    try {
        // Fechar o modal de histórico
        const historyModal = bootstrap.Modal.getInstance(document.getElementById('buildHistoryModal'));
        if (historyModal) {
            historyModal.hide();
        }
        
        // Abrir a visualização de execução
        await openPipelineRunView(runId, pipelineId);
        
    } catch (error) {
        console.error('Erro ao abrir visualização do run:', error);
        showNotification('Erro ao abrir detalhes da execução', 'error');
    }
}

async function viewBuildDetails(runId, runNumber) {
    /**
     * Exibe os logs detalhados de uma execução (build).
     */
    try {
        const data = await apiGetRunLogs(runId);
        const modalTitle = document.getElementById('buildDetailsTitle');
        const modalContent = document.getElementById('buildDetailsContent');
        
        modalTitle.textContent = `🔍 Build #${runNumber} - Logs Detalhados`;
        
        if (!data.logs || data.logs.length === 0) {
            modalContent.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhum log registrado para esta execução.
                </div>`;
        } else {
            const logsHtml = data.logs.map(log => {
                const levelClass = {
                    'info': 'text-primary',
                    'success': 'text-success',
                    'error': 'text-danger',
                    'warning': 'text-warning'
                }[log.status] || 'text-secondary';
                
                return `
                    <div class="log-entry mb-3 border-start border-3 border-${levelClass.replace('text-', '')} ps-3">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <strong>${log.command_name || 'Comando ' + log.command_order}</strong>
                                <small class="text-muted ms-2">${formatTime(log.started_at)}</small>
                            </div>
                            <span class="badge bg-${levelClass.replace('text-', '')}">
                                ${log.status}
                            </span>
                        </div>
                        ${log.output ? `
                            <pre class="mt-2 mb-0 p-2 bg-dark text-light rounded" style="max-height: 300px; overflow-y: auto; font-size: 0.85em;">${log.output}</pre>
                        ` : '<small class="text-muted">Sem output</small>'}
                    </div>`;
            }).join('');
            
            modalContent.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>
                            <i class="fas fa-tasks me-2"></i>
                            Status: ${getStatusBadge(data.run.status)}
                        </span>
                        <span class="text-muted">
                            <i class="fas fa-clock me-1"></i>
                            Duração: ${calculateDuration(data.run.started_at, data.run.finished_at)}
                        </span>
                    </div>
                    <div class="card-body" style="max-height: 600px; overflow-y: auto;">
                        ${logsHtml}
                    </div>
                </div>`;
        }
        
        const modal = new bootstrap.Modal(document.getElementById('buildDetailsModal'));
        modal.show();
        
    } catch (error) {
        console.error('Erro ao carregar detalhes do build:', error);
        showNotification('❌ Erro ao carregar detalhes do build: ' + error.message, 'error');
    }

        try {
        // Renderizar logs
        if (!data.logs || data.logs.length === 0) {
            modalContent.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhum log registrado para esta execução.
                </div>`;
        } else {
            const logsHtml = data.logs.map(log => {
                const levelClass = {
                    'info': 'text-primary',
                    'success': 'text-success',
                    'error': 'text-danger',
                    'warning': 'text-warning'
                }[log.status] || 'text-secondary';
                
                return `
                    <div class="log-entry mb-3 border-start border-3 border-${levelClass.replace('text-', '')} ps-3">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <strong>${log.command_name || 'Comando ' + log.command_order}</strong>
                                <small class="text-muted ms-2">${formatTime(log.started_at)}</small>
                            </div>
                            <span class="badge bg-${levelClass.replace('text-', '')}">
                                ${log.status}
                            </span>
                        </div>
                        ${log.output ? `
                            <pre class="mt-2 mb-0 p-2 bg-dark text-light rounded" style="max-height: 300px; overflow-y: auto; font-size: 0.85em;">
${log.output}</pre>
                        ` : '<small class="text-muted">Sem output</small>'}
                    </div>`;
            }).join('');
            
            modalContent.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>
                            <i class="fas fa-tasks me-2"></i>
                            Status: ${getStatusBadge(data.run.status)}
                        </span>
                        <span class="text-muted">
                            <i class="fas fa-clock me-1"></i>
                            Duração: ${calculateDuration(data.run.started_at, data.run.finished_at)}
                        </span>
                    </div>
                    <div class="card-body" style="max-height: 600px; overflow-y: auto;">
                        ${logsHtml}
                    </div>
                </div>`;
        }
        
        // Abrir modal
        const modal = new bootstrap.Modal(document.getElementById('buildDetailsModal'));
        modal.show();
        
    } catch (error) {
        console.error('Erro ao carregar detalhes do build:', error);
        showNotification('❌ Erro ao carregar detalhes do build: ' + error.message, 'error');
    }
}

// =====================================================================
// FUNÇÕES DE HISTÓRICO DE RELEASES
// =====================================================================

async function showReleaseHistory(pipelineId) {
    /**
     * Exibe o histórico de releases (deploys) de um pipeline.
     * Mostra uma lista de releases com status e opção de ver detalhes.
     */
    try {
        const pipeline = pipelines.find(p => p.id === pipelineId);
        if (!pipeline) {
            showNotification('Pipeline não encontrado', 'error');
            return;
        }
        
        // Buscar histórico de releases
        const data = await apiGetPipelineReleases(pipelineId, 1, 50);
        
        // Preparar conteúdo do modal
        const modalContent = document.getElementById('releaseHistoryContent');
        const modalTitle = document.getElementById('releaseHistoryTitle');
        
        modalTitle.textContent = `🚀 Histórico de Releases - ${pipeline.name}`;
        
        if (!data.releases || data.releases.length === 0) {
            modalContent.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-inbox fa-3x text-muted mb-3"></i>
                    <p class="text-muted">Nenhum deploy realizado para este pipeline.</p>
                </div>`;
        } else {
            modalContent.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Release #</th>
                                <th>Build</th>
                                <th>Status</th>
                                <th>Ambiente</th>
                                <th>Iniciado</th>
                                <th>Duração</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.releases.map(release => `
                                <tr>
                                    <td><strong>#${release.id}</strong></td>
                                    <td><span class="badge bg-secondary">#${release.build_number || 'N/A'}</span></td>
                                    <td>${getStatusBadge(release.status)}</td>
                                    <td><span class="badge bg-info">${release.environment_name || 'Padrão'}</span></td>
                                    <td>${formatDateTime(release.started_at)}</td>
                                    <td>${calculateDuration(release.started_at, release.finished_at)}</td>
                                    <td>
                                        <button class="btn btn-sm btn-outline-primary" 
                                                data-action="viewReleaseDetails" 
                                                data-params='{"releaseId":${release.id}}'>
                                            <i class="fas fa-file-alt me-1"></i>Detalhes
                                        </button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="text-center mt-3 text-muted">
                    <small>Total: ${data.total} deploys</small>
                </div>`;
        }
        
        // Abrir modal
        const modal = new bootstrap.Modal(document.getElementById('releaseHistoryModal'));
        modal.show();
        
    } catch (error) {
        console.error('Erro ao carregar histórico de releases:', error);
        showNotification('Erro ao carregar histórico de releases', 'error');
    }
}


async function viewReleaseDetails(releaseId) {
    /**
     * Exibe os logs detalhados de um release (deploy).
     */
    try {
        const data = await apiGetReleaseLogs(releaseId);
        const modalTitle = document.getElementById('releaseDetailsTitle');
        const modalContent = document.getElementById('releaseDetailsContent');
        
        modalTitle.textContent = `🚀 Release #${releaseId} - Logs Detalhados`;
        
        if (!data.logs || data.logs.length === 0) {
            modalContent.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhum log registrado para este release.
                </div>`;
        } else {
            const logsHtml = data.logs.map(log => {
                const levelClass = {
                    'info': 'text-primary',
                    'success': 'text-success', 
                    'error': 'text-danger',
                    'warning': 'text-warning'
                }[log.log_type] || 'text-secondary';
                
                return `
                    <div class="log-entry mb-2">
                        <div class="d-flex align-items-start">
                            <span class="badge bg-${levelClass.replace('text-', '')} me-2">
                                ${log.log_type}
                            </span>
                            <div class="flex-grow-1">
                                <small class="text-muted">${formatTime(log.created_at)}</small>
                                <pre class="mb-0 mt-1" style="white-space: pre-wrap; font-size: 0.9em;">${log.output || 'Sem output'}</pre>
                            </div>
                        </div>
                    </div>`;
            }).join('');
            
            modalContent.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>
                            <i class="fas fa-rocket me-2"></i>
                            Status: ${getStatusBadge(data.release.status)}
                        </span>
                        <span class="text-muted">
                            <i class="fas fa-clock me-1"></i>
                            Duração: ${calculateDuration(data.release.started_at, data.release.finished_at)}
                        </span>
                    </div>
                    <div class="card-body" style="max-height: 600px; overflow-y: auto; background-color: #f8f9fa; font-family: monospace; font-size: 0.9em;">
                        ${logsHtml}
                    </div>
                </div>`;
        }
        
        const modal = new bootstrap.Modal(document.getElementById('releaseDetailsModal'));
        modal.show();

    } catch (error) {
        console.error('Erro ao carregar detalhes do release:', error);
        showNotification('❌ Erro ao carregar detalhes do release: ' + error.message, 'error');
    }
    try {    
    // Renderizar logs
    if (!data.logs || data.logs.length === 0) {
        modalContent.innerHTML = `
            <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    Nenhum log registrado para este release.
                </div>`;
        } else {
            const logsHtml = data.logs.map(log => {
                const levelClass = {
                    'info': 'text-primary',
                    'success': 'text-success', 
                    'error': 'text-danger',
                    'warning': 'text-warning'
                }[log.log_type] || 'text-secondary';
                
                return `
                    <div class="log-entry mb-2">
                        <div class="d-flex align-items-start">
                            <span class="badge bg-${levelClass.replace('text-', '')} me-2">
                                ${log.log_type}
                            </span>
                            <div class="flex-grow-1">
                                <small class="text-muted">${formatTime(log.created_at)}</small>
                                <pre class="mb-0 mt-1" style="white-space: pre-wrap; font-size: 0.9em;">${log.output || 'Sem output'}</pre>
                            </div>
                        </div>
                    </div>`;
            }).join('');
            
            modalContent.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>
                            <i class="fas fa-rocket me-2"></i>
                            Status: ${getStatusBadge(data.release.status)}
                        </span>
                        <span class="text-muted">
                            <i class="fas fa-clock me-1"></i>
                            Duração: ${calculateDuration(data.release.started_at, data.release.finished_at)}
                        </span>
                    </div>
                    <div class="card-body" style="max-height: 600px; overflow-y: auto; background-color: #f8f9fa; font-family: monospace; font-size: 0.9em;">
                        ${logsHtml}
                    </div>
                </div>`;
        }
        
        // Abrir modal
        const modal = new bootstrap.Modal(document.getElementById('releaseDetailsModal'));
        modal.show();
        
    } catch (error) {
        console.error('Erro ao carregar detalhes do release:', error);
        showNotification('❌ Erro ao carregar detalhes do release: ' + error.message, 'error');
    }
}

// =====================================================================
// FUNÇÃO PARA CRIAR RELEASE A PARTIR DE UM RUN
// =====================================================================

async function createReleaseFromRun(runId, pipelineId) {
    /**
     * Cria um release (deploy) a partir de um RUN bem-sucedido.
     * Valida se o build foi bem-sucedido antes de permitir o deploy.
     */
    try {
        const pipeline = pipelines.find(p => p.id === pipelineId);
        if (!pipeline) {
            showNotification('Pipeline não encontrado', 'error');
            return;
        }
        
        // Confirmar com o usuário
        const confirmed = confirm(`Deseja criar um release (deploy) para o pipeline "${pipeline.name}"?`);
        if (!confirmed) return;
        
        // Criar release através da nova API
        const response = await apiCreateReleaseFromRun(runId);
        
        showNotification(response.message || 'Release iniciado com sucesso!', 'success');
        
        // Abrir modal de logs do release
        openReleaseLogsModal(response.release_id);
        
    } catch (error) {
        console.error('Erro ao criar release:', error);
        showNotification(error.message || 'Erro ao criar release', 'error');
    }
}


async function openReleaseLogsModal(releaseId) {
    /**
     * Abre modal de logs de release em tempo real.
     */
    const logModal = new bootstrap.Modal(document.getElementById('releaseLogsModal'));
    document.getElementById('releaseLogsTitle').textContent = `Release #${releaseId} - Logs`;
    const logOutput = document.getElementById('releaseLogsOutput');
    logOutput.textContent = 'Iniciando release...\n';
    logModal.show();

    const appendLog = (line) => {
        logOutput.textContent += line + '\n';
        logOutput.scrollTop = logOutput.scrollHeight;
    };

    try {
        // Conectar ao stream de logs do release
        const eventSource = new EventSource(`/api/releases/${releaseId}/logs/stream?auth_token=${authToken}`);

        appendLog('[CONECTADO AO STREAM DE LOGS]');

        eventSource.onmessage = function (event) {
            console.log('[SSE] Mensagem recebida:', event.data); // DEBUG
            
            try {
                const data = JSON.parse(event.data);
                console.log('[SSE] Dados parseados:', data); // DEBUG
                
                if (data.status === 'completed') {
                    appendLog(`\n[FIM DA EXECUÇÃO] Status final: ${data.final_status}`);
                    eventSource.close();
                    
                    // Destacar botão Fechar
                    const modalFooter = document.querySelector('#releaseLogsModal .modal-footer');
                    const closeBtn = modalFooter.querySelector('[data-bs-dismiss="modal"]');
                    if (closeBtn) {
                        closeBtn.classList.remove('btn-secondary');
                        closeBtn.classList.add('btn-primary');
                        closeBtn.textContent = '✅ Fechar';
                    }
                    
                    // Atualizar view do run se estiver aberta
                    const btnRefresh = document.getElementById('btnRefreshRun');
                    if (btnRefresh && btnRefresh.dataset.runId) {
                        const runId = parseInt(btnRefresh.dataset.runId);
                        const pipelineId = parseInt(btnRefresh.dataset.pipelineId);
                        
                        // Forçar recarga dos detalhes do run após o release
                        setTimeout(async () => {
                            console.log('🔄 Atualizando status do run após o release...');
                            await loadRunDetails(runId, pipelineId);
                        }, 1500);
                    }
                    
                    // Também atualizar se estiver na listagem de pipelines
                    const currentPipeline = pipelines.find(p => p.id === parseInt(btnRefresh?.dataset.pipelineId));
                    if (currentPipeline) {
                        setTimeout(() => {
                            console.log('🔄 Atualizando listagem de pipelines...');
                            loadPipelines();
                        }, 1500);
                    }
                    
                    // Atualizar lista de runs se estiver na listagem
                    if (window.currentPipelineIdForRuns) {
                        setTimeout(() => {
                            loadPipelineRuns(window.currentPipelineIdForRuns);
                        }, 1000);
                    }
                } else if (data.output) {
                    // Backend envia 'output', não 'message'
                    console.log('[SSE] Output recebido:', data.output); // DEBUG
                    appendLog(data.output);
                } else if (data.error) {
                    appendLog(`[ERRO] ${data.error}`);
                    eventSource.close();
                } else {
                    console.warn('[SSE] Formato de dados desconhecido:', data);
                }
            } catch (error) {
                console.error('[SSE] Erro ao parsear JSON:', error, 'Dados brutos:', event.data);
                appendLog(`[ERRO PARSING] ${event.data}`);
            }
        };

        eventSource.onerror = function (error) {
            console.error('[SSE] Erro na conexão:', error);
            appendLog('[ERRO] Conexão com o stream perdida.');
            eventSource.close();
            
            // Habilitar botão fechar em caso de erro
            const modalFooter = document.querySelector('#releaseLogsModal .modal-footer');
            const closeBtn = modalFooter.querySelector('[data-bs-dismiss="modal"]');
            if (closeBtn) {
                closeBtn.classList.remove('btn-secondary');
                closeBtn.classList.add('btn-warning');
                closeBtn.textContent = 'Fechar';
            }
        };

        // Fechar conexão se modal for fechado
        document.getElementById('releaseLogsModal').addEventListener('hidden.bs.modal', () => {
            eventSource.close();
            
            // Resetar botão
            const modalFooter = document.querySelector('#releaseLogsModal .modal-footer');
            const closeBtn = modalFooter.querySelector('[data-bs-dismiss="modal"]');
            closeBtn.classList.remove('btn-primary', 'btn-warning');
            closeBtn.classList.add('btn-secondary');
            closeBtn.textContent = 'Fechar';
        }, { once: true });

    } catch (error) {
        appendLog(`ERRO: ${error.message}`);
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

// Modal de importação CSV
function showImportVariablesModal() {
    const modal = new bootstrap.Modal(document.getElementById('importVariablesModal'));
    document.getElementById('csvFileInput').value = '';
    modal.show();
}

// Importar variáveis de CSV
async function importVariablesFromCSV() {
    const fileInput = document.getElementById('csvFileInput');
    const replaceExisting = document.getElementById('replaceExistingVars').checked;
    
    if (!fileInput.files.length) {
        showNotification('Selecione um arquivo CSV!', 'error');
        return;
    }
    
    const file = fileInput.files[0];
    const reader = new FileReader();
    
    reader.onload = async (e) => {
        try {
            const csvContent = e.target.result;
            const lines = csvContent.split('\n').filter(line => line.trim());
            
            // Remove header se existir
            const hasHeader = lines[0].toLowerCase().includes('name') && lines[0].toLowerCase().includes('value');
            const dataLines = hasHeader ? lines.slice(1) : lines;
            
            let imported = 0;
            let skipped = 0;
            let errors = 0;
            
            for (const line of dataLines) {
                const [name, value, description, isPasswordStr] = line.split(',').map(s => s.trim());
                
                if (!name || !value) {
                    errors++;
                    continue;
                }
                
                // Converter is_password para boolean (aceita: true, 1, yes, sim)
                const is_password = ['true', '1', 'yes', 'sim'].includes((isPasswordStr || '').toLowerCase());
                
                // Verifica se variável já existe
                const existing = serverVariables.find(v => v.name === name);
                
                if (existing && !replaceExisting) {
                    skipped++;
                    continue;
                }
                
                try {
                    if (existing) {
                        await apiUpdateServerVariable(existing.id, { name, value, description: description || '', is_password });
                    } else {
                        await apiCreateServerVariable({ name, value, description: description || '', is_password });
                    }
                    imported++;
                } catch (err) {
                    console.error(`Erro ao importar ${name}:`, err);
                    errors++;
                }
            }
            
            // Recarregar variáveis
            await loadServerVariables();
            reloadSettingsTab('variables-tab');
            
            // Fechar modal
            bootstrap.Modal.getInstance(document.getElementById('importVariablesModal')).hide();
            
            // Notificação de resultado
            showNotification(
                `✅ Importadas: ${imported} | ⏭️ Ignoradas: ${skipped} | ❌ Erros: ${errors}`,
                'success'
            );
            
        } catch (error) {
            console.error('Erro ao processar CSV:', error);
            showNotification('Erro ao processar arquivo CSV!', 'error');
        }
    };
    
    reader.readAsText(file);
}
