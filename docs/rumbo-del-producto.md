# 62xroots: rumbo del producto

## Propósito

Una bitácora de cultivo que permita registrar lo que pasó, reconocer lo que
requiere atención y aprender de cada ciclo. El registro cotidiano debe ser
rápido, confiable y cómodo desde el teléfono.

## Principios

- Conservar los registros y su contexto histórico.
- Mostrar claramente si un dato es medido, estimado, antiguo o desconocido.
- Web y API aplican los mismos permisos y reglas. El admin es mantenimiento
  global reservado a superusuarios, con responsabilidad explícita sobre datos ajenos.
- Ante un error, conservar lo escrito y explicar cómo corregirlo.
- La PWA debe distinguir entre borrador local, pendiente y guardado confirmado.
- Evolucionar Django, templates, HTMX y Alpine de forma incremental.
- Evitar cambios de estructura que no mejoren un flujo o protejan datos.

## Decisiones de producto confirmadas

1. **Acceso por cultivo:** cada persona ve los cultivos que le comparten y
   edita únicamente donde tiene permiso de escritura. Ser autor y tener acceso
   son conceptos distintos. Esta política debe abarcar API y notificaciones.
2. **Registro offline:** permitir registrar y guardar pendientes en el
   dispositivo, con sincronización al reconectar. Preservar la hora de la
   observación; comprobar permisos al sincronizar; identificar cada operación
   para que los reintentos no creen duplicados. Informar conflictos sin descartar
   silenciosamente los pendientes.

Confirmadas por el usuario el 21/09/2026. Queda por resolver el significado de
las lecturas energéticas existentes (acumulado o consumo de período) antes de
transformar históricos.

## Etapas y criterios de aceptación

### 1. Base confiable

- [x] Aplicar una política de permisos explícita a todos los canales del código.
- [x] Rechazar tokens de usuarios inactivos.
- [ ] Guardar riegos y snapshots de forma atómica.
- [x] Mantener plantas archivadas en la edición de registros históricos.
- [ ] Unificar validaciones e informar errores sin perder entradas.
- [x] Separar backups privados de media en la configuración y el comando.
- [ ] Verificar storage remoto privado, persistencia y restauración de backups.
- [x] Mantener pruebas de regresión ejecutables sin usar datos reales.

Criterio: una entrada inválida nunca deja un registro parcial; un lector no
puede escribir; desactivar un usuario revoca también el acceso con token.

### 2. Historia y cálculos coherentes

- [ ] Separar etapa observada, estado administrativo y planificación.
- [ ] Evaluar mediciones con el contexto de su fecha.
- [ ] Detener duración y estimaciones al finalizar un ciclo.
- [ ] Resolver semántica energética y versionar configuración por vigencia.
- [ ] Eliminar consultas por cada medición y paginar historiales completos.

Criterio: cambiar la configuración actual no reinterpreta silenciosamente el
pasado; todos los registros pueden encontrarse con filtros y paginación.

### 3. Experiencia cotidiana: Hoy y Registrar

- [x] Priorizar pendientes y frescura de datos en el resumen.
- [ ] Unificar navegación y nombres de acciones.
- [x] Registrar riego, plantas y nutrientes en un flujo completo.
- [ ] Consolidar tipografía, contraste, formularios y estados accesibles.
- [ ] Validar teléfono, teclado, errores y conectividad intermitente.

Criterio: registrar una observación no exige comprender la organización
interna del sistema; los errores conservan la información y el contexto.

### 4. PWA confiable

- [x] Definir almacenamiento local y límites de privacidad por usuario.
- [x] Mostrar conexión, borradores, pendientes y confirmaciones.
- [x] Agregar idempotencia antes de habilitar reintentos de escritura.
- [x] Resolver conflictos y cambios de sesión explícitamente.
- [x] Probar pérdida de conexión, cierre y reapertura, y reenvíos duplicados.

Criterio: ningún registro se pierde ni se duplica silenciosamente; cerrar
sesión no deja datos accesibles a la siguiente persona.

### 5. Aprendizaje entre ciclos

