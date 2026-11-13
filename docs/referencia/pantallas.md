# Pantallas generales

Pantallas que no son del trabajo diario de un cultivo: acceso y cuenta, invitaciones, Más, nutrientes, energía, Canopy, actividad, dudas, páginas de error, formularios genéricos, fotos protegidas y PWA. Las pantallas diarias (Hoy, Cultivo, Núcleo, Plantas, Tareas, Aire, Ciclo) están en [pantallas-cultivo.md](pantallas-cultivo.md), Registrar en [registrar.md](registrar.md) y el recorrido de alta a cierre en [ciclo-de-vida.md](ciclo-de-vida.md).

Salvo que se indique otra cosa, las vistas están en `growlog/views/`, los templates en `templates/growlog/` y las rutas en `growlog/urls.py` (espacio de nombres `growlog`). Las vistas con `@login_required` redirigen a `/login/` (`LOGIN_URL`) a quien no tiene sesión. Para el modelo de acceso por cultivo (propietario, editor, lector) ver [permisos.md](permisos.md).

## Índice

| Pantalla | URL | Nombre | Vista | Template |
|---|---|---|---|---|
| Login | `/login/` | `login` | `auth.login_view` | `login.html` |
| Logout | `/logout/` | `logout` | `auth.logout_view` | (sin template) |
| Invitación (aceptar) | `/invitacion/<token>/` | `invitacion_aceptar` | `invitados.invitacion_aceptar` | `invitacion.html` |
| Compartir | `/invitados/` | `invitados_panel` | `invitados.invitados_panel` | `invitados.html` |
| Más | `/mas/` | `mas` | `mas.mas` | `mas.html` |
| Tu cuenta | `/cuenta/` | `cuenta` | `cuenta.cuenta` | `cuenta.html` |
| Nutrientes | `/nutrientes/` | `nutrientes` | `nutrientes.nutrientes` | `nutrientes.html` |
| Energía | `/cultivo/<slug>/energia/` | `energia` | `reportes.cultivo_energia` | `energia.html` |
| Canopy | `/cultivo/<slug>/canopy/` | `canopy` | `canopy.canopy_view` | `canopy.html` |
| Actividad | `/actividad/` | `actividad` | `actividad.actividad` | `actividad.html` |
| Dudas | `/dudas/` | `faq` | `ayuda.faq` | `faq.html` |
| Errores | (handlers) | | `errors.error_400/403/404/500` | `400.html`, `403.html`, `404.html`, `500.html` |
| Fotos | `/media/<path>` | `protected_media` | `media.protected_media` | (archivo) |
| PWA | `/manifest.json`, `/sw.js`, `/push/...` | | `pwa.*` | `pwa/sw.js` |

## Login y logout

### Login

- Ruta: `/login/` (`login_view`, `templates/growlog/login.html`). Página independiente, sin la barra de navegación de la app. Acceso: público.
- Si ya hay sesión, redirige a Hoy (`dashboard`).
- Formulario: `username`, `password` y la casilla "Recordar sesión en este dispositivo" (`remember`, marcada por defecto).
- Con credenciales válidas: se borra el contador de fallos de esa IP, se inicia la sesión y, si la casilla no está marcada, la sesión vence al cerrar el navegador (`set_expiry(0)`). Redirige a `?next=` si es una dirección del mismo host (`url_has_allowed_host_and_scheme`); si no, a Hoy.
- Con credenciales inválidas: muestra "Usuario o contraseña incorrectos." y suma un fallo al contador de la IP.
- Límite de intentos: contador en caché por IP (`login_failures_<ip>`). Con `LOGIN_MAX_ATTEMPTS` (10) fallos, la vista no llama a `authenticate` y responde "Demasiados intentos fallidos. Esperá N minutos antes de reintentar.", con N derivado de `LOGIN_LOCKOUT_SECONDS` (1800 s, 30 minutos). Cada fallo renueva el plazo del contador.
- La IP se toma de `X-Forwarded-For` contando `TRUSTED_PROXY_HOPS` (1 por defecto) entradas desde el final de la lista; sin esa cantidad de entradas se usa `REMOTE_ADDR`.
- Cada ingreso exitoso y cada intento fallido que llega a `authenticate` se registra en la tabla `Ingreso` (ver Actividad). Los intentos bloqueados por el límite no se registran.
- El ingreso al sitio de administración (`/admin/login/`) redirige a este mismo login (`growlog/admin_site.py`, `MaintenanceAdminSite.login`); el admin solo admite usuarios activos con `is_superuser` e `is_staff`.

