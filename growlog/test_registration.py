import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import OperationalError
from django.test import Client, TestCase
from django.utils import timezone

from .models import Cultivo, CultivoMiembro, Evento, MedicionAmbiente, MedicionEC, Nutriente, Planta, RegistroRecibido, Riego, Tarea
from .registration_views import OFFLINE_COOKIE


class RegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('dueño-registro', password='test-only')
        cls.editor = User.objects.create_user('colaborador-registro', password='test-only')
        cls.other = User.objects.create_user('otra-cuenta', password='test-only')
        cls.cultivo = Cultivo.objects.create(nombre='Mi ciclo', fecha_inicio=timezone.localdate(), creado_por=cls.owner)
        cls.member = CultivoMiembro.objects.create(cultivo=cls.cultivo, usuario=cls.editor, rol='editor')
        cls.plant = Planta.objects.create(cultivo=cls.cultivo, apodo='Una planta')
        cls.other_c = Cultivo.objects.create(nombre='Ciclo ajeno', fecha_inicio=timezone.localdate(), creado_por=cls.other)
        cls.other_p = Planta.objects.create(cultivo=cls.other_c, apodo='Planta ajena')
        cls.nutrient = Nutriente.objects.create(nombre='Nutriente')

    def setUp(self):
        self.client.force_login(self.editor)

    def payload(self, tipo='ambiente', datos=None):
        return {'id': str(uuid4()), 'cultivo_id': self.cultivo.pk, 'tipo': tipo,
                'observado_en': (timezone.now() - timedelta(hours=5)).isoformat(),
                'datos': datos if datos is not None else {'temperatura_c': '24.5', 'humedad_relativa': '61', 'notas': 'Registrado sin red'}}

    def send(self, payload, account=None, client=None):
        return (client or self.client).post('/registrar/sincronizar/', data=json.dumps(payload), content_type='application/json', HTTP_X_REGISTRO_CUENTA=str(account or self.editor.pk))

    def test_recibo_y_registro_se_confirman_juntos(self):
        payload = self.payload()
        first = self.send(payload)
        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json()['repetido'])
        record = MedicionAmbiente.objects.get()
        self.assertEqual(record.creado_por, self.editor)
        self.assertEqual(record.timestamp.isoformat(), payload['observado_en'])
        self.assertEqual(RegistroRecibido.objects.get().resultado['registro_id'], record.pk)

    def test_reintentar_respuesta_perdida_no_duplica(self):
        payload = self.payload()
        first = self.send(payload).json()['data']
        for _ in range(3):
            response = self.send(payload)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['repetido'])
            self.assertEqual(response.json()['data'], first)
        self.assertEqual(MedicionAmbiente.objects.count(), 1)
        self.assertEqual(RegistroRecibido.objects.count(), 1)

    def test_uuid_reutilizado_con_datos_distintos_es_conflicto(self):
        payload = self.payload()
        self.send(payload)
        payload['datos']['temperatura_c'] = '27'
        self.assertEqual(self.send(payload).status_code, 409)
        self.assertEqual(MedicionAmbiente.objects.count(), 1)

    def test_uuid_reutilizado_en_otro_cultivo_es_conflicto(self):
        CultivoMiembro.objects.create(cultivo=self.other_c, usuario=self.editor, rol='editor')
        payload = self.payload()
        self.send(payload)
        payload['cultivo_id'] = self.other_c.pk
        self.assertEqual(self.send(payload).status_code, 409)
        self.assertFalse(self.other_c.mediciones.exists())

    def test_fallo_de_escritura_revierte_tambien_recibo(self):
        with patch('growlog.services.registro.MedicionAmbiente.save', side_effect=OperationalError('database is locked')):
            self.assertEqual(self.send(self.payload()).status_code, 503)
        self.assertFalse(RegistroRecibido.objects.exists())
        self.assertFalse(MedicionAmbiente.objects.exists())

    def test_datos_invalidos_no_dejan_recibo_ni_entrada(self):
        payload = self.payload(datos={'temperatura_c':'24', 'humedad_relativa':'101'})
        response = self.send(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('humedad_relativa', response.json()['campos'])
        self.assertFalse(RegistroRecibido.objects.exists())
        payload['datos']['humedad_relativa'] = '60'
        self.assertEqual(self.send(payload).status_code, 201)

    def test_no_acepta_autoria_o_campos_desconocidos(self):
        payload = self.payload()
        payload['datos']['creado_por'] = self.owner.pk
        self.assertEqual(self.send(payload).status_code, 400)
        self.assertFalse(RegistroRecibido.objects.exists())

    def test_rechaza_valores_y_fechas_invalidas(self):
        for field, value in [('id', 'mal'), ('id', 2), ('cultivo_id', True), ('observado_en', '2026-09-23T12:00:00'),
                             ('observado_en', None), ('observado_en', (timezone.now()+timedelta(hours=1)).isoformat()), ('tipo', 'desconocido'), ('datos', [])]:
            with self.subTest(field=field, value=value):
                payload = self.payload(); payload[field] = value
                self.assertEqual(self.send(payload).status_code, 400)
        self.assertFalse(RegistroRecibido.objects.exists())

    def test_rechaza_json_no_objeto_y_numeros_no_finitos(self):
        for raw in ('[]', 'null', '{"x":NaN}', '{', '"texto"'):
            response = self.client.post('/registrar/sincronizar/', data=raw, content_type='application/json', HTTP_X_REGISTRO_CUENTA=str(self.editor.pk))
            self.assertEqual(response.status_code, 400)

    def test_sesion_y_cuenta_requeridas(self):
        payload = self.payload()
        self.assertEqual(self.send(payload, account=self.other.pk).status_code, 409)
        self.client.logout()
        self.assertEqual(self.send(payload).status_code, 401)
        self.assertFalse(RegistroRecibido.objects.exists())

    def test_otra_cuenta_no_recibe_pendientes_ajenos(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.send(self.payload(), account=self.editor.pk).status_code, 409)
        self.assertFalse(MedicionAmbiente.objects.exists())

    def test_revocar_permiso_bloquea_incluso_reintentos_confirmados(self):
        payload = self.payload(); self.send(payload)
        self.member.delete()
        self.assertEqual(self.send(payload).status_code, 404)
        self.assertEqual(self.send(self.payload()).status_code, 404)
        self.assertEqual(MedicionAmbiente.objects.count(), 1)

    def test_lector_no_sincroniza(self):
        self.member.rol = 'lector'; self.member.save()
        self.assertEqual(self.send(self.payload()).status_code, 403)
        self.assertFalse(RegistroRecibido.objects.exists())

    def test_cultivo_ajeno_no_sincroniza(self):
        payload = self.payload(); payload['cultivo_id'] = self.other_c.pk
        self.assertEqual(self.send(payload).status_code, 404)

    def test_csrf_sigue_siendo_obligatorio(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.editor)
        self.assertEqual(self.send(self.payload(), client=client).status_code, 403)
        context = client.get('/registrar/contexto/').json()
        response = client.post('/registrar/sincronizar/', data=json.dumps(self.payload()), content_type='application/json', HTTP_X_REGISTRO_CUENTA=str(self.editor.pk), HTTP_X_CSRFTOKEN=context['csrf'])
        self.assertEqual(response.status_code, 201)

    def test_observacion_ec_y_tarea(self):
        cases = [('evento', {'tipo':'otro', 'descripcion':'Observación, con coma'}, Evento),
                 ('ec', {'tipo':'entrada', 'ph':'', 'ec':'0', 'notas':''}, MedicionEC),
                 ('tarea', {'titulo':'Revisar', 'categoria':'observacion', 'prioridad':'normal'}, Tarea)]
        for tipo, datos, model in cases:
            with self.subTest(tipo=tipo):
                payload = self.payload(tipo, datos)
                response = self.send(payload)
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(model.objects.get().creado_por, self.editor)
                self.assertEqual(self.send(payload).status_code, 200)
                self.assertEqual(model.objects.count(), 1)

    def test_ec_vacio_o_fuera_de_rango_se_conserva_como_error(self):
        for values in ({'ph':'', 'ec':''}, {'ph':'15'}, {'ec':'-1'}, {'ph':True}):
            self.assertEqual(self.send(self.payload('ec', {'tipo':'entrada', **values})).status_code, 400)
        self.assertFalse(MedicionEC.objects.exists())
        self.assertFalse(RegistroRecibido.objects.exists())

    def riego(self):
        return self.payload('riego', {'ph':'6.2', 'ec':'1.4', 'notas':'Riego completo', 'plantas':[{'planta_id':self.plant.pk, 'volumen_ml':600}],
                                     'nutrientes':[{'nutriente_id':self.nutrient.pk, 'dosis_g_por_litro':'1.25'}]})

    def test_riego_atomico_y_sin_duplicados_con_nutrientes(self):
        payload = self.riego()
        self.assertEqual(self.send(payload).status_code, 201)
        self.assertEqual(self.send(payload).status_code, 200)
        water = Riego.objects.get()
        self.assertEqual(water.volumen_total_ml, 600)
        self.assertEqual(water.detalle_plantas.count(), 1)
        self.assertEqual(water.nutrientes_aplicados.count(), 1)

    def test_riego_planta_ajena_o_archivada_no_deja_cabecera(self):
        for plant in (self.other_p, self.plant):
            self.plant.archivado = True; self.plant.save()
            payload = self.riego(); payload['datos']['plantas'][0]['planta_id'] = plant.pk
            self.assertEqual(self.send(payload).status_code, 409)
        self.assertFalse(Riego.objects.exists())
        self.assertFalse(RegistroRecibido.objects.exists())

    def test_riego_desglose_duplicado_o_vacio_no_se_guarda(self):
        for rows in ([], [{'planta_id':self.plant.pk, 'volumen_ml':100}]*2, [None], [{'planta_id':self.plant.pk, 'volumen_ml':0}]):
            payload = self.riego(); payload['datos']['plantas'] = rows
            self.assertEqual(self.send(payload).status_code, 400)
        self.assertFalse(Riego.objects.exists())
        self.assertFalse(RegistroRecibido.objects.exists())

    def test_contexto_solo_contiene_cultivos_editables(self):
        response = self.client.get('/registrar/contexto/')
        self.assertEqual([c['id'] for c in response.json()['cultivos']], [self.cultivo.pk])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(len(response.json()['desbloqueo']['clave']), 43)
        self.assertNotIn(OFFLINE_COOKIE, response.cookies)
        self.member.rol = 'lector'; self.member.save()
        self.assertEqual(self.client.get('/registrar/contexto/').json()['cultivos'], [])

    def test_clave_local_se_recupera_solo_en_la_misma_cuenta(self):
        first = self.client.get('/registrar/contexto/').json()['desbloqueo']['clave']
        self.client.cookies[OFFLINE_COOKIE] = f'{self.editor.pk}.{first}'
        self.client.post('/logout/')
        self.assertEqual(self.client.cookies[OFFLINE_COOKIE].value, '')
        self.assertEqual(self.client.get('/registrar/contexto/').status_code, 401)
        self.client.force_login(self.other)
        second = self.client.get('/registrar/contexto/').json()['desbloqueo']['clave']
        self.assertNotEqual(first, second)
        self.client.force_login(self.editor)
        recovered = self.client.get('/registrar/contexto/').json()['desbloqueo']['clave']
        self.assertEqual(first, recovered)

    def test_clave_local_no_autentica_solicitudes(self):
        key = self.client.get('/registrar/contexto/').json()['desbloqueo']['clave']
        self.client.cookies[OFFLINE_COOKIE] = f'{self.editor.pk}.{key}'
        self.client.cookies.pop('sessionid')
        self.assertEqual(self.send(self.payload()).status_code, 401)

    def test_cambio_de_cuenta_limpia_desbloqueo_previo(self):
        key = self.client.get('/registrar/contexto/').json()['desbloqueo']['clave']
        self.client.cookies[OFFLINE_COOKIE] = f'{self.editor.pk}.{key}'
        self.client.force_login(self.other)
        response = self.client.get('/')
        self.assertEqual(response.cookies[OFFLINE_COOKIE].value, '')

    def test_shell_publica_identica_sin_datos_de_cuenta(self):
        logged_in = self.client.get('/registrar/')
        self.client.logout()
        anonymous = self.client.get('/registrar/')
        self.assertEqual(logged_in.content, anonymous.content)
        self.assertNotContains(logged_in, self.editor.username)
        self.assertNotContains(logged_in, self.cultivo.nombre)
        self.assertIn('public', anonymous['Cache-Control'])
        self.assertNotIn(OFFLINE_COOKIE, anonymous.cookies)
