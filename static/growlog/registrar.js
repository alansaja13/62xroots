/* Registro diario: ningún envío ocurre antes de confirmar la escritura local. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const form = $('entry-form');
  let store, identity, context, syncing = false, saving = false, draftTimer, editingId = null;
  let csrf = null, retryAt = 0, failures = 0, lastItems = [], formTouched = false, lastSavedId = null;
  const labels = {ambiente: 'Ambiente', evento: 'Observación', ec: 'pH / EC', tarea: 'Tarea', riego: 'Riego'};
  const cookieIdentity = () => {
    const value = document.cookie.split('; ').find(c => c.startsWith('growlog_offline='))?.split('=')[1];
    const match = value?.match(/^(\d+)\.([\w-]{43})$/);
    return match ? {user: match[1], key: match[2]} : null;
  };
  const sessionEvent = () => {try {return localStorage.getItem('62xroots-session-change');} catch (_) {return null;}};
  const current = () => { const active = cookieIdentity(); return !!identity && active?.user === identity.user && active?.key === identity.key; };
  const notice = (text, state = '') => { $('connection').textContent = text; $('connection').className = `notice ${state}`; };
  function lock() {
    clearTimeout(draftTimer);
    identity = context = store = csrf = null;
    lastItems = []; form.reset(); $('queue').replaceChildren(); $('plant-volumes').replaceChildren(); $('nutrient-doses').replaceChildren();
    $('account').textContent = ''; $('pending-count').textContent = '0'; $('workspace').hidden = true; $('locked').hidden = false;
    notice('La bitácora local está bloqueada. Entrá con tu cuenta para recuperar tus pendientes.', 'warning');
  }
  function textNode(tag, text, className) {
    const node = document.createElement(tag); node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function localTime() {
    const date = new Date(); date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
  }
  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, {...options, credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000)});
    let body;
    try { body = await response.json(); } catch (_) { body = null; }
    return {status: response.status, body};
  }
  function options(select, values, chosen) {
    select.replaceChildren(...values.map(([value, label]) => new Option(label, String(value))));
    if (chosen && values.some(([value]) => String(value) === String(chosen))) select.value = chosen;
  }
  function checkboxRow(name, text, draftKey) {
    const label = document.createElement('label'); label.className = 'check-row';
    const input = document.createElement('input');
    Object.assign(input, {type: 'checkbox', name});
    if (draftKey) input.dataset.draftKey = draftKey;
    label.append(input, document.createTextNode(' ' + text));
    return {label, input};
  }
  function showKind() {
    document.querySelectorAll('[data-kind]').forEach(fieldset => {
      fieldset.hidden = fieldset.dataset.kind !== $('kind').value;
      fieldset.disabled = fieldset.hidden;
    });
  }
  function capture() {
    const values = {};
    // Incluye pestañas inactivas para conservar el borrador al alternar entre ellas.
    form.querySelectorAll('input,select,textarea').forEach((input, index) => {
      const key = input.dataset.draftKey || `${input.closest('[data-kind]')?.dataset.kind || 'general'}:${input.name}`;
      values[key] = input.type === 'checkbox' ? input.checked : input.value;
    });
    return {cultivo: $('cultivo').value, kind: $('kind').value, values, editingId};
  }
  function applyDraft(draft) {
    if (!draft) return;
    if (![...$('cultivo').options].some(option => option.value === draft.cultivo)) {
      $('cultivo').add(new Option('Cultivo del borrador · sin acceso actual', draft.cultivo));
    }
    $('cultivo').value = draft.cultivo; $('kind').value = draft.kind; populatePlants();
    form.querySelectorAll('input,select,textarea').forEach((input, index) => {
      const key = input.dataset.draftKey || `${input.closest('[data-kind]')?.dataset.kind || 'general'}:${input.name}`;
      if (!Object.hasOwn(draft.values, key)) return;
      if (input.type === 'checkbox') input.checked = !!draft.values[key];
      else input.value = draft.values[key];
    });
    editingId = draft.editingId || null; formTouched = true; showKind(); updateLinks();
    $('draft-status').textContent = 'Borrador recuperado de este dispositivo.';
  }
  function numberField(label, name, draftKey, opts = {}) {
    const l = textNode('label', label), input = document.createElement('input');
    Object.assign(input, {type: 'number', name, inputMode: 'decimal', step: '0.01', min: '0', max: '14', ...opts});
    input.dataset.draftKey = draftKey; l.append(input); return l;
  }
  function populatePlants() {
    const cultivo = context?.cultivos.find(c => String(c.id) === $('cultivo').value);
    const plantas = cultivo?.plantas || [];
    const rows = plantas.map(planta => {
      const wrap = document.createElement('div'); wrap.className = 'plant-row';
      const label = textNode('label', `${planta.nombre} · ml`), input = document.createElement('input');
      Object.assign(input, {type: 'number', name: `planta-${planta.id}`, min: '1', max: '2147483647', step: '1', inputMode: 'numeric', placeholder: 'Sin riego'});
      input.dataset.planta = String(planta.id); input.dataset.draftKey = `planta:${cultivo.id}:${planta.id}`;
      label.append(input);

      // Runoff por planta: plegado, no molesta a quien no lo usa.
      const details = document.createElement('details');
      details.append(textNode('summary', 'runoff'));
      const {label: runoffLabel} = checkboxRow(`runoff-${planta.id}`, 'Runoff observado', `planta:${cultivo.id}:${planta.id}:runoff`);
      const row2 = document.createElement('div'); row2.className = 'row';
      row2.append(
        numberField('pH runoff', `phrunoff-${planta.id}`, `planta:${cultivo.id}:${planta.id}:phrunoff`),
        numberField('EC runoff', `ecrunoff-${planta.id}`, `planta:${cultivo.id}:${planta.id}:ecrunoff`, {max: '999.99'}),
      );
      const notasLabel = textNode('label', 'Notas de esta planta'), notasInput = document.createElement('textarea');
      Object.assign(notasInput, {name: `notasplanta-${planta.id}`, rows: 2});
      notasInput.dataset.draftKey = `planta:${cultivo.id}:${planta.id}:notas`; notasLabel.append(notasInput);
      details.append(runoffLabel, row2, notasLabel);

      wrap.append(label, details); return wrap;
    });
    $('plant-volumes').replaceChildren(...(rows.length ? rows : [textNode('p', 'Este cultivo no tiene plantas disponibles para registrar un riego.', 'hint')]));

    const eventoRows = plantas.map(planta => checkboxRow(`eventoplanta-${planta.id}`, planta.nombre, cultivo ? `eventoplanta:${cultivo.id}:${planta.id}` : undefined).label);
    $('evento-plantas').replaceChildren(...(eventoRows.length ? eventoRows : [textNode('p', 'Este cultivo no tiene plantas disponibles.', 'hint')]));
    updateLinks();
  }
  function updateLinks() {
    const cultivo = context?.cultivos.find(c => String(c.id) === $('cultivo').value);
    $('history-link').href = cultivo ? `/cultivo/${encodeURIComponent(cultivo.slug)}/` : '/';
    $('classic-link').href = cultivo ? `/cultivo/${encodeURIComponent(cultivo.slug)}/quick/` : '/';
  }
  function renderContext(data, draft) {
    context = data;
    const params = new URLSearchParams(location.search);
    const selected = draft?.cultivo || $('cultivo').value || params.get('cultivo');
    options($('cultivo'), data.cultivos.map(c => [c.id, `${c.nombre}${c.archivado ? ' · archivado' : ''}`]), selected);
    options($('event-type'), data.opciones.eventos, 'otro'); options($('ec-type'), data.opciones.ec, 'solucion');
    options($('task-category'), data.opciones.categorias, 'observacion'); options($('task-priority'), data.opciones.prioridades, 'normal');
    $('nutrient-doses').replaceChildren(...data.nutrientes.map(nutriente => {
      const label = textNode('label', `${nutriente.marca} ${nutriente.nombre} · g/L`.trim()), input = document.createElement('input');
      Object.assign(input, {type: 'number', name: `nutriente-${nutriente.id}`, min: '0.001', max: '999.999', step: '0.001', inputMode: 'decimal', placeholder: 'No aplicado'});
      input.dataset.nutriente = String(nutriente.id); input.dataset.draftKey = `nutriente:${nutriente.id}`;
      label.append(input); return label;
    }));
    // Los botones "+ riego"/"+ evento"/… del cultivo llegan con ?kind= para abrir directo esa pestaña.
    const wantedKind = params.get('kind');
    if (!draft && wantedKind && [...$('kind').options].some(option => option.value === wantedKind)) $('kind').value = wantedKind;
    populatePlants(); $('observado').value = localTime(); showKind();
    if (draft) applyDraft(draft);
    $('account').textContent = data.usuario.nombre; $('workspace').hidden = false; $('locked').hidden = true;
    $('save-entry').disabled = !data.cultivos.length;
    if (!data.cultivos.length) $('form-message').textContent = 'No tenés cultivos con permiso para registrar. Podés crear uno o pedir que te compartan acceso de edición.';
  }
  async function saveDraft() {
    if (!current() || saving) return;
    const activeStore = store, snapshot = capture();
    try {
      await activeStore.put('draft', snapshot);
      if (current() && store === activeStore) $('draft-status').textContent = 'Borrador guardado en este dispositivo.';
    } catch (_) {
      if (current()) $('draft-status').textContent = 'No pudimos guardar el borrador. Conservá esta pantalla abierta y revisá el espacio del dispositivo.';
    }
  }
  async function renderQueue() {
    if (!current()) return;
    const activeStore = store, items = await activeStore.items();
    if (!current() || activeStore !== store) return;
    lastItems = items.sort((a, b) => b.created.localeCompare(a.created));
    if (lastSavedId && items.find(item => item.payload.id === lastSavedId)?.status === 'confirmed' && !formTouched) {
      $('form-message').textContent = 'Registro confirmado en tu bitácora.';
    }
    $('pending-count').textContent = String(items.filter(item => item.status !== 'confirmed').length);
    $('queue').replaceChildren();
    if (!items.length) $('queue').append(textNode('p', 'Todavía no hay registros en este dispositivo.', 'hint'));
    for (const item of lastItems) {
      const article = document.createElement('article'); article.className = 'entry';
      const states = {pending: 'Pendiente de sincronizar', confirmed: 'Confirmado en la bitácora', blocked: 'Necesita revisión · conservado aquí'};
      article.append(textNode('span', states[item.status], `badge ${item.status}`));
      article.append(textNode('h3', `${labels[item.payload.tipo]} · ${item.cultivoNombre}`));
      article.append(textNode('time', new Date(item.payload.observado_en).toLocaleString()));
      const datos = item.payload.datos;
      const summary = item.payload.tipo === 'ambiente' ? `${datos.temperatura_c} °C · ${datos.humedad_relativa}% HR` : item.payload.tipo === 'riego' ? `${datos.plantas.reduce((total, p) => total + p.volumen_ml, 0)} ml · ${datos.plantas.length} plantas` : datos.descripcion || datos.titulo || `pH ${datos.ph || '—'} · EC ${datos.ec || '—'}`;
      article.append(textNode('p', summary));
      if (datos.notas) {
        const detail = document.createElement('details');
        detail.append(textNode('summary', 'Ver notas'), textNode('p', datos.notas)); article.append(detail);
      }
      if (item.error) article.append(textNode('p', item.error));
      const actions = document.createElement('div'); actions.className = 'actions';
      const button = (label, fn) => {const node = textNode('button', label, 'secondary'); node.type = 'button'; node.addEventListener('click', () => fn().catch(showLocalError)); actions.append(node);};
      if (item.status === 'blocked') {
        button('Reintentar', async () => {
          if (!current()) return lock();
          await store.put(`item:${item.payload.id}`, {...item, status: 'pending', error: null});
          await renderQueue(); await sync();
        });
        if (item.httpStatus === 400) button('Corregir', async () => {
          if (!current()) return lock();
          if (formTouched && !confirm('¿Reemplazar el borrador actual por este registro para corregirlo?')) return;
          const cultivo = context.cultivos.find(c => c.id === item.payload.cultivo_id);
          if (!cultivo) { notice('Necesitás recuperar acceso al cultivo para corregir este registro.', 'warning'); return; }
          resetForm(); $('cultivo').value = String(cultivo.id); $('kind').value = item.payload.tipo; populatePlants(); showKind();
          const date = new Date(item.payload.observado_en); date.setMinutes(date.getMinutes() - date.getTimezoneOffset()); $('observado').value = date.toISOString().slice(0,16);
          const fieldset = form.querySelector(`[data-kind="${item.payload.tipo}"]`);
          fieldset.querySelectorAll('input,textarea,select').forEach(input => {
            if (input.dataset.planta) input.value = datos.plantas?.find(p => p.planta_id === Number(input.dataset.planta))?.volumen_ml || '';
            else if (input.dataset.nutriente) input.value = datos.nutrientes?.find(n => n.nutriente_id === Number(input.dataset.nutriente))?.dosis_g_por_litro || '';
            // El desglose por planta y las plantas afectadas ya viajan como listas aparte:
            // el runoff/tag de cada planta no se restaura acá, solo los campos generales.
            else if (input.type === 'checkbox') input.checked = !!datos[input.name];
            else input.value = datos[input.name] ?? '';
          });
          editingId = item.payload.id; formTouched = true;
          $('form-message').textContent = 'Corregí los datos y guardá. Se reemplazará el pendiente rechazado.';
          await saveDraft(); form.scrollIntoView({behavior:'smooth', block:'start'});
        });
      }
      button(item.status === 'confirmed' ? 'Quitar confirmación local' : 'Descartar', async () => {
        if (!current()) return lock();
        if (syncing) { notice('Esperá a que termine la sincronización.', 'warning'); return; }
        if (item.status !== 'confirmed' && !confirm('Este registro se borrará del dispositivo. Si aún no llegó a la bitácora, lo perderás. ¿Descartarlo?')) return;
        await store.remove(`item:${item.payload.id}`); await renderQueue();
      });
      article.append(actions); $('queue').append(article);
    }
    $('export').disabled = !items.some(item => item.status !== 'confirmed');
  }
  function showLocalError() {
    notice('No pudimos guardar o leer los datos locales. No cierres esta pantalla: revisá el espacio y los permisos de almacenamiento del navegador.', 'error');
  }
  function resetForm() {
    const cultivo = $('cultivo').value, kind = $('kind').value;
    form.reset(); $('cultivo').value = cultivo; $('kind').value = kind; $('observado').value = localTime();
    $('task-priority').value = 'normal'; $('task-category').value = 'observacion'; $('event-type').value = 'otro'; $('ec-type').value = 'solucion';
    editingId = null; formTouched = false; showKind(); $('draft-status').textContent = '';
  }
  async function refreshContext() {
    const previousIdentity = JSON.stringify(cookieIdentity()), previousEvent = sessionEvent();
    const response = await fetchJSON('/registrar/contexto/');
    if (response.status !== 200 || !response.body?.usuario) {
      if (response.status === 401) { csrf = null; $('session-link').hidden = false; retryAt = Date.now() + 60000; notice('Sesión vencida. Podés conservar pendientes aquí; iniciá sesión para sincronizarlos.', 'warning'); }
      return false;
    }
    if (previousIdentity !== JSON.stringify(cookieIdentity()) || previousEvent !== sessionEvent()) {lock(); return false;}
    const unlock = response.body.desbloqueo;
    if (!unlock || !/^[\w-]{43}$/.test(unlock.clave)) return false;
    const active = {user:String(response.body.usuario.id), key:unlock.clave};
    if (identity && (active.user !== identity.user || active.key !== identity.key)) { lock(); return false; }
    document.cookie = `growlog_offline=${active.user}.${active.key}; Path=/; SameSite=Lax${unlock.secure ? '; Secure' : ''}${unlock.max_age == null ? '' : `; Max-Age=${unlock.max_age}`}`;
    if (cookieIdentity()?.key !== active.key) throw new Error('No se pudo preparar el desbloqueo local.');
    identity = active; store ||= new RootsOffline.Store(identity);
    $('session-link').hidden = true;
    const snapshot = context && formTouched ? capture() : await store.read('draft');
    csrf = response.body.csrf;
    const {csrf: omitted, desbloqueo: omittedUnlock, ...catalogue} = response.body;
    await store.put('context', catalogue);
    if (!current()) return false;
    renderContext(catalogue, context && formTouched ? capture() : snapshot);
    return true;
  }
  async function sync() {
    if (syncing || saving || !current()) return;
    syncing = true; $('sync').disabled = true;
    const run = async () => {
      if (!await refreshContext() || !current()) return;
      const activeStore = store, account = identity.user;
      notice('Comprobando y sincronizando pendientes…');
      const result = await RootsOffline.drain({
        items: await activeStore.items(), isCurrent: () => current() && store === activeStore,
        save: item => activeStore.put(`item:${item.payload.id}`, item),
        send: payload => fetchJSON('/registrar/sincronizar/', {method: 'POST', headers: {'Content-Type':'application/json', 'X-CSRFToken':csrf, 'X-Registro-Cuenta':account}, body:JSON.stringify(payload)}),
      });
      if (!current() || store !== activeStore) return lock();
      if (result === 'offline') throw new Error('Conexión interrumpida');
      if (result === 'auth') { $('session-link').hidden = false; retryAt = Date.now() + 60000; notice('Tu sesión necesita renovarse. Los pendientes siguen guardados aquí.', 'warning'); return; }
      failures = 0; retryAt = Date.now() + 30000;
      await renderQueue();
      const blocked = lastItems.some(item => item.status === 'blocked');
      notice(blocked ? 'Hay registros que necesitan revisión. No se borró ninguno.' : 'Al día. Cada registro confirmado ya está en tu bitácora.', blocked ? 'warning' : '');
    };
    try {
      if (navigator.locks) await navigator.locks.request('62xroots-sync', {ifAvailable: true}, async lock => {if (lock) await run();});
      else await run(); // El recibo del servidor sigue evitando duplicados entre pestañas.
    } catch (_) {
      failures++; retryAt = Date.now() + Math.min(120000, 15000 * 2 ** Math.min(failures, 3));
      if (current()) notice('Sin confirmación del servidor. Podés seguir registrando; los pendientes se conservan y se reintentan al reconectar.', 'warning');
    } finally { syncing = false; $('sync').disabled = false; }
  }
  form.addEventListener('input', () => {
    if (!current()) return lock();
    formTouched = true; clearTimeout(draftTimer); draftTimer = setTimeout(saveDraft, 250);
  });
  $('kind').addEventListener('change', showKind);
  $('cultivo').addEventListener('change', () => {populatePlants(); formTouched = true; saveDraft();});
  form.addEventListener('submit', async event => {
    event.preventDefault(); clearTimeout(draftTimer);
    if (!current()) return lock();
    if (saving) return;
    const data = Object.fromEntries(new FormData(form)), tipo = data.kind;
    const cultivo = context.cultivos.find(c => c.id === Number(data.cultivo_id));
    if (!cultivo) { $('form-message').textContent = 'Elegí un cultivo con permiso de edición.'; return; }
    delete data.kind; delete data.cultivo_id; const observado = data.observado_en; delete data.observado_en;
    if (tipo === 'ec' && data.ph === '' && data.ec === '') { $('form-message').textContent = 'Ingresá pH o EC, al menos uno.'; return; }
    if (tipo === 'riego') {
      // Agrupa volumen + runoff por planta (mismo id en distintos campos) antes de armar el desglose.
      const porPlanta = {};
      for (const [key, value] of Object.entries(data)) {
        const campo = key.match(/^(planta|runoff|phrunoff|ecrunoff|notasplanta)-(\d+)$/);
        if (!campo) continue;
        delete data[key];
        (porPlanta[campo[2]] ||= {})[campo[1]] = value;
      }
      data.plantas = [];
      for (const [id, campos] of Object.entries(porPlanta)) {
        if (!campos.planta) continue; // vacío = no se regó esta planta
        const fila = {planta_id: Number(id), volumen_ml: Number(campos.planta)};
        if (campos.runoff === 'on') {
          fila.runoff_observado = 'on';
          if (campos.phrunoff) fila.ph_runoff = campos.phrunoff;
          if (campos.ecrunoff) fila.ec_runoff = campos.ecrunoff;
          if (campos.notasplanta) fila.notas = campos.notasplanta;
        }
        data.plantas.push(fila);
      }
      data.nutrientes = [];
      for (const [key, value] of Object.entries(data)) {
        if (key.startsWith('nutriente-')) {if (value !== '') data.nutrientes.push({nutriente_id:Number(key.slice(10)), dosis_g_por_litro:value}); delete data[key];}
      }
      if (!data.plantas.length) { $('form-message').textContent = 'Indicá cuánto recibió al menos una planta.'; return; }
    }
    if (tipo === 'evento') {
      data.plantas_afectadas = [];
      for (const [key, value] of Object.entries(data)) {
        if (key.startsWith('eventoplanta-')) {data.plantas_afectadas.push(Number(key.slice(13))); delete data[key];}
      }
    }
    saving = true; $('save-entry').disabled = true;
    const activeStore = store;
    try {
      const item = {payload:{id:crypto.randomUUID(), cultivo_id:cultivo.id, tipo, observado_en:new Date(observado).toISOString(), datos:data}, status:'pending', cultivoNombre:cultivo.nombre, created:new Date().toISOString()};
      await activeStore.enqueue(item, editingId);
      if (!current() || activeStore !== store) return lock();
      lastSavedId = item.payload.id;
      resetForm(); $('form-message').textContent = 'Guardado en este dispositivo. Esperando confirmación de la bitácora.';
      await renderQueue();
      // Una concesión de persistencia reduce el riesgo de limpieza automática;
      // si no se concede, la interfaz lo informa sin prometer durabilidad absoluta.
      if (navigator.storage?.persist) navigator.storage.persist().then(granted => {
        if (current() && !granted) $('storage-notice').textContent = 'El navegador puede liberar almacenamiento local. Sincronizá o descargá los pendientes antes de borrar datos del sitio.';
      }).catch(() => {});
    } catch (_) {showLocalError();}
    finally {saving = false; $('save-entry').disabled = !context?.cultivos.length;}
    await sync();
  });
  $('sync').addEventListener('click', sync);
  $('clear-draft').addEventListener('click', async () => {
    if (!current() || saving) return;
    if (!confirm('¿Descartar lo escrito en el formulario? Los pendientes guardados no se modifican.')) return;
    clearTimeout(draftTimer);
    try {await store.remove('draft'); resetForm(); $('form-message').textContent = '';}
    catch (_) {showLocalError();}
  });
  $('export').addEventListener('click', async () => {
    if (!current()) return lock();
    const items = (await store.items()).filter(item => item.status !== 'confirmed');
    if (!current()) return lock();
    const url = URL.createObjectURL(new Blob([JSON.stringify({version:1, registros:items}, null, 2)], {type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `bitacora-pendientes-${new Date().toISOString().slice(0,10)}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  window.addEventListener('online', sync);
  window.addEventListener('offline', () => {if (current()) notice('Sin conexión. Tus registros se guardan en este dispositivo.', 'warning');});
  window.addEventListener('storage', () => {if (identity && !current()) lock();});
  document.addEventListener('visibilitychange', () => {
    if (identity && !current()) return lock();
    if (document.hidden && formTouched) saveDraft();
    else if (!document.hidden && Date.now() > retryAt) sync();
  });
  setInterval(() => {
    if (identity && !current()) lock();
    if (!document.hidden && navigator.onLine && Date.now() > retryAt && lastItems.some(item => item.status === 'pending')) sync();
  }, 5000);
  (async () => {
    try {
      if (!crypto.subtle || !window.indexedDB) {notice('Este navegador no permite guardar registros offline de forma segura. Usá un navegador actualizado o el registro clásico.', 'error'); return;}
      if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', {scope:'/', updateViaCache:'none'}).catch(() => {
        $('storage-notice').textContent = 'No pudimos preparar la reapertura offline. Mantené esta pantalla abierta hasta recuperar conexión.';
      });
      identity = cookieIdentity();
      if (identity) {
        store = new RootsOffline.Store(identity);
        const catalogue = await store.read('context');
        if (catalogue && current()) {renderContext(catalogue, await store.read('draft')); await renderQueue(); notice('Listo para registrar en este dispositivo.');}
      }
      if (!context) {
        try { if (!await refreshContext()) {lock(); return;} await renderQueue(); }
        catch (_) {lock(); return;}
      }
      await sync();
    } catch (_) {showLocalError();}
  })();
})();
