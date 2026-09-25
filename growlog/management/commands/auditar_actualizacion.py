"""Auditoría de solo lectura, compatible con el esquema anterior a membresías."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "Revisa propietarios y migraciones sin modificar datos ni revelar credenciales"

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--fail-on-review", action="store_true")

    def handle(self, *args, **options):
        alias = options["database"]
        loader = MigrationLoader(connections[alias])
        applied = [node for node in loader.applied_migrations if node in loader.graph.nodes]
        if not any(app == "growlog" for app, _ in applied):
            raise CommandError("La base no tiene migraciones de growlog aplicadas. No se modificó nada.")
        # Modelos históricos: no consultar columnas que aún no existen en producción.
        apps = loader.project_state(applied).apps
        Cultivo = apps.get_model("growlog", "Cultivo")
        fields = {field.name for field in Cultivo._meta.fields}
        owner_field = "propietario_id" if "propietario" in fields else "creado_por_id"
        owners = dict(Cultivo.objects.using(alias).values_list("pk", owner_field))
        review = {}
        review["cultivos_sin_propietario"] = sorted(pk for pk, owner in owners.items() if owner is None)
        User = apps.get_model("auth", "User")
        inactive = set(User.objects.using(alias).filter(is_active=False).values_list("pk", flat=True))
        review["cultivos_con_propietario_inactivo"] = sorted(pk for pk, owner in owners.items() if owner in inactive)
        for name in ("Equipo", "TarifaElectrica"):
            Model = apps.get_model("growlog", name)
            if "propietario" in {field.name for field in Model._meta.fields}:
                unresolved = list(Model.objects.using(alias).filter(propietario__isnull=True).values_list("pk", flat=True))
            else:
                Costo = apps.get_model("growlog", "CostoEnergetico")
                relation = "equipo_id" if name == "Equipo" else "tarifa_id"
                linked = {}
                for resource, cultivo in Costo.objects.using(alias).values_list(relation, "cultivo_id"):
                    linked.setdefault(resource, set()).add(owners.get(cultivo))
                unresolved = [pk for pk in Model.objects.using(alias).values_list("pk", flat=True)
                              if len(linked.get(pk, set())) != 1 or None in linked.get(pk, set())]
            review[f"{name.lower()}_sin_propietario_inequivoco"] = sorted(unresolved)
        if "propietario" not in fields:
            # Las cuentas anteriores no recibirán membresías automáticamente.
            review["cuentas_activas_sin_cultivos_propios_a_revisar"] = list(
                User.objects.using(alias).filter(is_active=True).exclude(pk__in=[v for v in owners.values() if v])
                .order_by("pk").values_list("pk", flat=True))
        pending = sorted(name for app, name in loader.disk_migrations
                         if app == "growlog" and (app, name) not in loader.applied_migrations)
        report = {"solo_lectura": True, "migraciones_growlog_pendientes": pending,
                  "esquema_con_propietarios": "propietario" in fields, "revisar_ids": review,
                  "verificaciones_externas_pendientes": [
                      "Backup consistente y restauración en base separada",
                      "Privacidad real del bucket y dominios antiguos",
                      "Persistencia del almacenamiento de backups",
                      "Rama que dispara el despliegue automático",
                  ]}
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if options["fail_on_review"] and any(review.values()):
            raise CommandError("Hay datos que requieren revisión. No se modificó nada.")
