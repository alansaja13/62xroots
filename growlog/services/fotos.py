"""Fotos de plantas: se achican al subirlas y se arma una miniatura para listas y galerías."""
import logging
from io import BytesIO
from pathlib import PurePosixPath

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

LADO_MAXIMO = 2048     # la foto guardada no supera esto de lado
LADO_MINI = 480        # miniatura para tarjetas y tiras de fotos
PESO_SIN_TOCAR = 2_500_000  # una foto chica en JPEG no se vuelve a comprimir


def _jpeg(imagen, lado, calidad):
    copia = imagen.copy()
    copia.thumbnail((lado, lado))
    if copia.mode not in ("RGB", "L"):
        copia = copia.convert("RGB")
    salida = BytesIO()
    copia.save(salida, "JPEG", quality=calidad, optimize=True)
    return salida.getvalue()


def preparar_foto(medicion):
    """Antes de guardar una foto nueva: la endereza, la achica si hace falta y crea la miniatura.
    Si algo falla, se guarda la original tal cual y la galería usa esa."""
    from PIL import Image, ImageOps
    archivo = medicion.foto.file
    try:
        archivo.seek(0)
        imagen = ImageOps.exif_transpose(Image.open(archivo))
        base = PurePosixPath(medicion.foto.name).stem or "foto"
        grande = max(imagen.size) > LADO_MAXIMO or getattr(archivo, "size", 0) > PESO_SIN_TOCAR
        if grande:
            medicion.foto.save(f"{base}.jpg", ContentFile(_jpeg(imagen, LADO_MAXIMO, 85)), save=False)
        medicion.foto_mini.save(f"{base}-mini.jpg", ContentFile(_jpeg(imagen, LADO_MINI, 80)), save=False)
    except Exception:
        logger.exception("No se pudo procesar la foto %s", medicion.foto.name)
        if archivo:
            archivo.seek(0)
