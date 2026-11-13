# Diseño y front-end

Describe el sistema visual y la capa de front-end de 62×ROOTS: estructura de templates, hoja de estilos `suelo.css` con sus tokens y componentes, CSS por página, JavaScript, fuentes, tema, HTMX y Alpine, íconos y convenciones de tamaños y de texto. Para la arquitectura general ver [arquitectura.md](arquitectura.md); para el formulario Registrar ver [registrar.md](registrar.md).

## 1. Templates

Todos los templates están en `templates/`. Las pantallas de la app están en `templates/growlog/`, los parciales en `templates/growlog/partials/` y los de error en la raíz de `templates/`.

### 1.1 `templates/base.html`

Layout de todas las páginas, salvo `login.html`, `invitacion.html` y `500.html`, que son documentos independientes. El `<html>` lleva `lang="es"`. El `<title>` es `{% block title %}Hoy{% endblock %} · 62×ROOTS`.

Orden del `<head>`: `partials/tema.html`, `partials/pwa_head.html`, `partials/fonts.html`, `growlog/suelo.css`, `growlog/registrar.css` (solo con usuario autenticado) y el bloque `extra_head`.

Cuerpo: `<body class="app">`.

| Elemento | Condición | Contenido |
|---|---|---|
| `partials/lateral.html` | usuario autenticado | Barra lateral de la compu |
| `<main class="app-main">` | siempre | Cabecera del cultivo, mensajes y contenido |
| `<div id="hoja">` | usuario autenticado | Destino donde HTMX inserta la hoja de Registrar |
| `<nav class="barra">` | usuario autenticado | Barra inferior del celular |

Bloques que define `base.html`:

| Bloque | Dónde | Uso |
|---|---|---|
| `title` | `<title>` | Nombre de la página (valor por defecto `Hoy`) |
| `extra_head` | final del `<head>` | CSS de la página (`<link>` o `<style>`) |
| `cultivo_tabs` | dentro de `<main>`, solo si `cultivo_nav` está definido | Por defecto incluye `partials/cultivo_tabs.html` |
| `content` | dentro de `<main>`, después de los mensajes | Contenido de la página |
| `bottom_nav` | dentro de `<nav class="barra">` | Por defecto incluye `partials/bottom_nav.html` |
| `extra_js` | al final del `<body>`, después de los scripts de `base.html` | JS de la página |

Mensajes de Django (`messages`), dentro de `<div class="mensajes">`:

- Mensaje con la etiqueta `registro`: `.toast` con el texto, el enlace `Ver` (a `request.session.ultimo_registro.bitacora`) y un formulario POST `Deshacer` a `growlog:registrar_deshacer`. Ambos solo aparecen si existe `ultimo_registro` en la sesión.
- Mensaje con la etiqueta `borrado`: `.toast` con el texto y, si existe `request.session.ultimo_borrado`, un formulario POST `Deshacer` a `growlog:registro_restaurar`.
- Cualquier otra etiqueta: `.alert.alert-<etiqueta>` con el texto y un botón `.alert__cerrar` (`data-cerrar-aviso`) que elimina el aviso.

Scripts de `base.html` (en este orden):

1. HTMX 1.9.12 desde `cdn.jsdelivr.net`. Un listener de `htmx:configRequest` agrega el header `X-CSRFToken` a cada pedido HTMX y reemplaza la coma por punto en los controles `input[type="number"]` y `input[data-decimal]` del formulario que origina el pedido.
2. Solo con usuario autenticado: `static/growlog/registrar.js` y un script inline con el comportamiento de la hoja (ver 4.4).
3. Un script inline que convierte los `input[type="number"]` en `type="text"` con `inputmode="decimal"` y valida decimales (ver 4.5).
4. El bloque `extra_js`.

### 1.2 Páginas independientes y de error

| Template | Extiende | Contenido |
|---|---|---|
| `growlog/login.html` | ninguno | Documento propio con `tema.html`, `pwa_head.html`, `fonts.html`, `suelo.css` y `<style>` inline (`.login`, `.login__marca`, `.login__campos`, `.login__recordar`) |
| `growlog/invitacion.html` | ninguno | Igual que login, con `<meta name="robots" content="noindex">` y `<style>` inline (`.inv`, `.inv__marca`, `.inv__campos`, `.inv__otra`) |
| `error_base.html` | `base.html` | Base de los errores dentro de la app. Bloques: `codigo`, `titulo`, `texto`. Muestra `.vacio` con rótulo `Error <codigo>`, un `.h1`, el texto, el botón `Ir a Hoy` (`.btn.sm`, enlaza a `/`) y el botón `Volver` (`.btn.g.sm`, `history.back()`) |
| `400.html` | `error_base.html` | Título "No se entendió el pedido" |
| `403.html` | `error_base.html` | Título "Esto no lo podés ver o cambiar" |
| `404.html` | `error_base.html` | Título "Acá no hay nada" |
| `500.html` | ninguno | Documento propio con `tema.html`, `fonts.html` y `suelo.css`, sin `base.html` ni contexto de navegación. Título "Algo se rompió de nuestro lado" |

`500.html` no incluye `pwa_head.html`.

### 1.3 Parciales

| Parcial | Para qué sirve |
|---|---|
| `partials/tema.html` | Resuelve el tema antes de pintar (ver sección 6) y declara los `theme-color` |
| `partials/fonts.html` | Único lugar donde se cargan fuentes (ver sección 5) |
| `partials/pwa_head.html` | `manifest.json`, íconos, metas de app instalable y registro del service worker `/sw.js` con scope `/`. Se incluye en `base.html`, `login.html` e `invitacion.html` |
| `partials/lateral.html` | Barra lateral de la compu (`.lateral`): marca, Hoy, Cultivo, Plantas, Tareas (solo si hay cultivo destino), Más, botón `+ Registrar` y nombre de usuario (con `· solo lectura` si el usuario no puede editar el cultivo abierto) |
| `partials/bottom_nav.html` | Barra del celular: Hoy, Cultivo, `+` (`.barra__mas`), Plantas, Más |
| `partials/cultivo_tabs.html` | Encabezado de un cultivo: selector más chips de secciones (`pestanas_cultivo`) |
| `partials/cultivo_selector.html` | Menú `<details class="nav-cultivo">` con los grupos "Mis cultivos activos", "Compartidos conmigo" e "Historial", más "Ver todos" y "+ Nuevo cultivo" |
| `partials/registrar_hoja.html` | Registrar como hoja modal (`.hoja-fondo` y `.hoja`) que se carga en `#hoja` |
| `partials/registrar_form.html` | Formulario de Registrar, compartido por la página `registrar.html`, la hoja y `registro_editar.html`. Lleva `form[data-reg]` y un `json_script` con id `reg-datos` |
| `partials/hoy_cultivo.html` | Bloque de cada cultivo en Hoy, con el Núcleo (SVG) |
| `partials/hoy_item.html` | Fila de una tarea pendiente en Hoy (`hx-post` a `tarea_completar`, con `origen=hoy`) |
| `partials/hoy_tarea_hecha.html` | Fila de una tarea hecha en Hoy, con `Deshacer` o `Reabrir` (`hx-post` a `tarea_descompletar`) |
| `partials/tarea_row.html` | Fila de una tarea en la página del cultivo (`hx-post` a `tarea_completar`, `hx-swap="delete"`) |
| `partials/tarea_completar_oob.html` | Fragmento `hx-swap-oob="afterbegin:#tareas-done"` que agrega la tarea a "Hechas" |
| `partials/tarea_descompletar_oob.html` | Fragmento `hx-swap-oob="afterbegin:#tareas-lista"` que devuelve la tarea a pendientes |
| `partials/bitacora_filas.html` | Filas de la bitácora y enlace `Ver más` (`hx-get`, `hx-swap="outerHTML"`) que trae la página siguiente |
| `partials/nutriente_item.html` | Fila de un nutriente en `/nutrientes/` |

