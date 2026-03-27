// api-client.js - Cliente para comunicação com o backend

const API_BASE_URL = '/api';
let authToken = sessionStorage.getItem('auth_token') || null;

// =====================================================================
// FUNÇÕES AUXILIARES
// =====================================================================

function getHeaders() {
    const headers = {
        'Content-Type': 'application/json'
    };

    if (authToken) {
        headers['Authorization'] = authToken;
    }
    const activeEnvironmentId = sessionStorage.getItem('active_environment_id');
    if (activeEnvironmentId) {
        headers['X-Environment-Id'] = activeEnvironmentId;
    }

    return headers;
}

async function apiRequest(endpoint, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: getHeaders()
    };

    if (data && (method === 'POST' || method === 'PUT')) {
        options.body = JSON.stringify(data);
    }

try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
        
        if (!response.ok) {
            const responseData = await response.json().catch(() => ({ error: 'Resposta inválida do servidor' }));
            const error = new Error(responseData.error || `Erro ${response.status}`);
            error.status = response.status; // << NOVO: Anexar o status ao erro
            throw error;
        }

        return await response.json();
    } catch (error) {
        // Log detalhado para debugging
        console.error('Erro na API:', {
            endpoint: endpoint,
            method: method,
            status: error.status,
            message: error.message
        });
        throw error;
    }
}

// =====================================================================
// AUTENTICAÇÃO
// =====================================================================

async function apiLogin(username, password, force = false) {
    const response = await apiRequest('/login', 'POST', { username, password, force });

    if (response.success) {
        authToken = response.token;
        sessionStorage.setItem('auth_token', authToken);
        return response.user;
    }

    throw new Error('Login falhou');
}

async function apiLogout() {
    try {
        await apiRequest('/logout', 'POST');
    } catch (error) {
        if (error.status === 401) {
            console.warn('Sessão já expirada no servidor, limpando localmente');
        } else {
            console.error('Erro no logout da API:', error.message);
        }
    } finally {
        authToken = null;
        sessionStorage.removeItem('auth_token');
        sessionStorage.removeItem('active_environment_id');
    }
}

async function apiCheckSession() {
    if (!authToken) {
        throw new Error('Nenhum token de sessão encontrado');
    }
    return await apiRequest('/me');
}

async function apiChangeOwnPassword(passwordData) {
    /**
     * Altera a senha do usuário logado.
     *
     * @param {Object} passwordData - Dados das senhas
     * @param {string} passwordData.current_password - Senha atual
     * @param {string} passwordData.new_password - Nova senha
     * @returns {Promise} Resposta da API
     */
    return await apiRequest('/me/password', 'POST', passwordData);
}

async function apiForgotPassword(email) {
    return await apiRequest('/forgot-password', 'POST', { email });
}

async function apiResetPassword(token, new_password) {
    return await apiRequest('/reset-password', 'POST', { token, new_password });
}

// =====================================================================
// SISTEMA
// =====================================================================

async function apiGetSystemInfo() {
    return await apiRequest('/system/info');
}

// =====================================================================
// SESSÃO
// =====================================================================

async function apiKeepAlive() {
    try {
        await apiRequest('/session/keep-alive', 'POST');
    } catch (error) {
        console.warn('Ping de keep-alive falhou.', error);
        // Se receber 401, sessão expirou - fazer logout
        if (error.status === 401) {
            console.log('Sessão expirada por inatividade. Fazendo logout...');
            if (typeof logout === 'function') {
                logout(true);  // force=true para não mostrar notificação
            } else {
                sessionStorage.clear();
                window.location.reload();
            }
        }
    }
}

// =====================================================================
// USUÁRIOS
// =====================================================================

async function apiGetUsers() {
    return await apiRequest('/users');
}

async function apiCreateUser(userData) {
    return await apiRequest('/users', 'POST', userData);
}

async function apiUpdateUser(userId, userData) {
    return await apiRequest(`/users/${userId}`, 'PUT', userData);
}

async function apiDeleteUser(userId) {
    return await apiRequest(`/users/${userId}`, 'DELETE');
}

