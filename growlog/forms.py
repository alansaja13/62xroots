"""Formularios de la bitácora web. Los registros diarios usan los de registration_forms.py."""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.files.uploadedfile import UploadedFile

from .models import (
    ETAPA_CHOICES,
    CambioEtapaCultivo,
    CambioEtapaPlanta,
    CambioFotoperiodo,
    Cultivo,
    CultivoMiembro,
    MedicionPlanta,
    Nutriente,
    Planta,
)

# Formato que entiende <input type="datetime-local">.
DT_FMT = "%Y-%m-%dT%H:%M"
# <input type="date"> solo acepta ISO; sin esto es-ar renderiza "16/08/2026" y el campo queda vacío.
DATE_FMT = "%Y-%m-%d"


class NuevoCultivoForm(forms.ModelForm):
    class Meta:
        model = Cultivo
        fields = ["nombre", "fecha_inicio", "sustrato", "carpa_dimensiones",
                  "lampara_modelo", "lampara_watts_reales",
                  "dias_veg_estimados", "dias_flora_estimados", "notas"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Gorilla #3", "autofocus": True}),
            "fecha_inicio": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "sustrato": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Coco + perlita 30%"}),
            "carpa_dimensiones": forms.TextInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 80x80x180"}),
            "lampara_modelo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Spider Farmer SF2000"}),
            "lampara_watts_reales": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "200"}),
            "dias_veg_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 30"}),
            "dias_flora_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 60"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Notas iniciales..."}),
        }

    # Solo al crear: después la etapa se cambia desde la página de etapa del cultivo,
    # que es lo único que mantiene coherentes estado, día de flora y VPD ideal.
    etapa_inicial = forms.ChoiceField(
        choices=ETAPA_CHOICES[:5], initial="veg_temprano", label="Etapa inicial", required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["etapa_inicial"]
        else:
            # Al crear, la lámpara y la duración se piden en los primeros pasos.
            for nombre in ("lampara_modelo", "lampara_watts_reales", "dias_veg_estimados", "dias_flora_estimados"):
                del self.fields[nombre]


class DuracionCultivoForm(forms.ModelForm):
    class Meta:
        model = Cultivo
        fields = ["dias_veg_estimados", "dias_flora_estimados"]
        labels = {"dias_veg_estimados": "Días de vege", "dias_flora_estimados": "Días de flora"}
        widgets = {
            "dias_veg_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "30", "inputmode": "numeric"}),
            "dias_flora_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "60", "inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.required = True


class LuzCultivoForm(forms.ModelForm):
    class Meta:
        model = Cultivo
        fields = ["lampara_modelo", "lampara_watts_reales"]
        labels = {"lampara_modelo": "Lámpara", "lampara_watts_reales": "Watts reales"}
        widgets = {
            "lampara_modelo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Spider Farmer SF2000"}),
            "lampara_watts_reales": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "200", "inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lampara_watts_reales"].required = True


