# Ciclo de vida de un cultivo

Recorrido de un cultivo de punta a punta: alta, primeros pasos, plantas, etapas y fotoperíodo, ajustes, cosecha guiada, cierre y reporte. Cada apartado describe las reglas que aplica el código. Las pantallas diarias están en [pantallas-cultivo.md](pantallas-cultivo.md); el modelo de datos, en [modelos.md](modelos.md); el control de acceso, en [permisos.md](permisos.md).

## Resumen del recorrido

| Paso | Ruta | Nombre | Vista | Quién accede |
|---|---|---|---|---|
| Alta | `/cultivo/nuevo/` | `nuevo_cultivo` | `views/cultivos.py` `nuevo_cultivo` | Cualquier usuario con sesión |
| Primeros pasos | `/cultivo/<slug>/empezar/` | `cultivo_empezar` | `cultivo_empezar` | Propietario y editores |
| Alta de plantas | `/cultivo/<slug>/planta/nueva/` | `planta_crear` | `views/plantas.py` `planta_crear` | Propietario y editores |
| Fotoperíodo | `/cultivo/<slug>/fotoperiodo/` | `fotoperiodo_list` | `views/mediciones.py` `fotoperiodo_list` | Propietario y editores |
| Etapa | `/cultivo/<slug>/etapa/` | `cultivo_etapa` | `cultivo_etapa` | Ver: cualquiera con acceso. Cambiar: propietario y editores |
| Flip a flora | `/cultivo/<slug>/marcar-flora/` (POST) | `cultivo_marcar_flora` | `cultivo_marcar_flora` | Propietario y editores |
| Ciclo | `/cultivo/<slug>/ciclo/` | `cultivo_ciclo` | `cultivo_ciclo` | Cualquiera con acceso |
| Ajustes | `/cultivo/<slug>/ajustes/` | `cultivo_ajustes` | `cultivo_ajustes` | Propietario y editores |
| Datos del cultivo | `/cultivo/<slug>/editar/` | `cultivo_editar` | `cultivo_editar` | Propietario y editores |
| Cosecha guiada | `/cultivo/<slug>/cosecha/` | `cultivo_cosecha` | `cultivo_cosecha` | Propietario y editores |
| Reporte | `/cultivo/<slug>/reporte/` | `reporte` | `views/reportes.py` `cultivo_reporte` | Cualquiera con acceso |
| Reabrir | `/cultivo/<slug>/reabrir/` (POST) | `cultivo_reabrir` | `cultivo_reabrir` | Propietario y editores |
| Archivar | `/cultivo/<slug>/archivar/` (POST) | `cultivo_archivar` | `cultivo_archivar` | Solo el propietario |

Todas las vistas de cultivo viven en `growlog/views/cultivos.py` salvo las indicadas. "Cualquiera con acceso" es propietario, editor o lector; las vistas que exigen edición responden 403 a un lector y 404 a quien no tiene acceso al cultivo.

## 1. Alta del cultivo

- Pantalla: `templates/growlog/nuevo_cultivo.html`. Formulario `NuevoCultivoForm` (`growlog/forms.py`).
- Campos al crear: `nombre`, `fecha_inicio` (se propone la fecha de hoy), `etapa_inicial`, `sustrato`, `carpa_dimensiones`, `notas`. Los campos de lámpara y de días estimados se quitan del formulario de alta; se piden en los primeros pasos.
- `etapa_inicial` ofrece las cinco primeras etapas (Plántula, Veg. temprano, Veg. tardío, Flora temprana, Flora tardía). No es obligatoria: sin elegir se usa `veg_temprano`.
- Al guardar: `creado_por` y `propietario` quedan en el usuario que crea. El `slug` sale del nombre (`slugify`); si ya existe se agrega `-2`, `-3`, etc.; si el nombre no tiene letras ni números el slug base es `cultivo`.
- Se llama a `cambiar_etapa(cultivo, etapa_inicial, cultivo.fecha_inicio)`, que crea el primer registro del historial de etapas y deriva `estado` y `fecha_inicio_flora`.
- Redirige a `cultivo_empezar` con un mensaje de éxito.
- El campo `estado` del cultivo toma por defecto `vegetativo` y luego lo gobierna el historial de etapas (ver apartado 4).

## 2. Primeros pasos

Vista `cultivo_empezar`, template `cultivo_empezar.html`, lógica en `growlog/services/onboarding.py`.