### Logout

- Ruta: `/logout/`, solo POST (`@require_POST`; un GET devuelve 405). El formulario está en Más.
- Borra la `PushSubscription` del usuario cuyo `endpoint` llega en el campo `push_endpoint` o, si no, el guardado en la sesión (`push_endpoint`). Las suscripciones de otros dispositivos se conservan.
- Cierra la sesión y redirige a `/login/`.

## Invitación y compartir

Un cultivo se comparte con un link de un solo uso. Modelos `Invitacion` y `CultivoMiembro` en [modelos.md](modelos.md).

### Compartir (panel del propietario)

- Ruta: `/invitados/` (`invitados_panel`, `invitados.html`). Acceso: cualquier usuario con sesión; solo ofrece sus propios cultivos. Responde con `Cache-Control: no-store, private`.
- Contenido:
  - Formulario "Invitar": `cultivo` (solo cultivos donde el usuario es propietario), `rol` (Solo lectura o Puede registrar y editar; por defecto editor) y un campo opcional `usuario` dentro de "¿Ya tiene cuenta acá? Sumala directo". Si el usuario no es propietario de ningún cultivo, en lugar del formulario aparece un texto que lo aclara.
  - "Links sin usar": invitaciones del usuario sin usar y no vencidas, con "Ver link" y "Anular".
  - "Quiénes tienen acceso": miembros de sus cultivos, con selector de permiso y botón "Sacar".
- Link generado: `<esquema>://<host>/invitacion/<token>/`, con botones Compartir (Web Share API, si el navegador la tiene) y Copiar. El panel lo muestra con `?nueva=<id>#link`.

| Acción | Ruta (POST) | Nombre | Regla |
|---|---|---|---|
| Crear link o dar acceso | `/invitados/crear/` | `invitado_crear` | Sin `usuario`: crea una `Invitacion` y redirige al panel con el link. Con `usuario`: busca una cuenta activa con ese nombre distinta de la propia; crea o actualiza el `CultivoMiembro` con el rol elegido. Si no existe, devuelve el formulario con status 400 |
| Anular link | `/invitados/link/<id>/anular/` | `invitacion_revocar` | Borra una invitación propia sin usar |
| Cambiar permiso | `/invitados/<id>/rol/` | `invitado_rol` | Solo sobre miembros de cultivos propios; un rol fuera de `lector` y `editor` devuelve 400 |
| Sacar acceso | `/invitados/<id>/eliminar/` | `invitado_eliminar` | Borra la membresía; la cuenta y sus registros se conservan |

### Aceptar una invitación

- Ruta: `/invitacion/<token>/` (`invitacion_aceptar`, `invitacion.html`). Página independiente. Acceso: público. Sin caché.
- Una invitación sirve una vez y vence a los 7 días (`Invitacion.DIAS_VIGENCIA`). Un token inexistente, usado o vencido muestra "Este link ya no sirve" con status 410 y un botón a Entrar; el texto distingue "Ya se usó", "Venció" y "No existe o lo anularon".
- Con link válido, la pantalla muestra quién invita, el nombre del cultivo y qué podrá hacer según el rol (ver y registrar, o solo ver).
  - Con sesión iniciada: si el usuario es el propietario del cultivo, redirige al cultivo con un mensaje. Si no, un botón "Sumarme como <usuario>" (POST) lo agrega.
  - Sin sesión: formulario `CuentaInvitadoForm` (usuario, contraseña y repetición) que crea la cuenta, la agrega al cultivo, inicia sesión y redirige al cultivo. Debajo, un enlace a `/login/?next=<link>` para quien ya tiene cuenta.