- [ ] Conectar observación, intervención, seguimiento y resultado.
- [ ] Hacer del canopy un mapa histórico con dimensiones explícitas.
- [ ] Evaluar separar espacio físico y ciclo cuando los flujos lo requieran.

## Forma de trabajo

Cada entrega debe incluir comportamiento verificable, pruebas relevantes,
estado de migración y límites conocidos. No desplegar ni migrar datos reales
como parte de una prueba local. Un despliegue posterior debe tener revisión de
compatibilidad, backup privado y una estrategia de reversión.

## Entrega inicial — 21/09/2026

Implementado y verificado:

- Bloqueo del POST de energía para invitados y de tokens de usuarios inactivos.
- Validación del objeto JSON de entrada en la API.
- Servicio compartido y transaccional para alta de riegos por web/API y edición
  completa por web, incluyendo validación de plantas duplicadas y pertenencia.
- Conservación de plantas archivadas y nutrientes al editar un riego histórico.
- Validación de humedad/temperatura en registro rápido y de pH/EC en solución
  y drenaje de las sesiones de riego.
- Formularios rápidos con destino explícito, valores conservados, IDs distintos
  y pestaña activa al mostrar errores. Se utilizan POST normales porque el éxito
  ya navegaba a otra pantalla; las interacciones parciales existentes conservan HTMX.
- Normalización decimal limitada a controles numéricos, preservando las comas
  de los textos enviados con HTMX.
- Settings de pruebas aislados y 16 regresiones nuevas: 54 tests pasan.
- Verificación de migraciones: no hay cambios de esquema pendientes.

Esta entrega no completa la etapa 1. Siguen pendientes las membresías por
cultivo, snapshots atómicos, la alineación de escrituras individuales/admin,
backups privados y la cobertura del resto de las validaciones. No incorpora aún
sincronización offline, cambios de cálculos históricos ni el rediseño visual.
No se modificaron datos reales ni se desplegaron cambios.

La siguiente entrega debe implementar acceso por cultivo de forma completa
(consultas, escrituras, invitaciones, recursos de energía y notificaciones),
antes de permitir que una cola offline sincronice registros.

## Segunda entrega — 22/09/2026

Implementados propietarios, roles por cultivo y panel para compartir, modificar
permisos y revocar sin borrar cuentas. Web, API, fotos, energía y recordatorios
usan permisos por cultivo; staff deja de ser un permiso global. El admin queda
reservado a superusuarios. Se aislaron backups y se retiró la caché de HTML privado.

El detalle de comportamiento, migraciones y límites está en
[acceso-por-cultivo.md](acceso-por-cultivo.md). Las migraciones se probaron en una
base aislada; no se aplicaron a datos reales ni se cambió infraestructura remota.
La privacidad del bucket existente requiere verificación externa antes de la
puesta en uso. La pantalla de compartir se revisó en escritorio y móvil.

Verificación final: 86 pruebas Django y 5 pruebas JavaScript del service worker
pasan; no hay cambios de modelo sin migración y `git diff --check` no informa errores.

Al cierre de esta segunda entrega seguían pendientes la cola offline y el rediseño
general de Hoy/Registrar. La siguiente entrega incorpora Registrar.

## Tercera entrega — 24/09/2026

Registrar incorpora un formulario adaptable a móvil para ambiente, observaciones,
pH/EC, tareas y riegos con plantas y nutrientes. El guardado local cifrado precede
al envío. Borradores, pendientes, errores y confirmaciones tienen estados visibles;
los reintentos conservan identidad y el servidor evita duplicar operaciones.

Se verificaron desconexión real, cierre/reapertura, respuesta perdida después de
guardar y separación entre cuentas. Pasan 111 pruebas Django, 8 de sincronización
y cifrado y 6 del service worker. La interfaz se revisó en escritorio y móvil.
Las migraciones 0026/0027 están preparadas, sin aplicar a datos reales.

Alcance, arquitectura y límites: [registro-offline.md](registro-offline.md).
La sincronización requiere abrir Registrar; fotos e historial completo requieren
conexión. El almacenamiento del navegador no sustituye un backup y los conflictos
se conservan para corrección o revisión explícita.

