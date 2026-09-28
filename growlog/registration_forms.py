"""Contrato de entrada del registro diario (web y sincronización)."""
from django import forms

from .models import Evento, MedicionEC, Tarea


class NotasForm(forms.Form):
    notas = forms.CharField(required=False, max_length=5000)


class AmbienteForm(NotasForm):
    temperatura_c = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=60)
    humedad_relativa = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)


class ObservacionForm(forms.Form):
    tipo = forms.ChoiceField(choices=Evento.TIPO_CHOICES)
    descripcion = forms.CharField(max_length=5000)
    # plantas_afectadas viaja aparte (lista de ids, ver recibir_registro) porque
    # validar() rechaza listas en el cuerpo plano del formulario.
    follow_up_fecha = forms.DateField(required=False)
    follow_up_descripcion = forms.CharField(required=False, max_length=5000)


class SolucionForm(NotasForm):
    ph = forms.DecimalField(required=False, max_digits=4, decimal_places=2, min_value=0, max_value=14)
    ec = forms.DecimalField(required=False, max_digits=5, decimal_places=2, min_value=0)


class RiegoSolucionForm(SolucionForm):
    """Datos de la sesión de riego (fuera del desglose por planta)."""
    buscar_runoff = forms.BooleanField(required=False)


class ECForm(SolucionForm):
    tipo = forms.ChoiceField(choices=MedicionEC.TIPO_CHOICES)
    temp_agua = forms.DecimalField(required=False, max_digits=4, decimal_places=1, min_value=0, max_value=60)

    def clean(self):
        data = super().clean()
        if data.get("ph") is None and data.get("ec") is None:
            raise forms.ValidationError("Ingresá pH o EC, al menos uno de los dos.")
        return data


class PendienteForm(forms.Form):
    titulo = forms.CharField(max_length=200)
    descripcion = forms.CharField(required=False, max_length=5000)
    categoria = forms.ChoiceField(choices=Tarea.CATEGORIA_CHOICES)
    prioridad = forms.ChoiceField(choices=Tarea.PRIORIDAD_CHOICES)
    fecha_objetivo = forms.DateField(required=False)


class VolumenForm(forms.Form):
    planta_id = forms.IntegerField(min_value=1)
    volumen_ml = forms.IntegerField(min_value=1, max_value=2147483647)
    # Runoff por planta: mismos campos que RiegoPlanta, opcionales.
    runoff_observado = forms.BooleanField(required=False)
    ph_runoff = forms.DecimalField(required=False, max_digits=4, decimal_places=2, min_value=0, max_value=14)
    ec_runoff = forms.DecimalField(required=False, max_digits=5, decimal_places=2, min_value=0)
    notas = forms.CharField(required=False, max_length=5000)


class NutrienteForm(forms.Form):
    nutriente_id = forms.IntegerField(min_value=1)
    dosis_g_por_litro = forms.DecimalField(max_digits=6, decimal_places=3, min_value=0.001)