- Al usar la invitación (`_usar`): se crea el `CultivoMiembro` con el rol de la invitación. Si la persona ya era miembro y la invitación es de editor, sube a editor; un link nunca baja un rol existente. La invitación queda con `usada_por` y `usada_en`.

## Más

- Ruta: `/mas/` (`mas`, `mas.html`). Acceso: cualquier usuario con sesión.
- Grupo del cultivo (si hay uno): nombre del cultivo y enlaces a sus secciones, sin Resumen. Se muestran Bitácora, Tareas, Aire, Ciclo, Canopy, Energía, Reporte y, solo si el usuario puede editar el cultivo, Ajustes. El cultivo es el abierto, el último abierto en la sesión o el primero activo (`cultivo_destino`).
- Grupo General: Nuevo cultivo, Tareas de todos los cultivos, Nutrientes, Compartir cultivos (solo si el usuario es propietario de algún cultivo activo o del historial), Dudas de cultivo y, solo para superusuarios, Actividad y Admin (`/admin/`).
- Preferencias:
  - "Tu cuenta y avisos": enlace a Cuenta.
  - Tema: selector Auto, Claro, Oscuro. Se guarda en este dispositivo (`localStorage.tema`); Auto sigue la preferencia del sistema.
  - Avisos: interruptor (rótulo "Avisos de pendientes") de notificaciones push de este dispositivo. La fila solo se muestra si hay clave VAPID configurada y el navegador admite service worker y push. Al activar pide permiso al navegador, suscribe el dispositivo y lo registra en `/push/subscribe/`; al desactivar lo da de baja en `/push/unsubscribe/`. Si el navegador tiene las notificaciones bloqueadas, lo informa en el estado.
- Botón Salir: formulario POST a `/logout/`, con el `endpoint` de este dispositivo.

## Tu cuenta

- Ruta: `/cuenta/` (`cuenta`, `cuenta.html`). Acceso: cualquier usuario con sesión.
- Dos formularios en la misma página, distinguidos por el campo `accion`:

| Formulario | Campos | Efecto |
|---|---|---|
| `preferencias` | `nombre` (guardado en `first_name`), `unidad_ec` (µS/cm, mS/cm o "Como el medidor (×10 µS/cm)"), `avisar_ambiente`, `avisar_tareas`, `avisar_seguimientos`, `hora_avisos` (00:00 a 23:00) | Guarda el `Perfil` (se crea al primer uso con `perfil_de`) y el nombre. Redirige a Cuenta |
| `clave` | Contraseña actual, nueva y repetición (`PasswordChangeForm`, con los validadores de contraseña del proyecto) | Cambia la contraseña y mantiene la sesión abierta |

- `unidad_ec` determina cómo se muestra la EC en toda la app; al cargar un valor se sigue tipeando lo que marca el medidor (ver [registrar.md](registrar.md)).
- Los avisos los envía el comando `send_recordatorios` (`growlog/management/commands/send_recordatorios.py`) a las suscripciones push del propietario y de los editores de cada cultivo no archivado ni finalizado. Cada persona recibe solo lo que activó: ambiente del día sin registrar, seguimientos de eventos vencidos o de hoy, y tareas vencidas o de hoy. Con `--hora-actual` se envía solo a quienes eligieron la hora en curso; sin perfil, se avisa todo a las 20.

## Nutrientes

