# Fase 1 · El uso diario (guía para implementar)

> Escrita para retomar en una sesión nueva sin perder contexto. Plan general: [PLAN-fases.md](PLAN-fases.md). Problemas de partida: [BRIEF-claude-design.md](BRIEF-claude-design.md).
> Diseño de referencia: `C:\Users\Alan\Documents\Alan\Cultivan2\62xroots-handoff.zip`, carpeta `62xroots/project/`: `y-sys.jsx` (tokens y componentes), `y-screens1.jsx` (`YHoy`, `YCultivo`, `YReg`, `YReg2`, `YPlantas`), `y-screens2.jsx` (`YPlanta`, `YTareas`, `YEstados`), `y-desk.jsx` (compu). Ignorar las otras direcciones y los templates Django del zip.

## Lo que ya está (no rehacer)
- **Fase 0, commit `33e6100`:** `static/growlog/suelo.css` (tokens y componentes `card pill chip btn seg fila ck tog vital vacio aviso toast`), barra inferior y lateral, "Cultivo ▾" con chips de secciones, pantalla Más, login, errores y tema claro/oscuro.
- **Mapa de VPD, commit `50358eb`:** `services/vpd.py` + `templates/growlog/vpd.html`. Es la base de "Aire" (fase 2).
- **Bugs, commit `5c18ad7`.** La suite está verde: 230 tests.

## Reglas
- Commits chicos por sub-bloque, deployables. No hacer push sin pedirlo. No agregar línea de coautor (está en memoria).
- Copy: voseo, frases cortas, sin guiones largos, sin `//` ni `§`.
- Solo tokens nuevos de `suelo.css`, texto de 12 px como mínimo, objetivos táctiles de 44 px.
- Cada sub-bloque cierra con tests nuevos, la suite completa y una revisión en el navegador a 375 px y 1280 px.
  - Para revisar sin login: renderizar con el test client a `static/_tmpcheck/` y abrirlo con `preview_start django`. Hay scripts de ejemplo en el scratchpad de la sesión anterior; si no están, se rehacen en 20 líneas.
  - Borrar `static/_tmpcheck` al terminar.
- Actualizar `CLAUDE.md` (el de la carpeta de arriba) cuando cambien flujos: Registrar, HTMX, borrado.

## Decisiones tomadas para esta fase
Se pueden discutir, pero arrancamos con estas:
1. **Núcleo:** una capa por registro, con el color del tipo (riego `--w`, ambiente `--m`, evento `--e`, nota `--n`) y alto fijo por tipo. Lo que se lee es la lista de al lado; la barra es un acento.
2. **Tareas** sigue en Más en el celular y en la barra lateral en la compu.
3. **Deshacer:**
   - **Al crear:** un aviso "Guardado · Deshacer" que hace un POST a `/registro/<tipo>/<pk>/deshacer/`. Ese endpoint borra el registro solo si lo creó el mismo usuario hace menos de 30 s.
   - **Al borrar:** borrado lógico con el campo `eliminado_en` (null) en `Riego`, `MedicionAmbiente`, `MedicionEC`, `Evento` y `Tarea`, más un manager por defecto que los filtra. "Deshacer" lo limpia. El comando `purgar_eliminados` borra de verdad lo que tenga más de 1 día (cron de Railway, como `send_recordatorios`). La API v1 no debe ver los eliminados.
4. **Nota** es un tipo nuevo de `Evento` (`tipo="nota"`). Lleva migración de choices; la descripción es lo único obligatorio.
5. **Fotos:** se generan miniaturas al subir (Pillow ya está instalado): campo `foto_mini` en `MedicionPlanta`, de 480 px y JPEG con calidad 80. Las miniaturas se sirven con `Cache-Control: private, max-age=86400`. El límite sube a 12 MB.

## Orden de trabajo

### 1a · Hoy (`templates/growlog/dashboard.html`, `static/growlog/hoy.css`, `services/hoy.py`)
- **Encabezado:** `mo` con la fecha y `h1` "Hoy". Se van las 3 tarjetas de contadores.
- **"Para revisar · N":** filas `.fila` con `.ck` de 26 px que completa la tarea por HTMX ahí mismo.
  - Al completar aparece un aviso con **Deshacer**, que llama a `tarea_descompletar`.
  - Suma las **alertas de VPD fuera de rango** de la última lectura de cada cultivo activo, usando `services/vpd.estado_de`, con el botón "ver aire" que lleva a `cultivo_vpd`.
  - Los seguimientos vencidos siguen como hoy.
- **Cultivos:** por cada uno, el nombre, el pill de etapa con el día (veg día N / flora día N) y `temp° · HR% · VPD`, con el VPD coloreado por estado. También "sin riego N d" (ámbar desde 3 días) y la frescura "● hace X", o "◌ dato viejo · hace X" en ámbar si pasaron más de 6 h.
  - La barra "Núcleo" horizontal (últimos 14 días) se agrega en 1c.