### 1.4 `growlog/crud_form.html`

Formulario genérico de edición. Extiende `base.html`, deja vacío el bloque `cultivo_tabs` y reemplaza `bottom_nav` por un único enlace `‹ Volver` (clase `bottom-nav__item`, que `suelo.css` estira a toda la barra con `.barra:has(> .bottom-nav__item)`). El CSS está en un `<style>` en `extra_head`.

Variables de contexto:

| Variable | Obligatoria | Uso |
|---|---|---|
| `title` | sí | `<title>` y `<h1 class="h1">` |
| `subtitle` | no | Párrafo `.cf-sub` bajo el título |
| `form` | sí | Formulario Django; se recorre campo por campo |
| `back_url` | sí | Destino del enlace `‹ Volver`, del botón `Cancelar` y de la barra |
| `submit_label` | no | Texto del botón principal (por defecto `Guardar`) |
| `delete_url` | no | Si existe, muestra el enlace `Eliminar` (`.cf-borrar`) |

Comportamiento de cada campo:

- Muestra `field.label`, el widget, los errores (`.field-error`) y el `help_text` (`.field-hint`).
- Si el widget tiene la clase `form-check-input`, se dibuja como casilla: `<label class="cf-check">` con el control y la etiqueta.
- Si el widget tiene la clase `field-narrow`, el campo recibe `.cf-campo--corto` y ocupa una sola celda de la grilla; los demás ocupan la fila entera. `field-narrow` se pone en `widget.attrs["class"]` en `growlog/forms.py` y solo la interpreta `crud_form.html`; `suelo.css` no la define.
- Un campo con errores recibe `has-error`.
- Los errores generales (`non_field_errors`) se muestran como `.aviso.aviso--bad`.

Clases propias del template:

| Clase | Función |
|---|---|
| `.cf` | Contenedor, ancho máximo 560px |
| `.cf-volver` | Enlace superior "‹ Volver", alto mínimo `var(--toque)` |
| `.cf-sub` | Subtítulo en `--mu` |
| `.cf-form` | Grilla vertical del formulario |
| `.cf-campos` | Grilla `repeat(auto-fill, minmax(140px, 1fr))` |
| `.cf-campo` | Campo; ocupa toda la fila (`grid-column: 1 / -1`) |
| `.cf-campo--corto` | Campo corto; ocupa una celda |
| `.cf-check` | Casilla con etiqueta, alto mínimo `var(--toque)` |
| `.cf-acciones` | Fila con el botón principal (flex 1) y `Cancelar` (`.btn.g`) |
| `.cf-borrar` | Enlace `Eliminar` en `--mu`; al pasar el mouse toma `--bad` |

### 1.5 `growlog/crud_delete.html`

Confirmación de borrado o de acción destructiva. Misma estructura de bloques que `crud_form.html` (sin `cultivo_tabs`, barra con `‹ Volver`).

| Variable | Obligatoria | Uso |
|---|---|---|
| `title` | sí | `<title>` y `<h1 class="h1">` |
| `object_name` | sí | Nombre del objeto afectado, dentro de `.card.cd-borrar__que` |
| `back_url` | sí | Destino de `‹ Volver` y de `Cancelar` |
| `warn` | no | Aviso bajo el nombre (por defecto `No se puede deshacer.`) |
| `confirm_label` | no | Texto del botón de confirmación (por defecto `Eliminar`) |
| `confirm_seguro` | no | Si es verdadero, el botón es `.btn.sm` (color de acento); si no, `.btn.d.sm` (color `--bad`) |

La confirmación es un formulario `POST` con `{% csrf_token %}`; `Cancelar` es `.btn.g.sm`.

### 1.6 Variables de navegación

Los parciales de navegación usan variables del context processor `navegacion`: `cultivo_nav`, `seccion_cultivo`, `nav_cultivos`, `cultivo_destino`, `nav_activa`, `pestanas_cultivo` y `can_edit_cultivo`. Una página de cultivo nueva se agrega a `SECCIONES_CULTIVO`; una página global colgada de "Más" se agrega a `PANTALLAS_MAS`. Ver [pantallas-cultivo.md](pantallas-cultivo.md) y [pantallas.md](pantallas.md).

## 2. `static/growlog/suelo.css`

Hoja única del sistema de diseño. La usan todas las páginas, incluidas `login.html`, `invitacion.html` y `500.html`. Está organizada en seis secciones numeradas en el propio archivo: 1 tokens, 2 base, 3 marco, 4 componentes, 5 compatibilidad con las clases heredadas, 6 utilidades.

### 2.1 Tokens de color

El tema oscuro se define en `:root`; el claro, en `:root[data-theme="light"]`. `partials/tema.html` fija `data-theme` en `<html>`.

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--bg` | `#15110d` | `#ebdfc8` | Fondo de página |
| `--s1` | `#1f1812` | `#f6edda` | Superficie 1: tarjetas, barra inferior, menús |
| `--s2` | `#2a2118` | `#e0d1b4` | Superficie 2: elemento activo o con foco, fondo de píldoras |
| `--ink` | `#f2e7d3` | `#2a1d13` | Texto principal |
| `--mu` | `#a29481` | `#6a5741` | Texto secundario |
| `--ln` | `rgba(242,231,211,.13)` | `rgba(42,29,19,.17)` | Líneas y bordes |
| `--ln-soft` | `rgba(242,231,211,.07)` | `rgba(42,29,19,.09)` | Líneas suaves |
| `--ac` | `oklch(.89 .2 125)` | `oklch(.42 .13 150)` | Acento y acción primaria |
| `--on` | `#15110d` | `#fff` | Texto sobre `--ac` |
| `--bad` | `oklch(.68 .2 25)` | `oklch(.54 .21 27)` | Error, valor alto, acción destructiva |
| `--warn` | `oklch(.82 .14 85)` | `oklch(.56 .14 70)` | Advertencia, dato viejo |
| `--veg` | `oklch(.78 .1 155)` | `oklch(.48 .1 150)` | Vegetativo |
| `--flo` | `oklch(.74 .13 320)` | `oklch(.46 .15 320)` | Floración |
| `--w` | `oklch(.74 .09 195)` | `oklch(.52 .09 205)` | Registro de riego |
| `--m` | `oklch(.8 .12 85)` | `oklch(.66 .13 75)` | Registro de medición |
| `--e` | `oklch(.68 .13 55)` | `oklch(.56 .15 45)` | Registro de evento |
| `--n` | `oklch(.85 .04 85)` | `oklch(.72 .05 80)` | Registro de nota |
| `--z0` | `#0e2a30` | `#b4d3d8` | Zona VPD: muy bajo |
| `--z1` | `#13404a` | `#cfe2e4` | Zona VPD: bajo |
| `--z2` | `#1c4a24` | `#cce5b5` | Zona VPD: ideal |
| `--z3` | `#4f3d16` | `#f0dca6` | Zona VPD: alto |
| `--z4` | `#512018` | `#efb4a4` | Zona VPD: muy alto |

