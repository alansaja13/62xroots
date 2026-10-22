"""Registrar: alta de ambiente, riego, observación, EC/pH y tarea en un solo formulario."""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..forms import DT_FMT
from ..models import Evento, MedicionEC, Nutriente, Planta, Tarea
from ..permissions import cultivos_visibles
from ..services.registro import TIPOS, RegistroError, guardar_registro

ETIQUETAS = {"ambiente": "Ambiente", "riego": "Riego", "evento": "Observación", "ec": "pH / EC", "tarea": "Tarea"}

NOMBRES_CAMPOS = {
    "temperatura_c": "Temperatura", "humedad_relativa": "Humedad", "ph": "pH", "ec": "EC",
    "temp_agua": "Temperatura del agua", "descripcion": "Descripción", "titulo": "Título",
    "tipo": "Tipo", "follow_up_fecha": "Fecha de seguimiento", "fecha_objetivo": "Para cuándo",
    "volumen_ml": "Volumen", "ph_runoff": "pH runoff", "ec_runoff": "EC runoff",
    "dosis_g_por_litro": "Dosis", "__all__": "",
}

# Valores válidos pero raros: casi siempre un tipeo. Se avisa y quien registra decide.
RAROS = (
    ("temperatura_c", "Temperatura", " °C", 10, 40),
    ("humedad_relativa", "Humedad", " %", 15, None),
    ("ph", "pH", "", 4, 9),
    ("temp_agua", "Temperatura del agua", " °C", 10, 40),
)


def _numero(texto, *, ec=False):
    """"1,8" y "1.8" valen lo mismo. La EC se tipea en ×10 µS/cm como en el
    medidor (120 = 1200 µS/cm) y se guarda en mS/cm (1.20)."""
    texto = (texto or "").strip().replace(",", ".")
    if not ec or not texto:
        return texto
    if not texto.isdigit():
        raise RegistroError("La EC se escribe como número entero en ×10 µS/cm, por ejemplo 120.")
    return str((Decimal(texto) / 100).quantize(Decimal("0.01")))


def _observado(texto, tipo):
    if tipo == "tarea":
        return None
    observado = parse_datetime(texto or "")
    if observado is None:
        raise RegistroError("Indicá cuándo ocurrió.")
    if timezone.is_naive(observado):
        observado = timezone.make_aware(observado)
    if observado > timezone.now() + timedelta(minutes=5):
        raise RegistroError("La fecha está en el futuro. Revisá la hora.")
    return observado


def _campos(post, tipo):
    prefijo = f"{tipo}-"
    return {clave[len(prefijo):]: valor for clave, valor in post.items() if clave.startswith(prefijo)}


def _datos(post, tipo, plantas, nutrientes):
    campos = _campos(post, tipo)
    for clave in ("temperatura_c", "humedad_relativa", "ph", "temp_agua"):
        if clave in campos:
            campos[clave] = _numero(campos[clave])
    if "ec" in campos:
        campos["ec"] = _numero(campos["ec"], ec=True)

    if tipo == "evento":
        campos["plantas_afectadas"] = [p.pk for p in plantas if campos.get(f"planta-{p.pk}")]
    elif tipo == "riego":
        filas = []
        for p in plantas:
            volumen = campos.get(f"planta-{p.pk}", "").strip()
            if not volumen:
                continue  # vacío = no se regó esta planta
            fila = {"planta_id": p.pk, "volumen_ml": volumen}
            if campos.get(f"runoff-{p.pk}"):
                fila.update(
                    runoff_observado="on",
                    ph_runoff=_numero(campos.get(f"phrunoff-{p.pk}")),
                    ec_runoff=_numero(campos.get(f"ecrunoff-{p.pk}"), ec=True),
                    notas=campos.get(f"notasplanta-{p.pk}", ""),
                )
            filas.append(fila)
        if not filas:
            raise RegistroError("Indicá cuánto recibió al menos una planta.")
        campos["plantas"] = filas
        campos["nutrientes"] = [
            {"nutriente_id": n.pk, "dosis_g_por_litro": _numero(campos[f"nutriente-{n.pk}"])}
            for n in nutrientes if campos.get(f"nutriente-{n.pk}", "").strip()
        ]
    return campos