- **Compartidos e Historial:** quedan como listas simples abajo.
- **Compu:** dos columnas; a la derecha, el mapa de VPD de todos los cultivos queda para la fase 2.
- **Tests:** las alertas de VPD aparecen en Hoy y completar desde Hoy devuelve el fragmento con el aviso de deshacer.

### 1b · Resumen del cultivo (`templates/growlog/cultivo_detail.html`, se reescribe; `views/cultivos.cultivo_detail`)
- **Encabezado:** "Cultivo ▾" (ya existe) y `mo` con la luz ("◐ luz encendida · 18/6").
  - `h1` con el nombre, a 38 px en el celular.
  - Pills: etapa · sin riego N d · N plantas.
- **Selector `seg` Núcleo · Aire · Plantas · Ciclo:** en esta fase Núcleo es esta misma pantalla, Aire lleva a `cultivo_vpd`, Plantas a la pantalla nueva (1e) y Ciclo a `cultivo_etapa`.
  - Reemplaza los chips de secciones en esta pantalla; el resto de las secciones queda en Más.
- **Vitales:** 3 `.vital` (temp, HR, VPD). Si el dato tiene más de 6 h usan `.vital--viejo` y aparece el `aviso` "Última medición de ambiente: hace X" con el pill "medir", que abre Registrar en Ambiente.
  - Tocar VPD sigue llevando al mapa.
- **Pendientes primero:** tareas vencidas y de hoy, más los seguimientos, arriba de la actividad.
- **Actividad:** lista legible, sin tabla: tipo coloreado, dato y hora. Al tocar una fila se abre la ficha del registro (1f).
- **Compu:** grilla `1fr 360px`, con el panel derecho mostrando el registro seleccionado y los botones Editar y Repetir hoy (este último solo para riego, ver 1d).
- **Se va:** el neón animado, las cajas "día/flora" gigantes, la barra de progreso (pasa a Ciclo en la fase 2) y el CSS inline de 290 líneas. El CSS nuevo va a `static/growlog/cultivo.css`.

### 1c · Núcleo (bitácora) (`templates/growlog/timeline.html`, `views/helpers.build_timeline`)
- Columna de capas de 18 px y lista al lado; filtros por tipo con `chip`.
- **Paginación** de a 50 con "Ver más": cambiar `build_timeline(limit)` por `offset/limit`, o un paginador sobre la lista unida.
- **Suma a la bitácora:** cambios de etapa y de fotoperíodo, mediciones de planta (con miniatura) y notas.
- Partial `partials/nucleo_hoy.html` para la barra horizontal de Hoy.
- **Tests:** paginación, tipos nuevos en la bitácora y filtros.

### 1d · Registrar como hoja (`views/registrar.py`, `templates/growlog/registrar.html`, `static/growlog/registrar.js`, `services/registro.py`)
- **La hoja:**
  - El botón `+` de la barra y de la lateral abre la hoja por HTMX: `hx-get` a `/registrar/?hoja=1` devuelve solo el fragmento.
  - Si no hay JS, sigue la página completa.
  - Se cierra con ✕, con Escape o tocando el fondo.
- **Arriba de la hoja:** el cultivo fijado ("🔒 nombre ▾") y chips de tipo: Riego · Ambiente · Evento · Nota · pH/EC · Tarea · Planta. Se va el `<select>`.
- **Hora:** "◷ Ahora" por defecto, sin el campo `observado_en` visible. Si se toca, se despliega el datetime. Si queda en "ahora", el servidor usa `timezone.now()` al guardar.
- **Riego:**
  - Atajo "Repetir riego del dd/mm": el servidor arma los datos del último riego (volumen por planta, pH, EC, nutrientes y dosis) en `services/riegos.ultimo_riego(cultivo)`, y el cliente precarga.
  - "Afinar por planta": interruptor **mismo volumen para todas**, con un stepper ± de 25 ml y el total en vivo. Con el interruptor apagado, los inputs por planta de siempre.
  - pH con el rango ideal de la etapa (`ParametroIdeal.ph_*`) y EC con la conversión en vivo (`= 1400 µS · 140 en medidor`).
  - Nutrientes: chips "los de siempre" (los usados en los últimos 5 riegos) con su dosis, más un "+" que despliega el resto del catálogo.
  - Interruptor "Hubo runoff" que despliega pH y EC por planta. Se elimina `riego-buscar_runoff` como concepto separado y ya no se descartan datos en silencio.
