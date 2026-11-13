# Pantallas del trabajo diario sobre un cultivo

Describe la navegación de la app y las pantallas que se usan a diario: Hoy, Resumen del cultivo, Bitácora, Plantas, Tareas, Aire, Ciclo y fotos de planta. Para cargar datos (riegos, mediciones, eventos, notas, tareas) ver [registrar.md](registrar.md). Para el modelo de permisos ver [permisos.md](permisos.md) y [../acceso-por-cultivo.md](../acceso-por-cultivo.md).

Todas las pantallas exigen sesión iniciada (`@login_required`). Las rutas están en `growlog/urls.py` bajo el espacio de nombres `growlog`.

## Convenciones de acceso

| Rol | Qué puede hacer en las pantallas de este documento |
|---|---|
| Lector | Ver. Los botones y enlaces de edición no se dibujan. La barra lateral muestra "solo lectura" y el selector de cultivo agrega "· solo lectura". |
| Editor | Ver y modificar datos del cultivo (registrar, completar tareas, editar plantas, cambiar etapa y fotoperíodo, cosecha). |
| Propietario | Todo lo del editor, más archivar el cultivo y compartirlo. |

`objeto_del_cultivo()` (`growlog/permissions.py`) resuelve el cultivo de cada pantalla. Un cultivo al que el usuario no tiene acceso responde 404. Con `editar=True`, o con un método distinto de GET, HEAD u OPTIONS, un lector recibe 403. Además deja `request.cultivo_actual` y `request.puede_editar_cultivo`, que usan la navegación y los templates (`can_edit_cultivo` en el contexto).

## Navegación

### Estructura general

`templates/base.html` arma el marco de toda pantalla autenticada:

- Barra lateral de escritorio: `partials/lateral.html`.
- Encabezado del cultivo (selector y pestañas): bloque `cultivo_tabs`, que incluye `partials/cultivo_tabs.html` cuando existe `cultivo_nav`.
- Contenido de la pantalla: bloque `content`.
- Barra inferior del celular: bloque `bottom_nav`, que incluye `partials/bottom_nav.html`.
- Contenedor `#hoja`, donde se abre la hoja de Registrar.

Las pantallas `crud_form.html` y `crud_delete.html` dejan vacío el bloque `cultivo_tabs` y reemplazan la barra inferior por un único enlace "‹ Volver" a `back_url`.

### Barra inferior del celular

`partials/bottom_nav.html`. Cinco elementos, en este orden:

| Elemento | Destino | Se marca activo cuando |
|---|---|---|
| Hoy | `dashboard` (`/`) | `nav_activa == "hoy"` |
| Cultivo | `cultivo_detail` de `cultivo_destino`; si no hay cultivo, `nuevo_cultivo` | `nav_activa` es `cultivo` o `tareas` |
| + | Registrar (ver abajo) | no aplica |
| Plantas | `plantas_list` de `cultivo_destino`; si no hay cultivo, `nuevo_cultivo` | `nav_activa == "plantas"` |
| Más | `mas` | `nav_activa == "mas"` |

El botón + es un enlace a `/registrar/`. Salvo que la pantalla actual sea Registrar, también trae la hoja por HTMX (`hx-get` a `/registrar/?hoja=1` con destino `#hoja`). Si hay un cultivo abierto y el usuario puede editarlo, agrega `cultivo=<pk>` para preseleccionarlo. Detalle de la hoja en [registrar.md](registrar.md).

### Barra lateral de escritorio

`partials/lateral.html`. Mismos destinos que la barra inferior, con estas diferencias:

- Muestra "Tareas" (`tareas_list` de `cultivo_destino`) como elemento propio, solo si hay `cultivo_destino`.
- No tiene el + central; en el pie hay un botón "+ Registrar" con el mismo comportamiento y, debajo, el nombre de usuario con " · solo lectura" cuando el cultivo abierto no es editable por él.
- El logotipo "62×ROOTS" enlaza a Hoy.

### Selector "Cultivo ▾"

`partials/cultivo_selector.html`. Es un `<details class="nav-cultivo">` que se dibuja en el encabezado de cada pantalla de cultivo. El botón muestra "Cultivo · <nombre>" y, si el usuario no puede editar, "· solo lectura". El menú se cierra al tocar afuera o con Escape (script en `base.html`).

El menú agrupa los cultivos que arma `cultivos_del_menu()` (`growlog/context_processors.py`):

| Grupo | Contenido | Dato secundario |
|---|---|---|
| Mis cultivos activos | Propios, no archivados y no finalizados | Estado del cultivo |
| Compartidos conmigo | Ajenos, no archivados y no finalizados | "Editor" o "Solo lectura", y "de <propietario>" |
| Historial | Archivados o finalizados, propios y ajenos | "Archivado" o "Finalizado" |

Cada ítem enlaza a `cultivo_detail`. Al final hay "Ver todos" (`/#cultivos`) y "+ Nuevo cultivo" (`nuevo_cultivo`). Los cultivos se ordenan por `-fecha_inicio`, `-pk`.

### Pestañas del cultivo

`partials/cultivo_tabs.html` dibuja el selector y, debajo, una pestaña por cada ítem de `pestanas_cultivo`. El contexto lo arma `pestanas_cultivo()`, a partir de la lista `PESTANAS_CULTIVO`:

| Sección | Etiqueta | URL name |
|---|---|---|
| `resumen` | Resumen | `cultivo_detail` |
| `bitacora` | Bitácora | `timeline` |
| `tareas` | Tareas | `tareas_list` |
| `tendencias` | Aire | `cultivo_aire` |
| `ciclo` | Ciclo | `cultivo_ciclo` |
| `canopy` | Canopy | `canopy` |
| `energia` | Energía | `energia` |
| `reporte` | Reporte | `reporte` |
| `ajustes` | Ajustes | `cultivo_ajustes` |