`pasos(cultivo)` devuelve cinco pasos, cada uno con `clave`, `titulo`, `detalle`, `hecho` y `url`:

| Clave | Se considera hecho cuando | Dónde se completa |
|---|---|---|
| `duracion` | `dias_veg_estimados` y `dias_flora_estimados` tienen valor | Formulario en la misma pantalla (`DuracionCultivoForm`, ambos campos obligatorios) |
| `plantas` | El cultivo tiene al menos una planta | `planta_crear` (se abre con `?desde=empezar`) |
| `fotoperiodo` | Existe algún cambio de fotoperíodo | `fotoperiodo_list` |
| `luz` | `lampara_watts_reales` tiene valor o el cultivo tiene algún equipo de energía asignado | Formulario en la misma pantalla (`LuzCultivoForm`: `lampara_modelo` y `lampara_watts_reales`, este último obligatorio) |
| `medicion` | El cultivo tiene alguna medición de ambiente | Registrar en `?cultivo=<id>&kind=ambiente` (ver [registrar.md](registrar.md)) |

- También devuelve `hechos`, `total` (5), `completo` y `porcentaje` (redondeado).
- Los formularios de `duracion` y `luz` se envían por POST con un campo oculto `accion` (`duracion` o `luz`); al guardar, la pantalla se recarga. Un paso ya hecho muestra "Cambiar", que despliega su formulario.
- El botón final dice "Listo, ir al cultivo" si el checklist está completo y "Seguir después" si no; ambos llevan a `cultivo_detail`.
- Recordatorio en el cultivo: `recordar(cultivo)` devuelve los pasos solo si el cultivo no está finalizado ni archivado, tiene `DIAS_RECORDATORIO` (21) días o menos desde su inicio y el checklist no está completo. `cultivo_detail` lo muestra como tarjeta "Primeros pasos" únicamente a quien puede editar.
- Desde Ajustes hay un enlace a esta pantalla mientras el cultivo no está finalizado.

## 3. Alta de plantas

Vista `planta_crear` (`views/plantas.py`), template `plantas_nuevas.html`, formulario `PlantasNuevasForm`.

- Campos: `cantidad` (1 a 30, por defecto 1), `strain` (opcional, hasta 120 caracteres), `tipo` (`foto` fotoperiódica, por defecto, o `auto` autofloreciente).
- Los apodos llegan como campos sueltos `apodo-1`, `apodo-2`, etc. Un apodo vacío se reemplaza por `"<strain> <n>"`, o `"Planta <n>"` si no hay strain. Los apodos se recortan a 60 caracteres.
- Las plantas se crean juntas con `bulk_create`, con `creado_por` en el usuario actual. Posición en la carpa, yield estimado y demás datos se editan después en cada planta (`planta_editar`).
- Redirige a `cultivo_empezar` si vino de los primeros pasos (`siguiente=empezar`) y a `plantas_list` en otro caso.
- Una planta nueva queda `estado="activa"` y hereda la etapa del cultivo (ver apartado 4).

Borrado de una planta (`planta_eliminar`): si tiene riegos, mediciones, cambios de etapa, posiciones de cola en Canopy o eventos (`Planta.tiene_historial()`), no se borra: se archiva (`archivado=True`) y se restaura editándola. Sin historial se borra.

## 4. Etapas y fotoperíodo

### Etapa del cultivo

La etapa se guarda como historial de `CambioEtapaCultivo` (una fila por fecha de inicio, única por cultivo y fecha). Las siete etapas son `plantula`, `veg_temprano`, `veg_tardio`, `flora_temprana`, `flora_tardia`, `secado` y `curado`.

`growlog/services/etapas.py`:

| Función | Qué hace |
|---|---|
| `cambiar_etapa(cultivo, etapa, fecha, notas="")` | `update_or_create` por `(cultivo, fecha)`: repetir la misma fecha corrige el registro de ese día. Luego llama a `sincronizar_cultivo`. Es la única vía prevista para escribir `estado` y `fecha_inicio_flora`. |
| `sincronizar_cultivo(cultivo)` | Recalcula `fecha_inicio_flora` como la fecha mínima entre las etapas de flora (`flora_temprana`, `flora_tardia`), o `None` si no hay. Si hay etapas con fecha de inicio menor o igual a hoy y el cultivo no está finalizado, fija `estado` según la última de ellas. Descarta las memorias de etapa de la instancia. |
| `reabrir_cultivo(cultivo)` | Pone `estado="vegetativo"` y `fecha_fin=None`, y sincroniza: si hay historial, el estado vuelve a salir de la última etapa vigente. |

