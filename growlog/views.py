from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.urls import reverse
from django import forms

from .models import (
    Cultivo, Planta, MedicionAmbiente, Riego, NutrienteAplicado,
    Evento, MedicionPlanta, Tarea, ParametroIdeal, Nutriente,
)

_DT_FMT = "%Y-%m-%dT%H:%M"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect("growlog:dashboard")
    error = None
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
        if user:
            login(request, user)
            return redirect(request.GET.get("next") or "growlog:dashboard")
        error = "Usuario o contraseña incorrectos."
    return render(request, "growlog/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("growlog:login")


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class QuickEntryForm(forms.Form):
    temperatura_c = forms.DecimalField(
        label="Temperatura (°C)", max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "decimal", "step": "0.1", "placeholder": "24.5", "autofocus": True}),
    )
    humedad_relativa = forms.DecimalField(
        label="Humedad relativa (%)", max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "decimal", "step": "0.1", "placeholder": "60"}),
    )
    rego = forms.BooleanField(label="¿Regué hoy?", required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    volumen_total_ml = forms.IntegerField(label="Volumen total (ml)", required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "numeric", "placeholder": "3000"}))
    ph_agua = forms.DecimalField(label="pH del agua", max_digits=4, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "decimal", "step": "0.1", "placeholder": "6.2"}))
    notas = forms.CharField(label="Notas", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Observaciones rápidas..."}))


class NuevoCultivoForm(forms.ModelForm):
    class Meta:
        model = Cultivo
        fields = ["nombre", "fecha_inicio", "estado", "sustrato", "carpa_dimensiones",
                  "lampara_modelo", "lampara_watts_reales", "notas"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Gorilla #3", "autofocus": True}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "sustrato": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Coco + perlita 30%"}),
            "carpa_dimensiones": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 80x80x180"}),
            "lampara_modelo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Spider Farmer SF2000"}),
            "lampara_watts_reales": forms.NumberInput(attrs={"class": "form-control", "placeholder": "200"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Notas iniciales..."}),
        }


class PlantaForm(forms.ModelForm):
    class Meta:
        model = Planta
        fields = ["apodo", "strain", "posicion_tent", "dias_flora_estimados",
                  "indica_sativa_ratio", "thc_estimado", "yield_estimado_g",
                  "estado", "notas_genetica", "archivado"]
        widgets = {
            "apodo": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "strain": forms.TextInput(attrs={"class": "form-control"}),
            "posicion_tent": forms.Select(attrs={"class": "form-select"}),
            "dias_flora_estimados": forms.NumberInput(attrs={"class": "form-control"}),
            "indica_sativa_ratio": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 70/30"}),
            "thc_estimado": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "yield_estimado_g": forms.NumberInput(attrs={"class": "form-control"}),
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
            "fecha_objetivo": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "completada": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["timestamp", "tipo", "descripcion", "plantas_afectadas",
                  "follow_up_fecha", "follow_up_descripcion", "follow_up_resuelto"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=_DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "plantas_afectadas": forms.CheckboxSelectMultiple(),
            "follow_up_fecha": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "follow_up_descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "follow_up_resuelto": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class RiegoForm(forms.ModelForm):
    class Meta:
        model = Riego
        fields = ["timestamp", "volumen_total_ml", "volumen_por_planta_ml", "ph_agua",
                  "ec_solucion", "buscar_runoff", "runoff_observado", "notas"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=_DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "volumen_total_ml": forms.NumberInput(attrs={"class": "form-control", "autofocus": True}),
            "volumen_por_planta_ml": forms.NumberInput(attrs={"class": "form-control"}),
            "ph_agua": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ec_solucion": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "buscar_runoff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "runoff_observado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class MedicionPlantaForm(forms.ModelForm):
    class Meta:
        model = MedicionPlanta
        fields = ["fecha", "altura_cm", "nudos_count", "ancho_canopy_cm",
                  "aspecto_general", "sintomas", "foto"]
        widgets = {
            "fecha": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "altura_cm": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "nudos_count": forms.NumberInput(attrs={"class": "form-control"}),
            "ancho_canopy_cm": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "aspecto_general": forms.Select(attrs={"class": "form-select"}),
            "sintomas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "foto": forms.FileInput(attrs={"class": "form-control"}),
        }


class NutrienteAplicadoForm(forms.ModelForm):
    class Meta:
        model = NutrienteAplicado
        fields = ["nutriente", "dosis_g_por_litro"]
        widgets = {
            "nutriente": forms.Select(attrs={"class": "form-select"}),
            "dosis_g_por_litro": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        }


# ---------------------------------------------------------------------------
# Dashboard & Cultivo
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    activos = Cultivo.objects.filter(archivado=False).exclude(estado="finalizado").order_by("-fecha_inicio")
    archivados = Cultivo.objects.filter(archivado=True).order_by("-fecha_inicio")
    finalizados = Cultivo.objects.filter(estado="finalizado", archivado=False).order_by("-fecha_inicio")

    def _enrich(qs):
        result = []
        for c in qs:
            ultima = c.mediciones.first()
            semaforo = None
            if ultima:
                try:
                    param = ParametroIdeal.objects.get(etapa=c.estado)
                    semaforo = _evaluar_ambiente(ultima, param)
                except ParametroIdeal.DoesNotExist:
                    pass
            result.append({"cultivo": c, "ultima_medicion": ultima, "semaforo": semaforo,
                            "plantas_count": c.plantas.filter(estado="activa").count()})
        return result

    return render(request, "growlog/dashboard.html", {
        "activos": _enrich(activos),
        "archivados": _enrich(archivados),
        "finalizados": _enrich(finalizados),
    })


@login_required
def cultivo_detail(request, pk):
    cultivo = get_object_or_404(Cultivo, pk=pk)
    ultima_medicion = cultivo.mediciones.first()
    tareas_pendientes = cultivo.tareas.filter(completada=False).order_by("fecha_objetivo", "-prioridad")[:5]
    ultimos_registros = _build_timeline(cultivo, limit=8)
    plantas_count = cultivo.plantas.filter(estado="activa").count()
    plantas = cultivo.plantas.all()
    semaforo = None
    if ultima_medicion:
        try:
            param = ParametroIdeal.objects.get(etapa=cultivo.estado)
            semaforo = _evaluar_ambiente(ultima_medicion, param)
        except ParametroIdeal.DoesNotExist:
            pass
    return render(request, "growlog/cultivo_detail.html", {
        "cultivo": cultivo, "ultima_medicion": ultima_medicion,
        "tareas_pendientes": tareas_pendientes, "ultimos_registros": ultimos_registros,
        "semaforo": semaforo, "plantas_count": plantas_count, "plantas": plantas,
    })


@login_required
def quick_entry(request, pk):
    cultivo = get_object_or_404(Cultivo, pk=pk)
    form = QuickEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        medicion = MedicionAmbiente.objects.create(
            cultivo=cultivo, temperatura_c=d["temperatura_c"],
            humedad_relativa=d["humedad_relativa"], notas=d.get("notas", ""),
        )
        if d["rego"] and d.get("volumen_total_ml"):
            Riego.objects.create(cultivo=cultivo, volumen_total_ml=d["volumen_total_ml"], ph_agua=d.get("ph_agua"))
        if request.htmx:
            return render(request, "growlog/partials/quick_success.html", {"medicion": medicion, "rego": d["rego"]})
        messages.success(request, f"✓ Guardado — {medicion.temperatura_c}°C / {medicion.humedad_relativa}%HR / VPD {medicion.vpd} kPa")
        return redirect("growlog:quick", pk=cultivo.pk)
    return render(request, "growlog/quick.html", {"form": form, "cultivo": cultivo})


@login_required
def timeline(request, pk):
    cultivo = get_object_or_404(Cultivo, pk=pk)
    registros = _build_timeline(cultivo, limit=100)
    return render(request, "growlog/timeline.html", {"cultivo": cultivo, "registros": registros})


@login_required
def nuevo_cultivo(request):
    form = NuevoCultivoForm(request.POST or None, initial={"fecha_inicio": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        cultivo = form.save()
        messages.success(request, f"Cultivo «{cultivo.nombre}» creado. ¡A cultivar!")
        return redirect("growlog:cultivo_detail", pk=cultivo.pk)
    return render(request, "growlog/nuevo_cultivo.html", {"form": form})


@login_required
def cultivo_editar(request, pk):
    cultivo = get_object_or_404(Cultivo, pk=pk)
    form = NuevoCultivoForm(request.POST or None, instance=cultivo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cultivo actualizado.")
        return redirect("growlog:cultivo_detail", pk=pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar — {cultivo.nombre}",
        "subtitle": f"Día {cultivo.dias_desde_inicio}",
        "back_url": reverse("growlog:cultivo_detail", args=[pk]),
    })


# ---------------------------------------------------------------------------
# Planta CRUD
# ---------------------------------------------------------------------------

@login_required
def planta_crear(request, cultivo_pk):
    cultivo = get_object_or_404(Cultivo, pk=cultivo_pk)
    form = PlantaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.cultivo = cultivo
        p.save()
        messages.success(request, f"Planta «{p.apodo}» creada.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva planta",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo_pk]),
    })


@login_required
def planta_editar(request, pk):
    planta = get_object_or_404(Planta, pk=pk)
    form = PlantaForm(request.POST or None, instance=planta)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Planta actualizada.")
        return redirect("growlog:planta_detail", pk=pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar — {planta.apodo}",
        "subtitle": planta.cultivo.nombre,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
        "delete_url": reverse("growlog:planta_eliminar", args=[pk]),
    })


@login_required
def planta_eliminar(request, pk):
    planta = get_object_or_404(Planta, pk=pk)
    cultivo_pk = planta.cultivo_id
    if request.method == "POST":
        nombre = planta.apodo
        planta.delete()
        messages.success(request, f"Planta «{nombre}» eliminada.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar planta", "object_name": planta.apodo,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
    })


@login_required
def planta_detail(request, pk):
    planta = get_object_or_404(Planta, pk=pk)
    mediciones = planta.mediciones.all()
    return render(request, "growlog/planta_detail.html", {
        "planta": planta, "mediciones": mediciones,
        "cultivo": planta.cultivo,
    })


# ---------------------------------------------------------------------------
# Tarea CRUD
# ---------------------------------------------------------------------------

@login_required
def tarea_crear(request, cultivo_pk):
    cultivo = get_object_or_404(Cultivo, pk=cultivo_pk)
    form = TareaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.cultivo = cultivo
        t.save()
        messages.success(request, f"Tarea «{t.titulo}» creada.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva tarea",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo_pk]),
    })


