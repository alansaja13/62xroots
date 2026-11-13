# API JSON v1

Referencia de la API JSON que vive en `growlog/api_views.py` y se enruta en `growlog/urls.py` bajo `api/v1/`. Cubre autenticación, permisos, convenciones y cada endpoint con sus parámetros, respuestas y efectos. Las reglas de acceso por cultivo están en [permisos.md](permisos.md); los modelos en [modelos.md](modelos.md); la lógica compartida con la web en [servicios.md](servicios.md).

## Autenticación

| Elemento | Detalle |
|---|---|
| Modelo | `APIToken` (`user`, `token_hash` único de 64 caracteres, `created_at`). Se guarda solo el SHA-256 hexadecimal del token. |
| Cabecera | `Authorization: Bearer <token>` |
| Verificación | Se calcula `sha256(token)` y se busca en `APIToken.token_hash`. El usuario dueño del token debe estar activo. |
| Creación | `python manage.py create_api_token <username>` (`growlog/management/commands/create_api_token.py`). El usuario debe existir. Genera `secrets.token_hex(32)` (64 caracteres hexadecimales), guarda el hash e imprime el token una sola vez. Un usuario puede tener varios tokens. |
| CSRF | Las vistas con escritura están marcadas `csrf_exempt`; la autenticación es solo por token. |

Respuestas de autenticación:

| Caso | Estado | `error` |
|---|---|---|
| Sin cabecera, sin prefijo `Bearer ` o token vacío | 401 | `Authentication required` |
| Hash inexistente o usuario inactivo | 401 | `Invalid token` |

## Permisos

El token actúa como su usuario. Para las rutas con `<slug>` o `<planta_uuid>`, `require_token` resuelve el cultivo entre los visibles del usuario (`cultivos_visibles`: propietario o miembro, cualquier rol). Si no existe o no es visible responde 404 (`Cultivo no encontrado` o `Planta no encontrada`), sin distinguir entre inexistente y ajeno.

| Rol en el cultivo | Métodos seguros (`GET`, `HEAD`, `OPTIONS`) | `POST`, `PATCH`, `DELETE` |
|---|---|---|
| Propietario | Sí | Sí |
| Miembro `editor` | Sí | Sí |
| Miembro `lector` | Sí | 403 `Tenés acceso de solo lectura a este cultivo` |

Las rutas sin cultivo en la URL (`/equipos/`, `/tarifas/`, `/nutrientes/`, `/parametros-ideales/`, `/cultivos/`) no hacen esta comprobación; sus reglas propias están en cada sección.

## Convenciones

### Formato de respuesta

Todas las respuestas son JSON.

```json
{"ok": true, "data": ...}
{"ok": false, "error": "mensaje"}
```

### Códigos de estado

| Estado | Cuándo |
|---|---|
| 200 | Lectura, modificación o borrado correcto |
| 201 | Creación correcta (`POST` que crea un registro) |
| 400 | Cuerpo inválido, campo faltante o fuera de rango, error de validación del modelo |
| 401 | Falta o es inválido el token |
| 403 | Rol `lector` en escritura, o recurso de energía que no es del usuario |
| 404 | Cultivo, planta o registro inexistente o no visible |
| 405 | Método no admitido por la ruta. En las vistas con `@require_GET` lo devuelve Django (no es JSON); en el resto, `{"ok": false, "error": "Method not allowed"}` |
| 409 | Conflicto de borrado (ver equipos y tarifas) |
| 429 | Límite de escrituras superado |

### Cuerpo de las peticiones

- `POST` y `PATCH` reciben un objeto JSON. Un cuerpo vacío se toma como `{}`. JSON inválido responde `Invalid JSON body`; un JSON que no es objeto responde `El cuerpo JSON debe ser un objeto`.
- `PATCH` modifica solo los campos presentes en el cuerpo. Los campos no enviados no cambian.
- En `POST` los campos opcionales ausentes toman el valor por defecto que se indica en cada tabla.
- Los campos que no figuran en las tablas se ignoran.

### Tipos de campo

