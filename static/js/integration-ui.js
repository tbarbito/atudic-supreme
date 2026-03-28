// =====================================================================
// INTEGRATION-UI.JS
// Dashboard, tela de configurações (settings), variáveis, serviços
// =====================================================================

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
// DASHBOARD
// =====================================================================

// Listener global para ações de dashboard
document.addEventListener('click', async (e) => {
    const btnRefresh = e.target.closest('[data-action="refreshDashboard"]');
    if (btnRefresh) {
        e.preventDefault();
        const icon = btnRefresh.querySelector('i');
        if (icon) icon.classList.add('fa-spin');

        await showDashboard();

        if (icon) icon.classList.remove('fa-spin');
    }
});

let dashboardLastUpdated = null;
let dashboardUpdateInterval = null;
let dashboardAutoRefresh = null;
let dashboardCharts = {};
let dashboardPeriod = 7; // dias: 1, 7, 30

// =====================================================================
// DASHBOARD V2 — Command Center
// =====================================================================

async function showDashboard() {
    const contentArea = document.getElementById('content-area');

    // Skeleton loading
    contentArea.innerHTML = renderDashboardSkeleton();

    try {
        const envId = sessionStorage.getItem('active_environment_id') || '';
        const [stats, health, obsSummary, metrics] = await Promise.all([
            apiGetDashboardStats(),
            apiHealthCheck().catch(() => null),
            apiRequest('/log-alerts/summary?' + new URLSearchParams({environment_id: envId})).catch(() => null),
            apiGetDashboardMetrics(dashboardPeriod).catch(() => null)
        ]);
        dashboardLastUpdated = new Date();
        renderDashboard(stats, health, obsSummary, metrics);
        startDashboardUpdateTimer();
        startDashboardAutoRefresh();

        // Carregar dados secundarios em background (Tier 3 e 4)
        loadDashboardSecondaryData(stats);
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

function renderDashboardSkeleton() {
    return `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <div class="dashboard-skeleton dashboard-skeleton-line" style="width:200px;height:28px"></div>
                    <div class="dashboard-skeleton dashboard-skeleton-line short mt-2" style="height:16px"></div>
                </div>
                <div class="dashboard-skeleton dashboard-skeleton-line" style="width:180px;height:32px"></div>
            </div>
            <div class="dashboard-kpis">
                ${Array(5).fill('<div class="dashboard-skeleton dashboard-skeleton-card"></div>').join('')}
            </div>
            <div class="dashboard-charts">
                ${Array(2).fill('<div class="dashboard-skeleton dashboard-skeleton-chart"></div>').join('')}
            </div>
        </div>
    `;
}

function startDashboardUpdateTimer() {
    if (dashboardUpdateInterval) clearInterval(dashboardUpdateInterval);
    dashboardUpdateInterval = setInterval(() => {
        const el = document.getElementById('dashboard-last-updated');
        if (!el || !dashboardLastUpdated) {
            clearInterval(dashboardUpdateInterval);
            return;
        }
        const diffSecs = Math.floor((new Date() - dashboardLastUpdated) / 1000);
        if (diffSecs < 60) {
            el.textContent = 'Atualizado agora';
        } else {
            const mins = Math.floor(diffSecs / 60);
            el.textContent = `Atualizado ha ${mins} min`;
        }
    }, 15000);
}

function startDashboardAutoRefresh() {
    stopDashboardAutoRefresh();
    // KPIs a cada 30s
    dashboardAutoRefresh = setInterval(async () => {
        if (location.hash !== '#dashboard' && location.hash !== '') return;
        try {
            const envId = sessionStorage.getItem('active_environment_id') || '';
            const [stats, obsSummary] = await Promise.all([
                apiGetDashboardStats(),
                apiRequest('/log-alerts/summary?' + new URLSearchParams({environment_id: envId})).catch(() => null)
            ]);
            dashboardLastUpdated = new Date();
            // Atualizar apenas KPIs sem rebuild completo
            updateKPIValues(stats, obsSummary);
        } catch (e) {
            // Silencioso — nao interromper UX
        }
    }, 30000);
}

function stopDashboardAutoRefresh() {
    if (dashboardAutoRefresh) {
        clearInterval(dashboardAutoRefresh);
        dashboardAutoRefresh = null;
    }
    if (dashboardUpdateInterval) {
        clearInterval(dashboardUpdateInterval);
        dashboardUpdateInterval = null;
    }
    destroyDashboardCharts();
}

function destroyDashboardCharts() {
    Object.values(dashboardCharts).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') chart.destroy();
    });
    dashboardCharts = {};
}

// =====================================================================
// CHART.JS HELPERS
// =====================================================================

function getChartColors() {
    // Cores fixas em hex — getComputedStyle pode retornar rgb() ou var() que quebra
    // concatenacao de alpha hex (ex: '#218085CC')
    const style = getComputedStyle(document.documentElement);
    const resolve = (varName, fallback) => {
        const val = style.getPropertyValue(varName).trim();
        // Aceitar apenas se for hex (#xxxxxx)
        if (val && val.startsWith('#')) return val;
        return fallback;
    };
    return {
        primary: resolve('--color-primary', '#218085'),
        success: resolve('--color-success', '#218085'),
        error: resolve('--color-error', '#c0152f'),
        warning: resolve('--color-warning', '#a84b2f'),
        info: resolve('--color-info', '#626c71'),
        text: resolve('--color-text', '#133c3b'),
        textSecondary: resolve('--color-text-secondary', '#626c71'),
        border: resolve('--color-border', '#e0ddd8'),
        surface: resolve('--color-surface', '#fffffd'),
        // Cores extras para diferenciar charts
        blue: '#3b82f6',
        purple: '#8b5cf6',
        amber: '#f59e0b',
        emerald: '#10b981',
        rose: '#f43f5e',
        cyan: '#06b6d4',
        indigo: '#6366f1'
    };
}

function createDashboardChart(canvasId, type, data, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return null;

    const colors = getChartColors();
    const defaults = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: 'easeOutQuart' },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: colors.text,
                titleColor: '#fff',
                bodyColor: '#fff',
                cornerRadius: 8,
                padding: 10,
                titleFont: { size: 12, weight: 600 },
                bodyFont: { size: 11 }
            }
        },
        scales: {}
    };

    if (type === 'bar' || type === 'line') {
        defaults.scales = {
            x: {
                grid: { display: false },
                ticks: { color: colors.textSecondary, font: { size: 10 } }
            },
            y: {
                grid: { color: colors.border + '40' },
                ticks: { color: colors.textSecondary, font: { size: 10 } },
                beginAtZero: true
            }
        };
    }

    const mergedOptions = deepMerge(defaults, options);

    if (dashboardCharts[canvasId]) {
        dashboardCharts[canvasId].destroy();
    }

    dashboardCharts[canvasId] = new Chart(canvas, { type, data, options: mergedOptions });
    return dashboardCharts[canvasId];
}

function deepMerge(target, source) {
    const result = { ...target };
    for (const key in source) {
        if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
            result[key] = deepMerge(result[key] || {}, source[key]);
        } else {
            result[key] = source[key];
        }
    }
    return result;
}

// =====================================================================
// PERIOD SELECTOR
// =====================================================================

function handlePeriodChange(days) {
    dashboardPeriod = days;
    // Atualizar botoes ativos
    document.querySelectorAll('.dashboard-period-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.days) === days);
    });
    // Recarregar charts com novo periodo
    refreshDashboardCharts();
}

async function refreshDashboardCharts() {
    try {
        const metrics = await apiGetDashboardMetrics(dashboardPeriod);
        if (metrics) {
            renderPipelineRunsChart(metrics);
            renderResponseTimeChart(metrics);
            renderTopErrorsChart(metrics);
        }
    } catch (e) {
        console.error('Erro ao atualizar charts:', e);
    }
}

// =====================================================================
// RENDER DASHBOARD PRINCIPAL (mantém assinatura original + metrics)
// =====================================================================