@login_required
def tarea_editar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    form = TareaForm(request.POST or None, instance=tarea)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tarea actualizada.")
        return redirect("growlog:cultivo_detail", pk=tarea.cultivo_id)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar tarea",
        "subtitle": tarea.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[tarea.cultivo_id]),
        "delete_url": reverse("growlog:tarea_eliminar", args=[pk]),
    })


@login_required
def tarea_eliminar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    cultivo_pk = tarea.cultivo_id
    if request.method == "POST":
        tarea.delete()
        messages.success(request, "Tarea eliminada.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar tarea", "object_name": tarea.titulo,
        "back_url": reverse("growlog:tarea_editar", args=[pk]),
    })


@require_POST
@login_required
def tarea_completar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    tarea.completada = True
    tarea.completada_en = timezone.now()
    tarea.save()
    if request.htmx:
        return render(request, "growlog/partials/tarea_row.html", {"tarea": tarea})
    return redirect("growlog:cultivo_detail", pk=tarea.cultivo_id)


# ---------------------------------------------------------------------------
# Evento CRUD
# ---------------------------------------------------------------------------

@login_required
def evento_crear(request, cultivo_pk):
    cultivo = get_object_or_404(Cultivo, pk=cultivo_pk)
    initial = {"timestamp": timezone.localtime().strftime(_DT_FMT)}
    form = EventoForm(request.POST or None, initial=initial)
    form.fields["plantas_afectadas"].queryset = cultivo.plantas.all()
    if request.method == "POST" and form.is_valid():
        e = form.save(commit=False)
        e.cultivo = cultivo
        e.save()
        form.save_m2m()
        messages.success(request, "Evento registrado.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nuevo evento",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo_pk]),
    })


