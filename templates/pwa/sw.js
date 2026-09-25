// Service worker de 62×ROOTS.
// Privacidad: solo se guarda en Cache Storage la shell pública de Registrar y
// assets estáticos. Las páginas de la cuenta nunca se cachean; los registros
// pendientes viven cifrados en IndexedDB (ver offline-store.js).
// La vista inyecta las URLs con hash de collectstatic y una versión derivada
// de ellas: cada deploy que cambia la shell instala una caché nueva sola.
const VERSION = '{{ version }}';
const SHELL = `62xroots-public-${VERSION}`;
const STATIC = '62xroots-static';
const CDN = '62xroots-cdn';
const ALL_CACHES = [SHELL, STATIC, CDN];
const STATIC_LIMIT = 80;

const OFFLINE_URL = '{{ offline_url }}';
const OFFLINE_ASSETS = {{ offline_assets|safe }};

// URLs con versión fija: se pueden servir desde caché sin revalidar.
const CDN_URLS = [
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/',
  'https://cdn.jsdelivr.net/npm/htmx.org@1.9.12/',
  'https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(SHELL).then(cache => cache.addAll(OFFLINE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k.startsWith('62xroots-') && !ALL_CACHES.includes(k)).map(k => caches.delete(k))
      ))
      .then(() => self.registration.navigationPreload && self.registration.navigationPreload.enable())
      .then(() => clients.claim())
  );
});

// Los estáticos de producción llevan hash en el nombre: sin un límite, cada
// deploy dejaría versiones viejas acumulándose en el dispositivo.
async function trim(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  await Promise.all(keys.slice(0, Math.max(0, keys.length - max)).map(k => cache.delete(k)));
}

function staleWhileRevalidate(e, cacheName, request = e.request) {
  return caches.open(cacheName).then(cache =>
    cache.match(request).then(cached => {
      const fresh = fetch(request).then(async res => {
        if (res.ok) {
          await cache.put(request, res.clone());
          if (cacheName === STATIC) await trim(STATIC, STATIC_LIMIT);
        }
        return res;
      }).catch(() => cached || new Response('', {status: 503}));
      e.waitUntil(fresh.then(() => {}));
      return cached || fresh;
    })
  );
}

function offlinePage() {
  return new Response(
    '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="theme-color" content="#0e120c"><title>Sin conexión · 62×ROOTS</title>' +
    '<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0e120c;color:#ece2c8;font:15px/1.5 system-ui,sans-serif;padding:24px">' +
    '<main style="max-width:360px"><p style="font:600 10px/1 ui-monospace,monospace;letter-spacing:.22em;text-transform:uppercase;color:#8aab68">// sin conexión</p>' +
    '<h1 style="font-size:32px;letter-spacing:-.03em;margin:10px 0">Esta pantalla necesita conexión</h1>' +
    '<p style="color:#94a586">Abrí Registrar una vez con conexión para poder anotar sin señal en este dispositivo.</p>' +
    '<a href="/registrar/" style="display:inline-block;margin-top:12px;padding:12px 22px;border-radius:999px;background:#8aab68;color:#0e120c;font-weight:700;text-decoration:none">Abrir Registrar</a></main></body></html>',
    {status: 503, headers: {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'}}
  );
}

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (!url.protocol.startsWith('http')) return;

  if (CDN_URLS.some(u => e.request.url.startsWith(u))) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
        if (res.ok) {
          const copy = res.clone();
          e.waitUntil(caches.open(CDN).then(c => c.put(e.request, copy)));
        }
        return res;
      }))
    );
    return;
  }

  if (url.origin !== self.location.origin) return;

  // La shell y los assets de Registrar: primero lo guardado, así abre al
  // instante aunque la señal del indoor sea mala; se actualiza en segundo plano.
  if (OFFLINE_ASSETS.includes(url.pathname) && (url.pathname !== OFFLINE_URL || e.request.mode === 'navigate')) {
    e.respondWith(staleWhileRevalidate(e, SHELL, url.pathname === OFFLINE_URL ? OFFLINE_URL : e.request));
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    e.respondWith(staleWhileRevalidate(e, STATIC));
    return;
  }

  // Páginas de la cuenta: siempre red, nunca a Cache Storage.
  if (e.request.mode === 'navigate') {
    e.respondWith((async () => {
      try {
        const preloaded = await e.preloadResponse;
        return preloaded || await fetch(e.request);
      } catch (err) {
        const shell = await caches.match(OFFLINE_URL);
        return shell ? Response.redirect(new URL(OFFLINE_URL, self.location.origin).href, 302) : offlinePage();
      }
    })());
  }
});

self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) {
    data = {title: '62×ROOTS', body: e.data ? e.data.text() : ''};
  }
  e.waitUntil(self.registration.showNotification(data.title || '62×ROOTS', {
    body: data.body || '',
    icon: '/static/growlog/icons/icon-192x192.png',
    badge: '/static/growlog/icons/badge-96x96.png',
    data: {url: data.url || '/'},
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const target = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil(
    clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
      const exact = list.find(c => c.url === target);
      if (exact) return exact.focus();
      // Reutilizar la app abierta en vez de apilar ventanas nuevas.
      const any = list.find(c => 'navigate' in c);
      if (any) return any.navigate(target).then(c => c && c.focus());
      return clients.openWindow(target);
    })
  );
});