function renderDashboard(stats, health, obsSummary, metrics) {
    const envSelector = document.getElementById('environmentSelector');
    const envName = envSelector?.selectedOptions[0]?.text || 'Ambiente';

    // Calcular metricas
    const pipelineTotal = stats.pipeline_runs?.total || 0;
    const pipelineSuccess = stats.pipeline_runs?.success || 0;
    const pipelineRate = pipelineTotal > 0 ? Math.round((pipelineSuccess / pipelineTotal) * 100) : 0;
    const releaseTotal = stats.releases?.total || 0;
    const releaseSuccess = stats.releases?.success || 0;
    const hasRunning = (stats.pipeline_runs?.running || 0) > 0;
    const criticalAlerts = obsSummary?.unacknowledged?.critical || 0;
    const serviceTotal = stats.service_actions?.total || 0;
    const serviceActive = stats.service_actions?.active || 0;
    const serviceUptime = serviceTotal > 0 ? Math.round((serviceActive / serviceTotal) * 100) : 100;

    // Tendencia (comparar com dados do metrics)
    const trend = calcPipelineTrend(metrics);

    const periodLabels = { 1: '24h', 7: '7d', 30: '30d' };

    const content = `
        <div>
            <!-- Header -->
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2><i class="fas fa-chart-line me-2"></i>Dashboard</h2>
                    <p class="text-muted mb-0">Visao geral do ambiente: <strong>${envName}</strong></p>
                </div>
                <div class="d-flex align-items-center gap-3">
                    <div class="dashboard-period-selector">
                        <button class="dashboard-period-btn ${dashboardPeriod === 1 ? 'active' : ''}" data-days="1" data-action="changeDashboardPeriod">24h</button>
                        <button class="dashboard-period-btn ${dashboardPeriod === 7 ? 'active' : ''}" data-days="7" data-action="changeDashboardPeriod">7d</button>
                        <button class="dashboard-period-btn ${dashboardPeriod === 30 ? 'active' : ''}" data-days="30" data-action="changeDashboardPeriod">30d</button>
                    </div>
                    <div class="dashboard-refresh-indicator">
                        <span class="dashboard-refresh-dot"></span>
                        <span id="dashboard-last-updated" title="${dashboardLastUpdated ? dashboardLastUpdated.toLocaleString('pt-BR') : ''}">Atualizado agora</span>
                    </div>
                    <button class="btn btn-outline-primary btn-sm" data-action="refreshDashboard">
                        <i class="fas fa-sync-alt"></i>
                    </button>
                </div>
            </div>

            <!-- TIER 1: KPI Cards -->
            <div class="dashboard-kpis">
                <!-- Pipeline Health -->
                <div class="dashboard-kpi-card dashboard-card-enter dashboard-card-stagger-1" data-drilldown="#pipelines">
                    <div class="dashboard-kpi-header">
                        <div>
                            <div class="dashboard-kpi-value" id="kpi-pipeline-rate">${hasRunning ? '<span class="dashboard-pulse-dot"></span>' : ''}${pipelineRate}%</div>
                            <div class="dashboard-kpi-label">Pipeline Health</div>
                            ${trend.direction !== 'stable' ? `
                            <div class="dashboard-kpi-trend ${trend.direction}">
                                <i class="fas fa-arrow-${trend.direction === 'up' ? 'up' : 'down'}"></i>
                                ${trend.percentage}%
                            </div>` : ''}
                        </div>
                        <div class="dashboard-card-icon bg-primary">
                            <i class="fas fa-heartbeat"></i>
                        </div>
                    </div>
                    <div class="dashboard-kpi-sparkline"><canvas id="sparkline-pipelines"></canvas></div>
                    <div class="dashboard-kpi-footer">
                        <div class="dashboard-kpi-sub success"><div class="value" id="kpi-pipeline-success">${pipelineSuccess}</div><div class="label">Sucesso</div></div>
                        <div class="dashboard-kpi-sub failed"><div class="value" id="kpi-pipeline-failed">${stats.pipeline_runs?.failed || 0}</div><div class="label">Falha</div></div>
                        <div class="dashboard-kpi-sub warning"><div class="value" id="kpi-pipeline-running">${stats.pipeline_runs?.running || 0}</div><div class="label">Exec</div></div>
                    </div>
                </div>

                <!-- Deploys -->
                <div class="dashboard-kpi-card dashboard-card-enter dashboard-card-stagger-2" data-drilldown="#pipelines">
                    <div class="dashboard-kpi-header">
                        <div>
                            <div class="dashboard-kpi-value" id="kpi-deploy-total">${releaseTotal}</div>
                            <div class="dashboard-kpi-label">Deploys</div>
                        </div>
                        <div class="dashboard-kpi-mini-chart"><canvas id="minichart-deploys"></canvas></div>
                    </div>
                    <div class="dashboard-kpi-footer">
                        <div class="dashboard-kpi-sub success"><div class="value" id="kpi-deploy-success">${releaseSuccess}</div><div class="label">Sucesso</div></div>
                        <div class="dashboard-kpi-sub failed"><div class="value" id="kpi-deploy-failed">${stats.releases?.failed || 0}</div><div class="label">Falha</div></div>
                    </div>
                </div>

                <!-- Alertas Ativos -->
                <div class="dashboard-kpi-card dashboard-card-enter dashboard-card-stagger-3" data-drilldown="#observability">
                    <div class="dashboard-kpi-header">
                        <div>
                            <div class="dashboard-kpi-value" id="kpi-alerts-critical">${criticalAlerts > 0 ? '<span class="dashboard-pulse-dot"></span>' : ''}${criticalAlerts}</div>
                            <div class="dashboard-kpi-label">Alertas Ativos</div>
                        </div>
                        <div class="dashboard-card-icon bg-danger" style="background:rgba(192,21,47,0.15);color:#c0152f">
                            <i class="fas fa-bell"></i>
                        </div>
                    </div>
                    <div class="dashboard-kpi-footer">
                        <div class="dashboard-kpi-sub failed"><div class="value" id="kpi-alerts-crit-total">${obsSummary?.by_severity?.critical || 0}</div><div class="label">Crit</div></div>
                        <div class="dashboard-kpi-sub warning"><div class="value" id="kpi-alerts-warn">${obsSummary?.by_severity?.warning || 0}</div><div class="label">Warn</div></div>
                        <div class="dashboard-kpi-sub"><div class="value" id="kpi-alerts-info">${obsSummary?.by_severity?.info || 0}</div><div class="label">Info</div></div>
                    </div>
                </div>

                <!-- Uptime de Servicos -->
                <div class="dashboard-kpi-card dashboard-card-enter dashboard-card-stagger-4" data-drilldown="#schedules">
                    <div class="dashboard-kpi-header">
                        <div>
                            <div class="dashboard-kpi-value" id="kpi-service-uptime">${serviceUptime}%</div>
                            <div class="dashboard-kpi-label">Uptime Servicos</div>
                        </div>
                        <div class="dashboard-circular-progress">
                            <svg width="56" height="56" viewBox="0 0 56 56">
                                <circle cx="28" cy="28" r="24" fill="none" stroke="${getChartColors().border}" stroke-width="4"/>
                                <circle cx="28" cy="28" r="24" fill="none" stroke="${getChartColors().success}" stroke-width="4"
                                    stroke-dasharray="${(serviceUptime / 100) * 150.8} 150.8" stroke-linecap="round"/>
                            </svg>
                            <span class="progress-text">${serviceActive}/${serviceTotal}</span>
                        </div>
                    </div>
                    <div class="dashboard-kpi-footer">
                        <div class="dashboard-kpi-sub success"><div class="value">${serviceActive}</div><div class="label">Ativas</div></div>
                        <div class="dashboard-kpi-sub"><div class="value">${serviceTotal}</div><div class="label">Total</div></div>
                    </div>
                </div>

                <!-- Releases Recentes -->
                <div class="dashboard-kpi-card dashboard-card-enter dashboard-card-stagger-5" data-drilldown="#pipelines">
                    <div class="dashboard-kpi-header">
                        <div>
                            <div class="dashboard-kpi-value">${stats.totals?.pipelines || 0}</div>
                            <div class="dashboard-kpi-label">Pipelines</div>
                        </div>
                        <div class="dashboard-card-icon bg-info">
                            <i class="fas fa-layer-group"></i>
                        </div>
                    </div>
                    <div class="dashboard-kpi-sparkline"><canvas id="sparkline-releases"></canvas></div>
                    <div class="dashboard-kpi-footer">
                        <div class="dashboard-kpi-sub success"><div class="value">${stats.totals?.repositories || 0}</div><div class="label">Repos</div></div>
                        <div class="dashboard-kpi-sub"><div class="value">${stats.active_schedules?.length || 0}</div><div class="label">Agend</div></div>
                    </div>
                </div>
            </div>

            <!-- TIER 2: Charts -->
            <div class="dashboard-charts">
                <div class="dashboard-chart-card dashboard-card-enter dashboard-card-stagger-6">
                    <div class="dashboard-chart-header">
                        <div class="dashboard-chart-title">
                            <i class="fas fa-chart-bar text-primary"></i>
                            Pipeline Runs (${periodLabels[dashboardPeriod]})
                        </div>
                    </div>
                    <div class="dashboard-chart-canvas"><canvas id="chart-pipeline-runs"></canvas></div>
                </div>

                <div class="dashboard-chart-card dashboard-card-enter dashboard-card-stagger-7">
                    <div class="dashboard-chart-header">
                        <div class="dashboard-chart-title">
                            <i class="fas fa-clock text-info"></i>
                            Tempo Medio de Execucao
                        </div>
                    </div>
                    <div class="dashboard-chart-canvas"><canvas id="chart-response-time"></canvas></div>
                </div>
            </div>

            <div class="dashboard-charts">
                <div class="dashboard-chart-card dashboard-card-enter dashboard-card-stagger-8">
                    <div class="dashboard-chart-header">
                        <div class="dashboard-chart-title">
                            <i class="fas fa-exclamation-circle text-danger"></i>
                            Top Erros
                        </div>
                    </div>
                    <div class="dashboard-chart-canvas"><canvas id="chart-top-errors"></canvas></div>
                </div>

                <div class="dashboard-chart-card dashboard-card-enter dashboard-card-stagger-8" id="chart-alert-timeline-container">
                    <div class="dashboard-chart-header">
                        <div class="dashboard-chart-title">
                            <i class="fas fa-wave-square text-warning"></i>
                            Alert Timeline (24h)
                        </div>
                    </div>
                    <div class="dashboard-chart-canvas"><canvas id="chart-alert-timeline"></canvas></div>
                </div>
            </div>

            <!-- TIER 3: Activity & Status -->
            <div class="dashboard-activity">
                <!-- Live Feed -->
                <div class="dashboard-card dashboard-card-enter" id="dashboard-feed-container">
                    <h5 class="dashboard-section-title">
                        <i class="fas fa-stream text-primary"></i>
                        Atividade Recente
                    </h5>
                    <div class="dashboard-feed" id="dashboard-feed">
                        ${renderLiveFeed(stats.recent_runs, stats.recent_service_actions)}
                    </div>
                </div>

                <!-- Proximos Agendamentos -->
                <div class="dashboard-card dashboard-card-enter" id="dashboard-schedules-container">
                    <h5 class="dashboard-section-title">
                        <i class="fas fa-clock text-warning"></i>
                        Proximos Agendamentos
                    </h5>
                    ${renderNextSchedules(stats.active_schedules, stats.scheduled_service_actions)}
                </div>

                <!-- System Health -->
                <div class="dashboard-card dashboard-card-enter" id="dashboard-health-container">
                    <h5 class="dashboard-section-title">
                        <i class="fas fa-heart text-success"></i>
                        Saude do Sistema
                    </h5>
                    ${renderSystemHealthGrid(health, stats)}
                    ${renderQuickActionsV2(criticalAlerts)}
                </div>
            </div>

            <!-- TIER 4: Insights (admin only) -->
            ${isAdmin() ? `
            <button class="dashboard-insights-toggle" data-action="toggleDashboardInsights">
                <i class="fas fa-chevron-down"></i>
                Insights &amp; Modulos
            </button>
            <div class="dashboard-insights" id="dashboard-insights">
                <div class="dashboard-card dashboard-card-enter" id="dashboard-modules-container">
                    <h5 class="dashboard-section-title">
                        <i class="fas fa-cubes text-info"></i>
                        Modulos
                    </h5>
                    <div id="dashboard-modules-content">
                        <div class="dashboard-skeleton dashboard-skeleton-line"></div>
                        <div class="dashboard-skeleton dashboard-skeleton-line medium"></div>
                        <div class="dashboard-skeleton dashboard-skeleton-line short"></div>
                    </div>
                </div>

                <div class="dashboard-card dashboard-card-enter">
                    <h5 class="dashboard-section-title">
                        <i class="fab fa-github text-info"></i>
                        Repositorios
                    </h5>
                    ${renderReposSummary(stats.repositories)}
                </div>

                <div class="dashboard-card dashboard-card-enter" id="dashboard-kb-container">
                    <h5 class="dashboard-section-title">
                        <i class="fas fa-book text-primary"></i>
                        Knowledge Base
                    </h5>
                    <div id="dashboard-kb-content">
                        <div class="dashboard-skeleton dashboard-skeleton-line"></div>
                        <div class="dashboard-skeleton dashboard-skeleton-line medium"></div>
                    </div>
                </div>
            </div>` : ''}
        </div>
    `;

    document.getElementById('content-area').innerHTML = content;

    // Inicializar charts apos DOM render
    requestAnimationFrame(() => {
        if (metrics) {
            renderPipelineRunsChart(metrics);
            renderResponseTimeChart(metrics);
            renderTopErrorsChart(metrics);
            renderSparklines(metrics, stats);
        }
        renderDeployDonut(stats);
        setupDashboardDrillDown();
    });
}

