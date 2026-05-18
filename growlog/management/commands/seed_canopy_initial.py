import math
from django.core.management.base import BaseCommand, CommandError
from growlog.models import CanopySnapshot, ColaPosicion, Cultivo, POSICION_TENT_COORDS


def _default_colas(cx, cy, n=2, radius=50):
    positions = []
    for i in range(n):
        angle = 2 * math.pi * i / n - math.pi / 2
        positions.append({
            "indice": i,
            "x": round(cx + radius * math.cos(angle) / 400, 4),
            "y": round(cy + radius * math.sin(angle) / 400, 4),
        })
    return positions


class Command(BaseCommand):
    help = "Crea el primer CanopySnapshot para un cultivo con posiciones por defecto."

    def add_arguments(self, parser):
        parser.add_argument("slug", type=str, help="Slug del cultivo")
        parser.add_argument(
            "--scrog", type=int, default=0,
            help="Porcentaje de red SCROG llena (0-100, default 0)",
        )
        parser.add_argument(
            "--colas", type=int, default=2,
            help="Número de colas por planta (1-10, default 2)",
        )
        parser.add_argument(
            "--notas", type=str, default="",
            help="Notas del snapshot inicial",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Crear snapshot incluso si ya existe uno",
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        scrog_fill_pct = max(0, min(100, options["scrog"]))
        n_colas = max(1, min(10, options["colas"]))
        notas = options["notas"]
        force = options["force"]

        try:
            cultivo = Cultivo.objects.get(slug=slug)
        except Cultivo.DoesNotExist:
            raise CommandError(f"Cultivo '{slug}' no encontrado.")

        if not force and cultivo.canopy_snapshots.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"El cultivo '{cultivo.nombre}' ya tiene snapshots. "
                    f"Usá --force para crear otro de todas formas."
                )
            )
            return

        plantas = list(cultivo.plantas.filter(archivado=False).order_by("apodo"))
        if not plantas:
            raise CommandError(f"El cultivo '{cultivo.nombre}' no tiene plantas activas.")

        snapshot = CanopySnapshot.objects.create(
            cultivo=cultivo,
            scrog_fill_pct=scrog_fill_pct,
            notas=notas,
        )

        bulk = []
        for planta in plantas:
            cx_n, cy_n = POSICION_TENT_COORDS.get(planta.posicion_tent, (0.50, 0.50))
            colas = _default_colas(cx_n * 400, cy_n * 400, n=n_colas)
            for cola in colas:
                bulk.append(ColaPosicion(
                    snapshot=snapshot,
                    planta=planta,
                    indice=cola["indice"],
                    x=cola["x"],
                    y=cola["y"],
                ))

        ColaPosicion.objects.bulk_create(bulk)

        self.stdout.write(self.style.SUCCESS(
            f"Snapshot #{snapshot.id} creado para '{cultivo.nombre}' "
            f"con {len(plantas)} plantas × {n_colas} colas = {len(bulk)} ColaPosicion."
        ))
        for p in plantas:
            cx_n, cy_n = POSICION_TENT_COORDS.get(p.posicion_tent, (0.50, 0.50))
            self.stdout.write(f"  · {p.apodo} → posicion_tent={p.posicion_tent} → ({cx_n}, {cy_n})")