async function apiAdminChangePassword(userId, passwordData) {
    /**
     * Admin altera senha de outro usuário.
     * 
     * @param {number} userId - ID do usuário alvo
     * @param {Object} passwordData - Dados das senhas
     * @param {string} passwordData.admin_password - Senha do admin (autorização)
     * @param {string} passwordData.new_password - Nova senha do usuário
     * @returns {Promise} Resposta da API
     */
    return await apiRequest(`/users/${userId}/password`, 'PUT', passwordData);
}
// =====================================================================
// COMANDOS
// =====================================================================

// 🆕 Atualizada para suportar filtro de command_category
async function apiGetCommands() {
    return await apiRequest('/commands');
}

async function apiCreateCommand(commandData) {
    return await apiRequest('/commands', 'POST', commandData);
}

async function apiUpdateCommand(commandId, commandData) {
    return await apiRequest(`/commands/${commandId}`, 'PUT', commandData);
}

async function apiDeleteCommand(commandId) {
    return await apiRequest(`/commands/${commandId}`, 'DELETE');
}

// =====================================================================
// PIPELINES
// =====================================================================

async function apiGetPipelines() {
    return await apiRequest('/pipelines');
}

async function apiCreatePipeline(pipelineData) {
    return await apiRequest('/pipelines', 'POST', pipelineData);
}

async function apiUpdatePipeline(pipelineId, pipelineData) {
    return await apiRequest(`/pipelines/${pipelineId}`, 'PUT', pipelineData);
}

async function apiDeletePipeline(pipelineId) {
    return await apiRequest(`/pipelines/${pipelineId}`, 'DELETE');
}

async function apiRunPipeline(pipelineId) {
    return await apiRequest(`/pipelines/${pipelineId}/run`, 'POST');
}

// =====================================================================
// PIPELINES - BUILD & RELEASE (CI/CD)
// =====================================================================

async function apiGetPipelineRuns(pipelineId, page = 1, limit = 20) {
    return await apiRequest(`/pipelines/${pipelineId}/runs?page=${page}&limit=${limit}`);
}

async function apiGetRunLogs(runId) {
    return await apiRequest(`/runs/${runId}/logs`);
}

async function apiCreateRelease(pipelineId, data = {}) {
    /**
     * DEPRECADO: Use apiCreateReleaseFromRun(runId) no lugar.
     * 
     * Esta função ainda existe para compatibilidade, mas o correto
     * é criar releases associados a runs, não a pipelines.
     */
    console.warn('⚠️  apiCreateRelease está deprecated. Use apiCreateReleaseFromRun(runId)');
    return await apiRequest(`/pipelines/${pipelineId}/release`, 'POST', data);
}

async function apiCreateReleaseFromRun(runId) {
    /**
     * Cria um release (deploy) a partir de um RUN específico.
     * Valida automaticamente se o RUN foi bem-sucedido.
     * 
     * @param {number} runId - ID do run (build) que será deployado
     * @returns {Promise} Resposta contendo release_id e message
     */
    return await apiRequest(`/runs/${runId}/release`, 'POST');
}

async function apiGetPipelineReleases(pipelineId, page = 1, limit = 20) {
    return await apiRequest(`/pipelines/${pipelineId}/releases?page=${page}&limit=${limit}`);
}

async function apiGetRunReleases(runId) {
    /**
     * Busca releases associados a um RUN específico.
     * Usado para verificar se uma build teve deploy com sucesso.
     */
    return await apiRequest(`/runs/${runId}/releases`);
}

async function apiGetReleaseLogs(releaseId) {
    return await apiRequest(`/releases/${releaseId}/logs`);
}


// =====================================================================
// DEPLOYS
// =====================================================================

async function apiGetDeploys() {
    return await apiRequest('/deploys');
}

async function apiCreateDeploy(deployData) {
    return await apiRequest('/deploys', 'POST', deployData);
}

async function apiUpdateDeploy(deployId, deployData) {
    return await apiRequest(`/deploys/${deployId}`, 'PUT', deployData);
}

async function apiDeleteDeploy(deployId) {
    return await apiRequest(`/deploys/${deployId}`, 'DELETE');
}

async function apiRunDeploy(pipelineId) {
    return await apiRequest(`/pipelines/${pipelineId}/run-deploy`, 'POST');
}

// =====================================================================
// AMBIENTES
// =====================================================================

async function apiGetEnvironments() {
    return await apiRequest('/environments');
}

