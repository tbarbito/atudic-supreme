/**
 * Workspace Dashboard — Estatisticas e visao geral
 */

const WorkspaceDashboard = {
    async load(slug) {
        const container = document.getElementById('dashboard-content');
        if (!slug) {
            container.innerHTML = '<p class="text-muted">Selecione um workspace no Setup.</p>';
            return;
        }

        container.innerHTML = '<p class="text-muted">Carregando dashboard...</p>';

        try {
            const [stats, summary] = await Promise.all([
                API.get(`/workspaces/${slug}/stats`),
                API.get(`/workspaces/${slug}/explorer/summary`),
            ]);

            container.innerHTML = `
                <h3>Dashboard: ${slug}</h3>

                <div class="stats-grid">
                    ${this._statCard(stats.tabelas, 'Tabelas')}
                    ${this._statCard(stats.campos, 'Campos')}
                    ${this._statCard(stats.indices, 'Indices')}
                    ${this._statCard(stats.gatilhos, 'Gatilhos')}
                    ${this._statCard(stats.fontes, 'Fontes')}
                    ${this._statCard(stats.fonte_chunks, 'Chunks')}
                    ${this._statCard(stats.vinculos, 'Vinculos')}
                    ${this._statCard(stats.menus, 'Menus')}
                </div>

                <div class="card">
                    <h3>Customizacoes</h3>
                    <div class="stats-grid">
                        ${this._statCard(summary.tabelas_custom, 'Tabelas Custom', 'warning')}
                        ${this._statCard(summary.campos_custom, 'Campos Custom', 'warning')}
                        ${this._statCard(summary.gatilhos_custom, 'Gatilhos Custom', 'warning')}
                        ${this._statCard(summary.fontes_custom, 'Fontes Custom', 'warning')}
                        ${this._statCard(summary.parametros_custom, 'Params Custom', 'warning')}
                        ${this._statCard(summary.relacionamentos_custom, 'Relac. Custom', 'warning')}
                    </div>
                </div>
            `;
        } catch (e) {
            container.innerHTML = `<p class="text-danger">Erro: ${e.message}</p>`;
        }
    },

    _statCard(value, label, color = 'primary') {
        const colorVar = color === 'warning' ? 'var(--warning)' : 'var(--primary)';
        return `
            <div class="stat-card">
                <div class="stat-value" style="color:${colorVar}">${(value || 0).toLocaleString()}</div>
                <div class="stat-label">${label}</div>
            </div>
        `;
    },
};
