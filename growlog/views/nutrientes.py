"""Catálogo de nutrientes: los compartidos (del administrador) y los propios de cada usuario."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..forms import NutrienteForm
from ..models import Nutriente
from ..permissions import nutrientes_visibles


def _editable(request, pk):
    """Los propios; los compartidos solo los toca un administrador."""
    nutriente = get_object_or_404(Nutriente, pk=pk)
    if nutriente.propietario_id == request.user.pk:
        return nutriente
    if nutriente.propietario_id is None and request.user.is_superuser:
        return nutriente
    raise Http404


def _guardar(request, form):
    nutriente = form.save(commit=False)
    if "compartido" in form.cleaned_data:
        nutriente.propietario = None if form.cleaned_data["compartido"] else request.user
    elif nutriente.propietario_id is None and not nutriente.pk:
        nutriente.propietario = request.user
    nutriente.save()
    return nutriente


@login_required
def nutrientes(request):
    con_usos = Nutriente.objects.annotate(usos=Count("nutrienteaplicado"))
    compartidos = con_usos.filter(propietario__isnull=True)
    if not request.user.is_superuser:
        compartidos = compartidos.filter(oculto=False)
    return render(request, "growlog/nutrientes.html", {
        "propios": con_usos.filter(propietario=request.user),
        "compartidos": compartidos,
        # Los de los dueños de cultivos compartidos con vos: se ofrecen al registrar ahí.
        "de_otros": nutrientes_visibles(request.user).exclude(
            Q(propietario__isnull=True) | Q(propietario=request.user)).select_related("propietario"),
    })


@login_required
def nutriente_crear(request):
    form = NutrienteForm(request.POST or None, puede_compartir=request.user.is_superuser)
    if request.method == "POST" and form.is_valid():
        nutriente = _guardar(request, form)
        messages.success(request, f"Nutriente «{nutriente}» agregado.")
        return redirect("growlog:nutrientes")
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": "Nuevo nutriente",
        "subtitle": "Lo vas a ver al registrar riegos en tus cultivos.",
        "back_url": reverse("growlog:nutrientes"),
    })


@login_required
def nutriente_editar(request, pk):
    nutriente = _editable(request, pk)
    form = NutrienteForm(request.POST or None, instance=nutriente, puede_compartir=request.user.is_superuser)
    if request.method == "POST" and form.is_valid():
        _guardar(request, form)
        messages.success(request, "Nutriente actualizado.")
        return redirect("growlog:nutrientes")
    return render(request, "growlog/crud_form.html", {
        "form": form, "title": f"Editar: {nutriente}",
        "back_url": reverse("growlog:nutrientes"),
    })


@require_POST
@login_required
def nutriente_ocultar(request, pk):
    nutriente = _editable(request, pk)
    nutriente.oculto = not nutriente.oculto
    nutriente.save(update_fields=["oculto"])
    messages.success(request, f"«{nutriente}» {'oculto: ya no se ofrece al registrar' if nutriente.oculto else 'visible otra vez'}.")
    return redirect("growlog:nutrientes")


@require_POST
@login_required
def nutriente_eliminar(request, pk):
    nutriente = _editable(request, pk)
    usos = nutriente.nutrienteaplicado_set.count()
    if usos:
        # Los riegos guardados lo referencian: se oculta en vez de borrarse.
        messages.error(request, f"«{nutriente}» se usó en {usos} riego{'s' if usos != 1 else ''}. Ocultalo en lugar de borrarlo.")
    else:
        nutriente.delete()
        messages.success(request, f"Nutriente «{nutriente}» eliminado.")
    return redirect("growlog:nutrientes")