async function apiCreateEnvironment(environmentData) {
    return await apiRequest('/environments', 'POST', environmentData);
}

async function apiUpdateEnvironment(envId, environmentData) {
    return await apiRequest(`/environments/${envId}`, 'PUT', environmentData);
}

async function apiDeleteEnvironment(envId) {
    return await apiRequest(`/environments/${envId}`, 'DELETE');
}

// =====================================================================
// REPOSITÓRIOS
// =====================================================================

async function apiGetRepositories() {
    return await apiRequest('/repositories');
}

async function apiSaveRepositories(repositoriesData) {
    return await apiRequest('/repositories', 'POST', repositoriesData);
}

async function apiDeleteRepository(repoId) {
    return await apiRequest(`/repositories/${repoId}`, 'DELETE');
}

async function apiCloneRepository(repoId, branchName) {
    return await apiRequest(`/repositories/${repoId}/clone`, 'POST', { branch_name: branchName });
}

async function apiPullRepository(repoId, branchName) {
    return await apiRequest(`/repositories/${repoId}/pull`, 'POST', { branch_name: branchName });
}

async function apiPushTag(repoId, tagData) {
    return await apiRequest(`/repositories/${repoId}/tag`, 'POST', tagData);
}

async function apiPushChanges(repoId, commitData) { // commitData já inclui o branch
    return await apiRequest(`/repositories/${repoId}/push`, 'POST', commitData);
}

async function apiListBranches(repoId) {
    return await apiRequest(`/repositories/${repoId}/branches`);
}

async function apiListRemoteBranches(repoId) {
    return await apiRequest(`/repositories/${repoId}/remote-branches`);
}

async function apiCreateBranch(repoId, branchData) {
    return await apiRequest(`/repositories/${repoId}/branch`, 'POST', branchData);
}

async function apiListLocalFiles(repoId, path = '', branch = '') {
    const params = new URLSearchParams();
    if (path) params.set('path', path);
    if (branch) params.set('branch', branch);
    return await apiRequest(`/repositories/${repoId}/files?${params.toString()}`);
}

// =====================================================================
// INTEGRAÇÃO GITHUB
// =====================================================================

async function apiGetGithubSettings() {
    return await apiRequest('/github-settings');
}

async function apiSaveGithubSettings(settingsData) {
    return await apiRequest('/github-settings', 'POST', settingsData);
}

async function apiDiscoverRepositories() {
    return await apiRequest('/github/discover', 'POST');
}

async function apiTestGithubConnection(token, username) {
    return await apiRequest('/github/test-connection', 'POST', { token, username });
}

async function apiGetGithubStatus() {
    return await apiRequest('/github/status');
}

// =====================================================================
// SOURCE CONTROL
// =====================================================================

async function apiGetGitStatus(repoId, branch) {
    const t = Date.now();
    return await apiRequest(`/repositories/${repoId}/status?branch=${encodeURIComponent(branch)}&_t=${t}`);
}

async function apiGetFileDiff(repoId, branch, filePath, staged = false, untracked = false) {
    const params = new URLSearchParams({ branch, file_path: filePath, staged: staged.toString(), untracked: untracked.toString(), _t: Date.now() });
    return await apiRequest(`/repositories/${repoId}/diff?${params.toString()}`);
}

async function apiGetCommitLog(repoId, branch, limit = 20) {
    const t = Date.now();
    return await apiRequest(`/repositories/${repoId}/log?branch=${encodeURIComponent(branch)}&limit=${limit}&_t=${t}`);
}

async function apiStageFiles(repoId, data) {
    return await apiRequest(`/repositories/${repoId}/stage`, 'POST', data);
}

async function apiCommitChanges(repoId, data) {
    return await apiRequest(`/repositories/${repoId}/commit`, 'POST', data);
}

async function apiPushOnly(repoId, data) {
    return await apiRequest(`/repositories/${repoId}/push-only`, 'POST', data);
}

async function apiDiscardChanges(repoId, data) {
    return await apiRequest(`/repositories/${repoId}/discard`, 'POST', data);
}

async function apiGetCommitFiles(repoId, branch, hash) {
    const t = Date.now();
    return await apiRequest(`/repositories/${repoId}/commit-files?branch=${encodeURIComponent(branch)}&hash=${encodeURIComponent(hash)}&_t=${t}`);
}

