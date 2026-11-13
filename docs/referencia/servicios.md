# Servicios

Describe la lógica de dominio de `growlog/services/`, los helpers de `growlog/utils.py` y `growlog/views/helpers.py`, y los templatetags de `growlog/templatetags/`. Los servicios los usan tanto las vistas web como la API (ver [api.md](api.md)); el detalle del alta de registros está en [registrar.md](registrar.md). Los modelos están en [modelos.md](modelos.md) y las reglas de acceso en [permisos.md](permisos.md).

`growlog/services/__init__.py` solo tiene el docstring del paquete. Las vistas web no importan helpers privados de `api_views`: lo compartido vive acá.

## utils.py

Ruta: `growlog/utils.py`. Funciones de fotoperíodo, etapa y carpa que usan los modelos y los servicios.

| Función | Entrada | Salida y regla |
|---|---|---|
| `ARGENTINA_TZ` | constante | `ZoneInfo("America/Argentina/Buenos_Aires")`. Los horarios de luz se evalúan en esta zona. |
| `area_carpa_m2(dimensiones)` | texto como `80x80x180` (cm) | Toma los dos primeros números (acepta coma decimal) y devuelve ancho por largo en m², redondeado a 4 decimales. `None` si hay menos de 2 números o el área no es positiva. |
| `get_cambio_fotoperiodo_activo(cultivo, timestamp)` | cultivo, fecha y hora | `CambioFotoperiodo` con `fecha_inicio` más reciente que no supera la fecha local (Argentina) del timestamp, o `None`. Un timestamp sin zona se toma como hora argentina. |
| `calcular_luz_estado(timestamp, hora_lights_on, fotoperiodo)` | fecha y hora, hora de encendido, texto `N/M` | `"on"` o `"off"`. La luz está prendida desde `hora_lights_on` durante N horas; el intervalo puede cruzar la medianoche. |
| `get_flip_a_flora(cultivo)` | cultivo | Primer `CambioFotoperiodo` (por fecha) con 12 horas de luz o menos, o `None`. Ignora fotoperíodos mal formados. |
| `resolver_luz_estado_para_medicion(cultivo, timestamp)` | cultivo, fecha y hora | `"on"`/`"off"` según el fotoperíodo activo; `None` si el cultivo no tiene ninguno. La usa `MedicionAmbiente.save()`. |
| `ETAPA_ORDEN` | lista | Las 7 etapas en orden de ciclo. |
| `DEFAULT_ETAPA_POR_ESTADO_CULTIVO` | dict | Etapa que se asume para un cultivo sin historial de etapas, según `Cultivo.estado` (`finalizado` no tiene etapa). |
| `get_etapa_activa_cultivo(cultivo, fecha=None)` | cultivo, fecha (hoy por defecto) | `CambioEtapaCultivo` vigente en la fecha (el de `fecha_inicio` más alta que no la supera; desempata por pk), o `None`. El historial se trae una vez y queda memorizado en `cultivo.__dict__["_cambios_etapa"]`. |
| `olvidar_etapas(cultivo)` | cultivo | Borra lo memorizado en la instancia (`_cambios_etapa`, `_etapa_por_fecha`, `_parametro_por_etapa`). Se llama tras cambiar el historial. |
| `get_etapa_activa_planta(planta, fecha=None)` | planta, fecha | `CambioEtapaPlanta` vigente, usando el prefetch de `cambios_etapa` si está. |
| `etapa_efectiva_cultivo(cultivo, fecha=None)` | cultivo, fecha | Clave de etapa: la del cambio vigente; si no hay historial, la que corresponde al estado administrativo. |
| `etapa_efectiva_planta(planta, fecha=None)` | planta, fecha | La etapa propia de la planta si existe y su fecha es igual o posterior al cambio vigente del cultivo; si no, la del cultivo. |
| `parametro_ideal_de(cultivo, etapa)` | cultivo, etapa | `ParametroIdeal` de la etapa (o `None`), memorizado en `cultivo.__dict__["_parametro_por_etapa"]`. |

