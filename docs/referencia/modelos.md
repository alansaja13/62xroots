# Modelos

Describe los modelos de datos de `growlog/models.py`: campos, relaciones, propiedades calculadas y reglas. Los modelos están agrupados por dominio. La lógica que los usa está en [servicios.md](servicios.md) y las reglas de acceso en [permisos.md](permisos.md).

Convenciones generales:

- Todos los modelos viven en la app `growlog`.
- `creado_por` (cuando existe) es un `ForeignKey` a `User` con `SET_NULL`: quién cargó el registro.
- Los textos libres se llaman `notas` y son opcionales.
- La EC se guarda siempre en mS/cm (ver [Unidades de EC](#unidades-de-ec)).
- Las horas de luz y el estado de la luz se calculan con la zona horaria `America/Argentina/Buenos_Aires` (`ARGENTINA_TZ` en `growlog/utils.py`).

## Cultivo y acceso

### Cultivo

Ciclo de cultivo (carpa o cuarto). Es la raíz de la que cuelgan casi todos los demás datos.

| Campo | Tipo | Significado |
|---|---|---|
| `nombre` | texto (120) | Nombre del cultivo. |
| `slug` | slug (140), único | Identificador de las URLs. Se genera solo en `save()`. |
| `fecha_inicio` | fecha | Día 0 del cultivo. |
| `fecha_fin` | fecha, opcional | Fecha de cierre. La fija la cosecha guiada al cerrar. |
| `carpa_dimensiones` | texto (80) | Medidas en cm, por ejemplo `80x80x180`. `utils.area_carpa_m2` lo interpreta. |
| `sustrato` | texto (120) | Sustrato usado. |
| `lampara_watts_reales` | entero chico, opcional | Watts reales de la lámpara. Se usa para g/W y para estimar kWh. |
| `lampara_modelo` | texto (120) | Modelo de la lámpara. |
| `estado` | elección, por defecto `vegetativo` | `plantula`, `vegetativo`, `floracion`, `secado`, `curado`, `finalizado`. Es derivado de la etapa (ver reglas). |
| `dias_veg_estimados` | entero chico, opcional | Días totales esperados de vegetativo desde el inicio. |
| `dias_flora_estimados` | entero chico, opcional | Días esperados de floración. |
| `fecha_inicio_flora` | fecha, opcional, no editable | Primera etapa de flora del cultivo. Calculada. |
| `notas` | texto | Notas generales. |
| `archivado` | booleano | Oculta el cultivo de las listas activas. |
| `creado_en` | fecha y hora, automática | Alta del registro. |
| `creado_por` | FK `User` | Quién lo creó. Relación inversa `cultivos_creados`. |
| `propietario` | FK `User` | Dueño del cultivo. Relación inversa `cultivos_propios`. |

Orden por defecto: `-fecha_inicio`.

Reglas:

- **Slug.** Si está vacío, `save()` lo arma con `slugify(nombre)`. Si el nombre no tiene letras ni números, usa `cultivo`. Si el slug ya existe agrega `-2`, `-3`, etc.
- **Propietario.** Al crear (`_state.adding`) sin propietario, `save()` copia `creado_por` en `propietario`.
- **Estado y fecha de inicio de flora.** No se escriben a mano: se derivan de `CambioEtapaCultivo` con `services/etapas.py` (ver [servicios.md](servicios.md#etapaspy)). `estado = finalizado` lo fija la cosecha al cerrar.

Propiedades calculadas:

| Propiedad | Resultado |
|---|---|
| `fecha_referencia` | Hasta dónde corren los contadores: `min(hoy, fecha_fin)` si hay fecha de fin, si no hoy. |
| `dias_desde_inicio` | `fecha_referencia - fecha_inicio` en días, con piso en 0. El día 0 es `fecha_inicio`. Un cultivo que no empezó está en 0. Un cultivo cerrado queda en el día de su cierre. |
| `dia_flora` | Días desde `fecha_inicio_flora` hasta `fecha_referencia`. `None` si no hay `fecha_inicio_flora` o si es posterior a la referencia. El día del flip es el día 0. |

### CultivoMiembro

Pertenencia de un usuario a un cultivo ajeno, con un rol.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `miembros`. |
| `usuario` | FK `User`, CASCADE | Relación inversa `membresias_cultivo`. |
| `rol` | elección, por defecto `lector` | `lector` (solo lectura) o `editor` (puede registrar y editar). |
| `creado_en` | fecha y hora, automática | Alta de la membresía. |

Restricción: un usuario aparece una sola vez por cultivo (`cultivo_usuario_unico`). El dueño no se guarda acá: sale de `Cultivo.propietario`. Cómo se usa el rol está en [permisos.md](permisos.md) y en [../acceso-por-cultivo.md](../acceso-por-cultivo.md).

### Invitacion

Link de un solo uso para sumarse a un cultivo. La persona invitada crea su propia cuenta.

| Campo | Tipo | Significado |
|---|---|---|
| `token` | texto (64), único, no editable | Generado con `secrets.token_urlsafe(24)`. |
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `invitaciones`. |
| `rol` | elección de `CultivoMiembro.ROLES`, por defecto `editor` | Rol que recibe quien acepta. |
| `creada_por` | FK `User`, CASCADE | Quién la generó. Relación inversa `invitaciones_creadas`. |
| `creada` | fecha y hora, automática | Alta. |
| `vence` | fecha y hora | Por defecto, ahora más `DIAS_VIGENCIA` (7 días). |
| `usada_por` | FK `User`, SET_NULL, opcional | Quién la aceptó. Relación inversa `invitaciones_usadas`. |
| `usada_en` | fecha y hora, opcional | Cuándo se aceptó. |

Propiedad `vigente`: verdadera si `usada_en` es nulo y `vence` es posterior a ahora. Orden por defecto: `-creada`.

## Plantas y etapas

### Planta

Planta individual de un cultivo. Usa un `QuerySet` propio (`PlantaQuerySet`) como `objects`.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `plantas`. |
| `uuid` | UUID, único, no editable | Identificador estable. |
| `apodo` | texto (60) | Nombre corto de la planta. |
| `strain` | texto (120) | Genética. |
| `tipo` | elección, por defecto `foto` | `foto` (fotoperiódica) o `auto` (autofloreciente). |
| `posicion_tent` | elección, por defecto `otro` | `centro`, `arriba_izq`, `arriba_der`, `abajo_izq`, `abajo_der`, `otro`. |
| `dias_flora_estimados` | entero chico, opcional | Días de flora esperados para esta planta. |
| `indica_sativa_ratio` | texto (20) | Texto libre, por ejemplo `70/30`. |
| `thc_estimado` | decimal (5,2), opcional | THC estimado. |
| `yield_estimado_g` | entero chico, opcional | Rendimiento estimado en gramos. |
| `yield_real_g` | entero chico, opcional | Peso seco final en gramos. |
| `fecha_corte` | fecha, opcional | Día del corte (cosecha guiada). |
| `peso_humedo_g` | entero, opcional | Peso húmedo en gramos. |
| `fecha_seco` | fecha, opcional | Fin del secado. |
| `estado` | elección, por defecto `activa` | `activa`, `descartada`, `cosechada`. |
| `notas_genetica` | texto | Notas de la genética. |
| `archivado` | booleano | Oculta la planta sin borrarla. |
| `creado_por` | FK `User` | Relación inversa `plantas_creadas`. |

Orden por defecto: `apodo`.

Métodos y reglas:

- `Planta.objects.activas()` filtra `archivado=False` y `estado="activa"`. Son las plantas que pueden recibir riegos y mediciones nuevas.
- `tiene_historial()` es verdadero si la planta tiene alguno de: `riegos_detalle`, `mediciones`, `cambios_etapa`, `posiciones_cola` o `eventos`.
- `eliminar_o_archivar()` borra la planta si no tiene historial y devuelve `True`. Si tiene historial la marca `archivado=True` y devuelve `False`, para no perder en cascada sus riegos, fotos y etapas.
- El peso seco de la cosecha es `yield_real_g`; `peso_humedo_g`, `fecha_corte` y `fecha_seco` completan la cosecha guiada (ver [servicios.md](servicios.md#cosechapy)).

### CambioEtapaCultivo

Etapa del cultivo desde una fecha. Es la fuente única de la etapa: de ahí salen el estado del cultivo, el día de flora y el rango ideal de VPD.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `cambios_etapa`. |
| `etapa` | elección de las 7 etapas | Ver [Etapas](#etapas). |
| `fecha_inicio` | fecha | Desde cuándo rige la etapa. |
| `notas` | texto | Notas del cambio. |
| `created_at` | fecha y hora, automática | Alta. |

Unicidad: `(cultivo, fecha_inicio)`. Orden por defecto: `-fecha_inicio`, `-pk`.

### CambioEtapaPlanta

Etapa propia de una planta que va distinta al cultivo. Es opcional: una planta sin registros hereda la etapa del cultivo.

| Campo | Tipo | Significado |
|---|---|---|
| `planta` | FK `Planta`, CASCADE | Relación inversa `cambios_etapa`. |
| `etapa` | elección de las 7 etapas | Etapa de la planta. |
| `fecha_inicio` | fecha | Desde cuándo rige. |
| `notas` | texto | Notas. |
| `created_at` | fecha y hora, automática | Alta. |

Unicidad: `(planta, fecha_inicio)`. Orden: `-fecha_inicio`. La etapa de la planta prevalece solo si su fecha es igual o posterior al último cambio de etapa del cultivo (`etapa_efectiva_planta` en `growlog/utils.py`).

### Etapas

Las 7 etapas finas (`ETAPA_CHOICES`, igual en `ParametroIdeal.ETAPA_CHOICES`), en orden de ciclo (`ETAPA_ORDEN` en `growlog/utils.py`):

| Clave | Nombre | Estado del cultivo que le corresponde |
|---|---|---|
| `plantula` | Plántula | `plantula` |
| `veg_temprano` | Veg. temprano | `vegetativo` |
| `veg_tardio` | Veg. tardío | `vegetativo` |
| `flora_temprana` | Flora temprana | `floracion` |
| `flora_tardia` | Flora tardía | `floracion` |
| `secado` | Secado | `secado` |
| `curado` | Curado | `curado` |

Para un cultivo sin historial de etapas, la etapa efectiva se deduce de `Cultivo.estado` (`DEFAULT_ETAPA_POR_ESTADO_CULTIVO`): `plantula` a `plantula`, `vegetativo` a `veg_temprano`, `floracion` a `flora_temprana`, `secado` a `secado`, `curado` a `curado`, `finalizado` a ninguna.

## Ambiente y fotoperíodo

### CambioFotoperiodo

Fotoperíodo vigente en un cultivo desde una fecha.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `cambios_fotoperiodo`. |
| `fotoperiodo` | texto (5) | Formato `N/M` con N horas de luz y M de oscuridad, N+M=24. Ejemplos: `18/6`, `12/12`. |
| `hora_lights_on` | hora | Hora local de Argentina a la que se enciende la luz. |
| `fecha_inicio` | fecha | Desde cuándo rige. |
| `notas` | texto | Notas. |
| `created_at` | fecha y hora, automática | Alta. |

Unicidad: `(cultivo, fecha_inicio)`. Orden: `-fecha_inicio`.

`clean()` valida `fotoperiodo`: debe tener exactamente dos partes separadas por `/`, ambas enteras y positivas, y sumar 24.

### MedicionAmbiente

Lectura de temperatura y humedad de la carpa.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `mediciones`. |
| `timestamp` | fecha y hora, por defecto ahora | Cuándo se observó. |
| `temperatura_c` | decimal (5,2) | Temperatura en °C. |
| `humedad_relativa` | decimal (5,2) | Humedad relativa en %. |
| `luz_estado` | elección `on`/`off`, opcional | Luz prendida o apagada al medir. |
| `notas` | texto | Notas. |
| `creado_por` | FK `User` | Relación inversa `mediciones_creadas`. |

Orden: `-timestamp`.

Reglas y propiedades:

- **Estado de la luz.** En `save()`, si `luz_estado` es nulo se calcula con `utils.resolver_luz_estado_para_medicion`: toma el `CambioFotoperiodo` vigente en la fecha local de la medición y compara la hora con `hora_lights_on` y las horas de luz. Si el cultivo no tiene fotoperíodo cargado, queda nulo.
- **`vpd`** (kPa, no se guarda): fórmula de Magnus. `es = 0,6108 * exp(17,27 * T / (T + 237,3))` y `vpd = round(es * (1 - HR/100), 3)`, con T en °C y HR en %.
- **`vpd_estado`**: `ideal`, `alto` o `bajo`, o `None`. Busca la etapa efectiva del cultivo en la fecha local de la medición y el `ParametroIdeal` de esa etapa. Compara `vpd` contra `vpd_min` y `vpd_max` de ese parámetro. Devuelve `None` si no hay etapa o no hay parámetro cargado.

### ParametroIdeal

Tabla de referencia con los rangos ideales de cada etapa. Hay a lo sumo un registro por etapa.

| Campo | Tipo | Significado |
|---|---|---|
| `etapa` | elección de las 7 etapas, único | Etapa a la que aplica. |
| `temp_min`, `temp_max` | decimal (5,1) | Temperatura en °C. |
| `hr_min`, `hr_max` | decimal (5,1) | Humedad relativa en %. |
| `ph_min`, `ph_max` | decimal (4,2) | pH. |
| `ec_min`, `ec_max` | decimal (5,2), opcionales | EC en mS/cm. |
| `vpd_min`, `vpd_max` | decimal (4,2) | VPD en kPa. |
| `horas_luz` | entero chico, opcional | Horas de luz. |
| `distancia_luz_min`, `distancia_luz_max` | entero chico, opcionales | Distancia de la luz en cm. |

Una etapa cuyo `vpd_max` no supera a `vpd_min` (por ejemplo 0 a 0) se trata como sin rango de VPD (`services/vpd._rango`).

### MedicionEC

Medición de pH, EC y temperatura del agua, separada del riego.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `mediciones_ec`. |
| `timestamp` | fecha y hora, por defecto ahora | Cuándo se observó. |
| `tipo` | elección, por defecto `solucion` | `entrada` (agua de entrada), `solucion` (solución nutritiva), `runoff` (runoff o drenaje), `sustrato` (sustrato directo). |
| `ph` | decimal (4,2), opcional | pH. |
| `ec` | decimal (5,2), opcional | EC en mS/cm. |
| `temp_agua` | decimal (4,1), opcional | Temperatura del agua en °C. |
| `notas` | texto | Notas. |
| `creado_por` | FK `User` | Relación inversa `mediciones_ec_creadas`. |

Orden: `-timestamp`.

## Riego y nutrientes

### Nutriente

Catálogo de fertilizantes y aditivos.

| Campo | Tipo | Significado |
|---|---|---|
| `nombre` | texto (120) | Nombre del producto. |
| `marca` | texto (120) | Marca. |
| `npk` | texto (30) | Composición, por ejemplo `25-2.8-6.9`. |
| `etapa_recomendada` | elección, por defecto `veg` | `veg`, `flora`, `aditivo`. |
| `unidad` | elección, por defecto `g` | `g` (g/L, polvos y sales) o `ml` (ml/L, líquidos). |
| `dosis_recomendada_min`, `dosis_recomendada_max` | decimal (6,2), opcionales | Rango recomendado en la unidad del nutriente. |
| `propietario` | FK `User`, CASCADE, opcional | Sin propietario es del catálogo compartido. Con propietario lo ve su dueño. Relación inversa `nutrientes_propios`. |
| `oculto` | booleano | Deja de ofrecerse al registrar, pero los riegos viejos lo conservan. |

Orden: `marca`, `nombre`. `__str__` muestra `marca nombre`. Cuáles se ofrecen a cada usuario en un cultivo lo decide `permissions.nutrientes_para` (ver [permisos.md](permisos.md)). Un nutriente usado se oculta, no se borra, porque `NutrienteAplicado` lo referencia con `PROTECT`.

### Riego

Riego de un cultivo (la sesión completa; el detalle por planta está en `RiegoPlanta`).

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `riegos`. |
| `timestamp` | fecha y hora, por defecto ahora | Cuándo se regó. |
| `volumen_total_ml` | entero positivo | Suma de los volúmenes por planta, en ml. La calcula `guardar_riego`. |
| `volumen_por_planta_ml` | entero positivo, opcional | Volumen por planta en ml. |
| `ph_agua` | decimal (4,2), opcional | pH de la solución. |
| `ec_solucion` | decimal (5,2), opcional | EC de la solución en mS/cm. |
| `buscar_runoff` | booleano | Se intentó recoger runoff. |
| `runoff_observado` | booleano | Hubo runoff. |
| `ph_runoff` | decimal (4,2), opcional | pH del runoff. |
| `ec_runoff` | decimal (5,2), opcional | EC del runoff en mS/cm. |
| `notas` | texto | Notas. |
| `creado_por` | FK `User` | Relación inversa `riegos_creados`. |

Orden: `-timestamp`.

### NutrienteAplicado

Dosis de un nutriente en un riego.

| Campo | Tipo | Significado |
|---|---|---|
| `riego` | FK `Riego`, CASCADE | Relación inversa `nutrientes_aplicados`. |
| `nutriente` | FK `Nutriente`, PROTECT | Nutriente usado. |
| `dosis_g_por_litro` | decimal (6,3) | Dosis por litro. La unidad real (g o ml) es `nutriente.unidad`; el campo conserva su nombre. |

### RiegoPlanta

Detalle de un riego para una planta.

| Campo | Tipo | Significado |
|---|---|---|
| `riego` | FK `Riego`, CASCADE | Relación inversa `detalle_plantas`. |
| `planta` | FK `Planta`, CASCADE | Relación inversa `riegos_detalle`. |
| `volumen_ml` | entero positivo | Volumen que recibió la planta. |
| `runoff_observado` | booleano | Esa planta tuvo runoff. |
| `ph_runoff` | decimal (4,2), opcional | pH del runoff de la planta. |
| `ec_runoff` | decimal (5,2), opcional | EC del runoff de la planta en mS/cm. |
| `notas` | texto | Notas. |

Unicidad: `(riego, planta)`. Orden: `planta__apodo`.

## Eventos, tareas y mediciones de planta

### Evento

Hecho relevante del cultivo, con seguimiento opcional.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `eventos`. |
| `timestamp` | fecha y hora, por defecto ahora | Cuándo ocurrió. |
| `tipo` | elección | `topping`, `lst`, `defoliacion`, `transplante`, `problema`, `diagnostico`, `ajuste_ambiente`, `cambio_ciclo`, `nota`, `otro`. |
| `descripcion` | texto | Qué pasó. |
| `plantas_afectadas` | M2M `Planta` | Opcional. Relación inversa `eventos`. |
| `follow_up_fecha` | fecha, opcional | Cuándo revisar. |
| `follow_up_descripcion` | texto | Qué revisar. |
| `follow_up_resuelto` | booleano | Seguimiento cerrado. |
| `creado_por` | FK `User` | Relación inversa `eventos_creados`. |

Orden: `-timestamp`. Los eventos de tipo `nota` son las notas de Registrar.

### MedicionPlanta

Medición de crecimiento de una planta, con foto opcional.

| Campo | Tipo | Significado |
|---|---|---|
| `planta` | FK `Planta`, CASCADE | Relación inversa `mediciones`. |
| `fecha` | fecha, por defecto hoy | Día de la medición. |
| `altura_cm` | decimal (6,1), opcional | Altura en cm. |
| `nudos_count` | entero chico, opcional | Cantidad de nudos. |
| `ancho_canopy_cm` | decimal (6,1), opcional | Ancho de la copa en cm. |
| `aspecto_general` | elección, por defecto `bueno` | `bueno`, `regular`, `malo`. |
| `sintomas` | texto | Síntomas observados. |
| `foto` | imagen, opcional | Se guarda en `plantas/AAAA/MM/`. |
| `foto_mini` | imagen, opcional, no editable | Miniatura en `plantas/mini/AAAA/MM/`. |
| `creado_por` | FK `User` | Relación inversa `mediciones_planta_creadas`. |

Orden: `-fecha`. Permiso adicional del modelo: `subir_fotos` ("Puede subir fotos aunque estén deshabilitadas para todos").

Reglas:

- En `save()`, si la foto es nueva (todavía no está en el storage) se llama a `services.fotos.preparar_foto`, que la endereza, la achica y arma la miniatura. Si no hay foto, `foto_mini` se vacía.
- `foto_chica` devuelve `foto_mini` si existe, si no `foto`.

### Tarea

Tarea de un cultivo.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `tareas`. |
| `titulo` | texto (200) | Título. |
| `descripcion` | texto | Detalle. |
| `fecha_objetivo` | fecha, opcional | Fecha para hacerla. |
| `prioridad` | elección, por defecto `normal` | `urgente`, `normal`, `baja`. |
| `categoria` | elección, por defecto `observacion` | `riego`, `training`, `mantenimiento`, `compra`, `observacion`. |
| `completada` | booleano | Hecha. |
| `completada_en` | fecha y hora, opcional | Cuándo se completó. |
| `creado_por` | FK `User` | Relación inversa `tareas_creadas`. |

Orden: `completada`, `fecha_objetivo`, `-prioridad`.

## Canopy

### CanopySnapshot

Registro del estado de la copa en un momento.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `canopy_snapshots`. |
| `creado_en` | fecha y hora, automática | Cuándo se tomó. |
| `notas` | texto | Notas. |
| `scrog_fill_pct` | entero chico, por defecto 0 | Porcentaje de llenado de la malla SCROG. |
| `scrog_cells` | JSON (lista), por defecto vacía | Celdas de la malla. |

Orden: `-creado_en`.

### ColaPosicion

Posición de una cola de una planta dentro de un snapshot.

| Campo | Tipo | Significado |
|---|---|---|
| `snapshot` | FK `CanopySnapshot`, CASCADE | Relación inversa `colas`. |
| `planta` | FK `Planta`, CASCADE | Relación inversa `posiciones_cola`. |
| `indice` | entero chico | Número de cola de la planta. |
| `x`, `y` | float | Coordenadas de la cola. |

Unicidad: `(snapshot, planta, indice)`. Orden: `planta`, `indice`.

Constante `POSICION_TENT_COORDS`: coordenadas `(x, y)` de cada valor de `Planta.posicion_tent`: `centro` (0,50; 0,50), `arriba_izq` (0,30; 0,30), `arriba_der` (0,70; 0,30), `abajo_izq` (0,30; 0,70), `abajo_der` (0,70; 0,70), `otro` (0,50; 0,50).

## Energía

### Equipo

Equipo eléctrico de un usuario.

| Campo | Tipo | Significado |
|---|---|---|
| `nombre` | texto (120) | Nombre. |
| `watts` | decimal (8,2) | Potencia en watts. |
| `horas_dia` | decimal (4,2) | Horas de uso por día. |
| `categoria` | elección | `lampara`, `extractor`, `ventilador`, `humidificador`, `otro`. |
| `activo` | booleano, por defecto verdadero | En uso. |
| `notas` | texto | Notas. |
| `propietario` | FK `User`, SET_NULL | Relación inversa `equipos_propios`. |

Propiedad `kwh_mes`: `watts / 1000 * horas_dia * 30`, redondeado a 2 decimales. Orden: `categoria`, `nombre`.

### TarifaElectrica

Precio del kWh desde una fecha.

| Campo | Tipo | Significado |
|---|---|---|
| `fecha_desde` | fecha | Desde cuándo rige. |
| `precio_kwh` | decimal (10,4) | Precio por kWh. |
| `distribuidora` | texto (100), por defecto `Edesur` | Distribuidora. |
| `notas` | texto | Notas. |
| `propietario` | FK `User`, SET_NULL | Relación inversa `tarifas_propias`. |

Orden: `-fecha_desde`.

### CostoEnergetico

Uso de un equipo en un cultivo durante un período, con la tarifa aplicada.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `costos_energeticos`. |
| `equipo` | FK `Equipo`, CASCADE | Relación inversa `costos`. |
| `tarifa` | FK `TarifaElectrica`, PROTECT | Relación inversa `costos`. |
| `fecha_desde` | fecha | Inicio del uso. |
| `fecha_hasta` | fecha, opcional | Fin del uso. Vacío significa vigente. |

Orden: `-fecha_desde`.

### LecturaMedidor

Lectura real del medidor de electricidad.

| Campo | Tipo | Significado |
|---|---|---|
| `cultivo` | FK `Cultivo`, CASCADE | Relación inversa `lecturas_medidor`. |
| `fecha` | fecha | Día de la lectura. |
| `kwh_real` | decimal (10,2) | Consumo real en kWh. |
| `notas` | texto | Notas. |

Orden: `-fecha`. El cálculo de consumo y costo está en [servicios.md](servicios.md#energiapy) y [servicios.md](servicios.md#reportepy).

## Usuarios y sistema

### APIToken

Token de acceso a la API JSON (ver [api.md](api.md)).

| Campo | Tipo | Significado |
|---|---|---|
| `user` | FK `User`, CASCADE | Dueño. Relación inversa `api_tokens`. |
| `token_hash` | texto (64), único | Hash del token. |
| `created_at` | fecha y hora, automática | Alta. |

### PushSubscription

Suscripción a notificaciones push del navegador (Web Push).

| Campo | Tipo | Significado |
|---|---|---|
| `user` | FK `User`, CASCADE | Relación inversa `push_subscriptions`. |
| `endpoint` | URL (500), única | Endpoint del navegador. |
| `p256dh` | texto (255) | Clave pública del cliente. |
| `auth` | texto (255) | Secreto de autenticación. |
| `creado_en` | fecha y hora, automática | Alta. |

### Ingreso

Intento de inicio de sesión. Guarda un nombre corto de dispositivo, no la IP.

| Campo | Tipo | Significado |
|---|---|---|
| `usuario` | FK `User`, CASCADE, opcional | Relación inversa `ingresos`. |
| `nombre_usado` | texto (150) | Usuario que se tipeó. |
| `exito` | booleano, por defecto verdadero | Si el ingreso fue válido. |
| `dispositivo` | texto (60) | Dispositivo en forma corta. |
| `creado_en` | fecha y hora, automática, indexada | Cuándo ocurrió. |

Orden: `-creado_en`.

### Perfil

Preferencias de cada persona. Relación uno a uno con `User` (`related_name="perfil"`).

| Campo | Tipo | Significado |
|---|---|---|
| `usuario` | OneToOne `User`, CASCADE | Dueño. |
| `unidad_ec` | elección, por defecto `us` | Cómo se muestra la EC: `us` (µS/cm), `ms` (mS/cm), `x10` (como el medidor, ×10 µS/cm). |
| `avisar_ambiente` | booleano, por defecto verdadero | Avisar si falta medir el ambiente del día. |
| `avisar_tareas` | booleano, por defecto verdadero | Avisar tareas vencidas o de hoy. |
| `avisar_seguimientos` | booleano, por defecto verdadero | Avisar seguimientos pendientes. |
| `hora_avisos` | entero chico, por defecto 20 | Hora del día de los avisos. |

Función `perfil_de(usuario)`: devuelve `None` si el usuario no está autenticado. Si no tiene perfil, lo crea con los valores por defecto (`get_or_create`) y lo deja asociado a la instancia.

## Unidades de EC

- En la base de datos la EC se guarda siempre en **mS/cm** (`Riego.ec_solucion`, `Riego.ec_runoff`, `RiegoPlanta.ec_runoff`, `MedicionEC.ec`, `ParametroIdeal.ec_min` y `ec_max`).
- Se muestra según `Perfil.unidad_ec`: µS/cm (mS por 1000), mS/cm, o como el medidor (mS por 100, es decir ×10 µS/cm). Los filtros están en `templatetags/ec.py` (ver [servicios.md](servicios.md#templatetags)).
- En Registrar la EC se tipea en ×10 µS/cm y se guarda convertida a mS/cm (ver [registrar.md](registrar.md)).
- `services/vpd.py` entrega la EC de los rangos y de las lecturas en µS/cm.

## Resumen de relaciones

```
User ──< Cultivo (propietario, creado_por)
User ──< CultivoMiembro >── Cultivo        (rol: lector | editor)
Cultivo ──< Invitacion                      (creada_por: User; usada_por: User)

Cultivo ──< Planta
Cultivo ──< CambioEtapaCultivo              (fuente de estado, flora y VPD ideal)
Planta  ──< CambioEtapaPlanta               (opcional)
Cultivo ──< CambioFotoperiodo
Cultivo ──< MedicionAmbiente                (luz_estado desde CambioFotoperiodo; vpd_estado desde ParametroIdeal)
Cultivo ──< MedicionEC
Etapa  ──1 ParametroIdeal                   (una fila por etapa)

Cultivo ──< Riego ──< NutrienteAplicado >── Nutriente (PROTECT)
Riego   ──< RiegoPlanta >── Planta

Cultivo ──< Evento >──< Planta              (plantas_afectadas)
Cultivo ──< Tarea
Planta  ──< MedicionPlanta

Cultivo ──< CanopySnapshot ──< ColaPosicion >── Planta

Cultivo ──< CostoEnergetico >── Equipo
CostoEnergetico >── TarifaElectrica (PROTECT)
Cultivo ──< LecturaMedidor
User ──< Equipo, TarifaElectrica            (propietario)

User ──< APIToken, PushSubscription, Ingreso
User ──1 Perfil
User ──< Nutriente                          (propietario; sin propietario = catálogo compartido)
```

Borrados en cascada: al borrar un `Cultivo` se borran sus plantas, etapas, fotoperíodos, mediciones, riegos, eventos, tareas, snapshots, costos, lecturas, miembros e invitaciones. `Nutriente` y `TarifaElectrica` usados no se pueden borrar (`PROTECT`). Las plantas con historial se archivan en lugar de borrarse (`Planta.eliminar_o_archivar`).
