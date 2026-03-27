// =====================================================================
// integration-source-control.js
// Controle de Versão — Painel Git (status, diff, stage, commit, push)
// =====================================================================

let scState = {
    repoId: null,
    repoName: null,
    branch: null,
    staged: [],
    modified: [],
    untracked: [],
    selectedFile: null,
    selectedFileType: null,
    selectedFileStaged: false,
    diffContent: '',
    diffIsNew: false,
    diffIsBinary: false,
    commits: [],
    isLoading: false
};

// =====================================================================
// PÁGINA PRINCIPAL
// =====================================================================

async function showSourceControl() {
    const contentArea = document.getElementById('content-area');
    contentArea.innerHTML = `
        <div class="text-center p-5">
            <div class="spinner-border text-primary"></div>
            <p class="mt-3">Carregando Controle de Versão...</p>
        </div>
    `;

    // Carrega repositórios se necessário
    if (!repositories || repositories.length === 0) {
        try { await loadRepositories(); } catch (e) {}
    }

    renderSourceControlPage();
}

function renderSourceControlPage() {
    const canWrite = isOperator();

    const repoOptions = (repositories || []).map(r =>
        `<option value="${r.id}" ${scState.repoId === r.id ? 'selected' : ''}>${escapeHtml(r.name)}</option>`
    ).join('');

    const content = `
        <div>
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <h2><i class="fas fa-code-branch me-2"></i>Controle de Versão</h2>
                    <p class="text-muted mb-0">Gerencie alterações, commits e push dos repositórios</p>
                </div>
            </div>

            <div class="sc-layout">
                <!-- Toolbar -->
                <div class="sc-toolbar">
                    <select id="scRepoSelect" class="form-select form-select-sm" style="max-width:220px" onchange="scSelectRepo(this.value)">
                        <option value="">Selecione um repositório...</option>
                        ${repoOptions}
                    </select>
                    <select id="scBranchSelect" class="form-select form-select-sm" style="max-width:180px" onchange="scSelectBranch(this.value)" disabled>
                        <option value="">Branch...</option>
                    </select>
                    <div class="ms-auto d-flex gap-2">
                        ${canWrite ? `
                        <button class="btn btn-sm btn-outline-success" onclick="scPush()" title="Push para remote" id="scPushBtn" disabled>
                            <i class="fas fa-arrow-up me-1"></i>Push
                        </button>` : ''}
                        <button class="btn btn-sm btn-outline-primary" onclick="refreshSourceControl()" title="Atualizar status" id="scRefreshBtn" disabled>
                            <i class="fas fa-sync-alt me-1"></i>Atualizar
                        </button>
                    </div>
                </div>

                <!-- Painel de Arquivos (esquerda) -->
                <div class="sc-files-panel" id="scFilesPanel">
                    <div class="sc-diff-empty">
                        <i class="fas fa-folder-open fa-2x mb-2 d-block"></i>
                        Selecione um repositório e branch
                    </div>
                </div>

                <!-- Diff Viewer (direita) -->
                <div class="sc-diff-panel" id="scDiffPanel">
                    <div class="sc-diff-empty">
                        <i class="fas fa-file-code fa-2x mb-2 d-block"></i>
                        Selecione um arquivo para ver o diff
                    </div>
                </div>

                <!-- Commit Bar -->
                <div class="sc-commit-bar" id="scCommitBar" style="display:none">
                    <textarea id="scCommitMessage" class="form-control form-control-sm" placeholder="Mensagem do commit..." rows="1"></textarea>
                    <button class="btn btn-sm btn-success" onclick="scCommit()" id="scCommitBtn" disabled>
                        <i class="fas fa-check me-1"></i>Commit <span id="scCommitCount"></span>
                    </button>
                </div>

                <!-- Histórico de Commits -->
                <div class="sc-history" id="scHistory" style="display:none">
                    <h6 class="mb-2"><i class="fas fa-history me-1"></i>Histórico de Commits</h6>
                    <div id="scHistoryContent"></div>
                </div>
            </div>
        </div>
    `;

    document.getElementById('content-area').innerHTML = content;

    // Se já tinha repo/branch selecionado, restaurar
    if (scState.repoId && scState.branch) {
        document.getElementById('scRepoSelect').value = scState.repoId;
        scLoadBranches(scState.repoId).then(() => {
            const branchSelect = document.getElementById('scBranchSelect');
            if (branchSelect) branchSelect.value = scState.branch;
            scLoadStatus();
        });
    }
}

