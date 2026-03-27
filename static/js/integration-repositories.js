// =====================================================================
// INTEGRATION-REPOSITORIES.JS
// Operações de repositório, explorador, GitHub settings, branch selector
// =====================================================================

// =====================================================================
// FUNÇÕES DE REPOSITÓRIOS
// =====================================================================


async function discoverRepositories() {
    if (!gitHubSettings.configured) {
        showNotification('Configure o token GitHub primeiro!', 'warning');
        navigateToPage('settings');
        return;
    }

    showNotification('Descobrindo repositorios...', 'info');

    try {
        // Backend faz a chamada ao GitHub (token nunca sai do servidor)
        const repos = await apiDiscoverRepositories();

        // Salvar no backend
        await apiSaveRepositories(repos);

        // Recarregar do backend
        await loadRepositories();

        showNotification(`${repositories.length} repositorios descobertos e salvos!`, 'success');
        showRepositories();

    } catch (error) {
        console.error('Erro ao descobrir repositorios:', error);
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

function _getEnvSuffix() {
    const selector = document.getElementById('environmentSelector');
    if (!selector) return '???';
    const envName = selector.options[selector.selectedIndex]?.text || '';
    const map = { 'Produção': 'PRD', 'Homologação': 'HOM', 'Desenvolvimento': 'DEV', 'Testes': 'TST' };
    return map[envName] || envName.substring(0, 3).toUpperCase();
}

async function cloneRepositoryOnServer(repoId) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    showNotification('Buscando branches disponiveis...', 'info');

    try {
        // Busca branches remotas (GitHub) e locais (servidor) em paralelo
        const [remoteBranches, localBranches] = await Promise.all([
            apiListRemoteBranches(repo.id).catch(() => []),
            apiListBranches(repo.id).catch(() => [])
        ]);

        if (!remoteBranches || remoteBranches.length === 0) {
            showNotification('Nenhum branch encontrado no GitHub.', 'error');
            return;
        }

        // Identifica quais branches ja estao clonadas localmente
        const localSet = new Set(localBranches || []);
        // Remove da lista local a default_branch se for o fallback (nao clonada de verdade)
        if (localSet.size === 1 && localSet.has(repo.default_branch)) {
            // Pode ser fallback — verifica se aparece nas remotas tambem
            // Se sim, mantem; o usuario decide
        }

        // Monta HTML do modal de seleção
        const modalId = 'cloneBranchModal';
        let existingModal = document.getElementById(modalId);
        if (existingModal) existingModal.remove();

        const modalHtml = `
        <div class="modal fade" id="${modalId}" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-clone me-2"></i>Clonar/Resetar Branch</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="text-muted mb-3">Selecione a branch para clonar ou resetar no servidor:</p>
                        <div class="alert alert-warning small mb-3">
                            <i class="fas fa-exclamation-triangle me-1"></i>
                            Certifique-se de que a variavel <strong>BASE_DIR_${_getEnvSuffix()}</strong> esteja configurada em <em>Variaveis do Servidor</em> para o ambiente atual.
                        </div>
                        <div class="list-group">
                            ${remoteBranches.map(branch => {
                                const isCloned = localSet.has(branch);
                                return `
                                <button type="button" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
                                    onclick="executeClone(${repo.id}, '${escapeHtml(branch)}')">
                                    <div>
                                        <i class="fas fa-code-branch me-2"></i>
                                        <strong>${escapeHtml(branch)}</strong>
                                        ${branch === repo.default_branch ? ' <span class="badge bg-primary ms-1">default</span>' : ''}
                                    </div>
                                    ${isCloned
                                        ? '<span class="badge bg-warning text-dark"><i class="fas fa-sync-alt me-1"></i>Resetar</span>'
                                        : '<span class="badge bg-success"><i class="fas fa-download me-1"></i>Clonar</span>'}
                                </button>`;
                            }).join('')}
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                    </div>
                </div>
            </div>
        </div>`;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modal = new bootstrap.Modal(document.getElementById(modalId));
        modal.show();

    } catch (error) {
        showNotification(error.message || 'Erro ao buscar branches.', 'error');
    }
}

async function executeClone(repoId, branchName) {
    // Fecha o modal
    const modalEl = document.getElementById('cloneBranchModal');
    if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    }

    const repo = repositories.find(r => r.id === repoId);
    const repoName = repo ? repo.name : `repo ${repoId}`;

    const confirmation = confirm(
        `ATENCAO: A pasta "${repoName}/${branchName}" no servidor sera (re)criada.\n\nContinuar?`
    );
    if (!confirmation) {
        showNotification('Operacao cancelada.', 'info');
        return;
    }

    showNotification(`Clonando branch "${branchName}"...`, 'info');
    try {
        const result = await apiCloneRepository(repoId, branchName);
        showNotification(result.message, 'success');
        // Atualiza branch ativa e recarrega a lista
        if (repo) {
            currentBranch[repo.name] = branchName;
            currentPath[repo.name] = '';
        }
        document.getElementById('repositoriesContainer').innerHTML = renderRepositories();
    } catch (error) {
        showNotification(error.message || 'Erro ao clonar repositorio.', 'error');
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

    try {
        // Inicializa ou mantém o estado de navegação
        currentPath[repoName] = currentPath[repoName] || '';
        currentBranch[repoName] = currentBranch[repoName] || repo.default_branch;

        // Busca o conteúdo: via GitHub API (admin) ou via endpoint local (operador/viewer)
        const content = await loadRepositoryContent(repoName, currentPath[repoName]);

        // Renderiza a interface simplificada, sem passar a lista de branches
        showRepositoryExplorer(repo, content, currentPath[repoName]);

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
        selectBranch(repoId, newBranchName);

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
        // Busca branches locais (todos os perfis)
        const localBranches = await apiListBranches(repo.id).catch(() => []);
        const localSet = new Set(localBranches || []);

        // Admin/Operator: busca branches remotas tambem
        let remoteBranches = [];
        if (isAdmin() || isOperator()) {
            remoteBranches = await apiListRemoteBranches(repo.id).catch(() => []);
        }

        // Monta lista unificada: remote + local (sem duplicatas)
        const allBranches = new Set([...localBranches, ...remoteBranches]);

        if (allBranches.size === 0) {
            throw new Error('Nenhum branch encontrado.');
        }

        const activeBranch = currentBranch[repo.name] || repo.default_branch;

        // Se viewer e so tem 1 branch local, seleciona direto
        if (isViewer() && localBranches.length === 1) {
            selectBranch(repo.id, localBranches[0]);
            return;
        }

        // Ordena: default primeiro, depois alfabetico
        const sorted = [...allBranches].sort((a, b) => {
            if (a === repo.default_branch) return -1;
            if (b === repo.default_branch) return 1;
            return a.localeCompare(b);
        });

        // Dropdown estilizado com status local/origin
        const dropdownId = `branch-dropdown-${repo.id}`;
        const itemsHtml = sorted.map(branch => {
            const isLocal = localSet.has(branch);
            const isActive = branch === activeBranch;
            const statusBadge = isLocal
                ? '<span class="badge bg-success ms-auto">clonado</span>'
                : '<span class="badge bg-secondary ms-auto">somente origin</span>';
            const activeClass = isActive ? ' active' : '';
            const defaultBadge = branch === repo.default_branch
                ? ' <span class="badge bg-primary ms-1">default</span>' : '';

            return `
                <button type="button" class="list-group-item list-group-item-action d-flex align-items-center py-2${activeClass}"
                    onclick="selectBranch(${repo.id}, '${escapeHtml(branch)}'); document.getElementById('${dropdownId}').remove();">
                    <i class="fas fa-code-branch me-2 text-muted"></i>
                    <span>${escapeHtml(branch)}${defaultBadge}</span>
                    ${statusBadge}
                </button>`;
        }).join('');

        const dropdownHtml = `
            <div id="${dropdownId}" class="position-absolute shadow rounded border bg-body" style="z-index:1050; min-width:280px; max-height:250px; overflow-y:auto;">
                <div class="d-flex justify-content-between align-items-center px-3 py-2 border-bottom">
                    <small class="text-muted fw-bold">Selecionar branch</small>
                    <button type="button" class="btn-close btn-close-sm" onclick="document.getElementById('${dropdownId}').remove()"></button>
                </div>
                <div class="list-group list-group-flush">
                    ${itemsHtml}
                </div>
            </div>`;

        // Restaura o badge e insere o dropdown ao lado
        container.innerHTML = `
            <span class="badge bg-secondary">${escapeHtml(activeBranch)}</span>
            <button class="btn btn-link btn-sm p-0 ms-2" data-action="showBranchSelector" data-params='{"repoId":${repo.id}}'>Trocar</button>
        `;
        // Remove dropdown anterior se existir
        const existing = document.getElementById(dropdownId);
        if (existing) existing.remove();
        container.style.position = 'relative';
        container.insertAdjacentHTML('beforeend', dropdownHtml);

        // Fecha ao clicar fora
        const closeHandler = (e) => {
            const dd = document.getElementById(dropdownId);
            if (dd && !dd.contains(e.target) && !e.target.closest(`[data-params*='"repoId":${repo.id}']`)) {
                dd.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler), 100);

    } catch (error) {
        showNotification(error.message, 'error');
        container.innerHTML = `
            <span class="badge bg-secondary ms-1">${currentBranch[repo.name] || repo.default_branch}</span>
            <button class="btn btn-link btn-sm p-0 ms-2" data-action="showBranchSelector" data-params='{"repoId":${repo.id}}'>Trocar</button>
        `;
    }
}

function selectBranch(repoId, branchName) {
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    // Atualiza o estado global
    currentBranch[repo.name] = branchName;
    // Reset do path ao trocar branch (evita confusão path/branch no explorer)
    currentPath[repo.name] = '';
    showNotification(`Branch "${branchName}" selecionado para ${repo.name}.`, 'info');

    // Redesenha a lista de repositórios para refletir a mudança
    document.getElementById('repositoriesContainer').innerHTML = renderRepositories();
}

// =====================================================================
// FUNÇÕES DE CONFIGURAÇÕES GITHUB
// =====================================================================

async function saveGithubSettings() {
    try {
        const token = document.getElementById('githubToken').value.trim();
        const username = document.getElementById('githubUsername').value.trim();

        if (!token || !username) {
            showNotification('Preencha todos os campos!', 'error');
            return;
        }

        if (!token.startsWith('ghp_') && !token.startsWith('github_pat_')) {
            showNotification('Formato de token invalido. Deve comecar com "ghp_" ou "github_pat_".', 'error');
            return;
        }

        await apiSaveGithubSettings({ token, username });

        // Apenas marca como configurado (token nunca fica no frontend)
        gitHubSettings.configured = true;
        gitHubSettings.username = username;

        showNotification('Configuracoes GitHub salvas com sucesso!', 'success');

        // Apenas recarrega a própria tela de configurações para refletir o estado salvo
        showSettings();

    } catch (error) {
        console.error('Erro ao salvar configurações:', error);
        showNotification(error.message || 'Erro ao salvar configurações', 'error');
    }
}

async function testGithubConnection() {
    const token = document.getElementById('githubToken').value.trim();
    const username = document.getElementById('githubUsername').value.trim();
    const statusDiv = document.getElementById('connectionStatus');

    if (!token || !username) {
        showNotification('Preencha o Token e o Usuario para testar.', 'warning');
        return;
    }

    statusDiv.innerHTML = `<div class="text-info"><i class="fas fa-spinner fa-spin me-2"></i>Testando conexao...</div>`;

    try {
        // Testa via backend (token nao fica exposto no browser)
        const result = await apiTestGithubConnection(token, username);
        statusDiv.innerHTML = `
            <div class="alert alert-success mt-2">
                <i class="fas fa-check-circle me-2"></i>
                Conectado com sucesso como <strong>${result.login}</strong>!
            </div>
        `;
    } catch (error) {
        console.error('Erro no teste de conexao:', error);
        statusDiv.innerHTML = `
            <div class="alert alert-danger mt-2">
                <i class="fas fa-exclamation-circle me-2"></i>
                Erro na conexao: ${error.message}
            </div>
        `;
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



function showRepositories() {
    let content = '';
    if (!gitHubSettings.configured && canPerformAction('github_settings', 'view')) {
        // Só mostra aviso de "configurar GitHub" para quem pode configurar (admin)
        content = `
            <div class="card text-center p-5">
                <h4><i class="fab fa-github me-2"></i>Integração GitHub</h4>
                <p class="text-muted">A configuração do GitHub é necessária para descobrir e gerenciar repositórios.</p>
                <button class="btn btn-primary" onclick="window.location.hash='settings'">Ir para Configurações</button>
            </div>`;
    } else if (repositories.length === 0) {
        content = `
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2>Repositórios GitHub</h2>
                ${canPerformAction('repositories', 'sync') ? '<button class="btn btn-primary" data-action="discoverRepositories"><i class="fab fa-github me-2"></i>Sincronizar com GitHub</button>' : ''}
            </div>
            <div class="card text-center p-5">
                <p class="text-muted">Nenhum repositório sincronizado para este ambiente.</p>
            </div>`;
    } else {
        content = `
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2>Repositórios GitHub</h2>
                ${canPerformAction('repositories', 'sync') ? '<button class="btn btn-primary" data-action="discoverRepositories"><i class="fab fa-github me-2"></i>Sincronizar com GitHub</button>' : ''}
            </div>
            <div id="repositoriesContainer">${renderRepositories()}</div>`;
    }
    document.getElementById('content-area').innerHTML = content;

    // Viewer: verifica assincronamente quais repos tem branches locais
    if (isViewer() && repositories.length > 0) {
        checkViewerBranches();
    }
}

async function checkViewerBranches() {
    for (const repo of repositories) {
        const container = document.getElementById(`branch-container-${repo.id}`);
        if (!container) continue;

        try {
            const localBranches = await apiListBranches(repo.id).catch(() => []);
            if (!localBranches || localBranches.length === 0) {
                container.innerHTML = `<span class="text-muted small fst-italic">Nenhuma branch clonada no servidor</span>`;
            } else if (localBranches.length > 1) {
                // Tem branches clonadas — mostra botão Trocar
                const activeBranch = currentBranch[repo.name] || repo.default_branch;
                container.innerHTML = `
                    <span class="badge bg-secondary">${escapeHtml(activeBranch)}</span>
                    <button class="btn btn-link btn-sm p-0 ms-2" data-action="showBranchSelector" data-params='{"repoId":${repo.id}}'>Trocar</button>
                `;
            }
            // Se length === 1, mantém o badge padrão sem botão Trocar (só tem uma opção)
        } catch (e) {
            // Silencia erros — mantém o badge padrão
        }
    }
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
    // Permissões granulares para repositórios
    const canSync = canPerformAction('repositories', 'sync');
    const canEdit = canPerformAction('repositories', 'edit');
    const canDelete = canPerformAction('repositories', 'delete');

    if (repositories.length === 0) {
        return `
            <div class="card text-center p-5">
                <p class="text-muted">Nenhum repositório sincronizado para este ambiente.</p>
                ${canSync ? '<button class="btn btn-primary mt-3" data-action="discoverRepositories"><i class="fab fa-github me-2"></i>Sincronizar com GitHub</button>' : ''}
            </div>`;
    }

    return `
    <div class="row">
        ${repositories.map(repo => {
        const selectedBranch = currentBranch[repo.name] || repo.default_branch;
        return `
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-0 text-truncate" title="${escapeHtml(repo.name)}">
                                <i class="fas fa-${repo.private ? 'lock' : 'globe'} me-2"></i>
                                ${escapeHtml(repo.name)}
                            </h6>
                            <small class="text-muted">${repo.private ? 'Privado' : 'Público'}</small>
                        </div>
                        <div class="dropdown">
                            <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown">
                                <i class="fas fa-ellipsis-v"></i>
                            </button>
                            <ul class="dropdown-menu dropdown-menu-end">
                                <li><a class="dropdown-item" href="#" data-action="exploreRepository" data-params='{"repoName":"${escapeHtml(repo.name)}"}'><i class="fas fa-folder-open me-2"></i>Explorar Arquivos</a></li>
                                ${canSync ? `
                                    <li><a class="dropdown-item" href="${repo.html_url}" target="_blank"><i class="fab fa-github me-2"></i>Ver no GitHub</a></li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item" href="#" data-action="createNewBranch" data-params='{"repoId":${repo.id}}'><i class="fas fa-code-branch me-2"></i>Criar Branch</a></li>
                                    <li><a class="dropdown-item" href="#" data-action="cloneRepository" data-params='{"repoId":${repo.id}}'><i class="fas fa-clone me-2"></i>Clonar/Resetar</a></li>
                                ` : ''}
                                ${canDelete ? `
                                    <li><hr class="dropdown-divider"></li>
                                    <li><a class="dropdown-item text-danger" href="#" data-action="deleteRepository" data-params='{"repoId":${repo.id}}'><i class="fas fa-trash me-2"></i>Remover da Lista</a></li>
                                ` : ''}
                            </ul>
                        </div>
                    </div>
                    <div class="card-body">
                        <p class="card-text text-muted small" style="height: 3em; overflow: hidden;">${escapeHtml(repo.description || 'Sem descrição')}</p>
                        <div class="d-flex align-items-center mt-3">
                            <i class="fas fa-code-branch me-2 text-muted"></i>
                            <div id="branch-container-${repo.id}" class="d-flex align-items-center">
                                <span class="badge bg-secondary">${escapeHtml(selectedBranch)}</span>
                                ${!isViewer() ? `<button class="btn btn-link btn-sm p-0 ms-2" data-action="showBranchSelector" data-params='{"repoId":${repo.id}}'>Trocar</button>` : ''}
                            </div>
                        </div>
                    </div>
                    <div class="card-footer">
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">Atualizado: ${formatDate(repo.updated_at)}</small>
                            ${canEdit ? `
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

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

async function loadRepositoryContent(repoName, path = '') {
    const repo = repositories.find(r => r.name === repoName);
    const branch = currentBranch[repoName] || repo.default_branch;
    // Sempre usa endpoint local (mais rápido, funciona para todos os perfis)
    return await apiListLocalFiles(repo.id, path, branch);
}
function showRepositoryExplorer(repo, content, currentPath) { // O parâmetro 'branches' foi removido
    const activeBranch = currentBranch[repo.name] || repo.default_branch;
    const explorerContent = `
    <div class="repo-explorer-layout">
        <div class="repo-explorer-header">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <h2 class="mb-1">
                        <button class="btn btn-link p-0 text-decoration-none" data-action="navigate" data-params=\'{"page":"repositories"}\'>
                            <i class="fas fa-arrow-left me-2"></i>Repositórios GitHub
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
                    ${canPerformAction('repositories', 'edit') ? `
                    <button class="btn btn-sm btn-outline-primary" data-action="pullRepository" data-params=\'{"repoId":${repo.id}}\'>
                        <i class="fas fa-arrow-down me-2"></i>Pull (Forçado)
                    </button>
                    <button class="btn btn-sm btn-outline-success" data-action="pushChanges" data-params=\'{"repoId":${repo.id}}\'>
                        <i class="fas fa-arrow-up me-2"></i>Push Alterações
                    </button>
                    ` : ''}
                </div>
            </div>
            <div class="d-flex align-items-center">
                ${currentPath ? `
                        <button class="btn btn-sm btn-outline-secondary me-3" data-action="goBackPath" data-params=\'{"repoName":"${repo.name}"}\'>
                            <i class="fas fa-arrow-left"></i> Voltar
                        </button>
                    ` : ''}
                ${renderBreadcrumb(repo.name, currentPath)}
            </div>
        </div>
        <div class="repo-explorer-content">
            <div class="card">
                <div class="card-body">
                    ${renderRepositoryContent(repo, content, currentPath)}
                </div>
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
                ${content.download_url ? `<a href="${content.download_url}" class="btn btn-outline-success" target="_blank"><i class="fas fa-download"></i> Download</a>` : ''}
                ${content.html_url ? `<a href="${content.html_url}" class="btn btn-outline-primary" target="_blank"><i class="fab fa-github"></i> GitHub</a>` : ''}
            </div>
        </div>
        <p class="text-muted">Tamanho: ${formatSize(content.size)}</p>
    </div>
    ${isText ? `
                <pre class="code-viewer code-scroll-lg rounded"><code>${(() => {
                    try {
                        const raw = atob(content.content);
                        const ext = (content.name || '').split('.').pop().toLowerCase();
                        const isAdvpl = ['prw','prx','tlpp','aph','ch'].includes(ext);
                        const text = isAdvpl ? raw : decodeURIComponent(escape(raw));
                        return addLineNumbers(highlightCode(escapeHtml(text), ext));
                    } catch (e) { return escapeHtml(atob(content.content || '')); }
                })()}</code></pre>
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
                                         ${item.download_url ? `<a href="${item.download_url}" class="btn btn-outline-success" target="_blank"><i class="fas fa-download"></i> Download</a>` : ''}`
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