| Tipo | Regla |
|---|---|
| Fecha | Cadena `YYYY-MM-DD`. Vacía o `null` equivale a ausente. |
| Hora | Cadena `HH:MM` o `HH:MM:SS`. |
| Decimal | Número o cadena numérica. Rechaza booleanos, `NaN` e infinitos. Se serializa en las respuestas como cadena (por ejemplo `"6.20"`). |
| Entero | Entero, flotante sin decimales o cadena numérica entera. Rechaza booleanos. |
| Booleano | `true`/`false`, `1`/`0`, o las cadenas `true`, `1`, `si`, `sí`, `yes`, `on` (verdadero) y `false`, `0`, `no`, `off`, vacía (falso), sin distinguir mayúsculas. Otro valor responde `<campo> debe ser true o false`. |
| Texto | Si es obligatorio: se recortan espacios, no puede quedar vacío y no puede superar el largo máximo (error). Si es opcional: se trunca al largo máximo sin error. |
| Opción | Debe ser una de las cadenas permitidas; si no, `<campo> inválido. Opciones: [...]`. |
| Uuid de planta | Cadena con el `uuid` de una planta activa del cultivo (`archivado=False` y `estado="activa"`). Si no se encuentra: `planta_uuid desconocido o archivado: <uuid>`. |

Además del chequeo de cada campo, los registros se validan con `full_clean()` del modelo (las mismas reglas que la web y Registrar). Un error de validación responde 400 con los mensajes unidos por `; `, con el formato `campo: mensaje`.

### Fechas y horas en las respuestas

Los campos de fecha hora (`timestamp`, `creado_en`, `completada_en`) se devuelven en ISO 8601 con zona horaria. Las fechas, en `YYYY-MM-DD`. Las horas, en `HH:MM:SS`.

### Paginación y filtros

No hay paginación: los listados devuelven todos los registros. Los únicos filtros por querystring son:

| Ruta | Parámetro | Efecto |
|---|---|---|
| `GET /cultivos/<slug>/tareas/` | `completada=true` o `completada=false` | Filtra por estado. Otro valor no filtra. |
| `GET /cultivos/<slug>/plantas/` | `archivado=false` | Excluye plantas archivadas. Otro valor no filtra. |

Los listados siguen el orden por defecto del modelo (generalmente el más reciente primero; ver [modelos.md](modelos.md)).

### Límite de escrituras

Cada token puede hacer 60 escrituras por hora. El contador vive en la caché (`api_writes_<hash>`, ventana de 3600 s desde la última escritura contada). Superado el límite responde 429 `Rate limit exceeded: 60 writes/hour`. Se cuentan los `POST` y `PATCH` apenas se lee el cuerpo (aunque después falle la validación), y los `DELETE` apenas se ejecutan. Las lecturas no cuentan.

### Rutas

Todas las rutas empiezan con `/api/v1/`. En esta referencia se omite ese prefijo.

## Cultivos

Solo lectura. No hay endpoints para crear, modificar ni borrar cultivos. Resumen de cultivo que se repite en las respuestas:

| Campo | Tipo |
|---|---|
| `id`, `slug`, `nombre` | entero, cadena, cadena |
| `estado` | cadena (`plantula`, `vegetativo`, `floracion`, `secado`, `curado`, `finalizado`) |
| `fecha_inicio` | fecha |
| `dias_desde_inicio` | entero |
| `lampara_watts_reales` | número |
| `sustrato`, `carpa_dimensiones` | cadena |

### `GET /cultivos/`

Cultivos visibles del usuario (propios y compartidos) con `archivado=False`. Devuelve una lista de resúmenes.

### `GET /cultivos/<slug>/`

Resumen más:

| Campo | Contenido |
|---|---|
| `notas` | Notas del cultivo |
| `plantas` | Plantas no archivadas, cada una `{id, uuid, apodo, strain, estado}` |
| `ultimos_riegos` | Hasta 5 riegos, sin nutrientes ni detalle por planta |
| `ultimas_mediciones` | Hasta 5 mediciones de ambiente |
| `ultimos_eventos` | Hasta 10 eventos |
| `tareas_pendientes` | Tareas con `completada=False` |
| `cambios_fotoperiodo` | Todos los cambios de fotoperiodo |