- **Ambiente:** el VPD en vivo con su estado.
- **Planta** (tipo nuevo): elegir la planta y cargar altura, nudos, canopy, aspecto, síntomas y foto (`accept="image/*" capture="environment"`). Usa `MedicionPlantaForm`.
- **Errores y avisos:**
  - Los errores marcan el campo (clase `has-error`) e incluyen el nombre de la planta.
  - Cada valor raro ofrece "Corregir" o "Guardar igual". Se confirma con un token de los avisos vistos, no con un `confirmar=1` global.
- **Al guardar:** la hoja se cierra y aparece el `.toast` "Riego guardado · Ver · Deshacer".
- **Tests:** repetir riego, mismo volumen, runoff con y sin interruptor, hora "ahora" calculada al guardar, nota, medición de planta, deshacer dentro y fuera de los 30 s, y avisos confirmados uno por uno.

### 1e · Plantas (pantalla nueva `/cultivo/<slug>/plantas/`, `views/plantas.py`)
- **Lista:** `seg` Activas · Cosechadas · Descartadas · Archivadas.
  - Tarjetas en 2 columnas: miniatura de la última foto (o un rayado), apodo, altura actual, strain, un sparkline de altura (SVG simple en el servidor o con JS) y "● medida hoy / ◌ hace N d".
- **"Plantas" en la barra** pasa a esta URL; se agrega `"plantas_list": "plantas"` en `SECCIONES_CULTIVO` y `nav_activa`.
- **Ficha** (`planta_detail.html`, se reescribe): altura grande con cm/día, curva de altura con los eventos de la planta marcados, canopy · nudos · aspecto, tira de fotos con lightbox que se desliza, y "Medir a {apodo}" (abre la hoja en Planta).
- **Alta de varias plantas a la vez:** cantidad, strain y apodos editables. Puede quedar en 1e o pasar a la fase 3 si no da el tiempo.
- **Tests:** filtros de la lista, cm/día y miniaturas.

### 1f · Ficha de registro, edición y borrado
- **Ficha:** `/registro/<tipo>/<pk>/` muestra el detalle (en la compu es el panel derecho del Resumen).
- **Editar** usa los mismos fieldsets de la hoja en modo edición. Se eliminan `riego_form.html` y el uso de `crud_form` para registros; la dosis de un nutriente pasa a ser editable.
- **Borrar:** confirmación propia, borrado lógico y aviso con Deshacer. Se eliminan las páginas `crud_delete` de registros.
- Las URLs viejas `*_editar` / `*_eliminar` redirigen a la ficha.
- **Tests:** editar con la misma validación que Registrar, borrado lógico, deshacer, que la API no vea los eliminados y que `purgar_eliminados` borre lo viejo.

## Cómo saber que la fase 1 está lista
- Un riego repetido sale en 3 toques (+ → Repetir → Guardar).
- Ningún flujo diario usa `<select>` para elegir el tipo ni saca al usuario del cultivo.
- Plantas tiene su pantalla y "Medir" vive en la hoja.
- No quedan `riego_form.html` ni `crud_delete` en flujos de registros.
- La suite pasa, y está revisado en celular y compu, en tema claro y oscuro.

## Para pedirle a Claude Design en paralelo
Ficha y edición de un registro en el celular; los tipos Ambiente, Evento, Nota, pH/EC, Tarea y Planta dentro de la hoja; la experiencia del lector en Hoy y Cultivo; las pantallas de Plantas y Registrar en la compu.


## Estado al cierre (2026-11-02)
- **1a–1e hechos**, cada uno en su commit y con push a `main`.
- **1f, hecho en parte:**
  - Ficha de registro en `/registro/<tipo>/<pk>/`, que se abre al tocar cualquier fila de la bitácora, del Resumen o de la ficha de planta.
  - Borrado con confirmación propia y Deshacer de un minuto.
- **Diferencia con la decisión 3:** el Deshacer del borrado no usa borrado lógico (`eliminado_en`). Guarda en la sesión una copia del registro (con sus plantas y nutrientes) y la vuelve a crear con los mismos ids. Así no cambia lo que ven la API, el reporte ni energía. Las mediciones de planta con foto no se pueden deshacer, porque al borrarlas se va el archivo.
- **Edición unificada, hecha:**
  - Corregir cualquier registro usa el mismo formulario que la hoja, con los valores precargados, las mismas validaciones y avisos, y la dosis de nutrientes editable.
  - Las URLs de siempre (`/riego/<pk>/editar/`, `/tarea/<pk>/editar/`…) siguen andando y abren la corrección nueva, que también responde en `/registro/<tipo>/<pk>/editar/`.
  - Se fueron `riego_form.html`, las rutas de agregar o quitar nutrientes sueltos y los formularios viejos de edición.
- **Pendiente de 1c:** la barra "Núcleo" horizontal en Hoy (se suma con el mapa de VPD de Hoy en la fase 2).
