/* Registrar: muestra solo los campos del tipo y las plantas del cultivo elegidos.
   El servidor ya renderiza el estado inicial; esto solo acompaña los cambios. */
(() => {
  'use strict';
  const form = document.getElementById('reg-form');
  if (!form) return;
  const kind = document.getElementById('reg-kind');
  const cultivo = document.getElementById('reg-cultivo');
  const observado = document.getElementById('reg-observado');
  const bitacora = document.getElementById('reg-bitacora');

  // Un bloque oculto también se deshabilita: así no bloquea el envío con sus
  // campos requeridos y no viaja en el POST.
  function mostrar(el, visible) {
    el.hidden = !visible;
    if (el.tagName === 'FIELDSET') el.disabled = !visible;
    else el.querySelectorAll('input, textarea, select').forEach(input => { input.disabled = !visible; });
  }

  function actualizar() {
    form.querySelectorAll('[data-kind]').forEach(el => mostrar(el, el.dataset.kind === kind.value));
    form.querySelectorAll('[data-cultivo]').forEach(el => mostrar(el, el.dataset.cultivo === cultivo.value));
    mostrar(observado, kind.value !== 'tarea');
    if (bitacora) bitacora.href = cultivo.selectedOptions[0].dataset.bitacora;
  }

  kind.addEventListener('change', actualizar);
  cultivo.addEventListener('change', actualizar);
  // Runoff, nutrientes y seguimiento viven en <details>: plegados, el navegador
  // no puede señalar el campo inválido.
  form.addEventListener('invalid', event => {
    const details = event.target.closest('details');
    if (details) details.open = true;
  }, true);
  actualizar();
})();
