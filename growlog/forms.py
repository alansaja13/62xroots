"""Formularios de la bitácora web."""
from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q

from .models import (
    CambioEtapaPlanta,
    CambioFotoperiodo,
    Cultivo,
    CultivoMiembro,
    Evento,
    MedicionEC,
    MedicionPlanta,
    NutrienteAplicado,
    Planta,
    Riego,
    Tarea,
)
from .services.validacion import validar_solucion

# Formato que entiende <input type="datetime-local">.
DT_FMT = "%Y-%m-%dT%H:%M"


class NuevoCultivoForm(forms.ModelForm):
    class Meta:
        model = Cultivo
        fields = ["nombre", "fecha_inicio", "estado", "sustrato", "carpa_dimensiones",
                  "lampara_modelo", "lampara_watts_reales",
                  "dias_veg_estimados", "dias_flora_estimados", "fecha_inicio_flora", "notas"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Gorilla #3", "autofocus": True}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio_flora": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "sustrato": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Coco + perlita 30%"}),
            "carpa_dimensiones": forms.TextInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 80x80x180"}),
            "lampara_modelo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Spider Farmer SF2000"}),
            "lampara_watts_reales": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "200"}),
            "dias_veg_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 30"}),
            "dias_flora_estimados": forms.NumberInput(attrs={"class": "form-control field-narrow", "placeholder": "Ej: 60"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Notas iniciales..."}),
        }


class PlantaForm(forms.ModelForm):
    class Meta:
        model = Planta
        fields = ["apodo", "strain", "tipo", "posicion_tent", "dias_flora_estimados",
                  "indica_sativa_ratio", "thc_estimado", "yield_estimado_g",
                  "yield_real_g", "estado", "notas_genetica", "archivado"]
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
            "estado": forms.Select(attrs={"class": "form-select"}),
            "notas_genetica": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "archivado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class TareaForm(forms.ModelForm):
    class Meta:
        model = Tarea
        fields = ["titulo", "descripcion", "fecha_objetivo", "prioridad", "categoria", "completada"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "fecha_objetivo": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "prioridad": forms.Select(attrs={"class": "form-select field-narrow"}),
            "categoria": forms.Select(attrs={"class": "form-select field-narrow"}),
            "completada": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["timestamp", "tipo", "descripcion", "plantas_afectadas",
                  "follow_up_fecha", "follow_up_descripcion", "follow_up_resuelto"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "plantas_afectadas": forms.CheckboxSelectMultiple(),
            "follow_up_fecha": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "follow_up_descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "follow_up_resuelto": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class RiegoForm(forms.ModelForm):
    """Datos compartidos de la sesión de riego (solución madre). El volumen y el
    runoff se cargan por planta en RiegoPlantaEntryForm — ver riego_planta_formset."""
    def clean(self):
        data = super().clean()
        validar_solucion(ph=data.get("ph_agua"), ec=data.get("ec_solucion"))
        return data

    class Meta:
        model = Riego
        fields = ["timestamp", "ph_agua", "ec_solucion", "buscar_runoff", "notas"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "ph_agua": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01", "placeholder": "6.2"}),
            "ec_solucion": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01", "placeholder": "1.8"}),
            "buscar_runoff": forms.CheckboxInput(attrs={"class": "form-check-input", "x-model": "buscarRunoff"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Notas generales de la sesión (mezcla, incidencias)..."}),
        }


class RiegoPlantaEntryForm(forms.Form):
    """Una fila del desglose de riego por planta. Se instancia una por cada
    planta activa del cultivo — ver riego_planta_formset."""
    planta_id = forms.IntegerField(widget=forms.HiddenInput())
    incluida = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "x-model": "incluida"}),
    )
    volumen_ml = forms.IntegerField(
        required=False, min_value=1, label="Volumen (ml)",
        widget=forms.NumberInput(attrs={"class": "form-control field-narrow", "inputmode": "numeric", "placeholder": "500"}),
    )
    runoff_observado = forms.BooleanField(
        required=False, label="Runoff observado",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    ph_runoff = forms.DecimalField(
        required=False, max_digits=4, decimal_places=2, label="pH runoff",
        widget=forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01", "placeholder": "6.0"}),
    )
    ec_runoff = forms.DecimalField(
        required=False, max_digits=5, decimal_places=2, label="EC runoff (mS/cm)",
        widget=forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01", "placeholder": "1.8"}),
    )
    notas = forms.CharField(
        required=False, label="Notas",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Notas de esta planta..."}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("incluida") and not cleaned.get("volumen_ml"):
            self.add_error("volumen_ml", "Requerido para las plantas incluidas en el riego.")
        if cleaned.get("incluida"):
            validar_solucion(ph=cleaned.get("ph_runoff"), ec=cleaned.get("ec_runoff"))
        return cleaned


class BaseRiegoPlantaFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        vistos = set()
        for form in self.forms:
            planta_id = form.cleaned_data.get("planta_id")
            if planta_id in vistos:
                raise forms.ValidationError("Una planta no puede aparecer dos veces en el mismo riego.")
            vistos.add(planta_id)


RiegoPlantaFormSet = forms.formset_factory(
    RiegoPlantaEntryForm, formset=BaseRiegoPlantaFormSet, extra=0,
)


def riego_planta_formset(cultivo, data=None, riego=None):
    """Arma el formset de desglose por planta, precargado con lo ya guardado si
    `riego` existe (edición) o con todo desmarcado (alta nueva)."""
    existentes = {}
    if riego is not None:
        existentes = {rp.planta_id: rp for rp in riego.detalle_plantas.all()}
    # Se riegan las plantas activas; al editar, las que ya estaban en el riego
    # (aunque hoy estén archivadas o cosechadas) siguen formando parte del registro.
    plantas = list(cultivo.plantas.filter(
        Q(archivado=False, estado="activa") | Q(pk__in=existentes),
    ).order_by("apodo"))
    initial = []
    for p in plantas:
        rp = existentes.get(p.id)
        if rp:
            initial.append({
                "planta_id": p.id, "incluida": True, "volumen_ml": rp.volumen_ml,
                "runoff_observado": rp.runoff_observado, "ph_runoff": rp.ph_runoff,
                "ec_runoff": rp.ec_runoff, "notas": rp.notas,
            })
        else:
            initial.append({"planta_id": p.id, "incluida": False})
    formset = RiegoPlantaFormSet(data, initial=initial, prefix="rp")
    return formset, plantas


def riego_planta_entries(rp_formset, plantas):
    """Extrae del formset validado las filas marcadas como incluidas."""
    planta_by_id = {p.id: p for p in plantas}
    entries = []
    for f in rp_formset.forms:
        d = f.cleaned_data
        if not d or not d.get("incluida"):
            continue
        planta = planta_by_id.get(d["planta_id"])
        if not planta:
            raise ValidationError("La planta seleccionada no pertenece a este formulario de riego.")
        entries.append({
            "planta": planta,
            "volumen_ml": d["volumen_ml"],
            "runoff_observado": d.get("runoff_observado", False),
            "ph_runoff": d.get("ph_runoff"),
            "ec_runoff": d.get("ec_runoff"),
            "notas": d.get("notas", ""),
        })
    return entries


class MedicionPlantaForm(forms.ModelForm):
    class Meta:
        model = MedicionPlanta
        fields = ["fecha", "altura_cm", "nudos_count", "ancho_canopy_cm",
                  "aspecto_general", "sintomas", "foto"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "altura_cm": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.1"}),
            "nudos_count": forms.NumberInput(attrs={"class": "form-control field-narrow"}),
            "ancho_canopy_cm": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.1"}),
            "aspecto_general": forms.Select(attrs={"class": "form-select"}),
            "sintomas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "foto": forms.FileInput(attrs={"class": "form-control"}),
        }

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if isinstance(foto, UploadedFile) and foto.size > 5 * 1024 * 1024:
            raise forms.ValidationError("La foto no puede superar los 5 MB.")
        return foto


class NutrienteAplicadoForm(forms.ModelForm):
    class Meta:
        model = NutrienteAplicado
        fields = ["nutriente", "dosis_g_por_litro"]
        widgets = {
            "nutriente": forms.Select(attrs={"class": "form-select"}),
            "dosis_g_por_litro": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.001"}),
        }


class MedicionECForm(forms.ModelForm):
    class Meta:
        model = MedicionEC
        fields = ["timestamp", "tipo", "ph", "ec", "temp_agua", "notas"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "ph": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01"}),
            "ec": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.01"}),
            "temp_agua": forms.NumberInput(attrs={"class": "form-control field-narrow", "step": "0.1"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class CambioFotoperiodoForm(forms.ModelForm):
    class Meta:
        model = CambioFotoperiodo
        fields = ["fotoperiodo", "hora_lights_on", "fecha_inicio", "notas"]
        widgets = {
            "fotoperiodo": forms.TextInput(attrs={"class": "form-control field-narrow", "placeholder": "12/12", "autofocus": True}),
            "hora_lights_on": forms.TimeInput(attrs={"class": "form-control field-narrow", "type": "time"}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ej: Inicio de floración, semana 1..."}),
        }


class CambioEtapaPlantaForm(forms.ModelForm):
    class Meta:
        model = CambioEtapaPlanta
        fields = ["etapa", "fecha_inicio", "notas"]
        widgets = {
            "etapa": forms.Select(attrs={"class": "form-select", "autofocus": True}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control field-narrow", "type": "date"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ej: Primeros pistilos visibles..."}),
        }


# ---------------------------------------------------------------------------


class CompartirCultivoForm(forms.Form):
    cultivo = forms.ModelChoiceField(queryset=Cultivo.objects.none(), label="Cultivo")
    usuario = forms.CharField(required=False, max_length=150, label="Usuario existente",
                              help_text="Dejalo vacío para crear una cuenta nueva.")
    rol = forms.ChoiceField(choices=CultivoMiembro.ROLES, initial="editor", label="Permiso")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cultivo"].queryset = Cultivo.objects.filter(propietario=usuario)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
