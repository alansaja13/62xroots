# Registrar: carga de datos

Describe cómo se cargan, se ven, se corrigen y se borran los registros de un cultivo: la pantalla Registrar (página y hoja), los siete tipos de registro y sus campos, las validaciones, los avisos de valores inusuales, el deshacer, la ficha de cada registro, la línea de texto libre y las acciones sobre tareas y seguimientos.

Ver también [permisos.md](permisos.md) (quién puede leer y editar), [modelos.md](modelos.md) (campos guardados), [servicios.md](servicios.md) y [api.md](api.md) (la misma carga por JSON).

## Archivos

| Archivo | Contenido |
|---|---|
| `growlog/views/registrar.py` | Vista `registrar`, `registrar_deshacer`, `registro_editar` y los envoltorios de las URLs de corrección antiguas |
| `growlog/views/registros.py` | Ficha de un registro, borrado y restauración |
| `growlog/views/tareas.py` | Completar y reabrir tareas, listas de tareas |
| `growlog/views/eventos.py` | Resolver el seguimiento de un evento |
| `growlog/views/mediciones.py` | Solo cambios de fotoperíodo (la carga de mediciones vive en Registrar) |
| `growlog/services/registro.py` | `guardar_registro`, `actualizar_registro`, `RegistroError`, `TIPOS` |
| `growlog/services/riegos.py` | `guardar_riego`: persistencia atómica del riego, su desglose por planta y sus nutrientes |
| `growlog/services/validacion.py` | `validar_solucion`: rangos de pH y EC |
| `growlog/registration_forms.py` | Formularios de validación de cada tipo (`AmbienteForm`, `ObservacionForm`, `NotaForm`, `RiegoSolucionForm`, `ECForm`, `PendienteForm`, `VolumenForm`, `NutrienteForm`) |
| `growlog/forms.py` | `MedicionPlantaForm` (medición de planta, con foto) |
| `growlog/templatetags/registros.py` | Tag `{% ficha_url %}`: enlace a la ficha desde las filas de la bitácora |
| `templates/growlog/registrar.html` | Página de Registrar |
| `templates/growlog/partials/registrar_hoja.html` | Registrar como hoja sobre la pantalla actual |
| `templates/growlog/partials/registrar_form.html` | Formulario compartido por la página, la hoja y la corrección |
| `templates/growlog/registro_ficha.html` | Ficha de solo lectura |
| `templates/growlog/registro_editar.html` | Corrección de un registro |
| `templates/base.html` | Avisos (toasts) de guardado y borrado, contenedor `#hoja`, apertura de la hoja y atajo Ctrl+K / ⌘K |
| `templates/growlog/partials/tarea_row.html`, `tarea_completar_oob.html`, `tarea_descompletar_oob.html`, `hoy_tarea_hecha.html` | Fragmentos HTMX de tareas |
| `static/growlog/registrar.js`, `static/growlog/registrar.css` | Comportamiento y estilos del formulario |

## Tipos de registro

`services/registro.TIPOS` define siete tipos. Cada uno tiene su modelo, un prefijo de nombre de campo (el nombre del tipo seguido de `-`) y una etiqueta en los chips.

| Tipo | Etiqueta | Modelo | Mensaje al guardar | Usa hora |
|---|---|---|---|---|
| `riego` | Riego | `Riego` (+ `RiegoPlanta`, `NutrienteAplicado`) | Riego guardado | Sí |
| `ambiente` | Ambiente | `MedicionAmbiente` | Ambiente guardado | Sí |
| `evento` | Evento | `Evento` | Evento guardado | Sí |
| `nota` | Nota | `Evento` con `tipo="nota"` | Nota guardada | Sí |
| `ec` | pH/EC | `MedicionEC` | Medición de pH / EC guardada | Sí |
| `tarea` | Tarea | `Tarea` | Tarea guardada | No |
| `planta` | Planta | `MedicionPlanta` | Medición de planta guardada | Solo la fecha |

Los chips aparecen en el orden riego, ambiente, evento, nota, pH/EC, tarea, planta.

### Campos por tipo

Todos los nombres llevan el prefijo del tipo (`ambiente-temperatura_c`). Los valores numéricos aceptan coma o punto decimal.

**Ambiente** (`ambiente-`)

| Campo | Obligatorio | Regla |
|---|---|---|
| `temperatura_c` | Sí | 0 a 60 |
| `humedad_relativa` | Sí | 0 a 100 |
| `notas` | No | hasta 5000 caracteres |

