// Service worker de 62×ROOTS: solo notificaciones push. No guarda páginas ni
// assets; al activarse borra las cachés de la versión con Registrar offline.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('62xroots-')).map(k => caches.delete(k))))
      .then(() => clients.claim())
  );
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
