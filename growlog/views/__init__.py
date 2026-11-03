"""Vistas web de la bitácora, agrupadas por dominio.

Se reexportan aquí para que urls.py siga usando ``views.<nombre>``.
"""
from .actividad import actividad  # noqa: F401
from .auth import (  # noqa: F401
    login_view,
    logout_view,
)
from .ayuda import faq  # noqa: F401
from .cuenta import cuenta  # noqa: F401
from .mas import mas  # noqa: F401
from .cultivos import (  # noqa: F401
    cambio_etapa_cultivo_editar,
    cambio_etapa_cultivo_eliminar,
    cultivo_aire,
    cultivo_ajustes,
    cultivo_ciclo,
    cultivo_archivar,
    cultivo_detail,
    cultivo_cosecha,
    cultivo_empezar,
    cultivo_editar,
    cultivo_etapa,
    cultivo_marcar_flora,
    cultivo_reabrir,
    dashboard,
    nuevo_cultivo,
    timeline,
)
from .plantas import (  # noqa: F401
    cambio_etapa_planta_editar,
    cambio_etapa_planta_eliminar,
    medicion_planta_crear,
    planta_crear,
    planta_detail,
    planta_editar,
    planta_eliminar,
    planta_etapa_list,
    planta_fotos,
    plantas_list,
)
from .tareas import (  # noqa: F401
    tarea_completar,
    tarea_descompletar,
    tareas_list,
    tareas_todas,
)
from .eventos import (  # noqa: F401
    evento_resolver_followup,
)
from .mediciones import (  # noqa: F401
    cambio_fotoperiodo_editar,
    cambio_fotoperiodo_eliminar,
    fotoperiodo_list,
)
from .invitados import (  # noqa: F401
    invitacion_aceptar,
    invitacion_revocar,
    invitado_crear,
    invitado_eliminar,
    invitado_rol,
    invitados_panel,
)
from .nutrientes import (  # noqa: F401
    nutriente_crear,
    nutriente_editar,
    nutriente_eliminar,
    nutriente_ocultar,
    nutrientes,
)
from .registrar import (  # noqa: F401
    evento_editar, medicion_ambiente_editar, medicion_ec_editar, medicion_planta_editar,
    registrar, registrar_deshacer, registro_editar, riego_editar, tarea_editar,
)
from .registros import registro_borrar, registro_ficha, registro_restaurar  # noqa: F401
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
