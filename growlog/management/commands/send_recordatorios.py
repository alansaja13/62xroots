from django.core.management.base import BaseCommand
from django.utils import timezone

from growlog.models import Cultivo
from growlog.push import send_push_to_all


class Command(BaseCommand):
    help = (
        "Manda un push a los usuarios suscriptos si algún cultivo activo "
        "todavía no tiene una medición de ambiente hoy."
    )

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        activos = Cultivo.objects.filter(archivado=False).exclude(estado="finalizado")
        sin_medicion = [c for c in activos if not c.mediciones.filter(timestamp__date=hoy).exists()]

        if not sin_medicion:
            self.stdout.write("Todos los cultivos activos ya tienen medición hoy — no se manda nada.")
            return

        nombres = ", ".join(c.nombre for c in sin_medicion)
        titulo = "¿Ya chequeaste las plantas?"
        cuerpo = f"Hoy no tomaste medición en: {nombres}."
        enviados = send_push_to_all(titulo, cuerpo, url="/")
        self.stdout.write(self.style.SUCCESS(f"Recordatorio enviado a {enviados} suscripción(es)."))