"Ajustes" solo se incluye si el usuario puede editar el cultivo. La pestaña activa es la que coincide con `seccion_cultivo`. Las pestañas se desplazan horizontalmente en el celular y se envuelven en escritorio. En `cultivo_detail` el bloque `cultivo_tabs` se reemplaza por una versión que lleva el selector y, a su derecha, el estado de la luz (ver Resumen del cultivo).

### `SECCIONES_CULTIVO`

Diccionario en `growlog/context_processors.py` que asigna a cada URL name la sección de pestaña que queda marcada:

| URL name | Sección |
|---|---|
| `cultivo_detail`, `planta_detail`, `planta_etapa_list`, `plantas_list`, `planta_crear` | `resumen` |
| `timeline` | `bitacora` |
| `tareas_list` | `tareas` |
| `cultivo_aire` | `tendencias` |
| `canopy` | `canopy` |
| `energia` | `energia` |
| `reporte` | `reporte` |
| `cultivo_ajustes`, `cultivo_empezar` | `ajustes` |
| `cultivo_ciclo`, `cultivo_cosecha`, `cultivo_etapa`, `fotoperiodo_list` | `ciclo` |

Una pantalla cuyo URL name no está en el diccionario no marca ninguna pestaña. `planta_fotos` no figura, de modo que no marca pestaña, pero sí cuenta como "Plantas" en `nav_activa`.

### `navegacion` (context processor)

`navegacion(request)` devuelve un diccionario vacío si el usuario no está autenticado. Si lo está, expone:

| Variable | Valor |
|---|---|
| `cultivo_nav` | `request.cultivo_actual`, definido por `objeto_del_cultivo`. Es `None` en pantallas sin cultivo (Hoy, Más, Tareas de todos). |
| `seccion_cultivo` | Sección de `SECCIONES_CULTIVO` para el URL name actual. |
| `pestanas_cultivo` | Lista de pestañas con `seccion`, `etiqueta`, `icono`, `extra`, `activa`, `url`. Vacía si no hay `cultivo_nav`. |
| `pestana_extra_activa` | Primera pestaña con `extra` verdadero que esté activa, o `None`. |
| `nav_cultivos` | Grupos de `cultivos_del_menu()`. Se evalúa solo si el template lo usa (`SimpleLazyObject`). |
| `cultivo_destino` | Ver abajo. También perezoso. |
| `nav_activa` | `hoy`, `cultivo`, `plantas`, `tareas`, `mas` o cadena vacía. |

Otro context processor, `push_settings`, aporta `can_edit_cultivo` (permiso de edición sobre `cultivo_actual`), `can_manage_cultivo` (el usuario es el propietario del cultivo actual), `unidad_ec` y `vapid_public_key`.

### `cultivo_destino`

`cultivo_destino(request, cultivo, grupos)` decide a qué cultivo llevan "Cultivo", "Plantas" y "Tareas" de las barras:

1. Si la pantalla tiene cultivo abierto, ese.
2. Si no, el cultivo cuyo pk está en `request.session["cultivo_reciente"]`, buscado entre los activos, compartidos e historial.
3. Si no hay reciente o ya no es visible, el primer cultivo activo o compartido.
4. Si no hay ninguno, `None`, y los enlaces de la barra van a `nuevo_cultivo`.

### `nav_activa`

`seccion_nav(url_name, seccion)` calcula qué ítem de la barra queda marcado:

| Condición | Resultado |
|---|---|
| URL name `dashboard` | `hoy` |
| URL name `tareas_todas` | `tareas` |
| URL name en `PANTALLAS_MAS` | `mas` |
| URL name `planta_detail`, `planta_etapa_list`, `plantas_list` o `planta_fotos` | `plantas` |
| Sección `tareas` | `tareas` |
| Cualquier otra pantalla con sección | `cultivo` |
| Sin sección | cadena vacía |

En la barra inferior, "Cultivo" se marca activo tanto con `cultivo` como con `tareas`. En la lateral, "Cultivo" solo con `cultivo` y "Tareas" con `tareas`.

### `PANTALLAS_MAS`

Conjunto de URL names de pantallas globales que cuelgan de "Más": `mas`, `cuenta`, `nutrientes`, `nutriente_crear`, `nutriente_editar`, `invitados_panel`, `faq`, `actividad`. En ellas `nav_activa` es `mas`.

### Pantalla Más

URL `/mas/` (`mas`), vista `growlog/views/mas.py`, template `templates/growlog/mas.html`. Acceso: cualquier usuario autenticado.

Muestra:

- Si hay `cultivo_destino`: un bloque con el nombre del cultivo y una fila por cada pestaña de `pestanas_cultivo()` salvo Resumen (que ya es "Cultivo" en la barra). "Ajustes" aparece solo si el usuario puede editar ese cultivo.
- General: Nuevo cultivo, Tareas de todos los cultivos (`tareas_todas`), Nutrientes, Compartir cultivos (solo si el usuario es propietario de algún cultivo activo o del historial), Dudas de cultivo y, para superusuarios, Actividad y Admin.
- Preferencias: Tu cuenta y avisos (`cuenta`), selector de tema (Auto, Claro, Oscuro, guardado en el dispositivo) y el interruptor de avisos push (oculto hasta que el navegador lo soporta).
- Botón Salir (POST a `logout`).

### `CultivoRecienteMiddleware`

`growlog/middleware.py`. Después de cada respuesta, si la vista dejó `request.cultivo_actual` y es distinto de `session["cultivo_reciente"]`, guarda el pk en la sesión. Lo leen `cultivo_destino` y Registrar (propone ese cultivo primero).

## Hoy

