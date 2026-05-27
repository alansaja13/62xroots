import secrets
from functools import wraps

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django_htmx.http import HttpResponseClientRedirect
from django.templatetags.static import static as static_url
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.urls import reverse
from django import forms
from django.conf import settings


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponseForbidden(
                "<h2 style='font-family:monospace;padding:40px'>Acceso restringido — modo solo lectura.</h2>"
            )
        return view_func(request, *args, **kwargs)
    return _wrapped

from .models import (
    CambioFotoperiodo, CanopySnapshot, ColaPosicion, Cultivo, Planta,
    MedicionAmbiente, Riego, NutrienteAplicado, Evento, MedicionPlanta,
    Tarea, ParametroIdeal, Nutriente, MedicionEC, POSICION_TENT_COORDS,
)
from .utils import get_cambio_fotoperiodo_activo, calcular_luz_estado

_DT_FMT = "%Y-%m-%dT%H:%M"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("growlog:dashboard")
    error = None
    if request.method == "POST":
        ip = _get_client_ip(request)
        cache_key = f"login_failures_{ip}"
        failures = cache.get(cache_key, 0)
        max_attempts = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
        lockout_secs = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 3600)

        if failures >= max_attempts:
            error = "Demasiados intentos fallidos. Esperá 1 hora antes de reintentar."
        else:
            user = authenticate(
                request,
                username=request.POST.get("username"),
                password=request.POST.get("password"),
            )
            if user:
                cache.delete(cache_key)
                login(request, user)
                # L-3: "recordar sesión" funcional
                if not request.POST.get("remember"):
                    request.session.set_expiry(0)
                # H-3: validar next para evitar open redirect
                next_url = request.GET.get("next", "")
                if next_url and url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    return redirect(next_url)
                return redirect("growlog:dashboard")
            else:
                cache.set(cache_key, failures + 1, timeout=lockout_secs)
                error = "Usuario o contraseña incorrectos."
    return render(request, "growlog/login.html", {"error": error})


@require_POST
def logout_view(request):
    # M-3: solo POST para evitar logout forzado via GET
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
                  "lampara_modelo", "lampara_watts_reales",
                  "dias_veg_estimados", "dias_flora_estimados", "notas"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Gorilla #3", "autofocus": True}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "sustrato": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Coco + perlita 30%"}),
            "carpa_dimensiones": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: 80x80x180"}),
            "lampara_modelo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Spider Farmer SF2000"}),
            "lampara_watts_reales": forms.NumberInput(attrs={"class": "form-control", "placeholder": "200"}),
            "dias_veg_estimados": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ej: 30"}),
            "dias_flora_estimados": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ej: 60"}),
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
                  "ec_solucion", "buscar_runoff", "runoff_observado", "ph_runoff", "ec_runoff", "notas"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=_DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "volumen_total_ml": forms.NumberInput(attrs={"class": "form-control", "autofocus": True}),
            "volumen_por_planta_ml": forms.NumberInput(attrs={"class": "form-control"}),
            "ph_agua": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ec_solucion": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "buscar_runoff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "runoff_observado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ph_runoff": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ec_runoff": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
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
            "dosis_g_por_litro": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
        }


class QuickECForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=MedicionEC.TIPO_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-lg"}),
    )
    ph = forms.DecimalField(
        label="pH", max_digits=4, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "decimal", "step": "0.01", "placeholder": "6.2"}),
    )
    ec = forms.DecimalField(
        label="EC (mS/cm)", max_digits=5, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "decimal", "step": "0.01", "placeholder": "1.8"}),
    )
    temp_agua = forms.DecimalField(
        label="Temp. agua (°C)", max_digits=4, decimal_places=1, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-lg", "inputmode": "decimal", "step": "0.1", "placeholder": "20.0"}),
    )
    notas = forms.CharField(label="Notas", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Observaciones..."}))


class MedicionECForm(forms.ModelForm):
    class Meta:
        model = MedicionEC
        fields = ["timestamp", "tipo", "ph", "ec", "temp_agua", "notas"]
        widgets = {
            "timestamp": forms.DateTimeInput(format=_DT_FMT, attrs={"class": "form-control", "type": "datetime-local"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "ph": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ec": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "temp_agua": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class QuickEventoForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=Evento.TIPO_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-lg"}),
    )
    descripcion = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control", "rows": 4,
            "placeholder": "Describí qué pasó, qué observaste...",
        }),
    )


