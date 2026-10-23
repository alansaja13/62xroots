"""Catálogo de nutrientes: compartidos, propios y los del dueño del cultivo."""
import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import DT_FMT
from .models import APIToken, Cultivo, CultivoMiembro, Nutriente, Planta, Riego
from .permissions import nutrientes_para


class NutrientesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        hoy = timezone.localdate()
        cls.admin = User.objects.create_superuser("admin-nu", password="x")
        cls.duenio = User.objects.create_user("duenio-nu")
        cls.amigo = User.objects.create_user("amigo-nu")
        cls.cultivo = Cultivo.objects.create(nombre="Carpa", fecha_inicio=hoy, propietario=cls.duenio)
        cls.planta = Planta.objects.create(cultivo=cls.cultivo, apodo="P1")
        cls.propio_amigo = Cultivo.objects.create(nombre="Carpa amigo", fecha_inicio=hoy, propietario=cls.amigo)
        Planta.objects.create(cultivo=cls.propio_amigo, apodo="A1")
        CultivoMiembro.objects.create(cultivo=cls.cultivo, usuario=cls.amigo, rol="editor")
        cls.compartido = Nutriente.objects.create(nombre="Común")
        cls.del_duenio = Nutriente.objects.create(nombre="Del dueño", propietario=cls.duenio)
        cls.del_amigo = Nutriente.objects.create(nombre="Del amigo", propietario=cls.amigo)
        cls.oculto = Nutriente.objects.create(nombre="Viejo", propietario=cls.duenio, oculto=True)

    def test_que_se_ofrece_en_cada_cultivo(self):
        # En la carpa del dueño, el amigo ve el común, los del dueño y los suyos.
        self.assertCountEqual(nutrientes_para(self.amigo, self.cultivo),
                              [self.compartido, self.del_duenio, self.del_amigo])
        # El dueño, en su propia carpa, no ve los del amigo.
        self.assertCountEqual(nutrientes_para(self.duenio, self.cultivo), [self.compartido, self.del_duenio])
        # En la carpa del amigo no aparecen los del dueño.
        self.assertCountEqual(nutrientes_para(self.amigo, self.propio_amigo), [self.compartido, self.del_amigo])

    def test_registrar_rechaza_un_nutriente_que_no_se_ofrece(self):
        self.client.force_login(self.duenio)
        response = self.client.post(reverse("growlog:registrar"), {
            "cultivo": self.cultivo.pk, "kind": "riego",
            "observado_en": (timezone.localtime() - timedelta(hours=1)).strftime(DT_FMT),
            f"riego-planta-{self.planta.pk}": "500",
            f"riego-nutriente-{self.del_duenio.pk}": "1",
            f"riego-nutriente-{self.del_amigo.pk}": "2",  # no se ofrece al dueño: se ignora
        })
        self.assertEqual(response.status_code, 302)
        aplicados = Riego.objects.get().nutrientes_aplicados.all()
        self.assertEqual([(a.nutriente, a.dosis_g_por_litro) for a in aplicados], [(self.del_duenio, Decimal("1"))])

    def test_api_lista_solo_los_visibles_y_valida_al_registrar(self):
        APIToken.objects.create(user=self.duenio, token_hash=hashlib.sha256(b"tok-nu").hexdigest())
        auth = {"HTTP_AUTHORIZATION": "Bearer tok-nu"}
        nombres = [n["nombre"] for n in self.client.get("/api/v1/nutrientes/", **auth).json()["data"]]
        self.assertCountEqual(nombres, ["Común", "Del dueño"])
        response = self.client.post(f"/api/v1/cultivos/{self.cultivo.slug}/riegos/", data=json.dumps({
            "detalle_plantas": [{"planta_uuid": str(self.planta.uuid), "volumen_ml": 500}],
            "nutrientes": [{"nutriente_id": self.del_amigo.pk, "dosis_g_por_litro": 1}],
        }), content_type="application/json", **auth)
        self.assertEqual(response.status_code, 400)

    def test_cada_uno_carga_y_edita_los_suyos(self):
        self.client.force_login(self.amigo)
        self.client.post(reverse("growlog:nutriente_crear"), {
            "nombre": "Bloom", "marca": "Marca", "etapa_recomendada": "flora",
            "dosis_recomendada_min": "1", "dosis_recomendada_max": "2", "compartido": "on"})
        nuevo = Nutriente.objects.get(nombre="Bloom")
        self.assertEqual(nuevo.propietario, self.amigo)  # un usuario común no puede compartir
        self.assertEqual(self.client.get(reverse("growlog:nutriente_editar", args=[self.compartido.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("growlog:nutriente_editar", args=[self.del_duenio.pk])).status_code, 404)

    def test_dosis_maxima_no_menor_que_minima(self):
        self.client.force_login(self.amigo)
        response = self.client.post(reverse("growlog:nutriente_crear"), {
            "nombre": "Mal", "etapa_recomendada": "veg", "dosis_recomendada_min": "3", "dosis_recomendada_max": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Nutriente.objects.filter(nombre="Mal").exists())

    def test_admin_crea_en_el_catalogo_compartido(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("growlog:nutriente_crear"), {
            "nombre": "Para todos", "etapa_recomendada": "veg", "compartido": "on"})
        self.assertIsNone(Nutriente.objects.get(nombre="Para todos").propietario)

    def test_usado_no_se_borra_pero_se_oculta(self):
        riego = Riego.objects.create(cultivo=self.cultivo, volumen_total_ml=500, creado_por=self.duenio)
        riego.nutrientes_aplicados.create(nutriente=self.del_duenio, dosis_g_por_litro=1)
        self.client.force_login(self.duenio)
        self.client.post(reverse("growlog:nutriente_eliminar", args=[self.del_duenio.pk]))
        self.assertTrue(Nutriente.objects.filter(pk=self.del_duenio.pk).exists())
        self.client.post(reverse("growlog:nutriente_ocultar", args=[self.del_duenio.pk]))
        self.del_duenio.refresh_from_db()
        self.assertTrue(self.del_duenio.oculto)
        self.assertNotIn(self.del_duenio, nutrientes_para(self.duenio, self.cultivo))
        # Sin usos sí se borra.
        self.client.post(reverse("growlog:nutriente_eliminar", args=[self.oculto.pk]))
        self.assertFalse(Nutriente.objects.filter(pk=self.oculto.pk).exists())