| | |
|---|---|
| URL | `/` (`dashboard`) |
| Vista | `dashboard` en `growlog/views/cultivos.py`, que renderiza `resumen_hoy(request.user)` |
| Template | `templates/growlog/dashboard.html` con `partials/hoy_cultivo.html`, `partials/hoy_item.html` y `partials/hoy_tarea_hecha.html` |
| Servicio | `growlog/services/hoy.py` |
| Estáticos | `static/growlog/hoy.css`, `static/growlog/hoy.js` |
| Acceso | Cualquier usuario autenticado. Trabaja sobre todos los cultivos visibles (propios y compartidos). |

### Qué muestra

Encabezado con la fecha de hoy. Luego, según existan cultivos:

1. **Para revisar.** Encabezado con el total (`atencion_total`). Contiene, en este orden:
   - Alertas de Aire: un cultivo activo cuyo VPD de la última medición es `alto` o `bajo` y que se midió en las últimas 24 horas (`ALERTA_VPD_HASTA`). Cada alerta enlaza a Aire del cultivo.
   - Hasta 12 ítems (`atencion`): tareas sin completar con fecha objetivo hoy o anterior, o con prioridad urgente, y seguimientos de eventos sin resolver con fecha de seguimiento hoy o anterior. Se ordenan primero las vencidas, luego por fecha, prioridad (urgente, normal, baja), tipo y pk.
   - Si no hay nada: "Nada vencido ni urgente".
   - Si hay más de 12 relevantes: aviso con la cantidad restante (`atencion_restante`).
   - Línea con el total de tareas sin completar de los cultivos activos y cuántas no tienen fecha.
2. **Leyenda del Núcleo** (riego, medición, evento, nota), si hay cultivos activos.
3. **Mis cultivos activos** y **Compartidos conmigo**: una tarjeta por cultivo (`hoy_cultivo.html`).
4. **Historial**: cultivos finalizados (con fechas de inicio y cierre) y archivados, cada uno como enlace al resumen del cultivo.
5. **Aire ahora**: panel lateral en escritorio con el mapa temperatura × HR (ver abajo). Solo existe si algún cultivo activo tiene mediciones de ambiente.

Los cultivos activos son los no archivados y con estado distinto de `finalizado`. Se ordenan por `-fecha_inicio`, `-pk`.

### Tarjeta de cultivo

`partials/hoy_cultivo.html`. Contenido:

- Nombre del cultivo (enlace al resumen) y un pill con la etapa corta (Plántula, Veg, Flora, Secado, Curado) y el día. El día cuenta desde `fecha_inicio_flora` cuando el cultivo está en flora; si no, desde `fecha_inicio`.
- Núcleo: un SVG con una columna por día de vida del cultivo. Cada columna se divide en hasta cuatro capas, una por tipo de registro de ese día: riego (`w`), medición de ambiente o de pH/EC (`m`), evento (`e`) y nota (`n`, un evento de tipo nota). El ancho es proporcional a la edad: el cultivo más viejo ocupa todo el ancho y los demás un porcentaje, con mínimo 8 %.
- Para cultivos ajenos: "Editor" o "Solo lectura" y "de <propietario>".
- Última lectura de ambiente: temperatura, humedad y VPD con su estado (ideal, alto, bajo; por la etapa vigente cuando se midió). A la derecha, "regado hoy" o "sin riego N d" (en estilo de advertencia desde 3 días).
- Frescura de la lectura: "hace X" si es de menos de 6 horas; "dato viejo" si pasaron más de 6 horas (`DATO_VIEJO`); "fecha futura, revisá el registro" si la marca de tiempo es posterior a ahora.
- Sin mediciones: "Sin mediciones de ambiente", más los días sin riego si existen.
- Enlace "+ registrar" a `/registrar/?cultivo=<pk>`, solo si el usuario puede editar ese cultivo.

Toda la información de cada tarjeta sale de `resumen_hoy()`: la última `MedicionAmbiente`, el último `Riego`, el conteo de plantas activas no archivadas, los `CambioEtapaCultivo` (etapa efectiva a la fecha) y los rangos de `ParametroIdeal`.

### Mapa de aire

`hoy.js` lee el JSON `hoy-mapa-datos` (`mapa`, de `_mapa_aire`). Dibuja un SVG de temperatura contra humedad relativa, coloreado por zonas de VPD según el rango ideal del cultivo elegido. Por cada cultivo activo con medición dibuja un punto (la última lectura, hueco si es dato viejo, con color según el estado de VPD) y una línea punteada con hasta 12 lecturas de las últimas 24 horas. Si hay más de un cultivo, los chips permiten elegir de cuál se toman las zonas. La nota inferior indica el rango de VPD en uso o que se usan cortes generales si la etapa no tiene ideal.

### Completar tareas desde Hoy

Cada tarea de "Para revisar" (`hoy_item.html`) tiene un botón circular que hace `hx-post` a `tarea_completar` con `origen=hoy`. El servidor responde `hoy_tarea_hecha.html` y reemplaza la fila (`outerHTML`): queda tachada, con "Deshacer". Ese botón hace `hx-post` a `tarea_descompletar` con `origen=hoy` y devuelve la fila original. El botón solo se dibuja si el usuario puede editar el cultivo de la tarea; si no, se muestra un círculo sin acción. Los seguimientos enlazan a `cultivo_detail#followup-row-<pk>`.

### Estados

- Sin ningún cultivo: tarjeta "Tu bitácora empieza con un cultivo" con el botón "Crear mi primer cultivo".
- Sin cultivos activos pero con historial: tarjeta "No tenés cultivos activos" con "Empezar un cultivo".
- Cultivo ajeno de solo lectura: la tarjeta no muestra "+ registrar" y las tareas no se pueden completar.

## Resumen del cultivo

