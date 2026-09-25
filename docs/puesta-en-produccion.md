# Preparación de la actualización

## Estado

La preparación de esta entrega se completó el 25/09/2026: ensayo con copia real,
verificación de R2, volumen privado de backups y backup actualizado verificado.
`main` activa el despliegue automático. Railway aplica migraciones en el predeploy
del servicio web y luego inicia Gunicorn; recordatorios conserva su propio comando.
El `railway.toml` común define solo el build para no sobrescribir ambos servicios.
`Procfile` conserva el arranque alternativo con migraciones para otros despliegues.
El código nuevo aún no se publicó ni se aplicaron sus migraciones en producción.

Las migraciones 0024–0027 agregan propietarios, membresías, recibos de operaciones
y claves locales. No basta con volver al commit anterior después de migrar: se debe
evaluar la compatibilidad del esquema y conservar las nuevas escrituras y permisos.

## Auditoría antes de migrar

Desde un entorno controlado con este código y acceso a la base que se quiere revisar:

```sh
python manage.py auditar_actualizacion
```

El comando usa el estado de migraciones aplicado para consultar modelos históricos.
Funciona antes y después del cambio de permisos. Es de solo lectura: no migra,
asigna propietarios, concede accesos ni descarga archivos. Devuelve IDs para revisar,
migraciones pendientes y verificaciones externas que el código no puede certificar.
No imprime nombres, URLs de conexión, contraseñas ni claves offline.

`--fail-on-review` devuelve error cuando hay IDs que revisar. Una salida exitosa
no certifica que el bucket sea privado, que el backup sea recuperable ni que la
configuración externa de Railway esté preparada.

En el esquema antiguo se calcula la propiedad que aplicaría 0025. Se señalan las
cuentas activas sin cultivos propios para revisar su participación: esto no implica
concederles acceso a todos los cultivos. Los cultivos sin autor y los equipos/tarifas
con propiedad ambigua requieren una decisión explícita sobre el dueño correcto.

## Ensayo y publicación

1. Confirmar la rama que dispara producción. Guardar código en una rama separada
   solo después de comprobar que no dispara ese servicio ni una vista previa con
   credenciales de producción.
2. Obtener un backup consistente de PostgreSQL y restaurarlo en una base aislada.
   Configurar el entorno de ensayo con esa base, almacenamiento separado y
   notificaciones deshabilitadas. No copiar automáticamente credenciales de producción.
3. Ejecutar la auditoría, guardar el resultado en un lugar privado, aplicar
   migraciones en la copia y repetir la auditoría. Comparar cantidades y relaciones;
   resolver la asignación de propietarios con el usuario antes de hacerlo en producción.
4. Probar inicio de sesión, acceso de propietario/lector/editor, fotos y Registrar.
   Confirmar que un invitado anterior no puede consultar cultivos sin membresía.
5. Verificar en el proveedor que el bucket y sus dominios antiguos no sean públicos.
   Comprobar que un acceso anónimo no entregue fotos; los backups deben tener storage
   privado y persistente, separado de media.
6. Antes de publicar, coordinar una ventana sin escrituras, obtener el backup final
   y tener preparada la recuperación. Publicar, revisar las migraciones y repetir
   las pruebas básicas. Conservar los logs sin credenciales y la copia previa.

El ensayo, la comprobación de una foto privada y el almacenamiento persistente ya
se realizaron; sus resultados y límites se detallan a continuación. Si la publicación
se pospone, actualizar el backup antes de desplegar.

## Inspección de Railway — 24/09/2026

Se consultó configuración en modo lectura. El proyecto conectado tiene un entorno
`production` con servicios `web`, `Postgres` y `recordatorios`. Los despliegues de
web y recordatorios provienen de `main`. Solo se observó un volumen persistente,
montado en PostgreSQL; web no tiene `BACKUP_ROOT` configurado. Por ello el nuevo
backup local no tiene persistencia verificada.

El servicio recordatorios tiene configurado `python manage.py send_recordatorios`,
pero el manifiesto de su despliegue muestra el arranque web con migraciones y
Gunicorn. El archivo de configuración prevalece sobre el panel:
https://docs.railway.com/config-as-code/reference

La solución final elimina `startCommand` del archivo común. No hace falta un archivo
separado: se comprobó que Railway ya configura `gunicorn config.wsgi --log-file -`
para web, con `python manage.py migrate --noinput` en predeploy, y
`python manage.py send_recordatorios` para el cron. Su horario sigue siendo
`0 23 * * *`. El archivo alternativo preparado inicialmente se retiró para evitar
dos fuentes de configuración. Al publicar, comprobar que cada manifiesto use el
comando de su servicio y que las migraciones web finalicen antes de ejecutar el cron.

Railway documenta la retirada futura del formato Config as Code; esta separación
es para los servicios existentes y requiere planificar la migración al formato
vigente antes del plazo indicado por el proveedor.

