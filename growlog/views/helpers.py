"""Helpers compartidos por las vistas."""


def build_timeline(cultivo, limit=50):
    fetch = limit * 3
    items = []
    # Las relaciones que muestra el template se traen en bloque: antes cada fila
    # disparaba sus propias consultas (cientos por página).
    for m in cultivo.mediciones.select_related("creado_por")[:fetch]:
        items.append({"tipo": "medicion", "ts": m.timestamp, "obj": m, "icon": "bi-thermometer-half"})
    riegos = cultivo.riegos.select_related("creado_por").prefetch_related(
        "detalle_plantas__planta", "nutrientes_aplicados__nutriente")
    for r in riegos[:fetch]:
        items.append({"tipo": "riego", "ts": r.timestamp, "obj": r, "icon": "bi-droplet-fill"})
    for e in cultivo.eventos.select_related("creado_por").prefetch_related("plantas_afectadas")[:fetch]:
        items.append({"tipo": "evento", "ts": e.timestamp, "obj": e, "icon": "bi-calendar-event"})
    for ec in cultivo.mediciones_ec.select_related("creado_por")[:fetch]:
        items.append({"tipo": "medicion_ec", "ts": ec.timestamp, "obj": ec, "icon": "bi-moisture"})
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:limit]


def evaluar_ambiente(medicion, param):
    T = float(medicion.temperatura_c)
    HR = float(medicion.humedad_relativa)
    vpd = medicion.vpd

    def estado(val, mn, mx):
        if float(mn) <= val <= float(mx):
            return "ideal"
        return "alto" if val > float(mx) else "bajo"

    return {
        "temp": estado(T, param.temp_min, param.temp_max),
        "hr": estado(HR, param.hr_min, param.hr_max),
        "vpd": estado(vpd, param.vpd_min, param.vpd_max),
    }