## Plantas

Un objeto planta completo contiene: `id`, `uuid`, `apodo`, `strain`, `estado`, `estado_display`, `posicion_tent`, `posicion_tent_display`, `dias_flora_estimados`, `indica_sativa_ratio`, `thc_estimado` (cadena), `yield_estimado_g`, `yield_real_g`, `fecha_corte`, `peso_humedo_g`, `fecha_seco`, `notas_genetica`, `archivado`.

### `GET /cultivos/<slug>/plantas/`

Todas las plantas del cultivo, con el parámetro opcional `archivado=false`.

### `POST /cultivos/<slug>/plantas/`

Crea una planta (201). El creador queda como `creado_por`.

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `apodo` | texto | Sí | | Máx. 60 |
| `strain` | texto | No | `""` | Máx. 120 |
| `posicion_tent` | opción | No | `otro` | `centro`, `arriba_izq`, `arriba_der`, `abajo_izq`, `abajo_der`, `otro` |
| `estado` | opción | No | `activa` | `activa`, `descartada`, `cosechada` |
| `dias_flora_estimados` | entero | No | | 0 a 32767 |
| `indica_sativa_ratio` | texto | No | `""` | Máx. 20 |
| `thc_estimado` | decimal | No | | 0 a 100 |
| `yield_estimado_g` | entero | No | | 0 a 32767 |
| `yield_real_g` | entero | No | | 0 a 32767 |
| `notas_genetica` | texto | No | `""` | Máx. 2000 |
| `archivado` | booleano | No | `false` | |

Los campos `fecha_corte`, `peso_humedo_g`, `fecha_seco` y `tipo` de la planta no se pueden escribir por la API. La creación por API no registra cambio de etapa.

### `GET /plantas/<uuid>/`

Planta completa más `cultivo` (`{id, slug, nombre}`), `mediciones` (todas las mediciones de planta) y `riegos` (hasta los 20 detalles de riego más recientes: fila de riego por planta más `riego_id` y `timestamp` del riego).

### `PATCH /plantas/<uuid>/`

Mismos campos que el `POST`. Devuelve la planta completa.

### `DELETE /plantas/<uuid>/`

Cuenta como escritura. Si la planta tiene historial (detalles de riego, mediciones, cambios de etapa, posiciones de cola de canopy o eventos), no se borra: se marca `archivado=True` y responde `{"archived": "<uuid>"}`. Si no tiene historial, se borra y responde `{"deleted": "<uuid>"}`.

### Mediciones de planta

Objeto: `id`, `fecha`, `altura_cm`, `nudos_count`, `ancho_canopy_cm`, `aspecto_general`, `sintomas`. La API no sube ni devuelve fotos.

| Método y ruta | Efecto |
|---|---|
| `GET /plantas/<uuid>/mediciones/` | Lista las mediciones de la planta |
| `POST /plantas/<uuid>/mediciones/` | Crea una medición (201) |
| `GET /plantas/<uuid>/mediciones/<id>/` | Una medición |
| `PATCH /plantas/<uuid>/mediciones/<id>/` | Modifica campos presentes |
| `DELETE /plantas/<uuid>/mediciones/<id>/` | Borra la medición (`{"deleted": id}`) |

Campos de escritura:

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `fecha` | fecha | En `POST` se completa sola si falta | Fecha local de hoy | |
| `altura_cm` | decimal | No | | Mayor o igual que 0 |
| `nudos_count` | entero | No | | 0 a 32767 |
| `ancho_canopy_cm` | decimal | No | | Mayor o igual que 0 |
| `aspecto_general` | opción | No | `bueno` | `bueno`, `regular`, `malo` |
| `sintomas` | texto | No | `""` | Máx. 2000 |

## Riegos

