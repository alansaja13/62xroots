# Arquitectura

Estructura del proyecto Django, configuración, middleware, context processors, PWA y push, comandos de gestión, señales, storage, ejecución de tests y despliegue. Las reglas de acceso están en [permisos.md](permisos.md), los modelos en [modelos.md](modelos.md) y la lógica de dominio en [servicios.md](servicios.md).

## Estructura de carpetas

Todos los comandos `manage.py` se ejecutan desde la carpeta `62xroots/` (el proyecto Django). El repositorio tiene un único proyecto y una única app.

| Ruta | Contenido |
| --- | --- |
| `config/` | `settings.py`, `test_settings.py`, `urls.py`, `wsgi.py`, `asgi.py` |
| `growlog/` | App única: `models.py`, `forms.py`, `registration_forms.py`, `api_views.py`, `permissions.py`, `middleware.py`, `context_processors.py`, `signals.py`, `storage.py`, `push.py`, `admin.py`, `admin_site.py`, `urls.py`, `utils.py` |
| `growlog/views/` | Vistas web por dominio; `__init__.py` las re-exporta para que `urls.py` use `views.<nombre>` |
| `growlog/services/` | Lógica compartida por la web y la API |
| `growlog/templatetags/` | Filtros y tags de plantilla |
| `growlog/management/commands/` | Comandos de gestión |
| `growlog/migrations/` | Migraciones |
| `growlog/test_*.py`, `growlog/tests.py` | Tests de la app |
| `templates/` | Plantillas HTML (`growlog/`, `partials/`, `pwa/sw.js`, páginas de error) |
| `static/` | Estáticos (`static/growlog/`: CSS, JS, íconos) |
| `media/` | Destino local de fotos de plantas cuando no hay R2 |
| `backups/` | Destino por defecto de los backups |
| `docs/` | Documentación |
| `seed.py`, `seed_energia.py`, `import_excel.py` | Scripts sueltos de datos de demostración e importación |
| `Procfile`, `railway.toml`, `runtime.txt`, `requirements.txt` | Despliegue y dependencias |

Módulos de `growlog/views/`: `actividad`, `auth`, `ayuda`, `canopy`, `cuenta`, `cultivos`, `errors`, `eventos`, `helpers`, `invitados`, `mas`, `media`, `mediciones`, `nutrientes`, `plantas`, `pwa`, `registrar`, `registros`, `reportes`, `tareas`. Ver [pantallas.md](pantallas.md) y [pantallas-cultivo.md](pantallas-cultivo.md).

Rutas raíz (`config/urls.py`): `admin/`, `favicon.ico` (redirige a `static/growlog/logo.png`), `manifest.json`, `sw.js`, `media/<path>` (vista `protected_media`) y todo `growlog.urls` montado en `/`. Los handlers 400, 403, 404 y 500 son `growlog.views.error_400/403/404/500`, que renderizan `400.html`, `403.html`, `404.html` y `500.html`.

Dependencias (`requirements.txt`): Django 6.0.5, django-htmx, python-dotenv, Pillow, pywebpush, gunicorn, whitenoise, dj-database-url, psycopg2-binary y django-storages[s3]. Python 3.12 (`runtime.txt`).

## Configuración (`config/settings.py`)

`python-dotenv` carga un archivo `.env` al importar el módulo. Variables de entorno que se leen:

| Variable | Uso | Valor por defecto |
| --- | --- | --- |
| `DEBUG` | Es verdadero solo si vale exactamente `True` | falso |
| `SECRET_KEY` | Clave de Django. Si falta y `DEBUG` es falso, el arranque lanza `RuntimeError`. Si falta con `DEBUG` verdadero se usa una clave fija de desarrollo | sin valor |
| `ALLOWED_HOSTS` | Lista separada por comas | `localhost,127.0.0.1` |
| `DATABASE_URL` | Si está definida se usa `dj_database_url` con `conn_max_age=600`; si no, SQLite | sin valor |
| `CSRF_TRUSTED_ORIGINS` | Lista separada por comas; se le suma siempre `https://62xroots.up.railway.app` | vacío |
| `PERMITIR_FOTOS_A_TODOS` | `True` habilita la subida de fotos a cualquier usuario (ver [permisos.md](permisos.md)) | falso |
| `R2_BUCKET` | Si está definida, el storage de media pasa a Cloudflare R2 | sin valor |
| `R2_ENDPOINT`, `R2_ACCESS_KEY`, `R2_SECRET_KEY` | Credenciales del storage R2 | sin valor |
| `R2_PUBLIC_URL` | Se normaliza (sin esquema ni barra final) y queda en `settings.R2_PUBLIC_URL` | vacío |
| `BACKUP_ROOT` | Carpeta del storage `backups` | `backups/` dentro del proyecto |
| `TRUSTED_PROXY_HOPS` | Cantidad de proxies que agregan su entrada a `X-Forwarded-For` | `1` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Claves Web Push | vacío |
| `VAPID_ADMIN_EMAIL` | Contacto para el claim `sub` de VAPID | definido en `settings.py` |
| `RECORDATORIO_MEDICION_HORA` | Entero; se guarda en `settings.RECORDATORIO_MEDICION_HORA` | `20` |
| `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_VOLUME_MOUNT_PATH` | Los lee solo el comando `backup_db` (ver más abajo) | sin valor |

Otros valores fijos de `settings.py`:

- `LANGUAGE_CODE = "es-ar"`, `TIME_ZONE = "America/Argentina/Buenos_Aires"`, `USE_TZ = True`, `USE_I18N = True`.
- `DEFAULT_AUTO_FIELD = BigAutoField`.
- `LOGIN_URL = "/login/"`, `LOGIN_REDIRECT_URL = "/"`, `LOGOUT_REDIRECT_URL = "/login/"`.
- `DATA_UPLOAD_MAX_MEMORY_SIZE` y `FILE_UPLOAD_MAX_MEMORY_SIZE` en 5 MB.
- `AUTH_PASSWORD_VALIDATORS`: similitud con atributos del usuario, largo mínimo 8 y contraseñas comunes.
- `LOGIN_MAX_ATTEMPTS = 10` y `LOGIN_LOCKOUT_SECONDS = 1800` (ver [permisos.md](permisos.md)).
- Con `DEBUG` falso: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` y HSTS de un año con subdominios y preload.

### Apps instaladas

`growlog.apps.MaintenanceAdminConfig` (reemplaza a `django.contrib.admin`; su sitio por defecto es `growlog.admin_site.MaintenanceAdminSite`), `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles`, `django_htmx` y `growlog.apps.GrowlogConfig`. `GrowlogConfig.ready()` importa `growlog.signals`.

### Base de datos y caché

- Sin `DATABASE_URL`: SQLite en `db.sqlite3` dentro de `62xroots/`.
- Con `DATABASE_URL`: la base que indique (PostgreSQL en Railway).
- Caché `default`: `DatabaseCache` con la tabla `growlog_cache`, que crea una migración de `growlog`. La usan el límite de intentos de login y el límite de escrituras de la API.

### Archivos estáticos y whitenoise

- `STATIC_URL = "static/"`, `STATICFILES_DIRS = [static/]`, `STATIC_ROOT = staticfiles/`.
- Backend `whitenoise.storage.CompressedManifestStaticFilesStorage`: los archivos llevan hash en el nombre.
- `WHITENOISE_MANIFEST_STRICT = False`: si una plantilla pide un estático ausente del manifest, se usa el nombre sin hash.
- `WhiteNoiseMiddleware` va justo después de `SecurityMiddleware`.

### Storage de media

`STORAGES` define tres storages:

| Alias | Sin `R2_BUCKET` | Con `R2_BUCKET` |
| --- | --- | --- |
| `default` | `FileSystemStorage` sobre `MEDIA_ROOT = media/` | `growlog.storage.PrivateMediaStorage` sobre el bucket R2 (`querystring_auth=True`, `file_overwrite=False`, `region_name="auto"`, `addressing_style="path"`) |
| `staticfiles` | `CompressedManifestStaticFilesStorage` | igual |
| `backups` | `FileSystemStorage` en `BACKUP_ROOT` (archivos `0o600`, carpetas `0o700`) | igual |

`MEDIA_URL = "/media/"` en ambos casos. Las fotos se sirven siempre por la vista `protected_media` (`growlog/views/media.py`), que exige sesión y busca la ruta solo en `MedicionPlanta.foto` y `MedicionPlanta.foto_mini` de plantas de cultivos visibles para el usuario; cualquier otra ruta devuelve 404. Las fotos de tamaño completo responden con `Cache-Control: no-store, private`; las miniaturas con `private, max-age=86400`.

`growlog/storage.py` define `PrivateMediaStorage(S3Storage)`, cuyo `url()` no devuelve la URL del bucket sino `reverse("protected_media", path=name)`.

## Middleware

Orden en `MIDDLEWARE`:

1. `SecurityMiddleware`
2. `WhiteNoiseMiddleware`
3. `SessionMiddleware`
4. `CommonMiddleware`
5. `CsrfViewMiddleware`
6. `AuthenticationMiddleware`
7. `growlog.middleware.PrivateBitacoraMiddleware`
8. `growlog.middleware.CultivoRecienteMiddleware`
9. `MessageMiddleware`
10. `XFrameOptionsMiddleware`
11. `django_htmx.middleware.HtmxMiddleware`

`PrivateBitacoraMiddleware`: si el usuario está autenticado, o la ruta empieza con `/api/`, `/media/`, `/login/` o `/logout/`, agrega `Cache-Control: private, no-store` y `Vary: Cookie` a la respuesta. Se exceptúan `/sw.js` y `/manifest.json`. Si la respuesta ya trae un `max-age` (miniaturas de fotos), solo se le agrega `private` y se conserva el `max-age`.

`CultivoRecienteMiddleware`: después de la vista, si `request.cultivo_actual` está definido (lo fija `objeto_del_cultivo`, ver [permisos.md](permisos.md)) y la sesión no tiene ese cultivo en `cultivo_reciente`, guarda su `pk` en `request.session["cultivo_reciente"]`.

## Context processors

Registrados en `TEMPLATES`, además de `request`, `auth` y `messages`: `growlog.context_processors.push_settings` y `growlog.context_processors.navegacion`.

### `push_settings`

| Variable | Valor |
| --- | --- |
| `unidad_ec` | `Perfil.unidad_ec` del usuario (`us`, `ms` o `x10`); `us` si no hay perfil. Se evalúa de forma perezosa |
| `vapid_public_key` | `settings.VAPID_PUBLIC_KEY` |
| `can_edit_cultivo` | `request.puede_editar_cultivo` o `False` |
| `can_manage_cultivo` | `True` si hay `cultivo_actual` y su propietario es el usuario |

### `navegacion`

Devuelve `{}` si el usuario no está autenticado. Si lo está:

| Variable | Valor |
| --- | --- |
| `cultivo_nav` | `request.cultivo_actual` |
| `seccion_cultivo` | Sección activa del cultivo según el nombre de la URL, tomada de `SECCIONES_CULTIVO` |
| `pestanas_cultivo` | Lista de pestañas del cultivo (vacía si no hay cultivo abierto). La pestaña `ajustes` solo aparece si el usuario puede editar |
| `pestana_extra_activa` | La pestaña activa que figura como "extra" (se agrupa en el menú Más en el celular), o `None` |
| `nav_cultivos` | Cultivos visibles agrupados: `activos` (propios no finalizados ni archivados), `compartidos`, `historial` (finalizados o archivados) y `total`. Perezoso |
| `cultivo_destino` | Cultivo al que llevan "Cultivo", "Plantas" y "Tareas": el abierto, si no el de `session["cultivo_reciente"]`, si no el primero vivo (activos y compartidos). Perezoso |
| `nav_activa` | `hoy`, `cultivo`, `plantas`, `tareas`, `mas` o vacío |

Las pestañas definidas en `PESTANAS_CULTIVO` son: Resumen (`cultivo_detail`), Bitácora (`timeline`), Tareas (`tareas_list`), Aire (`cultivo_aire`), Ciclo (`cultivo_ciclo`), Canopy (`canopy`), Energía (`energia`), Reporte (`reporte`) y Ajustes (`cultivo_ajustes`). Desde Aire en adelante son "extra".

`SECCIONES_CULTIVO` asigna cada nombre de URL a una sección:

| Sección | Nombres de URL |
| --- | --- |
| `resumen` | `cultivo_detail`, `planta_detail`, `planta_etapa_list`, `plantas_list`, `planta_crear` |
| `bitacora` | `timeline` |
| `tareas` | `tareas_list` |
| `tendencias` | `cultivo_aire` |
| `canopy` | `canopy` |
| `energia` | `energia` |
| `reporte` | `reporte` |
| `ajustes` | `cultivo_ajustes`, `cultivo_empezar` |
| `ciclo` | `cultivo_ciclo`, `cultivo_cosecha`, `cultivo_etapa`, `fotoperiodo_list` |

`PANTALLAS_MAS` (pantallas globales que marcan "Más" como activo): `mas`, `cuenta`, `nutrientes`, `nutriente_crear`, `nutriente_editar`, `invitados_panel`, `faq`, `actividad`. `nav_activa` vale `hoy` para `dashboard`; `tareas` para `tareas_todas` o la sección `tareas`; `mas` para `PANTALLAS_MAS`; `plantas` para `planta_detail`, `planta_etapa_list`, `plantas_list` y `planta_fotos`; y `cultivo` para cualquier otra pantalla con sección.

## PWA y push

Vistas en `growlog/views/pwa.py`, envío en `growlog/push.py`, service worker en `templates/pwa/sw.js`.

### Manifest

`GET /manifest.json` (`pwa_manifest`) devuelve JSON con `Content-Type: application/manifest+json`. Contenido: `id`, `start_url` y `scope` en `/`, `name` "62×ROOTS GrowLog", `short_name` "62×ROOTS", `lang` `es-AR`, `display` `standalone`, `background_color` y `theme_color` `#15110d`, cuatro íconos (192 y 512, `any` y `maskable`, en `static/growlog/icons/`) y dos shortcuts: Registrar (`/registrar/`) y Hoy (`/`).

