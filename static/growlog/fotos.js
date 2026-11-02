/* Fotos de una planta: visor (anterior, siguiente, deslizar) y comparar dos fechas con un corte. */
(() => {
  'use strict';
  const fmt = (n, d) => Number(n).toLocaleString('es-AR', { minimumFractionDigits: d, maximumFractionDigits: d });

  // ── Visor ──
  const fotos = Array.from(document.querySelectorAll('[data-visor]'));
  const visor = document.getElementById('visor');
  if (visor && fotos.length) {
    const img = visor.querySelector('[data-visor-img]');
    let actual = 0, xInicio = null;
    const mostrar = i => {
      actual = (i + fotos.length) % fotos.length;
      const f = fotos[actual];
      img.src = f.dataset.src;
      img.alt = 'Foto del ' + f.dataset.fecha;
      visor.querySelector('[data-visor-texto]').textContent = f.dataset.fecha + (f.dataset.altura ? ' · ' + f.dataset.altura : '');
      visor.querySelector('[data-visor-cuenta]').textContent = `${actual + 1} de ${fotos.length}`;
    };
    fotos.forEach((f, i) => f.addEventListener('click', () => { mostrar(i); visor.hidden = false; }));
    visor.addEventListener('click', e => {
      const paso = e.target.closest('[data-visor-paso]');
      if (paso) mostrar(actual + Number(paso.dataset.visorPaso));
      if (e.target.closest('[data-visor-cerrar]')) visor.hidden = true;
    });
    document.addEventListener('keydown', e => {
      if (visor.hidden) return;
      if (e.key === 'Escape') visor.hidden = true;
      if (e.key === 'ArrowRight') mostrar(actual + 1);
      if (e.key === 'ArrowLeft') mostrar(actual - 1);
    });
    visor.addEventListener('touchstart', e => { xInicio = e.touches[0].clientX; }, { passive: true });
    visor.addEventListener('touchend', e => {
      if (xInicio === null) return;
      const dx = e.changedTouches[0].clientX - xInicio;
      if (Math.abs(dx) > 40) mostrar(actual + (dx < 0 ? 1 : -1));
      xInicio = null;
    });
  }

  // ── Línea de tiempo / Comparar ──
  document.querySelectorAll('[data-vista]').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('[data-vista]').forEach(b => { const on = b === btn; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
    document.querySelectorAll('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== btn.dataset.vista; });
  }));

  const caja = document.querySelector('[data-comparar]');
  if (!caja) return;
  const opciones = Array.from(document.querySelectorAll('[data-elegir]'));
  // Arranca comparando la más vieja (A, a la izquierda) con la más nueva (B).
  let elegidas = [opciones.length - 1, 0];

  function pintar() {
    const [ia, ib] = elegidas.slice().sort((x, y) => opciones[x].dataset.iso.localeCompare(opciones[y].dataset.iso) || y - x);
    const a = opciones[ia].dataset, b = opciones[ib].dataset;
    caja.querySelector('[data-img-a]').src = a.src;
    caja.querySelector('[data-img-b]').src = b.src;
    caja.querySelector('[data-rotulo-a]').textContent = `${a.fecha} · día ${a.dia}`;
    caja.querySelector('[data-rotulo-b]').textContent = `${b.fecha} · día ${b.dia}`;
    const partes = [];
    if (a.altura && b.altura) {
      const d = parseFloat(b.altura) - parseFloat(a.altura);
      partes.push(`${d >= 0 ? '+' : ''}${fmt(d, 1)} cm`);
    }
    if (a.nudos && b.nudos) {
      const n = parseInt(b.nudos, 10) - parseInt(a.nudos, 10);
      partes.push(`${n >= 0 ? '+' : ''}${n} nudos`);
    }
    document.querySelector('[data-diff]').textContent = partes.join(' · ');
    const dias = Math.round((Date.parse(b.iso) - Date.parse(a.iso)) / 86400000);
    document.querySelector('[data-dias]').textContent = dias ? `${dias} días` : 'mismo día';
    opciones.forEach((o, i) => o.setAttribute('aria-pressed', elegidas.includes(i)));
  }

  opciones.forEach((o, i) => o.addEventListener('click', () => {
    if (elegidas.includes(i)) return;
    elegidas = [elegidas[1], i];  // se reemplaza la que se eligió hace más
    pintar();
  }));
  document.querySelector('[data-rango]').addEventListener('input', e => {
    caja.style.setProperty('--corte', e.target.value + '%');
  });
  pintar();
})();