- Rutas: `/nutrientes/` (lista), `/nutrientes/nuevo/`, `/nutrientes/<id>/editar/`, `/nutrientes/<id>/ocultar/` (POST), `/nutrientes/<id>/eliminar/` (POST). Vistas en `views/nutrientes.py`; la lista usa `nutrientes.html` y `partials/nutriente_item.html`; el alta y la edición usan `crud_form.html`. Acceso: cualquier usuario con sesión.
- Qué muestra la lista:
  - "Mis nutrientes": los de `propietario = usuario`, incluidos los ocultos.
  - "Catálogo compartido": los de `propietario = None`. Un superusuario ve también los ocultos.
  - "De cultivos compartidos con vos": nutrientes visibles de los propietarios de los cultivos a los que el usuario tiene acceso (`permissions.nutrientes_visibles`), solo lectura y con el nombre del dueño.
  - Cada fila muestra marca y nombre, etapa recomendada, NPK, rango de dosis con su unidad (g/L o ml/L) y, si está oculto, el aviso "oculto".
- Formulario (`NutrienteForm`): `nombre`, `marca`, `npk`, `etapa_recomendada` (Vegetativo, Floración, Aditivo), `unidad` (g/L o ml/L; sin elegir queda en g/L), `dosis_recomendada_min` y `dosis_recomendada_max` (la mínima no puede superar a la máxima). Para superusuarios se agrega la casilla `compartido` ("Compartido con todos"), que deja el nutriente sin propietario.
- Propiedad: un nutriente nuevo queda a nombre del usuario; con `compartido` marcado queda sin propietario (catálogo compartido). Los nutrientes propios los edita su dueño; los compartidos, solo un superusuario. Cualquier otro intento da 404.
- Acciones:
  - Ocultar o mostrar (`nutriente_ocultar`): alterna `oculto`. Un nutriente oculto deja de ofrecerse al registrar, pero los riegos ya guardados lo conservan.
  - Eliminar (`nutriente_eliminar`): si el nutriente se usó en algún riego, no se borra y el mensaje indica ocultarlo. La lista solo ofrece "Eliminar" en los que no tienen usos.
- Qué nutrientes se ofrecen al registrar un riego en un cultivo (`permissions.nutrientes_para`): los no ocultos que son compartidos, del usuario o del propietario del cultivo.

## Energía

- Ruta: `/cultivo/<slug>/energia/` (`cultivo_energia`, `energia.html`, `services/energia.py`). Acceso: GET para cualquiera con acceso al cultivo; todas las acciones POST exigen permiso de edición, salvo que la tarifa solo la carga el propietario.
- Modelos (ver [modelos.md](modelos.md)): `Equipo` (nombre, watts, horas por día, categoría: Lámpara, Extractor, Ventilador, Humidificador, Otro; con propietario), `TarifaElectrica` (fecha desde, precio por kWh, distribuidora; con propietario), `CostoEnergetico` (asignación de un equipo a un cultivo con fecha desde, fecha hasta opcional y la tarifa vigente al asignarlo) y `LecturaMedidor` (fecha, kWh reales, notas).
- Qué se muestra:
  - Encabezado con el ciclo de luz activo (`ciclo_activo`: el fotoperíodo vigente; sin fotoperíodos, 12/12 si el estado es floración y hay plantas fotoperiódicas activas, y 18/6 en otro caso).
  - Cifras: kWh por mes y costo mensual de los equipos activos; kWh acumulados y costo estimado desde el inicio del cultivo; kWh y costo según el medidor, con la variación contra lo estimado (solo si hay lecturas); y la tarifa vigente (la más reciente con fecha menor o igual a hoy, de las tarifas del propietario o ya usadas por equipos del cultivo).
  - Aviso en pantalla si el medidor marca más de 15 % por encima de lo estimado.
  - Lista de equipos activos, lista de lecturas del medidor y tabla "Mes por mes" (mes, días, kWh y costo).
