# 62×ROOTS: Brief de rediseño completo (para Claude Design)

> Relevamiento hecho el 2026-11-02 leyendo todo el código (vistas, servicios, modelos, 36 templates, CSS, JS, PWA). Describe **cómo es la app hoy**, qué datos tiene, por dónde se mueve el usuario y qué está roto o confuso. No propone un diseño: el objetivo es que Claude Design defina un **rumbo nuevo** con toda la información a la vista.
>
> Cómo leerlo: §1–2 contexto y usuarios · §3 datos que existen · §4–5 mapa y pantallas · §6 flujos clave · §7 sistema visual actual · §8 problemas consolidados · §9 oportunidades · §10 qué conservar · §11 restricciones · §12 decisiones que hay que tomar.

---

## 1. Qué es el producto

- **62×ROOTS** (también aparece como "62xroots", "62xROOTS" y "GrowLog"): una **bitácora de cultivo indoor de cannabis**, en español rioplatense (voseo), locale es-AR, hora de Argentina.
- Raíz de todo: el **Cultivo** (una carpa/ciclo). Dentro hay plantas, riegos, mediciones de ambiente, pH/EC, observaciones (eventos), tareas, etapas, fotoperíodo, canopy SCROG y energía.
- **Usuarios reales**, pocos: un cultivador dueño y personas con las que comparte cultivos (editores que cargan datos, lectores que miran). Hay un superusuario (el dueño de la app) con panel de actividad y admin.
- **Contexto de uso dominante: el celular, adentro o al lado de la carpa.** Con poca luz o con la luz de cultivo encendida, manos ocupadas o sucias, apuro. Se instala como **PWA** (standalone, tema oscuro, atajos "Registrar" y "Hoy", notificaciones push de pendientes). La compu se usa para mirar historial, reportes y configurar.
- **Stack** (condiciona el diseño): Django con templates renderizados en el servidor, formularios POST de página completa, un poco de HTMX (completar tareas, resolver seguimientos) y Alpine (solo canopy y edición de riego), uPlot para gráficos. Hoy se cargan Bootstrap 5.3 completo y Bootstrap Icons. No es una SPA y no hay modo offline (el service worker solo maneja push).
- Tiene una **API JSON v1** con token que usa un asistente de IA (skill "growlog") para leer el cultivo. Hoy equipos y tarifas eléctricas solo se pueden cargar por API o por el admin.

## 2. Usuarios, roles y frecuencia de tareas

### Roles
| | Dueño | Editor ("Puede registrar y editar") | Lector ("Solo lectura") |
|---|---|---|---|
| Ver cultivo y pestañas | ✓ | ✓ | ✓ (sin Ajustes) |
| Registrar, editar, borrar registros | ✓ | ✓ | ✗ |
| Etapa, fotoperíodo, datos, plantas, canopy, lecturas de medidor | ✓ | ✓ | ✗ (puede *ver* Etapa y Energía) |
| Finalizar / reabrir el cultivo | ✓ | ✓ | ✗ |
| Archivar | ✓ | ✗ | ✗ |
| Compartir y gestionar accesos | ✓ | ✗ | ✗ |
| Recibir push de pendientes | ✓ | ✓ | ✗ |

- Además: subir fotos requiere un permiso especial (por defecto está **apagado para casi todos**). El superusuario edita el catálogo compartido de nutrientes y ve `/actividad/` y `/admin/`.
- Hoy el solo-lectura se señala con un ojito en el selector, una etiqueta "solo lectura" junto al usuario y botones deshabilitados. No hay un estado de lectura diseñado.

### Frecuencia real de tareas (para priorizar la jerarquía)
- **Varias veces por día / diario:** mirar el estado ("¿cómo está la carpa?"), registrar **ambiente** (temperatura y HR, de donde sale el VPD), **riego** (volumen por planta, pH/EC de la solución, nutrientes, runoff), **observaciones** y completar **tareas**.
- **Semanal:** pH/EC sueltos, **mediciones de planta** (altura, nudos, canopy, aspecto, síntomas) y **fotos**, revisar tendencias.
- **Una vez por ciclo:** crear cultivo, dar de alta plantas, configurar fotoperíodo y setup, el **flip a flora** (cambio de etapa más fotoperíodo 12/12), canopy SCROG, **cosecha** (yield por planta) y **finalizar** el cultivo. Después, reporte.
- **Ocasional:** compartir, catálogo de nutrientes, energía (equipos, tarifas, lecturas de medidor), dudas/FAQ.

---

## 3. Información que existe (modelo de datos orientado al usuario)

**Cultivo**
- Se carga: nombre, fecha de inicio, carpa (texto "80x80x180"), sustrato, lámpara (modelo y watts reales), días estimados de veg y de flora, notas.
- Derivados:
  - estado (Plántula / Vegetativo / Floración / Secado / Curado / Finalizado);
  - fecha de inicio de flora;
  - **día N** (el día 0 es el inicio, se congela al finalizar) y **día de flora N** (el día 0 es el flip);
  - progreso % (días transcurridos / días estimados);
  - **días sin riego**;
  - luz encendida/apagada *ahora* (según el fotoperíodo).
- Ciclo de vida: activo → finalizado (con fecha de fin) y/o archivado.

**Etapas:** 7 etapas finas: Plántula, Veg. temprano, Veg. tardío, Flora temprana, Flora tardía, Secado, Curado. Cada cambio queda con fecha y notas. Una planta puede tener su propia etapa, que se pisa si después cambia la del cultivo. La UI mezcla **dos vocabularios**: la etapa fina ("Flora temprana") y el estado grueso ("Floración").

