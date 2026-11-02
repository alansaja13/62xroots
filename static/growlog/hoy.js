// Mapa de aire de Hoy (compu): la última lectura de cada cultivo sobre temperatura × HR,
// con la cola de las últimas 24 h. Las zonas siguen el ideal de VPD del cultivo elegido.
(function () {
  'use strict';
  var datos = document.getElementById('hoy-mapa-datos');
  var svg = document.getElementById('hoy-aire-svg');
  if (!datos || !svg) return;
  var C = JSON.parse(datos.textContent);
  var NS = 'http://www.w3.org/2000/svg';
  var W = 340, H = 250;
  var css = function (v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); };
  var fmt = function (n, d) { return Number(n).toLocaleString('es-AR', { minimumFractionDigits: d, maximumFractionDigits: d }); };
  var vpdDe = function (t, h) { return 0.6108 * Math.exp(17.27 * t / (t + 237.3)) * (1 - h / 100); };
  var colorEstado = { ideal: '--ac', alto: '--bad', bajo: '--w' };

  function el(tag, attrs, padre) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    (padre || svg).appendChild(n);
    return n;
  }

  // Ejes: encuadran todas las lecturas y el ideal elegido, con una amplitud mínima.
  var T0, T1, H0, H1;
  function encuadrar(elegido) {
    var ts = [], hs = [];
    C.forEach(function (c) {
      ts.push(c.t); hs.push(c.h);
      c.cola.forEach(function (p) { ts.push(p.t); hs.push(p.h); });
    });
    if (elegido.temp) { ts.push(elegido.temp[0], elegido.temp[1]); hs.push(elegido.hr[0], elegido.hr[1]); }
    T0 = Math.min.apply(null, ts) - 3; T1 = Math.max.apply(null, ts) + 3;
    H0 = Math.min.apply(null, hs) - 8; H1 = Math.max.apply(null, hs) + 8;
    if (T1 - T0 < 12) { var mt = (T0 + T1) / 2; T0 = mt - 6; T1 = mt + 6; }
    if (H1 - H0 < 36) { var mh = (H0 + H1) / 2; H0 = mh - 18; H1 = mh + 18; }
    T0 = Math.floor(T0); T1 = Math.ceil(T1); H0 = Math.max(0, Math.floor(H0)); H1 = Math.min(100, Math.ceil(H1));
  }
  var X = function (t) { return (t - T0) / (T1 - T0) * W; };
  var Y = function (h) { return H - (h - H0) / (H1 - H0) * H; };

  function zona(v, rango) {
    var lo = rango ? rango[0] : 0.8, hi = rango ? rango[1] : 1.2, margen = 0.3;
    if (v < lo - margen) return '--z0';
    if (v < lo) return '--z1';
    if (v <= hi) return '--z2';
    if (v <= hi + margen) return '--z3';
    return '--z4';
  }

  function dibujar(i) {
    var elegido = C[i];
    svg.innerHTML = '';
    encuadrar(elegido);

    var cols = 56, filas = 40, cw = W / cols, ch = H / filas;
    var zonas = el('g', { 'aria-hidden': 'true' });
    for (var a = 0; a < cols; a++) {
      for (var b = 0; b < filas; b++) {
        var t = T0 + (a + 0.5) / cols * (T1 - T0), h = H1 - (b + 0.5) / filas * (H1 - H0);
        el('rect', { x: a * cw, y: b * ch, width: cw + 0.6, height: ch + 0.6, fill: css(zona(vpdDe(t, h), elegido.rango)) }, zonas);
      }
    }
    el('rect', { x: 0, y: 0, width: W, height: H, rx: 12, fill: 'none', stroke: css('--ln') });

    var mu = css('--mu'), ink = css('--ink'), bg = css('--bg');
    for (var tt = Math.ceil(T0 / 2) * 2; tt <= T1; tt += 2) {
      el('text', { x: X(tt), y: H + 16, 'font-size': 10, fill: mu, 'text-anchor': 'middle', 'font-family': 'DM Mono, monospace' }).textContent = tt + '°';
    }
    for (var hh = Math.ceil(H0 / 10) * 10; hh <= H1; hh += 10) {
      el('text', { x: -6, y: Y(hh) + 3, 'font-size': 10, fill: mu, 'text-anchor': 'end', 'font-family': 'DM Mono, monospace' }).textContent = hh + '%';
    }

    C.forEach(function (c, j) {
      var color = css(colorEstado[c.estado] || '--ink');
      var lejos = j !== i && C.length > 1;
      var g = el('g', { opacity: lejos ? 0.75 : 1 });
      if (c.cola.length > 1) {
        el('polyline', { points: c.cola.map(function (p) { return X(p.t).toFixed(1) + ',' + Y(p.h).toFixed(1); }).join(' '),
          fill: 'none', stroke: ink, 'stroke-width': 1, 'stroke-dasharray': '2 3', opacity: 0.45 }, g);
      }
      el('circle', { cx: X(c.t), cy: Y(c.h), r: 8, fill: c.viejo ? bg : color, stroke: c.viejo ? color : bg, 'stroke-width': 3 }, g);
      el('text', { x: X(c.t) + 13, y: Y(c.h) + 4, 'font-size': 11, 'font-weight': 600, fill: ink, stroke: bg, 'stroke-width': 3,
        'paint-order': 'stroke', 'font-family': 'Familjen Grotesk, sans-serif' }).textContent = c.nombre;
    });

    var nota = document.getElementById('hoy-aire-nota');
    if (nota) {
      var r = elegido.rango;
      nota.textContent = 'Zonas de ' + elegido.nombre + (elegido.etapa ? ' (' + elegido.etapa + ')' : '') + ': VPD ' +
        (r ? fmt(r[0], 1) + ' a ' + fmt(r[1], 1) + ' kPa' : 'sin ideal cargado, se usan cortes generales') +
        '. El punto hueco es un dato de hace más de 6 h.';
    }
  }

  var chips = document.querySelectorAll('#hoy-aire-chips .chip');
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { var on = c === chip; c.classList.toggle('on', on); c.setAttribute('aria-pressed', on); });
      dibujar(Number(chip.dataset.i));
    });
  });
  dibujar(0);
})();