// =====================================================================
// KPI INLINE UPDATE (sem rebuild do DOM)
// =====================================================================

function updateKPIValues(stats, obsSummary) {
    const pipelineTotal = stats.pipeline_runs?.total || 0;
    const pipelineSuccess = stats.pipeline_runs?.success || 0;
    const pipelineRate = pipelineTotal > 0 ? Math.round((pipelineSuccess / pipelineTotal) * 100) : 0;
    const criticalAlerts = obsSummary?.unacknowledged?.critical || 0;

    const updates = {
        'kpi-pipeline-rate': `${pipelineRate}%`,
        'kpi-pipeline-success': pipelineSuccess,
        'kpi-pipeline-failed': stats.pipeline_runs?.failed || 0,
        'kpi-pipeline-running': stats.pipeline_runs?.running || 0,
        'kpi-deploy-total': stats.releases?.total || 0,
        'kpi-deploy-success': stats.releases?.success || 0,
        'kpi-deploy-failed': stats.releases?.failed || 0,
        'kpi-alerts-critical': criticalAlerts,
        'kpi-alerts-crit-total': obsSummary?.by_severity?.critical || 0,
        'kpi-alerts-warn': obsSummary?.by_severity?.warning || 0,
        'kpi-alerts-info': obsSummary?.by_severity?.info || 0,
        'kpi-service-uptime': `${stats.service_actions?.total > 0 ? Math.round((stats.service_actions.active / stats.service_actions.total) * 100) : 100}%`
    };

    for (const [id, value] of Object.entries(updates)) {
        const el = document.getElementById(id);
        if (el) {
            const text = el.textContent.replace(/[^0-9%]/g, '');
            if (text !== String(value)) {
                el.textContent = value;
                el.style.transition = 'color 0.3s';
                el.style.color = 'var(--color-primary)';
                setTimeout(() => { el.style.color = ''; }, 600);
            }
        }
    }
}

// =====================================================================
// CHART RENDERERS
// =====================================================================

function renderSparklines(metrics, stats) {
    if (!metrics?.daily_runs?.length) return;

    const colors = getChartColors();
    const days = metrics.daily_runs.map(d => '');
    const successData = metrics.daily_runs.map(d => d.success || 0);

    createDashboardChart('sparkline-pipelines', 'line', {
        labels: days,
        datasets: [{
            data: successData,
            borderColor: colors.emerald,
            borderWidth: 2,
            fill: true,
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 6
        }]
    }, {
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
        animation: { duration: 800 }
    });

    // Sparkline de releases (totais por dia)
    if (metrics.daily_releases?.length) {
        const relDays = metrics.daily_releases.map(() => '');
        const relData = metrics.daily_releases.map(d => d.total || 0);
        createDashboardChart('sparkline-releases', 'line', {
            labels: relDays,
            datasets: [{
                data: relData,
                borderColor: colors.blue,
                borderWidth: 2,
                fill: true,
                backgroundColor: 'rgba(59, 130, 246, 0.12)',
                tension: 0.4,
                pointRadius: 0,
                pointHitRadius: 6
            }]
        }, {
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } },
            animation: { duration: 800 }
        });
    }
}

function renderDeployDonut(stats) {
    const success = stats.releases?.success || 0;
    const failed = stats.releases?.failed || 0;
    if (success === 0 && failed === 0) return;

    const colors = getChartColors();
    createDashboardChart('minichart-deploys', 'doughnut', {
        labels: ['Sucesso', 'Falha'],
        datasets: [{
            data: [success, failed],
            backgroundColor: [colors.emerald, colors.rose],
            borderWidth: 0
        }]
    }, {
        cutout: '65%',
        plugins: { legend: { display: false }, tooltip: { enabled: true } },
        animation: { duration: 600 }
    });
}