**Fotoperíodo:** historial de cambios "18/6", "12/12"… (las horas suman 24), con hora de encendido, fecha y notas.

**Planta**
- Se carga: apodo, strain, tipo (fotoperiódica o automática), posición en la carpa (centro o una de las 4 esquinas), días de flora estimados, ratio índica/sativa, THC estimado, yield estimado y **yield real**, estado (activa / cosechada / descartada), notas de genética, archivada.

**Medición de planta:** fecha, altura cm, nudos, ancho de canopy cm, aspecto (bueno / regular / malo), síntomas, **foto** (máx. 5 MB).

**Medición de ambiente:** fecha y hora, temperatura °C, HR %, notas. Derivados: **VPD** (kPa) con semáforo ideal/alto/bajo según la etapa vigente a esa fecha, y luz prendida/apagada en ese momento.

**pH / EC:** fecha y hora, qué se midió (agua de entrada / solución / runoff / sustrato), pH, EC, temperatura del agua, notas.
- **La EC se tipea "×10 µS/cm"** (como la lee el medidor: 120), se guarda en mS/cm (1,20) y se muestra en µS/cm (1200). Hay tres representaciones del mismo número.

**Riego:** fecha y hora, pH y EC de la solución, "midió runoff", notas.
- Por planta: ml, runoff observado, pH y EC del runoff, notas.
- Nutrientes aplicados con dosis en g/L.
- El total de ml se calcula solo.

**Nutriente (catálogo):** nombre, marca, NPK, etapa recomendada (veg / flora / aditivo), dosis mínima y máxima en g/L.
- Puede ser compartido (lo administra el admin), propio, o de otro dueño cuyo cultivo te compartieron.
- Un nutriente que ya se usó no se borra: se oculta.

**Observación / Evento:** fecha y hora, tipo (Topping, LST, Defoliación, Transplante, Problema, Diagnóstico, Ajuste de ambiente, Cambio de ciclo, Otro), descripción, plantas afectadas, **seguimiento** (fecha, qué revisar, resuelto).

**Tarea:** título, detalle, fecha objetivo, prioridad (Urgente / Normal / Baja), categoría (Riego / Training / Mantenimiento / Compra / Observación), completada (con fecha).

**Canopy SCROG:** snapshots con el % de red llena (grilla 6×6), la posición de cada "cola" por planta y notas. Calcula W por cola, colas/m² y si llegó al punto de flip (60 %) u óptimo (80 %).

**Energía:** equipos (watts, horas/día, categoría), tarifas ($/kWh, distribuidora, desde cuándo), vínculo equipo↔cultivo por fechas, lecturas reales del medidor. Derivados: kWh y $ por mes y acumulado, $/g.

**Rangos ideales (ParametroIdeal):** una tabla global por etapa con rangos de temperatura, HR, VPD, **pH, EC, horas de luz y distancia de la luz**. Solo se usan temperatura, HR y VPD. Solo se editan en el admin y el usuario no los puede ver.

**Sistema:** autor de cada registro (`creado_por`), membresías con rol, suscripciones push, log de ingresos.

---

## 4. Mapa actual y navegación

```
/login/ (página propia)
└─ / "Hoy" (inicio)
   ├─ /registrar/  (única carga diaria: Ambiente | Riego | Observación | pH/EC | Tarea)
   ├─ /cultivo/nuevo/
   ├─ /invitados/  "Compartir cultivos" (global)
   ├─ /dudas/      FAQ estática con buscador
   ├─ /nutrientes/ catálogo (solo se llega desde Ajustes o Registrar)
   ├─ /actividad/  (superusuario)   /admin/ (superusuario + staff)
   └─ /cultivo/<slug>/  PESTAÑAS:
      Resumen · Bitácora · Tareas · [Más:] Tendencias · Canopy · Energía · Reporte · Ajustes
      ├─ /planta/<pk>/ (+ etapa propia, + medición/foto, editar, archivar)
      ├─ Ajustes → Datos · Etapa · Fotoperíodo · Equipos (=Energía) · Nutrientes (global) · Compartir (global) · Finalizar/Reabrir · Archivar
      └─ editar/eliminar de cada registro (formularios genéricos de página completa)
```

**Navegación hoy:**
- **Barra superior:**
  - Desktop: marca "62×ROOTS / grower's terminal", **selector de cultivo** (grupos: mis activos / compartidos conmigo / historial, más "Ver todos" y "Nuevo cultivo"), links "hoy · registrar · compartir · dudas (· actividad · admin)", **reloj en vivo con segundos**, campana de push, usuario con logout (solo ícono).
  - Mobile: marca y selector más hamburguesa (adentro van logout y campana).
- **Pestañas del cultivo:** las 8 en desktop. En ≤991px solo Resumen/Bitácora/Tareas y un "Más ▾".
- **Barra inferior mobile:**
  - Fuera de un cultivo: Inicio · **Registrar** · Compartir · Dudas.
  - Dentro de un cultivo: Inicio · Resumen · **Registrar** · Bitácora · Tareas.
  - En formularios: un solo "← Volver".
- **Elegir cultivo:** tarjetas de Hoy, selector o la preselección de Registrar (el último cultivo abierto, guardado en sesión). Al entrar siempre se cae en Hoy.

---

## 5. Pantallas, una por una