## views/helpers.py

Ruta: `growlog/views/helpers.py`. Helpers compartidos por vistas.

| Función | Entrada | Salida y regla |
|---|---|---|
| `build_timeline(cultivo, limit=50)` | cultivo, cantidad | Lista de dicts `{tipo, ts, obj}` con mediciones de ambiente (`medicion`), riegos, eventos y mediciones EC (`medicion_ec`), ordenados del más nuevo al más viejo. Trae `limit * 3` de cada fuente, con `select_related` y `prefetch_related` de lo que muestra la plantilla, y recorta a `limit`. |
| `evaluar_ambiente(medicion, param)` | `MedicionAmbiente`, `ParametroIdeal` | Dict `{temp, hr, vpd}` con `"ideal"`, `"alto"` o `"bajo"` para cada magnitud, comparada con el min y max del parámetro. |

## Servicios por módulo

### etapas.py

Ruta: `growlog/services/etapas.py`. Única vía para cambiar la etapa de un cultivo. De la etapa salen `Cultivo.estado`, `Cultivo.fecha_inicio_flora` y el rango ideal de VPD.

| Elemento | Descripción |
|---|---|
| `ETAPAS_FLORA` | `("flora_temprana", "flora_tardia")`. |
| `ESTADO_POR_ETAPA` | Estado administrativo de cada etapa (ver tabla en [modelos.md](modelos.md#etapas)). |
| `sincronizar_cultivo(cultivo)` | Olvida lo memorizado, y recalcula `fecha_inicio_flora` como la fecha mínima entre los cambios de etapa de flora (pasar de flora temprana a tardía no reinicia el contador); sin etapas de flora queda en `None`. Si hay cambios ya vigentes (fecha menor o igual a hoy) y el cultivo no está `finalizado`, pone `estado` según la última etapa vigente. Guarda solo esos campos. |
| `reabrir_cultivo(cultivo)` | Transacción. Pone `estado="vegetativo"` y `fecha_fin=None`, y sincroniza con el historial. Sin historial queda en vegetativo. |
| `cambiar_etapa(cultivo, etapa, fecha, notas="")` | Transacción. `update_or_create` de `CambioEtapaCultivo` por `(cultivo, fecha)`: repetir una fecha corrige el registro en vez de fallar. Luego sincroniza. Devuelve el cambio. |

### ciclo.py

Ruta: `growlog/services/ciclo.py`. Duración real contra estimada de cada fase, y el paso a floración (flip).

- `FASES`: plántula, veg (`veg_temprano` y `veg_tardio`), flora (`flora_temprana` y `flora_tardia`), secado (10 días orientativos) y curado (21 días orientativos). `FOTOPERIODO_FLORA = "12/12"`.
- `resumen_ciclo(cultivo, hoy=None)` devuelve un dict con:
  - `filas`: por fase con estimado u observación, `estimado`, `orientativo` (verdadero para secado y curado), `est_desde`, `real_desde`, `real_dias` y porcentajes `est_izq`, `est_ancho`, `real_izq`, `real_ancho` sobre el total de la barra.
  - `total`: máximo entre la suma de estimados, los días desde el inicio y el fin de cada fase real.
  - `hoy_pct`: posición de hoy en la barra.
  - `en_flora`, `puede_flip` (no está en flora y no está finalizado), `fotoperiodo` (cambio vigente ahora), `scrog_pct` (último `CanopySnapshot`), `cosecha_estimada` (`fecha_inicio_flora` más días de flora estimados) y `dias_a_cosecha`.
  - Reglas: los días reales de una fase van desde cada cambio de etapa hasta el siguiente (el último, hasta la fecha de referencia del cultivo). Los estimados de veg y flora salen de `dias_veg_estimados` y `dias_flora_estimados`; si falta el de flora se usa el máximo de `dias_flora_estimados` de las plantas activas. Las fases sin estimado y sin datos reales no aparecen.
- `hacer_flip(cultivo, fecha=None)`: transacción. Si el cultivo ya tiene `fecha_inicio_flora` no toca nada y devuelve `False`. Si no, registra la etapa `flora_temprana` con nota "Flip" y, si el fotoperíodo vigente no es 12/12, crea o actualiza el `CambioFotoperiodo` 12/12 de esa fecha, conservando la hora de encendido vigente (6:00 si no había). Devuelve `True`.

### vpd.py

Ruta: `growlog/services/vpd.py`. Datos del mapa de Aire: lecturas de ambiente, pH/EC y rangos ideales por etapa.

| Elemento | Descripción |
|---|---|
| `RANGOS` | `24h` (1 día), `7d` (7), `30d` (30), `ciclo` (todo). Por defecto `7d`. `MAX_LECTURAS = 600`. |
| `estado_vpd(vpd, rango)` | `"ideal"`, `"bajo"`, `"alto"`, o `None` si no hay rango. |
| `estado_de(cultivo, medicion)` | Estado de VPD de una lectura con el ideal de la etapa vigente en la fecha de la medición. |
| `etapas_ideales()` | Lista, en orden de ciclo, con los rangos de cada `ParametroIdeal`: temp, hr, vpd (o `None` si `vpd_max <= vpd_min`), pH y EC en µS/cm (o `None`). |
| `mapa_vpd(cultivo, rango="7d")` | Rango inválido cae a `7d`. Devuelve las lecturas del rango (hasta 600, de la más vieja a la más nueva) con `ts`, `t`, `h`, `vpd`, `luz`, `etapa` y `estado`; más `rangos`, `ph_ec`, `etapas`, `etapa_actual`, `en_rango`, `en_rango_dia` y `en_rango_noche` (porcentaje de lecturas ideales sobre las clasificables, total, con luz prendida y con luz apagada). |
| `lecturas_ph_ec(cultivo, dias)` | Puntos con pH y EC (µS/cm) del rango, con `fuente` y `detalle`: cada `MedicionEC` (`entrada`, `solucion`, `runoff`, `sustrato`), la solución de cada riego (`solucion`, detalle `riego`) y el runoff de cada `RiegoPlanta` con runoff observado (`runoff`, detalle el apodo). Omite puntos sin pH ni EC. |

### hoy.py

Ruta: `growlog/services/hoy.py`. Arma la pantalla Hoy: cultivos visibles, pendientes, alertas, barra Núcleo y mapa de aire de escritorio. Solo muestra datos observados.

Constantes: `DATO_VIEJO` (6 h: una lectura más vieja se marca como dato viejo), `ALERTA_VPD_HASTA` (24 h: solo se alerta con lecturas recientes), `ETAPA_CORTA` (nombre corto de la etapa), `CAPAS = ("w", "m", "e", "n")` (riego, medición, evento, nota) y `COLA_MAPA` (24 h).

- `resumen_hoy(usuario, ahora=None)`: parte de `permissions.cultivos_visibles(usuario)` y devuelve un dict con:
  - `activos`, `propios`, `compartidos`, `finalizados`, `archivados` y `historial_total`. Cada ítem trae el cultivo, la última medición, `plantas_count` (activas y no archivadas), `puede_editar`, `frescura` (`sin_datos`, `futura`, `hoy`, `anterior`), `es_propio`, `etapa`, `etapa_nombre`, `en_flora`, `dia` (día de flora si está en flora, si no días desde el inicio), `vpd_estado`, `dato_viejo` y `dias_sin_riego`.
  - `alertas`: cultivos activos con VPD `alto` o `bajo` en una lectura de las últimas 24 h.
  - `atencion` (hasta 12) y `atencion_total`, `atencion_restante`: tareas incompletas con fecha vencida o de hoy, o urgentes, y seguimientos de eventos sin resolver con fecha vencida o de hoy. Orden: vencidos primero, luego fecha, prioridad (urgente, normal, baja), tipo y pk.
  - `tareas_total`, `tareas_sin_fecha`, `puede_registrar` (puede editar al menos un cultivo), `sin_medicion_hoy` y `mapa`.
- `_sumar_nucleo(activos, hoy)`: agrega a cada ítem `nucleo`: una columna por día desde el inicio del cultivo y una capa por tipo de registro de ese día (riego `w`, medición de ambiente o EC `m`, evento `e`, nota `n`), de alto 12 repartido entre las capas presentes. El ancho es proporcional a la edad, con el cultivo más viejo al 100 % y mínimo 8 %.
- `_mapa_aire(activos, ahora)`: para cada cultivo activo con medición, la última lectura (`t`, `h`, `vpd`, `estado`, `viejo`), su cola de las últimas 24 h (hasta 12 puntos), la etapa y los rangos ideales de temperatura, humedad y VPD.
- `item_tarea(tarea, puede_editar, hoy=None)`: fila de tarea para Hoy (tipo, título, cultivo, fecha, `urgente`, `prioridad`, `vencido`, categoría, `completada`).
- `agrupar_tareas(tareas, hoy=None, editables=())`: grupos `vencidas`, `proximas` ("Hoy y próximas") y `sin_fecha`, omitiendo los vacíos. Orden por fecha, prioridad y pk; los sin fecha por prioridad y pk.

### bitacora.py

Ruta: `growlog/services/bitacora.py`. Bitácora del cultivo, paginada.

- `POR_PAGINA = 50`.
- `FILTROS`: `medicion` (Ambiente), `riego` (Riego), `evento` (Evento), `medicion_ec` (pH/EC), `ciclo` (cambios de etapa y de fotoperíodo) y `planta` (Plantas).
- `bitacora(cultivo, filtro="", desde=0, por_pagina=50, dia_anterior=None)`: junta ambiente, riegos, eventos, pH/EC, cambios de etapa, cambios de fotoperíodo y mediciones de planta. Cada fuente se consulta ordenada y solo hasta la página pedida (`desde + por_pagina + 1`). Los registros con solo fecha se ubican al inicio de su día. Un filtro desconocido equivale a ninguno. Devuelve:

| Clave | Contenido |
|---|---|
| `registros` | Página: dicts `{tipo, ts, obj, dia, nuevo_dia}`. `nuevo_dia` es verdadero cuando cambia el día respecto del anterior, también entre páginas (usa `dia_anterior`). |
| `filtro`, `filtros` | Filtro activo y lista con clave, etiqueta y cuenta de cada filtro. |
| `total` | Suma de los conteos de todos los filtros. |
| `hay_mas`, `siguiente` | Si hay otra página y su `desde`. |
| `ultimo_dia` | Día del último registro de la página, para encadenar páginas. |

### energia.py

Ruta: `growlog/services/energia.py`. Estimación de consumo y costo eléctrico.

- `ciclo_activo(cultivo, hoy)`: fotoperíodo vigente según `CambioFotoperiodo`. Sin cambios, devuelve `12/12` si el cultivo está en `floracion` y tiene plantas activas fotoperiódicas; si no, `18/6`.
- `calcular_meses(cultivo_inicio, costos, tarifas, hoy)`: lista por mes calendario desde el mes de inicio hasta hoy, con `mes` (`AAAA-MM`), `dias` (días del mes dentro del período del cultivo), `kwh_estimado`, `costo_estimado` y `tarifa`. Cada `CostoEnergetico` suma `watts / 1000 * horas_dia * días` de la intersección entre su período y el mes. La tarifa del mes es la primera de `tarifas` (ordenadas de la más nueva) con `fecha_desde` menor o igual al primer día del mes; sin tarifa el costo es 0 y `tarifa` es `None`.

### reporte.py

Ruta: `growlog/services/reporte.py`. Reporte de cierre de un cultivo y comparación con cultivos anteriores. `ANTERIORES = 5`; los gráficos usan un viewBox de `ANCHO = 320` por `ALTO = 120`.

| Función | Descripción |
|---|---|
| `cifras(cultivo)` | Cifras comparables: fin (fecha de fin u hoy), días totales, de veg y de flora (el flip sale de `fecha_inicio_flora` o del primer fotoperíodo de 12 h), plantas (no archivadas ni descartadas), gramos secos y estimados, g/W (si hay watts), g por planta pesada, porcentaje de lecturas con VPD ideal y energía. |
| `anteriores(cultivo)` | Hasta 5 cultivos `finalizado` del mismo propietario, excluyendo el actual, del más nuevo al más viejo, con sus `cifras`. Sin propietario, lista vacía. |
| `reporte(cultivo)` | Todo lo de `cifras` más: detalle de lecturas en rango (total, día, noche y por semana del ciclo, con barras), curvas de crecimiento por planta en un mismo eje, yield por planta (barras de estimado y real), merma (porcentaje que se pierde de húmedo a seco, sobre plantas con ambos pesos), resumen de riegos (cantidad, litros, pH y EC promedio), nutrientes usados (aplicaciones, dosis promedio y total), estadísticas de ambiente (temperatura, humedad y VPD promedio, mínimo y máximo), eventos por tipo y `anteriores`. |

Energía (`_energia`), en orden de prioridad de la fuente: si hay lecturas de medidor hasta la fecha de fin, kWh es la suma de `kwh_real` (`fuente="medidor"`); si no y hay `CostoEnergetico`, kWh y costo salen de `calcular_meses` con las tarifas de `permissions.tarifas_del_cultivo` (`fuente="equipos"`); si no hay ninguno y el cultivo tiene `lampara_watts_reales`, kWh es la lámpara por las horas de luz de cada fotoperíodo (`fuente="lampara"`, sin costo). El costo con medidor usa la tarifa más reciente. También calcula `costo_por_gramo` y `g_por_kwh` cuando hay peso seco.

Rango de VPD: una lectura cuenta como ideal si su VPD está dentro del rango de la etapa vigente cuando se midió (`vpd.estado_de`).

### cosecha.py

Ruta: `growlog/services/cosecha.py`. Cosecha guiada. `PASOS = ("cortar", "pesar", "secar", "cerrar")`.

| Función | Descripción |
|---|---|
| `plantas_de_cosecha(cultivo)` | Plantas no archivadas con estado `activa` o `cosechada`, por apodo. |
| `resumen(cultivo)` | Plantas, cortadas y sin cortar, `hechos` por paso, `actual` (primer paso no hecho, `cerrar` si todos), `humedo_total`, `seco_total`, `merma`, `g_por_watt` y `etapa`. Reglas de paso hecho: `cortar`, hay cortadas y ninguna sin cortar; `pesar`, todas las cortadas tienen peso húmedo; `secar`, todas tienen `yield_real_g`; `cerrar`, el cultivo está `finalizado`. La merma usa solo plantas con peso húmedo y seco. |
| `cortar(cultivo, plantas, fecha, pasar_a_secado)` | Transacción. Marca `fecha_corte` y `estado="cosechada"`. Si `pasar_a_secado` y la etapa no es `secado` ni `curado`, cambia la etapa a `secado` en esa fecha. |
| `pesar(pesos)` | Transacción. Guarda `peso_humedo_g` de `{planta: gramos}`; `None` lo deja como estaba. |
| `secar(cultivo, pesos, fecha, pasar_a_curado)` | Transacción. Guarda `yield_real_g` y `fecha_seco`. Si `pasar_a_curado` y la etapa no es `curado`, cambia la etapa a `curado`. |
| `cerrar(cultivo)` | Pone `estado="finalizado"` y, si no tenía, `fecha_fin` de hoy. |

### onboarding.py

Ruta: `growlog/services/onboarding.py`. Primeros pasos de un cultivo nuevo. `DIAS_RECORDATORIO = 21`.

- `pasos(cultivo)`: cinco pasos con `clave`, `titulo`, `detalle`, `hecho` y `url`. `duracion` (hecho si tiene días de veg y de flora estimados), `plantas` (tiene alguna planta), `fotoperiodo` (tiene algún cambio de fotoperíodo), `luz` (tiene watts reales o algún costo energético) y `medicion` (tiene alguna medición de ambiente). Devuelve además `hechos`, `total`, `completo` y `porcentaje`.
- `recordar(cultivo)`: los pasos, o `None` si el cultivo está finalizado o archivado, tiene más de 21 días desde el inicio o ya está completo.

### fotos.py

Ruta: `growlog/services/fotos.py`. Procesa las fotos de `MedicionPlanta`. `LADO_MAXIMO = 2048`, `LADO_MINI = 480`, `PESO_SIN_TOCAR = 2_500_000` bytes.

- `preparar_foto(medicion)`: la llama `MedicionPlanta.save()` con una foto nueva. Corrige la orientación EXIF. Si el lado mayor supera 2048 px o el archivo pesa más de 2,5 MB, reemplaza la foto por un JPEG de lado máximo 2048 (calidad 85). Siempre crea `foto_mini` como JPEG de lado máximo 480 (calidad 80). Si algo falla, registra el error y guarda la original sin miniatura.

### plantas.py

Ruta: `growlog/services/plantas.py`. Resumen de cada planta para la lista y la ficha. `DIAS_MEDICION_VIEJA = 5`.

- `curva(puntos, ancho, alto, margen=3)`: convierte puntos `(día, valor)` a coordenadas SVG dentro de `ancho` por `alto`.
- `resumen_planta(planta, mediciones, hoy=None)`: recibe las mediciones de más vieja a más nueva y devuelve `altura` (última con altura), `ritmo` (cm por día entre las dos últimas alturas, 1 decimal), `ultima`, `dias_sin_medir`, `medicion_vieja` (sin mediciones o más de 5 días), `sparkline` (puntos SVG de 140 por 34, con al menos 2 alturas), `portada` (última foto), `fotos` (de la más nueva a la más vieja) y `con_altura`.

### riegos.py

Ruta: `growlog/services/riegos.py`. Guardado atómico de un riego.

- `guardar_riego(riego, detalles, nutrientes=None)`: transacción. `detalles` es una lista de dicts con `planta`, `volumen_ml` y opcionalmente `runoff_observado`, `ph_runoff`, `ec_runoff`, `notas`. `nutrientes` es una lista de `(nutriente, dosis)` o `None` para conservar los existentes. Valida antes de escribir: al menos una planta, sin plantas repetidas, todas del cultivo del riego, volumen mayor que cero, pH y EC válidos (`validacion.validar_solucion`) y dosis finitas y positivas. Si el riego ya existe, bloquea su fila. Fija `volumen_total_ml` como suma de los volúmenes, guarda el riego, borra los detalles de plantas que ya no están, actualiza o crea los demás y reemplaza los nutrientes aplicados. Lanza `ValidationError`. No comprueba permisos: eso le corresponde a quien obtuvo el cultivo.

### validacion.py

Ruta: `growlog/services/validacion.py`.

- `validar_solucion(ph=None, ec=None)`: lanza `ValidationError` si pH o EC no son números finitos. El pH debe estar entre 0 y 14; la EC debe ser mayor o igual que 0. Ignora los valores `None`.

### actividad.py

Ruta: `growlog/services/actividad.py`. Actividad de la app para el administrador: ingresos y lo que registró cada persona, derivado de `creado_por`.

- `FUENTES`: `MedicionAmbiente`, `Riego`, `MedicionEC`, `Evento` (campo `timestamp`) y `MedicionPlanta` (campo `fecha`). Tareas y plantas no cuentan porque no tienen fecha de observación. Se usa la fecha observada, no la de carga.
- `resumen_actividad(ahora=None)` devuelve un dict con:
  - `personas`: usuarios activos con `ultimo_registro`, `registros_7`, `registros_30`, `ultimo_ingreso` (el último `Ingreso` exitoso; si no hay, `last_login`), `dispositivo` y `activo_7` (registró o ingresó en los últimos 7 días). Ordenadas por la actividad más reciente.
  - `activos_7`: cantidad de personas con `activo_7`.
  - `movimientos`: los últimos 25 registros de todas las fuentes, con usuario, texto, cultivo y momento, sin fechas futuras.
  - `ingresos`: los últimos 20 `Ingreso`.
  - `fallidos_30`: ingresos fallidos en los últimos 30 días.

### registro.py

Ruta: `growlog/services/registro.py`. Alta y corrección de los registros de Registrar: `ambiente`, `riego`, `evento`, `nota`, `ec`, `tarea` y `planta` (`TIPOS`). Detalle en [registrar.md](registrar.md).

- `RegistroError(mensaje, campos=None)`: error de validación con `mensaje` y `campos` por campo.
- `validar(form_class, datos)`: valida con un formulario de `registration_forms` y devuelve `cleaned_data`, o lanza `RegistroError`.
- `guardar_registro(usuario, cultivo, tipo, observado, datos, archivos=None)`: transacción. Crea el registro del tipo indicado; la vista ya comprobó que el usuario puede editar el cultivo. En evento exige que las plantas afectadas sean activas del cultivo; en planta exige una planta activa del cultivo y respeta `puede_subir_fotos`; en riego arma los detalles por planta y los nutrientes (los que `nutrientes_para` ofrece) y delega en `riegos.guardar_riego`. Corre `full_clean()` antes de guardar.
- `actualizar_registro(usuario, obj, tipo, observado, datos, archivos=None)`: transacción. Corrige un registro con las mismas reglas. Las plantas y nutrientes que el registro ya tenía siguen siendo válidos aunque estén archivados u ocultos. En ambiente, `luz_estado` se recalcula con la hora nueva. En tarea, `completada_en` se fija al completar y se borra al reabrir.

## Templatetags

Ruta: `growlog/templatetags/`. `__init__.py` está vacío.

### ec.py

La EC se guarda en mS/cm y se muestra según la preferencia de `Perfil.unidad_ec` (ver [modelos.md](modelos.md#unidades-de-ec)). Los valores vacíos devuelven texto vacío; un valor no numérico se devuelve tal cual.

| Elemento | Resultado |
|---|---|
| `ec_us` (filtro) | mS/cm por 1000, redondeado a entero. `1,2` da `1200`. |
| `ec_x10` (filtro) | mS/cm por 100, redondeado a entero, como un medidor en escala ×10 µS/cm. `1,2` da `120`. |
| `formatear_ec(valor, unidad="us")` | Función: `us` da `1400 µS`, `ms` da `1,40 mS` (coma decimal, 2 decimales), `x10` da `140 medidor`. |
| `{% ec valor %}` (simple_tag con contexto) | Aplica `formatear_ec` con `unidad_ec` del contexto (por defecto `us`). |

### registros.py

- `{% ficha_url tipo pk %}` (simple_tag con contexto): URL de `growlog:registro_ficha` para un registro de la bitácora. Traduce el tipo de la bitácora al de la ficha: `medicion` a `ambiente`, `medicion_ec` a `ec`, y `riego`, `evento`, `planta`, `ambiente`, `ec` y `tarea` tal cual. Etapa y fotoperíodo no tienen ficha y devuelven texto vacío. Si hay `request` en el contexto agrega `?volver=<ruta actual>`.