async function apiGetCommitDiff(repoId, branch, hash, filePath) {
    const t = Date.now();
    return await apiRequest(`/repositories/${repoId}/commit-diff?branch=${encodeURIComponent(branch)}&hash=${encodeURIComponent(hash)}&file_path=${encodeURIComponent(filePath)}&_t=${t}`);
}

// =====================================================================
// CONFIGURAÇÕES DO SISTEMA
// =====================================================================

async function apiGetServerVariables() {
    return await apiRequest('/server-variables');
}

async function apiCreateServerVariable(variableData) {
    return await apiRequest('/server-variables', 'POST', variableData);
}

async function apiUpdateServerVariable(varId, variableData) {
    return await apiRequest(`/server-variables/${varId}`, 'PUT', variableData);
}

async function apiDeleteServerVariable(varId) {
    return await apiRequest(`/server-variables/${varId}`, 'DELETE');
}

async function apiGetServerServices() {
    return await apiRequest('/server-services');
}

async function apiCreateServerService(serviceData) {
    return await apiRequest('/server-services', 'POST', serviceData);
}

async function apiUpdateServerService(serviceId, serviceData) {
    return await apiRequest(`/server-services/${serviceId}`, 'PUT', serviceData);
}

async function apiDeleteServerService(serviceId) {
    return await apiRequest(`/server-services/${serviceId}`, 'DELETE');
}

// =====================================================================
// API - SCHEDULES
// =====================================================================

async function apiGetSchedules() {
    return apiRequest('/schedules', 'GET');
}

async function apiCreateSchedule(data) {
    return apiRequest('/schedules', 'POST', data);
}

async function apiUpdateSchedule(scheduleId, data) {
    return apiRequest(`/schedules/${scheduleId}`, 'PUT', data);
}

async function apiToggleSchedule(scheduleId) {
    return apiRequest(`/schedules/${scheduleId}/toggle`, 'PATCH');
}

async function apiDeleteSchedule(scheduleId) {
    return apiRequest(`/schedules/${scheduleId}`, 'DELETE');
}

// =====================================================================
// API - SERVICE ACTIONS
// =====================================================================

async function apiGetServiceActions() {
    return apiRequest('/service-actions', 'GET');
}

async function apiCreateServiceAction(data) {
    return apiRequest('/service-actions', 'POST', data);
}

async function apiUpdateServiceAction(actionId, data) {
    return apiRequest(`/service-actions/${actionId}`, 'PUT', data);
}

async function apiDeleteServiceAction(actionId) {
    return apiRequest(`/service-actions/${actionId}`, 'DELETE');
}

async function apiExecuteServiceAction(actionId) {
    return apiRequest(`/service-actions/${actionId}/execute`, 'POST');
}

// =====================================================================
// LOGS
// =====================================================================

async function apiGetLogs(options = {}) {
    const { pipelineId = null, page = 1 } = options;

    let endpoint = '/logs';
    const params = new URLSearchParams();

    if (pipelineId) {
        params.append('pipeline_id', pipelineId);
    } else {
        // Envia o parâmetro de página apenas para o histórico geral
        params.append('page', page);
    }

    const queryString = params.toString();
    if (queryString) {
        endpoint += `?${queryString}`;
    }

    return await apiRequest(endpoint);
}

// =====================================================================
// HEALTH CHECK
// =====================================================================

async function apiHealthCheck() {
    return await apiRequest('/health');
}

// =====================================================================
// DASHBOARD
// =====================================================================

async function apiGetDashboardStats() {
    const params = serverOS ? `?command_type=${serverOS.command_type}` : '';
    return await apiRequest(`/dashboard/stats${params}`);
}

async function apiGetDashboardMetrics(days = 7) {
    return await apiRequest(`/dashboard/metrics?days=${days}`);
}

async function apiGetDashboardFeed(limit = 10) {
    return await apiRequest(`/dashboard/feed?limit=${limit}`);
}

async function apiGetDashboardModulesSummary() {
    return await apiRequest('/dashboard/modules-summary');
}

async function apiGetLogAlertsTimeline(hours = 24) {
    const envId = sessionStorage.getItem('active_environment_id') || '';
    return await apiRequest(`/log-alerts/timeline?hours=${hours}&environment_id=${envId}`);
}
