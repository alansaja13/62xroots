"""EC: se carga en ×10 µS/cm (120 = 1200 µS/cm), se guarda en mS/cm y se muestra en µS/cm."""
from decimal import Decimal

from django.test import SimpleTestCase

from growlog.services.registro import RegistroError
from growlog.templatetags.ec import ec_us, ec_x10
from growlog.views.registrar import _numero, _x10


class EscalaECTests(SimpleTestCase):
    def test_120_se_guarda_como_1_20_ms(self):
        self.assertEqual(_numero("120", ec=True), "1.20")

    def test_lo_guardado_se_muestra_x10_al_corregir(self):
        self.assertEqual(_x10(Decimal("1.85")), "185")
        self.assertEqual(_x10(None), "")

    def test_rechaza_decimales_y_negativos(self):
        for valor in ("1.2", "-5", "1,4"):
            with self.subTest(valor=valor), self.assertRaises(RegistroError):
                _numero(valor, ec=True)

    def test_vacio_queda_vacio(self):
        self.assertEqual(_numero("", ec=True), "")

    def test_filtro_muestra_microsiemens(self):
        self.assertEqual(ec_us(Decimal("1.20")), "1200")
        self.assertEqual(ec_us(Decimal("0.85")), "850")
        self.assertEqual(ec_us(None), "")

    def test_filtro_muestra_la_escala_del_medidor(self):
        self.assertEqual(ec_x10(Decimal("1.20")), "120")
        self.assertEqual(ec_x10(None), "")