Al guardar, `MedicionAmbiente.save` completa `luz_estado` (luz prendida o apagada) según el fotoperíodo del cultivo en esa hora. Al corregir, `luz_estado` se vuelve a calcular con la hora nueva.

**Riego** (`riego-`)

| Campo | Descripción |
|---|---|
| `mismo` | Casilla "Mismo volumen para todas" |
| `volumen_todas` | ml por planta cuando `mismo` está marcado |
| `planta-<id>` | ml para esa planta; vacío significa que esa planta no se regó |
| `ph` | pH de la solución, 0 a 14 |
| `ec` | EC de la solución, escrita en ×10 µS/cm |
| `nutriente-<id>` | Dosis del nutriente, mayor que 0, hasta 3 decimales, en la unidad del propio nutriente |
| `hubo_runoff` | Casilla "Hubo runoff" (se guarda como `Riego.buscar_runoff`) |
| `runoff-<id>` | Marca el runoff de esa planta aunque no tenga datos |
| `phrunoff-<id>` | pH del drenaje de esa planta, 0 a 14 |
| `ecrunoff-<id>` | EC del drenaje de esa planta, en ×10 µS/cm |
| `notasplanta-<id>` | Notas del runoff de esa planta |
| `notas` | Notas del riego |

Reglas del riego:

- Tiene que recibir volumen al menos una planta activa; si no, falla con "Indicá cuánto recibió al menos una planta" y marca `volumen_todas`.
- Con `mismo` marcado y un valor en `volumen_todas`, el servidor aplica ese valor a todas las plantas activas del cultivo, aunque el navegador no tenga JavaScript.
- Una planta cuenta como "con runoff" si trae `runoff-<id>`, o si `hubo_runoff` está marcado y la planta tiene pH o EC de drenaje. Sin `hubo_runoff` y sin `runoff-<id>`, esos datos de drenaje se ignoran.
- El volumen total del riego (`volumen_total_ml`) es la suma de los volúmenes por planta.
- Un nutriente solo se guarda si su campo tiene valor. Los nutrientes ofrecidos salen de `permissions.nutrientes_para(usuario, cultivo)`: catálogo compartido, propios y los del dueño del cultivo, sin los ocultos.
- Una planta no puede repetirse y todas deben ser del cultivo.
- `guardar_riego` reemplaza el desglose completo por planta; los nutrientes se reemplazan en cada guardado.

**Evento** (`evento-`)

| Campo | Obligatorio | Regla |
|---|---|---|
| `tipo` | Sí | topping, lst, defoliacion, transplante, problema, diagnostico, ajuste_ambiente, cambio_ciclo, otro (el formulario no ofrece `nota`) |
| `descripcion` | Sí | hasta 5000 caracteres |
| `planta-<id>` | No | casilla por planta activa del cultivo (plantas afectadas) |
| `follow_up_fecha` | No | fecha del seguimiento |
| `follow_up_descripcion` | No | qué revisar |
| `follow_up_resuelto` | Solo al corregir | casilla "Ya está resuelto" |

**Nota** (`nota-`): solo `descripcion`, obligatoria, hasta 5000 caracteres. Se guarda como `Evento` de tipo `nota`.

**pH/EC** (`ec-`)

| Campo | Obligatorio | Regla |
|---|---|---|
| `tipo` | Sí | entrada (agua de entrada), solucion (solución nutritiva), runoff (runoff / drenaje), sustrato (sustrato directo) |
| `ph` | Uno de `ph` o `ec` | 0 a 14 |
| `ec` | Uno de `ph` o `ec` | en ×10 µS/cm; el cero vale |
| `temp_agua` | No | 0 a 60, un decimal |
| `notas` | No | hasta 5000 caracteres |

**Tarea** (`tarea-`)

| Campo | Obligatorio | Regla |
|---|---|---|
| `titulo` | Sí | hasta 200 caracteres |
| `categoria` | Sí | riego, training, mantenimiento, compra, observacion |
| `prioridad` | Sí | urgente, normal, baja |
| `fecha_objetivo` | No | fecha |
| `descripcion` | No | hasta 5000 caracteres |
| `completada` | Solo al corregir | casilla "Ya está hecha" |

**Planta** (`planta-`, medición de una planta)