function renderPipelineRunsChart(metrics) {
    if (!metrics?.daily_runs?.length) {
        const container = document.getElementById('chart-pipeline-runs')?.parentElement;
        if (container) container.innerHTML = '<div class="dashboard-chart-empty"><i class="fas fa-chart-bar"></i><p>Sem dados de execucao no periodo</p></div>';
        return;
    }

    const colors = getChartColors();
    const labels = metrics.daily_runs.map(d => formatDateLabel(d.day));

    createDashboardChart('chart-pipeline-runs', 'bar', {
        labels,
        datasets: [
            {
                label: 'Sucesso',
                data: metrics.daily_runs.map(d => d.success || 0),
                backgroundColor: colors.emerald,
                borderRadius: 4,
                borderSkipped: false
            },
            {
                label: 'Falha',
                data: metrics.daily_runs.map(d => d.failed || 0),
                backgroundColor: colors.rose,
                borderRadius: 4,
                borderSkipped: false
            }
        ]
    }, {
        plugins: {
            legend: { display: true, position: 'top', labels: { boxWidth: 12, usePointStyle: true, pointStyle: 'rectRounded', font: { size: 11 } } }
        },
        scales: {
            x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } },
            y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1, font: { size: 10 } } }
        }
    });
}

function renderResponseTimeChart(metrics) {
    if (!metrics?.pipeline_stats?.length) {
        const container = document.getElementById('chart-response-time')?.parentElement;
        if (container) container.innerHTML = '<div class="dashboard-chart-empty"><i class="fas fa-clock"></i><p>Sem dados de duracao</p></div>';
        return;
    }

    const colors = getChartColors();
    const sorted = [...metrics.pipeline_stats].sort((a, b) => (b.avg_duration_sec || 0) - (a.avg_duration_sec || 0)).slice(0, 8);
    const labels = sorted.map(p => p.pipeline_name.length > 20 ? p.pipeline_name.substring(0, 17) + '...' : p.pipeline_name);
    const durations = sorted.map(p => Math.round((p.avg_duration_sec || 0) / 60 * 10) / 10); // em minutos

    createDashboardChart('chart-response-time', 'bar', {
        labels,
        datasets: [{
            label: 'Duracao media (min)',
            data: durations,
            backgroundColor: durations.map((_, i) => [colors.blue, colors.cyan, colors.indigo, colors.purple, colors.primary, colors.info, colors.emerald, colors.amber][i % 8]),
            borderRadius: 4,
            borderSkipped: false
        }]
    }, {
        indexAxis: 'y',
        plugins: {
            legend: { display: false },
            tooltip: {
                callbacks: {
                    label: (ctx) => {
                        const sec = sorted[ctx.dataIndex]?.avg_duration_sec || 0;
                        if (sec < 60) return `${sec}s`;
                        return `${Math.floor(sec / 60)}m ${sec % 60}s`;
                    }
                }
            }
        },
        scales: {
            x: { beginAtZero: true, ticks: { callback: v => v + 'min', font: { size: 10 } } },
            y: { ticks: { font: { size: 10 } } }
        }
    });
}

function renderTopErrorsChart(metrics) {
    if (!metrics?.top_failures?.length) {
        const container = document.getElementById('chart-top-errors')?.parentElement;
        if (container) container.innerHTML = '<div class="dashboard-chart-empty"><i class="fas fa-check-circle" style="color:var(--color-success)"></i><p>Nenhuma falha no periodo</p></div>';
        return;
    }

    const colors = getChartColors();
    const labels = metrics.top_failures.map(f => f.pipeline_name.length > 25 ? f.pipeline_name.substring(0, 22) + '...' : f.pipeline_name);
    const data = metrics.top_failures.map(f => f.fail_count);

    createDashboardChart('chart-top-errors', 'bar', {
        labels,
        datasets: [{
            label: 'Falhas',
            data,
            backgroundColor: data.map((_, i) => {
                const opacity = 1 - (i * 0.15);
                return `rgba(192, 21, 47, ${Math.max(opacity, 0.3)})`;
            }),
            borderRadius: 4,
            borderSkipped: false
        }]
    }, {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
            x: { beginAtZero: true, ticks: { stepSize: 1, font: { size: 10 } } },
            y: { ticks: { font: { size: 10 } } }
        }
    });
}

async function renderAlertTimelineChart() {
    try {
        const data = await apiGetLogAlertsTimeline(24);
        if (!data?.timeline?.length) return;

        const colors = getChartColors();
        const labels = data.timeline.map(t => {
            const d = new Date(t.hour);
            return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        });

        createDashboardChart('chart-alert-timeline', 'line', {
            labels,
            datasets: [
                {
                    label: 'Critico',
                    data: data.timeline.map(t => t.critical || 0),
                    borderColor: colors.rose,
                    backgroundColor: 'rgba(244, 63, 94, 0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2
                },
                {
                    label: 'Warning',
                    data: data.timeline.map(t => t.warning || 0),
                    borderColor: colors.amber,
                    backgroundColor: 'rgba(245, 158, 11, 0.12)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2
                },
                {
                    label: 'Info',
                    data: data.timeline.map(t => t.info || 0),
                    borderColor: colors.blue,
                    backgroundColor: 'rgba(59, 130, 246, 0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2
                }
            ]
        }, {
            plugins: {
                legend: { display: true, position: 'top', labels: { boxWidth: 12, usePointStyle: true, font: { size: 10 } } }
            },
            scales: {
                y: { beginAtZero: true, stacked: true, ticks: { stepSize: 1 } },
                x: { ticks: { maxTicksLimit: 12, font: { size: 9 } } }
            }
        });
    } catch (e) {
        // Silencioso
    }
}

// =====================================================================
// TIER 3: WIDGETS DE ATIVIDADE
// =====================================================================

function renderLiveFeed(runs, serviceActions) {
    const items = [];

    if (runs?.length) {
        runs.forEach(run => {
            items.push({
                type: 'pipeline_run',
                icon: run.status === 'success' ? 'fa-check-circle' : run.status === 'failed' ? 'fa-times-circle' : 'fa-spinner fa-spin',
                color: run.status === 'success' ? 'success' : run.status === 'failed' ? 'danger' : 'warning',
                title: `${run.pipeline_name} #${run.run_number}`,
                subtitle: run.trigger_type === 'scheduled' ? 'Agendado' : 'Manual',
                timestamp: run.started_at,
                drilldown: '#pipelines'
            });
        });
    }

    if (serviceActions?.length) {
        serviceActions.forEach(action => {
            items.push({
                type: 'service_action',
                icon: 'fa-server',
                color: 'info',
                title: action.name,
                subtitle: `${action.action_type} - ${action.os_type}`,
                timestamp: action.last_run_at,
                drilldown: '#schedules'
            });
        });
    }

    // Ordenar por timestamp desc
    items.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));

    if (!items.length) {
        return '<div class="dashboard-empty-state"><i class="fas fa-inbox"></i><p>Nenhuma atividade recente</p></div>';
    }

    return items.slice(0, 10).map(item => `
        <div class="dashboard-feed-item" data-drilldown="${item.drilldown}" style="cursor:pointer">
            <div class="dashboard-feed-icon ${item.color}">
                <i class="fas ${item.icon}"></i>
            </div>
            <div class="dashboard-feed-content">
                <div class="dashboard-feed-title">${escapeHtml(item.title)}</div>
                <div class="dashboard-feed-subtitle">${escapeHtml(item.subtitle)}</div>
            </div>
            <div class="dashboard-feed-time">${formatTimeAgo(item.timestamp)}</div>
        </div>
    `).join('');
}

function renderNextSchedules(schedules, serviceActions) {
    const items = [];

    if (schedules?.length) {
        schedules.forEach(s => {
            items.push({ name: s.name, pipeline: s.pipeline_name, next: s.next_run_at, type: 'pipeline' });
        });
    }

    if (serviceActions?.length) {
        serviceActions.forEach(a => {
            items.push({ name: a.name, pipeline: a.action_type, next: a.next_run_at, type: 'service' });
        });
    }

    items.sort((a, b) => new Date(a.next || '2099-01-01') - new Date(b.next || '2099-01-01'));

    if (!items.length) {
        return '<div class="dashboard-empty-state"><i class="fas fa-calendar-times"></i><p>Nenhum agendamento</p><a href="#schedules" class="btn btn-sm btn-outline-primary">Criar agendamento</a></div>';
    }

    return '<ul class="dashboard-list">' + items.slice(0, 5).map(item => `
        <li class="dashboard-list-item">
            <div>
                <div class="dashboard-list-item-title">
                    <i class="fas fa-${item.type === 'pipeline' ? 'play-circle' : 'server'} me-1 text-muted"></i>
                    ${escapeHtml(item.name)}
                </div>
                <div class="dashboard-list-item-subtitle">${escapeHtml(item.pipeline)}</div>
            </div>
            <div class="dashboard-countdown">${item.next ? formatCountdown(item.next) : '--'}</div>
        </li>
    `).join('') + '</ul>' + `
        <div class="text-center mt-2">
            <a href="#schedules" class="btn btn-sm btn-outline-primary">Ver todos <i class="fas fa-arrow-right ms-1"></i></a>
        </div>`;
}

