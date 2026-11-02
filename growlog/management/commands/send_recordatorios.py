from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from growlog.models import Cultivo, Perfil
from growlog.push import send_push_to_users


class Command(BaseCommand):
    help = ("Envía pendientes de cada cultivo a su propietario y colaboradores editores activos, "
            "según lo que cada uno eligió avisar en Tu cuenta.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--hora-actual", action="store_true",
            help="Avisar solo a quienes eligieron esta hora (para correrlo cada hora). Sin esto, avisa a todos.")

    def handle(self, *args, **options):
        ahora = timezone.localtime()
        hoy = ahora.date()
        perfiles = {p.usuario_id: p for p in Perfil.objects.all()}
        enviados = 0
        for cultivo in Cultivo.objects.filter(archivado=False).exclude(estado="finalizado"):
            falta_ambiente = not cultivo.mediciones.filter(timestamp__date=hoy).exists()
            eventos = cultivo.eventos.filter(follow_up_fecha__lte=hoy, follow_up_resuelto=False).count()
            tareas = cultivo.tareas.filter(fecha_objetivo__lte=hoy, completada=False).count()
            if not (falta_ambiente or eventos or tareas):
                continue
            destinatarios = set(cultivo.miembros.filter(rol="editor").values_list("usuario_id", flat=True))
            if cultivo.propietario_id:
                destinatarios.add(cultivo.propietario_id)
            # Cada persona recibe solo lo que pidió (sin perfil: todo, a las 20).
            por_mensaje = {}
            for usuario_id in destinatarios:
                perfil = perfiles.get(usuario_id) or Perfil(usuario_id=usuario_id)
                if options["hora_actual"] and perfil.hora_avisos != ahora.hour:
                    continue
                pendientes = []
                if falta_ambiente and perfil.avisar_ambiente:
                    pendientes.append("registrar ambiente de hoy")
                if eventos and perfil.avisar_seguimientos:
                    pendientes.append(f"{eventos} seguimientos pendientes")
                if tareas and perfil.avisar_tareas:
                    pendientes.append(f"{tareas} tareas pendientes")
                if pendientes:
                    por_mensaje.setdefault("; ".join(pendientes), set()).add(usuario_id)
            for texto, usuarios in por_mensaje.items():
                enviados += send_push_to_users(
                    usuarios, f"Pendientes · {cultivo.nombre}", texto,
                    url=reverse("growlog:cultivo_detail", args=[cultivo.slug]),
                )
        self.stdout.write(self.style.SUCCESS(f"Recordatorios enviados a {enviados} suscripciones."))
