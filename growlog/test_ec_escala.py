"""EC: se carga en ×10 µS/cm (120 = 1200 µS/cm), se guarda en mS/cm y se muestra en µS/cm."""
from decimal import Decimal

from django.test import SimpleTestCase

from growlog.forms import MedicionECForm, RiegoPlantaEntryForm
from growlog.models import MedicionEC
from growlog.templatetags.ec import ec_us


class ECx10FieldTests(SimpleTestCase):
    def test_120_se_guarda_como_1_20_ms(self):
        form = RiegoPlantaEntryForm({"planta_id": 1, "incluida": "on", "volumen_ml": 500, "ec_runoff": "120"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ec_runoff"], Decimal("1.20"))

    def test_lo_guardado_se_muestra_x10_al_editar(self):
        form = MedicionECForm(instance=MedicionEC(ec=Decimal("1.85")))
        self.assertIn('value="185"', str(form["ec"]))

    def test_rechaza_decimales_y_negativos(self):
        for valor in ("1.2", "-5", "100000"):
            form = RiegoPlantaEntryForm({"planta_id": 1, "incluida": "on", "volumen_ml": 500, "ec_runoff": valor})
            self.assertFalse(form.is_valid(), valor)
            self.assertIn("ec_runoff", form.errors)

    def test_vacio_es_none(self):
        form = RiegoPlantaEntryForm({"planta_id": 1, "incluida": "on", "volumen_ml": 500, "ec_runoff": ""})
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["ec_runoff"])

    def test_filtro_muestra_microsiemens(self):
        self.assertEqual(ec_us(Decimal("1.20")), "1200")
        self.assertEqual(ec_us(Decimal("0.85")), "850")
        self.assertEqual(ec_us(None), "")
