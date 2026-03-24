"""
Acceso a memorias (CSV + .md). Esquema: id, resumen, ruta, fecha_ingesta, fuente.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_MEMORIA = [
    "id",
    "resumen",
    "ruta",
    "fecha_ingesta",
    "fuente",
]


@dataclass
class Memoria:
    id: str
    resumen: str
    ruta: str
    fecha_ingesta: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resumen": self.resumen,
            "ruta": self.ruta,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
        }


def _fila_a_memoria(fila: dict) -> Memoria:
    return Memoria(
        id=fila.get("id", ""),
        resumen=fila.get("resumen", ""),
        ruta=fila.get("ruta", ""),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "manual"),
    )


def _asegurar_csv() -> None:
    config.CSV_MEMORIAS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_MEMORIAS.exists():
        return
    with open(config.CSV_MEMORIAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_MEMORIA)
        writer.writeheader()


def leer_memorias() -> list[Memoria]:
    _asegurar_csv()
    memorias: list[Memoria] = []
    with open(config.CSV_MEMORIAS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            memorias.append(_fila_a_memoria(fila))
    return memorias


def escribir_memorias(memorias: list[Memoria]) -> None:
    _asegurar_csv()
    with open(config.CSV_MEMORIAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_MEMORIA)
        writer.writeheader()
        for m in memorias:
            writer.writerow(m.to_dict())


def añadir_memoria(m: Memoria) -> None:
    memorias = leer_memorias()
    memorias.append(m)
    escribir_memorias(memorias)


def buscar_por_id(id_buscar: str) -> Memoria | None:
    for m in leer_memorias():
        if m.id == id_buscar:
            return m
    return None


def actualizar_memoria(m: Memoria) -> bool:
    memorias = leer_memorias()
    for i, x in enumerate(memorias):
        if x.id == m.id:
            memorias[i] = m
            escribir_memorias(memorias)
            return True
    return False


def eliminar_por_id(id_buscar: str) -> Memoria | None:
    memorias = leer_memorias()
    removed: Memoria | None = None
    rest: list[Memoria] = []
    for m in memorias:
        if m.id == id_buscar:
            removed = m
        else:
            rest.append(m)
    if removed is None:
        return None
    escribir_memorias(rest)
    return removed
