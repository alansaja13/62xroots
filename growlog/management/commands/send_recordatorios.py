from django.core.management.base import BaseCommand
from django.utils import timezone

from growlog.models import Cultivo, Evento, Tarea
from growlog.push import send_push_to_all


class Command(BaseCommand):
    help = (
        "Manda push a los usuarios suscriptos: cultivos sin medición hoy, "
        "follow-ups de eventos vencidos, y tareas vencidas."
    )

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        self._recordar_medicion(hoy)
        self._recordar_followups_vencidos(hoy)
        self._recordar_tareas_vencidas(hoy)

    def _recordar_medicion(self, hoy):
        activos = Cultivo.objects.filter(archivado=False).exclude(estado="finalizado")
        sin_medicion = [c for c in activos if not c.mediciones.filter(timestamp__date=hoy).exists()]

        if not sin_medicion:
            self.stdout.write("Todos los cultivos activos ya tienen medición hoy — no se manda nada.")
            return

        nombres = ", ".join(c.nombre for c in sin_medicion)
        titulo = "¿Ya chequeaste las plantas?"
        cuerpo = f"Hoy no tomaste medición en: {nombres}."
        enviados = send_push_to_all(titulo, cuerpo, url="/")
        self.stdout.write(self.style.SUCCESS(f"Recordatorio de medición enviado a {enviados} suscripción(es)."))

    def _recordar_followups_vencidos(self, hoy):
        vencidos = Evento.objects.filter(
            cultivo__archivado=False,
            follow_up_fecha__lte=hoy,
            follow_up_resuelto=False,
        )
        if not vencidos.exists():
            self.stdout.write("No hay follow-ups de eventos vencidos.")
            return

        n = vencidos.count()
        plural = "s" if n != 1 else ""
        titulo = "Follow-up pendiente"
        cuerpo = f"Tenés {n} evento{plural} con follow-up vencido sin resolver."
        enviados = send_push_to_all(titulo, cuerpo, url="/")
        self.stdout.write(self.style.SUCCESS(f"Recordatorio de follow-ups enviado a {enviados} suscripción(es)."))

    def _recordar_tareas_vencidas(self, hoy):
        vencidas = Tarea.objects.filter(
            cultivo__archivado=False,
            fecha_objetivo__lte=hoy,
            completada=False,
        )
        if not vencidas.exists():
            self.stdout.write("No hay tareas vencidas.")
            return

        n = vencidas.count()
        plural = "s" if n != 1 else ""
        titulo = "Tareas vencidas"
        cuerpo = f"Tenés {n} tarea{plural} vencida{plural} sin completar."
        enviados = send_push_to_all(titulo, cuerpo, url="/")
        self.stdout.write(self.style.SUCCESS(f"Recordatorio de tareas enviado a {enviados} suscripción(es)."))
