"""URL de la ficha de un registro a partir del tipo con que lo nombra la bitácora."""
from urllib.parse import quote

from django import template
from django.urls import reverse

register = template.Library()

# Tipo en la bitácora → tipo de la ficha. Etapa y fotoperíodo no tienen ficha.
FICHA = {"medicion": "ambiente", "medicion_ec": "ec", "riego": "riego", "evento": "evento",
         "planta": "planta", "ambiente": "ambiente", "ec": "ec", "tarea": "tarea"}


@register.simple_tag(takes_context=True)
def ficha_url(context, tipo, pk):
    clave = FICHA.get(tipo)
    if not clave:
        return ""
    url = reverse("growlog:registro_ficha", args=[clave, pk])
    request = context.get("request")
    return f"{url}?volver={quote(request.get_full_path())}" if request else url