| | |
|---|---|
| URL | `/cultivo/<slug>/` (`cultivo_detail`) |
| Vista | `cultivo_detail` en `growlog/views/cultivos.py` |
| Template | `templates/growlog/cultivo_detail.html` con `partials/tarea_row.html`, `partials/tarea_completar_oob.html`, `partials/tarea_descompletar_oob.html` |
| Estáticos | `static/growlog/cultivo.css` |
| Acceso | Lector, editor o propietario. |

### Qué muestra

Cabecera:

- Selector de cultivo y, a la derecha, el estado de la luz ahora ("luz encendida" o "luz apagada" y el fotoperíodo vigente). Se calcula con `calcular_luz_estado` y el fotoperíodo vigente; no se muestra en cultivos finalizados ni sin fotoperíodo.
- Si el cultivo está finalizado: "cultivo finalizado el <fecha>"; si está archivado: "cultivo archivado".
- Título con el nombre.
- Pills: etapa y día (enlazan a Ciclo; "flora día N" cuando hay inicio de flora, si no "día N"), "regado hoy" o "sin riego N d" (advertencia desde 3 días, error desde 5; no se muestra en cultivos finalizados), y cantidad de plantas activas (enlaza a Plantas).
- Tarjeta "Primeros pasos · N de M" con barra de progreso, que enlaza a `cultivo_empezar`. Aparece solo para quien puede editar, solo si el cultivo no está finalizado ni archivado, tiene hasta 21 días de vida y le quedan pasos (`services/onboarding.recordar`).
- Navegación `Núcleo · Aire · Plantas · Ciclo` (Núcleo marcado).

Columna principal:

- **Vitales**: Temp, HR, VPD y pH/EC de la última medición. Temp, HR y VPD llevan debajo su estado (ideal, alto, bajo) comparando con `ParametroIdeal` de la etapa vigente al medir (`evaluar_ambiente`); si no hay rango, "sin ref.". Si la lectura es de hace más de 6 horas o no existe, los vitales se atenúan. El VPD enlaza a Aire. El bloque de pH/EC muestra la última `MedicionEC` (pH, EC en la unidad del perfil y en ×10 µS/cm) y, si la EC supera 5 mS/cm, "fuera de lo habitual" con enlace "revisar" para quien edita.
- **Aviso de dato viejo**: si la última medición tiene más de 6 horas, o no hay ninguna, y el cultivo no está finalizado, muestra su antigüedad y, para quien edita, el botón "medir" (`/registrar/?cultivo=<pk>&kind=ambiente`). Si la lectura es reciente muestra "medido hace X".
- **Actividad reciente**: los 8 registros más nuevos entre ambiente, riego, evento y pH/EC (`build_timeline`), con enlace a la ficha de cada registro (`ficha_url`). Quien edita ve "⋯" que lleva a la edición del registro. Enlace "bitácora completa" a Bitácora. Vacío: "Todavía no hay registros" y, para quien edita, "Registrar el primero".
- **Plantas**: lista de plantas no archivadas con apodo, strain, etapa efectiva y estado si no es activa. "+ agregar" lleva a `planta_crear` (solo editores). Vacío: "Sin plantas todavía". Si hay plantas archivadas, un desplegable "archivadas · N" las lista para abrirlas.

Columna lateral:

- **Tareas**: hasta 10 tareas sin completar, ordenadas por `fecha_objetivo` y prioridad descendente, con cuenta de vencidas. Enlaces "ver todas" (`tareas_list`) y, para editores, "+ nueva" (Registrar con `kind=tarea`). Mensaje "Sin tareas pendientes ✓" cuando la lista queda vacía.
- **Seguimientos**: eventos con fecha de seguimiento sin resolver, ordenados por fecha, con "vencido" u "hoy". El botón circular hace `hx-post` a `evento_resolver_followup` y reemplaza la fila.
- **Hechas hace poco**: las 5 últimas tareas completadas (`completada_en`), con "Reabrir" para editores. El bloque está oculto si no hay ninguna.
- **Setup**: fotoperíodo vigente (enlace a `fotoperiodo_list` para editores), lámpara, sustrato, carpa e inicio. "editar" lleva a `cultivo_editar` (editores).

### Completar y reabrir tareas en el Resumen

El botón de cada tarea (`tarea_row.html`) hace `hx-post` a `tarea_completar` sin `origen`, con destino la fila (`hx-swap="delete"`). La respuesta es `tarea_completar_oob.html`: agrega la tarea a `#tareas-done` con un bloque `hx-swap-oob="afterbegin"`. "Reabrir" hace `hx-post` a `tarea_descompletar`, borra la fila de Hechas y devuelve `tarea_descompletar_oob.html`, que reinserta la tarea al principio de `#tareas-lista`. Un script del template muestra el bloque Hechas cuando recibe contenido.

### Estados

- Finalizado: se muestra el encabezado "cultivo finalizado", el pill de estado dice "Finalizado", no se muestra la luz ni los días sin riego ni el aviso de dato viejo.
- Archivado: encabezado "cultivo archivado".
- Lector: no hay "+ agregar", "+ nueva", "medir", "editar", "⋯", ni botones para completar tareas o resolver seguimientos (se dibujan círculos sin acción).

## Bitácora (Núcleo)

| | |
|---|---|
| URL | `/cultivo/<slug>/timeline/` (`timeline`) |
| Vista | `timeline` en `growlog/views/cultivos.py` |
| Template | `templates/growlog/timeline.html` y `partials/bitacora_filas.html` |
| Servicio | `growlog/services/bitacora.py` |
| Estáticos | `static/growlog/bitacora.css` |
| Acceso | Lector, editor o propietario. |

### Parámetros

| Parámetro GET | Efecto |
|---|---|
| `tipo` | Filtro: `medicion`, `riego`, `evento`, `medicion_ec`, `ciclo`, `planta`. Cualquier otro valor equivale a "Todo". |
| `desde` | Posición inicial de la página (entero no negativo; un valor inválido vale 0). |
| `dia` | Fecha ISO del último día mostrado en la página anterior; sirve para no repetir el separador de día. |

