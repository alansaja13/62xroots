# Permisos

Roles y reglas de acceso de la app: cómo se resuelve el acceso a un cultivo, qué puede hacer cada rol, recursos que no pertenecen a un cultivo, permiso de fotos, invitaciones, autenticación con límite de intentos y pantalla de cuenta. El detalle de la política por cultivo está en [../acceso-por-cultivo.md](../acceso-por-cultivo.md); la configuración general, en [arquitectura.md](arquitectura.md).

## Roles

| Rol | Cómo se obtiene | Alcance |
| --- | --- | --- |
| Propietario | Es `Cultivo.propietario`. Se asigna al usuario que crea el cultivo (`nuevo_cultivo`) | Ve y edita el cultivo y administra quién accede |
| Editor | Fila `CultivoMiembro` con `rol="editor"` ("Puede registrar y editar") | Ve y edita el cultivo |
| Lector | Fila `CultivoMiembro` con `rol="lector"` ("Solo lectura") | Solo ve el cultivo |
| Sin acceso | Cualquier otro usuario autenticado | El cultivo no existe para él (404) |
| Superusuario / staff | `is_superuser`, `is_staff` | No dan acceso a ningún cultivo ajeno. Un superusuario con `is_staff` y activo entra al admin de Django; un superusuario administra además los nutrientes compartidos |

Cualquier usuario activo y autenticado puede crear cultivos propios. Un usuario inactivo (`is_active=False`) no ve ningún cultivo ni puede editar.

`CultivoMiembro` tiene los campos `cultivo`, `usuario`, `rol` (por defecto `lector`) y `creado_en`, y una restricción de unicidad por par cultivo/usuario. Ver [modelos.md](modelos.md).

## Cómo se resuelve el acceso (`growlog/permissions.py`)

| Función | Qué hace |
| --- | --- |
| `cultivos_visibles(usuario, editar=False)` | Cultivos donde el usuario es propietario o miembro. Con `editar=True`, propietario o miembro con rol `editor`. Devuelve vacío si el usuario no está autenticado o no está activo |
| `puede_editar(usuario, cultivo)` | `True` si es el propietario o tiene membresía `editor`; `False` si no está autenticado o activo |
| `exigir_edicion(usuario, cultivo)` | Lanza `PermissionDenied` ("Tenés acceso de solo lectura a este cultivo.") si no puede editar |
| `objeto_del_cultivo(request, model, editar=False, **lookup)` | Busca el objeto solo entre los de cultivos visibles (404 si no está), resuelve su cultivo, exige edición si `editar=True` o si el método HTTP no es GET, HEAD ni OPTIONS, y fija `request.cultivo_actual` y `request.puede_editar_cultivo` |
| `puede_subir_fotos(usuario)` | Ver la sección de fotos |
| `nutrientes_para(usuario, cultivo)` | Nutrientes que se ofrecen al registrar en un cultivo |
| `nutrientes_visibles(usuario)` | Catálogo que ve un usuario |
| `recursos_visibles(model, usuario, editar=False)` | Equipos y tarifas visibles o editables |
| `tarifas_del_cultivo(cultivo)` | Tarifas del propietario del cultivo y las ya usadas por los costos del cultivo |
| `equipos_asignables(usuario, cultivo)` | Equipos propios del usuario o ya vinculados al cultivo |

`objeto_del_cultivo` obtiene el cultivo de cada modelo con la tabla `RELACION_CULTIVO`:

| Modelo | Relación hacia el cultivo |
| --- | --- |
| `Cultivo` | (el propio objeto) |
| `Planta`, `Tarea`, `Evento`, `Riego`, `MedicionEC`, `MedicionAmbiente`, `CambioFotoperiodo`, `CanopySnapshot`, `CambioEtapaCultivo` | `cultivo` |
| `NutrienteAplicado`, `RiegoPlanta` | `riego__cultivo` |
| `MedicionPlanta`, `CambioEtapaPlanta` | `planta__cultivo` |

El cultivo se resuelve siempre por esa relación y no por el autor del registro, que puede ser un colaborador.

Códigos de respuesta: un recurso de un cultivo no visible devuelve 404; un lector que intenta escribir recibe 403 (`PermissionDenied`, renderizado por `error_403`).

## Qué puede hacer cada rol