@login_required
def evento_editar(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    form = EventoForm(request.POST or None, instance=evento)
    form.fields["plantas_afectadas"].queryset = evento.cultivo.plantas.all()
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Evento actualizado.")
        return redirect("growlog:cultivo_detail", pk=evento.cultivo_id)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar evento",
        "subtitle": evento.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[evento.cultivo_id]),
        "delete_url": reverse("growlog:evento_eliminar", args=[pk]),
    })


@login_required
def evento_eliminar(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    cultivo_pk = evento.cultivo_id
    if request.method == "POST":
        evento.delete()
        messages.success(request, "Evento eliminado.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar evento", "object_name": str(evento),
        "back_url": reverse("growlog:evento_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
# Riego CRUD
# ---------------------------------------------------------------------------

@login_required
def riego_crear(request, cultivo_pk):
    cultivo = get_object_or_404(Cultivo, pk=cultivo_pk)
    initial = {"timestamp": timezone.localtime().strftime(_DT_FMT)}
    form = RiegoForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.cultivo = cultivo
        r.save()
        messages.success(request, "Riego registrado.")
        return redirect("growlog:riego_editar", pk=r.pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nuevo riego",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo_pk]),
    })


@login_required
def riego_editar(request, pk):
    riego = get_object_or_404(Riego, pk=pk)
    form = RiegoForm(request.POST or None, instance=riego)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Riego actualizado.")
        return redirect("growlog:riego_editar", pk=pk)
    nutrientes = riego.nutrientes_aplicados.select_related("nutriente").all()
    na_form = NutrienteAplicadoForm()
    return render(request, "growlog/riego_form.html", {
        "form": form, "riego": riego, "nutrientes": nutrientes,
        "na_form": na_form,
        "back_url": reverse("growlog:cultivo_detail", args=[riego.cultivo_id]),
        "delete_url": reverse("growlog:riego_eliminar", args=[pk]),
    })


@login_required
def riego_eliminar(request, pk):
    riego = get_object_or_404(Riego, pk=pk)
    cultivo_pk = riego.cultivo_id
    if request.method == "POST":
        riego.delete()
        messages.success(request, "Riego eliminado.")
        return redirect("growlog:cultivo_detail", pk=cultivo_pk)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar riego", "object_name": str(riego),
        "back_url": reverse("growlog:riego_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
# NutrienteAplicado CRUD
# ---------------------------------------------------------------------------

@login_required
def nutriente_aplicado_crear(request, riego_pk):
    riego = get_object_or_404(Riego, pk=riego_pk)
    form = NutrienteAplicadoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        na = form.save(commit=False)
        na.riego = riego
        na.save()
        messages.success(request, "Nutriente agregado.")
        return redirect("growlog:riego_editar", pk=riego_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Agregar nutriente",
        "subtitle": str(riego),
        "back_url": reverse("growlog:riego_editar", args=[riego_pk]),
    })


@require_POST
@login_required
def nutriente_aplicado_eliminar(request, pk):
    na = get_object_or_404(NutrienteAplicado, pk=pk)
    riego_pk = na.riego_id
    na.delete()
    messages.success(request, "Nutriente eliminado.")
    return redirect("growlog:riego_editar", pk=riego_pk)


# ---------------------------------------------------------------------------
# MedicionPlanta CRUD
# ---------------------------------------------------------------------------

@login_required
def medicion_planta_crear(request, planta_pk):
    planta = get_object_or_404(Planta, pk=planta_pk)
    form = MedicionPlantaForm(request.POST or None, request.FILES or None,
                              initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.planta = planta
        m.save()
        messages.success(request, "Medición registrada.")
        return redirect("growlog:planta_detail", pk=planta_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva medición de planta",
        "subtitle": str(planta),
        "back_url": reverse("growlog:planta_detail", args=[planta_pk]),
        "multipart": True,
    })


@login_required
def medicion_planta_editar(request, pk):
    medicion = get_object_or_404(MedicionPlanta, pk=pk)
    form = MedicionPlantaForm(request.POST or None, request.FILES or None, instance=medicion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Medición actualizada.")
        return redirect("growlog:planta_detail", pk=medicion.planta_id)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar medición",
        "subtitle": str(medicion.planta),
        "back_url": reverse("growlog:planta_detail", args=[medicion.planta_id]),
        "delete_url": reverse("growlog:medicion_planta_eliminar", args=[pk]),
        "multipart": True,
    })


@login_required
def medicion_planta_eliminar(request, pk):
    medicion = get_object_or_404(MedicionPlanta, pk=pk)
    planta_pk = medicion.planta_id
    if request.method == "POST":
        medicion.delete()
        messages.success(request, "Medición eliminada.")
        return redirect("growlog:planta_detail", pk=planta_pk)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar medición", "object_name": str(medicion),
        "back_url": reverse("growlog:planta_detail", args=[planta_pk]),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_timeline(cultivo, limit=50):
    fetch = limit * 3
    items = []
    for m in cultivo.mediciones.all()[:fetch]:
        items.append({"tipo": "medicion", "ts": m.timestamp, "obj": m, "icon": "bi-thermometer-half"})
    for r in cultivo.riegos.all()[:fetch]:
        items.append({"tipo": "riego", "ts": r.timestamp, "obj": r, "icon": "bi-droplet-fill"})
    for e in cultivo.eventos.all()[:fetch]:
        items.append({"tipo": "evento", "ts": e.timestamp, "obj": e, "icon": "bi-calendar-event"})
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:limit]


def _evaluar_ambiente(medicion, param):
    T = float(medicion.temperatura_c)
    HR = float(medicion.humedad_relativa)
    vpd = medicion.vpd

    def estado(val, mn, mx):
        if float(mn) <= val <= float(mx):
            return "ideal"
        return "alto" if val > float(mx) else "bajo"

    return {
        "temp": estado(T, param.temp_min, param.temp_max),
        "hr": estado(HR, param.hr_min, param.hr_max),
        "vpd": estado(vpd, param.vpd_min, param.vpd_max),
    }