### Service worker

`GET /sw.js` (`pwa_service_worker`) renderiza `pwa/sw.js` como `application/javascript` con `Service-Worker-Allowed: /` y `Cache-Control: no-cache`. El service worker:

- En `install` llama `skipWaiting()`.
- En `activate` borra las cachés cuyo nombre empieza con `62xroots-` y toma control de los clientes.
- En `push` muestra una notificación con `title`, `body` y `url` del payload JSON (si el payload no es JSON, usa el texto como cuerpo). Ícono `icon-192x192.png`, badge `badge-96x96.png`.
- En `notificationclick` cierra la notificación y enfoca una ventana abierta con esa URL; si no la hay, navega otra ventana de la app, y si tampoco, abre una nueva.
- No intercepta `fetch` ni guarda páginas.

### Suscripciones

| Ruta | Vista | Método | Comportamiento |
| --- | --- | --- | --- |
| `/push/subscribe/` | `push_subscribe` | POST, requiere sesión | Cuerpo JSON con `endpoint` y `keys.p256dh`/`keys.auth`. Crea la `PushSubscription` o actualiza las claves si ya existía para el mismo usuario. Si el `endpoint` pertenece a otra cuenta responde 409. Datos inválidos o incompletos: 400. Guarda el endpoint en `session["push_endpoint"]` |
| `/push/unsubscribe/` | `push_unsubscribe` | POST, requiere sesión | Cuerpo JSON con `endpoint`; borra la suscripción de ese endpoint solo si es del usuario |

