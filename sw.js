/**
 * Service Worker do AtuDIC.
 * Cache de assets estáticos para carregamento rápido e modo offline parcial.
 */

const CACHE_NAME = 'atudic-v85';
const STATIC_ASSETS = [
    '/',
    '/static/favicon.ico',
    '/static/css/theme.css',
    '/static/css/app-inline.css',
    '/static/js/integration-core.js',
    '/static/js/api-client.js',
    '/static/js/integration-ui.js',
    '/static/locale/pt-BR.json',
    '/static/locale/en-US.json',
];

// CDN assets que queremos cachear
const CDN_ASSETS = [
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
];

// Instalar: pré-cachear assets estáticos
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn('[SW] Falha ao pré-cachear alguns assets:', err);
            });
        })
    );
    self.skipWaiting();
});

// Ativar: limpar caches antigos
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch: stale-while-revalidate para assets, network-first para API
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Chamadas de API: sempre network-first (não cachear dados dinâmicos)
    if (url.pathname.startsWith('/api/')) {
        return;
    }

    // Assets estáticos e CDN: stale-while-revalidate
    if (
        event.request.destination === 'style' ||
        event.request.destination === 'script' ||
        event.request.destination === 'image' ||
        event.request.destination === 'font' ||
        url.pathname.startsWith('/static/')
    ) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.match(event.request).then((cached) => {
                    const fetchPromise = fetch(event.request)
                        .then((response) => {
                            if (response.ok) {
                                cache.put(event.request, response.clone());
                            }
                            return response;
                        })
                        .catch(() => cached);

                    return cached || fetchPromise;
                });
            })
        );
        return;
    }

    // Navegação (HTML): network-first com fallback para cache
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
    }
});