Objeto riego: `id`, `timestamp`, `volumen_total_ml`, `volumen_por_planta_ml`, `ph_agua`, `ec_solucion`, `buscar_runoff`, `runoff_observado`, `notas`, `nutrientes_aplicados` y `detalle_plantas`. En el resumen de `GET /cultivos/<slug>/` esos dos últimos no se incluyen.

Detalle por planta (`detalle_plantas[]`): `id`, `planta` (`{uuid, apodo}`), `volumen_ml`, `runoff_observado`, `ph_runoff`, `ec_runoff`, `notas`.

Nutriente aplicado (`nutrientes_aplicados[]`): `id`, `nutriente_id`, `nutriente` (nombre), `dosis_g_por_litro`, `dosis` (mismo valor), `unidad` (`g/L` o `ml/L`). La dosis es por litro en la unidad del nutriente.

La EC se envía y se recibe en mS/cm (1.2 es 1200 µS/cm). El máximo aceptado es 20.

### `GET /cultivos/<slug>/riegos/`

Lista de riegos con nutrientes y detalle por planta.

### `POST /cultivos/<slug>/riegos/`

Crea un riego (201). Todo se guarda en una transacción con `guardar_riego` (ver [servicios.md](servicios.md)).

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `detalle_plantas` | lista de objetos | Sí (al menos uno) | | Ver abajo |
| `nutrientes` | lista de objetos | No | `[]` | Ver abajo |
| `ph_agua` | decimal | No | | 0 a 14 |
| `ec_solucion` | decimal | No | | 0 a 20 |
| `buscar_runoff` | booleano | No | `false` | |
| `notas` | texto | No | `""` | Máx. 500 |

Cada elemento de `detalle_plantas`:

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `planta_uuid` | cadena | Sí | | Planta activa del cultivo; no puede repetirse |
| `volumen_ml` | entero | Sí | | Mayor o igual que 1 |
| `runoff_observado` | booleano | No | `false` | |
| `ph_runoff` | decimal | No | | 0 a 14 |
| `ec_runoff` | decimal | No | | 0 a 20 |
| `notas` | texto | No | `""` | Máx. 500 |

Cada elemento de `nutrientes`:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `nutriente_id` | entero | Sí | Debe estar en `nutrientes_para(usuario, cultivo)`: catálogo compartido, propios y los del propietario del cultivo, sin ocultos. Si no: `nutriente_id <id> no existe` |
| `dosis_g_por_litro` | decimal | Sí | Mayor que 0. También se acepta la clave `dosis`. |

Efectos: `volumen_total_ml` se calcula como la suma de los `volumen_ml`; `creado_por` queda como el usuario del token; `timestamp` es el momento de la creación. Una planta repetida, o una planta de otro cultivo, responde 400.

### `GET /cultivos/<slug>/riegos/<id>/`

Un riego completo.

### `PATCH /cultivos/<slug>/riegos/<id>/`

Modifica solo `ph_agua`, `ec_solucion`, `buscar_runoff` y `notas`. No cambia detalle por planta ni nutrientes.

### `DELETE /cultivos/<slug>/riegos/<id>/`

Borra el riego con sus detalles y nutrientes aplicados. Responde `{"deleted": id}`.

### Detalle por planta de un riego

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/riegos/<id>/plantas/` | Lista los detalles |
| `POST /cultivos/<slug>/riegos/<id>/plantas/` | Agrega una fila (201). Campos: `planta_uuid` (obligatorio) más los de detalle. Si la planta ya tiene fila en ese riego: 400 y hay que usar `PATCH`. |
| `GET /cultivos/<slug>/riegos/<id>/plantas/<rp_id>/` | Una fila |
| `PATCH /cultivos/<slug>/riegos/<id>/plantas/<rp_id>/` | Modifica `volumen_ml`, `runoff_observado`, `ph_runoff`, `ec_runoff`, `notas` presentes |
| `DELETE /cultivos/<slug>/riegos/<id>/plantas/<rp_id>/` | Quita la fila (`{"deleted": rp_id}`). Si es la última del riego: 400 y hay que borrar el riego |

Cada alta, cambio o baja reescribe el desglose completo con `guardar_riego`, de modo que `volumen_total_ml` del riego se recalcula como la suma de las filas. El `PATCH` ignora `planta_uuid`.

### Nutrientes aplicados de un riego

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/riegos/<id>/nutrientes/` | Lista |
| `POST /cultivos/<slug>/riegos/<id>/nutrientes/` | Agrega un nutriente (201). Campos: `nutriente_id`, `dosis_g_por_litro` (o `dosis`), con las mismas reglas que en el alta del riego |
| `DELETE /cultivos/<slug>/riegos/<id>/nutrientes/<na_id>/` | Quita el nutriente aplicado (`{"deleted": na_id}`). No hay `GET` ni `PATCH` en esta ruta (405) |