### Login
- Página propia: "BIENVENIDO / log de cultivo", usuario, contraseña y "recordar sesión" (marcado por defecto).
- Pie: "// grower's terminal · v0.3 · alansaja13/62xroots".
- Bloqueo tras 10 intentos. Tiene los tokens de color duplicados a mano.
- **No existe:** registro, recuperar contraseña, cambiar contraseña ni perfil.

### Hoy (inicio)
1. Encabezado "Tu bitácora · fecha / **Hoy**" con [Registrar] [Nuevo cultivo] (ocultos en mobile).
2. Tres contadores: N para revisar · N cultivos activos · N sin medición de ambiente de hoy.
3. **Para revisar** (máx. 12): tareas vencidas, de hoy o urgentes, y seguimientos vencidos. Cada ítem lleva tag de fecha, urgente, título, cultivo y [Revisar]. "Revisar" lleva a la lista genérica de tareas, no a la tarea, y no permite completarla ahí.
4. **Mis cultivos activos:** tarjetas con estado, plantas activas, inicio, última T / HR / VPD, frescura del dato ("Medido hoy" / "Medición anterior a hoy") y [Registrar].
5. **Compartidos conmigo:** las mismas tarjetas con el rol y el dueño.
6. **Historial:** lista simple de finalizados y archivados.

Estados vacíos:
- Sin cultivos: "Tu bitácora empieza con un cultivo" con CTA.
- Sin activos pero con historial: no hay CTA.

Hoy no muestra días sin riego, etapa, día de flora ni plantas.

### Registrar (la acción principal)
- Arriba: dos `<select>` en la misma fila, **Cultivo** y **¿Qué querés registrar?** (por defecto Ambiente).
- Después: **Cuándo ocurrió** (fecha y hora completas, precargada con la hora en que se abrió la página).
- Un bloque por tipo:
  - **Ambiente:** temperatura y HR (números grandes), notas. No muestra el VPD mientras se carga.
  - **Riego:**
    - un input de ml **por cada planta activa** (vacío = no se regó);
    - por planta, un desplegable "runoff" con checkbox, pH, EC y notas;
    - pH y EC de la solución;
    - un desplegable "Nutrientes" con un input de g/L **por cada nutriente del catálogo**;
    - checkbox "midió runoff", notas.
    - No hay "mismo volumen para todas", "repetir el último riego" ni nada precargado.
  - **Observación:** tipo (por defecto "Otro"), descripción obligatoria, desplegable de plantas afectadas, desplegable "programar seguimiento".
  - **pH/EC:** qué se midió, pH, EC ×10, temperatura del agua, notas. Hay que cargar al menos pH o EC.
  - **Tarea:** título, detalle, categoría (por defecto Observación), prioridad, fecha.
- Se registra **un solo tipo por envío**.
- **Valores raros** (temperatura fuera de 10–40, HR <15, pH fuera de 4–9, EC >5 mS/cm, dosis >10 g/L): aparece una caja "Estos valores son poco comunes" con [Guardar igual], que confirma *todos* los avisos.
- Errores: caja arriba con la lista. **No se marca el campo**, y los errores por planta no dicen de qué planta se trata.
- Después de guardar: vuelve al mismo tipo en blanco con un mensaje (con errores de concordancia: "Tarea guardado"). No hay link al registro ni deshacer.
- Registrar **saca al usuario del contexto del cultivo**: no hay pestañas y la barra inferior pasa a la global.
- Fuera de Registrar quedan: mediciones y fotos de planta, alta de plantas, etapa, fotoperíodo, canopy y lecturas de medidor.

### Resumen del cultivo
De arriba hacia abajo:
1. **Header:** nombre gigante (88px), pill de etapa (lleva a Etapa), "desde · N plantas", días sin riego (ámbar a partir de 3, rojo a partir de 5), cajas "día N" y "flora N", [cambiar etapa] [registrar].
2. **4 vitales:** temperatura, HR, VPD (con semáforo según la etapa) y EC/pH. Debajo, en 10px: "última medición hace X". El semáforo se ve grande aunque el dato sea viejo.
3. **Luz:** indicador **neón animado** de luz encendida/apagada, más una tira de setup (fotoperíodo, lámpara, sustrato, carpa, "editar →").
4. **Barra de progreso veg/flora:** solo aparece si se cargaron días estimados, cosa que el alta no pide.
5. Dos columnas:
   - **Izquierda:**
     - "§ actividad reciente": los últimos 8 registros en una tabla de 5 columnas, con [+ evento][+ riego][+ EC/pH] y "bitácora completa →". En mobile la tabla pasa a tarjetas.
     - "§ plantas": filas 01, 02… con apodo, strain, posición y etapa. El estado se marca solo con el color del borde.
   - **Derecha:** tareas pendientes (checkbox HTMX de 16–18px), seguimientos pendientes (✓ HTMX) y completadas (plegado).
6. En mobile lo accionable (tareas, seguimientos) **cae al final**, debajo de la tabla y las plantas.
7. No tiene gráficos, sparklines, ni nada de energía o canopy.

### Bitácora
- Filtros tipo chip: todo / ambiente / riego / evento / EC-pH, con contadores.
- Tabla: fecha y autor / tipo / dato / detalle / notas / ⋯.
- **Tope fijo de 200 entradas**, sin paginación, sin filtro por fecha, planta, autor ni texto.
- No incluye cambios de etapa ni de fotoperíodo, mediciones ni fotos de planta, tareas hechas ni canopy.
- Bugs: muestra el código crudo del tipo de evento ("ajuste_ambiente") y "VPD · None" cuando no hay rango.

