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

    form.addEventListener('change', e => {
      if (e.target.name === 'kind' || e.target === cultivoSel || e.target.matches('[data-mismo], [data-runoff]')) actualizar();
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
