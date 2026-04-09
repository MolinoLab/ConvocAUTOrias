"""
Procesa una convocatoria objetivo y genera un resumen estructurado (JSON + Markdown).
Uso:
  python -m scripts.procesar_convocatoria --url <url>
  python -m scripts.procesar_convocatoria --query "<texto>"
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_resumenes_convocatoria import guardar_resultado
from src.investigacion_convocatoria import (
    descubrir_ediciones_anteriores,
    extraer_datos_clave_desde_html,
    extraer_ejemplos_previos_html,
    generar_resumen_estructurado,
    resolver_convocatoria_objetivo,
)
from src.notifier import enviar_mensaje


def _resultado_id(url_objetivo: str, query: str) -> str:
    seed = f"{datetime.now().isoformat()}::{url_objetivo}::{query}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def ejecutar(url: str | None, query: str | None, chat_id: str | None) -> dict:
    target = resolver_convocatoria_objetivo(url, query)
    objetivo = (target.get("url") or "").strip()
    if not objetivo:
        return {
            "success": False,
            "error": "No se pudo resolver una URL objetivo para la convocatoria.",
            "target": target,
        }

    convocatoria_actual, fuentes_1, adv_1 = extraer_datos_clave_desde_html(objetivo)
    ediciones = descubrir_ediciones_anteriores(objetivo)
    ejemplos, adv_2, fuentes_2 = extraer_ejemplos_previos_html(ediciones)

    rid = _resultado_id(objetivo, query or "")
    fuentes = _dedup_fuentes(fuentes_1 + fuentes_2)
    advertencias = adv_1 + adv_2

    resultado = generar_resumen_estructurado(
        convocatoria_actual=convocatoria_actual,
        ediciones_anteriores=ediciones,
        ejemplos_financiados=ejemplos,
        advertencias=advertencias,
        fuentes=fuentes,
        resultado_id=rid,
    )

    rutas = guardar_resultado(resultado)
    resumen_corto = resultado.get("metadata", {}).get("resumen_corto", "")

    if chat_id and resumen_corto:
        msg = (
            "Investigación de convocatoria completada.\n\n"
            f"{resumen_corto}\n"
            f"Resultado: {rutas['ruta_markdown']}"
        )[:3900]
        enviar_mensaje(msg, chat_id=chat_id)

    return {
        "success": True,
        "resultado_id": rid,
        "ruta_markdown": rutas["ruta_markdown"],
        "ruta_json": rutas["ruta_json"],
        "resumen_corto": resumen_corto,
        "fuentes_count": len(fuentes),
        "warning": "; ".join(advertencias[:3]) if advertencias else "",
    }


def _dedup_fuentes(fuentes: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for f in fuentes:
        u = (f.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(f)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Investigar convocatoria y generar resumen estructurado")
    p.add_argument("--url", default="", help="URL objetivo de la convocatoria")
    p.add_argument("--query", default="", help="Texto para resolver convocatoria por búsqueda")
    p.add_argument("--chat-id", default="", help="Chat de Telegram para notificación opcional")
    args = p.parse_args()

    if not args.url and not args.query:
        print(
            json.dumps(
                {"success": False, "error": "Debes indicar --url o --query."},
                ensure_ascii=False,
            )
        )
        return 2

    out = ejecutar(args.url or None, args.query or None, args.chat_id or None)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