### Tareas
- Filtros pendientes / completadas / todas, más categoría.
- Tabla de 7 columnas paginada de a 20 (en mobile pasa a tarjetas). Las vencidas en rojo.
- Completar con HTMX hace desaparecer la fila. No hay reabrir acá.
- "+ nueva tarea" manda a Registrar.

### Tendencias
- uPlot con 7d / 30d / todo. Tres gráficos apilados: temperatura, HR y VPD, con banda ideal (puntos de VPD coloreados).
- Inconsistencias:
  - La banda de VPD sigue la etapa de cada fecha, pero las de temperatura y HR usan la etapa actual.
  - No distingue lecturas con luz prendida o apagada (el dato existe).
- No hay EC, pH, riegos, crecimiento ni marcas de eventos o etapas en el eje.

### Canopy
- Mapa cenital SVG de la carpa: plantas en círculos según su posición, colas arrastrables (1–10 por planta), red SCROG 6×6 que se toca celda por celda o con un slider, snapshots históricos y notas.
- Estadísticas: colas, W/cola, colas/m², % de red, estado del flip, diagnóstico ("Demasiadas colas" … "Sobra luz").
- **Usa un área fija de 0,64 m² y 314 W por defecto**, sin leer la carpa ni la lámpara del cultivo.
- Paleta vieja hardcodeada. El touch bloquea el scroll.

### Energía
- Tarifa y ciclo arriba.
- Estadísticas: kWh/mes, $/mes, acumulado, $/g (calculado con el yield *estimado*).
- Tablas: equipos, histórico mensual, lecturas del medidor contra lo estimado (alerta si la diferencia supera el 15 %), y formulario "+ nueva lectura".
- **"Vincular equipo" lleva al admin de Django**, al que un usuario normal no puede entrar. No hay pantalla para equipos ni tarifas.
- Los mensajes salen duplicados.

### Reporte
- Duración (veg y flora), yield total real vs. estimado, g/W, agua total, pH/EC promedio.
- Yield por planta, nutrientes consumidos, ambiente mín/prom/máx, eventos por tipo, setup.
- Export a CSV (EC en mS/cm, sin el detalle por planta).
- No tiene gráficos, PDF ni comparación entre cultivos. Está siempre visible como pestaña aunque es de cierre.

### Ajustes del cultivo (solo editor y dueño)
- Lista con el valor actual de cada ítem: Datos · Etapa · Fotoperíodo · Equipos y consumo (lleva a Energía) · Nutrientes (catálogo **global**) · Compartir (pantalla **global**, solo el dueño).
- **Ciclo del cultivo:** Finalizar (con `confirm()`, sin pedir fecha ni yield), Reabrir, Archivar (sin confirmar).
- No existe eliminar cultivo.
- Subpantallas:
  - **Datos:** formulario genérico. Los días estimados solo se cargan acá.
  - **Etapa:** etapa actual, formulario de cambio con 7 opciones e historial.
  - **Fotoperíodo:** presets 20/4, 18/6 y 12/12, formulario e historial. Marca como "activo" la primera fila aunque tenga fecha futura.
  - Todas tienen "volver" al Resumen, no a Ajustes.
- Existe en el backend un atajo **"flip a flora hoy"** que **ningún botón usa**.

### Nuevo cultivo
- Una sola página con tres paneles:
  - identidad: nombre, fecha, etapa inicial (entre las 5 primeras);
  - setup opcional: lámpara, watts, sustrato, carpa;
  - notas.
- Sidebar con una tabla de referencia para vege.
- **No pide días estimados** (el formulario los tiene pero no los muestra), ni plantas, fotoperíodo o equipos.
- Eyebrow en spanglish: "// new cultivo · log book · entry".

### Detalle de planta
- Header gigante en mayúsculas con la strain, pills de estado y etapa, [medir] [etapa] [editar].
- 5 tarjetas casi estáticas: días de flora estimados, THC, yield estimado, índica/sativa, última medición. **No muestra el yield real.**
- Notas de genética.
- **Galería:** grilla con lightbox simple, sin anterior/siguiente, swipe ni comparación. Las fotos se sirven **a tamaño completo y sin caché**: no hay miniaturas ni compresión.
- Tablas de riegos y eventos (con tope silencioso de 20) y de mediciones (7 columnas que **se recortan en mobile**).
- "+ nuevo riego" no preselecciona la planta.

### Planta: alta, edición y baja
- Alta y edición usan el formulario genérico, con todos los campos juntos (en el alta aparecen hasta yield real y archivada).
- Después de crear lleva al cultivo, no a la planta.
- Si la planta tiene historial, "eliminar" en realidad archiva. Las archivadas **no aparecen en ningún listado** (solo en el Reporte).
- No hay flujo de cosecha (fecha de corte, peso húmedo/seco, curado).
- Etapa propia de la planta: historial sin la línea de etapas del cultivo, así que la herencia no se entiende.

### Medición de planta
Formulario genérico con fecha, altura, nudos, canopy, aspecto, síntomas y foto (`FileInput` común, sin cámara, sin vista previa, límite duro de 5 MB). Es el único dato de campo que no pasa por Registrar.

### Editar y eliminar registros
- **Cuatro estilos distintos de formulario:**
  - Registrar;
  - el formulario genérico, con labels automáticos en inglés o sin tildes: "Timestamp", "Follow up fecha", "Descripcion", "PH";
  - el formulario propio de riego (con Alpine, pestañas visibles, nutrientes en un panel aparte, dosis no editable);
  - la confirmación de borrado.