function renderSystemHealthGrid(health, stats) {
    if (!health) return '<div class="dashboard-empty-state"><i class="fas fa-heart-broken"></i><p>Dados indisponiveis</p></div>';

    const isHealthy = health.status === 'healthy';
    const dbOk = health.database === 'connected';
    const users = health.stats?.users || 0;

    return `
        <div class="dashboard-health-grid">
            <div class="dashboard-health-item">
                <span class="dashboard-health-dot ${dbOk ? 'green' : 'red'}"></span>
                <span>${dbOk ? 'DB Conectado' : 'DB Offline'}</span>
            </div>
            <div class="dashboard-health-item">
                <span class="dashboard-health-dot ${isHealthy ? 'green' : 'red'}"></span>
                <span>${isHealthy ? 'Sistema OK' : 'Problemas'}</span>
            </div>
            <div class="dashboard-health-item">
                <span class="dashboard-health-dot green"></span>
                <span>${users} Usuario${users !== 1 ? 's' : ''}</span>
            </div>
            <div class="dashboard-health-item">
                <span class="dashboard-health-dot gray"></span>
                <span>${serverOS?.os_display || serverOS?.os || 'N/A'}</span>
            </div>
        </div>
    `;
}

function renderQuickActionsV2(criticalAlerts) {
    if (!isOperator()) return '';

    const actions = [
        { href: '#pipelines', icon: 'fa-play-circle', label: 'Pipeline' },
        { href: '#repositories', icon: 'fa-sync', label: 'Repos' },
        { href: '#schedules', icon: 'fa-calendar-alt', label: 'Agenda' }
    ];

    if (criticalAlerts > 0) {
        actions.unshift({ href: '#observability', icon: 'fa-exclamation-triangle', label: 'Diagnosticar', highlight: true });
    }

    if (isAdmin()) {
        actions.push({ href: '#settings', icon: 'fa-cog', label: 'Config' });
    }

    return `
        <div class="dashboard-quick-actions-v2">
            ${actions.map(a => `
                <a href="${a.href}" class="dashboard-quick-btn-v2 ${a.highlight ? 'text-danger' : ''}">
                    <i class="fas ${a.icon}"></i>${a.label}
                </a>
            `).join('')}
        </div>
    `;
}

// =====================================================================
// TIER 4: REPOS SUMMARY
// =====================================================================

function renderReposSummary(repos) {
    if (!repos?.length) return '<div class="dashboard-empty-state"><i class="fas fa-code-branch"></i><p>Nenhum repositorio</p></div>';

    return repos.map(repo => {
        const branches = repo.branches?.length || 0;
        return `
            <div class="dashboard-module-stat">
                <div class="module-name">
                    <i class="fab fa-github"></i>
                    ${escapeHtml(repo.name)}
                </div>
                <div class="module-value">${branches} branch${branches !== 1 ? 'es' : ''}</div>
            </div>
        `;
    }).join('');
}

// =====================================================================
// SECONDARY DATA (Tier 3/4 — carregado apos render principal)
// =====================================================================

async function loadDashboardSecondaryData(stats) {
    // Alert timeline chart
    renderAlertTimelineChart();

    // Feed do backend (se endpoint existir)
    try {
        const feed = await apiGetDashboardFeed(10);
        if (feed?.items?.length) {
            const feedEl = document.getElementById('dashboard-feed');
            if (feedEl) {
                feedEl.innerHTML = feed.items.map(item => `
                    <div class="dashboard-feed-item" data-drilldown="${item.drilldown || '#dashboard'}" style="cursor:pointer">
                        <div class="dashboard-feed-icon ${item.color || 'info'}">
                            <i class="fas ${item.icon || 'fa-circle'}"></i>
                        </div>
                        <div class="dashboard-feed-content">
                            <div class="dashboard-feed-title">${escapeHtml(item.title || '')}</div>
                            <div class="dashboard-feed-subtitle">${escapeHtml(item.subtitle || '')}</div>
                        </div>
                        <div class="dashboard-feed-time">${formatTimeAgo(item.timestamp)}</div>
                    </div>
                `).join('');
            }
        }
    } catch (e) {
        // Feed endpoint pode nao existir ainda — usa dados do stats
    }

    // Modules summary
    if (isAdmin()) {
        try {
            const modules = await apiGetDashboardModulesSummary();
            const el = document.getElementById('dashboard-modules-content');
            if (el && modules) {
                el.innerHTML = `
                    ${modules.database ? `<div class="dashboard-module-stat"><div class="module-name"><i class="fas fa-database text-primary"></i> Database</div><div class="module-value">${modules.database.total || 0} conexoes</div></div>` : ''}
                    ${modules.processes ? `<div class="dashboard-module-stat"><div class="module-name"><i class="fas fa-project-diagram text-info"></i> Processos</div><div class="module-value">${modules.processes.total || 0}</div></div>` : ''}
                    ${modules.knowledge ? `<div class="dashboard-module-stat"><div class="module-name"><i class="fas fa-book text-success"></i> Knowledge</div><div class="module-value">${modules.knowledge.total || 0} artigos</div></div>` : ''}
                    ${modules.documentation ? `<div class="dashboard-module-stat"><div class="module-name"><i class="fas fa-file-alt text-warning"></i> Docs</div><div class="module-value">${modules.documentation.total || 0}</div></div>` : ''}
                    ${modules.schedules ? `<div class="dashboard-module-stat"><div class="module-name"><i class="fas fa-calendar text-info"></i> Agendamentos</div><div class="module-value">${modules.schedules.active || 0}/${modules.schedules.total || 0} ativos</div></div>` : ''}
                `;
            }
        } catch (e) {
            const el = document.getElementById('dashboard-modules-content');
            if (el) el.innerHTML = '<div class="text-muted small">Dados indisponiveis</div>';
        }

        // KB content
        try {
            const kb = await apiRequest('/knowledge?limit=3').catch(() => null);
            const kbEl = document.getElementById('dashboard-kb-content');
            if (kbEl && kb?.articles?.length) {
                kbEl.innerHTML = kb.articles.map(a => `
                    <div class="dashboard-module-stat">
                        <div class="module-name" style="font-size:12px">
                            <i class="fas fa-file-alt text-muted"></i>
                            ${escapeHtml((a.title || '').substring(0, 35))}
                        </div>
                        <div class="module-value" style="font-size:11px">${a.category || ''}</div>
                    </div>
                `).join('');
            } else if (kbEl) {
                kbEl.innerHTML = '<div class="dashboard-empty-state"><i class="fas fa-book"></i><p>Sem artigos</p></div>';
            }
        } catch (e) {
            const kbEl = document.getElementById('dashboard-kb-content');
            if (kbEl) kbEl.innerHTML = '<div class="text-muted small">Dados indisponiveis</div>';
        }
    }
}

// =====================================================================
// HELPERS
// =====================================================================

function calcPipelineTrend(metrics) {
    if (!metrics?.daily_runs?.length || metrics.daily_runs.length < 2) {
        return { direction: 'stable', percentage: 0 };
    }

    const runs = metrics.daily_runs;
    const mid = Math.floor(runs.length / 2);
    const firstHalf = runs.slice(0, mid);
    const secondHalf = runs.slice(mid);

    const avgFirst = firstHalf.reduce((s, d) => s + (d.success || 0), 0) / (firstHalf.length || 1);
    const avgSecond = secondHalf.reduce((s, d) => s + (d.success || 0), 0) / (secondHalf.length || 1);

    if (avgFirst === 0 && avgSecond === 0) return { direction: 'stable', percentage: 0 };

    const diff = avgSecond - avgFirst;
    const pct = avgFirst > 0 ? Math.round((diff / avgFirst) * 100) : (avgSecond > 0 ? 100 : 0);

    if (Math.abs(pct) < 5) return { direction: 'stable', percentage: 0 };
    return { direction: pct > 0 ? 'up' : 'down', percentage: Math.abs(pct) };
}

function formatTimeAgo(dateStr) {
    if (!dateStr) return '--';
    const now = new Date();
    const date = new Date(dateStr);
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 60) return 'agora';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}min`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h`;
    return `${Math.floor(diffSec / 86400)}d`;
}