Correspondencia etapa a `estado`: `plantula` a `plantula`; `veg_temprano` y `veg_tardio` a `vegetativo`; `flora_temprana` y `flora_tardia` a `floracion`; `secado` a `secado`; `curado` a `curado`. El estado `finalizado` no se pisa al sincronizar.

Consecuencias de la regla de `fecha_inicio_flora`:

- Pasar de flora temprana a flora tardía no reinicia el día de flora.
- Un cambio de etapa con fecha futura no cambia el estado hasta que llegue esa fecha.
- Sin historial de etapas, la etapa efectiva (`utils.etapa_efectiva_cultivo`) sale del estado: `plantula`, `vegetativo` a `veg_temprano`, `floracion` a `flora_temprana`, `secado`, `curado`; `finalizado` no tiene etapa.

`Cultivo.dia_flora` es `fecha_referencia - fecha_inicio_flora` en días (el día del flip es el 0) y es `None` si no hay inicio de flora o este es posterior a la referencia. `fecha_referencia` es hoy, o `fecha_fin` si el cultivo ya cerró y esa fecha es anterior.

El rango ideal de VPD de una medición usa la etapa vigente del cultivo en la fecha de la medición.

Pantallas:

- `cultivo_etapa` (`etapa_historial.html`): etapa actual, formulario para cambiarla (etapa, fecha de inicio, notas; fecha propuesta: hoy) e historial. Quien solo lee ve el historial sin formulario. Al guardar llama a `cambiar_etapa`.
- `cambio_etapa_cultivo_editar` y `cambio_etapa_cultivo_eliminar` corrigen o borran un registro del historial (con `crud_form.html` y `crud_delete.html`) y luego sincronizan el cultivo.

### Etapa de la planta

`CambioEtapaPlanta` es un reemplazo opcional por planta (`planta_etapa_list`, `cambio_etapa_planta_editar`, `cambio_etapa_planta_eliminar`). `etapa_efectiva_planta` usa la etapa propia solo si su fecha es igual o posterior a la del último cambio de etapa del cultivo; si no, la planta hereda la del cultivo.

### Fotoperíodo

- `fotoperiodo_list` (`fotoperiodo.html`): formulario y historial de `CambioFotoperiodo`, con accesos rápidos 20/4, 18/6 y 12/12 (hora de encendido 06:00). Campos: `fotoperiodo` (formato `N/M`), `hora_lights_on`, `fecha_inicio` (hoy por defecto), `notas`.
- Validación (`CambioFotoperiodo.clean`): dos números enteros positivos separados por `/` que sumen 24. Hay un registro por `(cultivo, fecha_inicio)`.
- Corrección y borrado: `cambio_fotoperiodo_editar` y `cambio_fotoperiodo_eliminar`.
- El fotoperíodo vigente se resuelve por fecha (el último con `fecha_inicio` menor o igual al momento consultado). Con él se calcula el estado de la luz de cada medición de ambiente (`luz_estado`, encendida o apagada).

### Flip a flora

`services/ciclo.hacer_flip(cultivo, fecha=None)`:

- Si el cultivo ya tiene `fecha_inicio_flora`, no hace nada y devuelve `False`.
- Si no, aplica `cambiar_etapa(cultivo, "flora_temprana", fecha, notas="Flip")` y, si el fotoperíodo vigente no es 12/12 (o no hay ninguno), crea o actualiza el cambio de fotoperíodo de esa fecha con `12/12` y notas "Flip". La hora de encendido se conserva del fotoperíodo vigente; sin uno vigente se usa 06:00. Todo en una transacción.

`cultivo_marcar_flora` (POST) lo invoca con la fecha de hoy y redirige a Ciclo. Si ya había flora, muestra un mensaje informativo con la fecha de inicio y no cambia nada.

### Pantalla Ciclo

`cultivo_ciclo` (`ciclo.html`, `services/ciclo.resumen_ciclo`) compara cada fase con lo estimado:

- Fases: Plántula, Veg (veg temprano y tardío), Flora (flora temprana y tardía), Secado (10 días orientativos) y Curado (21 días orientativos).
- Estimados: `dias_veg_estimados` para Veg; para Flora, `dias_flora_estimados` del cultivo o, si no hay, el mayor `dias_flora_estimados` entre las plantas activas. Plántula no tiene estimado.
- Días reales por fase: se suman desde cada cambio de etapa hasta el siguiente (el último, hasta la fecha de referencia o hoy, la menor).
- Muestra el botón "Hacer el flip hoy" mientras el cultivo no tiene inicio de flora ni está finalizado, y solo a quien puede editar. Junto al botón muestra la etapa y el fotoperíodo actuales, y el porcentaje de la red SCROG del último snapshot de Canopy.
- Con flora iniciada, muestra el día de flora y la cosecha estimada (`fecha_inicio_flora + días de flora estimados`, si hay estimado) con los días que faltan.
- Con el cultivo en secado, curado o finalizado, enlaza a la cosecha ("Seguir con la cosecha" o "Ver la cosecha").
- Lista los historiales de etapas y de fotoperíodo, con enlaces de corrección para quien edita.

## 5. Ajustes del cultivo

`cultivo_ajustes` (`cultivo_ajustes.html`) reúne la configuración. Exige permiso de edición; para un lector la pestaña "Ajustes" no existe.

| Entrada | Destino | Condición |
|---|---|---|
| Primeros pasos | `cultivo_empezar` | Cultivo no finalizado |
| Datos del cultivo | `cultivo_editar` | Siempre |
| Etapa | `cultivo_etapa` | Siempre |
| Fotoperíodo | `fotoperiodo_list` | Siempre |
| Equipos y consumo eléctrico | `energia` (ver [pantallas.md](pantallas.md)) | Siempre |
| Nutrientes | `nutrientes` | Siempre |
| Compartir | `invitados_panel` | Solo el propietario |

Bloque "Ciclo del cultivo":

- Cultivo no finalizado: botón "Cosecha y cierre" hacia `cultivo_cosecha`.
- Cultivo finalizado: botón "Reabrir cultivo" (POST a `cultivo_reabrir`, con confirmación en el navegador).
- Solo el propietario: botón "Archivar" o "Desarchivar" (POST a `cultivo_archivar`).

Acciones:

- `cultivo_editar` (`crud_form.html`): edita con `NuevoCultivoForm` los campos nombre, fecha de inicio, sustrato, carpa, lámpara (modelo y watts reales), días estimados de vege y de flora, y notas. No incluye etapa inicial. No cambia el `slug`. Redirige a `cultivo_detail`.
- `cultivo_archivar`: alterna `archivado`. Si el usuario no es el propietario responde 403. Un cultivo archivado pasa al grupo "historial" del selector de cultivos y no se borra ningún dato.
- `cultivo_reabrir`: si el cultivo está finalizado, llama a `reabrir_cultivo` (quita `fecha_fin` y recupera el estado desde el historial de etapas); si no lo está, informa que no estaba finalizado. Redirige a `cultivo_detail`. Las plantas ya cortadas conservan su estado `cosechada` y sus pesos.

## 6. Cosecha guiada

Vista `cultivo_cosecha` (`views/cultivos.py`), template `cosecha.html`, lógica en `growlog/services/cosecha.py`. Exige permiso de edición. Cuatro pasos, cada uno repetible para corregir: Cortar, Pesar en húmedo, Secar y Cerrar.

### Datos que usa

Campos de `Planta` (ver [modelos.md](modelos.md)):

| Campo | Significado |
|---|---|
| `fecha_corte` | Día de corte |
| `peso_humedo_g` | Peso húmedo en gramos (entero positivo) |
| `yield_real_g` | Peso seco en gramos; es el yield real |
| `fecha_seco` | Fin del secado |
| `estado` | Pasa de `activa` a `cosechada` al cortar |

`plantas_de_cosecha(cultivo)` toma las plantas no archivadas con estado `activa` o `cosechada`, ordenadas por apodo; las descartadas no entran.

`resumen(cultivo)` calcula lo que muestra la pantalla:

| Valor | Cálculo |
|---|---|
| `cortadas` / `sin_cortar` | Plantas de la cosecha con y sin `fecha_corte` |
| `hechos.cortar` | Hay cortadas y no quedan sin cortar |
| `hechos.pesar` | Hay cortadas y todas tienen `peso_humedo_g` |
| `hechos.secar` | Hay cortadas y todas tienen `yield_real_g` |
| `hechos.cerrar` | `estado == "finalizado"` |
| `actual` | Primer paso sin hacer, o `cerrar` |
| `humedo_total`, `seco_total` | Sumas sobre las cortadas |
| `merma` | `round(100 * (1 - seco / humedo))` sobre las plantas que tienen ambos pesos; `None` si no hay |
| `g_por_watt` | `round(seco_total / lampara_watts_reales, 2)`; `None` sin peso seco o sin watts |
| `etapa` | Etapa efectiva actual del cultivo |

### Reglas por paso

Todos los pasos se envían por POST al mismo URL con un campo `accion` (`cortar`, `pesar`, `secar`, `cerrar`). Si no hay errores se redirige a la misma pantalla.

| Paso | Campos del formulario | Efecto |
|---|---|---|
| Cortar (`cortar`) | `plantas` (casillas, una por planta sin cortar, marcadas por defecto), `fecha` (hoy por defecto), `etapa` (casilla "Pasar el cultivo a Secado", marcada por defecto; solo aparece si la etapa actual no es secado ni curado) | Para cada planta elegida: `fecha_corte = fecha`, `estado = "cosechada"`. Con `etapa` marcada y etapa actual distinta de secado y curado, ejecuta `cambiar_etapa(cultivo, "secado", fecha)`. Se puede cortar en tandas; las que no se eligen siguen activas. Sin plantas elegidas: error "Elegí al menos una planta." |
| Pesar (`pesar`) | `peso-<id de planta>` por cada cortada | Guarda `peso_humedo_g`. Un campo vacío deja el peso como estaba. No usa fecha. |
| Secar (`secar`) | `peso-<id de planta>`, `fecha` (fin del secado), `etapa` (casilla "Pasar el cultivo a Curado", marcada por defecto; aparece si la etapa actual no es curado) | Para cada planta con peso: `yield_real_g = peso` y `fecha_seco = fecha`. Con `etapa` marcada y etapa actual distinta de curado, ejecuta `cambiar_etapa(cultivo, "curado", fecha)`. |
| Cerrar (`cerrar`) | Ninguno | `cosecha.cerrar`: `estado = "finalizado"` y, si `fecha_fin` está vacía, `fecha_fin = hoy`. Redirige al reporte con el mensaje "Cultivo ... cerrado. Este es su reporte." |

Validaciones del formulario:

- La `fecha` debe estar entre `fecha_inicio` del cultivo y hoy; si no, error "La fecha tiene que estar entre el inicio del cultivo y hoy." y no se aplica el paso.
- Los pesos aceptan coma o punto decimal y se redondean a gramos enteros. Deben ser mayores que 0 y, para `pesar`, de hasta 1.000.000; para `secar`, de hasta 32.767 (campo `PositiveSmallIntegerField`). Un valor no numérico o fuera de rango da el error "El peso de <apodo> no es válido." y no se guarda ningún peso del envío.
- Los pasos Pesar y Secar muestran un aviso si no hay plantas cortadas ("Primero cortá alguna planta."). En Secar se muestra el estimado de cada planta (`yield_estimado_g`) si lo tiene.

### Cierre y finalización

- El paso Cerrar muestra los totales (seco, húmedo, merma y g por watt) cuando hay plantas cortadas. Al pedir confirmación en el navegador avisa si quedan plantas sin cortar. El botón se muestra con estilo secundario mientras no estén todos los pesos secos.
- Cerrar no exige haber completado los pasos anteriores.
- Un cultivo finalizado muestra "Cerrado el <fecha>" con enlace al reporte, y el botón de cierre no aparece.
- Estado `finalizado`: `sincronizar_cultivo` no lo modifica aunque cambie el historial de etapas. `fecha_referencia` pasa a ser `fecha_fin`, de modo que `dias_desde_inicio` y `dia_flora` quedan fijos en el día del cierre.
- En el resumen del cultivo, un cultivo finalizado no calcula el estado de la luz actual ni los días sin riego. En el selector de cultivos aparece en el grupo "historial".
- Para deshacer el cierre se usa `cultivo_reabrir` (apartado 5).

## 7. Reporte de cierre

Vista `cultivo_reporte` (`views/reportes.py`), template `reporte.html`, datos de `growlog/services/reporte.reporte(cultivo)`. Se puede abrir con el cultivo en cualquier estado (con el cultivo en curso muestra "en curso" como fecha de fin y usa hoy como fin). Acceso de lectura para cualquiera con acceso al cultivo.

