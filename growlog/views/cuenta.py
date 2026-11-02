"""Tu cuenta: nombre, unidad de EC, avisos y contraseña."""
from django import forms
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from ..models import Perfil, perfil_de


class PreferenciasForm(forms.ModelForm):
    nombre = forms.CharField(max_length=150, required=False, label="Cómo te llamamos")
    hora_avisos = forms.TypedChoiceField(coerce=int, label="Hora de los avisos",
                                         choices=[(h, f"{h:02d}:00") for h in range(24)])

    class Meta:
        model = Perfil
        fields = ["unidad_ec", "avisar_ambiente", "avisar_tareas", "avisar_seguimientos", "hora_avisos"]
        widgets = {"unidad_ec": forms.RadioSelect}


@login_required
def cuenta(request):
    perfil = perfil_de(request.user)
    accion = request.POST.get("accion") if request.method == "POST" else None
    preferencias = PreferenciasForm(request.POST if accion == "preferencias" else None, instance=perfil,
                                    initial={"nombre": request.user.first_name}, prefix="pref")
    clave = PasswordChangeForm(request.user, request.POST if accion == "clave" else None, prefix="clave")
    if accion == "preferencias" and preferencias.is_valid():
        preferencias.save()
        request.user.first_name = preferencias.cleaned_data["nombre"]
        request.user.save(update_fields=["first_name"])
        messages.success(request, "Listo, guardamos tus preferencias.")
        return redirect("growlog:cuenta")
    if accion == "clave" and clave.is_valid():
        usuario = clave.save()
        update_session_auth_hash(request, usuario)  # no te saca de la sesión
        messages.success(request, "Listo, cambiaste la contraseña.")
        return redirect("growlog:cuenta")
    return render(request, "growlog/cuenta.html", {"preferencias": preferencias, "clave": clave})