| Campo | Obligatorio | Regla |
|---|---|---|
| `planta_id` | Sí | una planta activa del cultivo |
| `altura_cm` | No | un decimal |
| `nudos_count` | No | entero |
| `ancho_canopy_cm` | No | un decimal |
| `aspecto_general` | Sí | bueno (por defecto), regular, malo |
| `sintomas` | No | texto |
| `foto` | No | imagen de hasta 12 MB; el campo solo existe si `permissions.puede_subir_fotos(usuario)` |

La fecha de la medición es el día local de la hora elegida. La foto se achica al guardar (`services/fotos.py`).

## Página y hoja

Registrar se presenta de dos maneras con el mismo formulario (`partials/registrar_form.html`):

| Modo | Cómo se abre | Plantilla |
|---|---|---|
| Página | `GET /registrar/` | `registrar.html` |
| Hoja | Un enlace con `hx-get` a `/registrar/?hoja=1` y `hx-target="#hoja"` (botón + de la barra móvil, "+ Registrar" del lateral, "Medir a ..." en la planta, "+ Nueva" en tareas) | `partials/registrar_hoja.html` |

La hoja se devuelve solo cuando la petición es GET, viene por HTMX y trae `hoja=1`. Dentro de la página de Registrar los botones + no abren hoja, llevan a la propia página. La hoja se inserta en `<div id="hoja">` de `base.html`, se cierra con el botón ✕, con el fondo (`data-cerrar-hoja`) o con Escape, y al abrirse enfoca el chip de tipo elegido.

El formulario se envía con un POST normal a `/registrar/` (no por HTMX). La hoja guarda la URL de la que venía (cabecera `HX-Current-URL`) en el campo oculto `volver`; tras guardar, la vista redirige a esa URL, siempre que pertenezca a este sitio (`url_has_allowed_host_and_scheme`). Sin `volver`, redirige a `/registrar/?cultivo=<id>&kind=<tipo>`.

Sin JavaScript el formulario funciona igual y muestra todos los bloques juntos.

### Parámetros de entrada (GET y POST)

| Parámetro | Efecto |
|---|---|
| `cultivo` | Id del cultivo elegido. Sin él se propone el último abierto (`cultivo_reciente` de la sesión) y, si no, el primero de la lista |
| `kind` | Tipo preseleccionado. Si falta o no es válido, se usa el último tipo guardado (`registrar_tipo` en la sesión) o `riego` |
| `planta` | Id de planta; preselecciona la planta en el bloque Planta |
| `hoja` | `1` para devolver la hoja (requiere HTMX) |
| `volver` | URL de regreso tras guardar (POST) |

La lista de cultivos del selector incluye los cultivos donde la persona es dueña o editora (`cultivos_visibles(usuario, editar=True)`). Si no hay ninguno se muestra "No tenés cultivos donde registrar" con un enlace para crear uno.

### Estructura del formulario

De arriba hacia abajo: selector de cultivo, línea de texto libre, chips de tipo, selector de hora y el bloque del tipo elegido. El bloque de cada tipo es un `fieldset[data-kind]`; el JavaScript deshabilita los bloques ocultos para que no bloqueen con campos requeridos ni viajen en el POST. Lo mismo se hace con los bloques por cultivo (`[data-cultivo]`): solo el del cultivo elegido queda activo. El botón principal dice "Guardar" más la etiqueta del tipo (por ejemplo "Guardar riego").

Por cultivo, la pantalla precarga (como JSON en `#reg-datos`, armado por `_contexto_cultivos`): el último riego (para "Repetir"), los nutrientes "de siempre" (los de los últimos 5 riegos), el rango de pH ideal y el rango de VPD de la etapa efectiva del cultivo (`ParametroIdeal`).

## Hora del registro

El selector de hora tiene dos modos, guardados en `observado_modo`:

| Modo | Comportamiento |
|---|---|
| `ahora` (por defecto) | La hora se toma en el servidor al guardar, no al abrir la pantalla |
| `elegida` | Se usa `observado_en` (campo `datetime-local`) |

Reglas de `_observado`:

- El tipo `tarea` no usa hora.
- Si `observado_modo` es `ahora`, o `observado_en` viene vacío con el modo presente, se usa `timezone.now()`.
- Una fecha que no se puede leer falla con "Indicá cuándo ocurrió."
- Una hora más de 5 minutos en el futuro falla con "La fecha está en el futuro. Revisá la hora."
- Una fecha sin zona horaria se interpreta en la zona del proyecto.

