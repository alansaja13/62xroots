"""Registrar: alta de cualquier registro diario en un solo formulario.

Se usa como página (/registrar/) y como hoja que se abre con el + de la barra
(?hoja=1 por HTMX). Al guardar vuelve a donde estabas con un aviso que permite
deshacer durante un minuto.
"""
import time
from datetime import datetime, time as dt_time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..forms import DT_FMT
from ..models import (
    Cultivo, Evento, MedicionAmbiente, MedicionEC, MedicionPlanta, Nutriente, ParametroIdeal, Planta, Riego, Tarea,
)
from ..permissions import cultivos_visibles, nutrientes_para, objeto_del_cultivo, puede_subir_fotos
from ..services.registro import TIPOS, RegistroError, actualizar_registro, guardar_registro
from ..utils import etapa_efectiva_cultivo

# En el orden de los chips: lo más frecuente primero.
ETIQUETAS = {"riego": "Riego", "ambiente": "Ambiente", "evento": "Evento", "nota": "Nota",
             "ec": "pH/EC", "tarea": "Tarea", "planta": "Planta"}
# Mensaje de éxito con la concordancia de cada tipo ("Tarea guardada", no "guardado").
GUARDADO = {
    "ambiente": "Ambiente guardado", "riego": "Riego guardado", "evento": "Evento guardado",
    "nota": "Nota guardada", "ec": "Medición de pH / EC guardada", "tarea": "Tarea guardada",
    "planta": "Medición de planta guardada",
}
MODELOS = {"ambiente": MedicionAmbiente, "riego": Riego, "evento": Evento, "nota": Evento,
           "ec": MedicionEC, "tarea": Tarea, "planta": MedicionPlanta}
# Tiempo para deshacer lo recién guardado.
DESHACER_SEGUNDOS = 60

