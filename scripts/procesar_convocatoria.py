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
from src.investigacion_convocatoria import construir_investigacion_convocatoria, resolver_convocatoria_objetivo
from src.notifier import enviar_mensaje


def _resultado_id(url_objetivo: str, query: str) -> str:
    seed = f"{datetime.now().isoformat()}::{url_objetivo}::{query}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def ejecutar(
    url: str | None,
    query: str | None,
    chat_id: str | None,
    *,
    resultado_id: str | None = None,
    append_indice: bool = True,
) -> dict:
    target = resolver_convocatoria_objetivo(url, query)
    objetivo = (target.get("url") or "").strip()
    if not objetivo:
        return {
            "success": False,
            "error": "No se pudo resolver una URL objetivo para la convocatoria.",
            "target": target,
        }

    rid = resultado_id or _resultado_id(objetivo, query or "")
    resultado = construir_investigacion_convocatoria(objetivo, rid, query=query or "")
    fuentes = resultado.get("fuentes") or []
    advertencias = resultado.get("advertencias") or []

    rutas = guardar_resultado(resultado, append_indice=append_indice)
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