En la corrección el modo arranca en `elegida` con la hora guardada (para `planta`, el día a las 12:00).

## EC en ×10 y conversión

La EC se escribe como el medidor en escala ×10 µS/cm (`120` = 1200 µS/cm) y se guarda en mS/cm.

- Al guardar, `_numero(..., ec=True)` exige un entero (solo dígitos) y lo divide por 100 con dos decimales: `120` se guarda como `1.20`. Un valor no entero falla con "La EC se escribe como número entero en ×10 µS/cm, por ejemplo 120."
- Aplica a `riego-ec`, `riego-ecrunoff-<id>` y `ec-ec`.
- Al mostrar un valor guardado en el formulario de corrección se multiplica por 100 (`_x10`). La ficha muestra la EC con el filtro `ec` y, aparte, el valor del medidor con el filtro `ec_x10`.
- Debajo del campo, el navegador muestra la conversión en vivo ("= 1.200 µS · 1,20 mS").

## Avisos por valores inusuales

Un valor puede ser válido y raro. Después de guardar los datos válidos dentro de una transacción, si no se envió `confirmar`, `_avisos` compara contra estos rangos. Si hay avisos sin confirmar, la transacción se revierte (`transaction.set_rollback`) y el formulario vuelve con la lista.

| Dato | Aviso si es |
|---|---|
| Temperatura (`temperatura_c`) | menor que 10 o mayor que 40 °C |
| Humedad (`humedad_relativa`) | menor que 15 % |
| pH (`ph`) | menor que 4 o mayor que 9 |
| Temperatura del agua (`temp_agua`) | menor que 10 o mayor que 40 °C |
| EC (`ec`, ya en mS/cm) | mayor que 5 (5000 µS/cm) |
| pH de runoff por planta | menor que 4 o mayor que 9 |
| Dosis de nutriente | menor que 0 o mayor que 10 en la unidad del nutriente |

Cada aviso tiene una clave (`campo=valor`, por ejemplo `ph=3.2`). El bloque de avisos muestra el texto, un enlace "Corregir" que lleva al campo (`data-campo`) y el botón "Guardar igual", que envía `aviso_ok` con las claves vistas separadas por `|`.

- Al reenviar con `aviso_ok`, solo esas claves quedan confirmadas; si el valor cambia, la clave cambia y vuelve a avisar.
- El parámetro `confirmar=1` confirma todos los avisos de una vez.
- Con avisos, el formulario conserva lo escrito (`_valores_post`).

## Errores de validación

Cualquier falla de validación lanza `RegistroError(mensaje, campos)`. La vista muestra un bloque rojo con el mensaje y la lista de errores por campo ("Temperatura: ...", usando `NOMBRES_CAMPOS`), marca los campos con `has-error` y enfoca el primero. Los errores de modelo (`full_clean`) se unen en un solo mensaje. Los mensajes de pH y EC vienen de `services/validacion.validar_solucion`: pH entre 0 y 14; EC mayor o igual que cero.

## Guardar y deshacer

Guardar (`POST /registrar/`):

1. Exige un cultivo elegido entre los que la persona puede editar; si no, "Elegí un cultivo en el que puedas registrar."
2. Calcula la hora, arma los datos del tipo y llama a `guardar_registro(usuario, cultivo, tipo, observado, datos, archivos)` dentro de una transacción.
3. Aplica los avisos (ver arriba).
4. Si todo está bien: guarda en la sesión `registrar_tipo` (el tipo para la próxima vez) y `ultimo_registro` (`tipo`, `pk`, `t` con la hora y `bitacora` con la URL de la bitácora del cultivo), agrega el mensaje "<Guardado> en <cultivo>." con la etiqueta `registro` y redirige.

`creado_por` queda con la persona que guardó. Las fotos de planta llegan como archivo con nombre `planta-foto`.

Aviso (toast) en `base.html`: para los mensajes con la etiqueta `registro` muestra el texto, el enlace "Ver" (a la bitácora del cultivo) y un formulario "Deshacer" que envía `POST /registrar/deshacer/` con `volver` igual a la URL actual. Desaparece solo a los 10 segundos. Los mensajes con la etiqueta `borrado` muestran el texto y "Deshacer" hacia `registro_restaurar`. El resto de los mensajes se muestran como alertas con botón de cierre.

