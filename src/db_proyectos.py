"""
Acceso a datos (CSV) para proyectos (modelo híbrido CSV + proyectos/*.md).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_PROYECTO = [
    "id",
    "titulo",
    "fecha_creacion",
    "persona_contacto",
    "email_contacto",
    "presupuesto",
    "tiempo_total",
    "fecha_fin",
    "estado",
    "ruta",
    "fuente",
]

ESTADOS_PROYECTO_VALIDOS = frozenset(
    {"idea", "activo", "en_espera", "presupuestado", "completado", "cancelado"}
)


@dataclass
class Proyecto:
    id: str
    titulo: str
    fecha_creacion: str
    persona_contacto: str
    email_contacto: str
    presupuesto: str
    tiempo_total: str  # minutos totales (entero como texto)
    fecha_fin: str
    estado: str
    ruta: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "fecha_creacion": self.fecha_creacion,
            "persona_contacto": self.persona_contacto,
            "email_contacto": self.email_contacto,
            "presupuesto": self.presupuesto,
            "tiempo_total": self.tiempo_total,
            "fecha_fin": self.fecha_fin,
            "estado": self.estado,
            "ruta": self.ruta,
            "fuente": self.fuente,
        }


def _fila_a_proyecto(fila: dict) -> Proyecto:
    return Proyecto(
        id=fila.get("id", ""),
        titulo=fila.get("titulo", ""),
        fecha_creacion=fila.get("fecha_creacion", ""),
        persona_contacto=fila.get("persona_contacto", ""),
        email_contacto=fila.get("email_contacto", ""),
        presupuesto=fila.get("presupuesto", ""),
        tiempo_total=fila.get("tiempo_total", "0"),
        fecha_fin=fila.get("fecha_fin", ""),
        estado=fila.get("estado", "idea"),
        ruta=fila.get("ruta", ""),
        fuente=fila.get("fuente", "telegram"),
    )


def _asegurar_csv() -> None:
    config.CSV_PROYECTOS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_PROYECTOS.exists():
        return
    with open(config.CSV_PROYECTOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_PROYECTO)
        writer.writeheader()


def leer_proyectos() -> list[Proyecto]:
    _asegurar_csv()
    items: list[Proyecto] = []
    with open(config.CSV_PROYECTOS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_proyecto(fila))
    return items


def escribir_proyectos(items: list[Proyecto]) -> None:
    _asegurar_csv()
    with open(config.CSV_PROYECTOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_PROYECTO)
        writer.writeheader()
        for p in items:
            writer.writerow(p.to_dict())


def añadir_proyecto(p: Proyecto) -> None:
    items = leer_proyectos()
    items.append(p)
    escribir_proyectos(items)


def buscar_por_id(id_buscar: str) -> Proyecto | None:
    for p in leer_proyectos():
        if p.id == id_buscar:
            return p
    return None


def actualizar_proyecto(p: Proyecto) -> bool:
    items = leer_proyectos()
    for i, x in enumerate(items):
        if x.id == p.id:
            items[i] = p
            escribir_proyectos(items)
            return True
    return False


def eliminar_por_id(id_buscar: str) -> Proyecto | None:
    items = leer_proyectos()
    removed: Proyecto | None = None
    rest: list[Proyecto] = []
    for p in items:
        if p.id == id_buscar:
            removed = p
        else:
            rest.append(p)
    if removed is None:
        return None
    escribir_proyectos(rest)
    return removed


def tiempo_total_minutos(p: Proyecto) -> int:
    try:
        return max(0, int((p.tiempo_total or "0").strip() or 0))
    except ValueError:
        return 0
