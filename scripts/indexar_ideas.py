"""
Indexa ideas anadidas manualmente en data/ideas dentro de data/ideas.csv.
Uso: python -m scripts.indexar_ideas
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
from src.db_ideas import Idea, añadir_idea, buscar_por_id, listar_rutas_indexadas


def _normalizar_lista(valor: object) -> str:
    if isinstance(valor, list):
        return ", ".join(str(x).strip() for x in valor if str(x).strip())
    if isinstance(valor, str):
        return valor.strip()
    return ""


def _resumen_simple(texto: str, max_len: int = 180) -> str:
    limpio = " ".join(texto.split())
    if not limpio:
        return "Idea sin contenido"
    return limpio[:max_len] + ("..." if len(limpio) > max_len else "")


def _extraer_metadatos(texto: str) -> dict:
    defaults = {
        "resumen": _resumen_simple(texto),
        "tags": "",
        "categorias": "",
        "presupuesto_aproximado": "",
    }
    prompt = f"""Analiza esta idea de proyecto y responde SOLO en JSON valido.

Campos requeridos:
- resumen: texto breve en espanol (maximo 220 caracteres)
- tags: array de strings cortos
- categorias: array de strings
- presupuesto_aproximado: texto (ej. "15000-20000 EUR") o vacio si no hay datos

Idea:
\"\"\"{texto[:5000]}\"\"\"
"""
    try:
        r = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=90,
        )
        if r.status_code != 200:
            return defaults
        raw = (r.json().get("response") or "").strip()
        inicio = raw.find("{")
        fin = raw.rfind("}")
        if inicio == -1 or fin == -1:
            return defaults
        payload = json.loads(raw[inicio:fin + 1])
        return {
            "resumen": str(payload.get("resumen") or defaults["resumen"]).strip(),
            "tags": _normalizar_lista(payload.get("tags")),
            "categorias": _normalizar_lista(payload.get("categorias")),
            "presupuesto_aproximado": str(payload.get("presupuesto_aproximado") or "").strip(),
        }
    except Exception:
        return defaults


def _generar_id_unico(ruta_rel: str, contenido: str) -> str:
    base = hashlib.sha256(f"{ruta_rel}::{contenido[:1000]}".encode("utf-8")).hexdigest()[:16]
    if buscar_por_id(base) is None:
        return base
    i = 1
    while True:
        candidato = f"{base[:12]}{i:04d}"[:16]
        if buscar_por_id(candidato) is None:
            return candidato
        i += 1


def indexar_ideas() -> int:
    config.CARPETA_IDEAS.mkdir(parents=True, exist_ok=True)
    rutas_existentes = listar_rutas_indexadas()
    indexadas = 0

    archivos = sorted(config.CARPETA_IDEAS.glob("*"))
    for archivo in archivos:
        if not archivo.is_file():
            continue
        if archivo.name == ".gitkeep":
            continue
        if archivo.suffix.lower() not in {".md", ".txt"}:
            continue

        try:
            ruta_rel = archivo.relative_to(config.DIR_PROYECTO).as_posix()
        except Exception:
            ruta_rel = str(archivo)
        if ruta_rel in rutas_existentes:
            continue

        contenido = archivo.read_text(encoding="utf-8").strip()
        if not contenido:
            continue
        metadatos = _extraer_metadatos(contenido)
        idea = Idea(
            id=_generar_id_unico(ruta_rel, contenido),
            resumen=metadatos["resumen"],
            tags=metadatos["tags"],
            categorias=metadatos["categorias"],
            presupuesto_aproximado=metadatos["presupuesto_aproximado"],
            ruta=ruta_rel,
            fecha_ingesta=datetime.now().isoformat(),
            fuente="manual",
        )
        añadir_idea(idea)
        rutas_existentes.add(ruta_rel)
        indexadas += 1
    return indexadas


def main() -> None:
    n = indexar_ideas()
    print(f"Ideas indexadas: {n}")


if __name__ == "__main__":
    main()