`registrar_deshacer` (`POST`, requiere sesión iniciada):

- Busca `ultimo_registro` en la sesión. Solo borra si pasaron 60 segundos o menos (`DESHACER_SEGUNDOS`) y el registro fue creado por la misma persona (`creado_por`).
- Si lo borra: mensaje "Listo, se deshizo."; si no, "Ya no se puede deshacer ese registro. Corregilo desde la bitácora."
- Siempre quita `ultimo_registro` de la sesión y redirige a `volver` (mismo sitio) o al panel de inicio (`growlog:dashboard`).

## Ficha de un registro

`GET /registro/<tipo>/<pk>/` muestra el registro en solo lectura (`registro_ficha.html`). Los tipos válidos son `ambiente`, `riego`, `evento`, `ec`, `tarea` y `planta`; cualquier otro da 404. Una nota se abre como `evento` y se titula "Nota".

| Tipo | Se muestra |
|---|---|
| ambiente | Temperatura y humedad en el título; VPD con su estado (según la etapa); estado de la luz |
| riego | Volumen total; pH y EC de la solución (y EC del medidor); cada nutriente con su dosis y unidad; sección "Por planta" con volumen y, si hubo, datos de runoff (pH, EC, notas) |
| ec | pH y EC; qué se midió; EC del medidor; temperatura del agua |
| evento | Tipo; plantas afectadas con enlace; seguimiento (fecha, qué revisar, si está resuelto); descripción |
| tarea | Título; estado (pendiente, o hecha con fecha); categoría y prioridad; fecha objetivo; descripción |
| planta | Planta, altura, nudos, canopy, aspecto, síntomas y foto |

Todas muestran las notas y quién registró (`creado_por`). El enlace "Volver" usa el parámetro `volver` (de este sitio) o la bitácora del cultivo.

Si la persona puede editar el cultivo se muestran "Corregir" y "Borrar". "Borrar" abre una confirmación que indica si se podrá deshacer durante un minuto (o, en una medición de planta con foto, que se borra también la foto y no se puede deshacer).

Las filas de la bitácora enlazan a la ficha con `{% ficha_url tipo pk %}`, que traduce el tipo de la bitácora (`medicion`, `medicion_ec`, `riego`, `evento`, `planta`, `ambiente`, `ec`, `tarea`) al de la ficha y agrega `?volver=` con la página actual. Etapas y fotoperíodo no tienen ficha.

## Corrección

`GET/POST /registro/<tipo>/<pk>/editar/` (`registro_editar`) reutiliza el formulario de Registrar (`registro_editar.html`) con un solo cultivo y un solo tipo fijados en campos ocultos. Acepta además `nota` como tipo; un `evento` cuyo `tipo` es `nota` se corrige como nota.

- Los valores iniciales se leen del registro con los mismos nombres que usa Registrar (`_valores_de`): la EC se convierte a ×10 y los decimales se muestran con coma.
- Las plantas ya presentes en el registro siguen disponibles aunque hoy estén archivadas (se marcan "archivada"); los nutrientes del riego siguen válidos aunque estén ocultos. Lo nuevo tiene que estar disponible en el cultivo.
- La hora del registro se muestra como elegida; la tarea no tiene hora.
- Usa `actualizar_registro` con las mismas reglas del alta, incluidos los avisos por valores inusuales y su confirmación.
- Aparecen dos casillas que no existen al crear: "Ya está resuelto" (seguimiento del evento) y "Ya está hecha" (tarea). Al marcar una tarea como hecha se completa `completada_en` con la hora actual; al desmarcarla se borra.
- En un riego, el desglose por planta y los nutrientes se reemplazan por lo enviado.
- Al guardar muestra "Listo, quedó corregido." y vuelve a `volver` o a la ficha.
- El pie del formulario ofrece "Cancelar o borrar", que lleva a la ficha.

Las URL anteriores siguen respondiendo y delegan en `registro_editar`:

| URL | Nombre | Tipo |
|---|---|---|
| `/riego/<pk>/editar/` | `riego_editar` | riego |
| `/evento/<pk>/editar/` | `evento_editar` | evento |
| `/medicion-ambiente/<pk>/editar/` | `medicion_ambiente_editar` | ambiente |
| `/medicion-ec/<pk>/editar/` | `medicion_ec_editar` | ec |
| `/tarea/<pk>/editar/` | `tarea_editar` | tarea |
| `/medicion-planta/<pk>/editar/` | `medicion_planta_editar` | planta |

