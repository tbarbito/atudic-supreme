/**
 * Workspace Explorer — Navegacao no dicionario Protheus
 */

const WorkspaceExplorer = {
    currentSlug: null,
    tabelas: [],

    async load(slug) {
        this.currentSlug = slug;
        const container = document.getElementById('explorer-content');
        if (!slug) {
            container.innerHTML = '<p class="text-muted">Selecione um workspace no Setup.</p>';
            return;
        }

        container.innerHTML = `
            <div class="split-layout">
                <div class="split-left">
                    <div class="search-box">
                        <input type="text" id="explorer-search" placeholder="Buscar tabela..."
                               oninput="WorkspaceExplorer.filterTables(this.value)">
                    </div>
                    <ul class="tree-list" id="table-tree">
                        <li class="text-muted" style="padding:0.5rem">Carregando...</li>
                    </ul>
                </div>
                <div class="split-right" id="table-detail">
                    <div class="detail-panel">
                        <p class="text-muted">Selecione uma tabela para ver detalhes.</p>
                    </div>
                </div>
            </div>
        `;

        try {
            this.tabelas = await API.get(`/workspaces/${slug}/explorer/tabelas`);
            this.renderTree(this.tabelas);
        } catch (e) {
            document.getElementById('table-tree').innerHTML =
                `<li class="text-danger" style="padding:0.5rem">Erro: ${e.message}</li>`;
        }
    },

    renderTree(tabelas) {
        const tree = document.getElementById('table-tree');
        if (!tabelas.length) {
            tree.innerHTML = '<li class="text-muted" style="padding:0.5rem">Nenhuma tabela encontrada.</li>';
            return;
        }

        tree.innerHTML = tabelas.map(t => `
            <li class="tree-item" onclick="WorkspaceExplorer.selectTable('${t.codigo}')">
                <code>${t.codigo}</code>
                <span style="flex:1;font-size:0.82rem;color:var(--text-muted)">${(t.nome || '').substring(0, 25)}</span>
                ${t.custom ? '<span class="badge badge-custom">C</span>' : ''}
            </li>
        `).join('');
    },

    filterTables(query) {
        const q = query.toUpperCase();
        const filtered = this.tabelas.filter(t =>
            t.codigo.toUpperCase().includes(q) ||
            (t.nome || '').toUpperCase().includes(q)
        );
        this.renderTree(filtered);
    },

    async selectTable(codigo) {
        // Highlight
        document.querySelectorAll('.tree-item').forEach(i => i.classList.remove('selected'));
        event.currentTarget?.classList.add('selected');

        const detail = document.getElementById('table-detail');
        detail.innerHTML = '<div class="detail-panel"><p class="text-muted">Carregando...</p></div>';

        try {
            const info = await API.get(`/workspaces/${this.currentSlug}/explorer/tabela/${codigo}`);
            detail.innerHTML = this._renderDetail(info);
        } catch (e) {
            detail.innerHTML = `<div class="detail-panel"><p class="text-danger">Erro: ${e.message}</p></div>`;
        }
    },

    _renderDetail(info) {
        const customBadge = info.custom ? '<span class="badge badge-custom">CUSTOM</span>' : '';

        let html = `<div class="detail-panel">
            <h3><code>${info.codigo}</code> — ${info.nome} ${customBadge}</h3>
            <p class="text-muted">Modo: ${info.modo || 'C'}</p>`;

        // Stats
        html += `<div class="stats-grid mt-2">
            ${this._miniStat(info.campos?.length, 'Campos')}
            ${this._miniStat(info.campos_custom?.length, 'Custom')}
            ${this._miniStat(info.indices?.length, 'Indices')}
            ${this._miniStat(info.gatilhos?.length, 'Gatilhos')}
        </div>`;

        // Campos custom
        if (info.campos_custom?.length) {
            html += `<div class="detail-section">
                <h4>Campos Customizados (${info.campos_custom.length})</h4>
                <table class="data-table"><thead><tr>
                    <th>Campo</th><th>Titulo</th><th>Tipo</th><th>Tam</th><th>Obrig</th><th>F3</th>
                </tr></thead><tbody>`;
            for (const c of info.campos_custom) {
                html += `<tr>
                    <td><code>${c.campo}</code></td>
                    <td>${c.titulo || ''}</td>
                    <td>${c.tipo}</td>
                    <td>${c.tamanho},${c.decimal}</td>
                    <td>${c.obrigatorio ? 'Sim' : ''}</td>
                    <td>${c.f3 || ''}</td>
                </tr>`;
            }
            html += '</tbody></table></div>';
        }

        // Indices custom
        if (info.indices_custom?.length) {
            html += `<div class="detail-section">
                <h4>Indices Custom (${info.indices_custom.length})</h4>
                <table class="data-table"><thead><tr>
                    <th>Ordem</th><th>Chave</th><th>Descricao</th>
                </tr></thead><tbody>`;
            for (const i of info.indices_custom) {
                html += `<tr><td>${i.ordem}</td><td><code>${i.chave}</code></td><td>${i.descricao || ''}</td></tr>`;
            }
            html += '</tbody></table></div>';
        }

        // Gatilhos custom
        if (info.gatilhos_custom?.length) {
            html += `<div class="detail-section">
                <h4>Gatilhos Custom (${info.gatilhos_custom.length})</h4>
                <table class="data-table"><thead><tr>
                    <th>Origem</th><th>Destino</th><th>Regra</th>
                </tr></thead><tbody>`;
            for (const g of info.gatilhos_custom) {
                html += `<tr><td><code>${g.campo_origem}</code></td><td><code>${g.campo_destino}</code></td><td>${(g.regra || '').substring(0, 60)}</td></tr>`;
            }
            html += '</tbody></table></div>';
        }

        // Relacionamentos
        const rels = [...(info.relacionamentos_saida || []), ...(info.relacionamentos_entrada || [])];
        if (rels.length) {
            html += `<div class="detail-section">
                <h4>Relacionamentos (${rels.length})</h4>
                <table class="data-table"><thead><tr>
                    <th>Origem</th><th>Destino</th><th>Expressao</th>
                </tr></thead><tbody>`;
            for (const r of rels) {
                const orig = r.tabela_origem || info.codigo;
                const dest = r.tabela_destino || info.codigo;
                html += `<tr><td><code>${orig}</code></td><td><code>${dest}</code></td><td>${r.expr_origem || ''} = ${r.expr_destino || ''}</td></tr>`;
            }
            html += '</tbody></table></div>';
        }

        // All campos (collapsed)
        if (info.campos?.length) {
            html += `<div class="detail-section">
                <h4>Todos os Campos (${info.campos.length})
                    <button class="btn btn-secondary" style="font-size:0.75rem;padding:0.2rem 0.6rem;margin-left:0.5rem"
                            onclick="this.parentElement.nextElementSibling.classList.toggle('hidden')">
                        Expandir/Recolher
                    </button>
                </h4>
                <div class="hidden">
                <table class="data-table"><thead><tr>
                    <th>Campo</th><th>Titulo</th><th>Tipo</th><th>Tam</th><th>Custom</th>
                </tr></thead><tbody>`;
            for (const c of info.campos) {
                const cls = c.custom ? 'style="background:var(--warning-dim)"' : '';
                html += `<tr ${cls}>
                    <td><code>${c.campo}</code></td>
                    <td>${c.titulo || ''}</td>
                    <td>${c.tipo}</td>
                    <td>${c.tamanho},${c.decimal}</td>
                    <td>${c.custom ? 'Sim' : ''}</td>
                </tr>`;
            }
            html += '</tbody></table></div></div>';
        }

        html += '</div>';
        return html;
    },

    _miniStat(value, label) {
        return `<div class="stat-card">
            <div class="stat-value" style="font-size:1.3rem">${value || 0}</div>
            <div class="stat-label">${label}</div>
        </div>`;
    },
};