`color-scheme` es `dark` en `:root` y `light` en `:root[data-theme="light"]`. El color de la acción primaria es siempre `--ac`, nunca `--bad`.

Los tokens `--z0` a `--z4` los leen `hoy.js` y la pantalla `aire.html` para pintar el mapa de VPD.

### 2.2 Tokens de tipografía, escalas y medidas

| Token | Valor |
|---|---|
| `--font-display` | `"Familjen Grotesk", system-ui, sans-serif` |
| `--font-body` | `"Familjen Grotesk", system-ui, -apple-system, sans-serif` |
| `--font-mono` | `"DM Mono", ui-monospace, "Consolas", monospace` |
| `--t-xs` / `--t-sm` / `--t-md` / `--t-lg` / `--t-xl` | 12px / 13px / 15px / 17px / 20px |
| `--t-2xl` / `--t-3xl` / `--t-4xl` | 28px / 38px / 52px |
| `--sp-1` a `--sp-7` | 4, 8, 12, 16, 20, 28, 40 px |
| `--r-sm` / `--r-md` / `--r-lg` / `--r-xl` / `--r-pill` | 8px / 12px / 16px / 28px / 999px |
| `--toque` | 44px (alto mínimo de un objetivo táctil) |
| `--lateral` | 224px (ancho de la barra lateral) |
| `--barra` | 72px (alto mínimo de la barra inferior) |

El cuerpo usa `--t-md`, `line-height: 1.45` y `--font-body`. Los títulos `h1` a `h6` usan `--font-display`, peso 600 y `letter-spacing: -.02em`.

### 2.3 Alias de VERDE

`suelo.css` mantiene nombres de la paleta anterior apuntando a los tokens actuales:

| Alias | Apunta a |
|---|---|
| `--bg-alt` | `--bg` |
| `--card` | `--s1` |
| `--card-alt` | `--s2` |
| `--rule` / `--rule-soft` | `--ln` / `--ln-soft` |
| `--cream` | `--ink` |
| `--cream-soft` / `--fine` | `--mu` |
| `--green` | `--ac` |
| `--green-deep` | mezcla de `--ac` (45%) con `--bg` |
| `--green-wash` | `--ac` al 12% sobre transparente |
| `--honey` | `--warn` |
| `--rust` | `--bad` |
| `--plum` | `--flo` |
| `--slate` | `--w` |

Los usan `actividad.css` y `faq.css`. El código nuevo usa los tokens de 2.1.

### 2.4 Base

- Reset: `box-sizing: border-box` global. Márgenes de `h1`-`h6`, `p`, `ul`, `ol`; `img { max-width: 100% }`; `button`, `input`, `select`, `textarea` heredan `font` y `color`; `[hidden]` fuerza `display: none`.
- Enlaces: color `--ac`, sin subrayado; en `:hover` mantienen el color y bajan a `opacity: .85`.
- Foco: `:focus-visible` dibuja un contorno de 2px en `--ac` con separación de 2px.
- Selección de texto: mezcla de `--ac` al 35%.
- `prefers-reduced-motion: reduce` anula animaciones y transiciones.

Clases de texto:

| Clase | Efecto |
|---|---|
| `.mono`, `.num` | `--font-mono` con números tabulares |
| `.mo` | Rótulo: `--font-mono`, `--t-xs`, peso 500, mayúsculas, `letter-spacing: .05em`, color `--mu` |
| `.h1` | `--font-display` 600, `--t-3xl` (38px), `line-height: 1` |
| `.h2` | `--font-display` 600, `--t-xl` (20px), `line-height: 1.1` |

### 2.5 Marco

| Clase | Descripción |
|---|---|
| `.app` | `min-height: 100vh` |
| `.app-main` | Contenedor de contenido, ancho máximo 1280px, con padding que respeta `env(safe-area-inset-*)` y deja espacio para la barra inferior. Desde 992px agrega `margin-left: var(--lateral)` |
| `.lateral` | Barra lateral fija de 224px. `display: none` por debajo de 992px |
| `.lateral__marca`, `.lateral__item`, `.lateral__pie`, `.lateral__usuario` | Marca, enlaces, pie con el botón de registrar y el usuario. `.lateral__item.on` es el activo (fondo `--s2` y punto en `--ac`) |
| `.barra` | Barra inferior fija, grilla de 5 columnas (`1fr 1fr 84px 1fr 1fr`). `display: none` desde 992px |
| `.barra__item` | Enlace de la barra, en `--font-mono` `--t-xs`; `.on` marca el activo con un punto en `--ac` |
| `.barra__mas` | Botón `+` central: círculo de 60px, fondo `--ac`, sobresale 24px hacia arriba |
| `.bottom-nav__item` | Enlace único de la barra en `crud_form` y `crud_delete` (`.barra:has(> .bottom-nav__item)` pasa a una columna) |
| `.cultivo-head` | Contenedor del encabezado del cultivo |
| `.nav-cultivo`, `__btn`, `__label`, `__caret`, `__ro`, `__menu`, `__grupo`, `__item`, `__linea` | Selector de cultivo basado en `<details>`; `__item.active` marca el cultivo actual con una barra de 3px en `--ac` |
| `.cultivo-tabs`, `.cultivo-tabs__item` | Chips de secciones, con scroll lateral en el celular y en varias líneas desde 992px. `.active` marca la sección actual |
| `.mensajes` | Contenedor de los mensajes de Django |

Ejemplo de la barra del celular:

```html
<nav class="barra" aria-label="Navegación principal">
  <a href="/" class="barra__item on" aria-current="page">Hoy</a>
  <a href="#" class="barra__item">Cultivo</a>
  <a href="/registrar/" class="barra__mas" aria-label="Registrar">+</a>
  <a href="#" class="barra__item">Plantas</a>
  <a href="#" class="barra__item">Más</a>
</nav>
```

### 2.6 Componentes

