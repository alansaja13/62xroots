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
