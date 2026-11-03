/* Registrar: muestra el tipo y el cultivo elegidos, calcula en vivo (VPD, EC, total de
   ml) y completa el último riego. El servidor ya dibuja el estado inicial y funciona sin
   esto; acá solo se acompaña lo que se toca. Sirve igual en la página y en la hoja. */
(() => {
  'use strict';
  const fmt = (n, d) => Number(n).toLocaleString('es-AR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const num = t => parseFloat(String(t || '').replace(',', '.'));
  const vpdDe = (t, h) => 0.6108 * Math.exp(17.27 * t / (t + 237.3)) * (1 - h / 100);
  const ETIQUETA = { riego: 'riego', ambiente: 'ambiente', evento: 'evento', nota: 'nota', ec: 'pH/EC', tarea: 'tarea', planta: 'medición' };

  function iniciar(form) {
    if (form.dataset.listo) return;
    form.dataset.listo = '1';
    const datos = JSON.parse((form.parentElement.querySelector('#reg-datos') || document.getElementById('reg-datos')).textContent);
    const $ = sel => form.querySelector(sel);
    const $$ = sel => form.querySelectorAll(sel);
    const cultivoSel = $('[data-cultivo-select]');
    // En una corrección el tipo y el cultivo vienen fijos en campos ocultos.
    const tipo = () => (form.querySelector('input[name="kind"]:checked') || form.querySelector('input[name="kind"][type="hidden"]') || {}).value || 'riego';
    const cultivo = () => cultivoSel.value;
    const delCultivo = () => datos[cultivo()] || {};

    // Un bloque oculto también se deshabilita: no bloquea con sus requeridos ni viaja en el POST.
    function mostrar(el, visible) {
      el.hidden = !visible;
      if (el.tagName === 'FIELDSET') el.disabled = !visible;
      else el.querySelectorAll('input, textarea, select, button').forEach(i => { i.disabled = !visible; });
    }

    function actualizar() {
      const t = tipo();
      $$('[data-kind]').forEach(el => mostrar(el, el.dataset.kind === t));
      $$('[data-cultivo]').forEach(el => mostrar(el, el.dataset.cultivo === cultivo()));
      if ($('[data-hora]')) mostrar($('[data-hora]'), t !== 'tarea');
      const mismo = $('[data-mismo]');
      if (mismo && t === 'riego') {
        mostrar($('[data-stepper]'), mismo.checked);
        $$('.reg-plantas[data-cultivo]').forEach(el => mostrar(el, !mismo.checked && el.dataset.cultivo === cultivo()));
        $$('[data-runoff-bloque]').forEach(el => mostrar(el, $('[data-runoff]').checked && el.dataset.cultivo === cultivo()));
      }
      const guardar = $('[data-guardar]');
      if (guardar) guardar.textContent = 'Guardar ' + (ETIQUETA[t] || '');
      total(); vivoVpd(); vivoEc(); vivoPh();
    }

    function plantasDelCultivo() {
      const bloque = form.querySelector(`.reg-plantas[data-cultivo="${cultivo()}"]`);
      return bloque ? Number(bloque.dataset.plantas) : 0;
    }

    function total() {
      const caja = $('[data-total]');
      if (!caja) return;
      const mismo = $('[data-mismo]').checked;
      let ml = 0;
      if (mismo) ml = (parseInt($('[name="riego-volumen_todas"]').value, 10) || 0) * plantasDelCultivo();
      else form.querySelectorAll(`.reg-plantas[data-cultivo="${cultivo()}"] [data-planta]`).forEach(i => { ml += parseInt(i.value, 10) || 0; });
      caja.textContent = ml ? `total ${ml.toLocaleString('es-AR')} ml` : `${plantasDelCultivo()} plantas`;
    }

    function vivoVpd() {
      const caja = $('[data-vpd]');
      const t = num($('[data-temp]').value), h = num($('[data-hr]').value);
      if (!caja) return;
      if (!(t >= 0) || !(h >= 0) || h > 100) { caja.textContent = ''; return; }
      const v = vpdDe(t, h), r = delCultivo().vpd;
      let estado = '';
      if (r) estado = v < r[0] ? ' · bajo, aire húmedo' : v > r[1] ? ' · alto, aire seco' : ' · en rango';
      caja.textContent = `VPD ${fmt(v, 2)} kPa${estado}${r ? ` (ideal ${fmt(r[0], 1)}–${fmt(r[1], 1)})` : ''}`;
      caja.dataset.estado = !r ? '' : v < r[0] ? 'bajo' : v > r[1] ? 'alto' : 'ideal';
    }

    function vivoEc() {
      $$('[data-ec]').forEach(input => {
        const hint = input.parentElement.querySelector('[data-ec-hint]');
        const x10 = parseInt(input.value, 10);
        hint.textContent = x10 >= 0 ? `= ${(x10 * 10).toLocaleString('es-AR')} µS · ${fmt(x10 / 100, 2)} mS` : '120 = 1200 µS';
      });
    }

    function vivoPh() {
      const r = delCultivo().ph;
      $$('[data-ph]').forEach(input => {
        const hint = input.parentElement.querySelector('[data-ph-hint]');
        const v = num(input.value);
        if (!r) { hint.textContent = ''; return; }
        const fuera = v >= 0 && (v < r[0] || v > r[1]);
        hint.textContent = `${fuera ? '◌ fuera del ideal' : '● ideal'} ${fmt(r[0], 1)}–${fmt(r[1], 1)}`;
        hint.classList.toggle('reg-fuera', fuera);
      });
    }

    function repetir(pk) {
      const u = (datos[pk] || {}).ultimo_riego;
      if (!u) return;
      const vols = Object.values(u.plantas);
      const iguales = vols.length && vols.every(x => x === vols[0]) && vols.length === plantasDelCultivo();
      $('[data-mismo]').checked = iguales;
      if (iguales) $('[name="riego-volumen_todas"]').value = vols[0];
      form.querySelectorAll(`.reg-plantas[data-cultivo="${pk}"] [data-planta]`).forEach(i => { i.value = u.plantas[i.dataset.planta] || ''; });
      $('[name="riego-ph"]').value = u.ph;
      $('[name="riego-ec"]').value = u.ec;
      form.querySelectorAll(`.reg-nutrientes[data-cultivo="${pk}"] [data-nutriente]`).forEach(i => {
        i.value = u.nutrientes[i.dataset.nutriente] || '';
        if (i.value) { const d = i.closest('details'); if (d) d.open = true; }
      });
      const btn = form.querySelector(`[data-repetir="${pk}"]`);
      btn.textContent = 'Listo ✓';
      actualizar();
    }


    // ── Texto libre: "riego 1,5 L con grow 2, pH 6,2" llena el formulario ──
    // Gramática acotada y todo en el navegador: volumen, nutrientes del catálogo (aunque
    // estén mal escritos), pH, EC, temperatura, humedad y nombres de planta. Lo que no
    // entiende queda en las notas. Muestra lo que entendió antes de guardar.
    const norm = s => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    const distancia = (a, b) => {
      const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
      for (let j = 1; j <= b.length; j++) d[0][j] = j;
      for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      return d[a.length][b.length];
    };
    const RELLENO = new Set(['riego', 'regue', 'regué', 'con', 'de', 'y', 'a', 'al', 'el', 'la', 'las', 'los', 'en', 'por', 'hoy', 'agua', 'litro', 'g', 'gr', 'ml', 'l']);

    function catalogo() {
      const c = cultivo();
      const nutrientes = Array.from(form.querySelectorAll(`.reg-nutrientes[data-cultivo="${c}"] [data-nutriente]`)).map(input => ({
        input, nombre: input.closest('label').querySelector('span').textContent.trim(),
      }));
      // Una palabra que aparece en varios nutrientes (la marca, casi siempre) no alcanza para elegir uno.
      const veces = {};
      nutrientes.forEach(n => { n.palabras = [...new Set(norm(n.nombre).split(/[^a-z0-9]+/).filter(p => p.length >= 3))];
        n.palabras.forEach(p => { veces[p] = (veces[p] || 0) + 1; }); });
      nutrientes.forEach(n => { n.propias = n.palabras.filter(p => veces[p] === 1); if (!n.propias.length) n.propias = n.palabras; });
      const plantas = Array.from(form.querySelectorAll(`.reg-plantas[data-cultivo="${c}"] [data-planta]`)).map(input => ({
        input, nombre: input.closest('label').querySelector('span').firstChild.textContent.trim(),
      }));
      return { nutrientes, plantas };
    }

    function interpretar(texto) {
      let t = ' ' + norm(texto).replace(/(\d),(\d)/g, '$1.$2') + ' ';
      const r = { nutrientes: [], plantas: [] };
      const tomar = (re, fn) => { t = t.replace(re, (...m) => { fn(m); return ' '; }); };
      const n = x => parseFloat(x);
      tomar(/\bph\s*[:=]?\s*(\d+(?:\.\d+)?)/, m => { r.ph = n(m[1]); });
      tomar(/\b(?:ec|ce)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ms|us|µs)?/, m => {
        const v = n(m[1]), u = m[2];
        // El campo es el medidor ×10 (140 = 1,4 mS). Se acepta mS (1,4) y µS (1400).
        r.ec = u === 'ms' || v < 10 ? Math.round(v * 100) : u || v >= 1000 ? Math.round(v / 10) : Math.round(v);
      });
      tomar(/\btemp(?:eratura)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:°|º)?c?/, m => { r.temp = n(m[1]); });
      tomar(/(\d+(?:\.\d+)?)\s*(?:°|º|grados)c?/, m => { r.temp = n(m[1]); });
      tomar(/\b(?:hr|humedad|hum)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?/, m => { r.hr = n(m[1]); });
      tomar(/(\d+(?:\.\d+)?)\s*%/, m => { r.hr = n(m[1]); });
      tomar(/(\d+(?:\.\d+)?)\s*(ml|cc|lts?|litros?|l)\b(?!\s*\/)/, m => { r.ml = Math.round(n(m[1]) * (/^(ml|cc)$/.test(m[2]) ? 1 : 1000)); });
      tomar(/\b(c\/u|cada una|cada planta|por planta|c\/planta)\b/, () => { r.porPlanta = true; });
      const cat = catalogo();
      cat.plantas.forEach(p => {
        const nombre = norm(p.nombre).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp('(^|[^a-z0-9])' + nombre + '(?=[^a-z0-9]|$)');
        if (re.test(t)) { r.plantas.push(p); t = t.replace(re, '$1 '); }
      });
      cat.nutrientes.forEach(nu => {
        const palabras = t.split(/\s+/);
        for (let i = 0; i < palabras.length; i++) {
          const w = palabras[i].replace(/[^a-z0-9]/g, '');
          if (w.length < 3 || !nu.propias.some(p => p === w || (p.length >= 4 && w.length >= 4 && distancia(p, w) <= 1))) continue;
          let dosis = null, hasta = i;
          for (let k = i + 1; k <= i + 2 && k < palabras.length; k++) {
            const m = palabras[k].match(/^(\d+(?:\.\d+)?)/);
            if (m) { dosis = n(m[1]); hasta = k; break; }
            if (!nu.palabras.includes(palabras[k].replace(/[^a-z0-9]/g, ''))) break;
          }
          r.nutrientes.push({ ...nu, dosis });
          palabras.splice(i, hasta - i + 1);
          t = ' ' + palabras.join(' ') + ' ';
          break;
        }
      });
      // Lo que sobra, si dice algo, va a las notas.
      const resto = t.split(/[\s,;.]+/).filter(w => w && !RELLENO.has(w) && !/^\d+(\.\d+)?$/.test(w));
      if (resto.join('').replace(/[^a-z]/g, '').length >= 3) {
        // Se toma del texto original para conservar mayúsculas y tildes.
        const original = texto.split(/[\s,;]+/).filter(w => resto.includes(norm(w).replace(/[.;]$/, '')));
        r.nota = original.join(' ');
      }
      r.tipo = r.ml || r.nutrientes.length || r.plantas.length ? 'riego'
        : r.temp != null || r.hr != null ? 'ambiente'
        : r.ph != null || r.ec != null ? 'ec' : null;
      return r;
    }

    const auto = new Map();
    function poner(input, valor) {
      if (!input) return;
      input.value = valor;
      auto.set(input, String(valor));
      const d = input.closest('details'); if (d) d.open = true;
    }
    function aplicarTexto() {
      const caja = $('[data-entendi]'), campo = $('[data-texto]');
      if (!caja || !campo) return;
      // Lo que se completó antes desde el texto (y no se tocó a mano) se vuelve a calcular.
      auto.forEach((v, input) => { if (input.value === v) input.value = ''; });
      auto.clear();
      const r = interpretar(campo.value);
      const chips = [];
      const chip = (texto, input) => chips.push({ texto, input });
      if (r.tipo && r.tipo !== tipo()) {
        const radio = form.querySelector(`input[name="kind"][value="${r.tipo}"]`);
        if (radio) { radio.checked = true; actualizar(); }
      }
      if (tipo() === 'riego') {
        const mismo = $('[data-mismo]'), todas = cultivoPlantas();
        if (r.ml) {
          if (r.plantas.length && r.plantas.length < todas.length) {
            mismo.checked = false; actualizar();
            r.plantas.forEach(p => poner(p.input, r.ml));
            chip(`${fmt(r.ml, 0)} ml a ${r.plantas.map(p => p.nombre).join(', ')}`, r.plantas[0].input);
          } else {
            mismo.checked = true; actualizar();
            const cada = r.porPlanta || r.plantas.length ? r.ml : Math.round(r.ml / Math.max(1, todas.length));
            poner($('[name="riego-volumen_todas"]'), cada);
            chip(`${fmt(cada, 0)} ml c/u${!r.porPlanta && !r.plantas.length && todas.length > 1 ? ` (${fmt(r.ml / 1000, 1)} L en total)` : ''}`, $('[name="riego-volumen_todas"]'));
          }
        }
        r.nutrientes.forEach(nu => {
          if (nu.dosis != null) poner(nu.input, String(nu.dosis).replace('.', ','));
          chip(nu.dosis != null ? `${nu.nombre} ${fmt(nu.dosis, nu.dosis % 1 ? 1 : 0)}` : `${nu.nombre}, ¿cuánto?`, nu.input);
        });
        if (r.ph != null) { poner($('[name="riego-ph"]'), String(r.ph).replace('.', ',')); chip(`pH ${fmt(r.ph, 1)}`, $('[name="riego-ph"]')); }
        if (r.ec != null) { poner($('[name="riego-ec"]'), r.ec); chip(`EC ${r.ec} (×10)`, $('[name="riego-ec"]')); }
        if (r.nota) { poner($('[name="riego-notas"]'), r.nota); chip(`Nota: ${r.nota}`, $('[name="riego-notas"]')); }
      } else if (tipo() === 'ambiente') {
        if (r.temp != null) { poner($('[data-temp]'), String(r.temp).replace('.', ',')); chip(`${fmt(r.temp, 1)}°`, $('[data-temp]')); }
        if (r.hr != null) { poner($('[data-hr]'), String(r.hr).replace('.', ',')); chip(`${fmt(r.hr, 0)} % HR`, $('[data-hr]')); }
        if (r.nota) { poner($('[name="ambiente-notas"]'), r.nota); chip(`Nota: ${r.nota}`, $('[name="ambiente-notas"]')); }
      } else if (tipo() === 'ec') {
        if (r.ph != null) { poner($('[name="ec-ph"]'), String(r.ph).replace('.', ',')); chip(`pH ${fmt(r.ph, 1)}`, $('[name="ec-ph"]')); }
        if (r.ec != null) { poner($('[name="ec-ec"]'), r.ec); chip(`EC ${r.ec} (×10)`, $('[name="ec-ec"]')); }
        if (r.nota) { poner($('[name="ec-notas"]'), r.nota); chip(`Nota: ${r.nota}`, $('[name="ec-notas"]')); }
      }
      caja.replaceChildren();
      if (chips.length) {
        const titulo = document.createElement('span');
        titulo.className = 'mo'; titulo.textContent = 'Entendí';
        caja.append(titulo);
        chips.forEach(c => {
          const b = document.createElement('button');
          b.type = 'button'; b.className = 'chip'; b.textContent = c.texto;
          b.addEventListener('click', () => { if (c.input) { c.input.focus(); c.input.select && c.input.select(); } });
          caja.append(b);
        });
      }
      caja.hidden = !campo.value.trim();
      if (!chips.length && campo.value.trim()) caja.textContent = 'No entendí nada todavía. Probá con "riego 1,5 L, pH 6,2" o "25° 60%".';
      actualizar();
    }
    function cultivoPlantas() { return catalogo().plantas; }
    let espera;
    const campoTexto = $('[data-texto]');
    if (campoTexto) {
      campoTexto.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(aplicarTexto, 250); });
      // Enter no manda el formulario: termina de interpretar.
      campoTexto.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); clearTimeout(espera); aplicarTexto(); } });
    }

    form.addEventListener('change', e => {
      if (e.target.name === 'kind' || e.target === cultivoSel || e.target.matches('[data-mismo], [data-runoff]')) actualizar();
      if (e.target === cultivoSel && campoTexto && campoTexto.value) aplicarTexto();
    });
    form.addEventListener('input', e => {
      if (e.target.matches('[data-temp], [data-hr]')) vivoVpd();
      else if (e.target.matches('[data-ec]')) vivoEc();
      else if (e.target.matches('[data-ph]')) vivoPh();
      else if (e.target.matches('[data-planta], [name="riego-volumen_todas"]')) total();
    });
    form.addEventListener('click', e => {
      const paso = e.target.closest('[data-paso]');
      if (paso) {
        const input = $('[name="riego-volumen_todas"]');
        input.value = Math.max(0, (parseInt(input.value, 10) || 0) + Number(paso.dataset.paso));
        total();
      }
      const rep = e.target.closest('[data-repetir]');
      if (rep) repetir(rep.dataset.repetir);
      const chip = e.target.closest('[data-hora-chip]');
      if (chip) {
        const campo = $('[data-hora-campo]'), abierto = campo.hidden;
        campo.hidden = !abierto;
        chip.setAttribute('aria-expanded', abierto);
        $('[data-hora-modo]').value = abierto ? 'elegida' : 'ahora';
        $('[data-hora-texto]').textContent = abierto ? 'Otra hora' : 'Ahora';
        if (abierto) campo.querySelector('input').focus();
      }
      const corregir = e.target.closest('.reg-corregir');
      if (corregir) {
        e.preventDefault();
        const campo = form.querySelector(`[name="${corregir.dataset.campo}"]`);
        if (campo) { const d = campo.closest('details'); if (d) d.open = true; campo.focus(); campo.select && campo.select(); }
      }
    });
    // Campos dentro de <details> plegados: abrirlos para que el navegador pueda señalar el error.
    form.addEventListener('invalid', e => { const d = e.target.closest('details'); if (d) d.open = true; }, true);
    actualizar();
    const conError = form.querySelector('.has-error input, .has-error textarea, input.has-error');
    if (conError) conError.focus();
  }

  const todos = root => (root || document).querySelectorAll('form[data-reg]').forEach(iniciar);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => todos());
  else todos();
  document.body.addEventListener('htmx:afterSwap', e => todos(e.target));
})();
