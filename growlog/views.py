from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django import forms

from .models import Cultivo, MedicionAmbiente, Riego, Tarea, ParametroIdeal


# ---------------------------------------------------------------------------
# Context helper
# ---------------------------------------------------------------------------

def _cultivo_activo():
    return Cultivo.objects.filter(archivado=False).exclude(estado="finalizado").first()


def _base_context():
    return {"cultivo_activo": _cultivo_activo()}


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class QuickEntryForm(forms.Form):
    temperatura_c = forms.DecimalField(
        label="Temperatura (°C)",
        max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-lg",
            "inputmode": "decimal",
            "step": "0.1",
            "placeholder": "24.5",
            "autofocus": True,
        }),
    )
    humedad_relativa = forms.DecimalField(
        label="Humedad relativa (%)",
        max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-lg",
            "inputmode": "decimal",
            "step": "0.1",
            "placeholder": "60",
        }),
    )
    rego = forms.BooleanField(
        label="¿Regué hoy?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    volumen_total_ml = forms.IntegerField(
        label="Volumen total (ml)",
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-lg",
            "inputmode": "numeric",
            "placeholder": "3000",
        }),
    )
    ph_agua = forms.DecimalField(
        label="pH del agua",
        max_digits=4, decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-lg",
            "inputmode": "decimal",
            "step": "0.1",
            "placeholder": "6.2",
        }),
    )
    notas = forms.CharField(
        label="Notas",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 2,
            "placeholder": "Observaciones rápidas...",
        }),
    )


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def dashboard(request):
    ctx = _base_context()
    cultivo = ctx["cultivo_activo"]

    if cultivo:
        ultima_medicion = cultivo.mediciones.first()
        tareas_pendientes = cultivo.tareas.filter(completada=False).order_by("fecha_objetivo", "-prioridad")[:5]
        ultimos_registros = _build_timeline(cultivo, limit=5)

        semaforo = None
        if ultima_medicion:
            try:
                param = ParametroIdeal.objects.get(etapa=cultivo.estado)
                semaforo = _evaluar_ambiente(ultima_medicion, param)
            except ParametroIdeal.DoesNotExist:
                pass

        ctx.update({
            "cultivo": cultivo,
            "ultima_medicion": ultima_medicion,
            "tareas_pendientes": tareas_pendientes,
            "ultimos_registros": ultimos_registros,
            "semaforo": semaforo,
        })

    return render(request, "growlog/dashboard.html", ctx)


def quick_entry(request):
    ctx = _base_context()
    cultivo = ctx["cultivo_activo"]

    if not cultivo:
        messages.warning(request, "No hay ningún cultivo activo. Creá uno en el admin primero.")
        return redirect("growlog:dashboard")

    form = QuickEntryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        medicion = MedicionAmbiente.objects.create(
            cultivo=cultivo,
            temperatura_c=d["temperatura_c"],
            humedad_relativa=d["humedad_relativa"],
            notas=d.get("notas", ""),
        )

        if d["rego"] and d.get("volumen_total_ml"):
            Riego.objects.create(
                cultivo=cultivo,
                volumen_total_ml=d["volumen_total_ml"],
                ph_agua=d.get("ph_agua"),
            )

        if request.htmx:
            return render(request, "growlog/partials/quick_success.html", {
                "medicion": medicion,
                "rego": d["rego"],
            })

        messages.success(
            request,
            f"✓ Guardado — {medicion.temperatura_c}°C / {medicion.humedad_relativa}%HR / VPD {medicion.vpd} kPa"
        )
        return redirect("growlog:quick")

    ctx["form"] = form
    ctx["cultivo"] = cultivo
    return render(request, "growlog/quick.html", ctx)


def timeline(request, pk):
    ctx = _base_context()
    cultivo = get_object_or_404(Cultivo, pk=pk)
    registros = _build_timeline(cultivo, limit=100)
    ctx.update({"cultivo": cultivo, "registros": registros})
    return render(request, "growlog/timeline.html", ctx)


def tarea_completar(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    tarea.completada = True
    tarea.completada_en = timezone.now()
    tarea.save()
    if request.htmx:
        return render(request, "growlog/partials/tarea_row.html", {"tarea": tarea})
    return redirect("growlog:dashboard")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_timeline(cultivo, limit=50):
    items = []
    for m in cultivo.mediciones.all()[:limit]:
        items.append({"tipo": "medicion", "ts": m.timestamp, "obj": m, "icon": "bi-thermometer-half"})
    for r in cultivo.riegos.all()[:limit]:
        items.append({"tipo": "riego", "ts": r.timestamp, "obj": r, "icon": "bi-droplet-fill"})
    for e in cultivo.eventos.all()[:limit]:
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
