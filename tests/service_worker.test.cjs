const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const views = fs.readFileSync(path.join(__dirname, '../growlog/views.py'), 'utf8');
const source = views.match(/def pwa_service_worker\(request\):\s+js = r?"""([\s\S]*?)"""/)[1];

function worker({offline = false, shell = false} = {}) {
  const handlers = {};
  const deleted = [], saved = [];
  const context = {
    URL, Response,
    self: {
      location: {origin: 'https://bitacora.test'},
      addEventListener(name, callback) {handlers[name] = callback;},
      skipWaiting: async () => {},
    },
    clients: {claim: async () => {}},
    caches: {
      keys: async () => ['62xroots-shell-v5', '62xroots-public-v6', '62xroots-public-v7', 'otra-app'],
      delete: async name => {deleted.push(name);},
      open: async () => ({
        add: async name => {saved.push(name);},
        addAll: async names => {saved.push(...names);},
        put: async name => {saved.push(name);},
        match: async () => undefined,
      }),
      match: async url => shell && url === '/registrar/' ? new Response('Shell pública sin datos personales') : undefined,
    },
    fetch: async () => {
      if (offline) throw new TypeError('Sin conexión');
      return new Response('Contenido privado de la cuenta');
    },
  };
  vm.runInNewContext(source, context);
  return {handlers, deleted, saved};
}

test('instalar solo precarga Registrar público y sus assets locales', async () => {
  const {handlers, saved} = worker();
  let promise;
  handlers.install({waitUntil(value) {promise = value;}});
  await promise;
  assert.equal(saved.includes('/'), false);
  assert.deepEqual(saved, ['/registrar/', '/static/growlog/registrar.css', '/static/growlog/offline-store.js', '/static/growlog/registrar.js']);
});

test('activar elimina caches privados anteriores sin afectar otra app', async () => {
  const {handlers, deleted} = worker();
  let promise;
  handlers.activate({waitUntil(value) {promise = value;}});
  await promise;
  assert.deepEqual(deleted, ['62xroots-shell-v5', '62xroots-public-v6']);
});

test('navegar online no almacena contenido privado', async () => {
  const {handlers, saved} = worker();
  let promise;
  handlers.fetch({request: {method: 'GET', mode: 'navigate', url: 'https://bitacora.test/invitados/'}, respondWith(value) {promise = value;}});
  assert.equal(await (await promise).text(), 'Contenido privado de la cuenta');
  assert.deepEqual(saved, []);
});

test('navegar offline muestra solo aviso público sin reutilizar otra sesión', async () => {
  const {handlers, saved} = worker({offline: true});
  let promise;
  handlers.fetch({request: {method: 'GET', mode: 'navigate', url: 'https://bitacora.test/cultivo/privado/'}, respondWith(value) {promise = value;}});
  const response = await promise;
  assert.equal(response.status, 503);
  assert.match(await response.text(), /Sin conexión/);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(saved, []);
});

test('no intercepta fotos, APIs ni escrituras', () => {
  const {handlers} = worker();
  for (const request of [
    {method: 'GET', mode: 'cors', url: 'https://bitacora.test/media/foto.jpg'},
    {method: 'GET', mode: 'cors', url: 'https://bitacora.test/api/v1/cultivos/'},
    {method: 'POST', mode: 'navigate', url: 'https://bitacora.test/cultivo/privado/quick/'},
  ]) {
    handlers.fetch({request, respondWith() {assert.fail('No debe interceptar este recurso');}});
  }
});

test('reabrir sin conexión devuelve shell pública preparada, nunca HTML de la cuenta', async () => {
  const {handlers, saved} = worker({offline:true, shell:true});
  let promise;
  handlers.fetch({request:{method:'GET',mode:'navigate',url:'https://bitacora.test/'},respondWith(value){promise=value;}});
  const response = await promise;
  assert.equal(response.status,200);
  assert.equal(await response.text(),'Shell pública sin datos personales');
  assert.deepEqual(saved,[]);
});