## Borrado y restauración

`POST /registro/<tipo>/<pk>/borrar/` (`registro_borrar`):

- Guarda en la sesión (`ultimo_borrado`) una copia serializada del registro con sus hijos (en un riego, el desglose por planta y los nutrientes aplicados), la hora y el nombre; después lo borra.
- Una medición de planta con foto no se copia: se quita `ultimo_borrado` y el borrado no se puede deshacer.
- Muestra "<Nombre> borrado." con la etiqueta `borrado` (el toast ofrece "Deshacer") y redirige a `volver` o a la bitácora del cultivo.
- No hay vistas de borrado por tipo; el borrado de estos registros pasa siempre por la ficha.

`POST /registro/restaurar/` (`registro_restaurar`):

- Toma `ultimo_borrado` de la sesión (y lo quita). Si no existe o pasaron más de 60 segundos: "Ya no se puede deshacer ese borrado."
- Comprueba que el cultivo siga existiendo (si no, 404) y que la persona pueda editarlo (`exigir_edicion`, que responde 403 si no).
- Vuelve a crear los objetos con los mismos ids, dentro de una transacción. Si algo de lo que usaban ya no está (por ejemplo una planta o un nutriente), falla con "No se pudo deshacer: cambió algo de lo que usaba ese registro."
- En caso de éxito: "Listo, volvió."

## Línea de texto libre

El campo `[data-texto]` ("Escribilo: riego 1,5 L con grow 2, pH 6,2") interpreta una frase y completa el formulario. Todo corre en el navegador (`registrar.js`), con una gramática acotada; el servidor recibe los campos como si se hubieran tipeado a mano. No existe en el modo de corrección.

Comportamiento:

- Interpreta 250 ms después de dejar de escribir. Enter no envía el formulario: interpreta de inmediato.
- Lo completado desde el texto y no tocado a mano se vuelve a calcular en cada cambio del texto; al cambiar de cultivo se reinterpreta.
- Muestra "Entendí" con un chip por cada dato reconocido; tocar un chip enfoca el campo. Si no reconoce nada: "No entendí nada todavía. Probá con "riego 1,5 L, pH 6,2" o "25° 60%"."
- Cambia el tipo según lo que detecta: riego si hay volumen, nutrientes o plantas; ambiente si hay temperatura o humedad; pH/EC si hay solo pH o EC. Si no detecta tipo, deja el elegido.

Qué reconoce (el texto se compara sin mayúsculas ni tildes; "1,5" vale como 1.5):

| Dato | Formas reconocidas | Efecto |
|---|---|---|
| pH | `ph 6,2`, `ph: 6.2`, `ph=6.2` | Campo `ph` |
| EC | `ec 140`, `ce 1,4`, con `ms` o `us`/`µs` | Si trae `ms` o el valor es menor que 10 se multiplica por 100 (1,4 mS pasa a 140); con `us`/`µs` o valor desde 1000 se divide por 10 (1400 µS pasa a 140); si no, se toma tal cual como ×10 |
| Temperatura | `temp 25`, `temperatura 25 °C`, `25°`, `25 grados` | Campo `temperatura_c` |
| Humedad | `hr 60`, `humedad 60`, `hum 60`, `60%` | Campo `humedad_relativa` |
| Volumen | número con `ml`, `cc`, `l`, `lt`, `lts`, `litro(s)` | Volumen en ml (litros por 1000) |
| Por planta | `c/u`, `cada una`, `cada planta`, `por planta`, `c/planta` | El volumen es por planta |
| Plantas | el apodo de una planta activa del cultivo | Riega solo esas plantas |
| Nutrientes | nombre (o una palabra propia) de un nutriente del catálogo, con tolerancia de una letra, seguido de un número (hasta 2 palabras después) | Dosis del nutriente; sin número queda el chip "¿cuánto?" |
| Resto | palabras no reconocidas (3 letras o más en total, sin las de relleno como "riego", "con", "de", "hoy", "agua") | Se copia a las notas del tipo |

Reglas del volumen en riego:

- Con nombres de plantas y menos plantas que las del cultivo: se desmarca "Mismo volumen" y cada planta nombrada recibe el volumen.
- En el resto de los casos se marca "Mismo volumen". Si el texto dice por planta o nombra plantas, el volumen se aplica a cada una; si no, el volumen es total y se divide en partes iguales entre las plantas activas.
- Una palabra que aparece en varios nutrientes (casi siempre la marca) no alcanza para elegir uno; se usan las palabras que son propias de un solo nutriente.