### Qué muestra

Cabecera con el total de registros y el día del cultivo, y, para editores, el botón "+ Registrar" (con `cultivo=<pk>`). Debajo, chips de filtro con la cuenta de cada tipo; los tipos sin registros no se muestran. Los filtros son:

| Filtro | Etiqueta | Fuentes que incluye |
|---|---|---|
| `medicion` | Ambiente | Mediciones de ambiente |
| `riego` | Riego | Riegos |
| `evento` | Evento | Eventos |
| `medicion_ec` | pH/EC | Mediciones de pH y EC |
| `ciclo` | Ciclo | Cambios de etapa y de fotoperíodo del cultivo |
| `planta` | Plantas | Mediciones de planta |

Sin filtro se incluyen las siete fuentes. Los registros se ordenan del más nuevo al más viejo. Los cambios de etapa, de fotoperíodo y las mediciones de planta tienen solo fecha, por lo que se ubican al comienzo de su día (00:00 locales). Un separador de día ("Hoy" o "día d/m") aparece cada vez que cambia el día, incluso entre una página y la siguiente.

Cada fila (`bitacora_filas.html`) tiene una franja de color por tipo, un título (por ejemplo, "Riego 500 ml · pH 6.0 · EC …", "Ambiente 24.0° · 60% · VPD …", "Pasó a flora temprana", "Fotoperíodo 12/12 · enciende 06:00"), una línea secundaria (hora o fecha, plantas con volumen y runoff, nutrientes con dosis, plantas afectadas, aviso de seguimiento, notas truncadas, autor) y un enlace a la ficha del registro cuando existe (`ficha_url`; las etapas y fotoperíodos no tienen ficha). Quien edita ve además "⋯", que lleva a la edición: `riego_editar`, `evento_editar`, `medicion_ec_editar`, `medicion_ambiente_editar`, `cambio_etapa_cultivo_editar`, `cambio_fotoperiodo_editar` o `medicion_planta_editar`.

### Paginación

Cada página tiene 50 registros (`POR_PAGINA`). Para cada fuente se piden solo `desde + 50 + 1` filas, así que el costo no depende del largo del historial. "Ver más" es un enlace con `desde=<siguiente>&dia=<ultimo_dia>` (y `tipo` si hay filtro). Con HTMX (`hx-get`, `hx-swap="outerHTML"`) y `desde` mayor que 0, la vista devuelve solo `partials/bitacora_filas.html` y las filas se agregan debajo; en cualquier otro caso devuelve la página completa.

### Estados

- Sin registros y sin filtro: "Todavía no hay registros" y, para editores, "Registrar el primero".
- Filtro sin resultados: "No hay registros de este tipo".
- Lector: no se muestran "+ Registrar" ni "⋯".

## Plantas

### Lista de plantas

| | |
|---|---|
| URL | `/cultivo/<slug>/plantas/` (`plantas_list`) |
| Vista | `plantas_list` en `growlog/views/plantas.py` |
| Template | `templates/growlog/plantas_list.html` |
| Estáticos | `static/growlog/plantas.css` |
| Acceso | Lector, editor o propietario. |

El parámetro `ver` elige la pestaña: `activas` (por defecto), `cosechadas`, `descartadas` o `archivadas`. Cualquier otro valor equivale a `activas`.

| Pestaña | Filtro sobre `Planta` |
|---|---|
| Activas | `estado = activa` y `archivado = False` |
| Cosechadas | `estado = cosechada` y `archivado = False` |
| Descartadas | `estado = descartada` y `archivado = False` |
| Archivadas | `archivado = True` |

Cada pestaña muestra su cuenta. La pantalla es una grilla de tarjetas (`resumen_planta` en `services/plantas.py`): foto de portada (la miniatura de la medición más reciente con foto) o "sin foto", apodo, altura actual en cm, strain, mini-curva de altura y una línea de última medición ("medida hoy", "ayer" o "hace N d", con ● o ◌ según tenga más de 5 días, y el ritmo en cm/día entre las dos últimas alturas). Sin mediciones: "sin medir todavía". Cada tarjeta enlaza a la ficha. Los editores ven "+ Agregar". Vacío: "Sin plantas activas" (o "No hay plantas acá" en otras pestañas) y, para editores en Activas, "Agregar planta".

### Alta de plantas

| | |
|---|---|
| URL | `/cultivo/<slug>/planta/nueva/` (`planta_crear`) |
| Vista | `planta_crear` |
| Template | `templates/growlog/plantas_nuevas.html` |
| Acceso | Editor o propietario. |

Formulario `PlantasNuevasForm`: cantidad (1 a 30), strain (opcional) y tipo (por defecto `foto`). El template agrega un campo de apodo por cada planta (`apodo-1`, `apodo-2`, ...) mediante JavaScript; el placeholder de cada uno es "<strain> N" (o "Planta N"). Al guardar, se crean todas con `bulk_create`; un apodo vacío se completa con "<strain> N" o "Planta N" (máximo 60 caracteres). Redirige a la lista de plantas, o a "Primeros pasos" si vino con `desde=empezar` en la URL (el formulario reenvía `siguiente=empezar`).

### Ficha de planta

| | |
|---|---|
| URL | `/planta/<pk>/` (`planta_detail`) |
| Vista | `planta_detail` |
| Template | `templates/growlog/planta_detail.html` |
| Estáticos | `cultivo.css`, `plantas.css`, `fotos.js` |
| Acceso | Lector, editor o propietario del cultivo de la planta. |

Muestra:

- Enlace "‹ Plantas" y, para editores, "editar".
- Apodo, strain, posición en la carpa, tipo y, si corresponde, estado (cosechada, descartada) y "archivada". El pill de etapa (etapa efectiva de la planta) enlaza al historial de etapa de la planta.
- Altura actual, ritmo en cm/día y antigüedad de la última medición.
- Curva de altura (si hay al menos 2 mediciones con altura), con líneas verticales para los eventos de la planta dentro del rango de fechas de la curva, salvo las notas, rotuladas con el tipo.
- Datos de la última medición: canopy, nudos y aspecto general; síntomas si los hay. Sin mediciones: "Todavía sin medir".
- Fotos: tira de miniaturas de las mediciones con foto. Cada una abre un visor a pantalla completa (anterior, siguiente, deslizar, flechas del teclado, Escape). El enlace "comparar" (o "ver" si hay una sola) va a Fotos.
- Riegos de la planta (últimos 10, con volumen, runoff, pH y EC de runoff si los hay), eventos (últimos 10) y mediciones (todas, más nueva primero), cada uno con enlace a su ficha y "⋯" de edición para editores.
- Genética: días de flora estimados, relación índica/sativa, THC estimado, rinde real y estimado, notas.
- Para editores, el botón "Medir a <apodo>", que abre Registrar con `kind=planta` y la planta elegida.

La ficha marca "Plantas" en la barra (`nav_activa = plantas`) y "Resumen" en las pestañas.

### Fotos de la planta

| | |
|---|---|
| URL | `/planta/<pk>/fotos/` (`planta_fotos`) |
| Vista | `planta_fotos` |
| Template | `templates/growlog/planta_fotos.html` |
| Estáticos | `plantas.css`, `fotos.js` |
| Acceso | Lector, editor o propietario. |

Lista las mediciones de la planta con foto, de la más nueva a la más vieja, con el día del cultivo (`fecha - fecha_inicio`) y la altura. Dos vistas, conmutadas con botones sin recargar:

- Línea de tiempo: grilla de miniaturas; cada una abre el visor.
- Comparar (solo con 2 o más fotos): dos fotos superpuestas con un corte vertical que se mueve con un control deslizante; abajo, una tira para elegir cuáles dos comparar. Arranca con la más vieja (A) y la más nueva (B). Los rótulos muestran fecha y día; debajo se muestran la diferencia entre ambas y la cantidad de días que las separan.

Vacío: "Todavía no hay fotos" ("Las fotos se suben al medir la planta"). Las imágenes se sirven desde `protected_media` (`growlog/views/media.py`), que solo entrega fotos de cultivos visibles para el usuario; la miniatura se cachea 1 día en el navegador y la foto completa no se guarda. Al subirse, `services/fotos.py` limita el lado a 2048 px y genera una miniatura de 480 px.

### Editar, archivar y eliminar una planta

| URL | Nombre | Acceso |
|---|---|---|
| `/planta/<pk>/editar/` | `planta_editar` | Editor o propietario |
| `/planta/<pk>/eliminar/` | `planta_eliminar` | Editor o propietario |

`planta_editar` usa `PlantaForm` en `crud_form.html` (apodo, strain, tipo, posición, días de flora estimados, relación índica/sativa, THC, yield estimado y real, fechas de corte y seco, peso húmedo, estado, notas de genética y casilla "Archivada"). Al guardar vuelve a la ficha. Desmarcar "Archivada" restaura la planta.

`planta_eliminar`: si la planta tiene historial (riegos, mediciones, cambios de etapa, posiciones en el canopy o eventos), la confirmación dice "Archivar planta": al aceptar se archiva y se conservan sus datos. Si no tiene historial, la confirmación es "Eliminar planta" y se borra. En ambos casos redirige al Resumen del cultivo; las archivadas quedan en el desplegable "archivadas" del Resumen y en la pestaña Archivadas de la lista.

### Etapa por planta

| | |
|---|---|
| URL | `/planta/<pk>/etapa/` (`planta_etapa_list`) |
| Template | `templates/growlog/etapa_historial.html` (compartido con la etapa del cultivo) |
| Acceso | Lector (solo ve el historial), editor o propietario. |

La etapa de una planta es la del cultivo, salvo que tenga un `CambioEtapaPlanta` propio más reciente que el último cambio de etapa del cultivo; un cambio de etapa del cultivo posterior la vuelve a igualar. La pantalla muestra la etapa actual ("heredada del cultivo" si no hay una propia vigente), un formulario "cambiar etapa" para editores (etapa, fecha de inicio por defecto hoy, notas) y la tabla de historial, con la fila vigente marcada "activo". Los editores ven "Editar" y "Eliminar" por fila (`cambio_etapa_planta_editar`, `cambio_etapa_planta_eliminar`). Un error de validación del modelo se muestra como error del formulario.

## Tareas

| | |
|---|---|
| URL de un cultivo | `/cultivo/<slug>/tareas/` (`tareas_list`) |
| URL de todos | `/tareas/` (`tareas_todas`) |
| Vistas | `tareas_list`, `tareas_todas` en `growlog/views/tareas.py` |
| Template | `templates/growlog/tareas_list.html`, con `partials/hoy_item.html` y `partials/hoy_tarea_hecha.html` |
| Servicio | `agrupar_tareas` e `item_tarea` en `services/hoy.py` |
| Acceso | `tareas_list`: lector, editor o propietario. `tareas_todas`: cualquier usuario autenticado; incluye solo los cultivos activos (no archivados ni finalizados) que puede ver. |

### Qué muestra

- Cabecera con el nombre del cultivo (o "Todos los cultivos") y la cantidad de tareas sin completar. El botón "+ Nueva" abre Registrar con `kind=tarea` (como hoja por HTMX); se dibuja solo si el usuario puede editar al menos un cultivo del alcance, y en la vista de un cultivo solo si puede editar ese cultivo.
- Selector "Este cultivo / Todos". En `tareas_todas` el primer botón lleva a las tareas del `cultivo_destino`.
- Chips de categoría. El parámetro GET `categoria` filtra sin completar y hechas por `Tarea.categoria`; "Todas" quita el filtro.
- Grupos de tareas sin completar, solo los que tienen elementos:

