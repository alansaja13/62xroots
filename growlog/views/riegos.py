"""Riegos: el borrado. La corrección (con plantas y nutrientes) está en views/registrar.py."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from ..models import Riego
from ..permissions import objeto_del_cultivo


# ---------------------------------------------------------------------------
# Riego CRUD
# ---------------------------------------------------------------------------


@login_required
def riego_eliminar(request, pk):
    riego = objeto_del_cultivo(request, Riego, editar=True, pk=pk)
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
# ---------------------------------------------------------------------------
# NutrienteAplicado CRUD
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
