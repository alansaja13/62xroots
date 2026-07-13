from django.core.management.base import BaseCommand

from growlog.models import Evento, Riego, RiegoPlanta


class Command(BaseCommand):
    help = (
        "Completa el detalle por planta (RiegoPlanta) de riegos viejos que no lo "
        "tienen, reconstruyendo qué plantas participaron a partir de: 1) un Evento "
        "con el mismo timestamp que ya tenga plantas_afectadas marcadas, o 2) si "
        "volumen_por_planta_ml * <plantas activas del cultivo> == volumen_total_ml, "
        "asume reparto parejo entre las plantas activas. Corre en modo dry-run por "
        "defecto — usar --apply para escribir los cambios."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe los cambios. Sin este flag solo se muestra qué haría (dry-run).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        riegos = Riego.objects.filter(detalle_plantas__isnull=True).select_related("cultivo").order_by("timestamp")

        if not riegos:
            self.stdout.write(self.style.SUCCESS("No hay riegos sin detalle por planta. Nada para hacer."))
            return

        resueltos, saltados = 0, 0

        for r in riegos:
            evento = Evento.objects.filter(
                cultivo=r.cultivo, timestamp=r.timestamp
            ).prefetch_related("plantas_afectadas").first()

            plantas = None
            fuente = None
            if evento and evento.plantas_afectadas.exists():
                candidatas = list(evento.plantas_afectadas.all())
                if r.volumen_por_planta_ml and len(candidatas) * r.volumen_por_planta_ml == r.volumen_total_ml:
                    plantas, fuente = candidatas, f"evento #{evento.id} (mismo timestamp)"
                elif not r.volumen_por_planta_ml and len(candidatas) > 0:
                    plantas, fuente = candidatas, f"evento #{evento.id} (mismo timestamp, sin volumen_por_planta_ml, se reparte parejo)"

            if plantas is None:
                activas = list(r.cultivo.plantas.filter(archivado=False))
                if activas and r.volumen_por_planta_ml and len(activas) * r.volumen_por_planta_ml == r.volumen_total_ml:
                    plantas, fuente = activas, f"inferido, {len(activas)} plantas activas del cultivo hoy (sin evento de referencia)"

            if plantas is None:
                self.stdout.write(self.style.WARNING(
                    f"Riego #{r.id} ({r.timestamp:%d/%m/%Y %H:%M}, {r.volumen_total_ml}ml): "
                    f"no se pudo inferir qué plantas — revisar a mano."
                ))
                saltados += 1
                continue

            vol_por_planta = r.volumen_por_planta_ml or (r.volumen_total_ml // len(plantas))
            nombres = ", ".join(p.apodo for p in plantas)
            self.stdout.write(
                f"Riego #{r.id} ({r.timestamp:%d/%m/%Y %H:%M}, {r.volumen_total_ml}ml) -> "
                f"{len(plantas)} plantas [{nombres}] @ {vol_por_planta}ml c/u -- fuente: {fuente}"
            )
            resueltos += 1

            if apply:
                RiegoPlanta.objects.bulk_create([
                    RiegoPlanta(riego=r, planta=p, volumen_ml=vol_por_planta) for p in plantas
                ])

        self.stdout.write("")
        if apply:
            self.stdout.write(self.style.SUCCESS(f"Aplicado: {resueltos} riegos completados, {saltados} sin resolver."))
        else:
            self.stdout.write(self.style.WARNING(
                f"Dry-run: {resueltos} riegos se completarían, {saltados} necesitan revisión manual. "
                f"Corré de nuevo con --apply para escribir los cambios."
            ))
