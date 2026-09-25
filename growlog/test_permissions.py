"""Aislamiento entre cultivos en web, API, fotos y notificaciones."""

import hashlib
import io
import json
import re
from datetime import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import models as m
from .urls import urlpatterns


class CultivoAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("propietario")
        cls.editor = User.objects.create_user("colaborador")
        cls.reader = User.objects.create_user("lector")
        cls.stranger = User.objects.create_user("ajeno", is_staff=True)
        cls.c = m.Cultivo.objects.create(nombre="Cultivo privado", fecha_inicio=timezone.localdate(), creado_por=cls.owner)
        cls.other = m.Cultivo.objects.create(nombre="Otro cultivo", fecha_inicio=timezone.localdate(), creado_por=cls.stranger)
        cls.editor_membership = m.CultivoMiembro.objects.create(cultivo=cls.c, usuario=cls.editor, rol="editor")
        cls.reader_membership = m.CultivoMiembro.objects.create(cultivo=cls.c, usuario=cls.reader, rol="lector")
        cls.plant = m.Planta.objects.create(cultivo=cls.c, apodo="P1")
        cls.other_plant = m.Planta.objects.create(cultivo=cls.other, apodo="P2")
        cls.task = m.Tarea.objects.create(cultivo=cls.c, titulo="Observar", creado_por=cls.editor)
        cls.event = m.Evento.objects.create(cultivo=cls.c, tipo="otro", descripcion="Observación privada")
        cls.water = m.Riego.objects.create(cultivo=cls.c, volumen_total_ml=100)
        cls.rp = m.RiegoPlanta.objects.create(riego=cls.water, planta=cls.plant, volumen_ml=100)
        cls.nutrient = m.Nutriente.objects.create(nombre="Nutriente")
        cls.na = m.NutrienteAplicado.objects.create(riego=cls.water, nutriente=cls.nutrient, dosis_g_por_litro=1)
        cls.mp = m.MedicionPlanta.objects.create(planta=cls.plant)
        cls.ma = m.MedicionAmbiente.objects.create(cultivo=cls.c, temperatura_c=25, humedad_relativa=55)
        cls.ec = m.MedicionEC.objects.create(cultivo=cls.c, tipo="entrada", ph=6)
        cls.cf = m.CambioFotoperiodo.objects.create(cultivo=cls.c, fotoperiodo="18/6", hora_lights_on=time(6), fecha_inicio=timezone.localdate())
        cls.stage = m.CambioEtapaPlanta.objects.create(planta=cls.plant, etapa="veg_temprano", fecha_inicio=timezone.localdate())
        cls.snap = m.CanopySnapshot.objects.create(cultivo=cls.c)
        cls.equipment = m.Equipo.objects.create(propietario=cls.owner, nombre="Lámpara", categoria="lampara", watts=100, horas_dia=18)
        cls.tariff = m.TarifaElectrica.objects.create(propietario=cls.owner, fecha_desde=timezone.localdate(), precio_kwh=12)
        cls.cost = m.CostoEnergetico.objects.create(cultivo=cls.c, equipo=cls.equipment, tarifa=cls.tariff, fecha_desde=timezone.localdate())
        cls.meter = m.LecturaMedidor.objects.create(cultivo=cls.c, fecha=timezone.localdate(), kwh_real=12)
        cls.tokens = {}
        for user in (cls.owner, cls.editor, cls.reader, cls.stranger):
            token = f"test-token-{user.username}"
            m.APIToken.objects.create(user=user, token_hash=hashlib.sha256(token.encode()).hexdigest())
            cls.tokens[user.pk] = token

    def setUp(self):
        cache.clear()

    def auth(self, user):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.tokens[user.pk]}"}

    def api_paths(self):
        ids = {
            "slug": self.c.slug, "planta_uuid": self.plant.uuid, "riego_id": self.water.pk,
            "rp_id": self.rp.pk, "na_id": self.na.pk, "evento_id": self.event.pk,
            "tarea_id": self.task.pk, "cf_id": self.cf.pk, "snapshot_id": self.snap.pk,
            "costo_id": self.cost.pk, "lectura_id": self.meter.pk,
        }
        for route in urlpatterns:
            pattern = str(route.pattern)
            if not pattern.startswith("api/") or not ("<slug:slug>" in pattern or "<uuid:planta_uuid>" in pattern):
                continue
            medicion = self.mp if "api/v1/plantas/" in pattern else self.ec if "mediciones-ec/" in pattern else self.ma
            values = {**ids, "medicion_id": medicion.pk}
            yield "/" + re.sub(r"<\w+:(\w+)>", lambda match: str(values[match[1]]), pattern)

    def web_reads(self):
        return [reverse(f"growlog:{name}", args=[self.c.slug]) for name in (
            "cultivo_detail", "cultivo_tendencias", "cultivo_tendencias_json", "timeline", "reporte", "canopy", "energia", "tareas_list",
        )] + [reverse("growlog:planta_detail", args=[self.plant.pk]), reverse("growlog:canopy_snapshot_json", args=[self.c.slug, self.snap.pk])]

    def web_writes(self):
        routes = [(name, self.c.slug) for name in (
            "quick", "quick_evento", "quick_tarea", "quick_ec", "cultivo_editar", "cultivo_marcar_flora", "cultivo_finalizar",
            "planta_crear", "tarea_crear", "evento_crear", "riego_crear", "medicion_ec_crear", "fotoperiodo_list", "canopy_guardar", "energia",
        )]
        for prefix, obj in (("planta", self.plant), ("tarea", self.task), ("evento", self.event), ("riego", self.water),
                            ("medicion_planta", self.mp), ("medicion_ec", self.ec), ("cambio_fotoperiodo", self.cf), ("cambio_etapa_planta", self.stage)):
            routes.extend([(f"{prefix}_editar", obj.pk), (f"{prefix}_eliminar", obj.pk)])
        routes.extend([
            ("tarea_completar", self.task.pk), ("tarea_descompletar", self.task.pk), ("evento_resolver_followup", self.event.pk),
            ("nutriente_aplicado_crear", self.water.pk), ("nutriente_aplicado_eliminar", self.na.pk),
            ("medicion_planta_crear", self.plant.pk), ("planta_etapa_list", self.plant.pk),
        ])
        return [reverse(f"growlog:{name}", args=[pk]) for name, pk in routes]

    def test_web_lectores_y_editores_pueden_leer_su_cultivo(self):
        for user in (self.owner, self.editor, self.reader):
            self.client.force_login(user)
            for url in self.web_reads():
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_web_staff_ajeno_no_puede_leer_ni_escribir(self):
        self.client.force_login(self.stranger)
        for url in self.web_reads():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        for url in self.web_writes():
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)

    def test_web_lector_no_puede_escribir_por_post_directo(self):
        self.client.force_login(self.reader)
        for url in self.web_writes():
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 403)

    def test_dashboard_y_api_listan_solo_cultivos_visibles(self):
        for user in (self.owner, self.editor, self.reader):
            self.client.force_login(user)
            response = self.client.get("/")
            self.assertContains(response, self.c.nombre)
            self.assertNotContains(response, self.other.nombre)
            response = self.client.get("/api/v1/cultivos/", **self.auth(user))
            self.assertEqual([item["slug"] for item in response.json()["data"]], [self.c.slug])

    def test_api_aislamiento_en_todas_las_rutas_de_cultivo(self):
        for url in self.api_paths():
            with self.subTest(url=url):
                # resolver-followup es exclusivamente POST.
                request = self.client.post if "resolver-followup" in url else self.client.get
                self.assertEqual(request(url, **self.auth(self.stranger)).status_code, 404)

    def test_api_lector_no_puede_escribir_en_ninguna_ruta(self):
        for url in self.api_paths():
            for method in ("post", "patch", "delete"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url, data="{}", content_type="application/json", **self.auth(self.reader))
                    self.assertIn(response.status_code, (403, 405))

    def test_api_colaborador_puede_leer_recursos_existentes(self):
        for url in self.api_paths():
            if "resolver-followup" in url or re.search(r"/nutrientes/\d+/$", url):
                continue
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, **self.auth(self.editor)).status_code, 200)

    def test_editor_sin_staff_registra_y_conserva_autoria(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse("growlog:quick_tarea", args=[self.c.slug]), {"titulo": "Revisar sensor", "prioridad": "normal", "categoria": "observacion"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.Tarea.objects.get(titulo="Revisar sensor").creado_por, self.editor)
        response = self.client.post(f"/api/v1/cultivos/{self.c.slug}/tareas/", data=json.dumps({"titulo": "Revisar luz"}), content_type="application/json", **self.auth(self.editor))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(m.Tarea.objects.get(titulo="Revisar luz").creado_por, self.editor)

    def test_plantas_de_otro_cultivo_no_se_pueden_vincular(self):
        response = self.client.post(f"/api/v1/cultivos/{self.c.slug}/riegos/", data=json.dumps({
            "plantas": [{"planta_uuid": str(self.other_plant.uuid), "volumen_ml": 100}],
        }), content_type="application/json", **self.auth(self.editor))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(m.Riego.objects.count(), 1)

    def test_ui_muestra_acciones_segun_rol_del_cultivo(self):
        url = reverse("growlog:cultivo_detail", args=[self.c.slug])
        quick = reverse("growlog:registrar") + f"?cultivo={self.c.pk}"
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), f'href="{quick}"')
        self.client.force_login(self.reader)
        self.assertNotContains(self.client.get(url), f'href="{quick}"')

    def test_solo_propietario_comparte_y_administra_membresias(self):
        for user in (self.editor, self.reader, self.stranger):
            self.client.force_login(user)
            response = self.client.post(reverse("growlog:invitado_crear"), {"cultivo": self.c.pk, "usuario": self.stranger.username, "rol": "editor"})
            self.assertEqual(response.status_code, 400)
            for name in ("invitado_eliminar", "invitado_rol"):
                response = self.client.post(reverse(f"growlog:{name}", args=[self.reader_membership.pk]), {"rol": "editor"})
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.c.miembros.count(), 2)

    def test_propietario_comparte_con_cuenta_existente_sin_cambiar_password(self):
        self.client.force_login(self.owner)
        old_password = self.stranger.password
        response = self.client.post(reverse("growlog:invitado_crear"), {"cultivo": self.c.pk, "usuario": self.stranger.username, "rol": "editor"})
        self.assertEqual(response.status_code, 302)
        self.stranger.refresh_from_db()
        self.assertEqual(self.stranger.password, old_password)
        self.assertEqual(self.c.miembros.get(usuario=self.stranger).rol, "editor")

    def test_cuenta_nueva_solo_tiene_acceso_al_cultivo_elegido(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("growlog:invitado_crear"), {"cultivo": self.c.pk, "rol": "editor"})
        self.assertEqual(response.status_code, 200)
        nuevo = response.context["nuevo"]
        user = User.objects.get(username=nuevo["username"])
        self.assertTrue(user.check_password(nuevo["password"]))
        self.assertFalse(user.is_staff)
        self.assertEqual(list(user.membresias_cultivo.values_list("cultivo_id", flat=True)), [self.c.pk])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotContains(self.client.get(reverse("growlog:invitados_panel")), nuevo["password"])

    def test_revocacion_bloquea_sesion_y_token_y_conserva_cuenta_y_autoria(self):
        self.client.force_login(self.editor)
        self.editor_membership.delete()
        self.assertEqual(self.client.get(reverse("growlog:cultivo_detail", args=[self.c.slug])).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/cultivos/{self.c.slug}/", **self.auth(self.editor)).status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.creado_por, self.editor)
        self.assertTrue(User.objects.filter(pk=self.editor.pk).exists())

    def test_revocar_desde_panel_no_borra_la_cuenta(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("growlog:invitado_eliminar", args=[self.editor_membership.pk])).status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.editor.pk).exists())
        self.assertFalse(self.c.miembros.filter(usuario=self.editor).exists())

    def test_degradar_a_lector_aplica_a_token_existente(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("growlog:invitado_rol", args=[self.editor_membership.pk]), {"rol": "lector"})
        response = self.client.patch(f"/api/v1/cultivos/{self.c.slug}/tareas/{self.task.pk}/", data='{"completada":true}', content_type="application/json", **self.auth(self.editor))
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertFalse(self.task.completada)

    def test_admin_reservado_a_superusuarios(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get("/admin/growlog/cultivo/").status_code, 302)
        self.stranger.is_superuser = True
        self.stranger.save(update_fields=["is_superuser"])
        self.assertEqual(self.client.get("/admin/growlog/cultivo/").status_code, 200)
        # El acceso global del administrador no se traslada a las pantallas diarias.
        self.assertEqual(self.client.get(reverse("growlog:cultivo_detail", args=[self.c.slug])).status_code, 404)

    def test_fotos_autorizadas_y_no_cacheadas(self):
        self.mp.foto.save("foto.jpg", ContentFile(b"imagen-de-prueba"))
        url = reverse("protected_media", kwargs={"path": self.mp.foto.name})
        self.client.force_login(self.reader)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"imagen-de-prueba")
        self.assertIn("no-store", response["Cache-Control"])
        self.reader_membership.delete()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/media/backups/backup.json").status_code, 404)

    def test_recursos_energeticos_aislados_y_compartidos_solo_para_lectura(self):
        for path, obj in (("equipos", self.equipment), ("tarifas", self.tariff)):
            with self.subTest(path=path):
                url = f"/api/v1/{path}/{obj.pk}/"
                self.assertEqual(self.client.get(url, **self.auth(self.stranger)).status_code, 404)
                self.assertEqual(self.client.get(f"/api/v1/{path}/", **self.auth(self.stranger)).json()["data"], [])
                self.assertEqual(self.client.get(url, **self.auth(self.editor)).status_code, 200)
                self.assertEqual(self.client.patch(url, data="{}", content_type="application/json", **self.auth(self.editor)).status_code, 403)
                self.assertEqual(self.client.delete(url, **self.auth(self.reader)).status_code, 403)

    def test_tarifa_ajena_no_cambia_los_calculos(self):
        m.TarifaElectrica.objects.create(propietario=self.stranger, fecha_desde=timezone.localdate(), precio_kwh=9999)
        response = self.client.get(f"/api/v1/cultivos/{self.c.slug}/costos/", **self.auth(self.editor))
        self.assertEqual(response.json()["data"]["tarifa_vigente"]["id"], self.tariff.pk)

    def test_no_republicar_equipo_conocido_por_otro_cultivo(self):
        m.CultivoMiembro.objects.create(cultivo=self.other, usuario=self.editor, rol="editor")
        response = self.client.post(f"/api/v1/cultivos/{self.other.slug}/costos/equipos/", data=json.dumps({"equipo_id": self.equipment.pk, "fecha_desde": timezone.localdate().isoformat()}), content_type="application/json", **self.auth(self.editor))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.other.costos_energeticos.exists())

    def test_compartir_no_expone_inventario_privado_del_propietario(self):
        hidden_equipment = m.Equipo.objects.create(propietario=self.owner, nombre="Equipo privado", categoria="lampara", watts=200, horas_dia=12)
        hidden_tariff = m.TarifaElectrica.objects.create(propietario=self.owner, fecha_desde=timezone.localdate(), precio_kwh=999)
        response = self.client.post(f"/api/v1/cultivos/{self.c.slug}/costos/equipos/", data=json.dumps({"equipo_id": hidden_equipment.pk, "fecha_desde": timezone.localdate().isoformat()}), content_type="application/json", **self.auth(self.editor))
        self.assertEqual(response.status_code, 400)
        response = self.client.get(f"/api/v1/cultivos/{self.c.slug}/costos/", **self.auth(self.editor))
        self.assertNotEqual(response.json()["data"]["tarifa_vigente"]["id"], hidden_tariff.pk)

    def test_revocacion_impide_editar_cultivo_mediante_recurso_propio(self):
        for resource in (self.equipment, self.tariff):
            resource.propietario = self.editor
            resource.save(update_fields=["propietario"])
        self.editor_membership.delete()
        for path, obj in (("equipos", self.equipment), ("tarifas", self.tariff)):
            response = self.client.patch(f"/api/v1/{path}/{obj.pk}/", data="{}", content_type="application/json", **self.auth(self.editor))
            self.assertEqual(response.status_code, 403)

    def test_borrar_equipo_no_elimina_historial_de_costos(self):
        response = self.client.delete(f"/api/v1/equipos/{self.equipment.pk}/", **self.auth(self.owner))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(m.CostoEnergetico.objects.filter(pk=self.cost.pk).exists())

    def test_recordatorios_separados_por_cultivo(self):
        with patch("growlog.management.commands.send_recordatorios.send_push_to_users", return_value=1) as send:
            self.ma.delete()
            call_command("send_recordatorios", stdout=io.StringIO())
        self.assertEqual(send.call_count, 2)
        by_url = {call.kwargs["url"]: call.args for call in send.call_args_list}
        recipients = by_url[reverse("growlog:cultivo_detail", args=[self.c.slug])][0]
        self.assertEqual(recipients, {self.owner.pk, self.editor.pk})
        self.assertNotIn(self.other.nombre, by_url[reverse("growlog:cultivo_detail", args=[self.c.slug])][1])

    @override_settings(VAPID_PRIVATE_KEY="test-key")
    def test_push_no_envia_a_cuentas_inactivas_ni_ajenas(self):
        from .push import send_push_to_users
        for user in (self.owner, self.editor, self.reader, self.stranger):
            m.PushSubscription.objects.create(user=user, endpoint=f"https://push.test/{user.pk}", p256dh="key", auth="auth")
        self.editor.is_active = False
        self.editor.save(update_fields=["is_active"])
        with patch("growlog.push.webpush") as push:
            self.assertEqual(send_push_to_users({self.owner.pk, self.editor.pk}, "Pendientes", "Texto"), 1)
        self.assertEqual(push.call_args.kwargs["subscription_info"]["endpoint"], f"https://push.test/{self.owner.pk}")

    def test_suscripciones_no_se_pueden_robar_ni_borrar_entre_cuentas(self):
        sub = m.PushSubscription.objects.create(user=self.owner, endpoint="https://push.test/owner", p256dh="key", auth="auth")
        self.client.force_login(self.stranger)
        response = self.client.post(reverse("growlog:push_subscribe"), data=json.dumps({"endpoint": sub.endpoint, "keys": {"p256dh": "otra", "auth": "otra"}}), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.client.post(reverse("growlog:push_unsubscribe"), data=json.dumps({"endpoint": sub.endpoint}), content_type="application/json")
        sub.refresh_from_db()
        self.assertEqual(sub.user, self.owner)
        self.assertEqual(sub.p256dh, "key")

    def test_paginas_privadas_indican_no_store(self):
        self.client.force_login(self.reader)
        for url in ("/", reverse("growlog:cultivo_detail", args=[self.c.slug]), reverse("growlog:invitados_panel")):
            self.assertIn("no-store", self.client.get(url)["Cache-Control"])
        self.assertIn("no-store", self.client.get("/api/v1/cultivos/", **self.auth(self.owner))["Cache-Control"])

    def test_cerrar_sesion_revoca_push_de_ese_dispositivo(self):
        self.client.force_login(self.owner)
        body = {"endpoint": "https://push.test/current", "keys": {"p256dh": "key", "auth": "auth"}}
        response = self.client.post(reverse("growlog:push_subscribe"), data=json.dumps(body), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        other_device = m.PushSubscription.objects.create(user=self.owner, endpoint="https://push.test/other", p256dh="key", auth="auth")
        self.client.post(reverse("growlog:logout"))
        self.assertFalse(m.PushSubscription.objects.filter(endpoint=body["endpoint"]).exists())
        self.assertTrue(m.PushSubscription.objects.filter(pk=other_device.pk).exists())

    def test_backup_no_se_guarda_en_media(self):
        def fake_dump(*args, **kwargs):
            kwargs["stdout"].write('[{"datos":"privados"}]')
        with patch("growlog.management.commands.backup_db.call_command", side_effect=fake_dump):
            call_command("backup_db", stdout=io.StringIO())
        _, files = storages["backups"].listdir("")
        self.assertTrue(any(name.startswith("backup_") for name in files))
        for name in files:
            self.assertFalse(storages["default"].exists(name))

    def test_usuario_puede_crear_cultivo_propio_sin_ser_staff(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse("growlog:nuevo_cultivo"), {
            "nombre": "Mi ciclo", "fecha_inicio": timezone.localdate().isoformat(), "estado": "vegetativo",
        })
        self.assertEqual(response.status_code, 302)
        nuevo = m.Cultivo.objects.get(nombre="Mi ciclo")
        self.assertEqual(nuevo.propietario, self.editor)
        self.assertEqual(nuevo.creado_por, self.editor)
