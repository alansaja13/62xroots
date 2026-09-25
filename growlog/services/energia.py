"""Estimación de consumo y costo eléctrico por cultivo."""
import calendar


def _mes_siguiente(d):
    """Primer día del mes siguiente."""
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1, day=1)
    return d.replace(month=d.month + 1, day=1)


def ciclo_activo(cultivo, hoy):
    """Fotoperiodo activo según CambioFotoperiodo o estado del cultivo."""
    cf = cultivo.cambios_fotoperiodo.filter(fecha_inicio__lte=hoy).order_by('-fecha_inicio').first()
    if cf:
        return cf.fotoperiodo
    return '12/12' if cultivo.estado == 'floracion' else '18/6'


def calcular_meses(cultivo_inicio, costos, tarifas, hoy):
    """Lista de dicts por mes desde cultivo_inicio hasta hoy con kWh y costo estimados."""
    meses = []
    mes = cultivo_inicio.replace(day=1)

    while mes <= hoy:
        tarifa_mes = next((t for t in tarifas if t.fecha_desde <= mes), None)

        last_day = calendar.monthrange(mes.year, mes.month)[1]
        mes_fin = mes.replace(day=last_day)

        dia_inicio = max(mes, cultivo_inicio)
        dia_fin = min(mes_fin, hoy)
        dias = (dia_fin - dia_inicio).days + 1

        if dias > 0:
            kwh_mes_val = 0.0
            for ce in costos:
                ce_hasta = ce.fecha_hasta
                if ce.fecha_desde <= dia_fin and (ce_hasta is None or ce_hasta >= dia_inicio):
                    equipo_inicio = max(dia_inicio, ce.fecha_desde)
                    equipo_fin = min(dia_fin, ce_hasta) if ce_hasta else dia_fin
                    dias_equipo = (equipo_fin - equipo_inicio).days + 1
                    kwh_mes_val += float(ce.equipo.watts) / 1000 * float(ce.equipo.horas_dia) * dias_equipo
            kwh_mes_val = round(kwh_mes_val, 2)
            costo_mes_val = round(kwh_mes_val * float(tarifa_mes.precio_kwh), 2) if tarifa_mes else 0.0

            meses.append({
                'mes': mes.strftime('%Y-%m'),
                'dias': dias,
                'kwh_estimado': kwh_mes_val,
                'costo_estimado': costo_mes_val,
                'tarifa': str(tarifa_mes.precio_kwh) if tarifa_mes else None,
            })

        mes = _mes_siguiente(mes)

    return meses
