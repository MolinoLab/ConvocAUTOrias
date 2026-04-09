"""
Persistencia de resultados del pipeline de investigación de convocatorias.
Guarda JSON + Markdown y mantiene un índice CSV ligero.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CARPETA_RESUMENES = config.DATA_DIR / "resumenes_convocatoria"
CARPETA_RESUMENES.mkdir(parents=True, exist_ok=True)
CSV_INDICE = config.DATA_DIR / "resumenes_convocatoria.csv"

CAMPOS_INDICE = [
    "id",
    "fecha",
    "nombre",
    "url_objetivo",
    "ruta_json",
    "ruta_markdown",
    "fuentes_count",
    "warning",
]


def guardar_resultado(resultado: dict) -> dict[str, str]:
    meta = resultado.get("metadata", {})
    rid = str(meta.get("resultado_id", "")).strip()
    if not rid:
        raise ValueError("resultado_id no informado en metadata.")

    ruta_json = CARPETA_RESUMENES / f"{rid}.json"
    ruta_md = CARPETA_RESUMENES / f"{rid}.md"

    data_json = dict(resultado)
    markdown = str(data_json.pop("markdown", ""))

    ruta_json.write_text(
        json.dumps(data_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ruta_md.write_text(markdown, encoding="utf-8")

    _append_indice(
        {
            "id": rid,
            "fecha": str(meta.get("creado_en", "")),
            "nombre": str(resultado.get("convocatoria_actual", {}).get("nombre", "")),
            "url_objetivo": str(resultado.get("convocatoria_actual", {}).get("url_objetivo", "")),
            "ruta_json": str(ruta_json),
            "ruta_markdown": str(ruta_md),
            "fuentes_count": str(len(resultado.get("fuentes", []))),
            "warning": "sí" if bool(resultado.get("advertencias")) else "no",
        }
    )

    return {"ruta_json": str(ruta_json), "ruta_markdown": str(ruta_md)}


def _append_indice(row: dict[str, str]) -> None:
    exists = CSV_INDICE.exists()
    with open(CSV_INDICE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_INDICE)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
