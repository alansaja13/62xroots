"""Primeros pasos de un cultivo nuevo: qué falta configurar para que la app sirva de verdad."""
from django.urls import reverse

# Hasta cuántos días de vida el resumen del cultivo recuerda los pasos que faltan.
DIAS_RECORDATORIO = 21


def pasos(cultivo):
    slug = cultivo.slug
    registrar = reverse("growlog:registrar")
    lista = [
        {"clave": "duracion", "titulo": "Cuánto esperás que dure",
         "detalle": "Días de vege y de flora. Con eso Ciclo te muestra estimado contra real.",
         "hecho": bool(cultivo.dias_veg_estimados and cultivo.dias_flora_estimados), "url": None},
        {"clave": "plantas", "titulo": "Plantas",
         "detalle": "Cargá todas juntas: cantidad y strain, los apodos los cambiás ahí mismo.",
         "hecho": cultivo.plantas.exists(), "url": reverse("growlog:planta_crear", args=[slug])},
        {"clave": "fotoperiodo", "titulo": "Fotoperíodo",
         "detalle": "Horas de luz y a qué hora prende. Separa las lecturas de día y de noche.",
         "hecho": cultivo.cambios_fotoperiodo.exists(), "url": reverse("growlog:fotoperiodo_list", args=[slug])},
        {"clave": "luz", "titulo": "Luz",
         "detalle": "Modelo y watts reales de la lámpara, para el g/W y el costo de la luz.",
         "hecho": bool(cultivo.lampara_watts_reales) or cultivo.costos_energeticos.exists(), "url": None},
        {"clave": "medicion", "titulo": "Primera medición",
         "detalle": "Temperatura y humedad de la carpa. Desde ahí arranca el mapa de Aire.",
         "hecho": cultivo.mediciones.exists(), "url": f"{registrar}?cultivo={cultivo.pk}&kind=ambiente"},
    ]
    hechos = sum(p["hecho"] for p in lista)
    return {"pasos": lista, "hechos": hechos, "total": len(lista), "completo": hechos == len(lista),
            "porcentaje": round(100 * hechos / len(lista))}


def recordar(cultivo):
    """Los pasos para el resumen del cultivo, solo mientras el cultivo es nuevo y le falta algo."""
    if cultivo.estado == "finalizado" or cultivo.archivado or cultivo.dias_desde_inicio > DIAS_RECORDATORIO:
        return None
    datos = pasos(cultivo)
    return None if datos["completo"] else datos
