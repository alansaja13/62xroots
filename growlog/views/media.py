"""Fotos servidas con control de acceso por cultivo."""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
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
        Q(foto=path) | Q(foto_mini=path), planta__cultivo__in=cultivos_visibles(request.user),
    ).first()
    if medicion is None:
        raise Http404("Foto no encontrada")
    mini = medicion.foto_mini.name == path
    try:
        response = FileResponse((medicion.foto_mini if mini else medicion.foto).open("rb"))
    except FileNotFoundError:
        raise Http404("Foto no encontrada")
    # Las miniaturas se repiten en listas y galerías: que el navegador las guarde un día, solo para quien las vio.
    response["Cache-Control"] = "private, max-age=86400" if mini else "no-store, private"
    return response
