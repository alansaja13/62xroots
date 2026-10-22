from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import DT_FMT
from .models import Cultivo, CultivoMiembro, Evento, MedicionAmbiente, MedicionEC, Nutriente, Planta, Riego, Tarea


class RegistrarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('dueño-registro')
        cls.editor = User.objects.create_user('colaborador-registro')
        cls.other = User.objects.create_user('otra-cuenta')
        cls.cultivo = Cultivo.objects.create(nombre='Mi ciclo', fecha_inicio=timezone.localdate(), creado_por=cls.owner)
        cls.member = CultivoMiembro.objects.create(cultivo=cls.cultivo, usuario=cls.editor, rol='editor')
        cls.plant = Planta.objects.create(cultivo=cls.cultivo, apodo='Una planta')
        cls.other_c = Cultivo.objects.create(nombre='Ciclo ajeno', fecha_inicio=timezone.localdate(), creado_por=cls.other)
        cls.other_p = Planta.objects.create(cultivo=cls.other_c, apodo='Planta ajena')
        cls.nutrient = Nutriente.objects.create(nombre='Nutriente')

    def setUp(self):
        self.client.force_login(self.editor)
        self.url = reverse('growlog:registrar')

    def send(self, kind, campos=None, cultivo=None, observado=None, **extra):
        data = {
            'cultivo': (cultivo or self.cultivo).pk, 'kind': kind,
            'observado_en': observado or (timezone.localtime() - timedelta(hours=2)).strftime(DT_FMT),
            **{f'{kind}-{k}': v for k, v in (campos or {}).items()}, **extra,
        }
        return self.client.post(self.url, data)

    def assertGuardado(self, response, kind='ambiente', cultivo=None):
        self.assertRedirects(response, f'{self.url}?cultivo={(cultivo or self.cultivo).pk}&kind={kind}', fetch_redirect_response=False)

    def test_ambiente_con_coma_decimal_y_autoria(self):
        response = self.send('ambiente', {'temperatura_c': '24,5', 'humedad_relativa': '61', 'notas': 'Todo bien'})
        self.assertGuardado(response)
        record = MedicionAmbiente.objects.get()
        self.assertEqual((record.temperatura_c, record.creado_por, record.notas), (Decimal('24.5'), self.editor, 'Todo bien'))

    def test_datos_invalidos_vuelven_con_lo_escrito(self):
        response = self.send('ambiente', {'temperatura_c': '24', 'humedad_relativa': '101'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Humedad')
        self.assertContains(response, 'value="101"')
        self.assertFalse(MedicionAmbiente.objects.exists())

    def test_valor_raro_pide_confirmacion_sin_guardar(self):
        campos = {'temperatura_c': '4', 'humedad_relativa': '60'}
        response = self.send('ambiente', campos)
        self.assertContains(response, 'poco comunes')
        self.assertFalse(MedicionAmbiente.objects.exists())
        self.assertGuardado(self.send('ambiente', campos, confirmar='1'))
        self.assertEqual(MedicionAmbiente.objects.count(), 1)

    def test_fecha_futura_o_vacia_se_rechaza(self):
        futura = (timezone.localtime() + timedelta(hours=1)).strftime(DT_FMT)
        for observado in (futura, 'no-es-fecha'):
            response = self.send('ambiente', {'temperatura_c': '24', 'humedad_relativa': '60'}, observado=observado)
            self.assertEqual(response.status_code, 200)
        self.assertFalse(MedicionAmbiente.objects.exists())

    def test_lector_o_cultivo_ajeno_no_registra(self):
        self.assertEqual(self.send('ambiente', {'temperatura_c': '24', 'humedad_relativa': '60'}, cultivo=self.other_c).status_code, 200)
        self.member.rol = 'lector'; self.member.save()
        response = self.send('ambiente', {'temperatura_c': '24', 'humedad_relativa': '60'})
        self.assertContains(response, 'No tenés cultivos con permiso')
        self.assertFalse(MedicionAmbiente.objects.exists())

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_get_preselecciona_cultivo_y_tipo(self):
        CultivoMiembro.objects.create(cultivo=self.other_c, usuario=self.editor, rol='editor')
        response = self.client.get(f'{self.url}?cultivo={self.other_c.pk}&kind=riego')
        self.assertEqual(response.context['elegido'], self.other_c)
        self.assertEqual(response.context['tipo'], 'riego')

    def test_solo_plantas_activas_y_cultivos_editables(self):
        Planta.objects.create(cultivo=self.cultivo, apodo='Archivada', archivado=True)
        Planta.objects.create(cultivo=self.cultivo, apodo='Cosechada', estado='cosechada')
        response = self.client.get(self.url)
        self.assertEqual(response.context['cultivos'], [self.cultivo])
        self.assertEqual([f['planta'] for f in response.context['plantas_por_cultivo'][0]['plantas']], [self.plant])

    def test_observacion_ec_y_tarea(self):
        cases = [('evento', {'tipo': 'otro', 'descripcion': 'Observación, con coma'}, Evento),
                 ('ec', {'tipo': 'entrada', 'ph': '', 'ec': '0'}, MedicionEC),
                 ('tarea', {'titulo': 'Revisar', 'descripcion': 'Ventilar más', 'categoria': 'observacion', 'prioridad': 'urgente'}, Tarea)]
        for kind, campos, model in cases:
            with self.subTest(kind=kind):
                self.assertGuardado(self.send(kind, campos), kind)
                self.assertEqual(model.objects.get().creado_por, self.editor)

    def test_ec_se_tipea_por_diez_microsiemens(self):
        self.assertGuardado(self.send('ec', {'tipo': 'entrada', 'ph': '6,2', 'ec': '120'}), 'ec')
        medicion = MedicionEC.objects.get()
        self.assertEqual((medicion.ph, medicion.ec), (Decimal('6.2'), Decimal('1.2')))

    def test_ec_vacio_o_invalido_no_se_guarda(self):
        for campos in ({'ph': '', 'ec': ''}, {'ph': '15'}, {'ec': '1,8'}, {'ec': '-1'}):
            with self.subTest(campos=campos):
                self.assertEqual(self.send('ec', {'tipo': 'entrada', **campos}).status_code, 200)
        self.assertFalse(MedicionEC.objects.exists())

    def test_evento_con_plantas_afectadas_y_seguimiento(self):
        self.assertGuardado(self.send('evento', {
            'tipo': 'problema', 'descripcion': 'Hojas amarillas', f'planta-{self.plant.pk}': 'on',
            f'planta-{self.other_p.pk}': 'on',  # de otro cultivo: se ignora
            'follow_up_fecha': str(timezone.localdate() + timedelta(days=3)), 'follow_up_descripcion': 'Revisar si mejoró',
        }), 'evento')
        evento = Evento.objects.get()
        self.assertEqual(list(evento.plantas_afectadas.all()), [self.plant])
        self.assertEqual(evento.follow_up_descripcion, 'Revisar si mejoró')

    def riego(self, **extra):
        return {'ph': '6,2', 'ec': '140', 'notas': 'Riego completo', f'planta-{self.plant.pk}': '600',
                f'nutriente-{self.nutrient.pk}': '1,25', **extra}

    def test_riego_con_nutrientes(self):
        self.assertGuardado(self.send('riego', self.riego()), 'riego')
        riego = Riego.objects.get()
        self.assertEqual((riego.volumen_total_ml, riego.ph_agua, riego.ec_solucion), (600, Decimal('6.2'), Decimal('1.4')))
        self.assertEqual(riego.nutrientes_aplicados.get().dosis_g_por_litro, Decimal('1.25'))

    def test_riego_con_runoff_por_planta(self):
        campos = self.riego(buscar_runoff='on', **{
            f'runoff-{self.plant.pk}': 'on', f'phrunoff-{self.plant.pk}': '6', f'ecrunoff-{self.plant.pk}': '110',
            f'notasplanta-{self.plant.pk}': 'Drenó bien',
        })
        self.assertGuardado(self.send('riego', campos), 'riego')
        riego = Riego.objects.get()
        self.assertTrue(riego.buscar_runoff)
        detalle = riego.detalle_plantas.get()
        self.assertEqual((detalle.runoff_observado, str(detalle.ph_runoff), str(detalle.ec_runoff), detalle.notas),
                         (True, '6.00', '1.10', 'Drenó bien'))

    def test_riego_sin_runoff_ignora_datos_de_drenaje(self):
        self.assertGuardado(self.send('riego', self.riego(**{f'phrunoff-{self.plant.pk}': '6'})), 'riego')
        detalle = Riego.objects.get().detalle_plantas.get()
        self.assertFalse(detalle.runoff_observado)
        self.assertIsNone(detalle.ph_runoff)

    def test_riego_sin_volumen_o_invalido_no_deja_cabecera(self):
        for volumen in ('', '0', 'abc'):
            with self.subTest(volumen=volumen):
                self.assertEqual(self.send('riego', self.riego(**{f'planta-{self.plant.pk}': volumen})).status_code, 200)
        self.assertEqual(self.send('riego', self.riego(**{f'nutriente-{self.nutrient.pk}': '0'})).status_code, 200)
        self.assertFalse(Riego.objects.exists())

    def test_campos_de_otro_tipo_no_se_mezclan(self):
        response = self.send('tarea', {'titulo': 'Solo la tarea', 'categoria': 'observacion', 'prioridad': 'normal'},
                             **{'ambiente-temperatura_c': '24', 'ambiente-humedad_relativa': '60'})
        self.assertGuardado(response, 'tarea')
        self.assertTrue(Tarea.objects.exists())
        self.assertFalse(MedicionAmbiente.objects.exists())
