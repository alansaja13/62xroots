"""
Completa el detalle por planta (RiegoPlanta) de riegos viejos que se cargaron
antes de que existiera esa funcionalidad -- pero hablando SOLO por HTTPS con
la API de 62xroots (por defecto la producción en Railway), nunca contra una
base de datos local.

Reconstruye qué plantas participaron de cada riego cruzando con el Evento que
tenga el mismo timestamp (ya trae plantas_afectadas marcadas). Si no hay
evento de referencia, reparte parejo entre las plantas activas del cultivo
cuando volumen_por_planta_ml * <plantas activas> == volumen_total_ml.

Corre en dry-run por defecto -- no escribe nada hasta que le pases --apply.

Uso:
    python backfill_riego_plantas_api.py --token TU_TOKEN --slug 1-c2040-fgx4-sx1
    python backfill_riego_plantas_api.py --token TU_TOKEN --slug 1-c2040-fgx4-sx1 --apply

El token se genera una sola vez en el servidor con:
    railway run python manage.py create_api_token <tu_usuario>
"""

import argparse
import sys

import requests

DEFAULT_BASE_URL = "https://62xroots.up.railway.app"


def api_get(base_url, token, path):
    r = requests.get(f"{base_url}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise SystemExit(f"Error de API en GET {path}: {body.get('error')}")
    return body["data"]


def api_post(base_url, token, path, payload):
    r = requests.post(
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload, timeout=20,
    )
    body = r.json()
    if not body.get("ok"):
        raise SystemExit(f"Error de API en POST {path}: {body.get('error')}")
    return body["data"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"default: {DEFAULT_BASE_URL}")
    parser.add_argument("--token", required=True, help="API token (Bearer)")
    parser.add_argument("--slug", required=True, help="slug del cultivo, ej: 1-c2040-fgx4-sx1")
    parser.add_argument("--apply", action="store_true", help="escribe los cambios (sin esto es dry-run)")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    plantas = api_get(base_url, args.token, f"/api/v1/cultivos/{args.slug}/plantas/")
    uuid_by_apodo = {p["apodo"]: p["uuid"] for p in plantas if not p["archivado"]}
    activas = [p for p in plantas if not p["archivado"]]

    eventos = api_get(base_url, args.token, f"/api/v1/cultivos/{args.slug}/eventos/")
    eventos_by_ts = {}
    for e in eventos:
        eventos_by_ts.setdefault(e["timestamp"], []).append(e)

    riegos = api_get(base_url, args.token, f"/api/v1/cultivos/{args.slug}/riegos/")

    resueltos, saltados = 0, 0

    for r in riegos:
        if r.get("detalle_plantas"):
            continue

        candidatos = None
        fuente = None
        for e in eventos_by_ts.get(r["timestamp"], []):
            apodos = e.get("plantas_afectadas") or []
            if not apodos:
                continue
            n = len(apodos)
            vol_por_planta = r.get("volumen_por_planta_ml")
            if vol_por_planta and n * vol_por_planta == r["volumen_total_ml"]:
                candidatos, fuente = apodos, f"evento #{e['id']} (mismo timestamp)"
                break
            if not vol_por_planta and n > 0:
                candidatos, fuente = apodos, f"evento #{e['id']} (mismo timestamp, sin volumen_por_planta_ml)"
                break

        if candidatos is None:
            n = len(activas)
            vol_por_planta = r.get("volumen_por_planta_ml")
            if n and vol_por_planta and n * vol_por_planta == r["volumen_total_ml"]:
                candidatos = [p["apodo"] for p in activas]
                fuente = f"inferido, {n} plantas activas del cultivo hoy (sin evento de referencia)"

        if candidatos is None:
            print(f"Riego #{r['id']} ({r['timestamp']}, {r['volumen_total_ml']}ml): "
                  f"no se pudo inferir que plantas -- revisar a mano.")
            saltados += 1
            continue

        vol_por_planta = r.get("volumen_por_planta_ml") or (r["volumen_total_ml"] // len(candidatos))
        print(f"Riego #{r['id']} ({r['timestamp']}, {r['volumen_total_ml']}ml) -> "
              f"{len(candidatos)} plantas {candidatos} @ {vol_por_planta}ml c/u -- fuente: {fuente}")
        resueltos += 1

        if args.apply:
            for apodo in candidatos:
                planta_uuid = uuid_by_apodo.get(apodo)
                if not planta_uuid:
                    print(f"  ! planta '{apodo}' no encontrada activa, se salta esa fila")
                    continue
                api_post(
                    base_url, args.token,
                    f"/api/v1/cultivos/{args.slug}/riegos/{r['id']}/plantas/",
                    {"planta_uuid": planta_uuid, "volumen_ml": vol_por_planta},
                )

    print()
    if args.apply:
        print(f"Aplicado via API ({base_url}): {resueltos} riegos completados, {saltados} sin resolver.")
    else:
        print(f"Dry-run: {resueltos} riegos se completarian, {saltados} necesitan revision manual. "
              f"Corre de nuevo con --apply para escribir los cambios.")


if __name__ == "__main__":
    main()