// =====================================================================
// SELEÇÃO DE REPO E BRANCH
// =====================================================================

async function scSelectRepo(repoId) {
    if (!repoId) return;
    repoId = parseInt(repoId);
    const repo = repositories.find(r => r.id === repoId);
    if (!repo) return;

    scState.repoId = repoId;
    scState.repoName = repo.name;
    scState.branch = null;
    scState.staged = [];
    scState.modified = [];
    scState.untracked = [];
    scState.selectedFile = null;
    scState.diffContent = '';
    scState.commits = [];

    await scLoadBranches(repoId);
}

async function scLoadBranches(repoId) {
    const branchSelect = document.getElementById('scBranchSelect');
    if (!branchSelect) return;

    branchSelect.disabled = true;
    branchSelect.innerHTML = '<option value="">Carregando...</option>';

    try {
        const branches = await apiListBranches(repoId);
        if (!branches || branches.length === 0) {
            branchSelect.innerHTML = '<option value="">Nenhuma branch clonada</option>';
            return;
        }

        const placeholder = branches.length > 1
            ? '<option value="">Selecione uma branch...</option>'
            : '';
        branchSelect.innerHTML = placeholder + branches.map(b =>
            `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`
        ).join('');
        branchSelect.disabled = false;

        // Auto-selecionar: branch anterior, ou única branch disponível
        if (scState.branch && branches.includes(scState.branch)) {
            branchSelect.value = scState.branch;
            scSelectBranch(scState.branch);
        } else if (branches.length === 1) {
            scSelectBranch(branches[0]);
        }
    } catch (e) {
        branchSelect.innerHTML = '<option value="">Erro ao carregar</option>';
    }
}

async function scSelectBranch(branch) {
    if (!branch || !scState.repoId) return;

    scState.branch = branch;
    const branchSelect = document.getElementById('scBranchSelect');
    if (branchSelect) branchSelect.value = branch;

    const refreshBtn = document.getElementById('scRefreshBtn');
    if (refreshBtn) refreshBtn.disabled = false;

    const pushBtn = document.getElementById('scPushBtn');
    if (pushBtn) pushBtn.disabled = false;

    await scLoadStatus();
}

// =====================================================================
// CARREGAR STATUS (git status)
// =====================================================================

async function scLoadStatus() {
    if (!scState.repoId || !scState.branch) return;

    const filesPanel = document.getElementById('scFilesPanel');
    if (filesPanel) {
        filesPanel.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div></div>';
    }

    try {
        const [status, logData] = await Promise.all([
            apiGetGitStatus(scState.repoId, scState.branch),
            apiGetCommitLog(scState.repoId, scState.branch, 15)
        ]);

        scState.staged = status.staged || [];
        scState.modified = status.modified || [];
        scState.untracked = status.untracked || [];
        scState.commits = logData.commits || [];

        renderFilesPanel();
        renderCommitHistory();
        updateCommitBar();

        // Se tinha um arquivo selecionado, manter o diff
        if (scState.selectedFile) {
            const allFiles = [...scState.staged, ...scState.modified, ...scState.untracked];
            const stillExists = allFiles.find(f => f.path === scState.selectedFile);
            if (!stillExists) {
                scState.selectedFile = null;
                renderDiffEmpty();
            }
        }
    } catch (e) {
        if (filesPanel) {
            filesPanel.innerHTML = `<div class="text-danger text-center p-3"><i class="fas fa-exclamation-triangle me-1"></i>${escapeHtml(e.message || 'Erro ao carregar status')}</div>`;
        }
    }
}

async function refreshSourceControl() {
    await scLoadStatus();
    showNotification('Status atualizado', 'success');
}

// =====================================================================
// RENDER: PAINEL DE ARQUIVOS
// =====================================================================

function renderFilesPanel() {
    const filesPanel = document.getElementById('scFilesPanel');
    if (!filesPanel) return;

    const totalChanges = scState.staged.length + scState.modified.length + scState.untracked.length;

    if (totalChanges === 0) {
        filesPanel.innerHTML = `
            <div class="sc-diff-empty">
                <i class="fas fa-check-circle fa-2x mb-2 d-block text-success"></i>
                Nenhuma alteração pendente
            </div>`;
        return;
    }

    const canWrite = isOperator();
    let html = '';

    // Staged
    if (scState.staged.length > 0) {
        html += renderFileGroup('Staged', scState.staged, 'staged', 'text-success', canWrite);
    }

    // Modified
    if (scState.modified.length > 0) {
        html += renderFileGroup('Modificados', scState.modified, 'modified', 'text-warning', canWrite);
    }

    // Untracked
    if (scState.untracked.length > 0) {
        html += renderFileGroup('Não Rastreados', scState.untracked, 'untracked', 'text-secondary', canWrite);
    }

    filesPanel.innerHTML = html;
}