- Validaciones que **solo existen en Registrar**: rangos, avisos, fecha futura, pH obligatorio de 0 a 14.
- Redirecciones inconsistentes (algunas vuelven al Resumen, otras se quedan en el formulario).
- Borrar: ícono ⋯ de 11px → formulario → link "eliminar" chico → página de confirmación. Son 4 taps, sin deshacer.

### Compartir (/invitados/)
- Global: el formulario `form.as_p` sin estilos tiene cultivo, usuario existente (hay que tipear el username exacto) y permiso.
- Si se deja vacío el usuario, se **crea una cuenta con usuario y contraseña aleatorios que se muestran una sola vez**, y el dueño se los pasa a la otra persona por fuera de la app.
- No hay links de invitación, aceptación, QR ni email.
- Lista de accesos con cambio de rol y revocar (`confirm()`).

### Nutrientes
Tres secciones: mis nutrientes / catálogo compartido / de cultivos compartidos conmigo. Cada uno con editar, ocultar y eliminar (eliminar solo si no se usó). **Todo en g/L**, aunque los fertilizantes líquidos se dosifican en ml/L. No se muestra cuántas veces se usó cada uno.

### Dudas
FAQ estática con buscador en 9 secciones: pH/EC, riego, ambiente/VPD, luz, nutrición, plagas, entrenamiento, cosecha/secado/curado, para empezar. No usa los datos del cultivo.

### Actividad (superusuario)
Usuarios activos en 7 días, ingresos fallidos, actividad por persona, últimos movimientos y log de ingresos (sin IP).

### Errores
- 400, 403 y 404: número gigante y botones, estilos inline. La 403 dice "contactá al administrador" en vez de hablar con el dueño del cultivo.
- 500: **paleta vieja marrón/lima** y fuentes del sistema.

### Notificaciones push
- Se activan con la campana (en mobile está escondida en la hamburguesa) y no hay explicación previa.
- Un cron manda "Pendientes · <cultivo>" (registrar ambiente de hoy, N seguimientos, N tareas) al dueño y a los editores.
- No hay preferencias ni centro de notificaciones.

---

## 6. Flujos clave y su fricción actual

1. **Riego con nutrientes (el registro más frecuente y el más caro):**
   - abrir Registrar → cambiar el select a Riego → tipear N volúmenes, uno por planta → abrir el desplegable de nutrientes → buscar en la lista completa y tipear dosis → (runoff: abrir cada planta, tildar, tipear) → Guardar → posible aviso → "Guardar igual".
   - Nada viene precargado del riego anterior.
   - Si se carga pH/EC de runoff sin tildar el checkbox, **se descarta en silencio**.
2. **Medir ambiente:**
   - Registrar → (Ambiente ya está por defecto) → temperatura y HR → Guardar.
   - Es rápido, pero no muestra el VPD resultante. Si la PWA quedó abierta, la hora que se guarda es la de cuando se abrió la página.
3. **Flip a flora (un solo evento real, repartido en 2 o 3 pantallas):**
   - Ajustes → Etapa → elegir "Flora temprana" entre 7 opciones → guardar;
   - aparte, Ajustes → Fotoperíodo → 12/12 → guardar.
   - Opcional: un snapshot de canopy para ver si la red está al 60 %.
   - El atajo "flip hoy" existe en el backend sin botón.
4. **Cierre del ciclo y cosecha:**
   - editar cada planta para cargar el yield real → Ajustes → Finalizar (sin pedir fecha ni yield) → Reporte.
   - No hay flujo guiado de cosecha, secado ni curado, aunque esas etapas existen.
5. **Seguimiento de una planta:**
   - Resumen → fila de la planta → [medir] → formulario genérico → (foto, si hay permiso) → vuelve.
   - No hay curva de crecimiento ni comparación de fotos.
6. **Primer uso:**
   - login → Hoy vacío → Nuevo cultivo (sin plantas ni fotoperíodo) → Resumen vacío → "+ agregar" planta, una por una, en un formulario genérico → Ajustes → Fotoperíodo.
   - No hay onboarding ni checklist de configuración.
7. **Corregir un error de carga:** buscar en la Bitácora → ⋯ de 11px → formulario con labels en inglés → guardar (vuelve a otra pantalla), o eliminar con 3 pantallas más.
8. **Compartir con alguien:**
   - Compartir (global) → elegir cultivo → dejar vacío el usuario → copiar a mano el usuario y la contraseña aleatorios → pasárselos por WhatsApp.
   - El invitado no puede cambiar ni su usuario ni su contraseña.
9. **Configurar energía:** imposible desde la web para un usuario normal.

---

## 7. Sistema visual actual ("VERDE")

**Estado general:**
- Conviven **dos lenguajes visuales**:
  - **"VERDE redondeado"** (lo nuevo: Hoy, Registrar, FAQ, Actividad, Ajustes, Nutrientes, selector, pestañas, barra inferior). Radio de 14px, píldoras, tono cálido y explicativo.
  - **"Terminal cuadrado"** (lo viejo: Resumen, Planta, Bitácora, Tareas, Canopy, Fotoperíodo, Etapa, Riego, Energía, Reporte, Borrar). Radio 0, mono en mayúsculas, prefijos `//`, sigilo `§`, "log raw", "authenticated session".
- Un solo CSS global (`verde.css`, 30 KB). El grueso del estilo vive en **19 bloques `<style>` dentro de los templates** y en unos 400 `style=""` inline.
- **Solo modo oscuro.**

**Paleta (tokens):**

