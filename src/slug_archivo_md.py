"""
Nombres de archivo .md legibles (pocas palabras) para ideas, proyectos, memorias, etc.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.db_contabilidad import nombre_archivo_seguro


def texto_a_slug_palabras(texto: str, max_palabras: int = 5) -> str:
    limpio = " ".join((texto or "").split())
    palabras = re.findall(r"[\wáéíóúñüÁÉÍÓÚÑÜ]+", limpio, re.UNICODE)[:max_palabras]
    if not palabras:
        return "nota"
    joined = "_".join(palabras)
    base = nombre_archivo_seguro(joined).strip("._") or "nota"
    if len(base) > 100:
        base = base[:100].rstrip("._") or "nota"
    return base


def elegir_path_md_unico(carpeta: Path, slug_base: str, id_interno: str) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo_seguro(slug_base).strip("._") or "nota"
    if len(base) > 100:
        base = base[:100].rstrip("._") or "nota"
    candidato = carpeta / f"{base}.md"
    if not candidato.exists():
        return candidato
    suf = (id_interno or "x")[:4]
    alt = carpeta / f"{base}_{suf}.md"
    if not alt.exists():
        return alt
    suf8 = (id_interno or "x")[:16]
    return carpeta / f"{base}_{suf8}.md"
