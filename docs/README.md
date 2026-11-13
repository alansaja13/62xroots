# Documentación de 62xroots

62xroots es una bitácora web de cultivo indoor (Django, en español de Argentina). Esta carpeta describe cómo está construida y cómo se comporta la app.

## Referencia de la app

Está en [`referencia/`](referencia/). Cada documento se puede leer por separado.

| Documento | Qué responde |
| --- | --- |
| [arquitectura.md](referencia/arquitectura.md) | Estructura del proyecto, configuración, middleware, PWA y push, comandos de gestión, tests y despliegue |
| [modelos.md](referencia/modelos.md) | Cada modelo de datos: campos, unidades, relaciones y reglas |
| [servicios.md](referencia/servicios.md) | La lógica de negocio compartida entre web y API |
| [permisos.md](referencia/permisos.md) | Roles, acceso por cultivo, invitaciones, login y cuenta |
| [registrar.md](referencia/registrar.md) | Carga, corrección y borrado de registros |
| [pantallas-cultivo.md](referencia/pantallas-cultivo.md) | Navegación y pantallas del trabajo diario: Hoy, Cultivo, Bitácora, Plantas, Tareas, Aire y Ciclo |
| [pantallas.md](referencia/pantallas.md) | Resto de las pantallas: Más, cuenta, nutrientes, energía, Canopy, actividad, dudas, errores |
| [ciclo-de-vida.md](referencia/ciclo-de-vida.md) | Un cultivo de punta a punta: alta, etapas, cosecha, cierre y reporte |
| [api.md](referencia/api.md) | API JSON v1 |
| [diseno.md](referencia/diseno.md) | Templates, sistema visual, CSS y JavaScript |

Por dónde empezar según lo que busques:

- Entender la app: arquitectura, modelos y ciclo de vida.
- Cambiar una pantalla: pantallas-cultivo o pantallas, y después diseno.
- Tocar la carga de datos: registrar y servicios.
- Integrar con otra herramienta: api y permisos.

## Historial del proyecto

Documentos que registran decisiones y entregas.

- [rumbo-del-producto.md](rumbo-del-producto.md): propósito, principios y entregas.
- [acceso-por-cultivo.md](acceso-por-cultivo.md): política de acceso por cultivo y su puesta en uso.
- [puesta-en-produccion.md](puesta-en-produccion.md): preparación y ensayo de la actualización en Railway.
- [rediseno/](rediseno/): brief y plan por fases del rediseño "Suelo y aire".
