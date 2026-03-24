"""
Acceso a datos (CSV) para enlaces sin categorizar.
Esquema: id, url, tags, categorias, notas, fecha_ingesta, fuente.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_ENLACE = [
    "id",
    "url",
    "tags",
    "categorias",
    "notas",
    "fecha_ingesta",
    "fuente",
]


@dataclass
class Enlace:
    id: str
    url: str
    tags: str
    categorias: str
    notas: str
    fecha_ingesta: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "tags": self.tags,
            "categorias": self.categorias,
            "notas": self.notas,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
        }


def _fila_a_enlace(fila: dict) -> Enlace:
    return Enlace(
        id=fila.get("id", ""),
        url=fila.get("url", ""),
        tags=fila.get("tags", ""),
        categorias=fila.get("categorias", ""),
        notas=fila.get("notas", ""),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "manual"),
    )


def _asegurar_csv() -> None:
    config.CSV_ENLACES.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_ENLACES.exists():
        return
    with open(config.CSV_ENLACES, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_ENLACE)
        writer.writeheader()


def leer_enlaces() -> list[Enlace]:
    _asegurar_csv()
    items: list[Enlace] = []
    with open(config.CSV_ENLACES, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_enlace(fila))
    return items


def escribir_enlaces(items: list[Enlace]) -> None:
    _asegurar_csv()
    with open(config.CSV_ENLACES, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_ENLACE)
        writer.writeheader()
        for item in items:
            writer.writerow(item.to_dict())


def añadir_enlace(enlace: Enlace) -> None:
    items = leer_enlaces()
    items.append(enlace)
    escribir_enlaces(items)


def buscar_enlace_por_id(id_buscar: str) -> Enlace | None:
    for e in leer_enlaces():
        if e.id == id_buscar:
            return e
    return None


def actualizar_enlace(enlace: Enlace) -> bool:
    items = leer_enlaces()
    for i, x in enumerate(items):
        if x.id == enlace.id:
            items[i] = enlace
            escribir_enlaces(items)
            return True
    return False


def buscar_enlace_por_url(url_buscar: str) -> Enlace | None:
    u = (url_buscar or "").strip()
    if not u:
        return None
    for e in leer_enlaces():
        if e.url.strip() == u:
            return e
    return None


def eliminar_enlace_por_id(id_buscar: str) -> bool:
    items = leer_enlaces()
    nuevos = [x for x in items if x.id != id_buscar]
    if len(nuevos) == len(items):
        return False
    escribir_enlaces(nuevos)
    return True
