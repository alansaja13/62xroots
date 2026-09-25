"""Fotos servidas con control de acceso por cultivo."""
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404

from ..models import MedicionPlanta
from ..permissions import cultivos_visibles


@login_required
def protected_media(request, path):
    # Solo fotos reconocidas del dominio; nunca exponer archivos arbitrarios
    # (por ejemplo un backup) porque alguien adivinó su ruta de almacenamiento.
    if not path:
        raise Http404("Foto no encontrada")
    medicion = MedicionPlanta.objects.filter(
        planta__cultivo__in=cultivos_visibles(request.user), foto=path,
    ).first()
    if medicion is None:
        raise Http404("Foto no encontrada")
    try:
        response = FileResponse(medicion.foto.open("rb"))
    except FileNotFoundError:
        raise Http404("Foto no encontrada")
    response["Cache-Control"] = "no-store, private"
    return response
