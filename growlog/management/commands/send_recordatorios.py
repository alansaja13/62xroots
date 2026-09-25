from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from growlog.models import Cultivo
from growlog.push import send_push_to_users


class Command(BaseCommand):
    help = "Envía pendientes de cada cultivo a su propietario y colaboradores editores activos."

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        enviados = 0
        for cultivo in Cultivo.objects.filter(archivado=False).exclude(estado="finalizado"):
            pendientes = []
            if not cultivo.mediciones.filter(timestamp__date=hoy).exists():
                pendientes.append("registrar ambiente de hoy")
            eventos = cultivo.eventos.filter(follow_up_fecha__lte=hoy, follow_up_resuelto=False).count()
            tareas = cultivo.tareas.filter(fecha_objetivo__lte=hoy, completada=False).count()
            if eventos:
                pendientes.append(f"{eventos} seguimientos pendientes")
            if tareas:
                pendientes.append(f"{tareas} tareas pendientes")
            if not pendientes:
                continue
            destinatarios = set(cultivo.miembros.filter(rol="editor").values_list("usuario_id", flat=True))
            if cultivo.propietario_id:
                destinatarios.add(cultivo.propietario_id)
            enviados += send_push_to_users(
                destinatarios, f"Pendientes · {cultivo.nombre}", "; ".join(pendientes),
                url=reverse("growlog:cultivo_detail", args=[cultivo.slug]),
            )
        self.stdout.write(self.style.SUCCESS(f"Recordatorios enviados a {enviados} suscripciones."))
