from django.conf import settings


def push_settings(request):
    cultivo = getattr(request, "cultivo_actual", None)
    return {
        "vapid_public_key": settings.VAPID_PUBLIC_KEY,
        "can_edit_cultivo": getattr(request, "puede_editar_cultivo", False),
        "can_manage_cultivo": bool(cultivo and cultivo.propietario_id == request.user.pk),
    }
