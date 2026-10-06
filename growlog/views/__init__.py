"""Vistas web de la bitácora, agrupadas por dominio.

Se reexportan aquí para que urls.py siga usando ``views.<nombre>``.
"""
from .auth import (  # noqa: F401
    login_view,
    logout_view,
)
from .cultivos import (  # noqa: F401
    cambio_etapa_cultivo_editar,
    cambio_etapa_cultivo_eliminar,
    cultivo_detail,
    cultivo_editar,
    cultivo_etapa,
    cultivo_finalizar,
    cultivo_marcar_flora,
    cultivo_tendencias,
    cultivo_tendencias_json,
    dashboard,
    nuevo_cultivo,
    registrar_en_cultivo,
    timeline,
)
from .plantas import (  # noqa: F401
    cambio_etapa_planta_editar,
    cambio_etapa_planta_eliminar,
    medicion_planta_crear,
    medicion_planta_editar,
    medicion_planta_eliminar,
    planta_crear,
    planta_detail,
    planta_editar,
    planta_eliminar,
    planta_etapa_list,
)
from .tareas import (  # noqa: F401
    tarea_completar,
    tarea_descompletar,
    tarea_editar,
    tarea_eliminar,
    tareas_list,
)
from .eventos import (  # noqa: F401
    evento_editar,
    evento_eliminar,
    evento_resolver_followup,
)
from .riegos import (  # noqa: F401
    nutriente_aplicado_crear,
    nutriente_aplicado_eliminar,
    riego_editar,
    riego_eliminar,
)
from .mediciones import (  # noqa: F401
    cambio_fotoperiodo_editar,
    cambio_fotoperiodo_eliminar,
    fotoperiodo_list,
    medicion_ambiente_editar,
    medicion_ambiente_eliminar,
    medicion_ec_editar,
    medicion_ec_eliminar,
)
from .invitados import (  # noqa: F401
    invitado_crear,
    invitado_eliminar,
    invitado_rol,
    invitados_panel,
)
from .pwa import (  # noqa: F401
    push_subscribe,
    push_unsubscribe,
    pwa_manifest,
    pwa_service_worker,
)
from .media import (  # noqa: F401
    protected_media,
)
from .reportes import (  # noqa: F401
    cultivo_energia,
    cultivo_reporte,
)
from .canopy import (  # noqa: F401
    canopy_guardar,
    canopy_snapshot_json,
    canopy_view,
)
from .errors import (  # noqa: F401
    error_400,
    error_403,
    error_404,
    error_500,
)