function formatDateLabel(dateStr) {
    // Parsear "2026-03-16" como string pura sem new Date() para evitar shift de timezone
    if (!dateStr) return '';
    const str = String(dateStr).substring(0, 10); // "2026-03-16"
    const parts = str.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}`;
    return str;
}

function formatCountdown(dateStr) {
    if (!dateStr) return '--';
    const now = new Date();
    const target = new Date(dateStr);
    const diffSec = Math.floor((target - now) / 1000);

    if (diffSec <= 0) return 'agora';
    if (diffSec < 3600) return `em ${Math.floor(diffSec / 60)}min`;
    if (diffSec < 86400) {
        const h = Math.floor(diffSec / 3600);
        const m = Math.floor((diffSec % 3600) / 60);
        return `em ${h}h${m > 0 ? ` ${m}m` : ''}`;
    }
    return `em ${Math.floor(diffSec / 86400)}d`;
}

function setupDashboardDrillDown() {
    document.querySelectorAll('[data-drilldown]').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target.closest('a, button')) return;
            const hash = el.dataset.drilldown;
            if (hash) location.hash = hash;
        });
    });
}

// Event delegation para period selector e insights toggle
document.addEventListener('click', (e) => {
    const periodBtn = e.target.closest('[data-action="changeDashboardPeriod"]');
    if (periodBtn) {
        const days = parseInt(periodBtn.dataset.days);
        if (days) handlePeriodChange(days);
        return;
    }

    const insightsToggle = e.target.closest('[data-action="toggleDashboardInsights"]');
    if (insightsToggle) {
        const insights = document.getElementById('dashboard-insights');
        if (insights) {
            const hidden = insights.style.display === 'none';
            insights.style.display = hidden ? '' : 'none';
            insightsToggle.classList.toggle('collapsed', !hidden);
        }
        return;
    }
});

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

// Retrocompatibilidade: Quick Actions original (chamado se algum modulo referenciar)
function renderQuickActions() {
    if (!isOperator()) return '';
    return `
        <div class="dashboard-quick-actions mb-4">
            <div class="d-flex gap-2 flex-wrap">
                <a href="#pipelines" class="btn btn-sm btn-outline-primary dashboard-quick-btn">
                    <i class="fas fa-play-circle me-1"></i>Executar Pipeline
                </a>
                <a href="#commands" class="btn btn-sm btn-outline-secondary dashboard-quick-btn">
                    <i class="fas fa-terminal me-1"></i>Comandos
                </a>
                <a href="#repositories" class="btn btn-sm btn-outline-info dashboard-quick-btn">
                    <i class="fas fa-sync me-1"></i>Repositorios
                </a>
                <a href="#schedules" class="btn btn-sm btn-outline-warning dashboard-quick-btn">
                    <i class="fas fa-calendar-alt me-1"></i>Agendamentos
                </a>
                ${isAdmin() ? `
                <a href="#settings" class="btn btn-sm btn-outline-success dashboard-quick-btn">
                    <i class="fas fa-cog me-1"></i>Configuracoes
                </a>` : ''}
            </div>
        </div>
    `;
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
                    <button class="nav-link" id="github-tab" data-bs-toggle="tab" data-bs-target="#github-content" type="button" role="tab">GitHub</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="variables-tab" data-bs-toggle="tab" data-bs-target="#variables-content" type="button" role="tab">Variáveis do Servidor</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="environments-tab" data-bs-toggle="tab" data-bs-target="#environments-content" type="button" role="tab">Ambientes</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="services-tab" data-bs-toggle="tab" data-bs-target="#services-content" type="button" role="tab">Serviços do Servidor</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="api-keys-tab" data-bs-toggle="tab" data-bs-target="#api-keys-content" type="button" role="tab">Integrações API</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="notifications-tab" data-bs-toggle="tab" data-bs-target="#notifications-content" type="button" role="tab">Notificações</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="llm-settings-tab" data-bs-toggle="tab" data-bs-target="#llm-settings-content" type="button" role="tab">
                        <i class="fas fa-brain me-1"></i>LLM / IA
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="branch-policies-tab" data-bs-toggle="tab" data-bs-target="#branch-policies-content" type="button" role="tab">Políticas de Branch</button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="workspace-settings-tab" data-bs-toggle="tab" data-bs-target="#workspace-settings-content" type="button" role="tab">
                        <i class="fas fa-code me-1"></i>Workspace
                    </button>
                </li>
            </ul>

            <div class="tab-content" id="settingsTabsContent">
                <div class="tab-pane fade" id="github-content" role="tabpanel"></div>
                <div class="tab-pane fade show active" id="variables-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="environments-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="services-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="api-keys-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="notifications-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="branch-policies-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="llm-settings-content" role="tabpanel"></div>
                <div class="tab-pane fade" id="workspace-settings-content" role="tabpanel"></div>
            </div>
        </div>
    `;
    document.getElementById('content-area').innerHTML = content;

    // Renderiza o conteúdo de cada aba (async com catch individual)
    renderGithubSettingsTab();
    renderServerVariablesTab();
    renderEnvironmentsTab();
    renderServerServicesTab();
    renderApiKeysTab().catch(e => console.error('Erro API Keys:', e));
    renderNotificationsTab().catch(e => console.error('Erro Notificações:', e));
    renderBranchPoliciesTab().catch(e => console.error('Erro Políticas:', e));
    renderLLMSettingsTab().catch(e => console.error('Erro LLM:', e));
    renderWorkspaceSettingsTab().catch(e => console.error('Erro Workspace:', e));

    // Restaurar aba ativa (caso usuario tenha navegado e voltado)
    const savedTab = sessionStorage.getItem('activeSettingsTab');
    if (savedTab && savedTab !== 'github-tab' && savedTab !== 'branch-policies-tab') {
        const tabBtn = document.getElementById(savedTab);
        if (tabBtn) {
            try { new bootstrap.Tab(tabBtn).show(); } catch (e) { /* ignora */ }
        }
    }
}

// --- ABA LLM/IA (delegada para integration-agent.js) ---
async function renderLLMSettingsTab() {
    const container = document.getElementById('llm-settings-content');
    if (!container) return;

    // Reutilizar o render do agent se disponível
    if (typeof agRenderLLM === 'function') {
        await agRenderLLM(container);
    } else {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-brain me-2"></i>
                Configuração de LLM disponível em <strong>GolIAs > LLM</strong>.
            </div>`;
    }
}

// --- ABA WORKSPACE (delegada para integration-devworkspace.js) ---
async function renderWorkspaceSettingsTab() {
    const container = document.getElementById('workspace-settings-content');
    if (!container) return;

    if (typeof wsRenderSetup === 'function') {
        await wsRenderSetup(container);
    } else {
        container.innerHTML = '<div class="alert alert-info"><i class="fas fa-code me-2"></i>Modulo Workspace nao carregado.</div>';
    }
}

// --- NOVAS ABAS CONFIGURAÇŌES (API Keys e Notifications) ---
async function renderApiKeysTab() {
    const container = document.getElementById('api-keys-content');
    if (!container) return;
    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border text-primary"></div></div>';

    try {
        const keys = await apiRequest('/api_management/keys');

        container.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0"><i class="fas fa-key me-2"></i>Chaves de API (Webhooks / Integrações)</h5>
                    <button class="btn btn-primary" onclick="createApiKey()"><i class="fas fa-plus me-2"></i>Nova Chave</button>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead>
                                <tr>
                                    <th>Nome</th>
                                    <th>Chave</th>
                                    <th>Criada em</th>
                                    <th>Último uso</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${keys.map(k => `
                                    <tr>
                                        <td>${escapeHtml(k.name)}</td>
                                        <td><code>${escapeHtml(k.masked_key)}</code></td>
                                        <td>${formatDateTime(k.created_at)}</td>
                                        <td>${k.last_used_at ? formatDateTime(k.last_used_at) : 'Nunca'}</td>
                                        <td>
                                            <button class="btn btn-sm btn-outline-secondary me-1 btn-copy-api-key" data-api-key="${k.key}" title="Copiar chave">
                                                <i class="fas fa-copy"></i>
                                            </button>
                                            <button class="btn btn-sm btn-danger" onclick="deleteApiKey(${k.id})" title="Revogar/Excluir">
                                                <i class="fas fa-trash"></i>
                                            </button>
                                        </td>
                                    </tr>
                                `).join('') || '<tr><td colspan="5" class="text-center py-4 text-muted">Ainda não há chaves de API.</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Bind dos botões de copiar via event listener (evita problemas de escape no onclick inline)
        container.querySelectorAll('.btn-copy-api-key').forEach(btn => {
            btn.addEventListener('click', () => copyApiKey(btn.dataset.apiKey));
        });

    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Erro ao carregar chaves: ${escapeHtml(e.message)}</div>`;
    }
}