| Clase | Descripción | Variantes |
|---|---|---|
| `.card` | Superficie `--s1`, radio `--r-lg`, padding `14px 16px` | |
| `.pill` | Etiqueta de 28px de alto, fondo `--s2`, `--font-mono` `--t-xs`. `<i class="punto">` dibuja un punto del color del texto | `.pill--green`, `.pill--rust`, `.pill--honey`, `.pill--slate`, `.pill--plum`, `.pill--cream` (texto en `--ac`, `--bad`, `--warn`, `--w`, `--flo`, `--ink`; fondo al 14% de ese color salvo `--cream`). `a.pill` baja a `opacity: .85` al pasar el mouse y mide 36px de alto mínimo por debajo de 992px |
| `.chip` | Botón o etiqueta de selección, alto mínimo 44px, borde de 1.5px | `.on` (borde `--ink`, fondo `--s1`) |
| `.btn` | Botón primario: alto mínimo 56px, fondo `--ac`, texto `--on`, `--font-display` 700 `--t-lg` | `.g` (transparente con borde), `.d` (fondo `--bad`, texto blanco), `.sm` (alto 44px, `--t-md`, radio `--r-md`) |
| `.btn-brand` | Botón primario heredado, alto 44px, fondo `--ac` | |
| `.btn-ghost` | Botón de borde, alto 44px | |
| `.seg` | Control segmentado: contenedor `--s1`, hijos de 40px de alto | Hijo activo: clase `.on` o `aria-pressed="true"` |
| `.fila` | Fila de lista, alto mínimo 56px, borde superior `--ln` | `.fila__texto` (flex 1), `.fila__chevron` |
| `.ck` | Casilla cuadrada de 26px con borde de 2px en `--mu` | |
| `.tog` | Interruptor de 52 por 30px | `.on` o `aria-pressed="true"` (fondo `--ac`) |
| `.vital` | Tarjeta de dato: `.vital__valor` (30px, `--font-display` 600) con `<small>` para la unidad | `.vital--viejo` (trama diagonal; `.vital__edad` en `--warn`) |
| `.vacio` | Estado vacío centrado | Usa `.h2` y `<p>` en `--mu` |
| `.aviso` | Caja con borde izquierdo de 4px en `--warn` | `.aviso--bad` (borde `--bad`) |
| `.toast` | Aviso fijo sobre la barra inferior; fondo `--ink`, texto `--bg`. Desde 992px va abajo a la derecha, de 380px de ancho | `.toast__accion` (acción subrayada de 44px de alto) |
| `.alert` | Mensaje de Django con borde izquierdo de 4px y botón `.alert__cerrar` | `.alert-success` (`--ac`), `.alert-error` y `.alert-danger` (`--bad`), `.alert-warning` (`--warn`), `.alert-info` (`--w`) |
| `.panel` | Caja con `.panel__head`, `.panel__title`, `.panel__body`, `.panel__head-left` | |
| `.table` | Tabla en `--font-mono` `--t-sm`, cabecera en mayúsculas `--t-xs` | |
| `.vpd` | Píldora de VPD de 24px de alto | `.vpd--ideal` (`--ac`), `.vpd--alto` (`--bad`), `.vpd--bajo` (`--w`) |
| `.label-eyebrow` | Equivalente a `.mo` | |
| `.form-errors`, `.form-errors__title` | Caja de errores de formulario con borde izquierdo en `--bad` | |
| `.field-error` | Mensaje de error de un campo, `--t-sm`, `--bad` | |
| `.field-hint` | Ayuda de un campo, `--font-mono` `--t-xs`, `--mu` | |
| `.has-error` | Aplicada a un contenedor: sus `input`, `textarea` y `select` toman borde `--bad` y halo | |
| `.form-control`, `.form-select`, `.form-check-input`, `.form-check-label`, `.form-label` | Nombres heredados con estilo propio, igual al de los controles nativos | |
| `.c-green`, `.c-honey`, `.c-cream`, `.c-soft`, `.c-fine` | Colores de texto (`--ac`, `--warn`, `--ink`, `--mu`) con `!important` | |
| `.estado-vegetativo`, `.estado-floracion`, `.estado-secado`, `.estado-curado`, `.estado-finalizado` | Color por etapa (`--veg`, `--flo`, `--m`, `--m`, `--mu`) | |

Controles de formulario sin clase: `input` de texto, número, contraseña, correo, búsqueda, fecha, hora y `datetime-local`, `textarea` y `select` tienen alto mínimo `--toque`, fondo `--bg`, borde de 1.5px en `--ln`, radio `--r-md` y fuente `--t-md`. Con foco el borde pasa a `--ac` con un halo de 3px. `select` oculta la flecha nativa y dibuja una propia con dos gradientes. Los `checkbox` y `radio` miden 20px con `accent-color: var(--ac)`. Todo `label` es un rótulo `.mo` en bloque.

Ejemplos de marcado:

```html
<div class="card">
  <span class="mo">Temperatura</span>
  <div class="vital__valor">26,4 <small>°C</small></div>
  <span class="vpd vpd--ideal">VPD 1,1</span>
</div>

<a class="btn" href="#">Guardar</a>
<a class="btn g sm" href="#">Cancelar</a>

<div class="seg" role="group">
  <button type="button" class="on">Hoy</button>
  <button type="button">Semana</button>
</div>

<div class="fila">
  <span class="ck"></span>
  <div class="fila__texto">Podar apical</div>
  <span class="fila__chevron">›</span>
</div>
```

### 2.7 Utilidades

Al final de `suelo.css` hay utilidades con nombres de Bootstrap que usan algunas pantallas: `.visually-hidden`, `.d-none`, `.d-flex`, `.d-inline`, `.d-inline-flex`, `.d-md-none` y `.d-md-table-cell` (desde 768px), `.d-lg-block` (desde 992px), `.flex-wrap`, `.align-items-end`, `.align-items-center`, `.justify-content-between`, `.justify-content-center`, `.gap-2` (8px), `.gap-3` (16px), `.w-100`, `.text-center`, `.mt-1` a `.mt-4` (4, 8, 16, 24 px), `.mb-2` a `.mb-4` (8, 16, 24 px), `.p-4`, `.py-3`. La grilla `.row` con columnas `.col-md-4`, `.col-md-5`, `.col-md-7`, `.col-md-8` (desde 768px) y `.col-lg-4`, `.col-lg-8` (desde 992px) apila las columnas en una sola por debajo del punto de corte; `.row.g-3` agrega `row-gap: 16px`. No se carga Bootstrap ni ninguna otra librería de CSS.

### 2.8 Puntos de corte

| Ancho | Efecto |
|---|---|
| menos de 992px | Se ve `.barra` y se oculta `.lateral` |
| 992px o más | Se ve `.lateral` (224px) y se oculta `.barra`; `.app-main` pasa a tener margen izquierdo; `.toast` va abajo a la derecha; `.hoja` pasa de hoja inferior a diálogo centrado |
| 768px | Activa `.d-md-*` y las columnas `.col-md-*` |

## 3. CSS por página

Se carga con `<link>` en el bloque `extra_head` de cada template. Todos usan los tokens de `suelo.css`, salvo `actividad.css` y `faq.css`, que usan los alias de VERDE.

