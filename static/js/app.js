/**
 * AtuDIC Supreme — Core Application
 */

const App = {
    currentPage: 'workspace',
    activeWorkspace: null,

    init() {
        this.setupNavigation();
        this.setupTabs();
    },

    setupNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                this.currentPage = item.dataset.page;
            });
        });
    },

    setupTabs() {
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabId = tab.dataset.tab;
                // Update tab buttons
                tab.closest('.tab-bar').querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                // Update tab content
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                const content = document.getElementById('tab-' + tabId);
                if (content) content.classList.add('active');
            });
        });
    },

    setActiveWorkspace(slug) {
        this.activeWorkspace = slug;
        // Notify modules
        if (window.WorkspaceDashboard) WorkspaceDashboard.load(slug);
        if (window.WorkspaceExplorer) WorkspaceExplorer.load(slug);
    },

    showNotification(message, type = 'info') {
        const el = document.createElement('div');
        el.style.cssText = `
            position:fixed;top:1rem;right:1rem;padding:0.75rem 1.25rem;
            border-radius:8px;font-size:0.9rem;z-index:1000;
            animation:fadeIn 0.2s;max-width:400px;
            background:${type === 'error' ? 'var(--danger-dim)' : type === 'success' ? 'var(--success-dim)' : 'var(--primary-dim)'};
            color:${type === 'error' ? 'var(--danger)' : type === 'success' ? 'var(--success)' : 'var(--primary)'};
            border:1px solid currentColor;
        `;
        el.textContent = message;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 4000);
    },
};

// API helper
const API = {
    async get(url) {
        const res = await fetch('/api/workspace' + url);
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    },
    async post(url, data) {
        const res = await fetch('/api/workspace' + url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `API error: ${res.status}`);
        }
        return res.json();
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