async function createApiKey() {
    const name = prompt("Defina uma identificação/nome para esta chave:");
    if (!name) return;
    try {
        const data = await apiRequest('/api_management/keys', 'POST', { name });
        if (data.success) {
            prompt("Chave gerada! COPIE E SALVE-A AGORA. Você não poderá vê-la por completo novamente:", data.key);
            renderApiKeysTab();
        } else {
            showNotification("Erro: " + data.error, "error");
        }
    } catch (e) {
        showNotification("Erro: " + e.message, "error");
    }
}

async function deleteApiKey(id) {
    if (!confirm("Tem certeza que deseja revogar esta chave? Qualquer integração externa que use ela deixará de funcionar imediatamente.")) return;
    try {
        const data = await apiRequest('/api_management/keys/' + id, 'DELETE');
        if (data.success) {
            showNotification(data.message, "success");
            renderApiKeysTab();
        } else {
            showNotification("Erro: " + data.error, "error");
        }
    } catch (e) {
        showNotification("Erro: " + e.message, "error");
    }
}

function copyApiKey(key) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(key).then(() => {
            showNotification('Chave copiada para a área de transferência!', 'success');
        }).catch(() => {
            copyApiKeyFallback(key);
        });
    } else {
        copyApiKeyFallback(key);
    }
}

function copyApiKeyFallback(key) {
    const textarea = document.createElement('textarea');
    textarea.value = key;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
        document.execCommand('copy');
        showNotification('Chave copiada para a área de transferência!', 'success');
    } catch (err) {
        showNotification('Não foi possível copiar. Selecione manualmente.', 'error');
    }
    document.body.removeChild(textarea);
}