| Operación | Propietario | Editor | Lector |
| --- | --- | --- | --- |
| Ver bitácora, plantas, fotos, reportes, energía y canopy del cultivo | Sí | Sí | Sí |
| Registrar, corregir y borrar registros, tareas, plantas, etapas, fotoperíodo, cosecha | Sí | Sí | No |
| Abrir `cultivo_ajustes` (usa `objeto_del_cultivo` con `editar=True`) | Sí | Sí | No |
| Ver la pestaña Ajustes en el menú del cultivo | Sí | Sí | No |
| Archivar o desarchivar el cultivo | Sí | No (403) | No |
| Cargar una tarifa de energía en el cultivo (acción `tarifa` de la pantalla de energía) | Sí | No | No |
| Compartir, cambiar el permiso o revocar accesos | Sí | No | No |
| Recibir recordatorios push de pendientes (`send_recordatorios`) | Sí | Sí | No |
| Recibir las fotos servidas por `protected_media` | Sí | Sí | Sí |

Las vistas web y la API aplican la misma política. La API ([api.md](api.md)) autentica por Bearer token, resuelve el cultivo por `slug` o la planta por `planta_uuid` entre los cultivos visibles del dueño del token (404 si no está), y rechaza escrituras de un lector con 403. Un token de un usuario inactivo responde 401. Las escrituras de la API tienen un límite de 60 por hora por token (429 al superarlo), guardado en la caché.

La navegación expone el rol a las plantillas: `can_edit_cultivo` (puede editar el cultivo abierto) y `can_manage_cultivo` (es su propietario). Ver [arquitectura.md](arquitectura.md).

## Recursos que no pertenecen a un cultivo

### Nutrientes

`Nutriente.propietario` vacío significa catálogo compartido; con valor, es privado de ese usuario. `Nutriente.oculto` los saca de las ofertas sin borrarlos.

| Consulta | Resultado |
| --- | --- |
| `nutrientes_para(usuario, cultivo)` | No ocultos, y compartidos, propios del usuario o del propietario del cultivo. Es lo que ofrecen Registrar, la API y los formularios de riego |
| `nutrientes_visibles(usuario)` | No ocultos, y compartidos, propios o de propietarios de cultivos visibles para el usuario |

Pantalla `/nutrientes/` (`views/nutrientes.py`, requiere sesión):

- Lista los nutrientes propios, los compartidos y los de propietarios de cultivos compartidos con el usuario. Los compartidos ocultos solo los ve un superusuario.
- Crear: cualquier usuario crea nutrientes propios. Solo un superusuario ve la opción "compartido" y puede crear o convertir un nutriente en compartido.
- Editar, ocultar y eliminar: solo el propietario del nutriente; los compartidos, solo un superusuario. Cualquier otro caso devuelve 404.
- Eliminar un nutriente que ya se usó en riegos (`NutrienteAplicado`) no se hace: se informa y se sugiere ocultarlo.

### Equipos y tarifas eléctricas

`Equipo.propietario` y `TarifaElectrica.propietario` identifican al dueño. `recursos_visibles` devuelve:

- Para lectura: los propios más los vinculados por costos (`CostoEnergetico`) a un cultivo visible para el usuario.
- Con `editar=True`: solo los propios.

Compartir un cultivo no comparte el resto del inventario del propietario. `equipos_asignables(usuario, cultivo)` limita los equipos que se pueden asignar a un cultivo a los propios del usuario o los que ya tiene vinculados ese cultivo. `tarifas_del_cultivo(cultivo)` devuelve las tarifas del propietario del cultivo y las que ya usan sus costos; la usan la pantalla de energía, el reporte y la API. Las tarifas nuevas desde la pantalla de energía quedan a nombre del usuario que las carga, y solo el propietario del cultivo puede cargarlas. Detalle en [../acceso-por-cultivo.md](../acceso-por-cultivo.md).

### Parámetros ideales

`ParametroIdeal` es una tabla de referencia común. Se mantiene desde el admin.

## Fotos

Hay dos controles distintos:

| Control | Dónde | Regla |
| --- | --- | --- |
| Subir fotos | `puede_subir_fotos(usuario)` en `permissions.py` | `True` si el usuario está activo y (`settings.PERMITIR_FOTOS_A_TODOS` es verdadero o `usuario.has_perm("growlog.subir_fotos")`). El permiso `growlog.subir_fotos` lo declara `MedicionPlanta.Meta.permissions` ("Puede subir fotos aunque estén deshabilitadas para todos"); un superusuario lo tiene por serlo. Se asigna desde el admin |
| Ver fotos | `protected_media` en `views/media.py` | Exige sesión y que la foto (o su miniatura) pertenezca a una `MedicionPlanta` de una planta de un cultivo visible para el usuario; si no, 404. No sirve ningún otro archivo del storage |

