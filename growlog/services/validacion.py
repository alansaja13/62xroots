"""Reglas de medición independientes del canal de entrada."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


def validar_solucion(*, ph=None, ec=None):
    for nombre, valor, maximo in (("pH", ph, 14), ("EC", ec, None)):
        if valor is None:
            continue
        try:
            numero = Decimal(str(valor))
        except InvalidOperation:
            raise ValidationError(f"{nombre} debe ser un número.")
        if not numero.is_finite() or numero < 0 or (maximo is not None and numero > maximo):
            if maximo is not None:
                raise ValidationError("El pH debe estar entre 0 y 14.")
            raise ValidationError("La EC debe ser un número mayor o igual que cero.")