async function renderNotificationsTab() {
    const container = document.getElementById('notifications-content');
    if (!container) return;
    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border text-primary"></div></div>';

    try {
        const settings = await apiRequest('/notification-settings');

        // Verificar se container ainda existe no DOM apos async
        if (!document.getElementById('notifications-content')) return;

        container.innerHTML = `
            <form id="notificationsForm" onsubmit="saveNotificationSettings(event)">
                <div class="row">
                    <div class="col-md-6 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-light">
                                <h5 class="mb-0"><i class="fas fa-envelope me-2"></i>E-mail (SMTP)</h5>
                            </div>
                            <div class="card-body">
                                <p class="text-muted small">Configuração global de servidor SMTP para envio de logs de finalização de pipeline via E-mail.</p>
                                <div class="mb-3">
                                    <label>Servidor SMTP</label>
                                    <input type="text" class="form-control" id="smtp_server" value="${settings.smtp_server || ''}" placeholder="smtp.gmail.com">
                                </div>
                                <div class="row">
                                    <div class="col-md-4 mb-3">
                                        <label>Porta SMTP</label>
                                        <input type="number" class="form-control" id="smtp_port" value="${settings.smtp_port || '587'}">
                                    </div>
                                    <div class="col-md-8 mb-3">
                                        <label>Email Remetente</label>
                                        <input type="email" class="form-control" id="smtp_from_email" value="${settings.smtp_from_email || ''}" placeholder="noreply@minhaempresa.com">
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label>Usuário SMTP</label>
                                        <input type="text" class="form-control" id="smtp_user" value="${settings.smtp_user || ''}">
                                    </div>
                                    <div class="col-md-6 mb-3">
                                        <label>Senha SMTP</label>
                                        <input type="password" class="form-control" id="smtp_password" value="${settings.smtp_password ? '••••••••' : ''}" placeholder="${settings.smtp_password ? '••••••••' : 'Senha'}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-light">
                                <h5 class="mb-0"><i class="fab fa-whatsapp me-2"></i>WhatsApp Genérico (Webhook)</h5>
                            </div>
                            <div class="card-body">
                                <p class="text-muted small">Configure sua API de WhatsApp (Ex: Z-API, Evolution API). Use as variáveis de contexto nos campos.</p>
                                <div class="mb-3">
                                    <label>URL (Webhook HTTP Endpoint)</label>
                                    <input type="text" class="form-control" id="whatsapp_api_url" value="${settings.whatsapp_api_url || ''}" placeholder="https://api.../sendText/{{phone}}">
                                    <small class="text-muted d-block">Var: <code>{{phone}}</code></small>
                                </div>
                                <div class="mb-3">
                                    <label>Método HTTP</label>
                                    <select class="form-select" id="whatsapp_api_method">
                                        <option value="POST" ${settings.whatsapp_api_method === 'POST' ? 'selected' : ''}>POST</option>
                                        <option value="GET" ${settings.whatsapp_api_method === 'GET' ? 'selected' : ''}>GET</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label>Headers Extras (JSON Opcional)</label>
                                    <textarea class="form-control" id="whatsapp_api_headers" rows="2" placeholder='{"Authorization": "Bearer TOKEN"}' style="font-family: monospace">${settings.whatsapp_api_headers || ''}</textarea>
                                </div>
                                <div class="mb-3">
                                    <label>Estrutura Payload (Body / JSON)</label>
                                    <textarea class="form-control" id="whatsapp_api_body" rows="3" placeholder='{"number": "{{phone}}", "text": "{{message}}"}' style="font-family: monospace">${settings.whatsapp_api_body || ''}</textarea>
                                    <small class="text-muted d-block">Vars: <code>{{phone}}</code>, <code>{{message}}</code>, etc.</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- Alertas e Salvar -->
                <div class="d-flex justify-content-end mb-4">
                    <button type="submit" class="btn btn-success btn-lg"><i class="fas fa-save me-2"></i>Salvar Configurações de Notificações</button>
                </div>
            </form>
        `;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Erro ao carregar configs: ${e.message}</div>`;
    }
}

async function saveNotificationSettings(e) {
    if (e) e.preventDefault();
    const payload = {
        smtp_server: document.getElementById('smtp_server').value,
        smtp_port: parseInt(document.getElementById('smtp_port').value) || null,
        smtp_user: document.getElementById('smtp_user').value,
        smtp_password: document.getElementById('smtp_password').value,
        smtp_from_email: document.getElementById('smtp_from_email').value,
        whatsapp_api_url: document.getElementById('whatsapp_api_url').value,
        whatsapp_api_method: document.getElementById('whatsapp_api_method').value,
        whatsapp_api_headers: document.getElementById('whatsapp_api_headers').value,
        whatsapp_api_body: document.getElementById('whatsapp_api_body').value
    };

    // Evita enviar senha placeholder de volta ao servidor se não foi alterada
    if (payload.smtp_password === '********' || payload.smtp_password === '••••••••') {
        delete payload.smtp_password;
    }

    try {
        const data = await apiRequest('/notification-settings', 'PUT', payload);
        if (data.success) {
            showNotification('Configurações Globais de Notificações Atualizadas', 'success');
            renderNotificationsTab();
        } else {
            showNotification('Erro: ' + data.error, 'error');
        }
    } catch (err) {
        showNotification('Erro: ' + err.message, 'error');
    }
}
// --- FIM NOVAS ABAS CONFIGURAÇŌES ---

// --- ABA POLITICAS DE BRANCH (movida do Dev Workspace) ---
async function renderBranchPoliciesTab() {
    const container = document.getElementById('branch-policies-content');
    if (!container) return;
    container.innerHTML = '<div class="text-center p-4"><div class="spinner-border text-primary"></div></div>';

    try {
    // Carregar dados usando funcoes do devworkspace (lazy load do modulo)
    try {
        await loadModule('integration-devworkspace');
    } catch (e) { /* modulo pode ja estar carregado */ }

    // Verificar se container ainda existe no DOM (usuario pode ter navegado)
    if (!document.getElementById('branch-policies-content')) return;

    const envId = parseInt(sessionStorage.getItem('active_environment_id')) || null;
    if (!envId) {
        container.innerHTML = '<div class="alert alert-warning m-3">Nenhum ambiente configurado.</div>';
        return;
    }

    // Carregar politicas e repositorios
    await dwLoadPolicies(envId);
    await dwLoadRepos();

    // Verificar se container ainda existe no DOM apos async
    if (!document.getElementById('branch-policies-content')) return;

    // Barra de controles (fora do card)
    let html = '<div class="d-flex justify-content-between align-items-center mb-3">' +
            '<div>' +
                '<h5 class="mb-1"><i class="fas fa-shield-alt me-2"></i>Politicas de Branch-Ambiente</h5>' +
                '<p class="text-muted small mb-0">Vincule branches a ambientes com regras de protecao para evitar push, pull ou commit indevido.</p>' +
            '</div>' +
            '<div class="d-flex gap-2 align-items-center">' +
                '<button class="btn btn-primary btn-sm" data-action="dwShowPolicyForm">' +
                    '<i class="fas fa-plus me-1"></i>Nova Politica' +
                '</button>' +
            '</div>' +
        '</div>';

    // Formulario (oculto por padrao, card separado)
    html += '<div id="dw-policy-form" style="display:none" class="card mb-3">' +
        '<div class="card-body">' +
            '<h6 class="mb-3"><i class="fas fa-plus-circle me-2"></i>Nova Politica</h6>' +
            '<div class="row g-2 mb-3">' +
                '<div class="col-md-4">' +
                    '<label class="form-label small fw-semibold">Repositorio</label>' +
                    '<select id="dw-policy-repo" class="form-select form-select-sm">' +
                        '<option value="">Selecione...</option>' +
                        dwRepos.map(function(r) {
                            return '<option value="' + dwEscapeHtml(r.name) + '">' + dwEscapeHtml(r.name) + '</option>';
                        }).join('') +
                    '</select>' +
                '</div>' +
                '<div class="col-md-4">' +
                    '<label class="form-label small fw-semibold">Branch</label>' +
                    '<input type="text" id="dw-policy-branch" class="form-control form-control-sm" placeholder="master">' +
                '</div>' +
            '</div>' +
            '<div class="row g-2 mb-3">' +
                '<div class="col-auto"><div class="form-check form-switch">' +
                    '<input class="form-check-input" type="checkbox" id="dw-pol-push" checked>' +
                    '<label class="form-check-label">Push</label></div></div>' +
                '<div class="col-auto"><div class="form-check form-switch">' +
                    '<input class="form-check-input" type="checkbox" id="dw-pol-pull" checked>' +
                    '<label class="form-check-label">Pull</label></div></div>' +
                '<div class="col-auto"><div class="form-check form-switch">' +
                    '<input class="form-check-input" type="checkbox" id="dw-pol-commit" checked>' +
                    '<label class="form-check-label">Commit</label></div></div>' +
                '<div class="col-auto"><div class="form-check form-switch">' +
                    '<input class="form-check-input" type="checkbox" id="dw-pol-create-branch">' +
                    '<label class="form-check-label">Criar Branch</label></div></div>' +
            '</div>' +
            '<div class="d-flex gap-2">' +
                '<button class="btn btn-primary btn-sm" onclick="bpSavePolicy()"><i class="fas fa-save me-1"></i>Salvar</button>' +
                '<button class="btn btn-outline-secondary btn-sm" data-action="dwCancelPolicy">Cancelar</button>' +
            '</div>' +
        '</div></div>';

    // Card de listagem de politicas
    html += '<div class="card"><div class="card-body">';
    if (dwPolicies.length === 0) {
        html += '<div class="text-center text-muted p-4">' +
            '<i class="fas fa-shield-alt fa-3x mb-3 opacity-50"></i>' +
            '<p>Nenhuma politica definida. Branches operam sem restricoes.</p></div>';
    } else {
        html += '<div class="table-responsive"><table class="table table-sm table-striped mb-0">' +
            '<thead><tr><th>Repositorio</th><th>Branch</th><th>Ambiente</th>' +
            '<th>Push</th><th>Pull</th><th>Commit</th><th>Criar Branch</th><th>Acoes</th></tr></thead><tbody>';
        for (let i = 0; i < dwPolicies.length; i++) {
            const p = dwPolicies[i];
            html += '<tr>' +
                '<td><code>' + dwEscapeHtml(p.repo_name) + '</code></td>' +
                '<td><code>' + dwEscapeHtml(p.branch_name) + '</code></td>' +
                '<td>' + dwEscapeHtml(p.environment_name || '') + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_push) + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_pull) + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_commit) + '</td>' +
                '<td>' + dwPolicyBadge(p.allow_create_branch) + '</td>' +
                '<td><button class="btn btn-outline-danger btn-sm" onclick="bpDeletePolicy(' + p.id + ')">' +
                    '<i class="fas fa-trash"></i></button></td></tr>';
        }
        html += '</tbody></table></div>';
    }
    html += '</div></div>';
    container.innerHTML = html;

    } catch (e) {
        console.error('Erro renderBranchPoliciesTab:', e);
        if (document.getElementById('branch-policies-content')) {
            container.innerHTML = '<div class="alert alert-danger m-3">Erro ao carregar politicas: ' + (e.message || e) + '</div>';
        }
    }
}

// Funcoes auxiliares para Politicas de Branch na aba Settings
window.bpSavePolicy = async function() {
    const repoName = document.getElementById('dw-policy-repo').value;
    const branchName = document.getElementById('dw-policy-branch').value.trim();
    if (!repoName || !branchName) {
        showNotification('Repositorio e branch obrigatorios', 'warning');
        return;
    }
    const envId = parseInt(sessionStorage.getItem('active_environment_id')) || null;
    if (!envId) {
        showNotification('Nenhum ambiente ativo', 'warning');
        return;
    }
    try {
        await apiRequest('/devworkspace/policies', 'POST', {
            environment_id: envId,
            repo_name: repoName,
            branch_name: branchName,
            allow_push: document.getElementById('dw-pol-push').checked,
            allow_pull: document.getElementById('dw-pol-pull').checked,
            allow_commit: document.getElementById('dw-pol-commit').checked,
            allow_create_branch: document.getElementById('dw-pol-create-branch').checked
        });
        showNotification('Politica criada com sucesso', 'success');
        await renderBranchPoliciesTab();
    } catch (e) {
        showNotification('Erro ao criar politica: ' + e.message, 'error');
    }
};

window.bpDeletePolicy = async function(policyId) {
    if (!confirm('Remover esta politica?')) return;
    try {
        await apiRequest('/devworkspace/policies/' + policyId, 'DELETE');
        showNotification('Politica removida', 'success');
        await renderBranchPoliciesTab();
    } catch (e) {
        showNotification('Erro ao remover: ' + e.message, 'error');
    }
};

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
function renderGithubSettingsTab() {
    const container = document.getElementById('github-content');
    container.innerHTML = `
        <div class="card">
            <div class="card-header"><h5><i class="fab fa-github me-2"></i>Configuração da Integração GitHub</h5></div>
            <div class="card-body">
                <form id="githubForm">
                    ${gitHubSettings.configured ? '<div class="alert alert-info mb-3"><i class="fas fa-check-circle me-2"></i>Token configurado. Insira um novo token para atualizar.</div>' : ''}
                    <div class="mb-3">
                        <label class="form-label">Personal Access Token (classic)</label>
                        <input type="password" class="form-control" id="githubToken" value="" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx">
                        <div class="text-muted">Token necessario para acessar os repositorios. <a href="https://github.com/settings/tokens/new?scopes=repo,read:user" target="_blank">Gerar novo token</a></div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Nome de Usuario GitHub</label>
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
        filteredVars = serverVariables.filter(v => v.name.trim().endsWith(`_${state.filterEnv}`));
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
        
        <!--Filtros de Ambiente-->
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
                                    <code>${escapeHtml(v.name)}</code>
                                    ${v.is_protected ? '<i class="fas fa-lock text-warning ms-2" title="Protegido"></i>' : ''}
                                </td>
                                <td class="text-truncate" style="max-width: 300px;" title="${v.is_password ? 'Valor oculto' : escapeHtml(v.value)}">
                                    ${v.is_password ? '<span class="text-muted"><i class="fas fa-key text-warning me-1"></i>••••••••</span>' : escapeHtml(v.value)}
                                </td>
                                <td class="text-muted">${escapeHtml(v.description || '-')}</td>
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
                                    <strong>${escapeHtml(s.display_name || s.name)}</strong>
                                    <small class="text-muted d-block">📦 ${escapeHtml(s.name)}</small>
                                </td>
                                <td><code>${escapeHtml(s.server_name || '-')}</code></td>
                                <td>${escapeHtml(envName)}</td>
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
    if (gitHubSettings.configured && gitHubSettings.username) {
        return `
            <div class="d-flex align-items-center">
                <span class="badge badge-success me-2">
                    <i class="fab fa-github me-1"></i>Conectado: ${gitHubSettings.username}
                </span>
            </div>
            `;
    } else {
        return `
            <span class="badge badge-warning">
                <i class="fab fa-github me-1"></i>GitHub nao configurado
            </span>
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
        // Preenche username se disponivel (token nunca fica no frontend)
        if (githubAuthData) {
            document.getElementById('githubUser').value = githubAuthData.username || '';
        } else {
            document.getElementById('githubUser').value = '';
        }
        document.getElementById('githubToken').value = '';
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
function clearGithubAuth() {
    gitHubSettings.configured = false;
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