class PlantasNuevasForm(forms.Form):
    """Alta de varias plantas iguales; los apodos llegan aparte (apodo-1, apodo-2…)."""
    cantidad = forms.IntegerField(min_value=1, max_value=30, initial=1, label="Cuántas",
                                  widget=forms.NumberInput(attrs={"class": "form-control field-narrow", "inputmode": "numeric"}))
    strain = forms.CharField(max_length=120, required=False, label="Strain",
                             widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Lemon Haze"}))
    tipo = forms.ChoiceField(choices=Planta.TIPO_CHOICES, initial="foto", label="Tipo",
                             widget=forms.Select(attrs={"class": "form-select"}))


class PlantaForm(forms.ModelForm):
    class Meta:
        model = Planta
        fields = ["apodo", "strain", "tipo", "posicion_tent", "dias_flora_estimados",
                  "indica_sativa_ratio", "thc_estimado", "yield_estimado_g",
                  "yield_real_g", "fecha_corte", "peso_humedo_g", "fecha_seco", "estado", "notas_genetica", "archivado"]
        widgets = {
            "apodo": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "strain": forms.TextInput(attrs={"class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "posicion_tent": forms.Select(attrs={"class": "form-select"}),
            "dias_flora_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow"}),
            "indica_sativa_ratio": forms.TextInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 70/30"}),
            "thc_estimado": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01"}),
            "yield_estimado_g": forms.NumberInput(attrs={"class": "form-control field-narrow"}),
            "yield_real_g": forms.NumberInput(attrs={"class": "form-control field-narrow"}),
            "fecha_corte": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "peso_humedo_g": forms.NumberInput(attrs={"class": "form-control field-narrow"}),
            "fecha_seco": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "notas_genetica": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "archivado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class MedicionPlantaForm(forms.ModelForm):
    class Meta:
        model = MedicionPlanta
        fields = ["fecha", "altura_cm", "nudos_count", "ancho_canopy_cm",
                  "aspecto_general", "sintomas", "foto"]
        widgets = {
            "fecha": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "altura_cm": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.1"}),
            "nudos_count": forms.NumberInput(attrs={"class": "form-control field-narrow"}),
            "ancho_canopy_cm": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.1"}),
            "aspecto_general": forms.Select(attrs={"class": "form-select"}),
            "sintomas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "foto": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, permitir_foto=True, **kwargs):
        super().__init__(*args, **kwargs)
        # Sin el campo, un archivo enviado igual se ignora y la foto previa se conserva.
        if not permitir_foto:
            del self.fields["foto"]

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        # Se achica al guardar (services/fotos.py): alcanza con frenar archivos absurdos.
        if isinstance(foto, UploadedFile) and foto.size > 12 * 1024 * 1024:
            raise forms.ValidationError("La foto no puede superar los 12 MB.")
        return foto


class NutrienteForm(forms.ModelForm):
    compartido = forms.BooleanField(
        required=False, label="Compartido con todos",
        help_text="Lo ven todos los usuarios al registrar. Solo administradores.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Nutriente
        fields = ["nombre", "marca", "npk", "etapa_recomendada", "unidad", "dosis_recomendada_min", "dosis_recomendada_max"]
        labels = {"npk": "NPK", "etapa_recomendada": "Etapa", "dosis_recomendada_min": "Dosis mínima (por litro)",
                  "dosis_recomendada_max": "Dosis máxima (por litro)"}
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Bio·Grow", "autofocus": True}),
            "marca": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: BioBizz"}),
            "npk": forms.TextInput(attrs={"class": "form-control field-narrow", "placeholder": "4-3-6"}),
            "etapa_recomendada": forms.Select(attrs={"class": "form-select"}),
            "unidad": forms.Select(attrs={"class": "form-select field-narrow"}),
            "dosis_recomendada_min": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01"}),
            "dosis_recomendada_max": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01"}),
        }

    def __init__(self, *args, puede_compartir=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Sin elegir, queda en g/L como estaban todos los nutrientes antes.
        self.fields["unidad"].required = False
        if puede_compartir:
            self.fields["compartido"].initial = self.instance.pk is not None and self.instance.propietario_id is None
        else:
            del self.fields["compartido"]

    def clean(self):
        data = super().clean()
        minimo, maximo = data.get("dosis_recomendada_min"), data.get("dosis_recomendada_max")
        if minimo is not None and maximo is not None and minimo > maximo:
            self.add_error("dosis_recomendada_max", "La dosis máxima no puede ser menor que la mínima.")
        data["unidad"] = data.get("unidad") or "g"
        return data


class CambioFotoperiodoForm(forms.ModelForm):
    class Meta:
        model = CambioFotoperiodo
        fields = ["fotoperiodo", "hora_lights_on", "fecha_inicio", "notas"]
        widgets = {
            "fotoperiodo": forms.TextInput(attrs={"class": "form-control field-narrow", "placeholder": "12/12", "autofocus": True}),
            "hora_lights_on": forms.TimeInput(attrs={"class": "form-control field-narrow", "type": "time"}),
            "fecha_inicio": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ej: Inicio de floración, semana 1..."}),
        }


class CambioEtapaCultivoForm(forms.ModelForm):
    class Meta:
        model = CambioEtapaCultivo
        fields = ["etapa", "fecha_inicio", "notas"]
        widgets = {
            "etapa": forms.Select(attrs={"class": "form-select", "autofocus": True}),
            "fecha_inicio": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ej: Flip a 12/12, primeros pistilos..."}),
        }


class CambioEtapaPlantaForm(forms.ModelForm):
    class Meta:
        model = CambioEtapaPlanta
        fields = ["etapa", "fecha_inicio", "notas"]
        widgets = {
            "etapa": forms.Select(attrs={"class": "form-select", "autofocus": True}),
            "fecha_inicio": forms.DateInput(format=DATE_FMT, attrs={"class": "form-control field-narrow", "type": "date"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ej: Primeros pistilos visibles..."}),
        }


# ---------------------------------------------------------------------------


class CompartirCultivoForm(forms.Form):
    """Link de invitación (sin usuario) o acceso directo a una cuenta que ya existe."""
    cultivo = forms.ModelChoiceField(queryset=Cultivo.objects.none(), label="Cultivo")
    rol = forms.ChoiceField(choices=CultivoMiembro.ROLES, initial="editor", label="Permiso")
    usuario = forms.CharField(required=False, max_length=150, label="Usuario")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cultivo"].queryset = Cultivo.objects.filter(propietario=usuario)
        self.fields["cultivo"].empty_label = None
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"


class CuentaInvitadoForm(UserCreationForm):
    """La cuenta que crea quien abre un link de invitación."""

    class Meta(UserCreationForm.Meta):
        fields = ["username"]
        labels = {"username": "Usuario"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Letras, números y @ . + - _"
        self.fields["password1"].help_text = ""
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "La contraseña, otra vez"
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none", "autofocus": True})
