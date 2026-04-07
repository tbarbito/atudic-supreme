// =====================================================================
// INTEGRATION-AUTH.JS
// Gerenciamento de usuários, senhas, licença, primeiro acesso
// =====================================================================

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

    // Popular checkboxes de ambientes dinamicamente
    const envContainer = document.getElementById('userEnvironments');
    if (envContainer) {
        envContainer.innerHTML = environments.map(e => `
            <div class="form-check">
                <input class="form-check-input user-env-check" type="checkbox" value="${e.id}" id="userEnv_${e.id}" checked>
                <label class="form-check-label" for="userEnv_${e.id}">${escapeHtml(e.name)}</label>
            </div>
        `).join('');
    }

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

                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-server me-1"></i>Ambientes com Acesso *
                                </label>
                                <div id="userEnvironments" class="border rounded p-2" style="max-height:150px;overflow-y:auto">
                                </div>
                                <small class="text-muted">Obrigatório selecionar pelo menos 1 ambiente</small>
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

        // Coletar ambientes selecionados
        const environmentIds = [...document.querySelectorAll('#userEnvironments .user-env-check:checked')]
            .map(cb => parseInt(cb.value));

        // Validações
        if (!name || !username || !email || !password || !profile) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }

        if (password !== passwordConfirm) {
            showNotification('Senhas não conferem!', 'error');
            return;
        }

        if (environmentIds.length === 0) {
            showNotification('Selecione pelo menos 1 ambiente!', 'error');
            return;
        }

        const userData = {
            username,
            name,
            email,
            password,
            profile,
            active,
            session_timeout_minutes: timeout,
            environment_ids: environmentIds
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

        // Coletar ambientes selecionados
        const environmentIds = [...document.querySelectorAll('#editUserEnvironments .edit-user-env-check:checked')]
            .map(cb => parseInt(cb.value));

        if (!name || !email || !profile) {
            showNotification('Preencha todos os campos obrigatórios!', 'error');
            return;
        }

        if (environmentIds.length === 0) {
            showNotification('Selecione pelo menos 1 ambiente!', 'error');
            return;
        }

        const userData = {
            name,
            email,
            profile,
            active,
            session_timeout_minutes: timeout,
            environment_ids: environmentIds
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

    // Popular checkboxes de ambientes dinamicamente
    const editEnvContainer = document.getElementById('editUserEnvironments');
    if (editEnvContainer) {
        editEnvContainer.innerHTML = environments.map(e => `
            <div class="form-check">
                <input class="form-check-input edit-user-env-check" type="checkbox" value="${e.id}" id="editUserEnv_${e.id}">
                <label class="form-check-label" for="editUserEnv_${e.id}">${escapeHtml(e.name)}</label>
            </div>
        `).join('');
    }

    // Marcar ambientes vinculados ao usuário
    document.querySelectorAll('#editUserEnvironments .edit-user-env-check').forEach(cb => {
        cb.checked = (user.environment_ids || []).includes(parseInt(cb.value));
    });

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

                            <div class="mb-3">
                                <label class="form-label">
                                    <i class="fas fa-server me-1"></i>Ambientes com Acesso *
                                </label>
                                <div id="editUserEnvironments" class="border rounded p-2" style="max-height:150px;overflow-y:auto">
                                </div>
                                <small class="text-muted">Obrigatório selecionar pelo menos 1 ambiente</small>
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
// ALTERAÇÃO DE SENHA DO PRÓPRIO USUÁRIO
// =====================================================================

function showChangeOwnPasswordModal() {
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
            const data = await apiRequest('/license/validate-admin', 'POST', { username, password });

            if (data.success) {
                window.location.href = data.redirect || '/activate';
            } else {
                errorDiv.textContent = data.error || 'Acesso negado';
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Erro ao validar acesso:', error);
            errorDiv.textContent = error.message || 'Erro de conexao com o servidor';
            errorDiv.style.display = 'block';
        }
    });
}

// =====================================================================
// PRIMEIRO ACESSO - Criação do Admin do Cliente
// =====================================================================

