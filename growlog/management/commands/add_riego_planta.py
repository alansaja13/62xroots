from django.core.management.base import BaseCommand, CommandError

from growlog.models import Planta, Riego, RiegoPlanta


class Command(BaseCommand):
    help = "Agrega (o actualiza) una fila de detalle por planta a un riego existente y resincroniza volumen_total_ml."

    def add_arguments(self, parser):
        parser.add_argument("riego_id", type=int)
        parser.add_argument("apodo", type=str)
        parser.add_argument("volumen_ml", type=int)

    def handle(self, *args, **options):
        try:
            riego = Riego.objects.get(pk=options["riego_id"])
        except Riego.DoesNotExist:
            raise CommandError(f"Riego #{options['riego_id']} no existe")
        try:
            planta = riego.cultivo.plantas.get(apodo=options["apodo"])
        except Planta.DoesNotExist:
            raise CommandError(f"Planta '{options['apodo']}' no existe en el cultivo de ese riego")

        rp, created = RiegoPlanta.objects.update_or_create(
            riego=riego, planta=planta,
            defaults={"volumen_ml": options["volumen_ml"]},
        )
        riego.volumen_total_ml = sum(riego.detalle_plantas.values_list("volumen_ml", flat=True))
        riego.save(update_fields=["volumen_total_ml"])

        accion = "creada" if created else "actualizada"
        self.stdout.write(self.style.SUCCESS(
            f"Riego #{riego.id}: fila {accion} para {planta.apodo} = {rp.volumen_ml}ml "
            f"(volumen_total_ml ahora {riego.volumen_total_ml})"
        ))
