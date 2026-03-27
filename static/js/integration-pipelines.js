// =====================================================================
// INTEGRATION-PIPELINES.JS
// CRUD de pipelines, paginação, filtros
// =====================================================================

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

// Função de filtro por tipo de script (mantida para compatibilidade, agora usa SO automático)
function filterPipelinesByScriptType(scriptType) {
    pipelineScriptTypeFilter = scriptType;
    currentPipelinePage = 1;
    showPipelines();
}

// 🖥️ Filtra pipelines pelo SO do servidor: só mostra se TODOS os comandos forem compatíveis
function getOSFilteredCommands() {
    if (!serverOS) return commands;
    return commands.filter(c => c.type === serverOS.command_type);
}

function getOSFilteredPipelines() {
    if (!serverOS) return pipelines;
    return pipelines.filter(p => {
        if (!p.commands || p.commands.length === 0) return true;
        return p.commands.every(cmd => cmd.type === serverOS.command_type);
    });
}

function renderPipelinesPagination() {
    // Filtro automático por SO do servidor
    let filteredPipelines = getOSFilteredPipelines();

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
    // Filtro automático por SO do servidor
    let filteredPipelines = getOSFilteredPipelines();

    if (filteredPipelines.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted">Nenhuma pipeline configurada para este ambiente${serverOS ? ' (' + (serverOS.os_display || serverOS.os) + ')' : ''}.</p>
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

    return `<div class="row">${pipelinesForCurrentPage.map(pipeline => {
        // Verificar se item é protegido
        const isProtected = pipeline.is_protected && !isRootAdmin();
        const showEditBtn = canEdit && !isProtected;
        const showDeleteBtn = canDelete && !isProtected;
        const cmdCount = pipeline.commands ? pipeline.commands.length : 0;

        return `
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center" style="gap: 8px;">
                        <div style="min-width: 0; flex: 1;">
                            <h6 class="mb-0 text-truncate" title="${escapeHtml(pipeline.name)}">
                                <i class="fas fa-cogs me-2"></i>${escapeHtml(pipeline.name)}
                                ${pipeline.is_protected ? '<i class="fas fa-lock text-warning ms-2" title="Protegido"></i>' : ''}
                            </h6>
                            <small class="text-muted">${cmdCount} comando${cmdCount !== 1 ? 's' : ''}</small>
                        </div>
                        <div class="dropdown flex-shrink-0">
                            <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                                <i class="fas fa-ellipsis-v"></i>
                            </button>
                            <ul class="dropdown-menu dropdown-menu-end">
                                ${canExecute ? `
                                <li><a class="dropdown-item" href="#" data-action="runPipelineBuild" data-params='{"pipelineId":${pipeline.id}}'><i class="fas fa-play me-2 text-primary"></i>Run Build</a></li>
                                ` : ''}
                                <li><a class="dropdown-item" href="#" data-action="showBuildHistory" data-params='{"pipelineId":${pipeline.id}}'><i class="fas fa-history me-2 text-info"></i>Builds e Deploys</a></li>
                                ${showEditBtn ? `
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item" href="#" data-action="showEditPipelineModal" data-params='{"pipelineId":${pipeline.id}}'><i class="fas fa-edit me-2"></i>Editar</a></li>
                                ` : ''}
                                ${showDeleteBtn ? `
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item text-danger" href="#" data-action="deletePipeline" data-params='{"pipelineId":${pipeline.id}}'><i class="fas fa-trash me-2"></i>Excluir</a></li>
                                ` : ''}
                            </ul>
                        </div>
                    </div>
                    <div class="card-body">
                        <p class="card-text text-muted small" style="height: 3em; overflow: hidden;">${escapeHtml(pipeline.description || 'Sem descrição')}</p>
                        <div class="command-sequence mt-3">
                            ${pipeline.commands.map((cmd, index) => `
                                <div class="d-flex align-items-center mb-1">
                                    <span class="badge bg-primary me-2" style="min-width: 24px;">${index + 1}</span>
                                    <small>${escapeHtml(cmd.name)}</small>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
    `}).join('')}</div>`;
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

    // Renderiza a lista de comandos compatíveis com o SO
    const filteredCmds = serverOS ? commands.filter(c => c.type === serverOS.command_type) : commands;
    commandList.innerHTML = filteredCmds.map(cmd => `
        <button type="button" class="list-group-item list-group-item-action" 
                data-action="selectDeployCommand" data-params=\'{"commandId":${cmd.id},"commandName":"${escapeHtml(cmd.name)}"}\'>
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${escapeHtml(cmd.name)}</strong>
                    <small class="text-muted d-block">${escapeHtml(cmd.description || 'Sem descrição')}</small>
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
            
                    <!-- Indicador do SO detectado -->
        ${serverOS ? `
        <div class="alert alert-info mb-3 py-2 px-3 d-flex align-items-center" style="font-size: 0.85rem;">
            <i class="fas fa-${serverOS.os === 'windows' ? 'windows' : 'linux'} me-2"></i>
            <span>Exibindo pipelines compatíveis com <strong>${serverOS.os_display || (serverOS.os === 'windows' ? 'Windows' : 'Linux')}</strong></span>
        </div>
        ` : ''}

            <div id="pipelinesContainer"></div>
            <div id="pipelinesPagination"></div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;
    updatePipelinesList();
}

