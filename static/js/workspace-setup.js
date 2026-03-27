/**
 * Workspace Setup — Criar workspace e ingerir dados
 */

const WorkspaceSetup = {
    init() {
        this.loadWorkspaces();
        // Mode selector
        document.querySelectorAll('.mode-option').forEach(opt => {
            opt.addEventListener('click', () => {
                if (opt.querySelector('input').disabled) return;
                document.querySelectorAll('.mode-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                opt.querySelector('input').checked = true;
            });
        });
    },

    async loadWorkspaces() {
        const container = document.getElementById('workspace-list');
        try {
            const workspaces = await API.get('/workspaces');
            if (!workspaces.length) {
                container.innerHTML = '<p class="text-muted">Nenhum workspace encontrado. Crie um acima.</p>';
                return;
            }
            container.innerHTML = workspaces.map(ws => `
                <div class="ws-item" onclick="WorkspaceSetup.selectWorkspace('${ws.slug}')">
                    <div>
                        <div class="ws-item-name">${ws.slug}</div>
                        <div class="ws-item-stats">
                            ${ws.stats.tabelas || 0} tabelas |
                            ${ws.stats.campos || 0} campos |
                            ${ws.stats.fontes || 0} fontes
                        </div>
                    </div>
                    <span class="badge badge-standard">${ws.stats.vinculos || 0} vinculos</span>
                </div>
            `).join('');
        } catch (e) {
            container.innerHTML = '<p class="text-muted">Erro ao carregar workspaces.</p>';
        }
    },

    selectWorkspace(slug) {
        document.getElementById('workspace-slug').value = slug;
        App.setActiveWorkspace(slug);
        App.showNotification(`Workspace "${slug}" selecionado`, 'success');
        // Switch to dashboard tab
        document.querySelector('.tab[data-tab="dashboard"]').click();
    },

    async ingestCSV() {
        const slug = document.getElementById('workspace-slug').value.trim();
        const csvDir = document.getElementById('csv-dir').value.trim();

        if (!slug) return App.showNotification('Informe o nome do workspace', 'error');
        if (!csvDir) return App.showNotification('Informe o diretorio dos CSVs', 'error');

        const btn = document.getElementById('btn-ingest-csv');
        const progress = document.getElementById('ingest-progress');
        btn.disabled = true;
        progress.style.display = 'block';
        document.getElementById('progress-text').textContent = 'Ingerindo CSVs...';
        document.getElementById('progress-fill').style.width = '30%';

        try {
            const result = await API.post(`/workspaces/${slug}/ingest/csv`, { csv_dir: csvDir });
            document.getElementById('progress-fill').style.width = '100%';
            document.getElementById('progress-text').textContent =
                `Concluido! ${JSON.stringify(result.stats)}`;
            App.showNotification('Ingestao CSV concluida!', 'success');
            this.loadWorkspaces();
            App.setActiveWorkspace(slug);
        } catch (e) {
            document.getElementById('progress-text').textContent = `Erro: ${e.message}`;
            App.showNotification(e.message, 'error');
        } finally {
            btn.disabled = false;
        }
    },

    async ingestFontes() {
        const slug = document.getElementById('workspace-slug').value.trim();
        const fontesDir = document.getElementById('fontes-dir').value.trim();
        const mapaModulos = document.getElementById('mapa-modulos').value.trim();

        if (!slug) return App.showNotification('Informe o nome do workspace', 'error');
        if (!fontesDir) return App.showNotification('Informe o diretorio dos fontes', 'error');

        const btn = document.getElementById('btn-ingest-fontes');
        const progress = document.getElementById('ingest-progress');
        btn.disabled = true;
        progress.style.display = 'block';
        document.getElementById('progress-text').textContent = 'Parseando fontes ADVPL/TLPP...';
        document.getElementById('progress-fill').style.width = '20%';

        try {
            const data = { fontes_dir: fontesDir };
            if (mapaModulos) data.mapa_modulos = mapaModulos;
            const result = await API.post(`/workspaces/${slug}/ingest/fontes`, data);
            document.getElementById('progress-fill').style.width = '100%';
            document.getElementById('progress-text').textContent =
                `Concluido! ${result.stats.fontes} fontes, ${result.stats.chunks} chunks, ${result.stats.operacoes_escrita} ops escrita`;
            App.showNotification('Parse de fontes concluido!', 'success');
            this.loadWorkspaces();
        } catch (e) {
            document.getElementById('progress-text').textContent = `Erro: ${e.message}`;
            App.showNotification(e.message, 'error');
        } finally {
            btn.disabled = false;
        }
    },
};

document.addEventListener('DOMContentLoaded', () => WorkspaceSetup.init());
