// =====================================================================
// INTEGRATION-CI-CD.JS
// Builds (CI), Releases (CD), Run View, históricos, logs SSE
// =====================================================================

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
                                <i class="fas fa-user"></i> ${escapeHtml(build.started_by_name || 'Sistema')}
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
                            <i class="fas fa-exclamation-circle"></i> ${escapeHtml(build.error_message)}
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
                                <strong>${idx + 1}.</strong> ${escapeHtml(log.command_name || 'Comando')}
                            </h6>
                            <small class="text-muted">${escapeHtml(log.command_description || '')}</small>
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
                            <pre class="code-viewer code-sm code-scroll-md code-wrap mt-2">${escapeHtml(log.output)}</pre>
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
                    logsHtml += `<pre class="code-viewer code-wrap code-scroll-md">${escapeHtml(log.output)}</pre>`;
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
            logText += `[${idx + 1}] ${log.command_name || 'Comando'}\\n`;
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

// calculateDuration removido - usando versão do integration-core.js

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
                        <i class="fas fa-terminal"></i> ${escapeHtml(log.command_name || 'Comando')}
                    </strong>
                    <span class="badge bg-${getStatusColor(log.status)}">
                        ${getStatusText(log.status)}
                    </span>
                </div>
                ${log.output ? `
                    <pre class="code-viewer code-scroll-md code-wrap">${escapeHtml(log.output)}</pre>
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
                                <i class="fas fa-user"></i> ${escapeHtml(release.deployed_by_name || 'Sistema')}
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
                            <i class="fas fa-exclamation-circle"></i> ${escapeHtml(release.error_message)}
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
                    <pre class="code-viewer code-sm code-wrap mb-0 flex-grow-1">${escapeHtml(log.output)}</pre>
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
                                <strong>${escapeHtml(log.command_name || 'Comando ' + log.command_order)}</strong>
                                <small class="text-muted ms-2">${formatTime(log.started_at)}</small>
                            </div>
                            <span class="badge bg-${levelClass.replace('text-', '')}">
                                ${escapeHtml(log.status)}
                            </span>
                        </div>
                        ${log.output ? `
                            <pre class="code-viewer code-sm code-scroll-md code-wrap mt-2 mb-0">${escapeHtml(log.output)}</pre>
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
                            <pre class="code-viewer code-sm code-scroll-md code-wrap mt-2 mb-0">${escapeHtml(log.output)}</pre>
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
                                <pre class="code-viewer code-sm code-wrap mb-0 mt-1">${escapeHtml(log.output || 'Sem output')}</pre>
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
                                <pre class="code-viewer code-sm code-wrap mb-0 mt-1">${escapeHtml(log.output || 'Sem output')}</pre>
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

                    // Se recebemos a flag -1 do backend (sinal final) finalizamos limpo
                    if (data.id === -1) {
                        eventSource.close();

                        // Atualiza o botão para fechar sem cor de erro
                        const modalFooter = document.querySelector('#releaseLogsModal .modal-footer');
                        const closeBtn = modalFooter?.querySelector('[data-bs-dismiss="modal"]');
                        if (closeBtn) {
                            closeBtn.classList.remove('btn-secondary');
                            closeBtn.classList.add('btn-success');
                            closeBtn.textContent = 'Fechar';
                        }
                    }
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
