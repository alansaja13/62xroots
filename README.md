# 62xroots

Bitácora de cultivo construida con Django, templates, HTMX y Alpine.

El rumbo de producto, las decisiones confirmadas y los criterios de cada
entrega están en [docs/rumbo-del-producto.md](docs/rumbo-del-producto.md).

Antes de subir a la rama con despliegue automático, revisar
[docs/puesta-en-produccion.md](docs/puesta-en-produccion.md). Incluye la auditoría
de solo lectura `python manage.py auditar_actualizacion`, compatible con el esquema
anterior y el nuevo, y el procedimiento de ensayo sobre una copia aislada.

Preparación verificada el 25/09/2026: restauración y migración de una copia real de
PostgreSQL, fotos privadas comprobadas, volumen de backups `/data` y copia actualizada
con checksum. El nuevo código no está desplegado. En Railway, los comandos de web y
recordatorios se configuran por servicio; el archivo común solo define el build.

## Pruebas locales aisladas

Con Python compatible con Django 6 y las dependencias de `requirements.txt`:

```sh
python manage.py test --settings=config.test_settings
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
node tests/service_worker.test.cjs
node tests/offline_sync.test.cjs
```

Estos settings usan una base SQLite en memoria, almacenamiento en memoria y
notificaciones deshabilitadas. No sirven para ejecutar producción. La suite no
modifica la base local ni accede al almacenamiento remoto.

## Desarrollo

Configurar `SECRET_KEY`, `DEBUG=True` y `ALLOWED_HOSTS=localhost,127.0.0.1` en
un entorno local. Sin `DATABASE_URL`, Django usa `db.sqlite3`. No usar valores
de producción para desarrollo. No ejecutar importadores, seeds o migraciones
sobre una base existente sin revisar sus efectos y contar con backup.

```sh
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

El acceso es por propietario y membresías de cultivo (`lector` / `editor`).
La pantalla **Compartir cultivos** administra los permisos. El admin global
queda reservado a superusuarios de mantenimiento; `is_staff` no habilita acceso
a cultivos ajenos en la web o la API.

Las migraciones 0024 y 0025 agregan propiedad y membresías y recuperan los
propietarios conocidos. No se aplicaron a datos reales como parte del desarrollo.
Revisar [docs/acceso-por-cultivo.md](docs/acceso-por-cultivo.md) antes de aplicarlas:
los invitados antiguos deben recibir acceso explícito y los recursos sin dueño
inequívoco requieren revisión administrativa.

Las fotos se sirven por una ruta autorizada de Django. Un bucket que antes era
público debe hacerse privado en el proveedor; este cambio de código no desactiva
los dominios públicos existentes. Los backups nuevos utilizan un almacenamiento
separado (`STORAGES["backups"]`, directorio `BACKUP_ROOT`), que debe ser persistente.

## Registrar con y sin conexión

La pantalla **Registrar** permite guardar ambiente, observaciones, tareas, pH/EC
y riegos por planta con nutrientes. Primero guarda en el dispositivo y luego
sincroniza; distingue pendientes, rechazos y confirmaciones del servidor.
Abrirla con conexión y sesión iniciada al menos una vez en cada dispositivo.
Se necesita HTTPS (o localhost para desarrollo), JavaScript, IndexedDB y WebCrypto.

Las migraciones 0026 y 0027 agregan recibos para evitar duplicados y claves de
almacenamiento local por cuenta. Tampoco se aplicaron a datos reales.
Los pendientes se guardan cifrados; cerrar sesión bloquea su acceso y volver a
entrar con la misma cuenta permite recuperarlos. Para reabrir sin conexión después
de cerrar el navegador, la sesión debe conservarse. No borrar los datos del sitio
mientras haya pendientes sin sincronizar o exportar.

La sincronización funciona con la pantalla abierta o al volver a abrirla. Fotos,
drenajes detallados y consulta del historial completo requieren conexión.
La caché del service worker conserva únicamente la pantalla pública y recursos
estáticos. Contrato, límites y pruebas: [docs/registro-offline.md](docs/registro-offline.md).
