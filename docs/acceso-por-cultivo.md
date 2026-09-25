# Acceso por cultivo

## Política implementada

`Cultivo.propietario` determina quién administra el acceso. `creado_por` conserva
la autoría; la participación de un colaborador nunca cambia al propietario.
Cada membresía es única para el par cultivo/usuario.

| Operación | Propietario | Editor | Lector | Sin acceso |
| --- | --- | --- | --- | --- |
| Ver bitácora, fotos, reportes y costos vinculados | Sí | Sí | Sí | No |
| Registrar, corregir o eliminar entradas | Sí | Sí | No | No |
| Compartir, cambiar permiso o revocar | Sí | No | No | No |
| Recibir recordatorios de pendientes | Sí | Sí | No | No |

Las pantallas específicas que combinan historial y edición de fotoperiodo/etapa
requieren escritura; sus datos siguen visibles para lectores en la bitácora/API.
Todo usuario activo autenticado puede iniciar un cultivo propio.

La política común vive en `growlog/permissions.py`. Las consultas web limitan
primero los recursos visibles y luego verifican escritura. La API aplica la misma
política tanto por slug de cultivo como por UUID de planta. Las relaciones hijas
siguen verificándose dentro de su cultivo o planta. Un recurso no visible devuelve
404; un lector que intenta escribir, 403. Los métodos no admitidos devuelven 405.
No hay permisos especiales de bitácora para `is_staff` ni `is_superuser`.

El admin de Django es una herramienta global de mantenimiento, accesible solo a
superusuarios activos con acceso al admin. Es una excepción explícita a la
separación por cultivo y no una vía de uso cotidiano para colaboradores.

## Compartir sin destruir información

La pantalla permite seleccionar un cultivo propio y una cuenta existente, o
crear una cuenta con credenciales aleatorias que se muestran una sola vez.
No se envían credenciales ni mensajes automáticamente. El permiso inicial del
formulario es editor, conforme al uso colaborativo acordado; puede elegirse lector.

Revocar elimina la membresía, no la cuenta ni sus registros. Cada solicitud nueva
consulta los permisos actuales: sesiones y tokens existentes también pierden el
acceso. Cambiar el permiso a lector impide las escrituras posteriores.

## Recursos relacionados

- Equipos y tarifas tienen propietario. Se pueden leer si son propios o están
  vinculados mediante costos a un cultivo visible.
- Compartir un cultivo no comparte el resto del inventario del propietario.
  Un editor puede asignar equipos propios o ya vinculados a ese mismo cultivo.
- La tarifa del cultivo se obtiene de sus asignaciones de costos. El propietario
  puede seleccionar su tarifa vigente al crear una asignación; un colaborador
  utiliza las tarifas ya vinculadas. Cambiar una tarifa privada no la publica
  automáticamente en todos los cultivos compartidos.
- Modificar un recurso requiere ser su dueño y poder editar todos los cultivos
  vinculados. Esto evita modificar un cultivo revocado a través de un equipo propio.
  La API no elimina equipos con costos históricos; permite desactivarlos.
- Nutrientes y parámetros ideales siguen siendo catálogos comunes de consulta.
  Su mantenimiento está en el admin.
- Los recordatorios se componen por cultivo y se envían solo a su propietario
  y editores activos. Una cuenta no puede apropiarse ni borrar una suscripción
  push ajena. Cerrar sesión revoca la suscripción identificada de ese navegador,
  sin cancelar otros dispositivos del usuario.

## Fotos, caché y backups

Las fotos se descargan mediante `/media/...`, comprobando que exista una medición
con ese archivo en un cultivo visible. No se sirve cualquier archivo del storage.
El backend R2 entrega esa misma URL autorizada, incluso en widgets de formularios.
Los bytes se transmiten a través de Django; revisar rendimiento para fotos grandes.

**El acceso público del bucket y sus dominios es configuración externa.** Antes de
usar estos permisos con datos reales hay que deshabilitarlo y comprobar que una URL
antigua anónima ya no entrega fotos o backups. El código no modifica esa configuración
ni elimina copias públicas antiguas. Esta comprobación remota sigue pendiente.

Páginas autenticadas, API y media indican `Cache-Control: private, no-store`. El
service worker v7 elimina las cachés antiguas de 62xroots al activarse y conserva
solo recursos públicos, incluida la estructura vacía de Registrar. Los registros
locales se almacenan por separado, cifrados por cuenta en IndexedDB; ver
[registro-offline.md](registro-offline.md). Los dispositivos
deben recibir la actualización del service worker para retirar su caché anterior.

`backup_db` usa `STORAGES["backups"]`, separado del almacenamiento de fotos. Por
defecto escribe en `BASE_DIR/backups`, fuera de las rutas HTTP. `BACKUP_ROOT` permite
elegir otro directorio. En un sistema con disco efímero se necesita almacenamiento
persistente o un backend privado independiente. La restauración de backups reales
y la revisión de copias antiguas permanecen pendientes.

## Migración y puesta en uso

1. Preparar un backup privado verificado y revisar los cultivos sin autor.
2. Aplicar 0024 (campos y membresías) y 0025 (asignación de propietarios).
3. Cada cultivo con autor conserva a esa persona como propietario. Los cultivos
   sin autor quedan sin propietario hasta su revisión por un superusuario.
4. Equipos/tarifas solo reciben dueño automáticamente si todos sus costos apuntan
   al mismo propietario conocido. Recursos sin uso, con varios propietarios o con
   algún cultivo sin dueño conservan propietario nulo; sus vínculos previos no se borran.
5. Compartir explícitamente con los invitados anteriores. No se concede acceso a
   todos los cultivos por tener una cuenta existente.
6. Verificar storage privado, ubicación persistente de backups y actualización PWA.

No se ejecutaron estos pasos sobre la base real. La migración de datos se comprobó
con fixtures aislados. Revertir el esquema elimina las membresías: requiere evaluar
los cambios posteriores y el backup, no ejecutar una reversión a ciegas.

## Verificación y límites

La suite cubre propietario, editor sin staff, lector, staff ajeno, revocación,
cambio de rol, autoría, rutas web/API, fotos, recursos energéticos, recordatorios,
suscripciones, backups separados y migración de datos. Las pruebas JavaScript
verifican retiro de cachés privadas, navegación y comportamiento sin conexión.
La pantalla de compartir se revisó visualmente en escritorio y a 390 px de ancho
con datos sintéticos.

Esta entrega cierra la política de acceso en el código. No completa el rediseño:
quedan las validaciones/escrituras de dominio pendientes, históricos y rendimiento
y el resumen Hoy. Registrar y su cola offline se incorporaron en la entrega posterior,
con el alcance y las limitaciones documentados en el enlace anterior.