def _avisos(datos, plantas, nutrientes):
    avisos = []

    def revisar(valor, texto, unidad, minimo, maximo, contexto=""):
        try:
            numero = Decimal(str(valor))
        except ArithmeticError:
            return
        if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
            habitual = f"entre {minimo} y {maximo}{unidad}" if maximo is not None else f"{minimo}{unidad} o más"
            avisos.append(f"{texto} {valor}{unidad}{contexto}: lo habitual es {habitual}.")

    for clave, texto, unidad, minimo, maximo in RAROS:
        if datos.get(clave):
            revisar(datos[clave], texto, unidad, minimo, maximo)
    if datos.get("ec") and Decimal(datos["ec"]) > 5:
        avisos.append(f"EC {int(Decimal(datos['ec']) * 1000)} µS/cm: lo habitual es hasta 5000 µS/cm.")
    nombres = {p.pk: p.apodo for p in plantas}
    for fila in datos.get("plantas", []):
        if fila.get("ph_runoff"):
            revisar(fila["ph_runoff"], "pH", "", 4, 9, f" (runoff de {nombres[fila['planta_id']]})")
    dosis_nombres = {n.pk: str(n) for n in nutrientes}
    for fila in datos.get("nutrientes", []):
        revisar(fila["dosis_g_por_litro"], "Dosis", " g/L", 0, 10, f" ({dosis_nombres[fila['nutriente_id']]})")
    return avisos


def _errores(exc):
    lista = []
    for campo, mensajes in exc.campos.items():
        nombre = NOMBRES_CAMPOS.get(campo, campo)
        lista.extend(f"{nombre}: {m}" if nombre else m for m in mensajes)
    return lista


@login_required
def registrar(request):
    cultivos = list(cultivos_visibles(request.user, editar=True).prefetch_related(
        Prefetch("plantas", queryset=Planta.objects.activas(), to_attr="plantas_activas"),
    ))
    nutrientes = list(Nutriente.objects.all())
    origen = request.POST if request.method == "POST" else request.GET
    elegido = next((c for c in cultivos if str(c.pk) == origen.get("cultivo")), None)
    tipo = origen.get("kind") if origen.get("kind") in TIPOS else "ambiente"
    error, errores, avisos = None, [], []

    if request.method == "POST":
        try:
            if elegido is None:
                raise RegistroError("Elegí un cultivo en el que puedas registrar.")
            observado = _observado(request.POST.get("observado_en"), tipo)
            datos = _datos(request.POST, tipo, elegido.plantas_activas, nutrientes)
            with transaction.atomic():
                guardar_registro(request.user, elegido, tipo, observado, datos)
                # Los avisos se muestran solo sobre datos válidos: se guarda, y si
                # hay algo raro sin confirmar se deshace y se pregunta.
                if not request.POST.get("confirmar"):
                    avisos = _avisos(datos, elegido.plantas_activas, nutrientes)
                    transaction.set_rollback(bool(avisos))
            if not avisos:
                messages.success(request, f"{ETIQUETAS[tipo]} guardado en {elegido.nombre}.")
                return redirect(f"{reverse('growlog:registrar')}?cultivo={elegido.pk}&kind={tipo}")
        except RegistroError as exc:
            error, errores, avisos = exc.mensaje, _errores(exc), []

    # Sin cultivo pedido, se propone el último que se abrió.
    reciente = request.session.get("cultivo_reciente")
    elegido = elegido or next((c for c in cultivos if c.pk == reciente), None) or (cultivos[0] if cultivos else None)
    # Al volver con errores o avisos, el formulario conserva lo escrito.
    v = {}
    if request.method == "POST":
        for clave, valor in request.POST.items():
            grupo, _, campo = clave.partition("-")
            v.setdefault(grupo, {})[campo] = valor
    riego, evento = v.get("riego", {}), v.get("evento", {})
    plantas_por_cultivo = [
        {"cultivo": c, "plantas": [{
            "planta": p,
            "volumen": riego.get(f"planta-{p.pk}", ""),
            "runoff": riego.get(f"runoff-{p.pk}"),
            "ph_runoff": riego.get(f"phrunoff-{p.pk}", ""),
            "ec_runoff": riego.get(f"ecrunoff-{p.pk}", ""),
            "notas": riego.get(f"notasplanta-{p.pk}", ""),
            "afectada": evento.get(f"planta-{p.pk}"),
        } for p in c.plantas_activas]}
        for c in cultivos
    ]
    return render(request, "growlog/registrar.html", {
        "cultivos": cultivos, "elegido": elegido, "tipo": tipo, "etiquetas": ETIQUETAS,
        "plantas_por_cultivo": plantas_por_cultivo,
        "nutrientes": [{"nutriente": n, "dosis": riego.get(f"nutriente-{n.pk}", "")} for n in nutrientes],
        "v": v, "observado": request.POST.get("observado_en") or timezone.localtime().strftime(DT_FMT),
        "error": error, "errores": errores, "avisos": avisos,
        "opciones": {
            "eventos": Evento.TIPO_CHOICES, "ec": MedicionEC.TIPO_CHOICES,
            "categorias": Tarea.CATEGORIA_CHOICES, "prioridades": Tarea.PRIORIDAD_CHOICES,
        },
    })