class QuickTareaForm(forms.Form):
    titulo = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "¿Qué hay que hacer?",
        }),
    )
    categoria = forms.ChoiceField(
        choices=Tarea.CATEGORIA_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    prioridad = forms.ChoiceField(
        choices=Tarea.PRIORIDAD_CHOICES,
        initial="normal",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    fecha_objetivo = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )


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
def cultivo_detail(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    ultima_medicion = cultivo.mediciones.first()
    tareas_pendientes = cultivo.tareas.filter(completada=False).order_by("fecha_objetivo", "-prioridad")[:10]
    tareas_completadas = cultivo.tareas.filter(completada=True).order_by("-completada_en")[:5]
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
    fotoperiodo_activo = get_cambio_fotoperiodo_activo(cultivo, timezone.now())
    luz_estado_actual = None
    if fotoperiodo_activo:
        luz_estado_actual = calcular_luz_estado(
            timezone.now(), fotoperiodo_activo.hora_lights_on, fotoperiodo_activo.fotoperiodo
        )
    progreso = None
    if cultivo.dias_veg_estimados and cultivo.dias_flora_estimados:
        total = cultivo.dias_veg_estimados + cultivo.dias_flora_estimados
        dias = cultivo.dias_desde_inicio
        pct = min(100, round(dias / total * 100))
        veg_pct = round(cultivo.dias_veg_estimados / total * 100, 2)
        progreso = {
            "pct": pct,
            "total": total,
            "dias": dias,
            "veg_pct": veg_pct,
            "en_flora": dias >= cultivo.dias_veg_estimados,
            "dias_veg": cultivo.dias_veg_estimados,
            "dias_flora": cultivo.dias_flora_estimados,
        }
    hoy = timezone.localdate()
    followups_pendientes = cultivo.eventos.filter(
        follow_up_fecha__isnull=False,
        follow_up_resuelto=False,
    ).order_by("follow_up_fecha")
    return render(request, "growlog/cultivo_detail.html", {
        "cultivo": cultivo, "ultima_medicion": ultima_medicion,
        "tareas_pendientes": tareas_pendientes, "tareas_completadas": tareas_completadas,
        "ultimos_registros": ultimos_registros,
        "semaforo": semaforo, "plantas_count": plantas_count, "plantas": plantas,
        "tarea_categorias": Tarea.CATEGORIA_CHOICES,
        "fotoperiodo_activo": fotoperiodo_activo,
        "luz_estado_actual": luz_estado_actual,
        "progreso": progreso,
        "followups_pendientes": followups_pendientes,
        "hoy": hoy,
    })


@login_required
@staff_required
def quick_entry(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = QuickEntryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        medicion = MedicionAmbiente.objects.create(
            cultivo=cultivo, temperatura_c=d["temperatura_c"],
            humedad_relativa=d["humedad_relativa"], notas=d.get("notas", ""),
            creado_por=request.user,
        )
        if d["rego"] and d.get("volumen_total_ml"):
            Riego.objects.create(cultivo=cultivo, volumen_total_ml=d["volumen_total_ml"],
                                 ph_agua=d.get("ph_agua"), creado_por=request.user)
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"✓ Guardado — {medicion.temperatura_c}°C / {medicion.humedad_relativa}%HR / VPD {medicion.vpd} kPa")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return render(request, "growlog/quick.html", {
        "form": form,
        "evento_form": QuickEventoForm(),
        "tarea_form": QuickTareaForm(),
        "ec_form": QuickECForm(),
        "cultivo": cultivo,
    })


@login_required
@staff_required
def quick_evento(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = QuickEventoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        evento = Evento.objects.create(
            cultivo=cultivo, tipo=d["tipo"], descripcion=d["descripcion"],
            creado_por=request.user,
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"Evento «{evento.get_tipo_display()}» registrado.")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return redirect("growlog:quick", cultivo.slug)


@login_required
@staff_required
def quick_medicion_ec(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = QuickECForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        medicion = MedicionEC.objects.create(
            cultivo=cultivo, tipo=d["tipo"],
            ph=d.get("ph"), ec=d.get("ec"), temp_agua=d.get("temp_agua"),
            notas=d.get("notas", ""),
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"Medición EC/pH registrada — {medicion.get_tipo_display()}")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return redirect("growlog:quick", cultivo.slug)


@login_required
@staff_required
def quick_tarea(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = QuickTareaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        tarea = Tarea.objects.create(
            cultivo=cultivo, titulo=d["titulo"], categoria=d["categoria"],
            prioridad=d["prioridad"], fecha_objetivo=d.get("fecha_objetivo"),
            creado_por=request.user,
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse("growlog:cultivo_detail", args=[cultivo.slug]))
        messages.success(request, f"Tarea «{tarea.titulo}» creada.")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return redirect("growlog:quick", cultivo.slug)


@login_required
def timeline(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    tipo = request.GET.get("tipo", "")
    todos = _build_timeline(cultivo, limit=200)
    VALID_TIPOS = {"medicion", "riego", "evento", "medicion_ec"}
    if tipo in VALID_TIPOS:
        registros = [r for r in todos if r["tipo"] == tipo]
    else:
        tipo = ""
        registros = todos
    counts = {t: sum(1 for r in todos if r["tipo"] == t) for t in VALID_TIPOS}
    return render(request, "growlog/timeline.html", {
        "cultivo": cultivo,
        "registros": registros,
        "tipo_activo": tipo,
        "counts": counts,
        "total": len(todos),
    })


@login_required
@staff_required
def nuevo_cultivo(request):
    form = NuevoCultivoForm(request.POST or None, initial={"fecha_inicio": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        cultivo = form.save(commit=False)
        cultivo.creado_por = request.user
        cultivo.save()
        messages.success(request, f"Cultivo «{cultivo.nombre}» creado. ¡A cultivar!")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/nuevo_cultivo.html", {"form": form})


@login_required
@staff_required
def cultivo_editar(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = NuevoCultivoForm(request.POST or None, instance=cultivo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cultivo actualizado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar — {cultivo.nombre}",
        "subtitle": f"Día {cultivo.dias_desde_inicio}",
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


# ---------------------------------------------------------------------------
# Planta CRUD
# ---------------------------------------------------------------------------

@login_required
@staff_required
def planta_crear(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = PlantaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.cultivo = cultivo
        p.creado_por = request.user
        p.save()
        messages.success(request, f"Planta «{p.apodo}» creada.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva planta",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
@staff_required
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
@staff_required
def planta_eliminar(request, pk):
    planta = get_object_or_404(Planta, pk=pk)
    cultivo = planta.cultivo
    if request.method == "POST":
        nombre = planta.apodo
        planta.delete()
        messages.success(request, f"Planta «{nombre}» eliminada.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar planta", "object_name": planta.apodo,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
    })


@login_required
def planta_detail(request, pk):
    planta = get_object_or_404(Planta, pk=pk)
    mediciones = list(planta.mediciones.all())
    fotos = [m for m in mediciones if m.foto]
    return render(request, "growlog/planta_detail.html", {
        "planta": planta, "mediciones": mediciones,
        "fotos": fotos,
        "cultivo": planta.cultivo,
    })


# ---------------------------------------------------------------------------
# Tarea CRUD
# ---------------------------------------------------------------------------

@login_required
@staff_required
def tarea_crear(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    form = TareaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.cultivo = cultivo
        t.creado_por = request.user
        t.save()
        messages.success(request, f"Tarea «{t.titulo}» creada.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva tarea",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
@staff_required
def tarea_editar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    form = TareaForm(request.POST or None, instance=tarea)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tarea actualizada.")
        return redirect("growlog:cultivo_detail", tarea.cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar tarea",
        "subtitle": tarea.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[tarea.cultivo.slug]),
        "delete_url": reverse("growlog:tarea_eliminar", args=[pk]),
    })


@login_required
@staff_required
def tarea_eliminar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    cultivo = tarea.cultivo
    if request.method == "POST":
        tarea.delete()
        messages.success(request, "Tarea eliminada.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar tarea", "object_name": tarea.titulo,
        "back_url": reverse("growlog:tarea_editar", args=[pk]),
    })


@require_POST
@login_required
@staff_required
def tarea_completar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    tarea.completada = True
    tarea.completada_en = timezone.now()
    tarea.save()
    if request.htmx:
        return render(request, "growlog/partials/tarea_completar_oob.html", {"tarea": tarea})
    return redirect("growlog:cultivo_detail", tarea.cultivo.slug)


@login_required
def tareas_list(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    qs = cultivo.tareas.all()
    categoria = request.GET.get("categoria", "")
    estado = request.GET.get("estado", "pendiente")
    if categoria:
        qs = qs.filter(categoria=categoria)
    if estado == "completada":
        qs = qs.filter(completada=True).order_by("-completada_en")
    elif estado == "todas":
        qs = qs.order_by("completada", "fecha_objetivo", "-prioridad")
    else:
        qs = qs.filter(completada=False).order_by("fecha_objetivo", "-prioridad")
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "growlog/tareas_list.html", {
        "cultivo": cultivo,
        "page_obj": page_obj,
        "categoria_filter": categoria,
        "estado_filter": estado,
        "categorias": Tarea.CATEGORIA_CHOICES,
        "today": timezone.localdate(),
    })


# ---------------------------------------------------------------------------
# Evento CRUD
# ---------------------------------------------------------------------------

@login_required
@staff_required
def evento_crear(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    initial = {"timestamp": timezone.localtime().strftime(_DT_FMT)}
    form = EventoForm(request.POST or None, initial=initial)
    form.fields["plantas_afectadas"].queryset = cultivo.plantas.all()
    if request.method == "POST" and form.is_valid():
        e = form.save(commit=False)
        e.cultivo = cultivo
        e.creado_por = request.user
        e.save()
        form.save_m2m()
        messages.success(request, "Evento registrado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nuevo evento",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
@staff_required
def evento_editar(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    form = EventoForm(request.POST or None, instance=evento)
    form.fields["plantas_afectadas"].queryset = evento.cultivo.plantas.all()
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Evento actualizado.")
        return redirect("growlog:cultivo_detail", evento.cultivo.slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar evento",
        "subtitle": evento.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[evento.cultivo.slug]),
        "delete_url": reverse("growlog:evento_eliminar", args=[pk]),
    })


@login_required
@staff_required
def evento_eliminar(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    cultivo = evento.cultivo
    if request.method == "POST":
        evento.delete()
        messages.success(request, "Evento eliminado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar evento", "object_name": str(evento),
        "back_url": reverse("growlog:evento_editar", args=[pk]),
    })


@login_required
@staff_required
@require_POST
def evento_resolver_followup(request, pk):
    evento = get_object_or_404(Evento, pk=pk)
    evento.follow_up_resuelto = True
    evento.save(update_fields=["follow_up_resuelto"])
    return HttpResponse("")


# ---------------------------------------------------------------------------
# Riego CRUD
# ---------------------------------------------------------------------------

@login_required
@staff_required
def riego_crear(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    initial = {"timestamp": timezone.localtime().strftime(_DT_FMT)}
    form = RiegoForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        r = form.save(commit=False)
        r.cultivo = cultivo
        r.creado_por = request.user
        r.save()
        messages.success(request, "Riego registrado.")
        return redirect("growlog:riego_editar", pk=r.pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nuevo riego",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[cultivo.slug]),
    })


@login_required
@staff_required
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
        "back_url": reverse("growlog:cultivo_detail", args=[riego.cultivo.slug]),
        "delete_url": reverse("growlog:riego_eliminar", args=[pk]),
    })


@login_required
@staff_required
def riego_eliminar(request, pk):
    riego = get_object_or_404(Riego, pk=pk)
    cultivo = riego.cultivo
    if request.method == "POST":
        riego.delete()
        messages.success(request, "Riego eliminado.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar riego", "object_name": str(riego),
        "back_url": reverse("growlog:riego_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
# NutrienteAplicado CRUD
# ---------------------------------------------------------------------------

@login_required
@staff_required
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
@staff_required
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
@staff_required
def medicion_planta_crear(request, planta_pk):
    planta = get_object_or_404(Planta, pk=planta_pk)
    form = MedicionPlantaForm(request.POST or None, request.FILES or None,
                              initial={"fecha": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.planta = planta
        m.creado_por = request.user
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
@staff_required
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
@staff_required
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
# MedicionEC CRUD
# ---------------------------------------------------------------------------

@login_required
@staff_required
def medicion_ec_crear(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    initial = {"timestamp": timezone.localtime().strftime(_DT_FMT)}
    form = MedicionECForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.cultivo = cultivo
        m.save()
        messages.success(request, "Medición EC/pH registrada.")
        return redirect("growlog:cultivo_detail", slug=slug)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva medición EC/pH",
        "subtitle": cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[slug]),
    })


@login_required
@staff_required
def medicion_ec_editar(request, pk):
    medicion = get_object_or_404(MedicionEC, pk=pk)
    form = MedicionECForm(request.POST or None, instance=medicion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Medición EC/pH actualizada.")
        return redirect("growlog:medicion_ec_editar", pk=pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Editar medición EC/pH",
        "subtitle": medicion.cultivo.nombre,
        "back_url": reverse("growlog:cultivo_detail", args=[medicion.cultivo.slug]),
        "delete_url": reverse("growlog:medicion_ec_eliminar", args=[pk]),
    })


@login_required
@staff_required
def medicion_ec_eliminar(request, pk):
    medicion = get_object_or_404(MedicionEC, pk=pk)
    cultivo = medicion.cultivo
    if request.method == "POST":
        medicion.delete()
        messages.success(request, "Medición EC/pH eliminada.")
        return redirect("growlog:cultivo_detail", slug=cultivo.slug)
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar medición EC/pH", "object_name": str(medicion),
        "back_url": reverse("growlog:medicion_ec_editar", args=[pk]),
    })


# ---------------------------------------------------------------------------
# Invitados
# ---------------------------------------------------------------------------

_ADJETIVOS = ["verde", "oscuro", "suave", "fresco", "lento", "rapido", "alto", "bajo",
               "denso", "claro", "largo", "nuevo", "viejo", "sabio", "fuerte", "fino"]
_SUSTANTIVOS = ["arbol", "hoja", "raiz", "flor", "tallo", "brote", "fruto", "campo",
                "tronco", "limon", "roca", "viento", "bosque", "campo", "lirio", "cedro"]


@login_required
@staff_required
def invitados_panel(request):
    invitados = User.objects.filter(is_staff=False, is_superuser=False).order_by("date_joined")
    return render(request, "growlog/invitados.html", {"invitados": invitados})


@login_required
@staff_required
@require_POST
def invitado_crear(request):
    # M-5: renderizar directo para no persistir la contraseña en la sesión
    username = f"{secrets.choice(_ADJETIVOS)}{secrets.choice(_SUSTANTIVOS)}{secrets.randbelow(90) + 10}"
    while User.objects.filter(username=username).exists():
        username = f"{secrets.choice(_ADJETIVOS)}{secrets.choice(_SUSTANTIVOS)}{secrets.randbelow(90) + 10}"
    password = secrets.token_urlsafe(10)
    User.objects.create_user(username=username, password=password, is_staff=False)
    invitados = User.objects.filter(is_staff=False, is_superuser=False).order_by("date_joined")
    return render(request, "growlog/invitados.html", {
        "invitados": invitados,
        "nuevo": {"username": username, "password": password},
    })


@login_required
@staff_required
@require_POST
def invitado_eliminar(request, pk):
    user = get_object_or_404(User, pk=pk, is_staff=False, is_superuser=False)
    user.delete()
    messages.success(request, "Invitado eliminado.")
    return redirect("growlog:invitados_panel")


# ---------------------------------------------------------------------------
# PWA — manifest + service worker
# ---------------------------------------------------------------------------

def pwa_manifest(request):
    def icon_url(name):
        return request.build_absolute_uri(static_url(f"growlog/icons/{name}"))

    data = {
        "name": "62×ROOTS GrowLog",
        "short_name": "62xROOTS",
        "description": "Terminal de cultivo indoor",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#16110b",
        "theme_color": "#16110b",
        "icons": [
            {"src": icon_url("icon-72x72.png"),   "sizes": "72x72",   "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-96x96.png"),   "sizes": "96x96",   "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-128x128.png"), "sizes": "128x128", "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-144x144.png"), "sizes": "144x144", "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-152x152.png"), "sizes": "152x152", "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-192x192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-192x192.png"), "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": icon_url("icon-384x384.png"), "sizes": "384x384", "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-512x512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": icon_url("icon-512x512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JsonResponse(data)


def pwa_service_worker(request):
    js = r"""
const SHELL = '62xroots-shell-v4';
const CDN   = '62xroots-cdn-v4';
const ALL_CACHES = [SHELL, CDN];

const CDN_URLS = [
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
  'https://unpkg.com/htmx.org@1.9.12',
  'https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(SHELL)
      .then(c => c.add('/'))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => !ALL_CACHES.includes(k)).map(k => caches.delete(k))
      ))
      .then(() => clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = e.request.url;
  if (!url.startsWith('http')) return;

  // CDN assets: cache-first (fixed versioned URLs)
  if (CDN_URLS.some(u => url.startsWith(u))) {
    e.respondWith(
      caches.match(e.request).then(cached => {
        if (cached) return cached;
        return fetch(e.request).then(res => {
          if (res.ok) caches.open(CDN).then(c => c.put(e.request, res.clone()));
          return res;
        });
      })
    );
    return;
  }

  // Django static files: stale-while-revalidate
  if (url.includes('/static/')) {
    e.respondWith(
      caches.open(SHELL).then(cache =>
        cache.match(e.request).then(cached => {
          const fresh = fetch(e.request).then(res => {
            if (res.ok) cache.put(e.request, res.clone());
            return res;
          });
          return cached || fresh;
        })
      )
    );
    return;
  }

  // Navigation: network-first, fall back to cached page or shell
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          if (res.ok) caches.open(SHELL).then(c => c.put(e.request, res.clone()));
          return res;
        })
        .catch(() =>
          caches.match(e.request).then(r => r || caches.match('/'))
        )
    );
  }
});
"""
    resp = HttpResponse(js.strip(), content_type="application/javascript; charset=utf-8")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

def error_400(request, exception=None):
    return render(request, '400.html', status=400)

def error_403(request, exception=None):
    return render(request, '403.html', status=403)

def error_404(request, exception=None):
    return render(request, '404.html', status=404)

def error_500(request):
    return render(request, '500.html', status=500)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Canopy Map
# ---------------------------------------------------------------------------

_PLANT_COLORS = ["#b1d160", "#d4923a", "#d96a3d", "#b384d8", "#79a4d4", "#f3e9d1"]


def _default_colas(cx, cy, n=2, radius=50):
    import math
    return [
        {
            "indice": i,
            "x": round(cx + radius * math.cos(2 * math.pi * i / n - math.pi / 2), 1),
            "y": round(cy + radius * math.sin(2 * math.pi * i / n - math.pi / 2), 1),
        }
        for i in range(n)
    ]


@login_required
def canopy_view(request, slug):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    plantas = list(cultivo.plantas.filter(archivado=False).order_by('apodo'))
    snapshots_qs = cultivo.canopy_snapshots.all()
    latest = snapshots_qs.first()

    colas_by_planta = {}
    if latest:
        for cp in latest.colas.select_related('planta').all():
            colas_by_planta.setdefault(cp.planta_id, []).append({
                "indice": cp.indice,
                "x": round(cp.x * 400, 1),
                "y": round(cp.y * 400, 1),
            })

    plantas_data = []
    for i, p in enumerate(plantas):
        cx_n, cy_n = POSICION_TENT_COORDS.get(p.posicion_tent, (0.50, 0.50))
        cx = round(cx_n * 400, 1)
        cy = round(cy_n * 400, 1)
        colas = colas_by_planta.get(p.id) or _default_colas(cx, cy, 2)
        plantas_data.append({
            "uuid": str(p.uuid),
            "apodo": p.apodo,
            "color": _PLANT_COLORS[i % len(_PLANT_COLORS)],
            "cx": cx,
            "cy": cy,
            "colas": colas,
        })

    snapshots_data = [
        {
            "id": s.id,
            "label": s.creado_en.strftime("%d/%m/%Y %H:%M"),
            "scrog_fill_pct": s.scrog_fill_pct,
        }
        for s in snapshots_qs
    ]

    init_data = {
        "slug": cultivo.slug,
        "watts": cultivo.lampara_watts_reales or 314,
        "plantas": plantas_data,
        "scrog_fill_pct": latest.scrog_fill_pct if latest else 0,
        "scrog_cells": list(latest.scrog_cells) if latest and latest.scrog_cells else [],
        "notas": latest.notas if latest else "",
        "currentSnapshotId": latest.id if latest else None,
        "snapshots": snapshots_data,
    }

    return render(request, "growlog/canopy.html", {
        "cultivo": cultivo,
        "init_data": init_data,
    })


@login_required
@staff_required
@require_POST
def canopy_guardar(request, slug):
    import json as _json
    cultivo = get_object_or_404(Cultivo, slug=slug)
    try:
        body = _json.loads(request.body or '{}')
    except _json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    scrog_fill_pct = body.get('scrog_fill_pct', 0)
    try:
        scrog_fill_pct = max(0, min(100, int(scrog_fill_pct)))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'scrog_fill_pct inválido'}, status=400)

    colas_raw = body.get('colas', [])
    if not isinstance(colas_raw, list):
        return JsonResponse({'ok': False, 'error': 'colas debe ser lista'}, status=400)

    plantas_qs = cultivo.plantas.filter(archivado=False)
    planta_map = {str(p.uuid): p for p in plantas_qs}

    colas_validated = []
    for item in colas_raw:
        uuid_str = str(item.get('planta_uuid', ''))
        planta = planta_map.get(uuid_str)
        if not planta:
            return JsonResponse({'ok': False, 'error': f'UUID desconocido: {uuid_str}'}, status=400)
        try:
            indice = int(item['indice'])
            x = float(item['x'])
            y = float(item['y'])
        except (KeyError, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'Cola requiere indice, x, y'}, status=400)
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return JsonResponse({'ok': False, 'error': 'x e y deben estar en [0,1]'}, status=400)
        colas_validated.append((planta, indice, x, y))

    scrog_cells_raw = body.get('scrog_cells', [])
    if isinstance(scrog_cells_raw, list):
        scrog_cells = [int(i) for i in scrog_cells_raw if 0 <= int(i) < 36]
        if scrog_cells:
            scrog_fill_pct = round(len(scrog_cells) / 36 * 100)
    else:
        scrog_cells = []

    snapshot = CanopySnapshot.objects.create(
        cultivo=cultivo,
        scrog_fill_pct=scrog_fill_pct,
        scrog_cells=scrog_cells,
        notas=str(body.get('notas', ''))[:500],
    )
    ColaPosicion.objects.bulk_create([
        ColaPosicion(snapshot=snapshot, planta=planta, indice=indice, x=x, y=y)
        for planta, indice, x, y in colas_validated
    ])

    return JsonResponse({
        'ok': True,
        'data': {
            'id': snapshot.id,
            'creado_en': snapshot.creado_en.isoformat(),
            'scrog_fill_pct': snapshot.scrog_fill_pct,
            'scrog_cells': snapshot.scrog_cells,
        }
    }, status=201)


@login_required
def canopy_snapshot_json(request, slug, snapshot_id):
    cultivo = get_object_or_404(Cultivo, slug=slug)
    try:
        snapshot = cultivo.canopy_snapshots.get(pk=snapshot_id)
    except CanopySnapshot.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'No encontrado'}, status=404)

    plantas_qs = cultivo.plantas.filter(archivado=False).order_by('apodo')
    colas_by_planta = {}
    for cp in snapshot.colas.select_related('planta').all():
        colas_by_planta.setdefault(cp.planta_id, []).append({
            "indice": cp.indice,
            "x": cp.x,
            "y": cp.y,
        })

    plantas_data = []
    for p in plantas_qs:
        plantas_data.append({
            "uuid": str(p.uuid),
            "apodo": p.apodo,
            "colas": colas_by_planta.get(p.id, []),
        })

    return JsonResponse({
        'ok': True,
        'data': {
            'id': snapshot.id,
            'creado_en': snapshot.creado_en.isoformat(),
            'scrog_fill_pct': snapshot.scrog_fill_pct,
            'scrog_cells': snapshot.scrog_cells,
            'notas': snapshot.notas,
            'plantas': plantas_data,
        }
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
    for ec in cultivo.mediciones_ec.all()[:fetch]:
        items.append({"tipo": "medicion_ec", "ts": ec.timestamp, "obj": ec, "icon": "bi-moisture"})
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