El cierre de sesión (`logout_view`) borra la suscripción del navegador actual (endpoint recibido por POST o guardado en sesión) y conserva las de otros dispositivos.

### Envío

`growlog.push.send_push_to_users(user_ids, title, body, url="/")` envía por `pywebpush` a las suscripciones de usuarios activos de la lista. Con `VAPID_PRIVATE_KEY` vacía registra una advertencia y devuelve 0. Las suscripciones que responden 404 o 410 se borran; otros errores se registran y se sigue con el resto. Devuelve la cantidad de envíos exitosos. El claim VAPID `sub` es `mailto:` más `VAPID_ADMIN_EMAIL`.

## Comandos de gestión

Ubicados en `growlog/management/commands/`. Se ejecutan con `python manage.py <comando>`.

| Comando | Argumentos | Qué hace |
| --- | --- | --- |
| `send_recordatorios` | `--hora-actual` (opcional) | Recorre los cultivos no archivados ni finalizados. Para cada uno calcula si falta medición de ambiente hoy, si hay seguimientos de eventos vencidos sin resolver y si hay tareas vencidas o de hoy sin completar. Destinatarios: propietario y miembros con rol editor. Cada persona recibe solo lo que activó en su `Perfil` (`avisar_ambiente`, `avisar_seguimientos`, `avisar_tareas`); sin perfil se asumen todos activados. Con `--hora-actual` avisa solo a quienes tienen `hora_avisos` igual a la hora local actual (para correrlo cada hora); sin el flag avisa a todos. Envía con `send_push_to_users` un mensaje por cultivo y combinación de textos, con título "Pendientes · <cultivo>" y enlace a la página del cultivo. Imprime el total de suscripciones alcanzadas |
| `backup_db` | ninguno | Ejecuta `dumpdata` (con `--natural-foreign --natural-primary --indent 2`) y lo guarda como `backup_AAAAMMDD_HHMMSS.json` en el storage `backups`. Si corre en Railway (`RAILWAY_ENVIRONMENT_ID` definida) con storage de filesystem, exige que su carpeta esté dentro de `RAILWAY_VOLUME_MOUNT_PATH`; si no, aborta con error sin exportar nada |
| `auditar_actualizacion` | `--database` (alias, por defecto `default`), `--fail-on-review` | Auditoría de solo lectura que usa el estado histórico de migraciones. Imprime un JSON con migraciones de `growlog` pendientes, si el esquema ya tiene propietarios, y listas de IDs a revisar: cultivos sin propietario, cultivos con propietario inactivo, equipos y tarifas sin propietario inequívoco y, en el esquema anterior a propietarios, cuentas activas sin cultivos propios. Con `--fail-on-review` termina con error si alguna lista no está vacía. Falla si la base no tiene migraciones de `growlog` aplicadas |
| `create_api_token` | `username` | Genera un token aleatorio de 64 caracteres hexadecimales, guarda su SHA-256 en `APIToken` para ese usuario e imprime el token en claro una sola vez |
| `seed_canopy_initial` | `slug`, `--scrog` (0 a 100, por defecto 0), `--colas` (1 a 10, por defecto 2), `--notas`, `--force` | Crea el primer `CanopySnapshot` de un cultivo con `ColaPosicion` por planta activa, ubicadas alrededor de la posición de carpa de cada planta. Si el cultivo ya tiene snapshots no hace nada salvo con `--force`. Falla si el cultivo no existe o no tiene plantas activas |
| `backfill_riego_plantas` | `--apply` (opcional) | Completa el detalle por planta (`RiegoPlanta`) de riegos que no lo tienen. Reconstruye las plantas desde un `Evento` con el mismo timestamp que tenga plantas afectadas o, si `volumen_por_planta_ml` por la cantidad de plantas activas coincide con `volumen_total_ml`, repartiendo entre las plantas activas. Sin `--apply` solo informa (dry-run); los riegos que no puede inferir quedan listados como no resueltos |
| `add_riego_planta` | `riego_id`, `apodo`, `volumen_ml` | Crea o actualiza la fila `RiegoPlanta` de la planta con ese apodo en el riego indicado y recalcula `volumen_total_ml` como suma de las filas |
| `migrate_media_to_r2` | ninguno | Sube a `default_storage` los archivos de `MEDIA_ROOT` que todavía no existen allí. Falla si `R2_BUCKET` no está configurado; si `MEDIA_ROOT` no existe, no hace nada |