`puede_subir_fotos` se usa en `services/registro.py` (parámetro `permitir_foto` del formulario de medición de planta, al crear y al editar) y en `views/registrar.py` (el valor `fotos` del contexto). Ver [registrar.md](registrar.md).

## Invitaciones y miembros

Código en `growlog/views/invitados.py`; formularios `CompartirCultivoForm` y `CuentaInvitadoForm` en `growlog/forms.py`; modelos `Invitacion` y `CultivoMiembro` en `growlog/models.py`.

### Modelo `Invitacion`

| Campo | Descripción |
| --- | --- |
| `token` | `secrets.token_urlsafe(24)`, único, no editable |
| `cultivo` | Cultivo al que da acceso |
| `rol` | `lector` o `editor` (por defecto `editor`) |
| `creada_por` | Usuario que la creó |
| `creada` | Fecha de creación |
| `vence` | Creación más 7 días (`DIAS_VIGENCIA`) |
| `usada_por`, `usada_en` | Quién la usó y cuándo; vacíos mientras no se use |

La propiedad `vigente` es verdadera si no fue usada y `vence` es futuro.

### Rutas

| Ruta | Vista | Quién | Comportamiento |
| --- | --- | --- | --- |
| `/invitados/` | `invitados_panel` | Usuario con sesión | Panel con el formulario de compartir, los miembros de los cultivos propios (con rol, ordenados por cultivo y usuario) y los links pendientes (propios, no usados y no vencidos). Respuesta sin caché |
| `/invitados/crear/` | `invitado_crear` | Usuario con sesión, POST | Formulario `CompartirCultivoForm`: cultivo (solo propios), permiso (por defecto editor) y usuario opcional. Sin usuario: crea una `Invitacion` y vuelve al panel mostrando el link nuevo. Con usuario: busca una cuenta activa con ese nombre distinta de la propia y crea o actualiza su `CultivoMiembro` con el rol elegido; si no existe, error 400 en el formulario |
| `/invitados/link/<pk>/anular/` | `invitacion_revocar` | Quien la creó, POST | Borra la invitación si no fue usada |
| `/invitados/<pk>/rol/` | `invitado_rol` | Propietario del cultivo, POST | Cambia el rol del miembro a `lector` o `editor`; otro valor responde 400 |
| `/invitados/<pk>/eliminar/` | `invitado_eliminar` | Propietario del cultivo, POST | Borra la membresía; la cuenta y sus registros se conservan |
| `/invitacion/<token>/` | `invitacion_aceptar` | Público | Ver abajo |

Las operaciones de miembros y links buscan por `cultivo__propietario=request.user` o `creada_por=request.user`; sobre algo ajeno devuelven 404.

### Aceptar una invitación

`/invitacion/<token>/` no exige sesión. Si el token no existe, ya se usó o venció, responde 410 con la página de invitación inválida. Si es válida:

- Con sesión iniciada: si el usuario es el propietario del cultivo, avisa y redirige al cultivo. Si no, un POST lo suma como miembro y redirige al cultivo.
- Sin sesión: muestra `CuentaInvitadoForm` (usuario y contraseña con confirmación, basado en `UserCreationForm`). Un POST válido crea la cuenta, la suma como miembro, la marca como usada, inicia sesión con `ModelBackend` y redirige al cultivo.

Al usar el link, la membresía se crea con el rol de la invitación. Si el usuario ya era miembro, no se le baja el rol; si ya era lector y la invitación es de editor, pasa a editor. La invitación queda con `usada_por` y `usada_en`. Cada link sirve una vez.

El panel también acepta dar acceso directo a una cuenta existente (campo "usuario" del formulario) sin pasar por un link.

## Autenticación y login

Código en `growlog/views/auth.py`. La app usa el backend de autenticación por defecto de Django.

### Login (`/login/`)

