// =====================================================================
// INTEGRATION-COMMANDS.JS
// Seletor de comandos, CRUD de comandos, tela de comandos
// =====================================================================

window.showCreatePipelineModal = function () {
    try {
        selectedCommands = [];
        updateSelectedCommandsDisplay('create');
        document.getElementById('createPipelineForm').reset();

        // 🆕 Busca comandos de deploy compatíveis com o SO e cria as opções para o dropdown
        const deployCommands = commands.filter(c => c.command_category === 'deploy' && (!serverOS || c.type === serverOS.command_type));
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
        // 🆕 Filtrar comandos pela categoria e pelo SO do servidor
        const filteredCommands = commands.filter(cmd => cmd.command_category === categoryFilter && (!serverOS || cmd.type === serverOS.command_type));

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
                                           data-cmd-id="${cmd.id}" data-cmd-name="${escapeHtml(cmd.name)}" data-cmd-desc="${escapeHtml(cmd.description || '')}" data-cmd-type="${escapeHtml(cmd.type)}"
                                           onchange="toggleCommand(Number(this.dataset.cmdId), this.dataset.cmdName, this.dataset.cmdDesc, this.dataset.cmdType)">
                                    <label class="form-check-label w-100" for="cmd${cmd.id}">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div>
                                                <h6 class="card-title">
                                                    <i class="fas fa-${getCommandIcon(cmd.type)} me-2"></i>
                                                    ${escapeHtml(cmd.name)}
                                                </h6>
                                                <p class="card-text small text-muted">${escapeHtml(cmd.description || 'Sem descrição')}</p>
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
            <h6 class="mb-2 small text-muted">Sequência de Execução (arraste para reordenar):</h6>
            <div class="selected-commands-sequence" id="${containerId}List">
                ${selectedCommands.map((cmd, index) => `
                    <div class="d-flex align-items-center bg-white rounded p-2 mb-2 border cmd-drag-item"
                         draggable="true" data-cmd-id="${cmd.id}" data-cmd-mode="${mode}"
                         style="cursor: grab;">
                        <div class="me-2 text-muted" style="cursor: grab;" title="Arraste para reordenar">
                            <i class="fas fa-grip-vertical"></i>
                        </div>
                        <div class="badge bg-primary me-3" style="min-width: 30px;">${index + 1}</div>
                        <div class="flex-grow-1">
                            <strong>${escapeHtml(cmd.name)}</strong>
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
        _initDragAndDrop(containerId + 'List', mode);
    }
}

// Drag-and-drop para reordenação de comandos
function _initDragAndDrop(listId, mode) {
    const list = document.getElementById(listId);
    if (!list) return;

    let dragItem = null;

    list.addEventListener('dragstart', function (e) {
        const item = e.target.closest('.cmd-drag-item');
        if (!item) return;
        dragItem = item;
        item.style.opacity = '0.4';
        e.dataTransfer.effectAllowed = 'move';
    });

    list.addEventListener('dragend', function (e) {
        const item = e.target.closest('.cmd-drag-item');
        if (item) item.style.opacity = '1';
        list.querySelectorAll('.cmd-drag-item').forEach(el => el.classList.remove('border-primary'));
        dragItem = null;
    });

    list.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const target = e.target.closest('.cmd-drag-item');
        if (target && target !== dragItem) {
            list.querySelectorAll('.cmd-drag-item').forEach(el => el.classList.remove('border-primary'));
            target.classList.add('border-primary');
        }
    });

    list.addEventListener('drop', function (e) {
        e.preventDefault();
        const target = e.target.closest('.cmd-drag-item');
        if (!target || !dragItem || target === dragItem) return;

        const dragId = parseInt(dragItem.dataset.cmdId);
        const targetId = parseInt(target.dataset.cmdId);
        const fromIndex = selectedCommands.findIndex(c => c.id === dragId);
        const toIndex = selectedCommands.findIndex(c => c.id === targetId);

        if (fromIndex === -1 || toIndex === -1) return;

        // Mover elemento no array
        const [moved] = selectedCommands.splice(fromIndex, 1);
        selectedCommands.splice(toIndex, 0, moved);

        updateSelectedCommandsDisplay(mode);
    });
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

        // 🆕 Busca comandos de deploy compatíveis com o SO e cria as opções para o dropdown de edição
        const deployCommands = commands.filter(c => c.command_category === 'deploy' && (!serverOS || c.type === serverOS.command_type));
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
        // Filtrar comandos pelo SO do servidor automaticamente
        let filteredCmds = commands;
        if (serverOS) {
            filteredCmds = commands.filter(cmd => cmd.type === serverOS.command_type);
        }

        if (filteredCmds.length === 0) {
            showNotification(`Nenhum comando compatível com ${serverOS ? (serverOS.os_display || serverOS.os) : 'este servidor'} cadastrado!`, 'warning');
            return;
        }
        // O código que gera o HTML dos comandos continua o mesmo
        const commandsHtml = filteredCmds.map(cmd => `
            <div class="col-md-6 mb-3">
                <div class="card h-100 ${selectedCommands.find(sc => sc.id === cmd.id) ? 'border-primary' : ''}">
                    <div class="card-body">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" value="${cmd.id}" id="cmd${cmd.id}"
                                   ${selectedCommands.find(sc => sc.id === cmd.id) ? 'checked' : ''}
                                   data-cmd-id="${cmd.id}" data-cmd-name="${escapeHtml(cmd.name)}" data-cmd-desc="${escapeHtml(cmd.description || '')}" data-cmd-type="${escapeHtml(cmd.type)}"
                                   onchange="toggleCommand(Number(this.dataset.cmdId), this.dataset.cmdName, this.dataset.cmdDesc, this.dataset.cmdType)">
                            <label class="form-check-label w-100" for="cmd${cmd.id}">
                                <h6 class="card-title"><i class="fas fa-${getCommandIcon(cmd.type)} me-2"></i>${escapeHtml(cmd.name)}</h6>
                                <p class="card-text small text-muted">${escapeHtml(cmd.description || 'Sem descrição')}</p>
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
// =====================================================================
// FUNÇÕES DE COMANDOS
// =====================================================================

async function createNewCommand() {
    try {
        const name = document.getElementById('commandName').value.trim();
        // Usar SO do servidor se disponível (campo pode estar disabled)
        const type = serverOS ? serverOS.command_type : document.getElementById('commandType').value;
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
        const type = serverOS ? serverOS.command_type : document.getElementById('editCommandType').value;
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
            const filteredLen = getOSFilteredCommands().length;
            const totalPages = Math.ceil(filteredLen / commandsPerPage);
            if (currentCommandsPage > totalPages && totalPages > 0) {
                currentCommandsPage = totalPages;
            } else if (filteredLen === 0) {
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
    const filteredCommands = getOSFilteredCommands();

    if (filteredCommands.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted">Nenhum comando compatível com ${serverOS ? (serverOS.os_display || serverOS.os) : 'este servidor'} cadastrado.</p>
                ${isAdmin() ? '<button class="btn btn-primary mt-3" data-action="showCreateCommandModal"><i class="fas fa-plus me-2"></i>Criar Primeiro Comando</button>' : ''}
            </div>`;
    }

    // Verificar permissões
    const canEdit = isAdmin();
    const canDelete = isAdmin();

    return `
        <div class="row">
            ${filteredCommands.map(command => {
        // Verificar se item é protegido
        const isProtected = command.is_protected && !isRootAdmin();
        const showEditBtn = canEdit && !isProtected;
        const showDeleteBtn = canDelete && !isProtected;

        return `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card h-100">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h6 class="mb-0">
                                <i class="fas fa-${getCommandIcon(command.type)} me-2"></i>${escapeHtml(command.name)}
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
                            <p class="card-text text-muted small" style="height: 4.5em; overflow: hidden;">${escapeHtml(command.description || 'Sem descrição')}</p>
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
        // 🖥️ Pré-selecionar e travar tipo de script pelo SO do servidor
        const cmdTypeSelect = document.getElementById('commandType');
        if (serverOS && cmdTypeSelect) {
            cmdTypeSelect.value = serverOS.command_type;
            cmdTypeSelect.disabled = true;
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
    // 🖥️ Travar tipo de script pelo SO do servidor
    const editCmdTypeSelect = document.getElementById('editCommandType');
    if (serverOS && editCmdTypeSelect) {
        editCmdTypeSelect.disabled = true;
    }
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
                <h6>${escapeHtml(command.name)}</h6>
                <p class="text-muted">${escapeHtml(command.description || 'Sem descrição')}</p>
                <span class="badge bg-secondary">${getCommandTypeText(command.type)}</span>
            </div>
            <pre class="code-viewer code-wrap"><code>${escapeHtml(command.script)}</code></pre>
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