El rediseño completo continúa pendiente: resumen Hoy, coherencia de históricos,
rendimiento y escrituras de dominio restantes. La verificación del storage privado
y la restauración de backups siguen siendo requisitos de puesta en producción.

## Cuarta entrega — 24/09/2026

El inicio pasa a ser **Hoy**. Reúne tareas vencidas, de hoy y urgentes, junto con
seguimientos pendientes de los cultivos activos visibles. Muestra hasta 12 elementos
con el total real y accesos a las listas completas. Las tareas futuras y sin fecha
no desaparecen: se contabilizan y siguen disponibles dentro de cada cultivo.

Las tarjetas distinguen ambiente medido hoy, anterior, con fecha futura o sin datos.
La fecha es local y se muestra explícitamente; el VPD se identifica como calculado.
No se califica una medición histórica usando la etapa actual ni se presenta como
monitoreo en vivo. «Anterior a hoy» describe antigüedad, no un umbral agronómico.
Las estimaciones energéticas quedan en su pantalla, accesible desde cada tarjeta.

Registrar tiene un acceso principal y accesos por cultivo para quienes pueden
editar. Los lectores conservan acceso a pendientes e historial. Finalizados y
archivados quedan separados de la atención diaria; el inicio muestra sus fechas
sin seguir incrementando un contador de días de ciclo cerrado.

La lectura se extrajo a `services/hoy.py`. La última medición se obtiene con una
subconsulta con desempate por ID; plantas y permisos se resuelven en conjunto.
Las listas de atención tienen límite en SQL. Una regresión comprueba que pasar
de uno a nueve cultivos no aumenta las consultas (8 para ese escenario).
El listado de cultivos aún no está paginado; esa limitación permanece explícita.

Verificación: 8 pruebas nuevas de fechas, permisos, revocación, cierre, ausencia
de datos, orden, límites y consultas; revisión en navegador a 390 px y escritorio.
Hoy muestra información sincronizada y deriva a Registrar para los pendientes
locales. No añade migraciones ni modifica datos reales. Siguen pendientes la
coherencia histórica en otras vistas, la paginación y las escrituras de dominio.

## Preparación de publicación — 24/09/2026

La auditoría autorizada sobre PostgreSQL se ejecutó con lectura forzada. No encontró
propietarios faltantes o inactivos ni recursos de energía ambiguos. Las migraciones
0024–0027 siguen pendientes en producción. El usuario confirmó que las cuentas 2 y 3
no deben recibir membresías; se conservarán sus cuentas y registros anteriores.

El comando de backup rechaza rutas filesystem fuera del volumen declarado de
Railway antes de exportar. La restauración de fixtures en la base de pruebas conserva
propietarios, miembros, claves y recibos. Pasan 125 pruebas Django. Esto no reemplaza
el ensayo con un backup consistente de PostgreSQL ni la verificación del storage real.

Se preparó una configuración separada para recordatorios, aún sin activar. Los
pendientes externos y el procedimiento están en
[puesta-en-produccion.md](puesta-en-produccion.md). El push a la rama de producción
sigue condicionado a completar el ensayo y preparar almacenamiento persistente.

Posteriormente se completó el ensayo autorizado con un backup real de PostgreSQL:
restauración en una base temporal vacía, migraciones 0024–0027 y comparación por hash
de 23 tablas originales sin alteraciones. Se verificaron permisos y respuestas web
en la copia. Producción sigue sin migrar. Restan storage privado/persistente,
configuración de recordatorios y backup final al publicar; ver el procedimiento.

El 25/09 se cerró la preparación de infraestructura: R2 autenticado operativo,
HEAD anónimo de una foto con resultado 403, volumen `/data` para backups con copia
verificada y backup actualizado. La credencial R2 inicialmente reportada ausente
sí estaba presente en ejecución. Se eliminó del `railway.toml` común el arranque
web que sobrescribía el cron; los comandos específicos ya existen en Railway.
La corrección se aplicará al subir el código. La base real no recibió las migraciones
nuevas. El servidor de ensayo quedó detenido; sus datos permanecen en el volumen.