function renderFileGroup(title, files, type, colorClass, canWrite) {
    const isStaged = type === 'staged';

    const allAction = canWrite ? (isStaged
        ? `<button class="btn btn-sm btn-link p-0 text-warning" onclick="scUnstageAll()" title="Remover todos do staging"><i class="fas fa-minus"></i></button>`
        : `<button class="btn btn-sm btn-link p-0 text-success" onclick="scStageAll()" title="Adicionar todos ao staging"><i class="fas fa-plus"></i></button>`)
        : '';

    const fileItems = files.map(f => {
        const isActive = scState.selectedFile === f.path ? 'active' : '';
        const statusIcon = getStatusIcon(f.status);
        const escapedPath = escapeHtml(f.path);
        const jsonPath = escapedPath.replace(/'/g, "\\'");

        let actions = '';
        if (canWrite) {
            if (isStaged) {
                actions = `
                    <span class="sc-file-actions">
                        <button class="btn btn-outline-warning" onclick="event.stopPropagation(); scUnstageFile('${jsonPath}')" title="Remover do staging"><i class="fas fa-minus"></i></button>
                        <button class="btn btn-outline-danger" onclick="event.stopPropagation(); scDiscardFile('${jsonPath}', 'staged')" title="Descartar"><i class="fas fa-times"></i></button>
                    </span>`;
            } else {
                actions = `
                    <span class="sc-file-actions">
                        <button class="btn btn-outline-success" onclick="event.stopPropagation(); scStageFile('${jsonPath}')" title="Adicionar ao staging"><i class="fas fa-plus"></i></button>
                        <button class="btn btn-outline-danger" onclick="event.stopPropagation(); scDiscardFile('${jsonPath}', '${type}')" title="Descartar"><i class="fas fa-times"></i></button>
                    </span>`;
            }
        }

        return `
            <div class="sc-file-item ${isActive}" onclick="scSelectFile('${jsonPath}', '${type}', ${isStaged})">
                <span class="sc-status-${f.status}">${statusIcon}</span>
                <span class="sc-file-name" title="${escapedPath}">${escapedPath}</span>
                ${actions}
            </div>`;
    }).join('');

    return `
        <div class="sc-file-group">
            <div class="sc-file-group-header ${colorClass}">
                <span><i class="fas fa-chevron-down me-1"></i>${title} (${files.length})</span>
                ${allAction}
            </div>
            ${fileItems}
        </div>`;
}

function getStatusIcon(status) {
    const icons = { 'M': 'M', 'A': 'A', 'D': 'D', 'R': 'R', '?': '?' };
    return icons[status] || status;
}

// =====================================================================
// RENDER: DIFF VIEWER
// =====================================================================

async function scSelectFile(filePath, fileType, isStaged) {
    scState.selectedFile = filePath;
    scState.selectedFileType = fileType;
    scState.selectedFileStaged = isStaged;

    // Atualiza o highlight no painel de arquivos
    document.querySelectorAll('.sc-file-item').forEach(el => el.classList.remove('active'));
    const activeItem = [...document.querySelectorAll('.sc-file-item')].find(el =>
        el.querySelector('.sc-file-name')?.title === filePath
    );
    if (activeItem) activeItem.classList.add('active');

    const diffPanel = document.getElementById('scDiffPanel');
    if (!diffPanel) return;

    diffPanel.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div></div>';

    try {
        const isUntracked = fileType === 'untracked';
        const data = await apiGetFileDiff(scState.repoId, scState.branch, filePath, isStaged, isUntracked);

        scState.diffContent = data.diff;
        scState.diffIsNew = data.is_new;
        scState.diffIsBinary = data.is_binary;

        renderDiffViewer();
    } catch (e) {
        diffPanel.innerHTML = `<div class="text-danger p-3">${escapeHtml(e.message || 'Erro ao carregar diff')}</div>`;
    }
}

function renderDiffViewer() {
    const diffPanel = document.getElementById('scDiffPanel');
    if (!diffPanel) return;

    if (scState.diffIsBinary) {
        diffPanel.innerHTML = `
            <div class="sc-diff-empty">
                <i class="fas fa-file-archive fa-2x mb-2 d-block"></i>
                Arquivo binário — diff não disponível
            </div>`;
        return;
    }

    if (!scState.diffContent) {
        diffPanel.innerHTML = `
            <div class="sc-diff-empty">
                <i class="fas fa-equals fa-2x mb-2 d-block"></i>
                Sem diferenças para exibir
            </div>`;
        return;
    }

    const header = `<div class="mb-2 pb-2 border-bottom" style="font-size:0.85rem">
        <i class="fas fa-file-code me-1"></i>
        <strong>${escapeHtml(scState.selectedFile)}</strong>
        ${scState.diffIsNew ? ' <span class="badge bg-success ms-1">Novo</span>' : ''}
    </div>`;

    if (scState.diffIsNew) {
        // Arquivo novo: mostra conteúdo com numeração e highlight
        const ext = (scState.selectedFile || '').split('.').pop();
        const lines = scState.diffContent.split('\n').map((line, i) => {
            const hl = highlightCode(escapeHtml(line), ext);
            return `<div class="diff-line diff-line-add"><span class="line-num">${i + 1}</span>${hl}</div>`;
        }).join('');
        diffPanel.innerHTML = header + lines;
    } else {
        const ext = (scState.selectedFile || '').split('.').pop();
        diffPanel.innerHTML = header + renderDiffLines(scState.diffContent, ext);
    }
}

function renderDiffLines(rawDiff, ext) {
    return rawDiff.split('\n')
        .filter(line =>
            !line.startsWith('diff --git') &&
            !line.startsWith('index ') &&
            !line.startsWith('new file mode') &&
            !line.startsWith('deleted file mode') &&
            !line.startsWith('old mode') &&
            !line.startsWith('new mode') &&
            !line.startsWith('similarity index') &&
            !line.startsWith('rename from') &&
            !line.startsWith('rename to') &&
            !line.startsWith('--- ') &&
            !line.startsWith('+++ ')
        )
        .map(line => {
            let cls = 'diff-line';
            if (line.startsWith('+')) cls = 'diff-line diff-line-add';
            else if (line.startsWith('-')) cls = 'diff-line diff-line-del';
            else if (line.startsWith('@@')) cls = 'diff-line diff-line-info';
            const content = line.startsWith('@@') ? escapeHtml(line) : highlightCode(escapeHtml(line), ext);
            return `<div class="${cls}">${content}</div>`;
        }).join('');
}

function renderDiffEmpty() {
    const diffPanel = document.getElementById('scDiffPanel');
    if (diffPanel) {
        diffPanel.innerHTML = `
            <div class="sc-diff-empty">
                <i class="fas fa-file-code fa-2x mb-2 d-block"></i>
                Selecione um arquivo para ver o diff
            </div>`;
    }
}

// =====================================================================
// RENDER: COMMIT BAR E HISTÓRICO
// =====================================================================

function updateCommitBar() {
    const commitBar = document.getElementById('scCommitBar');
    const commitBtn = document.getElementById('scCommitBtn');
    const commitCount = document.getElementById('scCommitCount');

    if (!commitBar || !isOperator()) return;

    const totalChanges = scState.staged.length + scState.modified.length + scState.untracked.length;
    commitBar.style.display = totalChanges > 0 || scState.commits.length > 0 ? 'flex' : 'none';

    if (commitBtn) {
        commitBtn.disabled = scState.staged.length === 0;
    }
    if (commitCount) {
        commitCount.textContent = scState.staged.length > 0 ? `(${scState.staged.length})` : '';
    }
}

function renderCommitHistory() {
    const historyDiv = document.getElementById('scHistory');
    const historyContent = document.getElementById('scHistoryContent');
    if (!historyDiv || !historyContent) return;

    if (scState.commits.length === 0) {
        historyDiv.style.display = 'none';
        return;
    }

    historyDiv.style.display = 'block';

    const rows = scState.commits.map(c => {
        const date = new Date(c.date).toLocaleString('pt-BR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
        const hash = escapeHtml(c.short_hash);
        return `
            <tr class="sc-commit-row" onclick="scToggleCommitFiles('${hash}')" style="cursor:pointer" title="Clique para ver arquivos alterados">
                <td class="commit-hash"><i class="fas fa-chevron-right me-1 sc-commit-chevron" id="scChevron_${hash}" style="font-size:0.7em;transition:transform 0.2s"></i>${hash}</td>
                <td>${escapeHtml(c.message)}</td>
                <td class="text-muted">${escapeHtml(c.author)}</td>
                <td class="text-muted text-nowrap">${date}</td>
            </tr>
            <tr class="sc-commit-files-row" id="scCommitFiles_${hash}" style="display:none">
                <td colspan="4" class="p-0">
                    <div class="sc-commit-files-content" id="scCommitFilesContent_${hash}"></div>
                </td>
            </tr>`;
    }).join('');

    historyContent.innerHTML = `
        <table class="table table-sm table-hover mb-0">
            <thead><tr>
                <th style="width:90px">Hash</th>
                <th>Mensagem</th>
                <th style="width:120px">Autor</th>
                <th style="width:140px">Data</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

async function scToggleCommitFiles(shortHash) {
    const filesRow = document.getElementById(`scCommitFiles_${shortHash}`);
    const filesContent = document.getElementById(`scCommitFilesContent_${shortHash}`);
    const chevron = document.getElementById(`scChevron_${shortHash}`);
    if (!filesRow || !filesContent) return;

    // Toggle visibilidade
    if (filesRow.style.display !== 'none') {
        filesRow.style.display = 'none';
        if (chevron) chevron.style.transform = 'rotate(0deg)';
        return;
    }

    filesRow.style.display = '';
    if (chevron) chevron.style.transform = 'rotate(90deg)';

    // Se já carregou, não recarrega
    if (filesContent.dataset.loaded === 'true') return;

    filesContent.innerHTML = '<div class="text-center p-2"><div class="spinner-border spinner-border-sm"></div> Carregando...</div>';

    try {
        const data = await apiGetCommitFiles(scState.repoId, scState.branch, shortHash);
        const files = data.files || [];

        if (files.length === 0) {
            filesContent.innerHTML = '<div class="text-muted p-2 ps-4">Nenhum arquivo alterado</div>';
        } else {
            const statusIcons = { 'M': '<span class="sc-status-M">M</span>', 'A': '<span class="sc-status-A">A</span>', 'D': '<span class="sc-status-D">D</span>', 'R': '<span class="sc-status-R">R</span>' };
            filesContent.innerHTML = '<div class="sc-commit-files-list">' + files.map(f => {
                const icon = statusIcons[f.status] || `<span>${escapeHtml(f.status)}</span>`;
                const escapedPath = escapeHtml(f.path);
                return `<div class="sc-commit-file-item" onclick="event.stopPropagation(); scShowCommitFileDiff('${shortHash}', '${escapedPath.replace(/'/g, "\\'")}')" title="Ver diff">
                    ${icon} <span>${escapedPath}</span>
                </div>`;
            }).join('') + '</div>';
        }
        filesContent.dataset.loaded = 'true';
    } catch (e) {
        filesContent.innerHTML = `<div class="text-danger p-2 ps-4">${escapeHtml(e.message || 'Erro ao carregar')}</div>`;
    }
}

async function scShowCommitFileDiff(shortHash, filePath) {
    const diffPanel = document.getElementById('scDiffPanel');
    if (!diffPanel) return;

    scState.selectedFile = filePath;
    scState.selectedFileType = 'commit';

    diffPanel.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div></div>';

    try {
        const data = await apiGetCommitDiff(scState.repoId, scState.branch, shortHash, filePath);
        const content = data.diff || '';

        if (!content) {
            diffPanel.innerHTML = '<div class="sc-diff-empty"><i class="fas fa-equals fa-2x mb-2 d-block"></i>Sem diferenças para exibir</div>';
            return;
        }

        const header = `<div class="mb-2 pb-2 border-bottom" style="font-size:0.85rem">
            <i class="fas fa-file-code me-1"></i>
            <strong>${escapeHtml(filePath)}</strong>
            <span class="badge bg-secondary ms-1">${escapeHtml(shortHash)}</span>
        </div>`;

        diffPanel.innerHTML = header + renderDiffLines(content);
    } catch (e) {
        diffPanel.innerHTML = `<div class="text-danger p-3">${escapeHtml(e.message || 'Erro ao carregar diff')}</div>`;
    }
}

// =====================================================================
// AÇÕES: STAGE / UNSTAGE
// =====================================================================

async function scStageFile(filePath) {
    if (!scState.repoId || !scState.branch) return;

    try {
        await apiStageFiles(scState.repoId, {
            branch_name: scState.branch,
            files: [filePath],
            action: 'stage'
        });
        await scLoadStatus();
    } catch (e) {
        showNotification('Erro ao adicionar ao staging: ' + (e.message || ''), 'error');
    }
}

async function scUnstageFile(filePath) {
    if (!scState.repoId || !scState.branch) return;

    try {
        await apiStageFiles(scState.repoId, {
            branch_name: scState.branch,
            files: [filePath],
            action: 'unstage'
        });
        await scLoadStatus();
    } catch (e) {
        showNotification('Erro ao remover do staging: ' + (e.message || ''), 'error');
    }
}

async function scStageAll() {
    if (!scState.repoId || !scState.branch) return;

    const allFiles = [
        ...scState.modified.map(f => f.path),
        ...scState.untracked.map(f => f.path)
    ];

    if (allFiles.length === 0) return;

    try {
        await apiStageFiles(scState.repoId, {
            branch_name: scState.branch,
            files: allFiles,
            action: 'stage'
        });
        await scLoadStatus();
        showNotification(`${allFiles.length} arquivo(s) adicionado(s) ao staging`, 'success');
    } catch (e) {
        showNotification('Erro ao adicionar ao staging: ' + (e.message || ''), 'error');
    }
}

async function scUnstageAll() {
    if (!scState.repoId || !scState.branch) return;

    const allFiles = scState.staged.map(f => f.path);
    if (allFiles.length === 0) return;

    try {
        await apiStageFiles(scState.repoId, {
            branch_name: scState.branch,
            files: allFiles,
            action: 'unstage'
        });
        await scLoadStatus();
        showNotification(`${allFiles.length} arquivo(s) removido(s) do staging`, 'success');
    } catch (e) {
        showNotification('Erro ao remover do staging: ' + (e.message || ''), 'error');
    }
}

// =====================================================================
// AÇÕES: COMMIT E PUSH
// =====================================================================

async function scCommit() {
    if (!scState.repoId || !scState.branch) return;
    if (scState.staged.length === 0) {
        showNotification('Nenhum arquivo staged para commit', 'warning');
        return;
    }

    const messageInput = document.getElementById('scCommitMessage');
    const message = messageInput ? messageInput.value.trim() : '';
    if (!message) {
        showNotification('Digite uma mensagem de commit', 'warning');
        if (messageInput) messageInput.focus();
        return;
    }

    const commitBtn = document.getElementById('scCommitBtn');
    if (commitBtn) { commitBtn.disabled = true; commitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Commitando...'; }

    try {
        const result = await apiCommitChanges(scState.repoId, {
            branch_name: scState.branch,
            commit_message: message
        });
        showNotification(result.message || 'Commit realizado!', 'success');
        if (messageInput) messageInput.value = '';
        await scLoadStatus();
    } catch (e) {
        showNotification('Erro ao commitar: ' + (e.message || ''), 'error');
    } finally {
        if (commitBtn) { commitBtn.disabled = false; commitBtn.innerHTML = '<i class="fas fa-check me-1"></i>Commit <span id="scCommitCount"></span>'; }
        updateCommitBar();
    }
}

async function scPush() {
    if (!scState.repoId || !scState.branch) return;

    if (!confirm(`Push do branch "${scState.branch}" para o remote?`)) return;

    const pushBtn = document.getElementById('scPushBtn');
    if (pushBtn) { pushBtn.disabled = true; pushBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Pushing...'; }

    try {
        const result = await apiPushOnly(scState.repoId, {
            branch_name: scState.branch
        });
        showNotification(result.message || 'Push realizado!', 'success');
    } catch (e) {
        showNotification('Erro ao fazer push: ' + (e.message || ''), 'error');
    } finally {
        if (pushBtn) { pushBtn.disabled = false; pushBtn.innerHTML = '<i class="fas fa-arrow-up me-1"></i>Push'; }
    }
}

// =====================================================================
// AÇÕES: DISCARD
// =====================================================================

async function scDiscardFile(filePath, fileType) {
    if (!scState.repoId || !scState.branch) return;

    const typeLabel = { 'staged': 'staged', 'modified': 'modificado', 'untracked': 'não rastreado' };
    if (!confirm(`Descartar alterações em "${filePath}" (${typeLabel[fileType] || fileType})?\n\nEsta ação não pode ser desfeita!`)) return;

    try {
        await apiDiscardChanges(scState.repoId, {
            branch_name: scState.branch,
            files: [filePath],
            file_type: fileType
        });
        showNotification('Alterações descartadas', 'success');
        if (scState.selectedFile === filePath) {
            scState.selectedFile = null;
            renderDiffEmpty();
        }
        await scLoadStatus();
    } catch (e) {
        showNotification('Erro ao descartar: ' + (e.message || ''), 'error');
    }
}
