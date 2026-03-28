// =====================================================================
// INTEGRATION-AGENT.JS
// Agente Inteligente — Memoria Persistente com busca FTS5
// =====================================================================

// ===== ESTADO LOCAL DO MODULO =====
var agStats = {};
var agChunks = [];
var agChunksTotal = 0;
var agChunksPage = 1;
var agFiles = [];
var agSearchResults = [];
var agSessions = [];
var agActiveTab = 'chat';
var AG_PER_PAGE = 30;

// Estado do chat (Item 9B)
var agChatMessages = [];
var agChatSessionId = null;
var AG_SESSION_TTL_MS = 2 * 60 * 60 * 1000; // 2 horas de inatividade
var agChatLoading = false;

// =====================================================================
// ENTRY POINT
// =====================================================================

function showAgent() {
    var content = document.getElementById('content-area');
    if (!content) return;

    content.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h4 class="mb-0"><i class="fas fa-robot me-2"></i>GolIAs</h4>
        </div>
        <div id="ag-tab-content">
            <div class="text-center py-4"><div class="spinner-border text-primary"></div></div>
        </div>
    `;

    agSwitchTab('chat');
}

// =====================================================================
// NAVEGACAO DE ABAS
// =====================================================================

async function agSwitchTab(tab) {
    agActiveTab = tab;

    // Atualizar abas ativas
    document.querySelectorAll('.nav-link[data-tab]').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
    });

    var container = document.getElementById('ag-tab-content');
    if (!container) return;

    container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';

    try {
        if (tab === 'chat') {
            await agRenderChat(container);
        } else if (tab === 'search') {
            await agRenderSearch(container);
        } else if (tab === 'files') {
            await agRenderFiles(container);
        } else if (tab === 'chunks') {
            await agRenderChunks(container);
        } else if (tab === 'llm') {
            // Redirecionar para Settings > LLM
            window.location.hash = 'settings';
            setTimeout(() => { const t = document.getElementById('llm-settings-tab'); if(t) new bootstrap.Tab(t).show(); }, 300);
            return;
        } else if (tab === 'stats') {
            await agRenderStats(container);
        }
    } catch (e) {
        console.error('Erro ao renderizar aba:', e);
        container.innerHTML = '<div class="alert alert-danger">Erro ao carregar aba: ' + e.message + '</div>';
    }
}

// =====================================================================
// ABA: BUSCA BM25
// =====================================================================

async function agRenderSearch(container) {
    container.innerHTML = `
        <div class="card">
            <div class="card-body">
                <div class="row g-2 mb-3">
                    <div class="col-md-8">
                        <div class="input-group">
                            <span class="input-group-text"><i class="fas fa-search"></i></span>
                            <input type="text" id="ag-search-input" class="form-control"
                                   placeholder="Buscar na memória do agente (ex: faturamento, SC5, Thread Error...)"
                                   onkeydown="if(event.key==='Enter') agDoSearch()">
                        </div>
                    </div>
                    <div class="col-md-3">
                        <select id="ag-search-type" class="form-select">
                            <option value="">Todos os tipos</option>
                            <option value="semantic">Semântica</option>
                            <option value="episodic">Episódica</option>
                            <option value="procedural">Procedural</option>
                        </select>
                    </div>
                    <div class="col-md-1">
                        <button class="btn btn-primary w-100" onclick="agDoSearch()">
                            <i class="fas fa-search"></i>
                        </button>
                    </div>
                </div>
                <div id="ag-search-results"></div>
            </div>
        </div>
    `;

    // Se já tinha resultados anteriores, mostrar
    if (agSearchResults.length > 0) {
        agRenderSearchResults();
    }
}

async function agDoSearch() {
    var query = document.getElementById('ag-search-input');
    var typeSelect = document.getElementById('ag-search-type');
    if (!query || !query.value.trim()) return;

    var resultsDiv = document.getElementById('ag-search-results');
    if (!resultsDiv) return;

    resultsDiv.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary"></div> Buscando...</div>';

    try {
        var qs = '?q=' + encodeURIComponent(query.value.trim()) + '&limit=20';
        if (typeSelect && typeSelect.value) qs += '&type=' + typeSelect.value;

        var envId = sessionStorage.getItem('active_environment_id');
        if (envId) qs += '&environment_id=' + envId;

        var resp = await apiRequest('/agent/memory/search' + qs);
        agSearchResults = resp.results || [];
        agRenderSearchResults();
    } catch (e) {
        resultsDiv.innerHTML = '<div class="alert alert-danger">Erro na busca: ' + e.message + '</div>';
    }
}

function agRenderSearchResults() {
    var resultsDiv = document.getElementById('ag-search-results');
    if (!resultsDiv) return;

    if (agSearchResults.length === 0) {
        resultsDiv.innerHTML = '<div class="text-muted text-center py-3"><i class="fas fa-info-circle me-1"></i>Nenhum resultado encontrado</div>';
        return;
    }

    var html = '<div class="small text-muted mb-2">' + agSearchResults.length + ' resultado(s) encontrado(s)</div>';

    agSearchResults.forEach(function(r) {
        var typeBadge = agTypeBadge(r.chunk_type);
        var preview = agEscapeHtml(r.content || '').substring(0, 400);
        if ((r.content || '').length > 400) preview += '...';

        html += `
            <div class="card mb-2">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-start mb-1">
                        <div>
                            ${typeBadge}
                            <strong class="ms-1">${agEscapeHtml(r.section_title || '(sem título)')}</strong>
                        </div>
                        <small class="text-muted">${agEscapeHtml(r.source_file || '')}</small>
                    </div>
                    <div class="small" style="white-space: pre-wrap; max-height: 150px; overflow-y: auto;">${preview}</div>
                    <div class="d-flex justify-content-between mt-1">
                        <small class="text-muted">Score: ${Math.abs(r.rank || 0).toFixed(2)}</small>
                        <button class="btn btn-sm btn-outline-secondary py-0" onclick="agViewChunk(${r.chunk_id})">
                            <i class="fas fa-expand-alt me-1"></i>Ver completo
                        </button>
                    </div>
                </div>
            </div>
        `;
    });

    resultsDiv.innerHTML = html;
}

// =====================================================================
// ABA: ARQUIVOS DE MEMORIA
// =====================================================================

async function agRenderFiles(container) {
    try {
        var resp = await apiRequest('/agent/memory/files');
        agFiles = resp.files || [];
    } catch (e) {
        agFiles = [];
    }

    if (agFiles.length === 0) {
        container.innerHTML = '<div class="alert alert-info">Nenhum arquivo de memória encontrado. Clique em "Indexar" para iniciar.</div>';
        return;
    }

    var html = '<div class="row"><div class="col-md-4">';
    html += '<div class="card"><div class="card-header fw-bold"><i class="fas fa-folder-open me-1"></i>Arquivos</div>';
    html += '<div class="list-group list-group-flush">';

    agFiles.forEach(function(f) {
        var icon = f.path === 'MEMORY.md' ? 'fa-brain' : f.path === 'TOOLS.md' ? 'fa-tools' : 'fa-file-alt';
        var sizeKb = (f.size / 1024).toFixed(1);
        html += `
            <a href="#" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
               onclick="agViewFile('${agEscapeHtml(f.path)}'); return false;">
                <span><i class="fas ${icon} me-2"></i>${agEscapeHtml(f.path)}</span>
                <span class="badge bg-secondary">${sizeKb} KB</span>
            </a>
        `;
    });

    html += '</div></div></div>';
    html += '<div class="col-md-8"><div id="ag-file-viewer" class="card"><div class="card-body text-muted text-center py-5"><i class="fas fa-arrow-left me-2"></i>Selecione um arquivo para visualizar</div></div></div>';
    html += '</div>';

    container.innerHTML = html;
}

async function agViewFile(path) {
    var viewer = document.getElementById('ag-file-viewer');
    if (!viewer) return;

    viewer.innerHTML = '<div class="card-body text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></div>';

    try {
        var resp = await apiRequest('/agent/memory/file?path=' + encodeURIComponent(path));
        var content = resp.content || '';
        var ext = path.split('.').pop() || 'md';

        // Highlight de sintaxe usando funcao global
        var escaped = agEscapeHtml(content);
        var highlighted = (typeof highlightCode === 'function') ? highlightCode(escaped, ext) : escaped;
        var withLines = (typeof addLineNumbers === 'function') ? addLineNumbers(highlighted) : highlighted;

        viewer.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <span><i class="fas fa-file-alt me-1"></i>${agEscapeHtml(path)}</span>
                <span class="badge bg-info">${(content.length / 1024).toFixed(1)} KB</span>
            </div>
            <div class="card-body p-0">
                <pre class="code-viewer code-scroll-lg m-0">${withLines}</pre>
            </div>
        `;
    } catch (e) {
        viewer.innerHTML = '<div class="card-body"><div class="alert alert-danger">Erro ao ler arquivo: ' + e.message + '</div></div>';
    }
}

// =====================================================================
// ABA: CHUNKS INDEXADOS
// =====================================================================