| Token | Hex | Uso |
|---|---|---|
| bg | `#0e120c` | fondo, más dos degradados radiales verde/rust |
| bg-alt | `#161a12` | inputs |
| card | `#1c2218` | paneles |
| card-alt | `#232a1f` | cabeceras |
| rule | `#2a3023` | bordes |
| cream | `#ece2c8` | texto, 14,7:1 |
| cream-soft | `#94a586` | texto secundario |
| fine | `#7a886d` | texto tenue: **4,3:1 sobre card, 3,9:1 sobre card-alt, no pasa AA** |
| green | `#8aab68` | marca, activo, veg, ideal |
| green-deep | `#4a5f30` | |
| honey | `#d49a3e` | aviso, eventos, secado |
| rust | `#c46a3e` | **CTA primario**, y también error y urgente |
| plum | `#b384d8` | floración, EC/pH, luz |
| slate | `#6a8aa8` | mediciones, VPD bajo en gráficos |

- **Semántica de facto:**
  - veg = verde, flora = ciruela, secado/curado = miel;
  - tipos de registro: ambiente slate, riego verde, evento miel, EC plum;
  - VPD: ideal verde / alto rust / bajo miel (pero slate en los gráficos).
- **Restos de una paleta vieja marrón/lima** en el 500, canopy y los colores de planta. El **logo** (dígitos LCD "62" con raíces, verde lima `#b1d160`) no coincide con `--green` y además el PNG **no se usa en ningún lado**.

**Tipografía:**
- Bricolage Grotesque condensada (display), Manrope (texto), JetBrains Mono (datos y rótulos).
- Los tokens casi no se usan: los nombres de fuente están escritos a mano en todos lados.
- **No hay escala:** hay 35 tamaños distintos, de 9px a 88px. Hay mucho microtexto mono de 9–10px con tracking amplio, y H1 de 48 a 88px con pesos y tracking que cambian por página.

**Espaciado, radios y breakpoints:** sin tokens. Radios de 0 / 5 / 8 / 9 / 10 / 12 / 14 / 999. Hay unos 10 breakpoints distintos.

**Componentes:**
- Existen: pill, panel con "§", tabla `.tbl-log` (pasa a tarjetas en mobile), chips de tipo y de VPD, botones `btn-brand`/`btn-ghost`, alertas, selector de cultivo, pestañas, barra inferior.
- Duplicados:
  - 7 variantes de tarjeta de estadística;
  - más de 14 encabezados de página (`.tl-header` definido distinto en 4 templates);
  - 5 copias del link "volver";
  - 6 estados vacíos y 5 estilos de aviso;
  - 4 familias de tablas;
  - botones propios fuera del sistema.
- **No hay** toasts, modales propios, hoja inferior (bottom sheet) ni confirmaciones propias: se usan `confirm()` y `alert()` nativos.

**Bootstrap:** se carga completo para la navbar o hamburguesa, dropdowns, alertas, un modal, un collapse y algunas grillas. VERDE lo pisa con `!important` y con selectores globales (`label`, `input`) que obligan a poner parches.

**Accesibilidad táctil:** completar una tarea (18px), editar (ícono de 11px), ⋯ en tablas, steppers de 28px, filtros de 26–30px, logout de 11px. Todo queda por debajo de 44px.

**Marca y copy:**
- Voseo rioplatense consistente ("Registrá", "Tenés", "Anotá el primero →"). Casi sin emojis; se usan glifos → ✓ ● ⚠.
- Mezcla de inglés y español: "Timeline", "snapshot", "yield est.", "setup", "new cultivo".
- Mayúsculas inconsistentes: "guardar" en minúscula, "Guardar permiso", "RIEGO".
- Nombres distintos para lo mismo:
  - hoy / Inicio / Hoy;
  - Bitácora / Timeline / log raw;
  - Evento / Observación;
  - pH/EC / EC/pH;
  - compartir / invitados.
- El login expone "alansaja13/62xroots · v0.3".

---

## 8. Problemas consolidados (lo que el rediseño tiene que resolver)

### A. Arquitectura de información
1. **Triple navegación en mobile dentro de un cultivo:** barra inferior, pestañas y panel del Resumen repiten Resumen, Bitácora y Tareas. Mientras tanto, Tendencias, Canopy, Energía, Reporte y Ajustes quedan escondidas en "Más".
2. La barra inferior **cambia de contenido según el contexto**, y Registrar (la acción principal) saca al usuario del cultivo.
3. **Global y de cultivo están mezclados:** Compartir y Nutrientes se presentan como ajustes del cultivo pero son pantallas globales. Nutrientes no tiene entrada propia, y un lector no puede llegar.
4. **Muchas entradas para lo mismo:**
   - etapa: pill, botón y Ajustes;
   - fotoperíodo: tira de setup y Ajustes;
   - energía: pestaña y Ajustes;
   - compartir: barra superior, barra inferior y Ajustes;
   - registrar: botón del header, 3 "+", "+ nueva", CTA inferior.
5. **La planta no tiene sección propia**, aunque es una entidad central: queda enterrada en el Resumen, numerada por posición, y las archivadas son inaccesibles.
6. **No hay vista "Mis cultivos"** (el historial está al final de Hoy, sin filtros).
7. Las subpantallas de Ajustes no vuelven a Ajustes. Editar o borrar desde la Bitácora o la Planta vuelve al Resumen y se pierde el contexto.
8. Hay pantallas que pertenecen a una fase del ciclo (Reporte, Canopy) y están siempre visibles. No hay una noción de "momento del ciclo".

