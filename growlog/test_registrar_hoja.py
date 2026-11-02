"""Registrar como hoja: hora "ahora", mismo volumen, runoff, nota, planta, avisos y deshacer."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cultivo, Evento, MedicionAmbiente, MedicionPlanta, Planta, Riego, RiegoPlanta


class RegistrarHojaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("hoja")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate() - timedelta(days=10),
                                             propietario=cls.user, creado_por=cls.user)
        cls.luna = Planta.objects.create(cultivo=cls.cultivo, apodo="Luna")
        cls.sol = Planta.objects.create(cultivo=cls.cultivo, apodo="Sol")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("growlog:registrar")

    def post(self, kind, campos=None, **extra):
        datos = {"cultivo": self.cultivo.pk, "kind": kind, "observado_modo": "ahora",
                 **{f"{kind}-{k}": v for k, v in (campos or {}).items()}, **extra}
        return self.client.post(self.url, datos)

    def test_ahora_se_calcula_al_guardar(self):
        # La pantalla quedó abierta con una hora vieja: "ahora" usa la del envío.
        viejo = (timezone.localtime() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        self.post("ambiente", {"temperatura_c": "24", "humedad_relativa": "60"}, observado_en=viejo)
        medicion = MedicionAmbiente.objects.get()
        self.assertLess(timezone.now() - medicion.timestamp, timedelta(minutes=1))
        # Con "otra hora" vale la elegida.
        self.post("ambiente", {"temperatura_c": "24", "humedad_relativa": "60"}, observado_en=viejo, observado_modo="elegida")
        self.assertEqual(MedicionAmbiente.objects.order_by("timestamp").first().timestamp.hour,
                         (timezone.now() - timedelta(hours=3)).hour)

    def test_mismo_volumen_y_runoff(self):
        self.post("riego", {"mismo": "on", "volumen_todas": "375", "hubo_runoff": "on",
                            f"phrunoff-{self.luna.pk}": "6,5", f"ecrunoff-{self.sol.pk}": "9"})
        riego = Riego.objects.get()
        self.assertEqual(riego.volumen_total_ml, 750)
        self.assertTrue(riego.buscar_runoff)
        detalle = {d.planta_id: d for d in RiegoPlanta.objects.all()}
        self.assertTrue(detalle[self.luna.pk].runoff_observado)
        self.assertEqual(str(detalle[self.sol.pk].ec_runoff), "0.09")
        # Sin "Hubo runoff" los datos de drenaje no cuentan.
        self.post("riego", {"mismo": "on", "volumen_todas": "300", f"phrunoff-{self.luna.pk}": "6,5"})
        self.assertFalse(Riego.objects.latest("pk").detalle_plantas.filter(runoff_observado=True).exists())

    def test_error_de_volumen_dice_la_planta(self):
        page = self.post("riego", {f"planta-{self.luna.pk}": "0"})
        self.assertContains(page, "Revisá el riego de Luna.")
        self.assertIn(f"riego-planta-{self.luna.pk}", page.context["campos_error"])

    def test_nota_y_medicion_de_planta(self):
        self.post("nota", {"descripcion": "Hojas firmes"})
        self.assertEqual(Evento.objects.get().tipo, "nota")
        self.post("planta", {"planta_id": self.luna.pk, "altura_cm": "38,5", "nudos_count": "7", "aspecto_general": "bueno"})
        medicion = MedicionPlanta.objects.get()
        self.assertEqual((medicion.planta, str(medicion.altura_cm), medicion.fecha), (self.luna, "38.5", timezone.localdate()))
        page = self.post("planta", {"altura_cm": "10", "aspecto_general": "bueno"})
        self.assertContains(page, "Elegí la planta que mediste.")

    def test_avisos_se_confirman_uno_por_uno(self):
        page = self.post("ambiente", {"temperatura_c": "45", "humedad_relativa": "60"})
        self.assertContains(page, "poco comunes")
        clave = page.context["avisos_clave"]
        self.post("ambiente", {"temperatura_c": "45", "humedad_relativa": "60"}, aviso_ok=clave)
        self.assertEqual(MedicionAmbiente.objects.count(), 1)
        # Otro valor raro distinto vuelve a avisar aunque se mande la clave anterior.
        page = self.post("ambiente", {"temperatura_c": "46", "humedad_relativa": "60"}, aviso_ok=clave)
        self.assertContains(page, "poco comunes")
        self.assertEqual(MedicionAmbiente.objects.count(), 1)

    def test_hoja_vuelve_a_la_pantalla_y_deshace(self):
        hoja = self.client.get(self.url + f"?hoja=1&cultivo={self.cultivo.pk}", HTTP_HX_REQUEST="true",
                               HTTP_HX_CURRENT_URL="http://testserver/")
        self.assertContains(hoja, 'role="dialog"')
        self.assertNotContains(hoja, "<html")
        respuesta = self.post("nota", {"descripcion": "Algo"}, volver="/")
        self.assertRedirects(respuesta, "/", fetch_redirect_response=False)
        self.assertContains(self.client.get("/"), "Deshacer")
        self.client.post(reverse("growlog:registrar_deshacer"), {"volver": "/"})
        self.assertFalse(Evento.objects.exists())

    def test_deshacer_vence_al_minuto(self):
        self.post("nota", {"descripcion": "Algo"})
        with mock.patch("growlog.views.registrar.time.time", return_value=__import__("time").time() + 120):
            self.client.post(reverse("growlog:registrar_deshacer"))
        self.assertTrue(Evento.objects.exists())

    def test_repetir_trae_el_ultimo_riego(self):
        self.post("riego", {"mismo": "on", "volumen_todas": "400", "ph": "6,2", "ec": "140"})
        page = self.client.get(self.url + f"?cultivo={self.cultivo.pk}&kind=riego")
        ultimo = page.context["por_cultivo"][str(self.cultivo.pk)]["ultimo_riego"]
        self.assertEqual((ultimo["ph"], ultimo["ec"], ultimo["plantas"][str(self.luna.pk)]), ("6,2", "140", 400))
        self.assertContains(page, "Repetir riego del")


class PlantasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("plantas")
        hoy = timezone.localdate()
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=hoy - timedelta(days=30), propietario=cls.user)
        cls.luna = Planta.objects.create(cultivo=cls.cultivo, apodo="Luna")
        Planta.objects.create(cultivo=cls.cultivo, apodo="Vieja", estado="cosechada")
        MedicionPlanta.objects.create(planta=cls.luna, fecha=hoy - timedelta(days=4), altura_cm=30)
        MedicionPlanta.objects.create(planta=cls.luna, fecha=hoy, altura_cm=38)
        Evento.objects.create(cultivo=cls.cultivo, tipo="topping", descripcion="corte",
                              timestamp=timezone.now() - timedelta(days=2)).plantas_afectadas.add(cls.luna)

    def setUp(self):
        self.client.force_login(self.user)

    def test_lista_por_estado_con_altura_y_ritmo(self):
        url = reverse("growlog:plantas_list", args=[self.cultivo.slug])
        page = self.client.get(url)
        self.assertEqual([r["planta"].apodo for r in page.context["plantas"]], ["Luna"])
        luna = page.context["plantas"][0]
        self.assertEqual((luna["altura"], luna["ritmo"], luna["dias_sin_medir"]), (38.0, 2.0, 0))
        self.assertTrue(luna["sparkline"])
        self.assertEqual([r["planta"].apodo for r in self.client.get(url + "?ver=cosechadas").context["plantas"]], ["Vieja"])
        self.assertEqual(page.context["nav_activa"], "plantas")

    def test_ficha_con_curva_eventos_y_medir(self):
        page = self.client.get(reverse("growlog:planta_detail", args=[self.luna.pk]))
        self.assertTrue(page.context["curva_altura"])
        self.assertEqual([m["texto"] for m in page.context["marcas"]], ["topping"])
        self.assertContains(page, f"kind=planta&planta={self.luna.pk}")
        hoja = self.client.get(reverse("growlog:registrar") + f"?cultivo={self.cultivo.pk}&kind=planta&planta={self.luna.pk}")
        self.assertEqual(hoja.context["v"]["planta"]["planta_id"], str(self.luna.pk))

    def test_miniatura_al_subir_foto(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = BytesIO()
        Image.new("RGB", (3000, 2000), "green").save(buf, "JPEG")
        foto = SimpleUploadedFile("grande.jpg", buf.getvalue(), content_type="image/jpeg")
        medicion = MedicionPlanta.objects.create(planta=self.luna, foto=foto)
        self.assertTrue(medicion.foto_mini)
        with Image.open(medicion.foto_mini) as mini, Image.open(medicion.foto) as original:
            self.assertEqual(max(mini.size), 480)
            self.assertEqual(max(original.size), 2048)
        respuesta = self.client.get(reverse("protected_media", args=[medicion.foto_mini.name]))
        self.assertIn("max-age=86400", respuesta["Cache-Control"])
        self.assertNotIn("no-store", respuesta["Cache-Control"])


class FichaRegistroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import CultivoMiembro, Nutriente, NutrienteAplicado
        cls.user = User.objects.create_user("ficha")
        cls.lector = User.objects.create_user("ficha-lector")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate(), propietario=cls.user)
        CultivoMiembro.objects.create(cultivo=cls.cultivo, usuario=cls.lector, rol="lector")
        cls.luna = Planta.objects.create(cultivo=cls.cultivo, apodo="Luna")
        cls.nutriente = Nutriente.objects.create(nombre="Grow")

    def setUp(self):
        from .models import NutrienteAplicado
        self.client.force_login(self.user)
        self.riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=500, creado_por=self.user)
        RiegoPlanta.objects.create(riego=self.riego, planta=self.luna, volumen_ml=500)
        NutrienteAplicado.objects.create(riego=self.riego, nutriente=self.nutriente, dosis_g_por_litro=2)

    def test_ficha_y_lector_sin_acciones(self):
        url = reverse("growlog:registro_ficha", args=["riego", self.riego.pk])
        page = self.client.get(url)
        self.assertContains(page, "500 ml")
        self.assertContains(page, reverse("growlog:riego_editar", args=[self.riego.pk]))
        self.client.force_login(self.lector)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Sí, borrar")
        self.assertEqual(self.client.post(reverse("growlog:registro_borrar", args=["riego", self.riego.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("growlog:registro_ficha", args=["otro", 1])).status_code, 404)

    def test_borrar_y_deshacer_con_hijos(self):
        self.client.post(reverse("growlog:registro_borrar", args=["riego", self.riego.pk]), {"volver": "/"})
        self.assertFalse(Riego.objects.exists())
        self.assertContains(self.client.get("/"), "Deshacer")
        self.client.post(reverse("growlog:registro_restaurar"))
        riego = Riego.objects.get(pk=self.riego.pk)
        self.assertEqual(riego.detalle_plantas.get().volumen_ml, 500)
        self.assertEqual(riego.nutrientes_aplicados.count(), 1)

    def test_deshacer_borrado_vence(self):
        self.client.post(reverse("growlog:registro_borrar", args=["riego", self.riego.pk]))
        with mock.patch("growlog.views.registros.time.time", return_value=__import__("time").time() + 120):
            self.client.post(reverse("growlog:registro_restaurar"))
        self.assertFalse(Riego.objects.exists())

    def test_filas_abren_la_ficha(self):
        ficha = reverse("growlog:registro_ficha", args=["riego", self.riego.pk])
        for pagina in (reverse("growlog:timeline", args=[self.cultivo.slug]),
                       reverse("growlog:cultivo_detail", args=[self.cultivo.slug]),
                       reverse("growlog:planta_detail", args=[self.luna.pk])):
            self.assertContains(self.client.get(pagina), ficha)


class CorreccionUnificadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import Nutriente
        cls.user = User.objects.create_user("corrige")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate() - timedelta(days=5), propietario=cls.user)
        cls.luna = Planta.objects.create(cultivo=cls.cultivo, apodo="Luna")
        cls.sol = Planta.objects.create(cultivo=cls.cultivo, apodo="Sol")
        cls.grow = Nutriente.objects.create(nombre="Grow")

    def setUp(self):
        from .models import NutrienteAplicado
        self.client.force_login(self.user)
        self.riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=400, ph_agua="6.2", ec_solucion="1.40",
                                          timestamp=timezone.now() - timedelta(hours=2))
        RiegoPlanta.objects.create(riego=self.riego, planta=self.luna, volumen_ml=400, runoff_observado=True, ph_runoff="6.5")
        NutrienteAplicado.objects.create(riego=self.riego, nutriente=self.grow, dosis_g_por_litro=2)

    def test_precarga_lo_guardado(self):
        page = self.client.get(reverse("growlog:riego_editar", args=[self.riego.pk]))
        v = page.context["v"]["riego"]
        self.assertEqual((v[f"planta-{self.luna.pk}"], v["ph"], v["ec"], v[f"nutriente-{self.grow.pk}"], v["hubo_runoff"]),
                         ("400", "6,2", "140", "2", "on"))
        self.assertContains(page, "Guardar cambios")
        self.assertNotContains(page, 'name="kind" value="ambiente"')

    def test_corrige_plantas_dosis_y_hora(self):
        cuando = (timezone.localtime() - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
        respuesta = self.client.post(reverse("growlog:riego_editar", args=[self.riego.pk]), {
            "observado_modo": "elegida", "observado_en": cuando,
            f"riego-planta-{self.luna.pk}": "300", f"riego-planta-{self.sol.pk}": "350",
            f"riego-nutriente-{self.grow.pk}": "1,2", "riego-ph": "6,0", "riego-ec": "130"})
        self.assertRedirects(respuesta, reverse("growlog:registro_ficha", args=["riego", self.riego.pk]),
                             fetch_redirect_response=False)
        self.riego.refresh_from_db()
        self.assertEqual((self.riego.volumen_total_ml, str(self.riego.ph_agua), str(self.riego.ec_solucion)), (650, "6.00", "1.30"))
        self.assertEqual(str(self.riego.nutrientes_aplicados.get().dosis_g_por_litro), "1.200")
        self.assertEqual(timezone.localtime(self.riego.timestamp).strftime("%Y-%m-%dT%H:%M"), cuando)
        # Sin "Hubo runoff" el drenaje de Luna deja de figurar.
        self.assertFalse(self.riego.detalle_plantas.get(planta=self.luna).runoff_observado)

    def test_nota_y_seguimiento_resuelto(self):
        nota = Evento.objects.create(cultivo=self.cultivo, tipo="nota", descripcion="vieja")
        self.client.post(reverse("growlog:evento_editar", args=[nota.pk]), {"observado_modo": "ahora", "nota-descripcion": "nueva"})
        nota.refresh_from_db()
        self.assertEqual((nota.tipo, nota.descripcion), ("nota", "nueva"))
        evento = Evento.objects.create(cultivo=self.cultivo, tipo="problema", descripcion="manchas",
                                       follow_up_fecha=timezone.localdate())
        self.client.post(reverse("growlog:evento_editar", args=[evento.pk]), {
            "observado_modo": "ahora", "evento-tipo": "problema", "evento-descripcion": "manchas",
            "evento-follow_up_fecha": timezone.localdate().isoformat(), "evento-follow_up_resuelto": "on"})
        evento.refresh_from_db()
        self.assertTrue(evento.follow_up_resuelto)

    def test_valor_raro_al_corregir_pide_confirmar(self):
        url = reverse("growlog:riego_editar", args=[self.riego.pk])
        datos = {"observado_modo": "ahora", f"riego-planta-{self.luna.pk}": "400", "riego-ph": "9,5"}
        page = self.client.post(url, datos)
        self.assertContains(page, "poco comunes")
        self.riego.refresh_from_db()
        self.assertEqual(str(self.riego.ph_agua), "6.20")
        self.client.post(url, {**datos, "aviso_ok": page.context["avisos_clave"]})
        self.riego.refresh_from_db()
        self.assertEqual(str(self.riego.ph_agua), "9.50")


class FotosPlantaTests(TestCase):
    def test_fotos_de_la_planta_en_orden_y_lector(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import CultivoMiembro
        user = User.objects.create_user("fotos")
        lector = User.objects.create_user("fotos-lector")
        cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=timezone.localdate() - timedelta(days=20), propietario=user)
        CultivoMiembro.objects.create(cultivo=cultivo, usuario=lector, rol="lector")
        luna = Planta.objects.create(cultivo=cultivo, apodo="Luna")

        def foto():
            b = BytesIO(); Image.new("RGB", (40, 40), "green").save(b, "JPEG")
            return SimpleUploadedFile("f.jpg", b.getvalue(), content_type="image/jpeg")
        MedicionPlanta.objects.create(planta=luna, fecha=timezone.localdate() - timedelta(days=10), altura_cm=20, foto=foto())
        MedicionPlanta.objects.create(planta=luna, fecha=timezone.localdate(), altura_cm=35, foto=foto())
        MedicionPlanta.objects.create(planta=luna, fecha=timezone.localdate(), altura_cm=36)
        url = reverse("growlog:planta_fotos", args=[luna.pk])
        self.client.force_login(lector)
        page = self.client.get(url)
        self.assertEqual([f.dia for f in page.context["fotos"]], [20, 10])
        self.assertContains(page, "Comparar")
        self.assertContains(self.client.get(reverse("growlog:planta_detail", args=[luna.pk])), url)
