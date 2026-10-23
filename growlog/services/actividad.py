"""Actividad de la app para el administrador: ingresos (tabla Ingreso) y lo que
cada persona registró, derivado de los datos que ya existen (creado_por).

Los registros no guardan cuándo se cargaron, sino cuándo se observó: esa es la
fecha que se usa. Tareas y plantas no tienen fecha, así que no cuentan."""
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth.models import User
from django.db.models import Count, Max, Q
from django.utils import timezone

from ..models import Evento, Ingreso, MedicionAmbiente, MedicionEC, MedicionPlanta, Riego

# (modelo, campo de fecha, ruta al cultivo, texto del movimiento)
FUENTES = [
    (MedicionAmbiente, "timestamp", "cultivo", "midió el ambiente"),
    (Riego, "timestamp", "cultivo", "registró un riego"),
    (MedicionEC, "timestamp", "cultivo", "midió pH/EC"),
    (Evento, "timestamp", "cultivo", "anotó una observación"),
    (MedicionPlanta, "fecha", "planta__cultivo", "midió una planta"),
]
MOVIMIENTOS = 25


def _como_datetime(valor):
    """Las mediciones de planta tienen solo fecha: se ubican al inicio del día."""
    if valor is None or isinstance(valor, datetime):
        return valor
    return timezone.make_aware(datetime.combine(valor, time.min))


def _desde(campo, momento):
    # Los campos de solo fecha se comparan contra la fecha local.
    return {f"{campo}__gte": momento.date() if campo == "fecha" else momento}


def resumen_actividad(*, ahora=None):
    ahora = ahora or timezone.now()
    hace_7, hace_30 = ahora - timedelta(days=7), ahora - timedelta(days=30)
    personas = {u.pk: {"usuario": u, "ultimo_registro": None, "registros_7": 0, "registros_30": 0,
                       "ultimo_ingreso": None, "dispositivo": ""}
                for u in User.objects.filter(is_active=True)}

    movimientos = []
    for modelo, campo, ruta_cultivo, texto in FUENTES:
        conteos = (modelo.objects.filter(creado_por__isnull=False).values("creado_por")
                   .annotate(ultimo=Max(campo),
                             d7=Count("pk", filter=Q(**_desde(campo, hace_7))),
                             d30=Count("pk", filter=Q(**_desde(campo, hace_30)))))
        for fila in conteos:
            persona = personas.get(fila["creado_por"])
            if persona is None:
                continue
            ultimo = _como_datetime(fila["ultimo"])
            if persona["ultimo_registro"] is None or ultimo > persona["ultimo_registro"]:
                persona["ultimo_registro"] = ultimo
            persona["registros_7"] += fila["d7"]
            persona["registros_30"] += fila["d30"]
        recientes = (modelo.objects.filter(creado_por__isnull=False)
                     .select_related("creado_por", ruta_cultivo).order_by(f"-{campo}", "-pk")[:MOVIMIENTOS])
        for obj in recientes:
            cultivo = obj
            for atributo in ruta_cultivo.split("__"):
                cultivo = getattr(cultivo, atributo)
            movimientos.append({"usuario": obj.creado_por, "texto": texto, "cultivo": cultivo,
                                "momento": _como_datetime(getattr(obj, campo))})

    # El último ingreso de cada uno: el pk más alto, que sirve igual en SQLite y PostgreSQL.
    ultimos = (Ingreso.objects.filter(exito=True, usuario__in=list(personas))
               .values("usuario_id").annotate(ultimo=Max("pk")).values_list("ultimo", flat=True))
    for ingreso in Ingreso.objects.filter(pk__in=list(ultimos)):
        personas[ingreso.usuario_id]["ultimo_ingreso"] = ingreso.creado_en
        personas[ingreso.usuario_id]["dispositivo"] = ingreso.dispositivo
    for persona in personas.values():
        # Antes de que existiera la tabla de ingresos, Django ya anotaba last_login.
        persona["ultimo_ingreso"] = persona["ultimo_ingreso"] or persona["usuario"].last_login
        persona["activo_7"] = bool(persona["registros_7"]
                                   or (persona["ultimo_ingreso"] and persona["ultimo_ingreso"] >= hace_7))

    minimo = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
    lista = sorted(personas.values(), key=lambda p: max(p["ultimo_registro"] or minimo,
                                                        p["ultimo_ingreso"] or minimo), reverse=True)
    movimientos.sort(key=lambda m: m["momento"], reverse=True)
    return {
        "personas": lista,
        "activos_7": sum(p["activo_7"] for p in lista),
        "movimientos": [m for m in movimientos if m["momento"] <= ahora][:MOVIMIENTOS],
        "ingresos": Ingreso.objects.select_related("usuario")[:20],
        "fallidos_30": Ingreso.objects.filter(exito=False, creado_en__gte=hace_30).count(),
    }

