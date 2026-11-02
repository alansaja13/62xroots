# Rediseño "Suelo y aire": plan por fases

> Diseño de referencia: `62xroots Sistema.html` (handoff de Claude Design: `y-sys.jsx`, `y-screens1/2.jsx`, `y-desk.jsx`).
> Contexto y problemas de partida: [BRIEF-claude-design.md](BRIEF-claude-design.md).
> Fecha: 2026-11-02.

## Principios

- **La app nunca se rompe para los usuarios reales.** Cada fase se puede deployar sola en Railway, sin rama de larga duración. Las URLs actuales siguen andando (o redirigen).
- **Primero el esqueleto, después las pantallas.** La fase 0 cambia el marco de todas las páginas a la vez. Desde ahí, cada pantalla se migra por separado.
- **Django + CSS propio, sin build.** Se agrega HTMX o Alpine donde haga falta interacción (la hoja de Registrar, deshacer, comparar fotos). No se convierte la app en una SPA.
- **El backend nuevo entra en la misma fase que la pantalla que lo usa**, con su migración y sus tests. Así no quedan modelos sin interfaz ni interfaz sin datos.
- Al cerrar cada fase se actualiza el `CLAUDE.md` (sistema de diseño, navegación, flujos) y corren `python manage.py test growlog --settings=config.test_settings` y una revisión en celular.

---

## Fase 0 · Fundaciones visuales (sin cambiar flujos)

**Objetivo:** que toda la app ya tenga la piel nueva y la navegación nueva, con las mismas pantallas por dentro.

**Sistema**
- `static/growlog/suelo.css` reemplaza a `verde.css`. Contiene:
  - los tokens de `y-sys.jsx` (`--bg --s1 --s2 --ink --mu --ln --ac --on --bad --warn --veg --flo`, las capas `--w --m --e --n` y las zonas `--z0…--z4`);
  - el tema oscuro y el claro, vía `[data-theme]` + `prefers-color-scheme`;
  - escalas de tipografía, espaciado, radios y breakpoints (no más de 4).
- **Tipografía:** Familjen Grotesk (display y texto) + DM Mono (datos y rótulos). Se cargan solo en `partials/fonts.html`. Mínimo **12 px** para cualquier texto (el mock usa 9,5–11 en algunos rótulos: se ajusta acá).
- **Componentes base** como clases y partials:
  - `card`, `pill` (etapa), `chip`, `btn` / `btn.g` / `btn.d`, `seg` (selector segmentado), `row`, `ck` (checkbox de 26px);
  - `tog`, `st` (stepper), `toast`, `sheet` + `dim`, `vital` (dato con frescura), estado vacío, estado de solo lectura, error por campo.
- **Capa de compatibilidad:** las clases viejas (`panel`, `tbl-log`, `btn-brand`, `pill--*`, `tc--*`, `vpd--*`) se remapean a los tokens nuevos, para que las pantallas todavía no migradas se vean coherentes.

**Marco**
- `base.html`:
  - **Celular:** barra inferior fija `Hoy · Cultivo · [+] · Plantas · Más` (reemplaza `bottom_nav`, `cultivo_tabs` y la hamburguesa).
  - **Compu:** barra lateral `Hoy · Cultivo · Plantas · Tareas · Fotos · Más` + botón "+ Registrar".
  - "Cultivo" y "Plantas" usan el último cultivo abierto (`CultivoRecienteMiddleware` ya lo guarda).
  - Se va el reloj con segundos. El usuario, el cierre de sesión y los avisos pasan a "Más".
- **Selector de cultivo** ("Cultivo ▾") en el encabezado de las pantallas de cultivo.
- **Por ahora el [+] abre la pantalla actual de Registrar.** La hoja llega en la fase 1.
- **Más** (pantalla nueva y simple): lleva a Ajustes del cultivo, Tareas, Bitácora, Tendencias, Canopy, Energía, Reporte, Nutrientes, Compartir, Dudas y Salir. Reemplaza el menú "Más" de las pestañas.
- **Login, 400/403/404/500, manifest y `theme-color`** pasan a la paleta nueva. El 500 deja de tener su propia paleta. Se saca "alansaja13/62xroots · v0.3" del login.

**Limpieza:** se borran `logo.png` sin uso, CSS muerto y estilos `<style>` de las pantallas migradas. Bootstrap queda por ahora (lo usan los formularios).