async function agRenderChunks(container) {
    var offset = (agChunksPage - 1) * AG_PER_PAGE;
    var qs = '?limit=' + AG_PER_PAGE + '&offset=' + offset;

    try {
        var resp = await apiRequest('/agent/memory/chunks' + qs);
        agChunks = resp.chunks || [];
        agChunksTotal = resp.total || 0;
    } catch (e) {
        agChunks = [];
        agChunksTotal = 0;
    }

    if (agChunksTotal === 0) {
        container.innerHTML = '<div class="alert alert-info">Nenhum chunk indexado. Clique em "Indexar" para processar os arquivos de memória.</div>';
        return;
    }

    var html = '<div class="d-flex justify-content-between align-items-center mb-2">';
    html += '<span class="text-muted">' + agChunksTotal + ' chunks indexados</span>';
    html += agPagination(agChunksTotal, agChunksPage, AG_PER_PAGE, 'agLoadChunksPage');
    html += '</div>';

    html += '<div class="table-responsive"><table class="table table-sm table-hover">';
    html += '<thead><tr><th>#</th><th>Arquivo</th><th>Tipo</th><th>Seção</th><th>Tamanho</th><th>Criado em</th><th></th></tr></thead>';
    html += '<tbody>';

    agChunks.forEach(function(c) {
        var typeBadge = agTypeBadge(c.chunk_type);
        html += `<tr>
            <td>${c.chunk_id}</td>
            <td><small>${agEscapeHtml(c.source_file || '')}</small></td>
            <td>${typeBadge}</td>
            <td>${agEscapeHtml(c.section_title || '')}</td>
            <td><small>${c.content_length} chars</small></td>
            <td><small>${(c.created_at || '').substring(0, 16)}</small></td>
            <td><button class="btn btn-sm btn-outline-secondary py-0" onclick="agViewChunk(${c.chunk_id})"><i class="fas fa-eye"></i></button></td>
        </tr>`;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

async function agLoadChunksPage(page) {
    agChunksPage = page;
    var container = document.getElementById('ag-tab-content');
    if (container) await agRenderChunks(container);
}

async function agViewChunk(chunkId) {
    try {
        var chunk = await apiRequest('/agent/memory/chunks/' + chunkId);
        var typeBadge = agTypeBadge(chunk.chunk_type);
        var escaped = agEscapeHtml(chunk.content || '');

        var modal = `
            <div class="modal fade" id="agChunkModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${typeBadge} ${agEscapeHtml(chunk.section_title || 'Chunk #' + chunkId)}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body p-0">
                            <div class="px-3 py-2 border-bottom small text-muted">
                                <span class="me-3"><i class="fas fa-file me-1"></i>${agEscapeHtml(chunk.source_file || '')}</span>
                                <span class="me-3"><i class="fas fa-ruler me-1"></i>${(chunk.content || '').length} caracteres</span>
                                <span><i class="fas fa-clock me-1"></i>${(chunk.created_at || '').substring(0, 16)}</span>
                            </div>
                            <pre class="code-viewer code-scroll-lg m-0">${escaped}</pre>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remover modal anterior se existir
        var old = document.getElementById('agChunkModal');
        if (old) old.remove();

        document.body.insertAdjacentHTML('beforeend', modal);
        var modalEl = new bootstrap.Modal(document.getElementById('agChunkModal'));
        modalEl.show();

        // Limpar ao fechar
        document.getElementById('agChunkModal').addEventListener('hidden.bs.modal', function() {
            this.remove();
        });
    } catch (e) {
        console.error('Erro ao carregar chunk:', e);
    }
}

// =====================================================================
// ABA: ESTATISTICAS
// =====================================================================

async function agRenderStats(container) {
    try {
        agStats = await apiRequest('/agent/memory/stats');
    } catch (e) {
        agStats = {};
    }

    var byType = agStats.chunks_by_type || {};
    var byFile = agStats.chunks_by_file || {};

    var html = '<div class="row g-3 mb-3">';

    // Cards de resumo
    html += agStatCard('fa-puzzle-piece', 'Total Chunks', agStats.total_chunks || 0, 'primary');
    html += agStatCard('fa-brain', 'Semânticos', byType.semantic || 0, 'info');
    html += agStatCard('fa-clock', 'Episódicos', byType.episodic || 0, 'warning');
    html += agStatCard('fa-tools', 'Procedurais', byType.procedural || 0, 'success');
    html += agStatCard('fa-search', 'Buscas', agStats.total_searches || 0, 'secondary');
    html += agStatCard('fa-database', 'DB Size', (agStats.db_size_mb || 0) + ' MB', 'dark');

    html += '</div>';

    // Chunks por arquivo
    html += '<div class="row g-3">';
    html += '<div class="col-md-6"><div class="card"><div class="card-header fw-bold"><i class="fas fa-file-alt me-1"></i>Chunks por Arquivo</div>';
    html += '<div class="list-group list-group-flush">';
    Object.keys(byFile).forEach(function(file) {
        html += '<div class="list-group-item d-flex justify-content-between"><span>' + agEscapeHtml(file) + '</span><span class="badge bg-primary">' + byFile[file] + '</span></div>';
    });
    if (Object.keys(byFile).length === 0) {
        html += '<div class="list-group-item text-muted">Nenhum chunk indexado</div>';
    }
    html += '</div></div></div>';

    // Arquivos disponíveis
    html += '<div class="col-md-6"><div class="card"><div class="card-header fw-bold"><i class="fas fa-folder me-1"></i>Arquivos de Memória</div>';
    html += '<div class="list-group list-group-flush">';
    (agStats.md_files || []).forEach(function(f) {
        var sizeKb = (f.size / 1024).toFixed(1);
        html += '<div class="list-group-item d-flex justify-content-between"><span><i class="fas fa-file-alt me-1 text-muted"></i>' + agEscapeHtml(f.path) + '</span><small class="text-muted">' + sizeKb + ' KB</small></div>';
    });
    if ((agStats.md_files || []).length === 0) {
        html += '<div class="list-group-item text-muted">Nenhum arquivo encontrado</div>';
    }
    html += '</div></div></div>';
    html += '</div>';

    // Última ingestão
    if (agStats.last_ingest) {
        html += '<div class="mt-2 small text-muted"><i class="fas fa-clock me-1"></i>Última ingestão: ' + agStats.last_ingest + '</div>';
    }

    container.innerHTML = html;
}

// =====================================================================
// AÇÕES: INDEXAR / REBUILD
// =====================================================================

async function agIngest() {
    if (!confirm('Indexar todos os arquivos de memória no FTS5?')) return;

    try {
        var envId = sessionStorage.getItem('active_environment_id');
        var body = envId ? { environment_id: parseInt(envId) } : {};
        var resp = await apiRequest('/agent/memory/ingest', 'POST', body);
        showNotification(resp.message || 'Ingestão concluída', 'success');
        agSwitchTab(agActiveTab);
    } catch (e) {
        showNotification('Erro na ingestão: ' + e.message, 'error');
    }
}

async function agRebuild() {
    if (!confirm('Reconstruir índice FTS5 do zero? Isso apaga e re-indexa todos os chunks.')) return;

    try {
        var resp = await apiRequest('/agent/memory/rebuild', 'POST', {});
        showNotification(resp.message || 'Índice reconstruído', 'success');
        agSwitchTab(agActiveTab);
    } catch (e) {
        showNotification('Erro no rebuild: ' + e.message, 'error');
    }
}

// =====================================================================
// ABA: CHAT DO AGENTE (Item 9B)
// =====================================================================

async function agRenderChat(container) {
    // Restaurar sessão anterior (se existir e não expirada)
    if (!agChatSessionId) {
        var saved = agRestoreSession();
        if (saved) {
            agChatSessionId = saved.session_id;
            await agLoadSessionHistory(saved.session_id);
        }
    }

    // Verificar se LLM está ativo (com retry — hard refresh demora)
    var llmStatus = {};
    for (let _retry = 0; _retry < 3; _retry++) {
        try {
            llmStatus = await apiRequest('/agent/llm/status');
            break;
        } catch (e) {
            if (_retry < 2) await new Promise(r => setTimeout(r, 800));
        }
    }

    var llmActive = llmStatus.mode === 'llm';
    var llmProvider = llmStatus.provider || '';
    var llmModel = llmStatus.model || '';

    // Mostrar status no badge mesmo se rule-based
    var statusBadge = llmActive
        ? `<span class="badge bg-success" style="font-size:0.7rem;"><i class="fas fa-brain me-1"></i>${llmProvider.toUpperCase()}</span>`
        : `<span class="badge bg-secondary" style="font-size:0.7rem;"><i class="fas fa-cog me-1"></i>RULE-BASED</span>`;

    container.innerHTML = `
        <div class="card" style="height: 70vh; display: flex; flex-direction: column;">
            <div class="card-header d-flex justify-content-between align-items-center py-2">
                <span><i class="fas fa-comments me-1"></i>Chat com GolIAs</span>
                <div class="d-flex align-items-center gap-2">
                    <span id="ag-llm-badge">${statusBadge}</span>
                    <small class="text-muted" id="ag-chat-session-info">
                        ${agChatSessionId ? 'Sessão ativa' : 'Sem sessão'}
                    </small>
                    <button class="btn btn-sm btn-outline-secondary" onclick="agNewChatSession()" title="Nova sessão">
                        <i class="fas fa-plus"></i>
                    </button>
                </div>
            </div>
            <div class="card-body p-3" id="ag-chat-messages" style="flex: 1; overflow-y: auto;">
                ${agChatMessages.length === 0 ? agChatWelcome() : ''}
            </div>
            <div class="card-footer py-2">
                <div id="ag-attachment-preview" class="d-none mb-1 small"></div>
                <div class="input-group">
                    <button class="btn btn-outline-secondary btn-sm" onclick="document.getElementById('ag-file-input').click()" title="Anexar arquivo ou imagem">
                        <i class="fas fa-paperclip"></i>
                    </button>
                    <input type="file" id="ag-file-input" class="d-none" accept=".txt,.log,.csv,.json,.prw,.tlpp,.prx,.aph,.ch,.py,.js,.html,.css,.md,.xml,.ini,.cfg,.sql,.png,.jpg,.jpeg,.gif,.bmp,.webp" onchange="agHandleFileAttach(event)" multiple>
                    <input type="text" id="ag-chat-input" class="form-control form-control-sm"
                           placeholder="Pergunte ao analista: alertas, banco de dados, auditoria, configurações..."
                           onkeydown="if(event.key==='Enter' && !event.shiftKey) { event.preventDefault(); agSendMessage(); }"
                           onpaste="agHandlePaste(event)">
                    <button class="btn btn-primary btn-sm" onclick="agSendMessage()" id="ag-chat-send">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        </div>
    `;

    // Renderizar mensagens existentes
    if (agChatMessages.length > 0) {
        agRenderChatMessages();
    }

}

async function agUpdateLLMBadge() {
    var badge = document.getElementById('ag-llm-badge');
    if (!badge) return;
    try {
        var resp = await apiRequest('/agent/llm/status');
        if (resp.mode === 'llm') {
            badge.className = 'badge bg-success';
            badge.innerHTML = '<i class="fas fa-brain me-1"></i>' + (resp.provider || 'LLM');
            badge.title = 'Modelo: ' + (resp.model || '?');
        } else {
            badge.className = 'badge bg-secondary';
            badge.innerHTML = '<i class="fas fa-cog me-1"></i>Rule-based';
            badge.title = 'Sem LLM configurado. Configure na aba LLM.';
        }
    } catch (e) {
        badge.className = 'badge bg-secondary';
        badge.textContent = 'Rule-based';
    }
}

function agChatWelcome() {
    // Carregar dados do ambiente ativo para contexto
    var envId = sessionStorage.getItem('active_environment_id');
    var envName = document.querySelector('.environment-selector .dropdown-toggle, select[id*=environment]');
    var envLabel = envName ? envName.textContent.trim() : 'Ambiente';

    // Montar welcome com mini-status e sugestoes contextuais
    var html = '<div class="py-3 px-2">';
    html += '<div class="d-flex align-items-center gap-2 mb-3">';
    html += '<i class="fas fa-robot text-primary" style="font-size: 1.5rem;"></i>';
    html += '<div>';
    html += '<strong>GolIAs</strong>';
    html += '<small class="text-muted d-block">Operador inteligente do AtuDIC — execute comandos em linguagem natural</small>';
    html += '</div>';
    html += '</div>';

    // Mini-dashboard do ambiente (carregado async)
    html += '<div id="ag-welcome-status" class="mb-3">';
    html += '<div class="row g-2" id="ag-welcome-cards"></div>';
    html += '</div>';

    // Sugestoes contextuais — frases reais que o usuario diria
    html += '<div class="border-top pt-3">';
    html += '<small class="text-muted d-block mb-2">Experimente perguntar:</small>';
    html += '<div class="d-flex flex-wrap gap-2">';

    var suggestions = [
        { text: 'Tem algum alerta critico agora?', icon: 'fa-exclamation-triangle' },
        { text: 'Compare o dicionario entre HML e PRD', icon: 'fa-exchange-alt' },
        { text: 'Rode o pipeline de compilacao', icon: 'fa-play' },
        { text: 'Quais variaveis estao configuradas?', icon: 'fa-cog' },
    ];

    suggestions.forEach(function(s) {
        html += '<button class="btn btn-sm btn-outline-secondary text-start" style="font-size:0.8rem;" onclick="agQuickQuestion(\'' + s.text.replace(/'/g, "\\'") + '\')">';
        html += '<i class="fas ' + s.icon + ' me-1 opacity-50"></i>' + s.text;
        html += '</button>';
    });

    html += '</div></div></div>';

    // Carregar status async
    setTimeout(function() { agLoadWelcomeStatus(envId); }, 100);

    return html;
}

async function agLoadWelcomeStatus(envId) {
    var container = document.getElementById('ag-welcome-cards');
    if (!container || !envId) return;

    try {
        var data = await apiRequest('/dashboard/modules-summary', 'GET');
        var alertData = {};
        try { alertData = await apiRequest('/log-alerts/summary?environment_id=' + envId + '&days=1'); } catch(e) {}

        var criticalAlerts = 0;
        var totalAlerts = 0;
        if (alertData.summary) {
            alertData.summary.forEach(function(s) {
                totalAlerts += s.count;
                if (s.severity === 'critical') criticalAlerts += s.count;
            });
        }

        var cards = [
            { label: 'Alertas (24h)', value: totalAlerts, icon: 'fa-bell', color: criticalAlerts > 0 ? 'danger' : 'success', extra: criticalAlerts > 0 ? criticalAlerts + ' critico(s)' : 'Sem criticos' },
            { label: 'Conexoes DB', value: data.database ? data.database.total : 0, icon: 'fa-database', color: 'primary', extra: '' },
            { label: 'Agendamentos', value: data.schedules ? data.schedules.active : 0, icon: 'fa-clock', color: 'info', extra: data.schedules ? data.schedules.total + ' total' : '' },
        ];

        var html = '';
        cards.forEach(function(c) {
            html += '<div class="col-auto">';
            html += '<div class="d-flex align-items-center gap-2 px-3 py-2 rounded" style="background: rgba(var(--bs-' + c.color + '-rgb, 0,0,0), 0.08);">';
            html += '<i class="fas ' + c.icon + ' text-' + c.color + '"></i>';
            html += '<div>';
            html += '<div class="fw-bold" style="font-size:1.1em;">' + c.value + '</div>';
            html += '<small class="text-muted">' + c.label + '</small>';
            if (c.extra) html += '<small class="d-block text-muted" style="font-size:0.7em;">' + c.extra + '</small>';
            html += '</div></div></div>';
        });

        container.innerHTML = html;
    } catch (e) {
        // Silenciar — welcome funciona sem status
    }
}

function agQuickQuestion(text) {
    var input = document.getElementById('ag-chat-input');
    if (input) {
        input.value = text;
        agSendMessage();
    }
}

function agSaveSession() {
    if (!agChatSessionId) return;
    var envId = sessionStorage.getItem('active_environment_id') || '';
    localStorage.setItem('ag_session', JSON.stringify({
        session_id: agChatSessionId,
        environment_id: envId,
        last_activity: Date.now()
    }));
}

function agClearSession() {
    localStorage.removeItem('ag_session');
}

function agRestoreSession() {
    try {
        var raw = localStorage.getItem('ag_session');
        if (!raw) return null;
        var data = JSON.parse(raw);
        // Verificar expiração (2h de inatividade)
        if (Date.now() - data.last_activity > AG_SESSION_TTL_MS) {
            agClearSession();
            return null;
        }
        // Verificar se o ambiente é o mesmo
        var currentEnv = sessionStorage.getItem('active_environment_id') || '';
        if (data.environment_id !== currentEnv) {
            agClearSession();
            return null;
        }
        return data;
    } catch (e) {
        agClearSession();
        return null;
    }
}

async function agLoadSessionHistory(sessionId) {
    try {
        var resp = await apiRequest('/agent/chat/history?session_id=' + encodeURIComponent(sessionId) + '&limit=50');
        if (resp.messages && resp.messages.length > 0) {
            agChatMessages = resp.messages.map(function(m) {
                return {
                    role: m.role,
                    content: m.content || '',
                    intent: m.intent || '',
                    confidence: m.confidence || 0,
                    sources_consulted: m.sources_consulted || [],
                    created_at: m.created_at || ''
                };
            });
            return true;
        }
    } catch (e) {
        // Sessão inválida — limpar
        agClearSession();
    }
    return false;
}

async function agNewChatSession() {
    agChatSessionId = null;
    agChatMessages = [];
    agClearSession();
    var container = document.getElementById('ag-tab-content');
    if (container) await agRenderChat(container);
}

// Anexos pendentes para envio
var agPendingAttachments = [];

function agHandleFileAttach(event) {
    var files = event.target.files;
    if (!files || files.length === 0) return;

    var imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'];
    var preview = document.getElementById('ag-attachment-preview');

    for (var i = 0; i < files.length; i++) {
        var file = files[i];
        var ext = file.name.split('.').pop().toLowerCase();
        var isImage = imageExts.indexOf(ext) >= 0;
        var maxSize = isImage ? 5 * 1024 * 1024 : 2 * 1024 * 1024; // 5MB imagem, 2MB texto

        if (file.size > maxSize) {
            showNotification('Arquivo ' + file.name + ' muito grande (máx ' + (maxSize / 1024 / 1024) + 'MB)', 'warning');
            continue;
        }

        (function(f, isImg) {
            var reader = new FileReader();
            reader.onload = function(e) {
                if (isImg) {
                    agPendingAttachments.push({
                        type: 'image',
                        name: f.name,
                        content: e.target.result.split(',')[1], // base64 sem prefixo
                        mime_type: f.type || 'image/png'
                    });
                } else {
                    agPendingAttachments.push({
                        type: 'text',
                        name: f.name,
                        content: e.target.result
                    });
                }
                agUpdateAttachmentPreview();
            };
            if (isImg) {
                reader.readAsDataURL(f);
            } else {
                reader.readAsText(f, 'utf-8');
            }
        })(file, isImage);
    }

    // Reset input para permitir reselecionar mesmo arquivo
    event.target.value = '';
}

function agUpdateAttachmentPreview() {
    var preview = document.getElementById('ag-attachment-preview');
    if (!preview) return;

    if (agPendingAttachments.length === 0) {
        preview.classList.add('d-none');
        preview.innerHTML = '';
        return;
    }

    preview.classList.remove('d-none');
    var html = '';
    agPendingAttachments.forEach(function(att, idx) {
        var icon = att.type === 'image' ? 'fa-image text-success' : 'fa-file-alt text-info';
        html += '<span class="badge bg-dark bg-opacity-25 me-1 mb-1"><i class="fas ' + icon + ' me-1"></i>' +
                agEscapeHtml(att.name) +
                ' <i class="fas fa-times ms-1" style="cursor:pointer;opacity:0.7;" onclick="agRemoveAttachment(' + idx + ')"></i></span>';
    });
    preview.innerHTML = html;
}

function agRemoveAttachment(idx) {
    agPendingAttachments.splice(idx, 1);
    agUpdateAttachmentPreview();
}

function agHandlePaste(event) {
    var items = (event.clipboardData || event.originalEvent.clipboardData).items;
    if (!items) return;

    for (var i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
            event.preventDefault();
            var file = items[i].getAsFile();
            if (!file) continue;

            var reader = new FileReader();
            reader.onload = function(e) {
                var timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
                agPendingAttachments.push({
                    type: 'image',
                    name: 'screenshot_' + timestamp + '.png',
                    content: e.target.result.split(',')[1],
                    mime_type: file.type || 'image/png'
                });
                agUpdateAttachmentPreview();
                showNotification('Imagem colada com sucesso!', 'success');
            };
            reader.readAsDataURL(file);
            break; // Só uma imagem por paste
        }
    }
}

/**
 * Envia mensagem via streaming SSE (POST /api/agent/chat/stream).
 * Atualiza o DOM progressivamente conforme chunks chegam.
 * Retorna a resposta completa ao final.
 */
async function agSendMessageStream(body) {
    var headers = getHeaders();
    headers['Content-Type'] = 'application/json';

    var response = await fetch(API_BASE_URL + '/agent/chat/stream', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(body)
    });

    if (!response.ok) {
        throw new Error('Stream falhou: HTTP ' + response.status);
    }

    // Adicionar mensagem do assistente vazia (sera preenchida progressivamente)
    var streamMsg = {
        role: 'assistant',
        content: '',
        intent: '',
        mode: 'streaming',
        created_at: new Date().toISOString()
    };
    agChatMessages.push(streamMsg);
    agRenderChatMessages();

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var fullResponse = null;

    while (true) {
        var result = await reader.read();
        if (result.done) break;

        buffer += decoder.decode(result.value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop(); // Ultimo fragmento incompleto volta pro buffer

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (!line.startsWith('data: ')) continue;

            try {
                var data = JSON.parse(line.substring(6));

                if (data.error) {
                    streamMsg.content += '\n\nErro: ' + data.error;
                    agRenderChatMessages();
                    return { text: streamMsg.content, error: data.error };
                }

                if (data.chunk) {
                    streamMsg.content += data.chunk;
                    // Atualizar DOM progressivamente (a cada chunk)
                    agRenderChatMessages();
                }

                if (data.done && data.response) {
                    fullResponse = data.response;
                    // Atualizar mensagem com metadados completos
                    streamMsg.content = fullResponse.text || streamMsg.content;
                    streamMsg.intent = fullResponse.intent || '';
                    streamMsg.confidence = fullResponse.confidence;
                    streamMsg.mode = fullResponse.mode || 'llm-stream';
                    streamMsg.llm_provider = fullResponse.llm_provider || '';
                    streamMsg.llm_model = fullResponse.llm_model || '';
                    streamMsg.sources_consulted = fullResponse.sources_consulted || [];
                    streamMsg.tools_used = fullResponse.tools_used || [];
                    streamMsg.react_steps = fullResponse.react_steps || [];
                    streamMsg.token_usage = fullResponse.token_usage || null;
                    agRenderChatMessages();
                }
            } catch (parseErr) {
                // Ignorar linhas mal-formadas
            }
        }
    }

    return fullResponse || { text: streamMsg.content };
}


async function agSendMessage() {
    var input = document.getElementById('ag-chat-input');
    if (!input || (!input.value.trim() && agPendingAttachments.length === 0) || agChatLoading) return;

    var message = input.value.trim() || '(arquivo anexado)';
    input.value = '';

    // Criar sessão se não existe
    if (!agChatSessionId) {
        try {
            var envId = sessionStorage.getItem('active_environment_id');
            var resp = await apiRequest('/agent/chat/session', 'POST', {
                environment_id: envId ? parseInt(envId) : null
            });
            agChatSessionId = resp.session_id;
            agSaveSession();
            var info = document.getElementById('ag-chat-session-info');
            if (info) info.textContent = 'Sessão ativa';
        } catch (e) {
            showNotification('Erro ao criar sessão: ' + e.message, 'error');
            return;
        }
    }

    // Montar display da mensagem (com indicação de anexos)
    var displayMsg = message;
    if (agPendingAttachments.length > 0) {
        var attNames = agPendingAttachments.map(function(a) { return a.name; }).join(', ');
        displayMsg = message + (message ? '\n' : '') + '📎 ' + attNames;
    }

    // Adicionar mensagem do usuário
    agChatMessages.push({ role: 'user', content: displayMsg, created_at: new Date().toISOString() });
    agRenderChatMessages();

    // Capturar e limpar anexos pendentes
    var attachmentsToSend = agPendingAttachments.slice();
    agPendingAttachments = [];
    agUpdateAttachmentPreview();

    // Mostrar indicador de loading
    agChatLoading = true;
    agRenderChatLoading(true);

    try {
        var envId = sessionStorage.getItem('active_environment_id');
        var body = {
            session_id: agChatSessionId,
            message: message,
            environment_id: envId ? parseInt(envId) : null
        };
        if (attachmentsToSend.length > 0) {
            body.attachments = attachmentsToSend;
        }

        // Se ha pending_action e usuario confirmou, enviar no body
        if (window._agPendingAction) {
            var confirmWords = ['sim', 'pode', 'manda', 'vai', 'bora', 'confirmo', 'yes', 'ok', 'positivo', 'afirmativo', 'confirma', 'execute', 'roda', 'faz', 'manda ver'];
            var msgLower = message.toLowerCase().trim();
            if (confirmWords.some(function(w) { return msgLower === w || msgLower.startsWith(w + ' ') || msgLower.startsWith(w + ',') || msgLower.startsWith(w + '!'); })) {
                body.pending_action = window._agPendingAction;
                window._agPendingAction = null;
            }
        }

        // Tentar streaming SSE primeiro, fallback para blocking
        var resp = null;
        var streamSuccess = false;

        if (!body.pending_action) {
            try {
                resp = await agSendMessageStream(body);
                streamSuccess = true;
            } catch (streamErr) {
                console.warn('Streaming indisponivel, usando fallback blocking:', streamErr.message);
            }
        }

        // Fallback: rota blocking (ou pending_action)
        if (!streamSuccess) {
            resp = await apiRequest('/agent/chat/message', 'POST', body);
        }

        // Armazenar pending_action se houver (confirmacao pendente)
        if (resp.pending_action) {
            window._agPendingAction = resp.pending_action;
        } else {
            window._agPendingAction = null;
        }

        // Adicionar tools_used ao sources
        var sources = resp.sources_consulted || [];
        if (resp.tools_used && resp.tools_used.length > 0) {
            resp.tools_used.forEach(function(t) {
                if (sources.indexOf('TOOL:' + t) === -1) sources.push('TOOL:' + t);
            });
        }

        // Adicionar resposta do agente (se streaming, ja foi adicionada progressivamente)
        if (!streamSuccess) {
            agChatMessages.push({
                role: 'assistant',
                content: resp.text || '',
                intent: resp.intent,
                confidence: resp.confidence,
                sections: resp.sections || [],
                links: resp.links || [],
                sources_consulted: sources,
                mode: resp.mode || 'rule-based',
                llm_provider: resp.llm_provider || '',
                llm_model: resp.llm_model || '',
                react_steps: resp.react_steps || [],
                token_usage: resp.token_usage || null,
                created_at: new Date().toISOString()
            });
        }
    } catch (e) {
        agChatMessages.push({
            role: 'assistant',
            content: 'Erro ao processar mensagem: ' + e.message,
            intent: 'error',
            created_at: new Date().toISOString()
        });
    }

    agChatLoading = false;
    agSaveSession(); // Atualizar timestamp de atividade
    agRenderChatMessages();
}

function agRenderChatMessages() {
    var container = document.getElementById('ag-chat-messages');
    if (!container) return;

    var html = '';
    agChatMessages.forEach(function(msg) {
        if (msg.role === 'user') {
            html += agRenderUserMessage(msg);
        } else {
            html += agRenderAssistantMessage(msg);
        }
    });

    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;
}

var agStepSource = null;

function agRenderChatLoading(show) {
    var container = document.getElementById('ag-chat-messages');
    if (!container) return;

    var loadingEl = document.getElementById('ag-chat-loading');
    if (show && !loadingEl) {
        container.insertAdjacentHTML('beforeend',
            '<div id="ag-chat-loading" class="d-flex align-items-center gap-2 mb-3">' +
            '<div class="rounded-circle bg-primary text-white d-flex align-items-center justify-content-center" style="width:32px;height:32px;font-size:0.8rem;"><i class="fas fa-robot"></i></div>' +
            '<div class="spinner-border spinner-border-sm text-primary"></div>' +
            '<small class="text-muted" id="ag-loading-text">Pensando...</small></div>'
        );
        container.scrollTop = container.scrollHeight;
        agStartStepStream();
    } else if (!show && loadingEl) {
        loadingEl.remove();
        agStopStepStream();
    }
}

function agStartStepStream() {
    agStopStepStream();
    try {
        agStepSource = new EventSource('/api/agent/steps/stream');
        agStepSource.onmessage = function(event) {
            try {
                var data = JSON.parse(event.data);
                if (data.type === 'keepalive') return;
                var stepData = data.data || data;
                var desc = stepData.description || '';
                var stepType = stepData.type || '';
                if (desc) {
                    var el = document.getElementById('ag-loading-text');
                    if (el) {
                        // Icone contextual por tipo de step
                        var icon = '';
                        if (stepType === 'agent_dispatch') icon = '🤖 ';
                        else if (stepType === 'orchestration') icon = '🎯 ';
                        else if (stepType === 'chain_step') icon = '🔗 ';
                        else if (stepType === 'replan') icon = '🔄 ';
                        else if (stepType === 'tool_call') icon = '🔧 ';
                        else if (stepType === 'composing') icon = '✍️ ';
                        el.textContent = icon + desc;
                    }
                    var container = document.getElementById('ag-chat-messages');
                    if (container) container.scrollTop = container.scrollHeight;
                }
            } catch (e) { /* ignora parse error */ }
        };
        agStepSource.onerror = function() {
            agStopStepStream();
        };
    } catch (e) { /* SSE não suportado */ }
}

function agStopStepStream() {
    if (agStepSource) {
        agStepSource.close();
        agStepSource = null;
    }
}

function agRenderUserMessage(msg) {
    return `
        <div class="d-flex justify-content-end mb-3">
            <div class="bg-primary text-white rounded-3 px-3 py-2" style="max-width: 75%;">
                <div>${agEscapeHtml(msg.content)}</div>
                <div class="text-end mt-1" style="opacity: 0.7; font-size: 0.7rem;">${agFormatTime(msg.created_at)}</div>
            </div>
        </div>
    `;
}

function agRenderAssistantMessage(msg) {
    // Badge do provider (só se LLM)
    var modeBadge = '';
    if (msg.llm_provider) {
        modeBadge = '<span class="badge bg-success me-1" style="font-size:0.65rem;" title="Modelo: ' + agEscapeHtml(msg.llm_model || '') + '"><i class="fas fa-brain me-1"></i>' + agEscapeHtml(msg.llm_provider) + '</span>';
    }

    // Mostrar sources só quando tiver TOOL de ação executada (não poluir com leitura)
    var sourcesBadges = '';
    if (msg.sources_consulted && msg.sources_consulted.length > 0) {
        var actionTools = msg.sources_consulted.filter(function(s) {
            return s.startsWith('TOOL:run_') || s.startsWith('TOOL:execute_') ||
                   s.startsWith('TOOL:git_') || s.startsWith('TOOL:acknowledge') ||
                   s.startsWith('TOOL:toggle_') || s.startsWith('TOOL:query_') ||
                   s.startsWith('TOOL:compare_');
        });
        if (actionTools.length > 0) {
            sourcesBadges = actionTools.map(function(s) {
                return '<span class="badge bg-warning text-dark me-1" style="font-size:0.65rem;"><i class="fas fa-cog me-1"></i>' + agEscapeHtml(s.replace('TOOL:', '')) + '</span>';
            }).join('');
        }
    }

    // React steps (se modo react)
    var reactStepsHtml = '';
    if (msg.react_steps && msg.react_steps.length > 0) {
        var stepsItems = msg.react_steps.map(function(step) {
            var icon = step.type === 'tool_executed'
                ? (step.success ? '<i class="fas fa-check-circle text-success"></i>' : '<i class="fas fa-times-circle text-danger"></i>')
                : step.type === 'blocked'
                ? '<i class="fas fa-ban text-warning"></i>'
                : step.type === 'budget_exceeded'
                ? '<i class="fas fa-coins text-warning"></i>'
                : '<i class="fas fa-flag-checkered text-info"></i>';
            var label = step.tool || step.type;
            return '<div class="d-flex align-items-center gap-1 small text-muted">' + icon + ' ' + agEscapeHtml(label) + '</div>';
        }).join('');
        reactStepsHtml = '<div class="border rounded p-2 mb-2" style="font-size:0.75rem;background:var(--bs-tertiary-bg,#f8f9fa);">' +
            '<div class="fw-bold mb-1"><i class="fas fa-project-diagram me-1"></i>Steps do agente</div>' +
            stepsItems + '</div>';
    }

    // Token usage badge (se react)
    var tokenBadge = '';
    if (msg.token_usage && msg.token_usage.total_tokens > 0) {
        tokenBadge = '<span class="badge bg-secondary me-1" style="font-size:0.6rem;" title="Budget: ' +
            msg.token_usage.total_tokens + '/' + msg.token_usage.max_tokens + ' tokens">' +
            '<i class="fas fa-coins me-1"></i>' + msg.token_usage.budget_percent_used + '% budget</span>';
    }

    // Mode badge (react, agent, orchestrated)
    if (msg.mode === 'react') {
        modeBadge += '<span class="badge bg-info me-1" style="font-size:0.65rem;"><i class="fas fa-sync-alt me-1"></i>ReAct</span>';
    } else if (msg.mode && msg.mode.startsWith('agent:')) {
        var agentName = msg.mode.replace('agent:', '');
        modeBadge += '<span class="badge bg-info me-1" style="font-size:0.65rem;"><i class="fas fa-user-cog me-1"></i>' + agEscapeHtml(agentName) + '</span>';
    } else if (msg.mode && msg.mode.startsWith('orchestrated:')) {
        var orchPattern = msg.mode.replace('orchestrated:', '');
        var orchIcon = orchPattern === 'fan_out' ? 'fa-project-diagram' : 'fa-link';
        var orchLabel = orchPattern === 'fan_out' ? 'Paralelo' : 'Cadeia';
        modeBadge += '<span class="badge bg-purple me-1" style="font-size:0.65rem;background-color:#6f42c1 !important;"><i class="fas ' + orchIcon + ' me-1"></i>' + orchLabel + '</span>';
    }

    // Confidence badge
    var confidenceBadge = '';
    if (typeof msg.confidence === 'number' && msg.confidence > 0) {
        var confPct = Math.round(msg.confidence * 100);
        var confColor = confPct >= 80 ? 'success' : confPct >= 50 ? 'warning' : 'danger';
        var confLabel = confPct >= 80 ? 'Alta' : confPct >= 50 ? 'Média' : 'Baixa';
        confidenceBadge = '<span class="badge bg-' + confColor + ' me-1" style="font-size:0.6rem;opacity:0.85;" title="Confiança: ' + confPct + '%"><i class="fas fa-signal me-1"></i>' + confPct + '% ' + confLabel + '</span>';
    }

    // Renderizar conteudo com markdown simples
    var rawContent = msg.content || '';
    if (!rawContent.trim()) {
        // Fallback visual para resposta vazia — nunca mostrar bolha vazia
        rawContent = '_Processando... A ferramenta foi executada mas a resposta não foi gerada. Tente novamente._';
    }
    var content = agSimpleMarkdown(rawContent);

    // Secoes expansiveis desabilitadas — manter chat limpo
    var sectionsHtml = '';

    // Links só quando ação foi executada (não poluir chat normal)
    var linksHtml = '';

    return `
        <div class="d-flex mb-3">
            <div class="rounded-circle bg-primary text-white d-flex align-items-center justify-content-center me-2 flex-shrink-0" style="width:32px;height:32px;font-size:0.8rem;">
                <i class="fas fa-robot"></i>
            </div>
            <div class="rounded-3 px-3 py-2 ag-msg-assistant" style="max-width: 85%;">
                <div class="d-flex align-items-center flex-wrap mb-1">
                    ${modeBadge}
                    ${confidenceBadge}
                    ${tokenBadge}
                    ${sourcesBadges}
                </div>
                ${reactStepsHtml}
                <div>${content}</div>
                ${sectionsHtml}
                ${linksHtml}
                <div class="d-flex justify-content-between align-items-center mt-1">
                    <div class="ag-feedback-btns" style="font-size:0.75rem;">
                        <button class="btn btn-sm p-0 border-0 text-muted" onclick="agSendFeedback(this, 1, ${JSON.stringify(msg.intent || '')}, ${JSON.stringify(msg.id || '')})" title="Resposta útil" style="opacity:0.5;"><i class="fas fa-thumbs-up"></i></button>
                        <button class="btn btn-sm p-0 border-0 text-muted ms-1" onclick="agSendFeedback(this, -1, ${JSON.stringify(msg.intent || '')}, ${JSON.stringify(msg.id || '')})" title="Resposta ruim" style="opacity:0.5;"><i class="fas fa-thumbs-down"></i></button>
                    </div>
                    <div class="text-muted" style="font-size: 0.7rem;">${agFormatTime(msg.created_at)}</div>
                </div>
            </div>
        </div>
    `;
}

async function agSendFeedback(btn, rating, intent, messageId) {
    var container = btn.closest('.ag-feedback-btns');
    if (!container) return;

    try {
        var envId = sessionStorage.getItem('active_environment_id');
        await apiRequest('/agent/feedback', 'POST', {
            message_id: messageId || null,
            session_id: agChatSessionId || '',
            environment_id: envId ? parseInt(envId) : null,
            rating: rating,
            intent: intent || '',
        });
        container.innerHTML = rating > 0
            ? '<span class="text-success" style="font-size:0.7rem;"><i class="fas fa-thumbs-up me-1"></i>Obrigado!</span>'
            : '<span class="text-warning" style="font-size:0.7rem;"><i class="fas fa-thumbs-down me-1"></i>Vamos melhorar</span>';
    } catch (e) {
        container.innerHTML = '<span class="text-muted" style="font-size:0.7rem;">Erro ao enviar</span>';
    }
}

function agSimpleMarkdown(text) {
    if (!text) return '';
    var html = agEscapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h6 class="mt-2 mb-1">$1</h6>');
    html = html.replace(/^## (.+)$/gm, '<h5 class="mt-2 mb-1">$1</h5>');
    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul class="mb-1">$&</ul>');
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    return html;
}

function agIntentColor(intent) {
    var colors = {
        error_analysis: 'danger', pipeline_status: 'info', table_info: 'primary',
        procedure_lookup: 'success', alert_recurrence: 'warning', environment_status: 'secondary',
        knowledge_search: 'info', general: 'secondary'
    };
    return colors[intent] || 'secondary';
}

function agIntentLabel(intent) {
    var labels = {
        error_analysis: 'Erro', pipeline_status: 'Pipeline', table_info: 'Tabela',
        procedure_lookup: 'Procedimento', alert_recurrence: 'Recorrência', environment_status: 'Ambiente',
        knowledge_search: 'KB', general: 'Geral'
    };
    return labels[intent] || intent;
}

function agSectionIcon(type) {
    var icons = {
        memory: 'fa-brain', article: 'fa-book', alert: 'fa-exclamation-triangle',
        pipeline: 'fa-cogs', environment: 'fa-server'
    };
    return icons[type] || 'fa-info-circle';
}

function agFormatTime(isoStr) {
    if (!isoStr) return '';
    try {
        var d = new Date(isoStr);
        return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return '';
    }
}

// =====================================================================
// ABA: CONFIGURAÇÃO LLM (Item 9D)
// =====================================================================

async function agRenderLLM(container) {
    var envId = sessionStorage.getItem('active_environment_id');

    // Carregar providers disponíveis e configs salvas em paralelo
    // Carregar cada API independentemente (uma falha não bloqueia as outras)
    var providers = [];
    var configs = [];
    var status = {};
    try { providers = (await apiRequest('/agent/llm/providers')).providers || []; } catch (e) { console.warn('LLM providers:', e); }
    try { configs = (await apiRequest('/agent/llm/configs?environment_id=' + (envId || 0))).configs || []; } catch (e) { console.warn('LLM configs:', e); }
    // Status com retry (hard refresh pode demorar para o token estar pronto)
    for (let _r = 0; _r < 3; _r++) {
        try { status = await apiRequest('/agent/llm/status?environment_id=' + (envId || 0)); break; } catch (e) {
            if (_r < 2) await new Promise(r => setTimeout(r, 800));
            else console.warn('LLM status indisponível após 3 tentativas:', e);
        }
    }

    // Mapear configs por provider_id
    var configMap = {};
    configs.forEach(function(c) { configMap[c.provider_id] = c; });

    var html = '<div class="row g-3">';

    // Card de status atual
    html += '<div class="col-12">';
    html += '<div class="card mb-3"><div class="card-body py-2 d-flex justify-content-between align-items-center">';
    html += '<div><strong>Modo atual:</strong> ';
    if (status.mode === 'llm') {
        html += '<span class="badge bg-success"><i class="fas fa-brain me-1"></i>' + agEscapeHtml(status.provider || '') + '</span>';
        html += ' <small class="text-muted ms-2">Modelo: ' + agEscapeHtml(status.model || '') + '</small>';
        html += '</div><div class="d-flex gap-2">';
        html += '<button class="btn btn-sm btn-outline-info" onclick="agReloadContext()" title="Recarregar contexto do agente"><i class="fas fa-sync-alt me-1"></i>Recarregar Contexto</button>';
        html += '<button class="btn btn-sm btn-outline-warning" onclick="agDeactivateLLM()"><i class="fas fa-power-off me-1"></i>Desativar LLM</button>';
        html += '</div>';
    } else {
        html += '<span class="badge bg-secondary"><i class="fas fa-cog me-1"></i>Rule-based</span>';
        html += ' <small class="text-muted ms-2">Configure e ative um provider abaixo</small>';
        html += '</div><div>';
        html += '<button class="btn btn-sm btn-outline-info" onclick="agReloadContext()" title="Recarregar contexto do agente"><i class="fas fa-sync-alt me-1"></i>Recarregar Contexto</button>';
        html += '</div>';
    }
    html += '</div></div></div>';

    // Card Base de Conhecimento TDN
    html += '<div class="col-12">';
    html += '<div class="card mb-3"><div class="card-header py-2 d-flex justify-content-between align-items-center">';
    html += '<span><i class="fas fa-book me-2"></i><strong>Base de Conhecimento TDN</strong></span>';
    html += '<button class="btn btn-sm btn-outline-primary" onclick="agLoadTDNStats()" title="Atualizar"><i class="fas fa-sync-alt"></i></button>';
    html += '</div><div class="card-body py-2" id="ag-tdn-stats-body">';
    html += '<div class="text-center text-muted py-2"><i class="fas fa-spinner fa-spin me-1"></i> Carregando...</div>';
    html += '</div></div></div>';

    // Card de configuracao ReAct / Sandbox (9J)
    html += '<div class="col-12">';
    html += '<div class="card mb-3"><div class="card-header py-2 d-flex justify-content-between align-items-center">';
    html += '<span><i class="fas fa-shield-alt me-2"></i><strong>ReAct Agent &amp; Sandbox</strong></span>';
    html += '<button class="btn btn-sm btn-outline-primary" onclick="agLoadSandboxConfig()" title="Recarregar"><i class="fas fa-sync-alt"></i></button>';
    html += '</div><div class="card-body" id="ag-sandbox-config-body">';
    html += '<div class="text-center text-muted py-2"><i class="fas fa-spinner fa-spin me-1"></i> Carregando...</div>';
    html += '</div></div></div>';

    // Carregar token stats
    var tokenStats = {};
    try {
        var statsResp = await apiRequest('/agent/llm/token-stats?environment_id=' + (envId || 0));
        (statsResp.by_provider || []).forEach(function(s) { tokenStats[s.provider] = s; });
    } catch (e) { console.warn('Token stats:', e); }

    // Cards de providers
    providers.forEach(function(p) {
        var cfg = configMap[p.id] || null;
        var hasKey = cfg && cfg.is_active;
        var isActive = status.mode === 'llm' && status.provider === p.id;
        var pStats = tokenStats[p.id] || null;

        var borderClass = isActive ? 'border-success' : (hasKey ? 'border-primary' : '');
        var statusBadge = isActive ? '<span class="badge bg-success">Ativo</span>' :
                          (hasKey ? '<span class="badge bg-primary">Configurado</span>' : '');

        html += '<div class="col-md-6 col-lg-4">';
        html += '<div class="card ' + borderClass + ' h-100">';
        html += '<div class="card-header d-flex justify-content-between align-items-center py-2">';
        html += '<strong>' + agEscapeHtml(p.name) + '</strong>' + statusBadge;
        html += '</div>';
        html += '<div class="card-body py-2">';
        html += '<small class="text-muted d-block mb-2">' + agEscapeHtml(p.description) + '</small>';
        html += '<small class="d-block mb-2">Modelo padrão: <code>' + agEscapeHtml(p.default_model) + '</code></small>';

        // Conta-giro de tokens com custo
        if (pStats && pStats.total_tokens > 0) {
            var callsToday = pStats.calls_today || 0;
            var costUsd = pStats.cost_usd || 0;

            html += '<div class="border rounded p-2 mb-2" style="background: rgba(var(--bs-primary-rgb, 13,110,253), 0.05);">';

            // Linha 1: titulo + chamadas
            html += '<div class="d-flex justify-content-between align-items-center mb-1">';
            html += '<small class="fw-bold"><i class="fas fa-tachometer-alt me-1"></i>Consumo</small>';
            html += '<small class="text-muted">' + callsToday + ' chamada' + (callsToday !== 1 ? 's' : '') + ' hoje</small>';
            html += '</div>';

            // Linha 2: tokens por periodo
            html += '<div class="d-flex gap-3 mb-1">';
            html += '<div class="text-center"><div class="fw-bold text-primary" style="font-size:1.1em;">' + agFormatTokens(pStats.tokens_today) + '</div><small class="text-muted">hoje</small></div>';
            html += '<div class="text-center"><div class="fw-bold" style="font-size:1.1em;">' + agFormatTokens(pStats.tokens_7d) + '</div><small class="text-muted">7 dias</small></div>';
            html += '<div class="text-center"><div class="fw-bold" style="font-size:1.1em;">' + agFormatTokens(pStats.tokens_30d) + '</div><small class="text-muted">30 dias</small></div>';
            html += '</div>';

            // Linha 3: input/output + custo
            html += '<div class="d-flex justify-content-between" style="font-size:0.75em;">';
            html += '<span class="text-muted"><i class="fas fa-arrow-right me-1"></i>In: ' + agFormatTokens(pStats.total_input || 0) + ' | Out: ' + agFormatTokens(pStats.total_output || 0) + '</span>';
            if (costUsd > 0) {
                html += '<span class="text-success fw-bold">~$' + costUsd.toFixed(2) + '</span>';
            }
            html += '</div>';

            html += '</div>';
        }

        // Formulário inline
        html += '<div class="mb-2">';
        if (p.requires_key) {
            html += '<input type="password" class="form-control form-control-sm mb-1" id="ag-llm-key-' + p.id + '" placeholder="API Key" value="">';
        }
        var currentModel = (cfg && cfg.model) || '';
        var modelOptions = (p.models || []);
        var isCustomModel = currentModel && modelOptions.indexOf(currentModel) === -1;
        html += '<select class="form-select form-select-sm mb-1" id="ag-llm-model-' + p.id + '" onchange="agToggleCustomModel(\'' + p.id + '\')">';
        html += '<option value="">Modelo (usar padrão: ' + agEscapeHtml(p.default_model) + ')</option>';
        modelOptions.forEach(function(m) {
            var selected = (m === currentModel) ? ' selected' : '';
            html += '<option value="' + agEscapeHtml(m) + '"' + selected + '>' + agEscapeHtml(m) + '</option>';
        });
        html += '<option value="__custom__"' + (isCustomModel ? ' selected' : '') + '>Outro (digitar)</option>';
        html += '</select>';
        html += '<input type="text" class="form-control form-control-sm mb-1' + (isCustomModel ? '' : ' d-none') + '" id="ag-llm-custom-model-' + p.id + '" placeholder="Digite o nome do modelo" value="' + (isCustomModel ? agEscapeHtml(currentModel) : '') + '">';
        if (p.id === 'ollama') {
            html += '<input type="text" class="form-control form-control-sm mb-1" id="ag-llm-url-' + p.id + '" placeholder="URL (ex: http://localhost:11434)" value="' + agEscapeHtml((cfg && cfg.base_url) || '') + '">';
        }
        html += '</div>';

        // Botões
        html += '<div class="d-flex gap-1">';
        html += '<button class="btn btn-sm btn-outline-primary flex-fill" onclick="agSaveLLMConfig(\'' + p.id + '\')"><i class="fas fa-save me-1"></i>Salvar</button>';
        html += '<button class="btn btn-sm btn-outline-success" onclick="agTestLLM(\'' + p.id + '\')" title="Testar conexão"><i class="fas fa-plug"></i></button>';
        if (hasKey && !isActive) {
            html += '<button class="btn btn-sm btn-success" onclick="agActivateLLM(\'' + p.id + '\')" title="Ativar este provider"><i class="fas fa-play"></i></button>';
        }
        if (cfg) {
            html += '<button class="btn btn-sm btn-outline-danger" onclick="agDeleteLLMConfig(' + cfg.id + ')" title="Remover"><i class="fas fa-trash"></i></button>';
        }
        html += '</div>';

        html += '</div></div></div>';
    });

    html += '</div>';
    container.innerHTML = html;

    // Carregar config do sandbox e stats TDN apos renderizar
    agLoadSandboxConfig();
    agLoadTDNStats();
}

// Alterna visibilidade do input de modelo customizado
function agToggleCustomModel(providerId) {
    var select = document.getElementById('ag-llm-model-' + providerId);
    var customInput = document.getElementById('ag-llm-custom-model-' + providerId);
    if (!select || !customInput) return;
    if (select.value === '__custom__') {
        customInput.classList.remove('d-none');
        customInput.focus();
    } else {
        customInput.classList.add('d-none');
        customInput.value = '';
    }
}

// Retorna o modelo selecionado (select ou input customizado)
function agGetSelectedModel(providerId) {
    var select = document.getElementById('ag-llm-model-' + providerId);
    if (!select) return '';
    if (select.value === '__custom__') {
        var customInput = document.getElementById('ag-llm-custom-model-' + providerId);
        return customInput ? customInput.value.trim() : '';
    }
    return select.value.trim();
}

async function agSaveLLMConfig(providerId) {
    var envId = sessionStorage.getItem('active_environment_id');
    var keyInput = document.getElementById('ag-llm-key-' + providerId);
    var urlInput = document.getElementById('ag-llm-url-' + providerId);
    var model = agGetSelectedModel(providerId);

    var body = {
        environment_id: envId ? parseInt(envId) : null,
        provider_id: providerId,
        api_key: keyInput ? keyInput.value.trim() : '',
        model: model,
        base_url: urlInput ? urlInput.value.trim() : '',
        is_active: true
    };

    try {
        await apiRequest('/agent/llm/configs', 'POST', body);
        showNotification('Provider ' + providerId + ' salvo!', 'success');
        if (typeof renderLLMSettingsTab === 'function') renderLLMSettingsTab().catch(() => {});
        else agSwitchTab('chat');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function agTestLLM(providerId) {
    var envId = sessionStorage.getItem('active_environment_id');
    var keyInput = document.getElementById('ag-llm-key-' + providerId);
    var urlInput = document.getElementById('ag-llm-url-' + providerId);
    var model = agGetSelectedModel(providerId);

    showNotification('Testando conexão com ' + providerId + '...', 'info');

    try {
        var resp = await apiRequest('/agent/llm/test', 'POST', {
            provider_id: providerId,
            api_key: keyInput ? keyInput.value.trim() : '',
            model: model,
            base_url: urlInput ? urlInput.value.trim() : '',
            environment_id: envId ? parseInt(envId) : null
        });

        if (resp.success) {
            showNotification('Conexão OK: ' + resp.message, 'success');
        } else {
            showNotification('Falha: ' + resp.message, 'error');
        }
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function agActivateLLM(providerId) {
    var envId = sessionStorage.getItem('active_environment_id');
    try {
        var resp = await apiRequest('/agent/llm/activate', 'POST', {
            environment_id: envId ? parseInt(envId) : null,
            provider_id: providerId
        });
        showNotification(resp.message || 'LLM ativado!', 'success');
        if (typeof renderLLMSettingsTab === 'function') renderLLMSettingsTab().catch(() => {});
        else agSwitchTab('chat');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function agDeactivateLLM() {
    var envId = sessionStorage.getItem('active_environment_id');
    try {
        await apiRequest('/agent/llm/deactivate', 'POST', {
            environment_id: envId ? parseInt(envId) : null
        });
        showNotification('LLM desativado. Modo rule-based.', 'info');
        if (typeof renderLLMSettingsTab === 'function') renderLLMSettingsTab().catch(() => {});
        else agSwitchTab('chat');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

async function agReloadContext() {
    try {
        var result = await apiRequest('/agent/context/reload', 'POST', {});
        showNotification(result.message + ' (' + result.chars + ' chars)', 'success');
    } catch (e) {
        showNotification('Erro ao recarregar contexto: ' + e.message, 'error');
    }
}

async function agDeleteLLMConfig(configId) {
    if (!confirm('Remover esta configuração de LLM?')) return;
    try {
        await apiRequest('/agent/llm/configs/' + configId, 'DELETE');
        showNotification('Configuração removida', 'success');
        if (typeof renderLLMSettingsTab === 'function') renderLLMSettingsTab().catch(() => {});
        else agSwitchTab('chat');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}

// =====================================================================
// BASE DE CONHECIMENTO TDN
// =====================================================================

async function agLoadTDNStats() {
    var body = document.getElementById('ag-tdn-stats-body');
    if (!body) return;
    body.innerHTML = '<div class="text-center text-muted py-2"><i class="fas fa-spinner fa-spin me-1"></i> Carregando...</div>';

    try {
        var stats = await apiRequest('/agent/memory/tdn-stats');
        if (!stats || stats.length === 0) {
            body.innerHTML = '<div class="text-muted py-2"><i class="fas fa-info-circle me-1"></i> Base TDN vazia. Use o botao Rebuild para popular.</div>';
            body.innerHTML += '<div class="mt-2"><button class="btn btn-sm btn-primary" onclick="agRebuildTDN()"><i class="fas fa-hammer me-1"></i>Rebuild Base TDN</button></div>';
            return;
        }

        var totalChunks = 0, totalPages = 0, totalPending = 0;
        stats.forEach(function(s) {
            totalChunks += s.total_chunks || 0;
            totalPages += s.total_pages || 0;
            totalPending += s.pending || 0;
        });

        var html = '<div class="row g-2 mb-2">';
        html += '<div class="col-auto"><span class="badge bg-info fs-6"><i class="fas fa-puzzle-piece me-1"></i>' + agFormatTokens(totalChunks) + ' chunks</span></div>';
        html += '<div class="col-auto"><span class="badge bg-secondary fs-6"><i class="fas fa-file-alt me-1"></i>' + agFormatTokens(totalPages) + ' paginas</span></div>';
        html += '<div class="col-auto"><span class="badge bg-' + (totalPending > 0 ? 'warning' : 'success') + ' fs-6">' + (totalPending > 0 ? '<i class="fas fa-clock me-1"></i>' + totalPending + ' pendentes' : '<i class="fas fa-check me-1"></i>Completo') + '</span></div>';
        html += '</div>';

        html += '<div class="table-responsive"><table class="table table-sm table-hover mb-2">';
        html += '<thead><tr><th>Fonte</th><th class="text-end">Paginas</th><th class="text-end">Chunks</th><th class="text-end">Pendentes</th><th>Status</th></tr></thead><tbody>';
        stats.forEach(function(s) {
            var pct = s.total_pages > 0 ? Math.round((s.scraped / s.total_pages) * 100) : 0;
            var statusBadge = s.pending > 0 ? '<span class="badge bg-warning">Em andamento</span>' :
                              s.errors > 0 ? '<span class="badge bg-danger">' + s.errors + ' erros</span>' :
                              '<span class="badge bg-success">OK</span>';
            html += '<tr><td><strong>' + agEscapeHtml(s.source) + '</strong></td>';
            html += '<td class="text-end">' + (s.scraped || 0) + '/' + s.total_pages + ' (' + pct + '%)</td>';
            html += '<td class="text-end">' + agFormatTokens(s.total_chunks || 0) + '</td>';
            html += '<td class="text-end">' + (s.pending || 0) + '</td>';
            html += '<td>' + statusBadge + '</td></tr>';
        });
        html += '</tbody></table></div>';

        html += '<div class="d-flex gap-2">';
        html += '<button class="btn btn-sm btn-outline-primary" onclick="agRebuildTDN()" title="Re-ingerir fontes .md existentes"><i class="fas fa-hammer me-1"></i>Rebuild MD</button>';
        html += '<button class="btn btn-sm btn-outline-secondary" onclick="agLoadTDNStats()"><i class="fas fa-sync-alt me-1"></i>Atualizar</button>';
        html += '</div>';

        body.innerHTML = html;
    } catch (e) {
        body.innerHTML = '<div class="text-danger py-2"><i class="fas fa-exclamation-triangle me-1"></i> Erro ao carregar stats TDN: ' + agEscapeHtml(e.message) + '</div>';
    }
}

async function agRebuildTDN() {
    if (!confirm('Rebuild da base TDN?\n\nIsso vai re-indexar todos os arquivos tdn_*.md no SQLite FTS5.\nPode levar alguns minutos.')) return;

    try {
        showNotification('Rebuild TDN iniciado... aguarde', 'info');
        var result = await apiRequest('/agent/memory/rebuild', 'POST', {});
        showNotification('Rebuild concluido: ' + (result.total_chunks || 0) + ' chunks indexados', 'success');
        setTimeout(function() { agLoadTDNStats(); }, 1000);
    } catch (e) {
        showNotification('Erro no rebuild TDN: ' + e.message, 'error');
    }
}

// =====================================================================
// UTILITÁRIOS
// =====================================================================

function agFormatTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
}

function agEscapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function agTypeBadge(type) {
    var colors = { semantic: 'info', episodic: 'warning', procedural: 'success' };
    var labels = { semantic: 'Semântica', episodic: 'Episódica', procedural: 'Procedural' };
    var color = colors[type] || 'secondary';
    var label = labels[type] || type;
    return '<span class="badge bg-' + color + '">' + label + '</span>';
}

function agStatCard(icon, label, value, color) {
    return `
        <div class="col-md-2 col-sm-4">
            <div class="card text-center">
                <div class="card-body py-2">
                    <i class="fas ${icon} text-${color} mb-1" style="font-size: 1.3rem;"></i>
                    <div class="fw-bold">${value}</div>
                    <small class="text-muted">${label}</small>
                </div>
            </div>
        </div>
    `;
}

function agPagination(total, current, perPage, fnName) {
    var totalPages = Math.ceil(total / perPage);
    if (totalPages <= 1) return '';

    var html = '<nav><ul class="pagination pagination-sm mb-0">';
    for (var p = 1; p <= totalPages && p <= 10; p++) {
        html += '<li class="page-item ' + (p === current ? 'active' : '') + '">';
        html += '<a class="page-link" href="#" onclick="' + fnName + '(' + p + '); return false;">' + p + '</a>';
        html += '</li>';
    }
    html += '</ul></nav>';
    return html;
}


// =====================================================================
// SANDBOX CONFIG (9J)
// =====================================================================

async function agLoadSandboxConfig() {
    var envId = sessionStorage.getItem('active_environment_id');
    var body = document.getElementById('ag-sandbox-config-body');
    if (!body) return;

    try {
        var resp = await apiRequest('/agent/sandbox/config?environment_id=' + (envId || 0));
        var cfg = resp.config || {};
        var disabled = typeof isAdmin === 'function' && !isAdmin() ? 'disabled' : '';

        body.innerHTML = `
            <div class="row g-3">
                <div class="col-md-6">
                    <div class="form-check form-switch mb-2">
                        <input class="form-check-input" type="checkbox" id="ag-react-enabled"
                               ${cfg.react_enabled ? 'checked' : ''} ${disabled}>
                        <label class="form-check-label" for="ag-react-enabled">
                            <strong>ReAct Loop</strong> — modo multi-step para tarefas complexas
                        </label>
                    </div>
                    <div class="form-check form-switch mb-2">
                        <input class="form-check-input" type="checkbox" id="ag-system-tools"
                               ${cfg.system_tools_enabled ? 'checked' : ''} ${disabled}>
                        <label class="form-check-label" for="ag-system-tools">
                            <strong>System Tools</strong> — ler/escrever arquivos, executar comandos
                        </label>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="row g-2">
                        <div class="col-4">
                            <label class="form-label small">Max iteracoes</label>
                            <input type="number" class="form-control form-control-sm" id="ag-max-iter"
                                   value="${cfg.max_iterations || 10}" min="1" max="20" ${disabled}>
                        </div>
                        <div class="col-4">
                            <label class="form-label small">Token budget</label>
                            <input type="number" class="form-control form-control-sm" id="ag-token-budget"
                                   value="${cfg.token_budget || 50000}" min="5000" max="200000" step="5000" ${disabled}>
                        </div>
                        <div class="col-4">
                            <label class="form-label small">Timeout cmd (s)</label>
                            <input type="number" class="form-control form-control-sm" id="ag-cmd-timeout"
                                   value="${cfg.command_timeout || 30}" min="5" max="120" ${disabled}>
                        </div>
                    </div>
                </div>
                ${!disabled ? '<div class="col-12 text-end"><button class="btn btn-sm btn-primary" onclick="agSaveSandboxConfig()"><i class="fas fa-save me-1"></i>Salvar</button></div>' : '<div class="col-12"><small class="text-muted"><i class="fas fa-lock me-1"></i>Apenas administradores podem alterar estas configuracoes.</small></div>'}
            </div>
        `;
    } catch (e) {
        body.innerHTML = '<div class="text-danger small">Erro ao carregar: ' + agEscapeHtml(e.message) + '</div>';
    }
}

async function agSaveSandboxConfig() {
    var envId = sessionStorage.getItem('active_environment_id');
    if (!envId) { alert('Selecione um ambiente primeiro.'); return; }

    var payload = {
        environment_id: parseInt(envId),
        react_enabled: document.getElementById('ag-react-enabled').checked,
        system_tools_enabled: document.getElementById('ag-system-tools').checked,
        max_iterations: parseInt(document.getElementById('ag-max-iter').value) || 10,
        token_budget: parseInt(document.getElementById('ag-token-budget').value) || 50000,
        command_timeout: parseInt(document.getElementById('ag-cmd-timeout').value) || 30,
    };

    try {
        await apiRequest('/agent/sandbox/config', 'PUT', payload);
        showNotification('Configuracao de sandbox salva!', 'success');
    } catch (e) {
        showNotification('Erro: ' + e.message, 'error');
    }
}
