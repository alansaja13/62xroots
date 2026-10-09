/* Números y armado de `datos` de Registrar. Sin DOM: se prueba en Node.
   El servidor (registration_forms.py) sigue siendo la fuente de verdad. */
(function (root) {
  'use strict';
  // Mismos límites que registration_forms.py, para avisar antes de encolar
  // y no dejar un pendiente que el servidor va a rechazar.
  const PH = {min: 0, max: 14, decimales: 2};
  // EC: se tipea en ×10 µS/cm como en el medidor (120 = 1200 µS/cm) y viaja en mS/cm (1.20).
  const EC = {min: 0, max: 99999, decimales: 0, divisor: 100};
  const REGLAS = {
    temperatura_c: {min: 0, max: 60, decimales: 2},
    humedad_relativa: {min: 0, max: 100, decimales: 2},
    ph: PH, ec: EC, phrunoff: PH, ecrunoff: EC,
    temp_agua: {min: 0, max: 60, decimales: 1},
    nutriente: {min: 0.001, max: 999.999, decimales: 3},
    planta: {min: 1, max: 2147483647, decimales: 0},
  };
  // Mismo criterio en el atributo pattern de los inputs.
  const PATRON = {decimal: '[0-9]*[.,]?[0-9]+', entero: '[0-9]+'};
  const regla = name => {
    const clave = String(name).replace(/-\d+$/, '');
    return Object.hasOwn(REGLAS, clave) ? REGLAS[clave] : undefined;
  };
  const coma = valor => String(valor).replace('.', ',');

  // "1,8" y "1.8" valen lo mismo. Sin separador de miles: "1.500" es ambiguo
  // y se rechaza en vez de adivinar.
  function leer(valor, reglaCampo) {
    let texto = String(valor ?? '').trim().replace(',', '.');
    if (texto === '') return {valor: ''};
    if (!(reglaCampo.decimales ? /^\d*\.?\d+$/ : /^\d+$/).test(texto)) {
      return {error: reglaCampo.decimales ? 'Escribí solo el número, por ejemplo 1,8.' : 'Escribí un número entero, sin puntos ni comas.'};
    }
    if (texto.startsWith('.')) texto = `0${texto}`;
    if ((texto.split('.')[1] || '').length > reglaCampo.decimales) {
      return {error: `Usá hasta ${reglaCampo.decimales} ${reglaCampo.decimales === 1 ? 'decimal' : 'decimales'}.`};
    }
    if (Number(texto) < reglaCampo.min) return {error: `El mínimo es ${coma(reglaCampo.min)}.`};
    if (Number(texto) > reglaCampo.max) return {error: `El máximo es ${coma(reglaCampo.max)}.`};
    return {valor: texto};
  }

  // `campos` son los valores crudos del formulario (FormData) de la pestaña activa.
  function armarDatos(tipo, campos) {
    const data = {};
    for (const [key, value] of Object.entries(campos)) {
      const reglaCampo = regla(key);
      if (!reglaCampo) { data[key] = value; continue; }
      const leido = leer(value, reglaCampo);
      if (leido.error) return {error: leido.error, campo: key};
      data[key] = reglaCampo.divisor && leido.valor !== '' ? (Number(leido.valor) / reglaCampo.divisor).toFixed(2) : leido.valor;
    }
    if (tipo === 'ec' && data.ph === '' && data.ec === '') return {error: 'Ingresá pH o EC, al menos uno.'};
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
      for (const [id, valores] of Object.entries(porPlanta)) {
        if (!valores.planta) continue; // vacío = no se regó esta planta
        const fila = {planta_id: Number(id), volumen_ml: Number(valores.planta)};
        if (valores.runoff === 'on') {
          fila.runoff_observado = 'on';
          if (valores.phrunoff) fila.ph_runoff = valores.phrunoff;
          if (valores.ecrunoff) fila.ec_runoff = valores.ecrunoff;
          if (valores.notasplanta) fila.notas = valores.notasplanta;
        }
        data.plantas.push(fila);
      }
      data.nutrientes = [];
      for (const [key, value] of Object.entries(data)) {
        if (key.startsWith('nutriente-')) {if (value !== '') data.nutrientes.push({nutriente_id: Number(key.slice(10)), dosis_g_por_litro: value}); delete data[key];}
      }
      if (!data.plantas.length) return {error: 'Indicá cuánto recibió al menos una planta.'};
    }
    if (tipo === 'evento') {
      data.plantas_afectadas = [];
      for (const [key] of Object.entries(data)) {
        if (key.startsWith('eventoplanta-')) {data.plantas_afectadas.push(Number(key.slice(13))); delete data[key];}
      }
    }
    return {datos: data};
  }

  // Valores válidos pero raros: casi siempre un tipeo (coma, unidad, dígito de más).
  // Solo se avisa; quien registra decide.
  const RAROS = {
    temperatura_c: {texto: 'Temperatura', unidad: ' °C', min: 10, max: 40, habitual: 'entre 10 y 40 °C'},
    humedad_relativa: {texto: 'Humedad', unidad: ' %', min: 15, habitual: '15 % o más'},
    ph: {texto: 'pH', unidad: '', min: 4, max: 9, habitual: 'entre 4 y 9'},
    ec: {texto: 'EC', unidad: ' µS/cm', max: 5, factor: 1000, habitual: 'hasta 5000 µS/cm'},
    temp_agua: {texto: 'Temperatura del agua', unidad: ' °C', min: 10, max: 40, habitual: 'entre 10 y 40 °C'},
    dosis: {texto: 'Dosis', unidad: ' g/L', max: 10, habitual: 'hasta 10 g/L'},
  };
  function advertencias(datos, nombres = {}) {
    const avisos = [];
    const revisar = (clave, valor, contexto) => {
      const raro = RAROS[clave];
      if (valor === '' || valor == null) return;
      const n = Number(valor);
      if (n < (raro.min ?? -Infinity) || n > (raro.max ?? Infinity)) {
        avisos.push(`${raro.texto} ${coma(raro.factor ? Math.round(n * raro.factor) : valor)}${raro.unidad}${contexto ? ` (${contexto})` : ''}: lo habitual es ${raro.habitual}.`);
      }
    };
    for (const clave of ['temperatura_c', 'humedad_relativa', 'ph', 'ec', 'temp_agua']) revisar(clave, datos[clave]);
    for (const fila of datos.plantas || []) {
      const planta = nombres.plantas?.[fila.planta_id];
      const contexto = `runoff${planta ? ` de ${planta}` : ''}`;
      revisar('ph', fila.ph_runoff, contexto); revisar('ec', fila.ec_runoff, contexto);
    }
    for (const fila of datos.nutrientes || []) {
      revisar('dosis', fila.dosis_g_por_litro, nombres.nutrientes?.[fila.nutriente_id]);
    }
    return avisos;
  }

  const api = {PATRON, regla, leer, armarDatos, advertencias};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.RootsDatos = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