**Listo cuando:**
- Todas las URLs renderizan con el marco nuevo, en tema claro y oscuro, a 375 px y a 1280 px.
- Ningún objetivo táctil del marco queda por debajo de 44 px.
- Los tests pasan.

**Decisión antes de arrancar:** el logo. El "62" LCD lima no combina con la paleta tierra. Opciones: usar solo el wordmark "62×ROOTS" (como el mock) o pedirle a Claude Design un logo nuevo.

---

## Fase 1 · El uso diario

### 1a · Hoy
- **Para revisar** suma, a lo que ya trae `services/hoy.py`, las alertas de VPD fuera de rango.
  - Cada fila tiene un check de 26 px que completa la tarea ahí mismo (HTMX) y muestra un aviso con **Deshacer**.
- **Cultivos:** nombre, pill de etapa con el día, temperatura, HR y VPD, días sin riego y frescura ("◌ dato viejo · hace 11 h").
  - La barra "Núcleo" horizontal entra en 1c.
- **Compu:** dos columnas. El mapa de VPD entra en la fase 2.

### 1b · Cultivo (Resumen)
- **Encabezado:** "Cultivo ▾", estado de la luz y fotoperíodo, nombre, pills (etapa, sin riego, plantas).
- **Selector segmentado** `Núcleo · Aire · Plantas · Ciclo`. En esta fase Aire y Ciclo apuntan a las pantallas actuales (Tendencias y Etapa).
- **Vitales con frescura.** Si el dato es viejo se ve rayado y aparece la franja "Última medición hace X → medir", que abre la hoja en Ambiente.
- **Actividad reciente** como lista legible (tipo, dato, hora), con tareas y seguimientos arriba.
- **Compu:** panel de detalle a la derecha con el registro seleccionado y los botones Editar y Repetir hoy.

### 1c · Núcleo (bitácora)
- **Definición propuesta:** una capa por registro, con el color del tipo (riego, ambiente, evento, nota), alto fijo por tipo y la fila legible al lado. Es un acento visual: lo que se lee es la lista.
- Reemplaza la tabla de `timeline.html`:
  - filtros por tipo como chips;
  - **paginación**, en vez del tope de 200;
  - suma cambios de etapa y de fotoperíodo, y mediciones de planta.

### 1d · Registrar como hoja
- **Hoja inferior** sobre la pantalla actual (HTMX trae el formulario; se cierra con deslizar o ✕).
  - Cultivo fijado arriba ("🔒 Lemon Haze #3 ▾"). Chips de tipo: Riego, Ambiente, Evento, Nota, pH/EC, Tarea.
  - "◷ Ahora" como default; tocarlo abre fecha y hora. La hora se calcula al guardar, no al abrir.
- **Riego:**
  - atajo **"Repetir riego del dd/mm"**, que precarga volumen, pH, EC y nutrientes del último riego;
  - "afinar por planta →" abre la pantalla Riego: interruptor **mismo volumen para todas**, stepper con el valor por planta y total en vivo;
  - pH y EC con rango ideal según la etapa;
  - EC con conversión visible (mS · µS · medidor);
  - nutrientes **"los de siempre"** (los usados en los últimos riegos) y "+" para el resto;
  - interruptor **Hubo runoff**, que despliega pH y EC por planta. Se elimina el doble concepto de runoff.
- **Ambiente:** muestra el VPD calculado en vivo.
- **Errores y avisos** marcan el campo. "Valor raro" ofrece **Corregir / Guardar igual** por aviso.
- **Al guardar:** aviso "Riego guardado · Ver · Deshacer". Deshacer borra lo recién creado si se toca dentro de los 10 s.
- **Nota** es un tipo nuevo: un Evento de tipo "nota", sin campos extra. Va en la misma migración que agrega el tipo.
- `/registrar/` sigue existiendo como página completa (atajo de la PWA, enlaces viejos) y usa el mismo formulario.

### 1e · Plantas y ficha de planta
- **Plantas** (pestaña nueva):
  - selector Activas / Cosechadas / Descartadas / Archivadas;
  - tarjetas con foto de portada (la última), altura, sparkline de crecimiento y frescura de la medición.