## Ambiente

Objeto: `id`, `timestamp`, `temperatura_c` (cadena), `humedad_relativa` (cadena), `vpd` (número en kPa, calculado, no se guarda), `vpd_estado`, `luz_estado` (`on`/`off`/`null`), `luz_estado_display`, `notas`. `vpd_estado` se calcula con los rangos de `ParametroIdeal` de la etapa vigente a la fecha de la medición, y es `null` si no hay etapa o rango cargado.

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/mediciones/` | Lista |
| `POST /cultivos/<slug>/mediciones/` | Crea (201) |
| `GET`, `PATCH`, `DELETE /cultivos/<slug>/mediciones/<id>/` | Lectura, modificación y borrado |

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `temperatura_c` | decimal | Sí | 0 a 60 |
| `humedad_relativa` | decimal | Sí | 0 a 100 |
| `notas` | texto | No | Máx. 500 |

Efectos: el `timestamp` es el momento de la creación (no se puede enviar). Al guardar por primera vez, `luz_estado` se calcula según el fotoperiodo vigente a ese momento. `creado_por` es el usuario del token.

## EC y pH

Objeto: `id`, `timestamp`, `tipo`, `tipo_display`, `ph`, `ec`, `temp_agua`, `notas` (decimales como cadena, `null` si faltan).

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/mediciones-ec/` | Lista |
| `POST /cultivos/<slug>/mediciones-ec/` | Crea (201) |
| `GET`, `PATCH`, `DELETE /cultivos/<slug>/mediciones-ec/<id>/` | Lectura, modificación y borrado |

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `tipo` | opción | No | `solucion` | `entrada`, `solucion`, `runoff`, `sustrato` |
| `ph` | decimal | No | | 0 a 14 |
| `ec` | decimal | No | | 0 a 20, en mS/cm |
| `temp_agua` | decimal | No | | 0 a 60 |
| `notas` | texto | No | `""` | Máx. 500 |

El `timestamp` es el de la creación. `creado_por` es el usuario del token.

## Eventos y seguimientos

Objeto: `id`, `timestamp`, `tipo`, `tipo_display`, `descripcion`, `plantas_afectadas` (lista de apodos), `follow_up_fecha`, `follow_up_resuelto`. La descripción del seguimiento (`follow_up_descripcion`) se escribe pero no se devuelve.

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/eventos/` | Lista |
| `POST /cultivos/<slug>/eventos/` | Crea (201) |
| `GET`, `PATCH`, `DELETE /cultivos/<slug>/eventos/<id>/` | Lectura, modificación y borrado |
| `POST /cultivos/<slug>/eventos/<id>/resolver-followup/` | Marca `follow_up_resuelto=true` y devuelve el evento. No lleva cuerpo. Cuenta como escritura. Cualquier otro método: 405 |

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `tipo` | opción | Sí | `topping`, `lst`, `defoliacion`, `transplante`, `problema`, `diagnostico`, `ajuste_ambiente`, `cambio_ciclo`, `nota`, `otro` |
| `descripcion` | texto | Sí | Máx. 2000 |
| `follow_up_fecha` | fecha | No | |
| `follow_up_descripcion` | texto | No | Máx. 500 |
| `follow_up_resuelto` | booleano | No | Por defecto `false` |
| `plantas_afectadas` | lista de uuids | No | Plantas activas del cultivo. En `PATCH`, si se envía reemplaza el conjunto; si se omite no cambia |

`tipo` no tiene valor por defecto: en `PATCH` solo se valida si viene. El `timestamp` es el de la creación.

## Tareas

Objeto: `id`, `titulo`, `descripcion`, `prioridad`, `categoria`, `fecha_objetivo`, `completada`, `completada_en`.

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/tareas/` | Lista; filtro `completada=true` o `completada=false` |
| `POST /cultivos/<slug>/tareas/` | Crea (201) |
| `GET`, `PATCH`, `DELETE /cultivos/<slug>/tareas/<id>/` | Lectura, modificación y borrado |

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `titulo` | texto | Sí | | Máx. 200 |
| `descripcion` | texto | No | `""` | Máx. 1000 |
| `prioridad` | opción | No | `normal` | `urgente`, `normal`, `baja` |
| `categoria` | opción | No | `observacion` | `riego`, `training`, `mantenimiento`, `compra`, `observacion` |
| `fecha_objetivo` | fecha | No | | |
| `completada` | booleano | Solo en `PATCH` | | Al marcarla, `completada_en` toma la hora actual; al desmarcarla vuelve a `null` |