NOMBRES_CAMPOS = {
    "temperatura_c": "Temperatura", "humedad_relativa": "Humedad", "ph": "pH", "ec": "EC",
    "temp_agua": "Temperatura del agua", "descripcion": "Descripción", "titulo": "Título",
    "tipo": "Tipo", "follow_up_fecha": "Fecha de seguimiento", "fecha_objetivo": "Para cuándo",
    "volumen_ml": "Volumen", "ph_runoff": "pH runoff", "ec_runoff": "EC runoff",
    "dosis_g_por_litro": "Dosis", "planta_id": "Planta", "altura_cm": "Altura", "nudos_count": "Nudos",
    "ancho_canopy_cm": "Canopy", "aspecto_general": "Aspecto", "sintomas": "Síntomas", "foto": "Foto",
    "__all__": "",
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
        raise RegistroError("La EC se escribe como número entero en ×10 µS/cm, por ejemplo 120.",
                            campos={"ec": ["Usá la escala del medidor: 120 = 1200 µS/cm."]})
    return str((Decimal(texto) / 100).quantize(Decimal("0.01")))


def _observado(post, tipo):
    """La hora del registro. "Ahora" se calcula al guardar, no cuando se abrió la pantalla."""
    if tipo == "tarea":
        return None
    texto = post.get("observado_en")
    if post.get("observado_modo") == "ahora" or (not texto and "observado_modo" in post):
        return timezone.now()
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
    for clave in ("temperatura_c", "humedad_relativa", "ph", "temp_agua", "altura_cm", "ancho_canopy_cm"):
        if clave in campos:
            campos[clave] = _numero(campos[clave])
    if "ec" in campos:
        campos["ec"] = _numero(campos["ec"], ec=True)

    if tipo == "evento":
        campos["plantas_afectadas"] = [p.pk for p in plantas if campos.get(f"planta-{p.pk}")]
    elif tipo == "riego":
        # "Mismo volumen para todas": el mismo valor a cada planta, aunque no haya JavaScript.
        mismo = campos.get("mismo") and campos.get("volumen_todas", "").strip()
        hubo_runoff = bool(campos.get("hubo_runoff"))
        filas = []
        for p in plantas:
            volumen = mismo or campos.get(f"planta-{p.pk}", "").strip()
            if not volumen:
                continue  # vacío = no se regó esta planta
            fila = {"planta_id": p.pk, "volumen_ml": volumen}
            ph_runoff = campos.get(f"phrunoff-{p.pk}", "").strip()
            ec_runoff = campos.get(f"ecrunoff-{p.pk}", "").strip()
            # Con "Hubo runoff" cuenta la planta que tenga pH o EC de drenaje; sin él, los datos se ignoran.
            if campos.get(f"runoff-{p.pk}") or (hubo_runoff and (ph_runoff or ec_runoff)):
                fila.update(
                    runoff_observado="on",
                    ph_runoff=_numero(ph_runoff),
                    ec_runoff=_numero(ec_runoff, ec=True),
                    notas=campos.get(f"notasplanta-{p.pk}", ""),
                )
            filas.append(fila)
        if not filas:
            raise RegistroError("Indicá cuánto recibió al menos una planta.",
                                campos={"volumen_todas": ["Poné los ml."]})
        campos["plantas"] = filas
        campos["buscar_runoff"] = campos.get("buscar_runoff") or ("on" if hubo_runoff else "")
        campos["nutrientes"] = [
            {"nutriente_id": n.pk, "dosis_g_por_litro": _numero(campos[f"nutriente-{n.pk}"])}
            for n in nutrientes if campos.get(f"nutriente-{n.pk}", "").strip()
        ]
    return campos


def _avisos(tipo, datos, plantas, nutrientes):
    """Valores raros: cada uno con una clave (campo y valor) para confirmarlo por separado."""
    avisos = []

    def revisar(campo, valor, texto, unidad, minimo, maximo, contexto=""):
        try:
            numero = Decimal(str(valor))
        except ArithmeticError:
            return
        if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
            habitual = f"entre {minimo} y {maximo}{unidad}" if maximo is not None else f"{minimo}{unidad} o más"
            avisos.append({"clave": f"{campo}={valor}", "campo": f"{tipo}-{campo}",
                           "texto": f"{texto} {valor}{unidad}{contexto}: lo habitual es {habitual}."})

    for clave, texto, unidad, minimo, maximo in RAROS:
        if datos.get(clave):
            revisar(clave, datos[clave], texto, unidad, minimo, maximo)
    if datos.get("ec") and Decimal(datos["ec"]) > 5:
        avisos.append({"clave": f"ec={datos['ec']}", "campo": f"{tipo}-ec",
                       "texto": f"EC {int(Decimal(datos['ec']) * 1000)} µS/cm: lo habitual es hasta 5000 µS/cm."})
    nombres = {p.pk: p.apodo for p in plantas}
    for fila in datos.get("plantas", []):
        if fila.get("ph_runoff"):
            revisar(f"phrunoff-{fila['planta_id']}", fila["ph_runoff"], "pH", "", 4, 9,
                    f" (runoff de {nombres[fila['planta_id']]})")
    por_pk = {n.pk: n for n in nutrientes}
    for fila in datos.get("nutrientes", []):
        n = por_pk[fila["nutriente_id"]]
        revisar(f"nutriente-{fila['nutriente_id']}", fila["dosis_g_por_litro"], "Dosis", f" {n.get_unidad_display()}", 0, 10,
                f" ({n})")
    return avisos


def _errores(exc, tipo):
    lista, campos = [], set()
    for campo, mensajes in exc.campos.items():
        nombre = NOMBRES_CAMPOS.get(campo, "")
        lista.extend(f"{nombre}: {m}" if nombre else m for m in mensajes)
        campos.add(f"{tipo}-{campo}")
    return lista, campos


def _volver(request):
    """Adónde volver después de guardar desde la hoja (solo rutas de este sitio)."""
    destino = request.POST.get("volver", "")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return None


def _contexto_cultivos(cultivos):
    """Lo que la pantalla precarga por cultivo: último riego, nutrientes de siempre y rangos de la etapa."""
    ids = [c.pk for c in cultivos]
    riegos = (Riego.objects.filter(cultivo_id__in=ids).order_by("cultivo_id", "-timestamp", "-pk")
              .prefetch_related("detalle_plantas", "nutrientes_aplicados__nutriente"))
    recientes = {}
    for r in riegos:
        lista = recientes.setdefault(r.cultivo_id, [])
        if len(lista) < 5:
            lista.append(r)
    parametros = {p.etapa: p for p in ParametroIdeal.objects.all()}
    datos = {}
    for c in cultivos:
        ultimos = recientes.get(c.pk, [])
        ultimo = ultimos[0] if ultimos else None
        param = parametros.get(etapa_efectiva_cultivo(c))
        habituales = []
        for r in ultimos:
            for na in r.nutrientes_aplicados.all():
                if na.nutriente_id not in habituales:
                    habituales.append(na.nutriente_id)
        resumen = ""
        if ultimo:
            partes = [f"{ultimo.volumen_total_ml} ml"]
            partes += [f"{na.nutriente.nombre} {na.dosis_g_por_litro.normalize():f}".replace(".", ",")
                       for na in ultimo.nutrientes_aplicados.all()]
            if ultimo.ph_agua is not None:
                partes.append(f"pH {ultimo.ph_agua:.1f}".replace(".", ","))
            resumen = " · ".join(partes)
        datos[c.pk] = {
            "resumen": resumen,
            "ultimo_riego": {
                "fecha": timezone.localtime(ultimo.timestamp).strftime("%d/%m"),
                "plantas": {str(d.planta_id): d.volumen_ml for d in ultimo.detalle_plantas.all()},
                "ph": f"{ultimo.ph_agua:.1f}".replace(".", ",") if ultimo.ph_agua is not None else "",
                "ec": str(int(ultimo.ec_solucion * 100)) if ultimo.ec_solucion is not None else "",
                "nutrientes": {str(na.nutriente_id): f"{na.dosis_g_por_litro.normalize():f}".replace(".", ",")
                               for na in ultimo.nutrientes_aplicados.all()},
            } if ultimo else None,
            "habituales": habituales,
            "ph": [float(param.ph_min), float(param.ph_max)] if param else None,
            "vpd": [float(param.vpd_min), float(param.vpd_max)] if param and param.vpd_max > param.vpd_min else None,
        }
    return datos


@login_required
def registrar(request):
    cultivos = list(cultivos_visibles(request.user, editar=True).prefetch_related(
        Prefetch("plantas", queryset=Planta.objects.activas(), to_attr="plantas_activas"),
        "cambios_etapa",
    ))
    # Un solo query para el catálogo de todos los cultivos; cada cultivo ofrece
    # los compartidos, los propios y los de su dueño.
    catalogo = list(Nutriente.objects.filter(oculto=False).filter(
        Q(propietario__isnull=True) | Q(propietario=request.user)
        | Q(propietario_id__in={c.propietario_id for c in cultivos})))

    def nutrientes_de(cultivo):
        return [n for n in catalogo if n.propietario_id in (None, request.user.pk, cultivo.propietario_id)]
    origen = request.POST if request.method == "POST" else request.GET
    elegido = next((c for c in cultivos if str(c.pk) == origen.get("cultivo")), None)
    tipo = origen.get("kind")
    if tipo not in TIPOS:
        tipo = request.session.get("registrar_tipo") if request.session.get("registrar_tipo") in TIPOS else "riego"
    error, errores, campos_error, avisos = None, [], set(), []

    if request.method == "POST":
        try:
            if elegido is None:
                raise RegistroError("Elegí un cultivo en el que puedas registrar.")
            observado = _observado(request.POST, tipo)
            datos = _datos(request.POST, tipo, elegido.plantas_activas, nutrientes_de(elegido))
            archivos = {k[len("planta-"):]: v for k, v in request.FILES.items() if k.startswith("planta-")}
            # "Guardar igual" confirma solo los avisos que se vieron; un valor cambiado vuelve a avisar.
            confirmados = set(filter(None, request.POST.get("aviso_ok", "").split("|")))
            with transaction.atomic():
                obj = guardar_registro(request.user, elegido, tipo, observado, datos, archivos)
                # Los avisos se muestran solo sobre datos válidos: se guarda, y si
                # hay algo raro sin confirmar se deshace y se pregunta.
                if not request.POST.get("confirmar"):
                    avisos = [a for a in _avisos(tipo, datos, elegido.plantas_activas, nutrientes_de(elegido))
                              if a["clave"] not in confirmados]
                    transaction.set_rollback(bool(avisos))
            if not avisos:
                request.session["registrar_tipo"] = tipo
                request.session["ultimo_registro"] = {
                    "tipo": tipo, "pk": obj.pk, "t": time.time(),
                    "bitacora": reverse("growlog:timeline", args=[elegido.slug]),
                }
                messages.success(request, f"{GUARDADO[tipo]} en {elegido.nombre}.", extra_tags="registro")
                return redirect(_volver(request) or f"{reverse('growlog:registrar')}?cultivo={elegido.pk}&kind={tipo}")
        except RegistroError as exc:
            error, avisos = exc.mensaje, []
            errores, campos_error = _errores(exc, tipo)

    # Sin cultivo pedido, se propone el último que se abrió.
    reciente = request.session.get("cultivo_reciente")
    elegido = elegido or next((c for c in cultivos if c.pk == reciente), None) or (cultivos[0] if cultivos else None)
    # Al volver con errores o avisos, el formulario conserva lo escrito.
    v = _valores_post(request.POST) if request.method == "POST" else {}
    if request.method == "GET" and request.GET.get("planta"):
        v.setdefault("planta", {})["planta_id"] = request.GET["planta"]
    hoja = bool(request.GET.get("hoja")) and request.htmx and request.method == "GET"
    return _render_formulario(
        request, "growlog/partials/registrar_hoja.html" if hoja else "growlog/registrar.html",
        cultivos=cultivos, elegido=elegido, tipo=tipo, v=v, nutrientes_de=nutrientes_de,
        error=error, errores=errores, campos_error=campos_error, avisos=avisos,
        volver=request.POST.get("volver") or (request.headers.get("HX-Current-URL", "") if hoja else ""),
    )


def _valores_post(post):
    """Lo enviado, agrupado por tipo ({"riego": {"ph": ...}}), para volver a mostrarlo."""
    v = {}
    for clave, valor in post.items():
        grupo, _, campo = clave.partition("-")
        v.setdefault(grupo, {})[campo] = valor
    return v


def _render_formulario(request, plantilla, *, cultivos, elegido, tipo, v, nutrientes_de, error, errores,
                       campos_error, avisos, volver, edicion=None, observado=None):
    """Arma el formulario de Registrar (alta o corrección). En corrección hay un solo cultivo
    y un solo tipo, y las plantas pueden incluir las que ya tenía el registro."""
    riego, evento = v.get("riego", {}), v.get("evento", {})
    plantas_por_cultivo = [
        {"cultivo": c, "plantas": [{
            "planta": p,
            "volumen": riego.get(f"planta-{p.pk}", ""),
            "ph_runoff": riego.get(f"phrunoff-{p.pk}", ""),
            "ec_runoff": riego.get(f"ecrunoff-{p.pk}", ""),
            "afectada": evento.get(f"planta-{p.pk}"),
            "error": f"riego-planta-{p.pk}" in campos_error,
        } for p in getattr(c, "plantas_form", c.plantas_activas)]}
        for c in cultivos
    ]
    por_cultivo = _contexto_cultivos(cultivos)
    for c in cultivos:
        c.reg = por_cultivo[c.pk]
    nutrientes_por_cultivo = []
    for c in cultivos:
        habituales = por_cultivo[c.pk]["habituales"]
        filas = [{"nutriente": n, "dosis": riego.get(f"nutriente-{n.pk}", ""),
                  "habitual": n.pk in habituales or bool(edicion and riego.get(f"nutriente-{n.pk}"))}
                 for n in nutrientes_de(c)]
        nutrientes_por_cultivo.append({"cultivo": c, "habituales": [f for f in filas if f["habitual"]],
                                       "otros": [f for f in filas if not f["habitual"]]})
    es_post = request.method == "POST"
    return render(request, plantilla, {
        "cultivos": cultivos, "elegido": elegido, "tipo": tipo,
        "etiquetas": {tipo: ETIQUETAS[tipo]} if edicion else ETIQUETAS,
        "plantas_por_cultivo": plantas_por_cultivo, "nutrientes_por_cultivo": nutrientes_por_cultivo,
        "por_cultivo": {str(k): val for k, val in por_cultivo.items()},
        "v": v,
        "observado": request.POST.get("observado_en") or observado or timezone.localtime().strftime(DT_FMT),
        "hora_elegida": request.POST.get("observado_modo") == "elegida" if es_post else bool(edicion),
        "mismo_volumen": riego.get("mismo", "" if (es_post or edicion) else "on"),
        "error": error, "errores": errores, "campos_error": campos_error, "avisos": avisos,
        "avisos_clave": "|".join([a["clave"] for a in avisos] + list(filter(None, request.POST.get("aviso_ok", "").split("|")))),
        "volver": volver, "edicion": edicion,
        "fotos": puede_subir_fotos(request.user),
        "opciones": {
            "eventos": [o for o in Evento.TIPO_CHOICES if o[0] != "nota"], "ec": MedicionEC.TIPO_CHOICES,
            "categorias": Tarea.CATEGORIA_CHOICES, "prioridades": Tarea.PRIORIDAD_CHOICES,
            "aspectos": MedicionPlanta.ASPECTO_CHOICES,
        },
    })


@require_POST
@login_required
def registrar_deshacer(request):
    """Borra lo último que guardó esta sesión, si fue hace menos de un minuto."""
    ultimo = request.session.get("ultimo_registro") or {}
    modelo = MODELOS.get(ultimo.get("tipo"))
    vigente = modelo and time.time() - ultimo.get("t", 0) <= DESHACER_SEGUNDOS
    obj = modelo.objects.filter(pk=ultimo.get("pk"), creado_por=request.user).first() if vigente else None
    if obj is None:
        messages.error(request, "Ya no se puede deshacer ese registro. Corregilo desde la bitácora.")
    else:
        obj.delete()
        messages.success(request, "Listo, se deshizo.")
    request.session.pop("ultimo_registro", None)
    destino = request.POST.get("volver", "")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return redirect(destino)
    return redirect("growlog:dashboard")


# ── Corrección ───────────────────────────────────────────────────────────────

def _texto(numero, decimales=None):
    """Un número como se tipea acá: con coma y sin ceros de más."""
    if numero is None:
        return ""
    if decimales is not None:
        numero = round(Decimal(numero), decimales)
    return f"{Decimal(numero).normalize():f}".replace(".", ",")


def _x10(ec):
    return "" if ec is None else str(int((Decimal(ec) * 100).to_integral_value()))


def _valores_de(obj, tipo):
    """Los valores guardados con los mismos nombres que usa el formulario de Registrar."""
    if tipo == "ambiente":
        d = {"temperatura_c": _texto(obj.temperatura_c), "humedad_relativa": _texto(obj.humedad_relativa), "notas": obj.notas}
    elif tipo == "riego":
        d = {"ph": _texto(obj.ph_agua), "ec": _x10(obj.ec_solucion), "notas": obj.notas}
        for rp in obj.detalle_plantas.all():
            d[f"planta-{rp.planta_id}"] = str(rp.volumen_ml)
            if rp.runoff_observado:
                d["hubo_runoff"] = "on"
                d[f"phrunoff-{rp.planta_id}"] = _texto(rp.ph_runoff)
                d[f"ecrunoff-{rp.planta_id}"] = _x10(rp.ec_runoff)
        for na in obj.nutrientes_aplicados.all():
            d[f"nutriente-{na.nutriente_id}"] = _texto(na.dosis_g_por_litro)
    elif tipo in ("evento", "nota"):
        d = {"tipo": obj.tipo, "descripcion": obj.descripcion,
             "follow_up_fecha": obj.follow_up_fecha.isoformat() if obj.follow_up_fecha else "",
             "follow_up_descripcion": obj.follow_up_descripcion,
             "follow_up_resuelto": "on" if obj.follow_up_resuelto else ""}
        d.update({f"planta-{p.pk}": "on" for p in obj.plantas_afectadas.all()})
    elif tipo == "ec":
        d = {"tipo": obj.tipo, "ph": _texto(obj.ph), "ec": _x10(obj.ec), "temp_agua": _texto(obj.temp_agua), "notas": obj.notas}
    elif tipo == "tarea":
        d = {"titulo": obj.titulo, "descripcion": obj.descripcion, "categoria": obj.categoria, "prioridad": obj.prioridad,
             "fecha_objetivo": obj.fecha_objetivo.isoformat() if obj.fecha_objetivo else "",
             "completada": "on" if obj.completada else ""}
    else:  # planta
        d = {"planta_id": str(obj.planta_id), "altura_cm": _texto(obj.altura_cm), "nudos_count": str(obj.nudos_count or ""),
             "ancho_canopy_cm": _texto(obj.ancho_canopy_cm), "aspecto_general": obj.aspecto_general, "sintomas": obj.sintomas}
    return {tipo: d}


def _momento(obj, tipo):
    if tipo == "tarea":
        return None
    if tipo == "planta":
        return timezone.make_aware(datetime.combine(obj.fecha, dt_time(12))).strftime(DT_FMT)
    return timezone.localtime(obj.timestamp).strftime(DT_FMT)


@login_required
def registro_editar(request, tipo, pk):
    """Corregir un registro con el mismo formulario que la hoja de Registrar."""
    obj = objeto_del_cultivo(request, MODELOS[tipo], editar=True, pk=pk)
    if tipo == "evento" and obj.tipo == "nota":
        tipo = "nota"
    cultivo = Cultivo.objects.prefetch_related(
        Prefetch("plantas", queryset=Planta.objects.activas(), to_attr="plantas_activas"), "cambios_etapa",
    ).get(pk=request.cultivo_actual.pk)
    # Las plantas que ya tenía el registro siguen apareciendo aunque estén archivadas.
    plantas = list(cultivo.plantas_activas)
    if tipo == "riego":
        ya = [rp.planta for rp in obj.detalle_plantas.select_related("planta")]
    elif tipo in ("evento", "nota"):
        ya = list(obj.plantas_afectadas.all())
    elif tipo == "planta":
        ya = [obj.planta]
    else:
        ya = []
    plantas += [p for p in ya if p.pk not in {q.pk for q in plantas}]
    cultivo.plantas_form = plantas
    catalogo = list(nutrientes_para(request.user, cultivo))
    if tipo == "riego":
        catalogo += [na.nutriente for na in obj.nutrientes_aplicados.select_related("nutriente")
                     if na.nutriente_id not in {n.pk for n in catalogo}]

    ficha = reverse("growlog:registro_ficha", args=[{"nota": "evento"}.get(tipo, tipo), obj.pk])
    error, errores, campos_error, avisos = None, [], set(), []
    if request.method == "POST":
        try:
            observado = _observado(request.POST, tipo)
            datos = _datos(request.POST, tipo, plantas, catalogo)
            archivos = {k[len("planta-"):]: v for k, v in request.FILES.items() if k.startswith("planta-")}
            confirmados = set(filter(None, request.POST.get("aviso_ok", "").split("|")))
            with transaction.atomic():
                actualizar_registro(request.user, obj, tipo, observado, datos, archivos)
                if not request.POST.get("confirmar"):
                    avisos = [a for a in _avisos(tipo, datos, plantas, catalogo) if a["clave"] not in confirmados]
                    transaction.set_rollback(bool(avisos))
            if not avisos:
                messages.success(request, "Listo, quedó corregido.")
                return redirect(_volver(request) or ficha)
        except RegistroError as exc:
            error, avisos = exc.mensaje, []
            errores, campos_error = _errores(exc, tipo)
            obj.refresh_from_db()
    v = _valores_post(request.POST) if request.method == "POST" else _valores_de(obj, tipo)
    return _render_formulario(
        request, "growlog/registro_editar.html", cultivos=[cultivo], elegido=cultivo, tipo=tipo, v=v,
        nutrientes_de=lambda c: catalogo, error=error, errores=errores, campos_error=campos_error, avisos=avisos,
        volver=request.POST.get("volver") or request.GET.get("volver") or ficha,
        edicion={"obj": obj, "ficha": ficha, "nombre": GUARDADO[tipo].rsplit(" ", 1)[0]},
        observado=_momento(obj, tipo),
    )


# Las direcciones de siempre (/riego/<pk>/editar/…) ahora abren la corrección unificada.
def riego_editar(request, pk):
    return registro_editar(request, "riego", pk)


def evento_editar(request, pk):
    return registro_editar(request, "evento", pk)


def medicion_ambiente_editar(request, pk):
    return registro_editar(request, "ambiente", pk)


def medicion_ec_editar(request, pk):
    return registro_editar(request, "ec", pk)


def tarea_editar(request, pk):
    return registro_editar(request, "tarea", pk)


def medicion_planta_editar(request, pk):
    return registro_editar(request, "planta", pk)