- Estimación (`calcular_meses`): para cada mes desde el inicio del cultivo hasta hoy, suma `watts / 1000 * horas_dia * días` de cada equipo asignado que estuvo activo en ese tramo, y multiplica por la tarifa vigente al primer día de ese mes. Los equipos retirados siguen contando por los días en que estuvieron asignados.
- Acciones (POST al mismo URL, campo `accion`; al terminar redirige a Energía con un mensaje de éxito o de error):

| `accion` | Quién | Campos | Reglas |
|---|---|---|---|
| `lectura` | Propietario o editor | `fecha`, `kwh_real`, `notas` | Fecha válida y no futura; kWh entre 0 y 99.999.999 (acepta coma); notas hasta 500 caracteres |
| `lectura_editar` | Propietario o editor | `pk`, más los de `lectura` | Corrige una lectura de este cultivo |
| `lectura_borrar` | Propietario o editor | `pk` | Borra una lectura de este cultivo |
| `tarifa` | Solo el propietario del cultivo | `precio_kwh`, `fecha_desde`, `distribuidora` | Precio mayor que 0 y hasta 999.999; fecha hasta 366 días en el futuro; distribuidora hasta 100 caracteres ("Sin especificar" si queda vacía). Crea una tarifa nueva a nombre del usuario; las anteriores no se modifican |
| `equipo` | Propietario o editor | `equipo` (uno existente) o `nombre`, `categoria`, `watts`, `horas_dia`; `fecha_desde` | Requiere una tarifa vigente: la más reciente se guarda en la asignación. Un equipo existente debe ser del usuario o ya estar asignado a este cultivo. Uno nuevo exige nombre (hasta 120), watts mayores que 0 (hasta 100.000) y horas por día entre 0 y 24; la categoría inválida pasa a Otro. La fecha no puede ser futura |
| `equipo_editar` | Propietario o editor | `pk`, `watts`, `horas_dia` | Modifica el `Equipo` de esa asignación (el cambio vale para todos los cultivos que lo usan) |
| `equipo_quitar` | Propietario o editor | `pk` | Pone `fecha_hasta = max(hoy, fecha_desde)` en una asignación vigente. Lo consumido hasta entonces sigue en la cuenta |

- Quien solo lee no ve formularios ni botones de edición. El formulario de tarifa se muestra únicamente al propietario. Sin tarifa, no se ofrece sumar equipos.
- El reporte de cierre usa esta información para el costo por gramo (ver [ciclo-de-vida.md](ciclo-de-vida.md)). La API expone los mismos datos en [api.md](api.md).

## Canopy

- Ruta: `/cultivo/<slug>/canopy/` (`canopy_view`, `canopy.html`). Acceso: lectura para cualquiera con acceso al cultivo; guardar exige permiso de edición. Carga Alpine.js desde jsDelivr (`alpinejs@3.14.9`) y la configuración inicial como JSON embebido (`json_script`).
- Datos (`CanopySnapshot` y `ColaPosicion`, ver [modelos.md](modelos.md)): cada guardado crea un snapshot nuevo con porcentaje de llenado de la red SCROG, lista de celdas llenas (`scrog_cells`, índices 0 a 35), notas y una `ColaPosicion` por cola (planta, índice, `x` e `y` entre 0 y 1). Los snapshots no se editan ni se borran desde la pantalla.
- Qué muestra:
  - Mapa de la carpa (SVG de 400 por 400): grilla de 6 por 6 cuadros (la red SCROG), un círculo por planta no archivada y sus colas numeradas. Los rótulos indican fondo (arriba), puerta (abajo), izquierda y derecha.
  - Posición de cada planta: según su campo `posicion_tent` (centro y cuatro esquinas). Las que no tienen posición o están en "otro" se reparten en una grilla; las que comparten posición se separan un poco.
  - Colas: se toman del último snapshot; una planta sin colas guardadas empieza con 2.
  - Selector de snapshots (cuando hay alguno): carga el snapshot elegido desde `/cultivo/<slug>/canopy/snapshot/<id>/json/` (`canopy_snapshot_json`, GET, devuelve JSON).
  - Colas por planta (de 1 a 10, con botones más y menos), red SCROG llena (porcentaje y cuadros llenos de 36, control deslizante de 5 en 5 que llena en bloque, botones Vaciar y Llenar) y notas del snapshot.
  - Cifras: cantidad de colas, W por cola (`lampara_watts_reales` dividido por las colas), colas por m² (área de `carpa_dimensiones` leída como ancho por largo en cm) y estado del flip.
  - Diagnóstico por W por cola: menos de 20 "Demasiadas colas"; hasta 25 "En el límite"; hasta 45 "Bien repartida"; más de 45 "Sobra luz". Sin lámpara cargada indica "Sin lámpara cargada"; sin colas, "Sin colas".
  - Estado del flip por llenado de la red: menos de 60 %, aún no; de 60 a 80 %, "listo"; más de 80 %, "pasado".
