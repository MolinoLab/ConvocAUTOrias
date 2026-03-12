"""
Acceso a datos (CSV) para ideas en modelo hibrido.
Esquema: id, resumen, tags, categorias, presupuesto_aproximado, ruta, fecha_ingesta, fuente.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_IDEA = [
    "id",
    "resumen",
    "tags",
    "categorias",
    "presupuesto_aproximado",
    "ruta",
    "fecha_ingesta",
    "fuente",
]


@dataclass
class Idea:
    id: str
    resumen: str
    tags: str
    categorias: str
    presupuesto_aproximado: str
    ruta: str
    fecha_ingesta: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resumen": self.resumen,
            "tags": self.tags,
            "categorias": self.categorias,
            "presupuesto_aproximado": self.presupuesto_aproximado,
            "ruta": self.ruta,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
        }


def _fila_a_idea(fila: dict) -> Idea:
    return Idea(
        id=fila.get("id", ""),
        resumen=fila.get("resumen", ""),
        tags=fila.get("tags", ""),
        categorias=fila.get("categorias", ""),
        presupuesto_aproximado=fila.get("presupuesto_aproximado", ""),
        ruta=fila.get("ruta", ""),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "manual"),
    )


def _asegurar_csv() -> None:
    config.CSV_IDEAS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_IDEAS.exists():
        return
    with open(config.CSV_IDEAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_IDEA)
        writer.writeheader()


def leer_ideas() -> list[Idea]:
    _asegurar_csv()
    ideas: list[Idea] = []
    with open(config.CSV_IDEAS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            ideas.append(_fila_a_idea(fila))
    return ideas


def escribir_ideas(ideas: list[Idea]) -> None:
    _asegurar_csv()
    with open(config.CSV_IDEAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_IDEA)
        writer.writeheader()
        for idea in ideas:
            writer.writerow(idea.to_dict())


def añadir_idea(idea: Idea) -> None:
    ideas = leer_ideas()
    ideas.append(idea)
    escribir_ideas(ideas)


def buscar_por_id(id_buscar: str) -> Idea | None:
    for idea in leer_ideas():
        if idea.id == id_buscar:
            return idea
    return None


def buscar_por_ruta(ruta_buscar: str) -> Idea | None:
    for idea in leer_ideas():
        if idea.ruta == ruta_buscar:
            return idea
    return None


def listar_rutas_indexadas() -> set[str]:
    return {idea.ruta for idea in leer_ideas() if idea.ruta}