- **Ficha:** altura actual grande con cm/día, curva de altura con eventos marcados (topping, LST), canopy, nudos, aspecto, tira de fotos y botón **Medir a {planta}**.
  - Medir pasa a ser un tipo en la hoja de Registrar ("Planta"), con la planta preseleccionada.
- **Backend:** miniaturas de fotos con Pillow (ya está instalado) al subirlas. Se sirven con caché privada en vez de `no-store` en las miniaturas. Se suben `accept="image/*"` y `capture`, y el límite de 5 MB pasa a 12 MB, comprimiendo en el servidor.

### 1f · Edición y borrado
- **Editar un registro** usa el mismo formulario que la hoja, en modo edición. Se van `crud_form` para los registros y `riego_form.html`; la dosis se puede editar.
- **Borrar** se hace desde la ficha del registro, con confirmación propia y deshacer de 10 s (borrado diferido). Se va `crud_delete` para los registros.

**Listo cuando:**
- Un riego repetido sale en **3 toques** (+ → Repetir → Guardar).
- Ningún flujo diario usa `<select>` nativo para elegir el tipo ni sale del contexto del cultivo.
- Hay tests de: repetir riego, mismo volumen, runoff, deshacer y nota.

---

## Fase 2 · Entender el cultivo

- **Aire** (reemplaza Tendencias):
  - selector Hoy · 7 d · 30 d · Ciclo;
  - **mapa temperatura × HR** con la cola de las últimas lecturas;
  - curva de VPD con la banda ideal **según la etapa de cada fecha**, aplicada también a temperatura y HR (hoy está mal);
  - franja de etapas bajo el eje;
  - tarjetas **En rango / Día / Noche** (usa `luz_estado`, que ya se guarda).
  - Corrección conceptual del mock: las zonas del mapa salen de `ParametroIdeal` para la etapa de cada cultivo, no de cortes fijos. En el Hoy de compu se dibuja una zona ideal por cultivo, o el mapa se muestra por cultivo.
- **pH/EC en Aire**, como una segunda sección: solución vs runoff a lo largo del tiempo, con los rangos ideales de pH/EC que hoy no se usan.
- **Ciclo** (reemplaza Etapa y Fotoperíodo como pantallas sueltas):
  - línea **estimado vs real** por etapa, con marca "hoy";
  - tarjeta **Pasar a floración** que cambia etapa y fotoperíodo en un paso (usa el `cultivo_marcar_flora` que ya existe, ampliado) y muestra el % de la red SCROG del último snapshot;
  - el historial de etapas y de fotoperíodo queda abajo, editable.
- **Fotos:** línea de tiempo y **comparar** dos fechas con un divisor deslizable (Alpine), con la diferencia de altura y nudos entre ambas.
- **Tareas:** lista agrupada (Vencidas / Hoy y próximas / Hechas), con la opción **Todos los cultivos**, filtros de categoría en chips y deshacer. Se va la tabla de 7 columnas.
- **Más / preferencias:**
  - **Modelo nuevo `Perfil`** (uno a uno con User): unidad de EC visible (mS/cm, µS/cm, medidor ×10), tema (auto/claro/oscuro), hora de avisos y qué avisos recibir. Se aplica en toda la app.
  - `send_recordatorios` respeta la hora y las preferencias de cada usuario.
  - Cambio de contraseña y de nombre visible.
- **Nutrientes con unidad:** el campo `unidad` (g/L o ml/L) en `Nutriente`, y `NutrienteAplicado.dosis` neutra. Lleva migración con renombre de `dosis_g_por_litro` y ajustes en el reporte, la API y la skill de growlog.
- **Sale Bootstrap:** al terminar esta fase, ninguna pantalla depende de él. Se reemplazan dropdown, modal, collapse y grilla.

**Listo cuando:**
- Tendencias, Etapa y Fotoperíodo redirigen a Aire y Ciclo.
- El flip se hace en un toque.
- La EC se ve en la unidad que eligió cada usuario.
- No queda Bootstrap.

---

## Fase 3 · Ciclo de vida completo

- **Onboarding:** al crear un cultivo aparece un checklist (nombre y fecha · plantas · fotoperíodo · equipos de luz · primera medición), con progreso y "Hacer" en cada paso.
  - Alta de **varias plantas a la vez** (cantidad + strain, con apodos editables).
  - Los días estimados se piden acá.