Tras la autorización explícita del usuario se ejecutó la auditoría de PostgreSQL
con `default_transaction_read_only=on`, comprobado antes de consultar, y timeout
de 15 segundos por sentencia. Resultado: pendientes 0024–0027; ningún cultivo sin
propietario ni con propietario inactivo; ningún equipo o tarifa con propietario
ambiguo. El usuario confirmó que las cuentas 2 y 3 deben perder el acceso anterior:
no se crearán membresías para ellas. Sus cuentas y los registros que hayan creado
se conservan. No se asignaron ni revocaron permisos en producción durante la auditoría.

## Ensayo autorizado con copia real — 24/09/2026

El usuario autorizó obtener el backup y crear un PostgreSQL temporal separado.
Se creó el entorno `ensayo-migracion`, sin servicios web ni notificaciones, y un
PostgreSQL 18.6 independiente. No se duplicaron credenciales de servicios externos.

Se exportó producción con `pg_dump` en formato custom y transacciones de solo
lectura. El archivo local `backups/produccion_20260924T195256Z.dump` ocupa 139745 bytes;
su SHA-256 y los resultados están en `backups/ensayo_manifest.json`. Ambos quedan
excluidos de Git. Conservar el archivo como información privada.

Se comprobó que el destino estaba vacío y se restauró en una sola transacción.
El ensayo se ejecutó por SSH dentro del contenedor temporal, sin exponer PostgreSQL
a Internet, con Python 3.13 y las dependencias del repositorio. Los settings del
ensayo deshabilitaron notificaciones y aislaron almacenamiento de archivos.

Las migraciones 0024–0027 terminaron correctamente. Se compararon hashes de todos
los valores de las columnas originales de 23 tablas de growlog antes y después:
no hubo alteraciones. Se verificó asignación de propietarios, ausencia de membresías
automáticas y falta de acceso de las cuentas 2 y 3. Inicio y contexto de Registrar
respondieron 200 con cada cuenta activa de la copia.

Esto valida restauración y migración de los datos de esa instantánea, no las fotos
remotas ni concurrencia bajo carga. Producción no se migró ni desplegó. Antes de
publicar se necesita un backup final actualizado y cerrar la configuración de
storage y recordatorios. El volumen de ensayo se conserva y puede generar cargos
de almacenamiento incluso si el servicio está detenido.

La consulta posterior confirmó que el servicio temporal quedó sin despliegue
activo y conserva el volumen. Se restauró el contexto local de Railway a production.

## Cierre de infraestructura — 25/09/2026

Se corrigió una conclusión de la revisión anterior: `R2_SECRET_KEY` no aparecía en
la salida de variables del CLI, pero sí está presente dentro del servicio web en
ejecución. No era una credencial faltante. Se comprobó su presencia sin mostrarla.
El acceso autenticado al bucket y a una foto existente funcionó; un HEAD anónimo
sobre la URL del dominio público configurado de esa foto devolvió 403. Esto verifica
esa ruta conocida, no constituye un inventario exhaustivo de dominios históricos.

Se creó `web-volume`, montado en `/data`, y se configuró `BACKUP_ROOT=/data/backups`.
Adjuntar el volumen provocó un redespliegue del código anterior: terminó en SUCCESS.
No publicó los cambios locales. Se comprobó el montaje desde el proceso web y se
copió el backup ensayado al volumen con permisos 0600, verificando su SHA-256.

También se generó un backup PostgreSQL actualizado, conservado localmente y en el
volumen privado, con verificación de hash tras escribir. Su nombre y checksum están
en `backups/release_backup_manifest.json`, excluido de Git. No se usa el bucket de
fotos para estos backups. El volumen de web y el de ensayo generan almacenamiento
facturable; el servidor de ensayo permanece detenido.

Verificación final de código: 125 pruebas Django y 14 JavaScript aprobadas, sin
modelos pendientes de migración ni errores de whitespace. Tras subir el código,
verificar SUCCESS de web, manifiesto de recordatorios, fotos autenticadas y Registrar.

## Qué cubre el backup de la aplicación

`backup_db` exporta un fixture JSON al storage privado de backups. La prueba
automatizada restaura ese fixture en la base de pruebas vacía y verifica propietarios,
membresías, claves locales y recibos. No prueba restauración PostgreSQL, volumen
persistente ni permisos reales del proveedor.

En Railway, si el storage de backups es filesystem, el comando exige que su ruta
resuelta esté dentro de `RAILWAY_VOLUME_MOUNT_PATH`. Si no, falla antes de exportar
datos. Configurar `BACKUP_ROOT` dentro del volumen montado. Este control evita el
directorio efímero por defecto, pero no sustituye verificar el volumen y restaurar
la copia. El comando no crea volúmenes ni cambia infraestructura.

El fixture contiene información privada, incluidas claves offline y hashes de
contraseñas. No subirlo a GitHub. No incluye los bytes de las fotos ni configuración
de infraestructura. `dumpdata` no garantiza por sí solo una instantánea consistente
entre tablas mientras la aplicación recibe escrituras; usar un backup consistente
de la base para la transición de producción.

Restaurar una copia antigua puede perder claves, recibos y registros posteriores.
Antes de habilitar la sincronización de dispositivos se deben conciliar esas
operaciones. Un backup existente sin ensayo de restauración no cierra este requisito.