`?export=csv` descarga `<slug>-registros.csv` (UTF-8 con BOM, separador `;`) con las columnas `fecha`, `hora`, `tipo`, `dato`, `ph`, `ec`, `volumen_ml`, `temperatura_c`, `humedad_pct`, `vpd_kpa`, `notas`, ordenadas por momento. Incluye mediciones de ambiente (`medicion`), riegos (`riego`, con nutrientes y dosis en las notas), mediciones de EC y pH (`medicion_ec`) y eventos (`evento`).

### Cifras de cabecera

`cifras(cultivo)` reúne lo que se compara entre cultivos.

| Cifra | Cálculo |
|---|---|
| Duración | `fin - fecha_inicio` en días, con `fin = fecha_fin` o hoy. Muestra días de vege y de flora si hay inicio de flora (de `fecha_inicio_flora` o, si no, del primer fotoperíodo de 12 horas de luz o menos); sin él, "sin flip registrado" |
| Seco | Suma de `yield_real_g` de las plantas no archivadas y no descartadas, con el estimado (suma de `yield_estimado_g`) y los g por planta pesada |
| g por watt | `seco / lampara_watts_reales`, redondeado a 2 decimales |
| Costo por gramo | `round(costo / seco)`, si hay costo y peso seco (ver más abajo) |
| Aire en rango | Porcentaje de lecturas de ambiente cuyo VPD cae en el ideal de su etapa (`vpd.estado_de`); las lecturas sin ideal aplicable no cuentan |
| Agua | Litros totales de riego (`volumen_total_ml / 1000`), cantidad de riegos y pH promedio de agua; muestra también la merma si hay plantas con peso húmedo y seco |

### Costo de energía

`_energia(cultivo, fin, seco)` elige la fuente así, de menor a mayor prioridad:

1. `lampara`: si el cultivo no tiene equipos de energía asignados pero sí `lampara_watts_reales`, los kWh salen de `watts / 1000 * horas de luz * días` de cada tramo de fotoperíodo. No se calcula costo.
2. `equipos`: si hay equipos asignados, `calcular_meses` (ver `services/energia.py` y [pantallas.md](pantallas.md)) estima los kWh por mes y el costo con la tarifa vigente de cada mes. El costo solo se calcula si el cultivo tiene alguna tarifa con fecha anterior o igual al fin.
3. `medidor`: si hay lecturas del medidor hasta el fin, los kWh son la suma de las lecturas y el costo es esa suma por el precio de la tarifa más reciente hasta el fin. Esta fuente reemplaza a las anteriores.

El resultado incluye `kwh`, `costo`, `fuente`, `costo_por_gramo` y `g_por_kwh` (`seco / kwh`, 2 decimales; el template no lo muestra). La tarjeta de costo por gramo aclara si el costo es "según el medidor" o "estimado por equipos".

### Secciones del reporte

| Sección | Contenido |
|---|---|
| Aire en rango por semana | Porcentaje total, de día y de noche (según `luz_estado` de cada lectura) y una barra por semana del ciclo (verde desde 70 %, ámbar desde 40 %, rojo por debajo) |
| Crecimiento | Una línea por planta con al menos dos mediciones de altura, en un mismo eje de días del cultivo y centímetros |
| Yield por planta | Barras de estimado y real en la misma escala, con enlace a cada planta. Si no hay peso seco y el usuario puede editar, enlaza a Cosecha |
| Contra tus cultivos anteriores | Tabla con este cultivo y otros hasta 5 cultivos del mismo propietario con estado `finalizado`, del más reciente al más antiguo (por `fecha_fin` y `fecha_inicio`); columnas: días, seco, g por watt, aire en rango y costo por gramo. Cada fila enlaza al reporte de ese cultivo. Sin cultivos anteriores cerrados, la sección lo indica |
| Nutrientes | Por nutriente aplicado: cantidad de aplicaciones, dosis promedio y total (dosis por litro por volumen del riego) |
| Ambiente | Mínimo, promedio y máximo de temperatura, humedad y VPD sobre todas las mediciones |
| Eventos | Cantidad de eventos por tipo |

La comparación toma los cultivos del propietario del cultivo abierto, sin importar quién mira el reporte. Un cultivo sin propietario no tiene comparación.