async function checkFirstAccess() {
    try {
        const data = await apiRequest('/first-access/check');

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
            const data = await apiRequest('/first-access/create', 'POST', { username, name, email, password });

            if (data.success) {
                successDiv.innerHTML = `<i class="fas fa-check-circle me-1"></i>${escapeHtml(data.message)}`;
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

// =====================================================================
// ESQUECI MINHA SENHA - Recuperação por E-mail
// =====================================================================

function setupForgotPasswordModal() {
    const btnForgot = document.getElementById('btnForgotPassword');
    const forgotModal = document.getElementById('forgotPasswordModal');
    const closeForgotBtn = document.getElementById('closeForgotPasswordModal');
    const forgotForm = document.getElementById('forgotPasswordForm');
    const forgotError = document.getElementById('forgotPasswordError');
    const forgotSuccess = document.getElementById('forgotPasswordSuccess');

    const resetModal = document.getElementById('resetPasswordModal');
    const closeResetBtn = document.getElementById('closeResetPasswordModal');
    const resetForm = document.getElementById('resetPasswordForm');
    const resetError = document.getElementById('resetPasswordError');
    const resetSuccess = document.getElementById('resetPasswordSuccess');

    if (!btnForgot || !forgotModal || !resetModal) return;

    // Abrir modal de solicitar recuperação
    btnForgot.addEventListener('click', (e) => {
        e.preventDefault();
        forgotModal.style.display = 'block';
        document.getElementById('forgotPasswordEmail').value = '';
        forgotError.style.display = 'none';
        forgotSuccess.style.display = 'none';
        document.getElementById('forgotPasswordEmail').focus();
    });

    // Fechar modal de solicitar recuperação
    closeForgotBtn.addEventListener('click', () => {
        forgotModal.style.display = 'none';
    });

    window.addEventListener('click', (e) => {
        if (e.target === forgotModal) {
            forgotModal.style.display = 'none';
        }
        if (e.target === resetModal) {
            resetModal.style.display = 'none';
        }
    });

    // Submit - solicitar recuperação
    forgotForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const email = document.getElementById('forgotPasswordEmail').value.trim();
        forgotError.style.display = 'none';
        forgotSuccess.style.display = 'none';

        if (!email) {
            forgotError.textContent = 'Informe seu e-mail';
            forgotError.style.display = 'block';
            return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            forgotError.textContent = 'Digite um e-mail válido';
            forgotError.style.display = 'block';
            return;
        }

        const submitBtn = document.getElementById('btnForgotPasswordSubmit');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Enviando...';
        submitBtn.disabled = true;

        try {
            const data = await apiForgotPassword(email);
            forgotSuccess.innerHTML = `<i class="fas fa-check-circle me-1"></i>${escapeHtml(data.message)}`;
            forgotSuccess.style.display = 'block';
            forgotForm.reset();

            // Após 2.5s, fechar modal e abrir o de redefinição
            setTimeout(() => {
                forgotModal.style.display = 'none';
                openResetPasswordModal();
            }, 2500);
        } catch (error) {
            forgotError.textContent = error.message || 'Erro ao enviar. Tente novamente.';
            forgotError.style.display = 'block';
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    });

    // Função para abrir modal de redefinição
    function openResetPasswordModal() {
        resetModal.style.display = 'block';
        document.getElementById('resetPasswordToken').value = '';
        document.getElementById('resetPasswordNew').value = '';
        document.getElementById('resetPasswordConfirm').value = '';
        resetError.style.display = 'none';
        resetSuccess.style.display = 'none';
        document.getElementById('resetPasswordToken').focus();
    }

    // Fechar modal de redefinição
    closeResetBtn.addEventListener('click', () => {
        resetModal.style.display = 'none';
    });

    // Submit - redefinir senha
    resetForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const token = document.getElementById('resetPasswordToken').value.trim();
        const newPassword = document.getElementById('resetPasswordNew').value;
        const confirmPassword = document.getElementById('resetPasswordConfirm').value;

        resetError.style.display = 'none';
        resetSuccess.style.display = 'none';

        if (!token || !newPassword || !confirmPassword) {
            resetError.textContent = 'Preencha todos os campos';
            resetError.style.display = 'block';
            return;
        }

        if (newPassword !== confirmPassword) {
            resetError.textContent = 'As senhas não conferem';
            resetError.style.display = 'block';
            return;
        }

        if (newPassword.length < 6) {
            resetError.textContent = 'A senha deve ter no mínimo 6 caracteres';
            resetError.style.display = 'block';
            return;
        }

        const submitBtn = document.getElementById('btnResetPasswordSubmit');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Redefinindo...';
        submitBtn.disabled = true;

        try {
            const data = await apiResetPassword(token, newPassword);
            resetSuccess.innerHTML = `<i class="fas fa-check-circle me-1"></i>${escapeHtml(data.message)}`;
            resetSuccess.style.display = 'block';
            resetForm.reset();

            // Fechar modal após 2s e focar no login
            setTimeout(() => {
                resetModal.style.display = 'none';
                document.getElementById('password').focus();
            }, 2000);
        } catch (error) {
            resetError.textContent = error.message || 'Erro ao redefinir. Tente novamente.';
            resetError.style.display = 'block';
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    });
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
                                <strong>${escapeHtml(user.username)}</strong>
                                ${isTargetRootAdmin ? '<i class="fas fa-crown text-warning ms-2" title="Root Admin"></i>' : ''}
                            </td>
                            <td>${escapeHtml(user.name || user.username)}</td>
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
                                    <button class="btn btn-outline-info"
                                            data-action="showPermissionOverridesModal"
                                            data-params='{"userId":${user.id}}'
                                            title="Permissões detalhadas">
                                        <i class="fas fa-user-shield"></i>
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


// =====================================================================
// RBAC HIBRIDO - PERMISSION OVERRIDES
// =====================================================================

// Cache do catalogo de permissoes (carregado 1x por sessao)
let _permissionCatalog = null;
let _permissionRoles = null;

async function loadPermissionCatalog() {
    if (_permissionCatalog) return _permissionCatalog;
    try {
        const data = await apiRequest('/permissions/catalog');
        _permissionCatalog = data.catalog;
        _permissionRoles = data.roles;
        return _permissionCatalog;
    } catch (e) {
        console.error('Erro ao carregar catalogo de permissoes:', e);
    }
    return null;
}

async function showPermissionOverridesModal({ userId }) {
    if (!isAdmin()) {
        showNotification('Acesso negado!', 'error');
        return;
    }

    // Carregar catalogo e permissoes do usuario em paralelo
    let permData;
    try {
        const [catalog_, permData_] = await Promise.all([
            loadPermissionCatalog(),
            apiRequest(`/users/${userId}/permissions`)
        ]);
        if (!catalog_) {
            showNotification('Erro ao carregar catalogo de permissoes', 'error');
            return;
        }
        var catalog = catalog_;
        permData = permData_;
    } catch (e) {
        showNotification('Erro ao carregar permissoes', 'error');
        return;
    }

    if (permData.is_root) {
        showNotification('Root admin tem permissão total — não aceita overrides', 'warning');
        return;
    }

    // Agrupar catalogo por resource
    const groups = {};
    catalog.forEach(entry => {
        if (entry.resource === 'system') return;
        if (!groups[entry.resource]) groups[entry.resource] = [];
        groups[entry.resource].push(entry);
    });

    // Mapear overrides por key
    const overrideMap = {};
    (permData.overrides || []).forEach(o => {
        overrideMap[o.permission_key] = o;
    });

    // Permissoes do perfil base
    const roleKeys = new Set(_permissionRoles[permData.profile] || []);

    // Gerar HTML
    const resourceLabels = {
        // Admin
        users: 'Usuários', environments: 'Ambientes', settings: 'Configurações',
        license: 'Licença', api_keys: 'Chaves de API',
        // CI/CD
        pipelines: 'Pipelines', schedules: 'Agendamentos', commands: 'Comandos',
        service_actions: 'Ações de Serviço', variables: 'Variáveis', services: 'Serviços',
        webhooks: 'Webhooks', processes: 'Processos de Negócio',
        // Repositórios
        repositories: 'Repositórios', source_control: 'Source Control',
        github_settings: 'Configurações GitHub',
        // Monitoramento
        observability: 'Observabilidade', database_connections: 'Conexões de Banco',
        auditor: 'Auditor INI',
        // IA
        agent: 'Agente IA', knowledge: 'Base de Conhecimento',
        tdn: 'TDN', documentation: 'Documentação',
        // Workspace
        devworkspace: 'Workspace', dictionary: 'Dicionário Protheus',
        rpo: 'Análise RPO'
    };

    const actionLabels = {
        view: 'Visualizar', create: 'Criar', edit: 'Editar', delete: 'Excluir',
        execute: 'Executar', release: 'Liberar Release', sync: 'Sincronizar',
        manage: 'Gerenciar', chat: 'Conversar', tools: 'Executar Tools',
        search: 'Buscar', ingest: 'Ingerir', compare: 'Comparar',
        equalize: 'Equalizar', analyze: 'Analisar', query: 'Executar Query',
        acknowledge: 'Reconhecer Alertas', test: 'Testar', export: 'Exportar',
        edit_protected: 'Editar Protegidos'
    };

    const effectLabels = {
        inherited: '<span class="badge bg-secondary">Perfil</span>',
        GRANT: '<span class="badge bg-success">Concedido</span>',
        DENY: '<span class="badge bg-danger">Negado</span>',
        not_in_profile: '<span class="badge bg-dark">Sem acesso</span>'
    };

    let accordionHtml = '';
    Object.entries(groups).forEach(([resource, entries]) => {
        const label = resourceLabels[resource] || resource;
        const collapseId = `perm_collapse_${resource}`;

        let rowsHtml = entries.map(entry => {
            const key = entry.key;
            const override = overrideMap[key];
            const inProfile = roleKeys.has(key);
            const effectiveGranted = permData.permission_keys.includes(key);

            let currentState = 'inherited';
            if (override) {
                currentState = override.effect;
            } else if (!inProfile) {
                currentState = 'not_in_profile';
            }

            const effectiveIcon = effectiveGranted
                ? '<i class="fas fa-check-circle text-success" title="Acesso efetivo: Permitido"></i>'
                : '<i class="fas fa-times-circle text-danger" title="Acesso efetivo: Negado"></i>';

            const actionLabel = actionLabels[entry.action] || entry.action;

            return `
                <tr data-perm-key="${key}" data-user-id="${userId}"
                    data-override-id="${override ? override.id : ''}">
                    <td>${actionLabel}</td>
                    <td class="text-center">${inProfile ? '<i class="fas fa-check text-muted"></i>' : ''}</td>
                    <td class="text-center perm-override-cell">
                        ${override ? effectLabels[override.effect] : (inProfile ? effectLabels.inherited : effectLabels.not_in_profile)}
                    </td>
                    <td class="text-center">${effectiveIcon}</td>
                    <td class="text-end">
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-success btn-sm" title="Conceder (GRANT)"
                                    data-action="setPermOverride"
                                    data-params='${JSON.stringify({userId, key, effect: "GRANT"})}'>
                                <i class="fas fa-plus-circle"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm" title="Negar (DENY)"
                                    data-action="setPermOverride"
                                    data-params='${JSON.stringify({userId, key, effect: "DENY"})}'>
                                <i class="fas fa-minus-circle"></i>
                            </button>
                            ${override ? `
                            <button class="btn btn-outline-secondary btn-sm" title="Remover override (voltar ao perfil)"
                                    data-action="removePermOverride"
                                    data-params='${JSON.stringify({userId, overrideId: override.id})}'>
                                <i class="fas fa-undo"></i>
                            </button>` : ''}
                        </div>
                    </td>
                </tr>`;
        }).join('');

        // Contar overrides nesse resource
        const overrideCount = entries.filter(e => overrideMap[e.key]).length;
        const overrideBadge = overrideCount > 0
            ? ` <span class="badge bg-info">${overrideCount} override${overrideCount > 1 ? 's' : ''}</span>`
            : '';

        accordionHtml += `
            <div class="accordion-item">
                <h2 class="accordion-header">
                    <button class="accordion-button collapsed py-2" type="button"
                            data-bs-toggle="collapse" data-bs-target="#${collapseId}">
                        <i class="fas fa-layer-group me-2"></i>${label}${overrideBadge}
                    </button>
                </h2>
                <div id="${collapseId}" class="accordion-collapse collapse">
                    <div class="accordion-body p-0">
                        <table class="table table-sm table-hover mb-0">
                            <thead class="table-light">
                                <tr>
                                    <th>Ação</th>
                                    <th class="text-center" style="width:80px">Perfil</th>
                                    <th class="text-center" style="width:100px">Override</th>
                                    <th class="text-center" style="width:80px">Efetivo</th>
                                    <th class="text-end" style="width:120px">Ações</th>
                                </tr>
                            </thead>
                            <tbody>${rowsHtml}</tbody>
                        </table>
                    </div>
                </div>
            </div>`;
    });

    // Remover modal anterior se existir
    const existing = document.getElementById('permOverridesModal');
    if (existing) existing.remove();

    const modalHtml = `
        <div class="modal fade" id="permOverridesModal" tabindex="-1">
            <div class="modal-dialog modal-lg modal-dialog-scrollable">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-user-shield me-2"></i>Permissões Detalhadas
                            <small class="text-muted ms-2">
                                ${escapeHtml(permData.username)}
                                <span class="badge bg-${permData.profile === 'admin' ? 'danger' : permData.profile === 'operator' ? 'primary' : 'secondary'} ms-1">
                                    ${permData.profile}
                                </span>
                            </small>
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-info py-2 small">
                            <i class="fas fa-info-circle me-1"></i>
                            <strong>Perfil base:</strong> define permissões padrão.
                            <strong>Overrides:</strong> concedem (GRANT) ou negam (DENY) permissões individualmente.
                            DENY sempre prevalece sobre o perfil.
                        </div>
                        <div class="accordion" id="permAccordion">
                            ${accordionHtml}
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            <i class="fas fa-times me-1"></i>Fechar
                        </button>
                    </div>
                </div>
            </div>
        </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('permOverridesModal'));
    modal.show();
}

async function setPermOverride({ userId, key, effect }) {
    const reason = prompt(`Motivo para ${effect === 'GRANT' ? 'conceder' : 'negar'} "${key}":`);
    if (!reason) {
        showNotification('Motivo é obrigatório para auditoria', 'warning');
        return;
    }

    try {
        const data = await apiRequest(`/users/${userId}/permissions/overrides`, 'POST', { permission_key: key, effect, reason });
        showNotification(data.message || 'Override criado', 'success');
        const modal = bootstrap.Modal.getInstance(document.getElementById('permOverridesModal'));
        if (modal) modal.hide();
        setTimeout(() => showPermissionOverridesModal({ userId }), 300);
    } catch (e) {
        console.error('Erro ao criar override:', e);
        showNotification(e.message || 'Erro ao criar override', 'error');
    }
}

async function removePermOverride({ userId, overrideId }) {
    if (!confirm('Remover este override? O usuario voltara ao perfil base para esta permissao.')) return;

    try {
        const data = await apiRequest(`/users/${userId}/permissions/overrides/${overrideId}`, 'DELETE');
        showNotification('Override removido', 'success');
        const modal = bootstrap.Modal.getInstance(document.getElementById('permOverridesModal'));
        if (modal) modal.hide();
        setTimeout(() => showPermissionOverridesModal({ userId }), 300);
    } catch (e) {
        console.error('Erro ao remover override:', e);
        showNotification(e.message || 'Erro ao remover override', 'error');
    }
}