- Si el usuario ya tiene sesión, redirige a `dashboard`.
- Solo en POST: calcula la IP del cliente con `_get_client_ip` y usa la caché con la clave `login_failures_<ip>`.
- Si los fallos acumulados alcanzan `LOGIN_MAX_ATTEMPTS` (10), no intenta autenticar y muestra "Demasiados intentos fallidos. Esperá N minutos antes de reintentar." con N = `LOGIN_LOCKOUT_SECONDS // 60` (30).
- Con credenciales correctas: borra el contador de la IP, inicia sesión y redirige a `next` si es una URL del mismo host (`url_has_allowed_host_and_scheme`), o a `dashboard`. Si el formulario no trae el campo `remember`, la sesión expira al cerrar el navegador (`set_expiry(0)`).
- Con credenciales incorrectas: incrementa el contador (con vencimiento de `LOGIN_LOCKOUT_SECONDS`, que se renueva en cada fallo) y muestra "Usuario o contraseña incorrectos."
- `_get_client_ip` toma la entrada de `X-Forwarded-For` ubicada `TRUSTED_PROXY_HOPS` posiciones desde el final de la lista (las entradas a la izquierda las puede escribir el cliente); si hay menos entradas que proxies, o no hay header, usa `REMOTE_ADDR`.

### Logout (`/logout/`)

Solo POST. Borra la suscripción push del navegador (endpoint recibido por POST o guardado en sesión) y cierra la sesión; redirige a `login`.

### Registro de ingresos (modelo `Ingreso`)

Las señales de `growlog/signals.py` registran cada intento ([arquitectura.md](arquitectura.md)):

| Campo | Descripción |
| --- | --- |
| `usuario` | Usuario, vacío en los intentos fallidos |
| `nombre_usado` | Nombre de usuario ingresado (hasta 150 caracteres) |
| `exito` | Éxito o fallo |
| `dispositivo` | Sistema y navegador deducidos del User-Agent; no se guarda la IP |
| `creado_en` | Fecha y hora |

Al registrar un ingreso exitoso se borran los de más de 90 días. En el admin, `Ingreso` es de solo lectura (no se puede agregar ni cambiar).

### Admin de Django

`MaintenanceAdminSite` (`growlog/admin_site.py`) permite el acceso solo a usuarios activos que son superusuarios y `is_staff`. Su vista de login no muestra un formulario propio: redirige al login de la app (con `next`), que es el que limita los intentos; si el usuario ya tiene permiso, va directo al índice del admin. Es una herramienta global de mantenimiento fuera de la separación por cultivo.

### Páginas protegidas y sesiones

No hay un middleware global de login: cada vista de la app usa `@login_required` (`LOGIN_URL = /login/`). Las páginas de login, logout, invitación y las rutas `/manifest.json` y `/sw.js` son accesibles sin sesión. Con sesión o en `/api/`, `/media/`, `/login/` y `/logout/`, las respuestas salen con `Cache-Control: private, no-store` (middleware `PrivateBitacoraMiddleware`).

### Tokens de la API

El modelo `APIToken` guarda por usuario el hash SHA-256 del token (`token_hash`, único) y `created_at`. El comando `create_api_token <username>` genera el token y lo muestra una sola vez. Ver [api.md](api.md).

## Cuenta (`/cuenta/`)

`growlog/views/cuenta.py`, vista `cuenta` (requiere sesión). Una sola pantalla con dos formularios, que se distinguen por el campo `accion` del POST.

| Acción | Formulario | Campos | Efecto |
| --- | --- | --- | --- |
| `preferencias` | `PreferenciasForm` (ModelForm de `Perfil`) | `nombre` (guarda `first_name` del usuario, opcional), `unidad_ec` (`us`, `ms`, `x10`), `avisar_ambiente`, `avisar_tareas`, `avisar_seguimientos`, `hora_avisos` (0 a 23) | Guarda el `Perfil` y el nombre; mensaje "Listo, guardamos tus preferencias." |
| `clave` | `PasswordChangeForm` de Django | Contraseña actual y nueva con confirmación | Cambia la contraseña y mantiene la sesión (`update_session_auth_hash`); mensaje "Listo, cambiaste la contraseña." |

`perfil_de(usuario)` crea el `Perfil` con valores por defecto la primera vez que se necesita: `unidad_ec="us"`, los tres avisos activados y `hora_avisos=20`. Las preferencias de avisos las usa `send_recordatorios` (ver [arquitectura.md](arquitectura.md)) y `unidad_ec` determina cómo se muestra la EC en toda la app.