- Edición (solo con permiso de edición): arrastrar cada cola, tocar cuadros de la red, sumar o quitar colas y el botón "Guardar snapshot". Sin permiso, el mapa es de solo lectura.
- Guardado: `/cultivo/<slug>/canopy/guardar/` (`canopy_guardar`, POST con JSON, exige edición). Cuerpo: `scrog_fill_pct`, `scrog_cells`, `notas` (hasta 500 caracteres) y `colas` (`planta_uuid`, `indice`, `x`, `y`). Valida que cada `planta_uuid` sea de una planta no archivada del cultivo, que `indice` esté entre 0 y 32767, que `x` e `y` estén en [0, 1] y que no haya colas repetidas por planta. Si llegan celdas, el porcentaje se recalcula como `celdas / 36` y se descartan índices fuera de 0 a 35. Responde 201 con `{ok, data}` o 400 con `{ok: false, error}`.
- El porcentaje del último snapshot aparece en la pantalla Ciclo junto al flip, y la API expone los snapshots (ver [api.md](api.md)).

## Actividad

- Ruta: `/actividad/` (`actividad`, `actividad.html`, `static/growlog/actividad.css`). Acceso: solo superusuarios; cualquier otro usuario recibe 404. Se enlaza desde Más.
- Datos (`services/actividad.resumen_actividad`):
  - Por cada usuario activo: último ingreso exitoso (con dispositivo), último registro, registros de los últimos 7 y 30 días y un indicador de actividad (registró algo o ingresó en los últimos 7 días). Si no hay ingresos en la tabla, usa `last_login` de Django.
  - "Registros" son los de mediciones de ambiente, riegos, mediciones de EC y pH, eventos (observaciones) y mediciones de planta con `creado_por`, contados por la fecha en que se observó, no por cuándo se cargaron. Tareas y plantas no cuentan.
  - Últimos movimientos: hasta 25, ordenados por momento, con usuario, tipo de movimiento, cultivo y fecha. No incluye momentos futuros.
  - Ingresos recientes: los últimos 20 de la tabla `Ingreso`, con el nombre usado, resultado, dispositivo y fecha. Más el total de ingresos fallidos en 30 días.
- Tabla `Ingreso` (`models.Ingreso`): `usuario` (vacío en un fallo), `nombre_usado`, `exito`, `dispositivo` y `creado_en`. Se escribe por señales de `growlog/signals.py` al iniciar sesión y al fallar una autenticación. El dispositivo se guarda en forma corta, por ejemplo "iPhone · Safari", derivado del User-Agent; no se guarda la IP. En cada ingreso exitoso se borran los registros de más de 90 días.

## Dudas