## Señales (`growlog/signals.py`)

| Señal | Receptor | Efecto |
| --- | --- | --- |
| `post_delete` de `MedicionPlanta` | `borrar_foto_de_medicion` | Al confirmarse la transacción borra del storage `foto` y `foto_mini` |
| `pre_save` de `MedicionPlanta` | `borrar_foto_reemplazada` | Si la medición ya existía y cambió `foto` o `foto_mini`, borra el archivo anterior al confirmarse la transacción |
| `user_logged_in` | `registrar_ingreso` | Crea un `Ingreso` exitoso con el usuario, el nombre usado y el dispositivo; borra los `Ingreso` de más de 90 días |
| `user_login_failed` | `registrar_ingreso_fallido` | Crea un `Ingreso` fallido con el nombre usado (hasta 150 caracteres) y el dispositivo |

Un error del storage al borrar un archivo se registra en el log y no interrumpe la operación. El dispositivo se calcula en `dispositivo_corto(user_agent)` a partir del User-Agent, con el formato "Sistema · Navegador" (por ejemplo "iPhone · Safari"); queda vacío si no se reconoce. No se guarda la IP.

## Tests

Los tests están en `growlog/test_*.py` y `growlog/tests.py`. Se ejecutan con una configuración aislada:

```powershell
cd "62xroots"
python manage.py test growlog --settings=config.test_settings
```

`config/test_settings.py` importa `settings.py` y reemplaza: `DEBUG = False`; base SQLite en memoria; storages `default` y `backups` en `InMemoryStorage` y `staticfiles` en `StaticFilesStorage` (sin manifest); caché `LocMemCache`; hasher de contraseñas MD5; backend de correo `locmem`; `ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]`; sin redirección SSL ni cookies seguras; claves VAPID vacías. Si no hay `SECRET_KEY` en el entorno, define una de prueba. Un módulo individual se corre con `python manage.py test growlog.test_permissions --settings=config.test_settings`.

## Despliegue

- `Procfile`: `web: python manage.py migrate --noinput && gunicorn config.wsgi --log-file -`.
- `railway.toml`: define solo la fase de build, `python manage.py collectstatic --noinput`. No define `startCommand`, para no pisar el del servicio de recordatorios.
- En Railway, según los comentarios de `railway.toml`, el servicio web usa `python manage.py migrate --noinput` como comando previo al despliegue y `gunicorn config.wsgi --log-file -` como arranque, y un servicio aparte ejecuta `python manage.py send_recordatorios`.
- La base es PostgreSQL vía `DATABASE_URL`; las fotos van a Cloudflare R2 cuando `R2_BUCKET` está definida; los estáticos los sirve whitenoise.
- Detrás del proxy de Railway, Django confía en `X-Forwarded-Proto` para detectar HTTPS y en `TRUSTED_PROXY_HOPS` para leer la IP del cliente.
- El procedimiento de actualización y las verificaciones previas están en `docs/puesta-en-produccion.md`.