`POST` ignora `completada`.

## Fotoperíodo

Objeto: `id`, `fotoperiodo`, `hora_lights_on`, `fecha_inicio`, `notas`.

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/cambios-fotoperiodo/` | Lista |
| `POST /cultivos/<slug>/cambios-fotoperiodo/` | Crea (201) |
| `GET`, `PATCH`, `DELETE /cultivos/<slug>/cambios-fotoperiodo/<id>/` | Lectura, modificación y borrado |

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `fotoperiodo` | texto | Sí | Máx. 5. Formato `N/M` con enteros positivos que suman 24 (por ejemplo `18/6`, `12/12`) |
| `hora_lights_on` | hora | Sí | |
| `fecha_inicio` | fecha | Sí | Única por cultivo: dos cambios no pueden compartir fecha |
| `notas` | texto | No | Máx. 500 |

## Canopy

Un snapshot serializado tiene: `id`, `creado_en`, `scrog_fill_pct`, `scrog_cells`, `notas` y `plantas`. Cada elemento de `plantas` (plantas no archivadas del cultivo, ordenadas por apodo) contiene `uuid`, `apodo`, `centro_tent` (`{x, y}` según la posición de la planta en la carpa; `0.5, 0.5` si no hay coordenadas) y `colas` (`[{indice, x, y}]` del snapshot).

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/canopy/` | Último snapshot, o `data: null` si no hay ninguno |
| `POST /cultivos/<slug>/canopy/` | Crea un snapshot (201) y devuelve el snapshot |
| `GET /cultivos/<slug>/canopy/history/` | Lista resumida de snapshots: `id`, `creado_en`, `scrog_fill_pct`, `notas`. Solo `GET` |
| `GET /cultivos/<slug>/canopy/<snapshot_id>/` | Un snapshot completo. Solo `GET` |

Campos del `POST`:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `colas` | lista de objetos | No | Cada uno: `planta_uuid` (planta activa del cultivo), `indice` (entero, mínimo 0), `x` e `y` (decimales de 0 a 1). Una combinación `(planta, indice)` repetida es un error |
| `scrog_cells` | lista de enteros | No | Se conservan los valores de 0 a 35 (grilla de 36 celdas) y se descartan los demás. Si queda al menos uno, `scrog_fill_pct` se calcula como `round(cantidad / 36 * 100)` y reemplaza al valor enviado |
| `scrog_fill_pct` | entero | No | 0 a 100. Por defecto 0. Solo vale si `scrog_cells` queda vacío |
| `notas` | texto | No | Máx. 500 |

## Nutrientes y parámetros ideales

Solo lectura.

### `GET /nutrientes/`

Nutrientes visibles para el usuario (`nutrientes_visibles`: catálogo compartido, propios y los de los propietarios de los cultivos a los que tiene acceso; sin ocultos). Campos: `id`, `nombre`, `marca`, `npk`, `etapa_recomendada` (`veg`, `flora`, `aditivo`), `etapa_recomendada_display`, `dosis_recomendada_min`, `dosis_recomendada_max`, `unidad` (`g/L` o `ml/L`).