- Ruta: `/dudas/` (`faq`, `faq.html`, `static/growlog/faq.css`). Acceso: cualquier usuario con sesión. Contenido estático, sin datos de la base.
- Estructura: buscador de texto, índice de temas y preguntas desplegables (`<details>`). Temas: pH y EC, Riego, Ambiente y VPD, Luz y ciclo, Nutrición en tierra, Plagas y hongos, Entrenamiento, Cosecha secado y curado, y Recomendaciones para empezar. La sección de VPD incluye la fórmula usada por la app. Si el buscador no encuentra coincidencias, muestra un mensaje.

## Páginas de error

`config/urls.py` registra los handlers de `growlog/views/errors.py`.

| Código | Handler | Template | Título | Cuándo aparece |
|---|---|---|---|---|
| 400 | `error_400` | `400.html` | "No se entendió el pedido" | Pedido mal formado (por ejemplo una `SuspiciousOperation`) |
| 403 | `error_403` | `403.html` | "Esto no lo podés ver o cambiar" | `PermissionDenied`: un lector que intenta editar, o archivar sin ser propietario |
| 404 | `error_404` | `404.html` | "Acá no hay nada" | Rutas inexistentes, cultivos u objetos sin acceso, y Actividad para no superusuarios |
| 500 | `error_500` | `500.html` | "Algo se rompió de nuestro lado" | Error interno |

- 400, 403 y 404 extienden `error_base.html` (que extiende `base.html`): muestran el código, un título, un texto y dos botones, "Ir a Hoy" y "Volver" (historial del navegador).
- 500 es una página independiente (sin `base.html`) que solo carga los estilos y ofrece "Ir a Hoy".
- La respuesta de `invitacion_aceptar` con un link inválido no usa estas páginas: devuelve 410 con `invitacion.html`.

## Formularios genéricos: `crud_form.html` y `crud_delete.html`

Plantillas reutilizadas para editar y confirmar borrados. Ocultan las pestañas del cultivo y reemplazan la barra inferior del celular por un único "Volver" hacia `back_url`.

### `crud_form.html`

Variables de contexto: `form`, `title`, `subtitle` (opcional), `back_url`, `delete_url` (opcional, agrega el enlace "Eliminar") y `submit_label` (por defecto "Guardar"). Dibuja cada campo del formulario con su etiqueta, error y ayuda; los campos con la clase `field-narrow` van de a varios por fila y las casillas (`form-check-input`) ocupan una fila propia. Botones: Guardar y Cancelar.

### `crud_delete.html`

Variables: `title`, `object_name`, `back_url`, `warn` (por defecto "No se puede deshacer."), `confirm_label` (por defecto "Eliminar") y `confirm_seguro` (si es verdadero el botón de confirmación no usa el estilo destructivo; se usa para archivar). El botón confirma por POST al mismo URL.

### Dónde se usan

| Vista | Archivo | Template | Uso |
|---|---|---|---|
| `cultivo_editar` | `views/cultivos.py` | `crud_form` | Datos del cultivo |
| `cambio_etapa_cultivo_editar` | `views/cultivos.py` | `crud_form` | Corregir una etapa del cultivo (con enlace a eliminar) |
| `cambio_etapa_cultivo_eliminar` | `views/cultivos.py` | `crud_delete` | Eliminar una etapa del cultivo |
| `cambio_fotoperiodo_editar` | `views/mediciones.py` | `crud_form` | Corregir un fotoperíodo |
| `cambio_fotoperiodo_eliminar` | `views/mediciones.py` | `crud_delete` | Eliminar un fotoperíodo |
| `planta_editar` | `views/plantas.py` | `crud_form` | Editar una planta (incluye estado, archivada y datos de cosecha) |
| `planta_eliminar` | `views/plantas.py` | `crud_delete` | Eliminar una planta sin historial, o archivar una con historial (`confirm_seguro`) |
| `cambio_etapa_planta_editar` | `views/plantas.py` | `crud_form` | Corregir la etapa propia de una planta |
| `cambio_etapa_planta_eliminar` | `views/plantas.py` | `crud_delete` | Eliminar la etapa propia de una planta |
| `nutriente_crear`, `nutriente_editar` | `views/nutrientes.py` | `crud_form` | Alta y edición de nutrientes |