## Ayudas en vivo del formulario

| Ayuda | Cuándo | Qué muestra |
|---|---|---|
| Total de ml | Riego | "total N ml" (suma de plantas, o volumen por planta por cantidad de plantas) o la cantidad de plantas |
| VPD | Ambiente, al tipear temperatura y humedad | VPD en kPa (fórmula de Magnus) y su estado frente al rango de la etapa del cultivo: bajo, alto o en rango |
| EC | Campos de EC | Conversión a µS y mS |
| pH | Campos de pH | "ideal" o "fuera del ideal" con el rango de la etapa |
| Paso de volumen | Riego con "Mismo volumen" | Botones − y + de 25 ml |

## Repetir riego

Si el cultivo tiene riegos previos, el bloque Riego muestra una tarjeta "Repetir riego del dd/mm" con el resumen del último riego (volumen total, nutrientes con dosis y pH). El botón "Repetir" completa:

- el volumen por planta (si todas recibieron lo mismo y son todas las plantas activas se marca "Mismo volumen" con ese valor; si no, se cargan los ml por planta),
- pH y EC de la solución,
- la dosis de cada nutriente (abre los nutrientes "Otros" si hace falta).

No se copian notas ni datos de runoff. La tarjeta no aparece en la corrección. Después de repetir, el botón cambia a "Listo ✓". El último riego es el de mayor `timestamp` del cultivo.

## Atajo Ctrl+K / ⌘K

Definido en `base.html` para las personas con sesión iniciada:

- Si la página ya tiene un campo de texto libre (`[data-texto]`, por ejemplo en `/registrar/` o con la hoja abierta), lo enfoca.
- Si no, abre la hoja haciendo clic en el botón de Registrar del lateral o de la barra, y al cargarse enfoca el campo de texto.
- Escape cierra la hoja.

## Tareas

Las tareas se crean y corrigen con el formulario de Registrar (tipo `tarea`, sin hora). Las acciones rápidas están en `views/tareas.py`.

| Acción | Comportamiento |
|---|---|
| Completar (`tarea_completar`) | Marca `completada=True` y `completada_en` con la hora actual |
| Reabrir (`tarea_descompletar`) | Marca `completada=False` y borra `completada_en` |

Respuestas de las dos acciones según el campo `origen` (solo con HTMX):

| Origen | Completar | Reabrir |
|---|---|---|
| `lista` (lista de tareas) | Respuesta vacía; la fila se borra | Respuesta del caso general |
| `hoy` (pantalla Hoy) | `hoy_tarea_hecha.html`: fila tachada con "Deshacer" | `hoy_item.html`: vuelve la fila original |
| Otro (resumen del cultivo) | `tarea_completar_oob.html`: la fila se borra y se suma a "Hechas" con "Reabrir" | `tarea_descompletar_oob.html`: se borra de "Hechas" y vuelve a pendientes (`tarea_row.html`) |
| Sin HTMX | Redirige a la página del cultivo | Redirige a la página del cultivo |

Listas:

- `/cultivo/<slug>/tareas/` (`tareas_list`): tareas de ese cultivo; accesible a quien pueda ver el cultivo.
- `/tareas/` (`tareas_todas`): tareas de todos los cultivos activos visibles (no archivados ni finalizados).
- Ambas aceptan `?categoria=` para filtrar, agrupan las pendientes con `services/hoy.agrupar_tareas` y muestran hasta 15 hechas, las más recientes primero. El botón "+ Nueva" aparece solo si la persona puede editar algún cultivo (o ese cultivo). Cada fila ofrece acciones solo si la persona puede editar su cultivo.

## Seguimientos de eventos

Un evento puede tener un seguimiento: `follow_up_fecha`, `follow_up_descripcion` y `follow_up_resuelto`. El bloque "Programar un seguimiento" del formulario de evento es plegable y se abre si ya hay fecha. Mientras no esté resuelto y su fecha llegue, el seguimiento aparece en la pantalla Hoy (en "Para revisar") y en el panel "Seguimientos" del cultivo.

