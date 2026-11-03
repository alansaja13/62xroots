"""Plantas, sus mediciones y cambios de etapa."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import CambioEtapaPlantaForm, MedicionPlantaForm, PlantaForm, PlantasNuevasForm
from ..models import CambioEtapaPlanta, Cultivo, MedicionPlanta, Planta
from ..permissions import objeto_del_cultivo, puede_subir_fotos
from ..services.plantas import curva, resumen_planta
from ..utils import etapa_efectiva_planta, get_etapa_activa_cultivo, get_etapa_activa_planta

# Pestañas de la lista de plantas: clave → (etiqueta, filtro).
VISTAS_PLANTAS = {
    "activas": ("Activas", {"estado": "activa", "archivado": False}),
    "cosechadas": ("Cosechadas", {"estado": "cosechada", "archivado": False}),
    "descartadas": ("Descartadas", {"estado": "descartada", "archivado": False}),
    "archivadas": ("Archivadas", {"archivado": True}),
}


@login_required
def plantas_list(request, slug):
    cultivo = objeto_del_cultivo(request, Cultivo, slug=slug)
    vista = request.GET.get("ver") if request.GET.get("ver") in VISTAS_PLANTAS else "activas"
    todas = list(cultivo.plantas.prefetch_related(
        Prefetch("mediciones", queryset=MedicionPlanta.objects.order_by("fecha", "pk"), to_attr="mediciones_orden")))
    hoy = timezone.localdate()
    cuentas = {clave: sum(all(getattr(p, k) == v for k, v in filtro.items()) for p in todas)
               for clave, (_, filtro) in VISTAS_PLANTAS.items()}
    filtro = VISTAS_PLANTAS[vista][1]
    plantas = [resumen_planta(p, p.mediciones_orden, hoy) for p in todas
               if all(getattr(p, k) == v for k, v in filtro.items())]
    return render(request, "growlog/plantas_list.html", {
        "cultivo": cultivo, "plantas": plantas, "vista": vista,
        "vistas": [{"clave": k, "etiqueta": v[0], "cuenta": cuentas[k]} for k, v in VISTAS_PLANTAS.items()],
    })


# ---------------------------------------------------------------------------
# Planta CRUD
# ---------------------------------------------------------------------------

@login_required
def planta_crear(request, slug):
    """Una o varias plantas de una vez: cantidad, strain y tipo, con un apodo editable para cada una."""
    cultivo = objeto_del_cultivo(request, Cultivo, editar=True, slug=slug)
    form = PlantasNuevasForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        base = datos["strain"] or "Planta"
        nuevas = [Planta(cultivo=cultivo, creado_por=request.user, strain=datos["strain"], tipo=datos["tipo"],
                         apodo=(request.POST.get(f"apodo-{i}") or "").strip()[:60] or f"{base} {i}")
                  for i in range(1, datos["cantidad"] + 1)]
        Planta.objects.bulk_create(nuevas)
        messages.success(request, f"Planta «{nuevas[0].apodo}» creada." if len(nuevas) == 1
                         else f"{len(nuevas)} plantas creadas.")
        return redirect(request.POST.get("siguiente") == "empezar" and reverse("growlog:cultivo_empezar", args=[cultivo.slug])
                        or reverse("growlog:plantas_list", args=[cultivo.slug]))
    return render(request, "growlog/plantas_nuevas.html", {
        "cultivo": cultivo, "form": form, "desde_empezar": request.GET.get("desde") == "empezar"
        or request.POST.get("siguiente") == "empezar",
        "apodos": [request.POST.get(f"apodo-{i}", "") for i in range(1, 31)] if request.method == "POST" else [],
    })


@login_required
def planta_editar(request, pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=pk)
    form = PlantaForm(request.POST or None, instance=planta)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Planta actualizada.")
        return redirect("growlog:planta_detail", pk=pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar: {planta.apodo}",
        "subtitle": planta.cultivo.nombre,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
        "delete_url": reverse("growlog:planta_eliminar", args=[pk]),
    })


@login_required
def planta_eliminar(request, pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=pk)
    cultivo = planta.cultivo
    if request.method == "POST":
        nombre = planta.apodo
        if planta.eliminar_o_archivar():
            messages.success(request, f"Planta «{nombre}» eliminada.")
        else:
            messages.success(request, f"Planta «{nombre}» archivada. Sus riegos, mediciones y etapas se conservan; "
                                      "la encontrás en «archivadas», debajo de las plantas, y la restaurás editándola.")
        return redirect("growlog:cultivo_detail", cultivo.slug)
    if planta.tiene_historial():
        return render(request, "growlog/crud_delete.html", {
            "title": "Archivar planta", "object_name": planta.apodo,
            "warn": "tiene historial: se archiva y se conservan sus riegos, fotos y etapas",
            "confirm_label": "archivar planta", "confirm_icon": "bi-archive",
            "back_url": reverse("growlog:planta_detail", args=[pk]),
        })
    return render(request, "growlog/crud_delete.html", {
        "title": "Eliminar planta", "object_name": planta.apodo,
        "back_url": reverse("growlog:planta_detail", args=[pk]),
    })


@login_required
def planta_detail(request, pk):
    planta = objeto_del_cultivo(request, Planta, pk=pk)
    mediciones = list(planta.mediciones.order_by("fecha", "pk"))
    r = resumen_planta(planta, mediciones)
    riegos_planta = list(planta.riegos_detalle.select_related("riego").order_by("-riego__timestamp")[:10])
    eventos = list(planta.eventos.order_by("-timestamp")[:10])
    etapa_actual = etapa_efectiva_planta(planta)

    # Curva de altura con los eventos de la planta marcados (topping, LST…) en su fecha.
    con_altura = r["con_altura"]
    curva_altura, marcas = "", []
    if len(con_altura) >= 2:
        inicio, fin = con_altura[0].fecha, con_altura[-1].fecha
        puntos = curva([((m.fecha - inicio).days, float(m.altura_cm)) for m in con_altura], 340, 120, margen=8)
        curva_altura = " ".join(f"{x},{y}" for x, y in puntos)
        span = (fin - inicio).days or 1
        for e in eventos:
            fecha = timezone.localdate(e.timestamp)
            if inicio <= fecha <= fin and e.tipo != "nota":
                marcas.append({"x": round(8 + (fecha - inicio).days / span * 324, 1), "texto": e.get_tipo_display().lower()})
    return render(request, "growlog/planta_detail.html", {
        **r, "planta": planta, "mediciones": list(reversed(mediciones)), "cultivo": planta.cultivo,
        "riegos_planta": riegos_planta, "eventos": eventos,
        "etapa_actual": etapa_actual,
        "etapa_actual_display": dict(CambioEtapaPlanta.ETAPA_CHOICES).get(etapa_actual),
        "curva_altura": curva_altura, "marcas": marcas,
    })


@login_required
def planta_fotos(request, pk):
    """Las fotos de una planta en el tiempo, y para comparar dos fechas."""
    planta = objeto_del_cultivo(request, Planta, pk=pk)
    fotos = list(planta.mediciones.exclude(foto="").exclude(foto__isnull=True).order_by("-fecha", "-pk"))
    for f in fotos:
        f.dia = (f.fecha - planta.cultivo.fecha_inicio).days
    return render(request, "growlog/planta_fotos.html", {"planta": planta, "cultivo": planta.cultivo, "fotos": fotos})


# ---------------------------------------------------------------------------
# MedicionPlanta CRUD
# ---------------------------------------------------------------------------

def _subtitulo_medicion(planta, fotos):
    return str(planta) if fotos else f"{planta} · Por ahora la subida de fotos está deshabilitada."


@login_required
def medicion_planta_crear(request, planta_pk):
    planta = objeto_del_cultivo(request, Planta, editar=True, pk=planta_pk)
    fotos = puede_subir_fotos(request.user)
    form = MedicionPlantaForm(request.POST or None, request.FILES or None,
                              initial={"fecha": timezone.localdate()}, permitir_foto=fotos)
    if request.method == "POST" and form.is_valid():
        m = form.save(commit=False)
        m.planta = planta
        m.creado_por = request.user
        m.save()
        messages.success(request, "Medición registrada.")
        return redirect("growlog:planta_detail", pk=planta_pk)
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nueva medición de planta",
        "subtitle": _subtitulo_medicion(planta, fotos),
        "back_url": reverse("growlog:planta_detail", args=[planta_pk]),
        "multipart": fotos,
    })


# ---------------------------------------------------------------------------
# CambioEtapaPlanta
# ---------------------------------------------------------------------------

@login_required
def planta_etapa_list(request, pk):
    # Un lector ve el historial; objeto_del_cultivo exige edición para el POST.
    planta = objeto_del_cultivo(request, Planta, pk=pk)
    puede_editar = request.puede_editar_cultivo
    historial = planta.cambios_etapa.order_by("-fecha_inicio")
    propia = get_etapa_activa_planta(planta)
    del_cultivo = get_etapa_activa_cultivo(planta.cultivo)
    if propia and del_cultivo and propia.fecha_inicio < del_cultivo.fecha_inicio:
        propia = None  # un cambio de etapa del cultivo posterior la igualó
    etapa_actual = etapa_efectiva_planta(planta)

    if not puede_editar:
        form = None
    elif request.method == "POST":
        form = CambioEtapaPlantaForm(request.POST)
        if form.is_valid():
            cambio = form.save(commit=False)
            cambio.planta = planta
            try:
                cambio.full_clean()
                cambio.save()
                messages.success(request, f"Etapa {cambio.get_etapa_display()} guardada.")
                return redirect("growlog:planta_etapa_list", pk=pk)
            except ValidationError as e:
                for mensaje in e.messages:
                    form.add_error(None, mensaje)
    else:
        form = CambioEtapaPlantaForm(initial={"fecha_inicio": timezone.localdate()})

    return render(request, "growlog/etapa_historial.html", {
        "planta": planta,
        "cultivo": planta.cultivo,
        "historial": historial,
        "form": form,
        "puede_editar": puede_editar,
        "propia": propia, "vigente_pk": propia.pk if propia else None,
        "etapa_actual_display": dict(CambioEtapaPlanta.ETAPA_CHOICES).get(etapa_actual),
        "back_url": reverse("growlog:planta_detail", args=[planta.pk]),
        "back_label": planta.apodo,
        "editar_url": "growlog:cambio_etapa_planta_editar",
        "eliminar_url": "growlog:cambio_etapa_planta_eliminar",
    })


@login_required
def cambio_etapa_planta_editar(request, pk):
    cambio = objeto_del_cultivo(request, CambioEtapaPlanta, editar=True, pk=pk)
    planta = cambio.planta
    form = CambioEtapaPlantaForm(request.POST or None, instance=cambio)
    if form.is_valid():
        try:
            obj = form.save(commit=False)
            obj.full_clean()
            obj.save()
            messages.success(request, "Etapa actualizada.")
            return redirect("growlog:planta_etapa_list", pk=planta.pk)
        except ValidationError as e:
            for mensaje in e.messages:
                form.add_error(None, mensaje)
    return render(request, "growlog/crud_form.html", {
        "form": form,
        "title": f"Editar etapa: {planta.apodo}",
        "back_url": reverse("growlog:planta_etapa_list", args=[planta.pk]),
        "delete_url": reverse("growlog:cambio_etapa_planta_eliminar", args=[pk]),
    })


@login_required
def cambio_etapa_planta_eliminar(request, pk):
    cambio = objeto_del_cultivo(request, CambioEtapaPlanta, editar=True, pk=pk)
    planta = cambio.planta
    if request.method == "POST":
        cambio.delete()
        messages.success(request, "Registro de etapa eliminado.")
        return redirect("growlog:planta_etapa_list", pk=planta.pk)
    return render(request, "growlog/crud_delete.html", {
        "title": f"Eliminar etapa {cambio.get_etapa_display()}",
        "object_name": f"{cambio.get_etapa_display()} · desde {cambio.fecha_inicio}",
        "back_url": reverse("growlog:cambio_etapa_planta_editar", args=[pk]),
    })