Las correcciones de riegos, ambiente, EC y pH, eventos, tareas y mediciones de planta usan la pantalla de edición de Registrar (`registro_editar.html`), descrita en [registrar.md](registrar.md).

## Fotos protegidas

- Ruta: `/media/<path>` (`media.protected_media`, nombre `protected_media`), registrada en `config/urls.py`. Acceso: con sesión.
- Sirve solo las fotos de mediciones de planta: busca una `MedicionPlanta` cuya `foto` o `foto_mini` coincida con la ruta y cuya planta pertenezca a un cultivo visible para el usuario (`cultivos_visibles`). Si no hay coincidencia o el archivo no existe en el almacenamiento, responde 404. No expone otros archivos de `MEDIA_ROOT`.
- Cabeceras: las miniaturas salen con `Cache-Control: private, max-age=86400`; la foto completa, con `no-store, private`.
- Almacenamiento: archivos en `MEDIA_ROOT` (`media/`) por defecto; si la variable `R2_BUCKET` está definida, el almacenamiento por defecto es `PrivateMediaStorage` (Cloudflare R2), cuyas URLs apuntan siempre a esta ruta protegida.
- Subir fotos requiere el permiso `growlog.subir_fotos` o la opción `PERMITIR_FOTOS_A_TODOS` (ver [permisos.md](permisos.md)). Al borrar o reemplazar una medición de planta, `signals.py` borra los archivos huérfanos una vez confirmada la transacción.

## PWA y notificaciones push

Vistas en `views/pwa.py`, templates `pwa/sw.js` y `partials/pwa_head.html`.

| Ruta | Vista | Método y acceso | Qué hace |
|---|---|---|---|
| `/manifest.json` | `pwa_manifest` | GET, público | Manifiesto de la app: nombre "62×ROOTS GrowLog", `start_url` y `scope` `/`, `display: standalone`, idioma `es-AR`, color de tema `#15110d`, íconos de 192 y 512 px (comunes y "maskable") y accesos directos a Registrar y Hoy. Tipo `application/manifest+json` |
| `/sw.js` | `pwa_service_worker` | GET, público | Service worker con `Service-Worker-Allowed: /` y `Cache-Control: no-cache` |
| `/push/subscribe/` | `push_subscribe` | POST con JSON, con sesión | Guarda la suscripción (`endpoint`, `keys.p256dh`, `keys.auth`). Un `endpoint` ya registrado por otra cuenta devuelve 409; si ya es del usuario, actualiza las claves. Guarda el `endpoint` en la sesión. JSON inválido o incompleto devuelve 400 |
| `/push/unsubscribe/` | `push_unsubscribe` | POST con JSON, con sesión | Borra la suscripción de ese `endpoint` del usuario |

- Service worker: no guarda páginas ni archivos en caché. Al instalarse llama a `skipWaiting`; al activarse borra las cachés cuyo nombre empieza con `62xroots-` y toma control de las pestañas. Al recibir un push muestra una notificación con título, texto e ícono (`icon-192x192.png`, insignia `badge-96x96.png`); al tocarla enfoca una ventana abierta de la app en la dirección indicada, o abre una nueva.
- `partials/pwa_head.html` (manifiesto, íconos, metas para iOS y registro del service worker) se incluye en `base.html`, `login.html` e `invitacion.html`.
- Envío: `growlog/push.py` (`send_push_to_users`) envía por Web Push con las claves VAPID de la configuración, solo a cuentas activas, y borra las suscripciones que el servicio de push informa como vencidas (404 o 410). Sin `VAPID_PRIVATE_KEY` no envía. Los avisos programados salen de `send_recordatorios` (ver Tu cuenta).