| Archivo | Lo cargan | Contenido |
|---|---|---|
| `static/growlog/registrar.css` | `base.html` (usuario autenticado) | Formulario Registrar y hoja |
| `static/growlog/hoy.css` | `dashboard.html`, `tareas_list.html` | Pantalla Hoy |
| `static/growlog/cultivo.css` | `cultivo_detail.html`, `ciclo.html`, `planta_detail.html`, `registro_ficha.html` | Resumen del cultivo y ficha de registro |
| `static/growlog/plantas.css` | `plantas_list.html`, `planta_detail.html`, `planta_fotos.html` | Lista y ficha de plantas, visor de fotos |
| `static/growlog/bitacora.css` | `timeline.html` | Bitácora |
| `static/growlog/actividad.css` | `actividad.html` | Panel de actividad |
| `static/growlog/faq.css` | `faq.html` | Dudas frecuentes |

Las demás pantallas (`aire.html`, `canopy.html`, `cosecha.html`, `cuenta.html`, `cultivo_ajustes.html`, `cultivo_empezar.html`, `energia.html`, `etapa_historial.html`, `fotoperiodo.html`, `invitados.html`, `mas.html`, `nuevo_cultivo.html`, `nutrientes.html`, `plantas_nuevas.html`, `reporte.html`, `crud_form.html`, `crud_delete.html`, `login.html`, `invitacion.html`) llevan su CSS en un `<style>` dentro de `extra_head`.

### 3.1 `registrar.css`

Prefijo `reg-`. Se carga siempre para usuarios autenticados porque la hoja puede abrirse desde cualquier pantalla.

| Clase | Función |
|---|---|
| `.reg` | Contenedor de la página, ancho máximo 640px |
| `.reg-form`, `.reg-bloque` | Grillas verticales del formulario y de cada bloque por tipo |
| `.reg-aviso`, `.reg-corregir` | Aviso de valores inusuales con su lista y el enlace que lleva al campo |
| `.reg-arriba`, `.reg-cultivo` | Selector de cultivo (un `select` con forma de píldora) |
| `.reg-tipos`, `.reg-tipo` | Selector de tipo de registro como chips con radio oculto. El punto `<i>` de cada tipo usa su color: riego `--w`, ambiente `--m`, evento `--e`, ec `--flo`, tarea `--mu`, planta `--ac`; el resto (nota) usa `--n`. El chip marcado (`:has(input:checked)`) toma borde `--ink` |
| `.reg-hora`, `.reg-hora__chip`, `.reg-hora__campo` | Hora "Ahora" u "Otra hora" |
| `.reg-atajo`, `.reg-atajo__texto`, `.reg-atajo__btn`, `.reg-meta` | Atajo "Repetir riego" |
| `.reg-switch`, `input.tog` | Interruptor hecho con un checkbox (52 por 30px) |
| `.reg-stepper`, `.st`, `.reg-num-gigante` | Volumen con botones menos y más (52px) y número de 44px |
| `.reg-plantas`, `.reg-planta`, `.reg-nutrientes`, `.reg-runoff`, `.reg-runoff__fila` | Listas por planta, de nutrientes y de runoff |
| `.reg-dos`, `.reg-tres`, `.reg-medida` | Grillas de 2 y 3 columnas y campo de medida con número de 28px |
| `.reg-vivo` | Línea de cálculo en vivo (VPD); `data-estado` en `ideal`, `alto` o `bajo` pinta el texto en `--ac`, `--bad` o `--w` |
| `.reg-fuera` | Texto de pH fuera de rango, en `--warn` |
| `.reg-campo`, `.reg-chips`, `.reg-nota` | Campos y grupos de chips de elección |
| `.reg-acciones`, `.reg-guardar` | Barra del botón Guardar, pegada abajo (`position: sticky`) |
| `.hoja-fondo`, `.hoja`, `.hoja__head`, `.hoja__cerrar` | Hoja modal. En el celular es una hoja inferior de hasta 92vh con asa; desde 992px es un diálogo centrado de 620px |
| `body.hoja-abierta` | Bloquea el scroll del fondo (`overflow: hidden`) |
| `.reg-borrar-link` | Enlace `Eliminar` al pie del formulario de edición |
| `.reg-texto`, `.reg-entendi` | Línea de texto libre y chips con lo que se entendió |

### 3.2 `hoy.css`

Prefijo `hoy-`.

| Clase | Función |
|---|---|
| `.hoy`, `.hoy-head` | Contenedor (ancho máximo 1200px) y cabecera. Desde 992px el `.h1` sube a `--t-4xl` |
| `.hoy-cols`, `.hoy-cols--una` | Grilla de dos columnas desde 992px (una sola de 640px con `--una`) |
| `.hoy-sec` | Rótulo de sección |
| `.hoy-fila`, `.hoy-titulo`, `.hoy-meta`, `.hoy-pill--bad`, `.hoy-pill--warn` | Fila de tarea y sus textos |
| `button.ck` | Casilla de tarea; el área táctil real es de 44px (pseudoelemento `::before` con `inset: -9px`) |
| `.hoy-ck--alerta`, `.hoy-ck--hecha`, `.hoy-fila--hecha` | Estados de la casilla y de la fila (hecha: título tachado) |
| `.hoy-deshacer`, `.hoy-nada`, `.hoy-nota` | Botón Deshacer, texto de lista vacía y nota |
| `.hoy-cultivo`, `.hoy-cultivo__fila`, `.hoy-cultivo__link`, `.hoy-lectura`, `.hoy-vpd` (`--ideal`, `--alto`, `--bajo`), `.hoy-riego`, `.hoy-viejo`, `.hoy-espacio` | Bloque de cada cultivo; `.hoy-cultivo__link::after` extiende el enlace a todo el bloque |
| `.hoy-registrar` | Enlace "+ registrar", con `z-index: 1` para quedar sobre el enlace extendido |
| `.hoy-nucleo`, `.hoy-nucleo__w`, `__m`, `__e`, `__n` | SVG del Núcleo (22px de alto): una raya por día, una capa por tipo de registro con los colores `--w`, `--m`, `--e`, `--n` |
| `.hoy-leyenda` | Leyenda de colores del Núcleo |
| `.hoy-aire`, `.hoy-aire__chips`, `.hoy-aire__mapa`, `.hoy-aire__leyenda` | Mapa de aire; `display: none` por debajo de 992px y `position: sticky` desde ahí |

Ejemplo del Núcleo (`partials/hoy_cultivo.html`):

```html
<svg class="hoy-nucleo" style="width: 80%" viewBox="0 0 30 12" preserveAspectRatio="none" role="img">
  <rect x="3" y="0" width="1" height="4" class="hoy-nucleo__w"/>
</svg>
```

### 3.3 `cultivo.css`

Prefijos `cd-` (resumen), `rf-` (ficha de registro) y `tareas-`.