### B. Carga de datos
9. **El riego es caro:** N inputs, sin precarga, sin "igual para todas", nutrientes en una lista completa sin "los de siempre", runoff escondido detrás de un checkbox que descarta datos en silencio, y dos conceptos de runoff que se pisan.
10. El tipo de registro se elige con un `<select>` nativo y el cultivo comparte fila con él: es fácil cargar en el cultivo equivocado sin darse cuenta.
11. "Cuándo ocurrió" siempre visible y con la hora vieja.
12. Valores por defecto malos: el evento arranca en "Otro" y la tarea en la categoría "Observación".
13. **No hay cálculo en vivo** (VPD, total de ml, equivalencia de EC). La escala ×10 de la EC solo se explica con un placeholder.
14. Errores que no marcan el campo. Avisos que se confirman todos juntos. Mensaje de éxito sin link al registro ni deshacer.
15. **No todo pasa por Registrar:** mediciones y fotos de planta, alta de plantas, etapa, fotoperíodo, lecturas de medidor y canopy van por otro lado.
16. **Editar no es lo mismo que crear:** otro estilo, labels en inglés, validaciones distintas, la dosis no se edita, redirects distintos.
17. Borrar requiere 4 taps y 3 pantallas, y no hay deshacer.

### C. Jerarquía y lectura del estado
18. **El Resumen tiene la jerarquía invertida:** nombre gigante, cajas de día, 4 vitales, neón animado, setup y progreso arriba, y lo accionable (tareas vencidas, seguimientos) abajo o en la columna lateral.
19. **La frescura del dato está casi oculta** (10px). Un semáforo "ideal" de hace 3 días se ve igual que uno de hoy. En Hoy la frescura sí es protagonista: los criterios no coinciden.
20. Hoy no muestra días sin riego, etapa ni día de flora.
21. El Resumen no tiene ninguna visualización temporal.
22. Hay cosas que compiten por la atención sin aportar: el neón animado (sin `prefers-reduced-motion`) y el reloj con segundos.

### D. Consistencia de datos y lógica visibles
23. Etapa fina vs. estado grueso según la pantalla. El día de flora sale de fuentes distintas. La barra de progreso pinta "flora" según los días estimados y no según la etapa real.
24. Las bandas de Tendencias usan etapas distintas en el mismo gráfico. "Bajo" tiene un color distinto en los gráficos y en los chips.
25. Fotoperíodo "activo" con fecha futura. Canopy con área y watts hardcodeados. $/g con el yield estimado en un lado y g/W con el real en otro.
26. La EC aparece en tres escalas (×10 / µS / mS), y el CSV la exporta en mS.

### E. Funciones incompletas o huérfanas
27. Energía no se puede configurar sin el admin.
28. No existe eliminar cultivo. Finalizar no pide fecha ni yield.
29. El "flip hoy" está sin botón. Los días estimados no se piden al crear el cultivo.
30. Fotos: apagadas por defecto, sin compresión, miniaturas, cámara ni vista previa, y con un límite de 5 MB que una foto de celular supera.
31. Compartir con cuentas aleatorias y contraseña mostrada una vez. No hay perfil, cambio ni recuperación de contraseña.
32. Notificaciones sin explicación ni preferencias. Los lectores no reciben nada.
33. Bitácora incompleta y con tope de 200. Tendencias solo de ambiente. Reporte sin gráficos.

### F. Sistema visual
34. Dos estéticas peleadas (redondeado cálido vs. terminal cuadrado) y una tercera vieja (marrón/lima).
35. No hay escala tipográfica, de espaciado, de radios ni de breakpoints. Los tokens de fuente se ignoran.
36. Contraste insuficiente de `--fine` en texto de 9–10px. Opacidades que bajan aún más el contraste.
37. **El CTA primario es rust,** el mismo color de error y urgente. Registrar es naranja en la página y verde en la barra inferior.
38. Objetivos táctiles chicos en todas las acciones secundarias.
39. Tablas anchas que se rompen en mobile, con 4 estrategias distintas para resolverlo.
40. El nombre de la marca aparece con 4 grafías, el tono de voz es doble y se mezclan idiomas y mayúsculas.

---

## 9. Oportunidades: datos que ya existen y no se aprovechan

- **Curvas de crecimiento por planta** (altura, canopy, nudos), velocidad en cm/día, el estirón post-flip y la comparación entre plantas, con eventos (topping, LST) marcados.
- **Línea de tiempo visual de fotos**, antes/después, foto de portada por planta y fotos dentro de la Bitácora.
- **Salud por planta en el tiempo** (aspecto y síntomas) e indicador en la lista (último aspecto, días sin medir).
- **Runoff vs. entrada** de pH/EC por planta a lo largo del tiempo, para detectar acumulación de sales.
- **Rangos de pH, EC, horas de luz y distancia de la luz**, que hoy están cargados y no se usan:
  - colorear pH/EC;
  - recomendar la distancia de la luz por etapa;
  - comparar el fotoperíodo configurado con el recomendado.
- **"% del tiempo en rango"** por variable y etapa. **Día y noche** separados (`luz_estado`), por ejemplo HR nocturna alta.
- **Franja de etapas, fotoperíodo y eventos** sobre el eje de todos los gráficos y en la Bitácora. **Línea del ciclo tipo Gantt**, estimado vs. real.
- **Cuenta regresiva a la cosecha** por planta (tipo, días de flora estimados).
- **Yield estimado vs. real**, g/planta, g/W y costo real por gramo cruzando con energía. **Comparación histórica entre cultivos.**
- **Dosis aplicada vs. recomendada** por nutriente, plan de alimentación semanal y "los de siempre".
- **Autoría** (`creado_por`): filtrar la Bitácora por persona y mostrar "quién registró qué" al dueño.
- Seguimientos pendientes dentro de cada planta. Chips de planta clickeables.
- Evolución del llenado SCROG. Consumo eléctrico real vs. estimado por mes.