- **Cosecha guiada:** Cortar → Pesar (húmedo por planta) → Secar (fecha y peso seco) → Cerrar (yield real, finalizar el cultivo, reporte).
  - **Modelo:** en `Planta`, `fecha_corte`, `peso_humedo_g` y `peso_seco_g` (el `yield_real_g` actual pasa a ser el seco).
  - "Cerrar" reemplaza el Finalizar suelto y ofrece pasar las etapas a Secado y Curado.
- **Reporte de cierre** con el diseño nuevo:
  - gráficos de ambiente en rango, crecimiento y yield estimado vs real;
  - g/W y **costo real por gramo** (cruzando con energía);
  - comparación con cultivos anteriores.
- **Compartir con link:**
  - **Modelo nuevo `Invitacion`** (token, cultivo, rol, vencimiento, usada por).
  - El invitado abre el link, crea su cuenta con su usuario y contraseña, y queda como miembro.
  - Se va la creación de cuentas aleatorias con contraseña mostrada una vez.
  - Recuperar contraseña por email, si hay email configurado; si no, solo por link de invitación.
- **Energía desde la web:** alta y edición de equipos y tarifas, y lecturas del medidor editables. Deja de depender del admin.
- **Canopy** con la piel nueva: objetivos táctiles grandes, sin bloquear el scroll, área y watts reales (ya corregidos).
- **Texto libre en Registrar** (opcional, el último ítem):
  - parser **determinista en el navegador**, con una gramática acotada: volumen, nombres de nutriente del catálogo con fuzzy match, pH, EC y nombres de planta;
  - muestra "Entendí" con chips editables antes de guardar;
  - sin IA externa, para que no salgan datos ni haya costo por uso.
  - Si no entiende algo, lo deja en las notas.
- **Compu:** ⌘K abre la hoja de Registrar.

**Listo cuando:**
- Se puede ir de un cultivo nuevo a un cultivo cerrado con reporte **sin pasar por el admin ni por formularios genéricos**.
- Desaparecen `crud_form` y `crud_delete` de los flujos de usuario. Quedan solo para casos raros de admin, si hace falta.

---

## Lo que hay que pedirle a Claude Design (en paralelo a la fase 0)

El mock no cubre estas pantallas. Conviene tenerlas antes de la fase en que se necesitan:

| Pantalla | Fase |
|---|---|
| Formulario de edición de un registro y ficha del registro en celular | 1 |
| Tipos Ambiente, Evento, pH/EC, Tarea y Planta dentro de la hoja | 1 |
| Experiencia del lector (Hoy y Cultivo sin acciones) | 1 |
| Login y errores | 0 |
| Logo / wordmark para la paleta tierra | 0 |
| Pantallas de compu además de Hoy y Cultivo (Plantas, Aire, Ciclo, Registrar) | 1–2 |
| pH/EC en Aire | 2 |
| Catálogo de nutrientes, Compartir/invitación, Energía (equipos, tarifas, lecturas), Canopy | 2–3 |
| Reporte de cierre y pasos 1, 3 y 4 de la cosecha | 3 |

## Decisiones para confirmar

1. **Logo:** usar solo el wordmark "62×ROOTS" o pedir uno nuevo. Se necesita en la fase 0.
2. **Tareas** queda en "Más" en celular (las pendientes ya están en Hoy). ¿O reemplaza a "Plantas" en la barra?
3. **Núcleo:** ¿una capa por registro (propuesta) o una por día?
4. **Unidad de EC por defecto** para los usuarios nuevos: el diseño sugiere mS/cm. Hoy se tipea ×10 del medidor.
5. **Texto libre:** ¿entra en la fase 3 o queda afuera?

## Riesgos

- **Migraciones con datos reales** (unidad de nutrientes, cosecha, `Perfil`): siempre aditivas, con valores por defecto y backup previo (skill `backup`). Nada destructivo en el mismo deploy.
- **API y skill de growlog:** los cambios de nombres (dosis, yield) mantienen los campos viejos en la API v1 un tiempo. Se avisa en la skill.
- **Deshacer con borrado diferido:** se implementa como borrado después de 10 s o soft delete con limpieza. Conviene decidirlo en la fase 1 y aplicarlo igual en todos lados.
- **Tamaño de cada fase:** la fase 1 es la más grande. Se puede deployar por sub-bloques (1a+1b → 1c → 1d → 1e → 1f).