| Grupo | Criterio | Orden |
|---|---|---|
| Vencidas | `fecha_objetivo` anterior a hoy | fecha, prioridad, pk |
| Hoy y próximas | `fecha_objetivo` de hoy en adelante | fecha, prioridad, pk |
| Sin fecha | sin `fecha_objetivo` | prioridad, pk |

La prioridad ordena urgente, normal, baja. Cada fila muestra el título (truncado a 120 caracteres), el cultivo (en la vista de todos), la categoría, la fecha ("hoy", "venció d/m" o "sin fecha") y la marca "urgente". El texto enlaza a la ficha de la tarea.

- "Hechas hace poco": desplegable con las 15 últimas completadas, con el botón "Reabrir".

### Completar y descompletar

| URL | Nombre | Método | Acceso |
|---|---|---|---|
| `/tarea/<pk>/completar/` | `tarea_completar` | POST | Editor o propietario |
| `/tarea/<pk>/descompletar/` | `tarea_descompletar` | POST | Editor o propietario |
| `/tarea/<pk>/editar/` | `tarea_editar` | GET/POST | Editor o propietario |

`tarea_completar` marca `completada = True` y `completada_en = ahora`. `tarea_descompletar` los revierte. Sin HTMX, ambas redirigen al Resumen del cultivo. Con HTMX responden según el parámetro `origen`:

| Vista | `origen` | Respuesta |
|---|---|---|
| `tarea_completar` | `lista` | Respuesta vacía (la fila se borra). |
| `tarea_completar` | `hoy` | `hoy_tarea_hecha.html`: la fila tachada con "Deshacer". |
| `tarea_completar` | otro o ausente | `tarea_completar_oob.html` (Resumen del cultivo). |
| `tarea_descompletar` | `hoy` | `hoy_item.html`: la fila original. |
| `tarea_descompletar` | otro o ausente | `tarea_descompletar_oob.html` (Resumen del cultivo). |

Los templates `hoy_item.html` y `hoy_tarea_hecha.html`, usados en Hoy y en Tareas, envían siempre `origen=hoy`; el Resumen del cultivo no envía `origen`. En la lista de Tareas, la fila hecha muestra "Reabrir" en lugar de "Deshacer" y el nombre del cultivo.

El alta de tareas se hace desde Registrar ([registrar.md](registrar.md)); la edición usa el mismo formulario en modo edición.

### Estados

- Sin tareas: "Nada pendiente" (con "en esta categoría" si hay filtro).
- Lector: las filas muestran un círculo sin acción y no hay "+ Nueva" ni "Reabrir".

## Aire

| | |
|---|---|
| URL | `/cultivo/<slug>/aire/` (`cultivo_aire`) |
| Vista | `cultivo_aire` en `growlog/views/cultivos.py` |
| Template | `templates/growlog/aire.html` (JavaScript y estilos incluidos en el template) |
| Servicio | `growlog/services/vpd.py` (`mapa_vpd`, `lecturas_ph_ec`, `etapas_ideales`, `estado_de`) |
| Acceso | Lector, editor o propietario. |

### Parámetros

`rango` elige la ventana de tiempo: `24h`, `7d` (por defecto), `30d` o `ciclo` (todo el cultivo). Un valor desconocido equivale a `7d`. Se leen como máximo 600 lecturas por serie (las más recientes del rango).

### Qué muestra

- Etapa actual del cultivo.
- VPD de la última medición del cultivo, aunque quede fuera del rango elegido, con su estado ("En rango", "Aire seco, VPD alto", "Aire húmedo, VPD bajo" o "Sin rango ideal cargado"), temperatura, humedad y antigüedad (resaltada si pasaron más de 6 horas).
- Selector de rango de tiempo.
- Chips con una etapa por cada `ParametroIdeal` cargado (en el orden del ciclo), con "ahora" en la etapa vigente. Al elegir una etapa se redibuja el mapa y se muestran sus rangos de VPD, temperatura y humedad. Arranca en la etapa actual. Sin parámetros cargados, un aviso indica que el mapa muestra solo el VPD.
- Mapa de VPD: gráfico de temperatura contra humedad relativa con cinco zonas de color (muy bajo, bajo, ideal, alto, muy alto) calculadas con el rango de VPD de la etapa elegida (sin rango, se usan cortes 0,8 y 1,2 kPa con margen de 0,3), el rectángulo punteado de temperatura y HR ideales, la estela de lecturas de la más vieja a la más nueva, y la última lectura resaltada. El punto es hueco si la luz estaba apagada (según el fotoperíodo vigente al medir). Tocar un punto, o enfocarlo y presionar Enter o espacio, muestra fecha, etapa, estado de la luz, VPD y su estado, temperatura y humedad. Sin lecturas en el rango: "No hay mediciones en este rango" y, para editores, "Medir ahora".
- Porcentajes de lecturas en rango: total, con luz y sin luz. Cada lectura se juzga con el ideal de la etapa vigente cuando se midió; las lecturas sin ideal no cuentan.
- Curvas en el tiempo de temperatura, humedad y VPD, con una banda que sigue el ideal de la etapa de cada tramo y los puntos fuera de banda en color de error; una franja inferior muestra las etapas (veg, flora, secado y curado) y los extremos de fecha.
- pH y EC: curvas con los puntos de las mediciones de pH/EC, la solución de cada riego (`ph_agua`, `ec_solucion`) y el runoff por planta (`ph_runoff`, `ec_runoff`), coloreados por fuente (solución, runoff, agua de entrada, sustrato). La EC se calcula en µS/cm y se muestra en la unidad del perfil del usuario. Sin datos: "No hay pH ni EC en este rango" y, para editores, "Cargar una medición".
- Los gráficos se redibujan si cambia el tema.

