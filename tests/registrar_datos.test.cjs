const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {PATRON, regla, leer, armarDatos, advertencias} = require('../static/growlog/registrar-datos.js');

test('coma decimal: 1,8 se guarda como 1.8, no como 18', () => {
  const {datos} = armarDatos('ec', {tipo: 'solucion', ph: '6,2', ec: '1,8', temp_agua: '21,5', notas: ''});
  assert.deepEqual(datos, {tipo: 'solucion', ph: '6.2', ec: '1.8', temp_agua: '21.5', notas: ''});
  assert.deepEqual(armarDatos('ambiente', {temperatura_c: ' 25,4 ', humedad_relativa: '60', notas: ''}).datos,
    {temperatura_c: '25.4', humedad_relativa: '60', notas: ''});
});

test('riego: volumen, runoff por planta y dosis normalizados en el desglose', () => {
  const {datos} = armarDatos('riego', {
    ph: '6,0', ec: '1,4', buscar_runoff: 'on', notas: '',
    'planta-7': '600', 'runoff-7': 'on', 'phrunoff-7': '6,4', 'ecrunoff-7': '2,1', 'notasplanta-7': 'Drenó poco',
    'planta-8': '', 'phrunoff-8': '',
    'nutriente-3': '2,5', 'nutriente-4': '',
  });
  assert.deepEqual(datos, {
    ph: '6.0', ec: '1.4', buscar_runoff: 'on', notas: '',
    plantas: [{planta_id: 7, volumen_ml: 600, runoff_observado: 'on', ph_runoff: '6.4', ec_runoff: '2.1', notas: 'Drenó poco'}],
    nutrientes: [{nutriente_id: 3, dosis_g_por_litro: '2.5'}],
  });
});

test('formato ambiguo o fuera de límites se rechaza en vez de adivinar', () => {
  const casos = [
    ['ec', '1.2.3', /número/], ['ec', '1,234.5', /número/], ['ph', '-1', /número/], ['ph', '6,2abc', /número/],
    ['ec', '1,855', /2 decimales/], ['temp_agua', '21,55', /1 decimal\./], ['nutriente-3', '0,0001', /3 decimales/],
    ['temperatura_c', '254', /máximo es 60/], ['humedad_relativa', '100,5', /máximo es 100/], ['ph', '15', /máximo es 14/],
    ['nutriente-3', '0', /mínimo es 0,001/], ['planta-7', '0', /mínimo es 1/],
    // "1.500" ml en es-AR sería 1500; no se interpreta ni como 1.5 ni como 1500.
    ['planta-7', '1.500', /entero/], ['planta-7', '1,5', /entero/],
  ];
  for (const [campo, valor, mensaje] of casos) {
    assert.match(leer(valor, regla(campo)).error ?? '', mensaje, `${campo}=${valor}`);
  }
  assert.deepEqual(armarDatos('ambiente', {temperatura_c: '25,4,1', humedad_relativa: '60'}), {error: 'Escribí solo el número, por ejemplo 1,8.', campo: 'temperatura_c'});
  assert.deepEqual(leer(',5', regla('ec')), {valor: '0.5'});
  assert.deepEqual(leer('', regla('ec')), {valor: ''});
});

test('el pattern del input acepta lo mismo que leer()', () => {
  const decimal = new RegExp(`^(?:${PATRON.decimal})$`, 'v'), entero = new RegExp(`^(?:${PATRON.entero})$`, 'v');
  for (const valor of ['1,8', '1.8', ',5', '25']) assert.ok(decimal.test(valor), valor);
  for (const valor of ['1.2.3', '1,', '-1', '1e3', '']) assert.ok(!decimal.test(valor), valor);
  assert.ok(entero.test('600') && !entero.test('1.500'));
});

test('campos sin regla numérica pasan tal cual', () => {
  assert.equal(regla('notas'), undefined); assert.equal(regla('constructor'), undefined); assert.equal(regla('runoff-7'), undefined);
  const {datos} = armarDatos('evento', {tipo: 'otro', descripcion: 'Hojas 1,8 cm', 'eventoplanta-7': 'on'});
  assert.deepEqual(datos, {tipo: 'otro', descripcion: 'Hojas 1,8 cm', plantas_afectadas: [7]});
});

test('errores de armado que antes resolvía el submit', () => {
  assert.equal(armarDatos('ec', {tipo: 'solucion', ph: '', ec: ' '}).error, 'Ingresá pH o EC, al menos uno.');
  assert.equal(armarDatos('riego', {'planta-7': '', ph: ''}).error, 'Indicá cuánto recibió al menos una planta.');
});

test('valores raros piden confirmación, los normales no', () => {
  assert.deepEqual(advertencias({tipo: 'solucion', ph: '6.2', ec: '1.8', temp_agua: '21'}), []);
  assert.deepEqual(advertencias({temperatura_c: '25.4', humedad_relativa: '60'}), []);
  assert.deepEqual(advertencias({ph: '6.2', ec: '18'}), ['EC 18 mS/cm: lo habitual es hasta 5 mS/cm.']);
  assert.deepEqual(advertencias({temperatura_c: '45', humedad_relativa: '10'}), [
    'Temperatura 45 °C: lo habitual es entre 10 y 40 °C.', 'Humedad 10 %: lo habitual es 15 % o más.',
  ]);
  assert.deepEqual(advertencias({ph: '3.5'}), ['pH 3,5: lo habitual es entre 4 y 9.']);
  const riego = armarDatos('riego', {'planta-7': '600', 'runoff-7': 'on', 'ecrunoff-7': '7', 'nutriente-3': '25'}).datos;
  assert.deepEqual(advertencias(riego, {plantas: {7: 'Gelato'}, nutrientes: {3: 'Grow A'}}), [
    'EC 7 mS/cm (runoff de Gelato): lo habitual es hasta 5 mS/cm.', 'Dosis 25 g/L (Grow A): lo habitual es hasta 10 g/L.',
  ]);
});

test('Registrar no usa type="number" en ningún campo', () => {
  const html = fs.readFileSync(path.join(__dirname, '../templates/growlog/registrar.html'), 'utf8');
  const js = fs.readFileSync(path.join(__dirname, '../static/growlog/registrar.js'), 'utf8');
  assert.doesNotMatch(html, /type="number"/);
  assert.doesNotMatch(js, /type: 'number'/);
  // Cada input con regla numérica del template usa el mismo pattern que el módulo.
  for (const [, name, attrs] of html.matchAll(/<input name="([\w-]+)"([^>]*)>/g)) {
    if (regla(name)) assert.match(attrs, new RegExp(`pattern="${PATRON.decimal.replace(/[.*+?[\]]/g, '\\$&')}"`), name);
  }
});
