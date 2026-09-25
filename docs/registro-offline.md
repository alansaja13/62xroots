# Registrar y sincronizar

## Uso cotidiano

Entrar a **Registrar** con conexión prepara el dispositivo: descarga la pantalla
pública y obtiene los cultivos editables, plantas activas y catálogo de nutrientes.
Después se puede registrar ambiente, observaciones, pH/EC, tareas y riegos con
volumen por planta y nutrientes sin conexión. La fecha indica cuándo ocurrió el
hecho, no cuándo llegó al servidor. El formulario conserva un borrador local.

**Guardar registro** confirma primero la escritura en IndexedDB. La entrada queda
pendiente hasta recibir una confirmación del servidor. Con Registrar abierto se
reintenta al recuperar conexión; volver a abrirlo también inicia la sincronización.
No depende de que el sistema operativo ejecute la PWA cerrada en segundo plano.

Los errores de validación permiten corregir y volver a guardar. Un rechazo por
permisos conserva la entrada para reintentar cuando se restituya el acceso o
descargarla. Los conflictos 409 se conservan para revisión, sin crear automáticamente
otra operación. **Descartar** elimina la copia local; no deshace una escritura que
el servidor pudiera haber recibido. **Quitar confirmación local** tampoco borra la
entrada de la bitácora. La descarga de pendientes es JSON sin cifrar, para recuperación
manual: todavía no existe una pantalla de importación.

## Separación de responsabilidades

- `registration_forms.py`: validaciones de cada tipo de registro.
- `services/registro.py`: permisos, operación transaccional y recibo idempotente.
- `registration_views.py`: pantalla pública, contexto autenticado y transporte HTTP.
- `offline-store.js`: cifrado, persistencia y estados de sincronización.
- `registrar.js`: formulario, borrador, cuenta activa y reintentos.

El POST `/registrar/sincronizar/` exige sesión activa, CSRF y `X-Registro-Cuenta`
coincidente con la cuenta autenticada. Recibe este formato:

```json
{
  "id": "b85c31cb-1675-4079-8119-3c46dba80f76",
  "cultivo_id": 7,
  "tipo": "ambiente",
  "observado_en": "2026-09-24T12:00:00-03:00",
  "datos": {"temperatura_c": "24.5", "humedad_relativa": "60", "notas": "Ventilación revisada"}
}
```

El cliente conserva el UUID y el contenido exactos entre reintentos. Dentro de una
transacción, el servidor verifica acceso, crea el registro y guarda `RegistroRecibido`.
La restricción única por usuario/UUID y el hash del contenido distinguen un reenvío
de un conflicto. Un reenvío válido devuelve el recibo anterior; cambiar el contenido
del mismo UUID devuelve 409. Un error revierte tanto registro como recibo. Los riegos
reutilizan el servicio de dominio para guardar plantas y nutrientes juntos.

Se verifican permisos incluso cuando ya existe un recibo. Un lector recibe 403 y
un cultivo inaccesible, 404. Errores temporales, desconexiones o respuestas perdidas
mantienen el pendiente. Solo una respuesta válida con el UUID esperado lo confirma.
Web Locks coordina pestañas cuando está disponible; la restricción del servidor
protege también los reintentos simultáneos de clientes sin esa API.

## Privacidad y límites locales

El service worker v7 almacena recursos públicos y la estructura vacía de Registrar,
nunca respuestas del contexto, API, fotos o páginas privadas. IndexedDB guarda
catálogo, borrador y operaciones cifrados con AES-GCM, IV nuevo por escritura y el
identificador de fila autenticado. Los identificadores numéricos de cuenta no se cifran.

Cada usuario tiene una clave aleatoria estable en `ClaveRegistroLocal`. Se entrega
solo a su sesión autenticada. El navegador guarda el desbloqueo en una cookie que
se elimina al cerrar sesión; la cookie no sirve para autenticarse ante el servidor.
Una respuesta tardía de contexto no se acepta si cambió la cuenta o se cerró sesión
durante la solicitud. La clave es independiente de `SECRET_KEY` y de la contraseña.
Volver a iniciar sesión con la misma cuenta permite recuperar las copias cifradas.

Esto separa cuentas en el uso normal del navegador; no protege de código malicioso
ejecutado en el mismo origen ni de acceso al dispositivo mientras la cuenta está
desbloqueada. Revocar acceso en el servidor impide sincronizar, pero no puede retirar
instantáneamente datos ya descargados en un dispositivo desconectado.

Se solicita almacenamiento persistente, pero el navegador puede no concederlo.
Borrar datos del sitio, usar navegación privada o perder el dispositivo puede eliminar
pendientes. Si la sesión no se conserva al cerrar el navegador, se necesita conexión
para iniciar sesión nuevamente. Fotos, historial completo y drenajes detallados siguen
en los flujos con conexión. Las confirmaciones locales no tienen todavía limpieza por
antigüedad y no sustituyen un historial paginado del servidor.

## Migración y operación

0026 agrega recibos y 0027 claves locales, después de 0024/0025 de acceso por cultivo.
Las claves se crean al preparar Registrar para cada cuenta. Estas migraciones se
probaron solo con bases aisladas; no se migró ni desplegó la base real.

Los backups privados deben conservar tanto claves como recibos. Borrar o regenerar
una clave impide descifrar pendientes existentes. Restaurar un backup antiguo puede
perder recibos y registros posteriores: antes de reactivar sincronización se deben
conciliar las operaciones posteriores al backup para evitar duplicaciones. No se
probó una restauración de producción ni concurrencia bajo carga en PostgreSQL.

## Verificación de esta entrega

- 111 pruebas Django: permisos, CSRF, cuenta, validación, rollback, cinco tipos de
  registro, recuperación de claves y reintentos idempotentes, más regresiones previas.
- 8 pruebas JavaScript de cifrado y sincronización; 6 del service worker.
- Navegador real con fixtures aislados: registrar con el servidor apagado, cerrar
  y reabrir, recuperar pendientes y sincronizar. Se simuló guardar en el servidor
  y perder la respuesta: el reintento no duplicó la entrada.
- Riego con dos plantas y nutrientes comprobado contra la base de pruebas.
- Cambio entre dos cuentas: pendientes separados y recuperables al volver.
- Revisión visual de Registrar en escritorio y a 390 px de ancho.