### `GET /parametros-ideales/`

Todas las filas de `ParametroIdeal`. Campos: `etapa`, `etapa_display`, `temp_min`, `temp_max`, `hr_min`, `hr_max`, `ph_min`, `ph_max`, `ec_min`, `ec_max`, `vpd_min`, `vpd_max`, `horas_luz`, `distancia_luz_min`, `distancia_luz_max`. Los valores decimales son cadenas; `ec_min` y `ec_max` pueden ser `null`.

## Energía

### Reglas de acceso de equipos y tarifas

`/equipos/` y `/tarifas/` no cuelgan de un cultivo.

- Lectura: los recursos propios más los vinculados por un costo energético a cualquier cultivo visible para el usuario.
- Alta: el recurso queda con `propietario` igual al usuario del token.
- `PATCH`, `DELETE` (y cualquier método no seguro sobre `/<id>/`, incluso uno no admitido): solo el propietario (403 `Solo el propietario puede modificar este equipo` o `esta tarifa`), y solo si el recurso no está asignado a un cultivo que el usuario no pueda editar (403 `No podés modificar ...: se usa en un cultivo que no podés editar`).

### Equipos

Objeto: `id`, `nombre`, `categoria`, `categoria_display`, `watts` (cadena), `horas_dia` (cadena), `kwh_mes`, `activo`, `notas`. `kwh_mes` es `watts / 1000 * horas_dia * 30`. En el listado se agrega `costo_mes` (`kwh_mes` por el precio de la tarifa vigente del usuario) solo si hay una tarifa vigente.

| Método y ruta | Efecto |
|---|---|
| `GET /equipos/` | Lista, con `costo_mes` |
| `POST /equipos/` | Crea (201) |
| `GET /equipos/<id>/` | Un equipo |
| `PATCH /equipos/<id>/` | Modifica campos presentes |
| `DELETE /equipos/<id>/` | Borra. Si el equipo tiene historial de costos: 409 `No se puede eliminar un equipo con historial de costos; desactivalo` (cuenta como escritura). Hay que desactivarlo con `PATCH` y `activo=false` |

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `nombre` | texto | Sí | | Máx. 120 |
| `categoria` | opción | Sí | | `lampara`, `extractor`, `ventilador`, `humidificador`, `otro` |
| `watts` | decimal | Sí | | Mayor que 0 |
| `horas_dia` | decimal | Sí | | Mayor que 0 y hasta 24 |
| `activo` | booleano | No | `true` | |
| `notas` | texto | No | `""` | Máx. 500 |

### Tarifas

Objeto: `id`, `fecha_desde`, `precio_kwh` (cadena), `distribuidora`.

| Método y ruta | Efecto |
|---|---|
| `GET /tarifas/` | Lista |
| `POST /tarifas/` | Crea (201) |
| `GET /tarifas/<id>/` | Una tarifa |
| `PATCH /tarifas/<id>/` | Modifica campos presentes |
| `DELETE /tarifas/<id>/` | Borra. Si algún costo energético la referencia: 409 `No se puede eliminar: hay costos energéticos que referencian esta tarifa` |

| Campo | Tipo | Obligatorio | Por defecto | Regla |
|---|---|---|---|---|
| `fecha_desde` | fecha | Sí | | |
| `precio_kwh` | decimal | Sí | | Mayor que 0 |
| `distribuidora` | texto | No | `Edesur` | Máx. 100 |
| `notas` | texto | No | `""` | Máx. 500 (se acepta, la respuesta no la incluye) |

### Asignación de equipos a un cultivo (costos energéticos)

