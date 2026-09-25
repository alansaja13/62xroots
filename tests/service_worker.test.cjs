const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const template = fs.readFileSync(path.join(__dirname, '../templates/pwa/sw.js'), 'utf8');
const ASSETS = ['/registrar/', '/static/growlog/verde.css', '/static/growlog/registrar.css', '/static/growlog/offline-store.js', '/static/growlog/registrar.js'];
// Mismo reemplazo que hace growlog.views.pwa.pwa_service_worker.
const source = template
  .replace("{{ version }}", 'v9')
  .replace("{{ offline_url }}", '/registrar/')
  .replace('{{ offline_assets|safe }}', JSON.stringify(ASSETS));

test('el template solo usa las variables que inyecta la vista', () => {
  assert.doesNotMatch(source, /\{\{|\{%|\{#/);
});

function worker({offline = false, shell = false, preload} = {}) {
  const handlers = {};
  const deleted = [], saved = [];
  const shellFor = request => shell && request === '/registrar/' ? new Response('Shell pública sin datos personales') : undefined;
  const context = {
    URL, Response,
    self: {
      location: {origin: 'https://bitacora.test'},
      addEventListener(name, callback) {handlers[name] = callback;},
      skipWaiting: async () => {},
      registration: {navigationPreload: {enable: async () => {}}},
    },
    clients: {claim: async () => {}},
    caches: {
      keys: async () => ['62xroots-shell-v5', '62xroots-public-v8', '62xroots-public-v9', '62xroots-static', '62xroots-cdn-v7', 'otra-app'],
      delete: async name => {deleted.push(name);},
      open: async () => ({
        add: async name => {saved.push(name);},
        addAll: async names => {saved.push(...names);},
        put: async request => {saved.push(typeof request === 'string' ? request : request.url);},
        match: async request => shellFor(request),
        keys: async () => [],
        delete: async () => {},
      }),
      match: async request => shellFor(request),
    },
    fetch: async () => {
      if (offline) throw new TypeError('Sin conexión');
      return new Response('Contenido privado de la cuenta');
    },
  };
  vm.runInNewContext(source, context);
  return {handlers, deleted, saved};
}

function navigate(handlers, url, extra = {}) {
  let promise;
  const waits = [];
  handlers.fetch({
    request: {method: 'GET', mode: 'navigate', url},
    preloadResponse: Promise.resolve(extra.preload),
    respondWith(value) {promise = value;},
    waitUntil(value) {waits.push(value);},
  });
  return {promise, waits};
}

test('instalar solo precarga Registrar público y sus assets locales', async () => {
  const {handlers, saved} = worker();
  let promise;
  handlers.install({waitUntil(value) {promise = value;}});
  await promise;
  assert.equal(saved.includes('/'), false);
  assert.deepEqual(saved, ASSETS);
});

test('activar elimina caches anteriores sin afectar otra app', async () => {
  const {handlers, deleted} = worker();
  let promise;
  handlers.activate({waitUntil(value) {promise = value;}});
  await promise;
  assert.deepEqual(deleted, ['62xroots-shell-v5', '62xroots-public-v8', '62xroots-cdn-v7']);
});

test('navegar online no almacena contenido privado', async () => {
  const {handlers, saved} = worker();
  const {promise} = navigate(handlers, 'https://bitacora.test/invitados/');
  assert.equal(await (await promise).text(), 'Contenido privado de la cuenta');
  assert.deepEqual(saved, []);
});

test('usa la respuesta precargada por el navegador cuando existe', async () => {
  const {handlers} = worker();
  const {promise} = navigate(handlers, 'https://bitacora.test/', {preload: new Response('Precargada')});
  assert.equal(await (await promise).text(), 'Precargada');
});

test('navegar offline sin shell preparada muestra aviso público', async () => {
  const {handlers, saved} = worker({offline: true});
  const {promise} = navigate(handlers, 'https://bitacora.test/cultivo/privado/');
  const response = await promise;
  assert.equal(response.status, 503);
  assert.match(await response.text(), /Abrir Registrar/);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(saved, []);
});

test('navegar offline con shell preparada redirige a Registrar, nunca HTML de la cuenta', async () => {
  const {handlers, saved} = worker({offline: true, shell: true});
  const {promise} = navigate(handlers, 'https://bitacora.test/cultivo/privado/');
  const response = await promise;
  assert.equal(response.status, 302);
  assert.equal(new URL(response.headers.get('Location'), 'https://bitacora.test').pathname, '/registrar/');
  assert.deepEqual(saved, []);
});

test('Registrar abre desde la shell guardada aunque no haya red', async () => {
  const {handlers} = worker({offline: true, shell: true});
  const {promise} = navigate(handlers, 'https://bitacora.test/registrar/?cultivo=3');
  const response = await promise;
  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'Shell pública sin datos personales');
});

test('no intercepta fotos, APIs ni escrituras', () => {
  const {handlers} = worker();
  for (const request of [
    {method: 'GET', mode: 'cors', url: 'https://bitacora.test/media/foto.jpg'},
    {method: 'GET', mode: 'cors', url: 'https://bitacora.test/api/v1/cultivos/'},
    {method: 'GET', mode: 'cors', url: 'https://bitacora.test/registrar/contexto/'},
    {method: 'POST', mode: 'navigate', url: 'https://bitacora.test/cultivo/privado/quick/'},
  ]) {
    handlers.fetch({request, respondWith() {assert.fail('No debe interceptar este recurso');}});
  }
});
