// =====================================================================
// INTEGRATION-SCHEDULES.JS
// Schedules de pipelines, service actions, polling, sequenciador
// =====================================================================

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
        
        <!-- Indicador do SO detectado -->
        ${serverOS ? `
        <div class="alert alert-info mb-3 py-2 px-3 d-flex align-items-center" style="font-size: 0.85rem;">
            <i class="fas fa-${serverOS.os === 'windows' ? 'windows' : 'linux'} me-2"></i>
            <span>Exibindo agendamentos de pipelines compatíveis com <strong>${serverOS.os_display || (serverOS.os === 'windows' ? 'Windows' : 'Linux')}</strong></span>
        </div>
        ` : ''}

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

    // Estado de filtro — automático pelo SO do servidor
    if (!window.serviceActionsState) {
        window.serviceActionsState = {
            filterOS: serverOS ? serverOS.os.toUpperCase() : 'TODOS'
        };
    } else if (serverOS) {
        window.serviceActionsState.filterOS = serverOS.os.toUpperCase();
    }

    const state = window.serviceActionsState;

    // Filtrar ações por OS automaticamente
    let filteredActions = serviceActions || [];
    if (serverOS) {
        filteredActions = filteredActions.filter(a => a.os_type === serverOS.os);
    }

    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <h5>⚙️ Gestão de Serviços</h5>
                <p class="text-muted mb-0">Configure e execute start/stop de serviços do servidor.</p>
            </div>
            ${isOperator() ? '<button class="btn btn-primary" data-action="showCreateServiceActionModal"><i class="fas fa-plus me-2"></i>Nova Ação</button>' : ''}
        </div>

        <!-- Indicador do SO detectado -->
        ${serverOS ? `
        <div class="alert alert-info mb-3 py-2 px-3 d-flex align-items-center" style="font-size: 0.85rem;">
            <i class="fas fa-${serverOS.os === 'windows' ? 'windows' : 'linux'} me-2"></i>
            <span>Exibindo ações de serviço para <strong>${serverOS.os_display || (serverOS.os === 'windows' ? 'Windows' : 'Linux')}</strong></span>
        </div>
        ` : ''}

        ${filteredActions.length === 0 ? `
            <div class="card text-center p-5">
                <i class="fas fa-cog text-muted" style="font-size: 4rem;"></i>
                <p class="text-muted mt-3">Nenhuma ação de serviço cadastrada${serverOS ? ' para ' + serverOS.os : ''}.</p>
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
                                <i class="fas fa-cog me-2"></i>${escapeHtml(action.name)}
                                ${action.schedule_type ? (!!action.is_active
                ? '<span class="badge bg-success ms-2">Agendamento Ativo</span>'
                : '<span class="badge bg-secondary ms-2">Agendamento Inativo</span>')
                : '<span class="badge bg-info ms-2">Execução Manual</span>'}
                            </h6>
                            <small class="text-muted">
                                <span class="badge ${actionBadgeClass}">${actionIcon} ${action.action_type.toUpperCase()}</span>${forceFlag}
                                <span class="ms-2">${osIcon} ${action.os_type.toUpperCase()}</span>
                                <span class="ms-2">Serviços: ${escapeHtml(serviceNames)}</span>
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
                        ${action.description ? `<p class="text-muted mb-0"><em>${escapeHtml(action.description)}</em></p>` : ''}
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

    console.log(`🔄 Iniciando polling de service actions (intervalo: ${pollingInterval / 1000}s)...`);

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
                <p class="text-muted mt-3">Nenhum agendamento configurado para este ambiente${serverOS ? ' (' + (serverOS.os_display || serverOS.os) + ')' : ''}.</p>
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
                            <i class="fas fa-clock me-2"></i>${escapeHtml(schedule.name)}
                            ${schedule.is_active
                ? '<span class="badge bg-success ms-2">Ativo</span>'
                : '<span class="badge bg-secondary ms-2">Inativo</span>'}
                        </h6>
                        <small class="text-muted">Pipeline: ${escapeHtml(pipelineName)}</small>
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
                                <strong>Criado por:</strong> ${escapeHtml(schedule.created_by_name)}
                            </p>
                        </div>
                    </div>
                    ${schedule.description ? `<p class="text-muted mt-2 mb-0"><em>${escapeHtml(schedule.description)}</em></p>` : ''}
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
    // Filtro automático por SO: só mostra schedules de pipelines compatíveis
    const compatiblePipelines = getOSFilteredPipelines();
    const compatibleIds = new Set(compatiblePipelines.map(p => p.id));
    return schedules.filter(schedule => compatibleIds.has(schedule.pipeline_id));
}

function getFilteredPipelinesForSchedule() {
    // Retorna apenas pipelines compatíveis com o SO do servidor
    return getOSFilteredPipelines();
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
        showNotification(`Nenhuma pipeline compatível com ${serverOS ? (serverOS.os_display || serverOS.os) : 'este servidor'} encontrada!`, 'warning');
        return;
    }

    pipelineSelect.innerHTML = '<option value="">Selecione uma pipeline</option>' +
        filteredPipelines.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');

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
    document.getElementById('editScheduleNotifyEmails').value = schedule.notify_emails || '';
    document.getElementById('editScheduleNotifyWhatsapp').value = schedule.notify_whatsapp || '';

    // Popula dropdown de pipelines (desabilitado, mas mostra todas para não perder a selecionada)
    const pipelineSelect = document.getElementById('editSchedulePipelineId');
    pipelineSelect.innerHTML = '<option value="">Selecione uma pipeline</option>' +
        pipelines.map(p => `<option value="${p.id}" ${p.id === schedule.pipeline_id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('');

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
        const notify_emails = document.getElementById('scheduleNotifyEmails').value.trim();
        const notify_whatsapp = document.getElementById('scheduleNotifyWhatsapp').value.trim();

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
            schedule_config: JSON.stringify(scheduleConfig),
            notify_emails: notify_emails || null,
            notify_whatsapp: notify_whatsapp || null
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
        const notify_emails = document.getElementById('editScheduleNotifyEmails').value.trim();
        const notify_whatsapp = document.getElementById('editScheduleNotifyWhatsapp').value.trim();

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
            schedule_config: JSON.stringify(scheduleConfig),
            notify_emails: notify_emails || null,
            notify_whatsapp: notify_whatsapp || null
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

    // 🖥️ Pré-selecionar e travar SO do servidor automaticamente
    const osSelect = document.getElementById('serviceActionOS');
    if (serverOS && osSelect) {
        osSelect.value = serverOS.os;
        osSelect.disabled = true;
    }

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
                        <strong>${escapeHtml(service.display_name || service.name)}</strong>
                        <small class="text-muted d-block">
                            📦 ${escapeHtml(service.name)} @ ${escapeHtml(service.server_name)} (${escapeHtml(envName)})
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
        return service ? `<span class="badge bg-light text-dark border me-1 mb-1">${index + 1}. ${escapeHtml(service.display_name || service.name)}</span>` : '';
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

    checkbox.addEventListener('change', function () {
        configSection.style.display = this.checked ? 'block' : 'none';
        if (!this.checked) {
            typeSelect.value = '';
            document.getElementById(`${prefix}serviceActionScheduleConfigArea`).innerHTML = '';
        }
    });

    // Remove listeners antigos para evitar duplicação
    const newTypeSelect = typeSelect.cloneNode(true);
    typeSelect.parentNode.replaceChild(newTypeSelect, typeSelect);

    newTypeSelect.addEventListener('change', function () {
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
        // Usar o SO do servidor se disponível (campo pode estar disabled)
        const osSelect = document.getElementById('serviceActionOS');
        const osType = serverOS ? serverOS.os : osSelect.value;
        const forceStop = document.getElementById('serviceActionForceStop').checked;
        const notify_emails = document.getElementById('serviceActionNotifyEmails').value.trim();
        const notify_whatsapp = document.getElementById('serviceActionNotifyWhatsapp').value.trim();

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
            notify_emails: notify_emails || null,
            notify_whatsapp: notify_whatsapp || null,
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
    // 🖥️ Travar campo OS no servidor detectado
    const editOsSelect = document.getElementById('editServiceActionOS');
    if (serverOS && editOsSelect) {
        editOsSelect.disabled = true;
    }
    document.getElementById('editServiceActionForceStop').checked = action.force_stop || false;
    document.getElementById('editServiceActionNotifyEmails').value = action.notify_emails || '';
    document.getElementById('editServiceActionNotifyWhatsapp').value = action.notify_whatsapp || '';

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
        // Usar o SO do servidor se disponível (campo pode estar disabled)
        const editOsSelect = document.getElementById('editServiceActionOS');
        const osType = serverOS ? serverOS.os : editOsSelect.value;
        const forceStop = document.getElementById('editServiceActionForceStop').checked;
        const notify_emails = document.getElementById('editServiceActionNotifyEmails').value.trim();
        const notify_whatsapp = document.getElementById('editServiceActionNotifyWhatsapp').value.trim();

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
            notify_emails: notify_emails || null,
            notify_whatsapp: notify_whatsapp || null,
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