Objeto: `id`, `equipo` (objeto equipo, sin `costo_mes`), `tarifa_id`, `fecha_desde`, `fecha_hasta` (`null` si está vigente).

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/costos/equipos/` | Lista de asignaciones |
| `POST /cultivos/<slug>/costos/equipos/` | Asigna un equipo (201) |
| `GET /cultivos/<slug>/costos/equipos/<costo_id>/` | Una asignación |
| `PATCH /cultivos/<slug>/costos/equipos/<costo_id>/` | Solo acepta `fecha_hasta` (fecha) para cerrar la vigencia |
| `DELETE /cultivos/<slug>/costos/equipos/<costo_id>/` | Borra la asignación |

Campos del `POST`:

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `equipo_id` | entero | Sí | Equipo propio o ya vinculado a este cultivo (`equipos_asignables`). Si no: `equipo_id es requerido y debe existir` |
| `fecha_desde` | fecha | Sí | |

La tarifa se asigna sola: la más reciente con `fecha_desde` menor o igual que hoy, entre las tarifas del cultivo (si quien llama es el propietario, entre sus tarifas y las usadas por el cultivo). Si no hay ninguna: 400 `No hay tarifa eléctrica cargada. Creá una en /api/v1/tarifas/ primero`.

### Lecturas de medidor

Objeto: `id`, `fecha`, `kwh_real` (cadena), `notas`.

| Método y ruta | Efecto |
|---|---|
| `GET /cultivos/<slug>/lecturas-medidor/` | Lista |
| `POST /cultivos/<slug>/lecturas-medidor/` | Crea (201) |
| `GET`, `PATCH`, `DELETE /cultivos/<slug>/lecturas-medidor/<lectura_id>/` | Lectura, modificación y borrado |

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `fecha` | fecha | Sí | |
| `kwh_real` | decimal | Sí | Mayor o igual que 0 |
| `notas` | texto | No | Máx. 500 (se acepta, la respuesta no la incluye) |

### Costos calculados (solo `GET`)

Se calculan con las asignaciones del cultivo, las tarifas del cultivo con `fecha_desde` menor o igual que hoy y la fecha local de hoy. Un mes usa la tarifa más reciente vigente al día 1 de ese mes; cada asignación aporta `watts / 1000 * horas_dia * días` por los días del mes en que está vigente (desde el mayor entre el inicio del cultivo y su `fecha_desde`, hasta el menor entre fin de mes, hoy y su `fecha_hasta`).

`GET /cultivos/<slug>/costos/`:

| Campo | Contenido |
|---|---|
| `cultivo` | slug |
| `tarifa_vigente` | Objeto tarifa o `null` |
| `ciclo` | Fotoperiodo activo hoy: el último `CambioFotoperiodo` con fecha menor o igual que hoy; si no hay, `12/12` cuando el cultivo está en floración y tiene plantas fotoperiódicas activas, y `18/6` en el resto |
| `equipos` | Equipos de las asignaciones sin `fecha_hasta`, con `costo_mes` |
| `totales.kwh_mes`, `totales.costo_mes` | Suma de esos equipos (el costo es 0 sin tarifa) |
| `totales.kwh_acumulado`, `totales.costo_acumulado` | Suma del desglose mensual desde el inicio del cultivo |
| `totales.costo_por_gramo_estimado` | `costo_acumulado` dividido por la suma de `yield_estimado_g` de las plantas no archivadas, redondeado a 2 decimales; `null` si la suma es 0 |

`GET /cultivos/<slug>/costos/historico/`: `cultivo`, `fecha_inicio`, `meses` y `totales` (`kwh_estimado`, `costo_estimado`). Cada mes: `mes` (`YYYY-MM`), `dias`, `kwh_estimado`, `costo_estimado`, `tarifa` (precio o `null`).

`GET /cultivos/<slug>/costos/comparacion/`: compara lo estimado con las lecturas de medidor. Si el cultivo no tiene lecturas responde 404 `No hay lecturas de medidor cargadas para este cultivo`. Campos: `cultivo`, `kwh_estimado`, `kwh_real` (suma de todas las lecturas), `costo_estimado`, `costo_real` (`kwh_real` por la tarifa más reciente vigente, `null` sin tarifa), `variacion_pct` (`(real - estimado) / estimado * 100`, `null` si el estimado es 0), `alerta` (`true` si `kwh_real` supera en más de 15 % al estimado) y `lecturas`.