| Clase | Función |
|---|---|
| `.cd`, `.cd-head`, `.cd-titulo`, `.cd-luz`, `.cd-pills`, `.cd-pill--*`, `.cd-seg` | Cabecera del cultivo, píldoras de estado y selector de periodo |
| `.cd-cols`, `.cd-principal`, `.cd-lateral` | Dos columnas desde 992px (`1fr 360px`). En el celular son una columna donde `order` coloca vitales y avisos primero, luego tareas y seguimientos, luego las secciones y por último la configuración |
| `.cd-vitales`, `.cd-vital-ec`, `.cd-vital-link`, `.cd-ideal`, `.cd-alto`, `.cd-bajo`, `.cd-x`, `.cd-warn`, `.cd-bad` | Grilla de `.vital` (3 columnas; 4 desde 992px) y colores de estado |
| `.cd-aviso`, `.cd-edad` | Aviso y edad del dato |
| `.cd-seccion`, `.cd-seccion__head`, `.cd-head-links`, `.cd-link` | Secciones con cabecera |
| `.cd-reg`, `.cd-reg__capa`, `.cd-reg--riego`, `--medicion`, `--evento`, `--medicion_ec`, `.cd-reg__texto`, `.cd-reg__titulo`, `.cd-reg__meta`, `.cd-reg__mas` | Fila de actividad con la banda de color por tipo |
| `.cd-tarea`, `.cd-tarea__titulo`, `.cd-ck--bad`, `.cd-ck--hecha`, `.cd-tarea--hecha`, `.cd-reabrir`, `.cd-hechas`, `.tareas-empty` | Tareas. `#tareas-lista:not(:has(.cd-tarea)) .tareas-empty` muestra el texto de lista vacía |
| `.cd-plantas`, `.cd-planta`, `.cd-planta__estado` (`--cosechada`, `--descartada`), `.cd-archivadas` | Lista de plantas en dos columnas desde 640px |
| `.cd-setup__lista` | Lista de configuración (`dl`) |
| `.rf`, `.rf-titulo`, `.rf-datos`, `.rf-texto`, `.rf-foto`, `.rf-acciones`, `.rf-borrar` | Ficha de un registro; `.rf-borrar` es un `<details>` cuyo `summary` se oculta al abrir |
| `.cd-empezar`, `.cd-empezar__barra` | Recordatorio de primeros pasos con barra de progreso |

### 3.4 `plantas.css`

Prefijos `pl-` (lista), `pf-` (ficha) y `visor`.

| Clase | Función |
|---|---|
| `.pl`, `.pl-head`, `.pl-seg`, `.pl-cuenta` | Lista de plantas y filtro |
| `.pl-grilla`, `.pl-tarjeta`, `.pl-foto`, `.pl-foto--vacia`, `.pl-fila`, `.pl-nombre`, `.pl-altura`, `.pl-meta`, `.pl-vieja`, `.pl-spark` | Grilla de 2 columnas (3 desde 700px, 4 desde 1100px), tarjeta con foto cuadrada, altura y minigráfico |
| `.pf`, `.pf-head`, `.pf-altura`, `.pf-altura__num`, `.pf-altura__ritmo`, `.pf-curva`, `.pf-curva__fechas`, `.pf-datos`, `.pf-seccion`, `.pf-seccion__head`, `.pf-genetica` | Ficha de planta: altura en 84px, curva, datos en 3 columnas |
| `.pf-tira` | Tira de fotos con scroll horizontal y `scroll-snap` |
| `.pf-acciones` | Barra de acciones pegada abajo, sobre la barra inferior en el celular |
| `.visor`, `.visor__barra`, `.visor__cerrar`, `.visor__nav`, `.visor__img`, `.visor__pie` | Visor de fotos a pantalla completa (`position: fixed`, `z-index: 1300`, fondo negro al 92%) |

### 3.5 `bitacora.css`

Prefijo `nc-`.

| Clase | Función |
|---|---|
| `.nc`, `.nc-head`, `.nc-registrar` | Contenedor (ancho máximo 860px) y cabecera. `.nc-registrar` se oculta por debajo de 992px |
| `.nc-filtros`, `.nc-filtro--*`, `.nc-cuenta` | Chips de filtro por tipo con un punto de color: medicion `--m`, riego `--w`, evento `--e`, medicion_ec `--flo`, ciclo `--veg`, planta `--ac` |
| `.nc-dia`, `.nc-reg`, `.nc-capa`, `.nc-reg--*` | Encabezado de día y fila de registro con una columna de color de 18px por tipo (riego, medicion, evento, medicion_ec, etapa y fotoperiodo, planta) |
| `.nc-texto`, `.nc-texto--link`, `.nc-titulo`, `.nc-tag`, `.nc-meta`, `.nc-ideal`, `.nc-alto`, `.nc-bajo`, `.nc-x`, `.nc-warn`, `.nc-mas`, `.nc-mas-pagina` | Texto, estados de VPD y enlace a la ficha |

### 3.6 `actividad.css`

Prefijo `act-`. Panel de actividad: `.act`, `.act-header`, `.act-summary` (tarjetas de cifras; `.is-alert` en `--honey`), `.act-panel`, `.act-people`, `.act-person`, `.act-dot` (`.is-on` en `--green`), `.act-tag`, `.act-num`, `.act-cols` (dos columnas; una por debajo de 900px), `.act-feed` (`.is-fail` en `--honey`), `.act-empty`, `.act-note`. Usa los alias `--cream`, `--cream-soft`, `--fine`, `--green`, `--honey`, `--rule`, `--rule-soft` y `--card`.

### 3.7 `faq.css`

Prefijo `faq-`. Dudas frecuentes: `.faq`, `.faq-header`, `.faq-search` (campo de búsqueda con ícono SVG), `.faq-toc` (índice de secciones), `.faq-section`, `details` y `summary` con `+` y `−` generados por `::after`, `.faq-formula`, `.faq-table-wrap`, `.faq-table`, `.faq-empty`, `.faq-foot`. Usa los alias de VERDE.

## 4. JavaScript

No hay bundler ni paquetes locales. Los scripts propios son archivos estáticos sin dependencias, más bloques inline en los templates. Las librerías externas se cargan por CDN: HTMX 1.9.12 (en `base.html`) y Alpine 3.14.9 (solo en `canopy.html`). Los números se formatean con `toLocaleString('es-AR')`.

### 4.1 `static/growlog/registrar.js`

Lo carga `base.html` para usuarios autenticados. Busca `form[data-reg]` y lo inicializa una sola vez (marca `data-listo`); se vuelve a ejecutar tras cada `htmx:afterSwap`, así que sirve en la página, en la hoja y en la corrección de un registro. Lee los datos por cultivo del `json_script` `reg-datos`. El servidor ya dibuja el estado inicial del formulario; el script acompaña lo que el usuario toca.