## Ciclo

### Pantalla Ciclo

| | |
|---|---|
| URL | `/cultivo/<slug>/ciclo/` (`cultivo_ciclo`) |
| Vista | `cultivo_ciclo` |
| Template | `templates/growlog/ciclo.html` |
| Servicio | `growlog/services/ciclo.py` (`resumen_ciclo`) |
| Acceso | Lector, editor o propietario. |

Muestra:

- Etapa actual y día (de flora si hay inicio de flora, si no desde el inicio del cultivo).
- Línea "Estimado contra real": una pista por fase (Plántula, Veg, Flora, Secado, Curado) con la barra punteada de lo estimado y la barra llena de lo real, y una marca "hoy". La duración real de cada fase sale de los `CambioEtapaCultivo`; la estimada, de `dias_veg_estimados` y `dias_flora_estimados` del cultivo (para Flora, si no está, el máximo de `dias_flora_estimados` de las plantas activas) y, para Secado y Curado, 10 y 21 días orientativos. Las fases sin estimado ni dato real no se dibujan. Si faltan los días estimados, los editores ven un enlace a `cultivo_editar`.
- Un bloque según el estado del cultivo:
  - **Sin flora y no finalizado** (`puede_flip`): "El flip, en un paso" con la etapa actual contra "Flora temprana", el fotoperíodo actual contra 12/12 y el relleno de la red SCROG de la última foto de canopy (se destaca si es 60 % o más). Los editores ven "Hacer el flip hoy", un POST a `cultivo_marcar_flora`.
  - **En flora**: día de flora, cosecha estimada (inicio de flora más días de flora estimados; "faltan N días", "es hoy" o "ya pasó la fecha estimada") y, para editores, "Cosecha y cierre".
  - **Secado, curado o finalizado**: el estado y, para editores, "Seguir con la cosecha" o "Ver la cosecha" (cultivo finalizado), que lleva a `cultivo_cosecha`.
- Etapas: historial de `CambioEtapaCultivo` (más nuevo primero) con "⋯" de corrección para editores y "+ cambiar etapa".
- Fotoperíodo: historial de `CambioFotoperiodo` con el vigente marcado, "⋯" de corrección y "+ cambiar fotoperíodo" para editores.

### Marcar flora (flip)

`POST /cultivo/<slug>/marcar-flora/` (`cultivo_marcar_flora`). Acceso: editor o propietario. Llama a `hacer_flip()`: si el cultivo todavía no tiene `fecha_inicio_flora`, registra la etapa `flora_temprana` desde hoy (nota "Flip") y, si el fotoperíodo vigente no es 12/12, crea o actualiza el cambio de fotoperíodo de hoy a 12/12 con la hora de encendido vigente (06:00 si no había). Si ya había flora, no cambia nada y avisa la fecha de inicio de flora. Redirige a Ciclo.

### Etapa del cultivo

| | |
|---|---|
| URL | `/cultivo/<slug>/etapa/` (`cultivo_etapa`) |
| Template | `templates/growlog/etapa_historial.html` |
| Acceso | Lector (solo ve el historial), editor o propietario. |

Muestra la etapa actual, el día de flora y, para editores, un formulario para cambiar la etapa (etapa, fecha de inicio por defecto hoy, notas). Guardar llama a `cambiar_etapa()`: crea o corrige el registro de esa fecha y recalcula el estado del cultivo y `fecha_inicio_flora` (la primera etapa de flora de todas, que no se reinicia al pasar de flora temprana a tardía). El historial marca la fila vigente como "activo" y da "Editar" y "Eliminar" a los editores.

| URL | Nombre | Acceso |
|---|---|---|
| `/etapa-cultivo/<pk>/editar/` | `cambio_etapa_cultivo_editar` | Editor o propietario |
| `/etapa-cultivo/<pk>/eliminar/` | `cambio_etapa_cultivo_eliminar` | Editor o propietario |

Ambas sincronizan el cultivo después de guardar o borrar.

### Fotoperíodo

| | |
|---|---|
| URL | `/cultivo/<slug>/fotoperiodo/` (`fotoperiodo_list`) |
| Template | `templates/growlog/fotoperiodo.html` |
| Acceso | Editor o propietario (un lector recibe 403). |

Formulario con fotoperíodo (luz/oscuridad), hora de encendido, fecha de inicio (por defecto hoy) y notas, con tres accesos rápidos que completan el formulario: 20/4, 18/6 y 12/12 con encendido a las 06:00. Debajo, la tabla de historial con el fotoperíodo vigente hoy marcado "activo" y los de fecha futura marcados "programado", y "Editar" y "Eliminar" por fila.

| URL | Nombre | Acceso |
|---|---|---|
| `/fotoperiodo/<pk>/editar/` | `cambio_fotoperiodo_editar` | Editor o propietario |
| `/fotoperiodo/<pk>/eliminar/` | `cambio_fotoperiodo_eliminar` | Editor o propietario |

Las tres pantallas redirigen a la lista de fotoperíodo después de guardar o borrar.

## Referencias cruzadas

- Carga de datos y edición de registros: [registrar.md](registrar.md).
- Servicios usados por estas pantallas (`hoy`, `bitacora`, `vpd`, `ciclo`, `plantas`, `fotos`, `etapas`, `onboarding`): [servicios.md](servicios.md).
- Campos de los modelos mencionados: [modelos.md](modelos.md).
- Resto de las pantallas (Canopy, Energía, Reporte, Ajustes, Cosecha, Nutrientes, Cuenta): [pantallas.md](pantallas.md).
- Estilos y componentes: [diseno.md](diseno.md).