---

## 10. Lo que funciona y conviene conservar (o rescatar)

- **Registrar como lugar único de carga**, con valores raros que se pueden confirmar (no bloquean) y aceptación de coma decimal.
- Inputs numéricos de texto con `inputmode` (sin flechitas).
- **Hoy** como bandeja de pendientes entre cultivos, con la frescura del dato visible.
- Selector de cultivo agrupado (mis activos / compartidos / historial).
- **Semántica de color por etapa y tipo de registro**: veg verde, flora ciruela, secado miel. Es reconocible.
- Voseo cálido y explicativo de las pantallas nuevas ("Lo que tenés pendiente y lo último que registraste.").
- Tema oscuro (tiene sentido en la carpa y de noche) con la paleta tierra/verde.
- Tablas que pasan a tarjetas en mobile. Botones de 44px donde se aplicó.
- Completar tareas y resolver seguimientos sin recargar.
- Valores que no se pierden: borrado protegido (lo usado se oculta, las plantas con historial se archivan).

---

## 11. Restricciones del rediseño

- Tiene que poder implementarse con **Django templates renderizados en el servidor + CSS propio**, con sumas progresivas de HTMX y Alpine. No hay SPA ni build step de frontend.
- **Mobile-first y PWA:** área segura, uso con una mano, objetivos de 44px como mínimo, legible con poca luz o con luz de cultivo.
- Español rioplatense con voseo. Unidades: °C, %, kPa, pH, EC (definir la escala visible: ×10 del medidor vs. µS/cm), ml, g/L (y ml/L para líquidos), kWh, $.
- Las reglas de dominio no cambian:
  - la etapa sale del historial de cambios;
  - el día 0 es el inicio y el flip;
  - VPD con rango según la etapa vigente a la fecha;
  - tres roles;
  - lo usado no se borra, se oculta o se archiva.
- La API v1 y el asistente de IA siguen leyendo los mismos datos.

## 12. Decisiones que Claude Design tiene que tomar

1. **Modelo de navegación:** ¿cultivo-céntrico (todo dentro de un cultivo, con cambio rápido entre cultivos) o una bandeja global ("Hoy") como centro? ¿Qué va en la barra inferior, de forma fija, y qué se elimina (pestañas o barra)?
2. **¿La planta es una sección de primer nivel?** (lista, ficha, galería, crecimiento.)
3. **Registrar:**
   - ¿formulario, hoja inferior (bottom sheet) contextual o acciones rápidas por tipo (por ejemplo "Regar" con "repetir el último")?
   - ¿Se pueden combinar tipos en una sola sesión de carga ("ronda diaria": ambiente + riego + observación)?
   - ¿Entran las mediciones y fotos de planta?
4. **¿El ciclo como columna vertebral?** Una UI que cambia según la fase (veg / flip / flora / cosecha / secado / curado) y que muestra Canopy, el flip o la cosecha cuando corresponde.
5. **Jerarquía del Resumen:** ¿qué es lo primero que se ve? Propuesta a evaluar: pendientes, luego estado con frescura y luego tendencia, con identidad y setup en segundo plano.
6. **Flujos que hoy no existen:** "flip a flora" en un paso, cosecha y cierre guiado, onboarding del primer cultivo, invitar con link, perfil y contraseña, configuración de energía, preferencias de notificaciones.
7. **Visualización:** qué gráficos van y dónde (sparklines en el resumen, crecimiento por planta, pH/EC, línea del ciclo).
8. **Identidad:**
   - ¿se mantiene la estética "terminal" (`//`, `§`, mono en mayúsculas) o se pasa al tono cálido de lo nuevo?
   - nombre único de la marca (62×ROOTS);
   - un logo que coincida con la paleta;
   - un solo color de CTA, distinto del de error;
   - ¿hace falta modo claro?
9. **Sistema:** tokens completos (color con variantes tintadas, escala tipográfica, espaciado, radios, sombras, breakpoints, movimiento) e inventario mínimo de componentes:
   - stat/vital con frescura;
   - fila de registro;
   - chip;
   - pill de etapa;
   - formulario con error por campo;
   - hoja inferior;
   - toast con deshacer;
   - confirmación propia;
   - estado vacío;
   - estado de solo lectura.
10. **Escala de EC visible** y unidades de dosis (g/L vs. ml/L).

---

### Apéndice: bugs detectados durante el relevamiento (no son de diseño, pero conviene saberlos)

- Mensaje de éxito con la concordancia rota ("Tarea guardado", "Observación guardado").
- Marcar una tarea "Completada" desde el formulario de edición no guarda la fecha de completado.
- Completar una tarea desde la lista de Tareas apunta a un contenedor que no existe en esa página.
- La Bitácora muestra el código crudo del tipo de evento y "VPD · None".
- Mensajes duplicados en Energía.
- La edición de pH/EC no valida pH 0–14 ni exige alguno de los dos. La dosis editada acepta 0 o valores negativos.
- Fotoperíodo marca como "activo" un cambio con fecha futura.
- Reporte con atributos `style` duplicados (las negritas se pierden).
- Canopy usa 0,64 m² y 314 W hardcodeados.
- Plantas archivadas inaccesibles a pesar del mensaje "podés restaurarla editándola".