| Función | Comportamiento |
|---|---|
| Tipo y cultivo | Muestra los bloques `[data-kind]` del tipo elegido y los `[data-cultivo]` del cultivo elegido. Los bloques ocultos quedan `disabled`, de modo que no bloquean con `required` ni viajan en el POST. El texto de `[data-guardar]` pasa a `Guardar <tipo>` |
| Total de riego | Calcula el total de ml en `[data-total]` (volumen común por cantidad de plantas, o suma por planta) |
| VPD en vivo | Con `[data-temp]` y `[data-hr]` calcula el VPD (fórmula de Magnus) y lo muestra en `[data-vpd]`, con el rango ideal del cultivo y `data-estado` |
| EC en vivo | Con `[data-ec]` muestra el equivalente en µS y mS en `[data-ec-hint]` (el campo se escribe en ×10 µS/cm) |
| pH en vivo | Con `[data-ph]` indica en `[data-ph-hint]` si el valor está dentro del rango ideal del cultivo |
| Repetir riego | `[data-repetir]` completa volúmenes, pH, EC y nutrientes con el último riego del cultivo (`ultimo_riego` de `reg-datos`) |
| Stepper | `[data-paso]` suma o resta al volumen común |
| Hora | `[data-hora-chip]` alterna entre `Ahora` y `Otra hora`; actualiza `[data-hora-modo]` (`ahora` o `elegida`) |
| Corregir | `.reg-corregir` abre el campo señalado y le da foco |
| Texto libre | `[data-texto]` se interpreta 250 ms después de dejar de escribir (o con Enter, que no envía el formulario). Reconoce volumen (ml, cc, L), pH, EC (mS, µS o valor ×10), temperatura, humedad, `c/u`, nombres de planta y nutrientes del catálogo (tolerando un error de una letra). Cambia el tipo si hace falta, completa los campos y muestra chips en `[data-entendi]`; lo que sobra va a notas. Los valores puestos por el texto se vuelven a calcular en cada interpretación, salvo que se hayan editado a mano |
| Errores | Un campo inválido dentro de un `<details>` plegado lo abre; si hay un campo con error, recibe foco |

Para el comportamiento funcional del formulario ver [registrar.md](registrar.md).

### 4.2 `static/growlog/hoy.js`

Lo carga `dashboard.html` con `defer`, solo si la vista pasa `mapa`. Lee los datos del `json_script` `hoy-mapa-datos` y dibuja en el `<svg id="hoy-aire-svg">` el mapa de aire (temperatura en X, humedad relativa en Y), de 340 por 250 unidades.

- Fondo: grilla de 56 por 40 celdas coloreadas con `--z0` a `--z4` según el VPD de cada punto y el rango del cultivo elegido (margen de 0,3 kPa a cada lado; sin rango, cortes de 0,8 y 1,2 kPa).
- Puntos: una lectura por cultivo, coloreada según estado (`ideal` en `--ac`, `alto` en `--bad`, `bajo` en `--w`), con la cola de las últimas 24 h como línea punteada. Un dato viejo se dibuja hueco.
- Chips `#hoy-aire-chips .chip`: eligen qué cultivo define las zonas y redibujan. El texto de `#hoy-aire-nota` describe las zonas.
- Los colores se leen de las variables CSS en cada dibujo.

### 4.3 `static/growlog/fotos.js`

Lo cargan `planta_detail.html` (si hay fotos) y `planta_fotos.html`.

- Visor: los elementos `[data-visor]` abren `#visor` con la foto, la fecha y la altura. Navegación con `[data-visor-paso]` (`-1` o `1`), flechas del teclado, deslizamiento horizontal de más de 40px y cierre con `[data-visor-cerrar]` o Escape.
- Vistas: los botones `[data-vista]` alternan los paneles `[data-panel]` (línea de tiempo y comparar).
- Comparar: en `[data-comparar]` el usuario elige dos fotos (`[data-elegir]`); la selección arranca con la más vieja y la más nueva y, al elegir otra, reemplaza la elegida hace más tiempo. Calcula la diferencia de altura (cm) y de nudos, y los días entre ambas. El control `[data-rango]` fija la variable CSS `--corte` del contenedor, que marca el corte entre las dos imágenes.

### 4.4 Scripts inline de `base.html`

| Función | Comportamiento |
|---|---|
| Hoja de Registrar | Tras `htmx:afterSwap` sobre `#hoja` con contenido, agrega `hoja-abierta` al `<body>` y da foco al tipo marcado. Se cierra (vacía `#hoja`) con cualquier `[data-cerrar-hoja]` (botón `✕` o fondo) o con Escape |
| Cerrar avisos | `[data-cerrar-aviso]` elimina su `.alert` |
| Selector de cultivo | Cierra los `details.nav-cultivo` abiertos al tocar afuera o con Escape |
| Atajo Cmd/Ctrl+K | Si la pantalla tiene `[data-texto]`, le da foco; si no, abre la hoja (clic en el `+` del lateral o de la barra) y le da foco a `[data-texto]` al cargar |
| Toast | El `[data-toast]` se elimina a los 10 segundos |

### 4.5 Números decimales

El script inline final de `base.html` convierte, al cargar el DOM, todo `input[type="number"]` en `type="text"` con `inputmode="decimal"` y `data-decimal="1"`. La tecla coma inserta un punto; al salir del campo se normaliza la coma a punto y se valida que sea numérico (mensaje `Ese número no se entiende. Probá con 26.5` en un `.field-error.js-decimal-err`, y borde `--bad`). Al enviar un formulario se sanean los campos `[data-decimal]` y, si alguno es inválido, se cancela el envío. Los pedidos HTMX aplican la misma normalización (ver 1.1).

### 4.6 Scripts inline por página

| Template | Función |
|---|---|
| `mas.html` | Selector de tema (`#tema-seg`, ver sección 6) y alta o baja de notificaciones push |
| `cultivo_detail.html` | Tras `htmx:afterSettle`, muestra el bloque `#tareas-done-panel` si `#tareas-done` tiene hijos |
| `aire.html` | Dibuja el mapa de VPD de la pantalla Aire en `#vpd-svg` con los datos de `#vpd-datos`; se redibuja al cambiar el tema |
| `canopy.html` | Componente Alpine `canopyApp` (ver 7.2) |
| `faq.html` | Filtro local de las dudas: normaliza el texto (minúsculas, sin tildes), muestra solo los `<details>` que contienen todas las palabras, los abre y oculta las secciones vacías |
| `energia.html` | Oculta los campos `[data-nuevo]` cuando se elige un equipo existente en `[data-equipo]` |
| `fotoperiodo.html` | `setPreset(fp, hora)` completa fotoperíodo y hora de encendido |
| `invitados.html` | Copia el link de invitación (`[data-copiar]`) y lo comparte con `navigator.share` (`[data-compartir]`, se elimina si no existe la API) |
| `cultivo_empezar.html` | `[data-cambiar]` muestra el formulario editable de un paso del checklist |
| `plantas_nuevas.html` | Arma los campos de apodo según cantidad y strain, sin pisar los que se editaron a mano |

## 5. Fuentes

`partials/fonts.html` es el único lugar donde se cargan fuentes. Incluye `preconnect` a `fonts.googleapis.com` y `fonts.gstatic.com`, y una hoja de Google Fonts con:

- Familjen Grotesk, peso variable 400 a 700 (`--font-display` y `--font-body`).
- DM Mono, pesos 400 y 500 (`--font-mono`).

