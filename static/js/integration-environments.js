// =====================================================================
// INTEGRATION-ENVIRONMENTS.JS
// Gerenciamento de ambientes e feed de atividades
// =====================================================================

// =====================================================================
// FUNÇÕES DE AMBIENTES
// =====================================================================
function setupEnvironmentSelector() {
    const selectorContainer = document.getElementById('environment-selector-container');
    const selector = document.getElementById('environmentSelector');
    if (!selector || !selectorContainer) return;

    // Filtrar ambientes pelo acesso do usuário (root admin vê todos)
    const userEnvIds = currentUser && currentUser.environment_ids;
    const isRoot = currentUser && currentUser.username === 'admin';
    const visibleEnvs = (!isRoot && userEnvIds && userEnvIds.length > 0)
        ? environments.filter(env => userEnvIds.includes(env.id))
        : environments;

    selector.innerHTML = visibleEnvs.map(env =>
        `<option value="${env.id}">${escapeHtml(env.name)}</option>`
    ).join('');

    const activeEnvId = sessionStorage.getItem('active_environment_id');
    const activeEnvValid = visibleEnvs.some(env => String(env.id) === String(activeEnvId));
    if (activeEnvId && activeEnvValid) {
        selector.value = activeEnvId;
    } else if (visibleEnvs.length > 0) {
        selector.value = visibleEnvs[0].id;
        sessionStorage.setItem('active_environment_id', visibleEnvs[0].id);
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
                    <h5 class="mb-1"><i class="fas fa-layer-group text-primary me-2"></i>${escapeHtml(env.name)}</h5>
                    <p class="text-muted mb-0">${escapeHtml(env.description || 'Sem descrição')}</p>
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
            message = `<strong>${escapeHtml(event.user)}</strong> iniciou <em>${escapeHtml(event.pipeline_name)}</em>.`;
            break;
        case 'PIPELINE_FINISH':
            icon = event.status === 'success' ? 'fa-check-circle' : 'fa-times-circle';
            color = event.status === 'success' ? 'text-success' : 'text-danger';
            message = `Pipeline <em>${escapeHtml(event.pipeline_name)}</em> finalizada (${escapeHtml(event.status)}).`;
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