`POST /evento/<pk>/resolver-followup/` (`evento_resolver_followup`) marca `follow_up_resuelto=True` y responde vacío; el panel del cultivo lo usa con HTMX para quitar la fila (`hx-swap="outerHTML"`). Para volver a abrir un seguimiento se corrige el evento y se desmarca "Ya está resuelto".

## Permisos

Reglas completas en [permisos.md](permisos.md) y [../acceso-por-cultivo.md](../acceso-por-cultivo.md).

| Acción | Quién puede |
|---|---|
| Abrir Registrar y elegir cultivo | Sesión iniciada; el selector lista solo cultivos propios o donde es editora |
| Guardar un registro nuevo | Dueña o editora del cultivo elegido; si el cultivo no está en su lista, error "Elegí un cultivo en el que puedas registrar." |
| Ver la ficha de un registro (GET) | Cualquier persona con acceso al cultivo, incluido el rol lector; sin acceso responde 404 |
| Corregir | Dueña o editora (`objeto_del_cultivo(..., editar=True)`); un lector recibe 403 |
| Borrar | Dueña o editora (es un POST sobre el registro); un lector recibe 403 |
| Restaurar un borrado | Dueña o editora del cultivo del registro |
| Deshacer un guardado | La misma persona que lo creó (`creado_por`), dentro de 60 segundos y en la misma sesión |
| Completar o reabrir una tarea | Dueña o editora |
| Resolver un seguimiento | Dueña o editora |
| Ver listas de tareas | Cualquier persona con acceso; las acciones solo en cultivos editables |
| Subir foto en una medición de planta | Quien cumpla `puede_subir_fotos` (ajuste `PERMITIR_FOTOS_A_TODOS` o permiso `growlog.subir_fotos`) |

## Rutas

Todas se incluyen bajo `/` con el espacio de nombres `growlog:` y requieren sesión iniciada.

| URL | Nombre | Método | Efecto |
|---|---|---|---|
| `/registrar/` | `registrar` | GET | Página de Registrar; con `hoja=1` por HTMX, la hoja |
| `/registrar/` | `registrar` | POST | Valida y guarda un registro nuevo; redirige con el aviso de guardado |
| `/registrar/deshacer/` | `registrar_deshacer` | POST | Borra el último registro guardado de esta sesión si tiene menos de un minuto |
| `/registro/<tipo>/<pk>/` | `registro_ficha` | GET | Ficha de solo lectura |
| `/registro/<tipo>/<pk>/editar/` | `registro_editar` | GET | Formulario de corrección |
| `/registro/<tipo>/<pk>/editar/` | `registro_editar` | POST | Guarda la corrección |
| `/registro/<tipo>/<pk>/borrar/` | `registro_borrar` | POST | Borra el registro y guarda una copia para restaurar |
| `/registro/restaurar/` | `registro_restaurar` | POST | Vuelve a crear el último registro borrado si tiene menos de un minuto |
| `/riego/<pk>/editar/` | `riego_editar` | GET, POST | Equivale a `registro_editar` de riego |
| `/evento/<pk>/editar/` | `evento_editar` | GET, POST | Equivale a `registro_editar` de evento |
| `/medicion-ambiente/<pk>/editar/` | `medicion_ambiente_editar` | GET, POST | Equivale a `registro_editar` de ambiente |
| `/medicion-ec/<pk>/editar/` | `medicion_ec_editar` | GET, POST | Equivale a `registro_editar` de ec |
| `/tarea/<pk>/editar/` | `tarea_editar` | GET, POST | Equivale a `registro_editar` de tarea |
| `/medicion-planta/<pk>/editar/` | `medicion_planta_editar` | GET, POST | Equivale a `registro_editar` de planta |
| `/tarea/<pk>/completar/` | `tarea_completar` | POST | Completa la tarea; la respuesta depende de `origen` |
| `/tarea/<pk>/descompletar/` | `tarea_descompletar` | POST | Reabre la tarea; la respuesta depende de `origen` |
| `/cultivo/<slug>/tareas/` | `tareas_list` | GET | Tareas del cultivo, con filtro `categoria` |
| `/tareas/` | `tareas_todas` | GET | Tareas de todos los cultivos activos visibles |
| `/evento/<pk>/resolver-followup/` | `evento_resolver_followup` | POST | Marca el seguimiento como resuelto |

`<tipo>` en `/registro/...`: `ambiente`, `riego`, `evento`, `ec`, `tarea` y `planta` para la ficha y el borrado; esos mismos más `nota` para la corrección.