Con `display=swap`. Lo incluyen `base.html`, `login.html`, `invitacion.html` y `500.html`. Los SVG dibujados por JS usan `'DM Mono, monospace'` y `'Familjen Grotesk, sans-serif'` en el atributo `font-family`.

## 6. Tema claro y oscuro

`partials/tema.html` se incluye en el `<head>` antes de cargar cualquier hoja, para que la página no parpadee.

1. Declara dos `<meta name="theme-color">`: `#15110d` con `prefers-color-scheme: dark` y `#ebdfc8` con `prefers-color-scheme: light`.
2. Un script lee `localStorage.tema` (valores `auto`, `claro` u `oscuro`; por defecto `auto`; la lectura va en `try/catch`).
3. Resuelve oscuro si el valor es `oscuro`, o si no es `claro` y el sistema no declara `prefers-color-scheme: light`.
4. Escribe `data-theme="dark"` o `data-theme="light"` en `<html>`.

El oscuro es el tema por defecto. El claro se activa con `:root[data-theme="light"]` en `suelo.css`.

El selector está en `mas.html`: un `.seg` con id `tema-seg` y tres botones `data-tema="auto"`, `"claro"` y `"oscuro"`. Al tocar uno, guarda el valor en `localStorage.tema`, actualiza `data-theme` de inmediato y marca el botón activo con `aria-pressed`. La preferencia es por dispositivo y no se guarda en el servidor.

Los SVG dibujados por JS (`hoy.js`, `aire.html`, `canopy.html`) leen los colores de las variables CSS con `getComputedStyle` al dibujar; `aire.html` y `canopy.html` se redibujan cuando cambia el tema.

## 7. HTMX y Alpine

### 7.1 HTMX

`django-htmx` está activo en el servidor y HTMX 1.9.12 se carga en `base.html`. Usos:

| Dónde | Atributos | Qué hace |
|---|---|---|
| `lateral.html`, `bottom_nav.html`, `tareas_list.html`, `planta_detail.html` | `hx-get="/registrar/?hoja=1…"` `hx-target="#hoja"` | Abre Registrar como hoja. `planta_detail.html` agrega `kind=planta&planta=<pk>`; `tareas_list.html` agrega `kind=tarea`. En `lateral.html` y `bottom_nav.html` el enlace conserva su `href` a `/registrar/` y no lleva `hx-get` cuando la página actual ya es Registrar |
| `hoy_item.html`, `hoy_tarea_hecha.html` | `hx-post` a `tarea_completar` o `tarea_descompletar`, `hx-vals='{"origen": "hoy"}'`, `hx-swap="outerHTML"` | Completa o deshace una tarea desde Hoy |
| `tarea_row.html` | `hx-post` a `tarea_completar`, `hx-swap="delete"` | Completa una tarea en la página del cultivo. La respuesta incluye el fragmento fuera de banda de `tarea_completar_oob.html` |
| `cultivo_detail.html`, `tarea_completar_oob.html` | `hx-post` a `tarea_descompletar`, `hx-swap="delete"` | Reabre una tarea hecha; `tarea_descompletar_oob.html` la devuelve a `#tareas-lista` |
| `cultivo_detail.html` | `hx-post` a `evento_resolver_followup`, `hx-swap="outerHTML"` | Resuelve un seguimiento |
| `bitacora_filas.html` | `hx-get="?desde=…"`, `hx-swap="outerHTML"` | `Ver más` reemplaza el enlace por las filas siguientes |

El resto de los formularios son envíos normales de página completa. El token CSRF de los pedidos HTMX viaja en el header `X-CSRFToken` (ver 1.1).

### 7.2 Alpine

Alpine 3.14.9 se carga con `defer` solo desde el bloque `extra_js` de `canopy.html`, la pantalla del canopy (rejilla de 36 celdas, colas por planta y snapshots). Define el componente `canopyApp(cfg)` con estado (celdas, plantas, colas, notas, snapshots), propiedades calculadas (porcentaje de relleno, colas totales, vatios por cola, densidad, estado del flip) y el arrastre de colas. Ninguna otra página usa Alpine.

## 8. Íconos y gráficos

- No hay librería ni fuente de íconos. Los controles de acción se escriben con texto o caracteres: `+`, `✕`, `‹`, `›`, `▾`, `✓`, `−`, `+ Registrar`, `+ Nuevo cultivo`.
- Los íconos de la app instalada son archivos PNG en `static/growlog/icons/` (`icon-96x96.png`, `icon-192x192.png`, `icon-512x512.png`, `maskable-192x192.png`, `maskable-512x512.png`, `apple-touch-icon.png`, `badge-96x96.png`, `shortcut-registrar-96x96.png`), referenciados desde `pwa_head.html` y el manifest.
- El SVG inline se usa para gráficos y para el ícono de búsqueda: Núcleo en `partials/hoy_cultivo.html`, mapa de aire en `dashboard.html` (dibujado por `hoy.js`), mapa de VPD en `aire.html`, canopy en `canopy.html`, curva y minigráficos en `planta_detail.html` y `plantas_list.html`, gráficos de `reporte.html` y la lupa de `faq.html`.
- Los puntos de color (`<i>`) de las leyendas y de los chips de tipo son elementos con fondo, no íconos.

## 9. Tamaños mínimos y objetivos táctiles

| Regla | Valor |
|---|---|
| Tamaño mínimo de texto | 12px (`--t-xs`) |
| Objetivo táctil | 44px (`--toque`) para botones, chips, enlaces de acción, filas y controles de formulario |
| Alturas menores | `.pill` mide 28px y `a.pill` 36px por debajo de 992px; `.cultivo-tabs__item`, `.seg > *`, `.reg-chips .chip`, `.nc-filtros .chip` y `.hoy-aire__chips .chip` miden 40px; `.cd-reabrir` mide 36px |
| Casilla de tarea | Dibujada de 26px; el área táctil es de 44px por un pseudoelemento `::before` con `inset: -9px` |
| Botón primario | 56px de alto (`.btn`); 44px con `.sm` |
| Barra inferior | 72px de alto mínimo; el botón `+` mide 60px |
| Zonas seguras | `.app-main`, `.barra`, `.toast`, `.visor` y las páginas de login e invitación usan `env(safe-area-inset-*)` |

## 10. Convenciones de texto

Fijadas en `CLAUDE.md`:

- Voseo rioplatense, frases cortas y simples (por ejemplo "Entrá para ver cómo vienen tus plantas", "Probá de nuevo en un rato").
- Sin guiones largos (em dash) y sin decoración de terminal como `//` o `§`.
- Los rótulos de campo van en mayúsculas por CSS (`.mo`, `label`), no en el texto del template.
- En los formularios genéricos, las etiquetas legibles se definen en `labels` del `Meta` del ModelForm y los campos cortos se marcan con `field-narrow`.
- Los números se muestran con coma decimal (`toLocaleString('es-AR')`) y se aceptan con coma o punto.
- Las fechas de los `datetime-local` usan `DT_FMT` de `growlog/forms.py`.
- La marca se escribe `62×ROOTS`.
