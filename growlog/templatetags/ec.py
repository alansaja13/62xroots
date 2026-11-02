"""La EC se guarda en mS/cm y se muestra en µS/cm, como en el medidor (1,2 → 1200)."""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def ec_us(valor):
    if valor in (None, ""):
        return ""
    try:
        return f"{(Decimal(str(valor)) * 1000).quantize(Decimal('1')):f}"
    except InvalidOperation:
        return valor


@register.filter
def ec_x10(valor):
    """Como lo muestra un medidor en escala ×10 µS/cm (1,2 mS/cm → 120)."""
    if valor in (None, ""):
        return ""
    try:
        return f"{(Decimal(str(valor)) * 100).quantize(Decimal('1')):f}"
    except InvalidOperation:
        return valor


def formatear_ec(valor, unidad="us"):
    """EC guardada en mS/cm, con su unidad: 1400 µS · 1,40 mS · 140 en el medidor."""
    if valor in (None, ""):
        return ""
    try:
        ms = Decimal(str(valor))
    except InvalidOperation:
        return valor
    if unidad == "ms":
        return f"{ms.quantize(Decimal('0.01'))} mS".replace(".", ",")
    if unidad == "x10":
        return f"{(ms * 100).quantize(Decimal('1')):f} medidor"
    return f"{(ms * 1000).quantize(Decimal('1')):f} µS"


@register.simple_tag(takes_context=True)
def ec(context, valor):
    """{% ec valor %}: la EC en la unidad que eligió quien mira (Más › Tu cuenta)."""
    return formatear_ec(valor, context.get("unidad_ec", "us"))
