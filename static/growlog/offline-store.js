(function (root) {
  'use strict';
  const enc = new TextEncoder(), dec = new TextDecoder();
  const to64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes)));
  const from64 = value => Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));

  class Store {
    constructor(identity) {
      this.identity = identity;
      this.serial = Promise.resolve();
      this.key = crypto.subtle.importKey('raw', from64(identity.key), 'AES-GCM', false, ['encrypt', 'decrypt']);
      this.db = new Promise((resolve, reject) => {
        const req = indexedDB.open('62xroots-registros-v1', 1);
        req.onupgradeneeded = () => req.result.createObjectStore('registros', {keyPath: 'id'});
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
        req.onblocked = () => reject(new Error('Cerrá otras pestañas de la bitácora y volvé a intentar.'));
      });
    }
    async encrypt(id, value) {
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const name = `${this.identity.user}:${id}`;
      const data = await crypto.subtle.encrypt({name: 'AES-GCM', iv, additionalData: enc.encode(name)}, await this.key, enc.encode(JSON.stringify(value)));
      return {id: name, iv: to64(iv), data: to64(data)};
    }
    async decrypt(row) {
      if (!row) return null;
      const value = await crypto.subtle.decrypt({name: 'AES-GCM', iv: from64(row.iv), additionalData: enc.encode(row.id)}, await this.key, from64(row.data));
      return JSON.parse(dec.decode(value));
    }
    async read(id) {
      const db = await this.db;
      const row = await new Promise((resolve, reject) => {
        const req = db.transaction('registros').objectStore('registros').get(`${this.identity.user}:${id}`);
        req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
      });
      return this.decrypt(row);
    }
    async items() {
      const db = await this.db;
      const rows = await new Promise((resolve, reject) => {
        const req = db.transaction('registros').objectStore('registros').getAll();
        req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
      });
      const prefix = `${this.identity.user}:item:`;
      return Promise.all(rows.filter(row => row.id.startsWith(prefix)).map(row => this.decrypt(row)));
    }
    write(work) {
      const result = this.serial.then(work);
      this.serial = result.catch(() => {});
      return result;
    }
    async transaction(rows, remove = []) {
      const db = await this.db;
      await new Promise((resolve, reject) => {
        const tx = db.transaction('registros', 'readwrite'), os = tx.objectStore('registros');
        rows.forEach(row => os.put(row));
        remove.forEach(id => os.delete(`${this.identity.user}:${id}`));
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || new Error('No se pudo guardar en el dispositivo.'));
      });
    }
    put(id, value) { return this.write(async () => this.transaction([await this.encrypt(id, value)])); }
    remove(id) { return this.write(() => this.transaction([], [id])); }
    enqueue(item, replaces) {
      return this.write(async () => this.transaction([await this.encrypt(`item:${item.payload.id}`, item)], ['draft', ...(replaces ? [`item:${replaces}`] : [])]));
    }
  }

  // Función independiente del DOM/IndexedDB: los estados dependen de una
  // confirmación explícita del servidor, nunca de navigator.onLine.
  async function drain({items, send, save, isCurrent}) {
    for (const item of items.filter(item => item.status === 'pending')) {
      if (!isCurrent()) return 'account';
      let response;
      try { response = await send(item.payload); }
      catch (_) { return 'offline'; }
      if (!isCurrent()) return 'account';
      if (response.status === 401 || response.status === 403 && !response.body?.ok && !response.body?.error) return 'auth';
      if (response.status >= 500 || response.status === 429) return 'offline';
      if (response.status >= 200 && response.status < 300 && response.body?.ok && response.body.data?.id === item.payload.id) {
        await save({...item, status: 'confirmed', confirmation: response.body.data, error: null});
      } else if (response.status >= 400 && response.status < 500) {
        const errors = Object.entries(response.body?.campos || {}).flatMap(([field, values]) => values.map(value => `${field}: ${value.message}`));
        await save({...item, status: 'blocked', httpStatus: response.status, error: [response.body?.error || 'Revisá este registro antes de enviarlo.', ...errors].join(' ')});
      } else {
        // Login HTML, proxy o respuesta incompleta: conservar el UUID y reintentar.
        return 'offline';
      }
    }
    return 'done';
  }
  const api = {Store, drain};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.RootsOffline = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
