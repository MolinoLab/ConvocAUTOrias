"""
Acceso a datos (CSV) para presupuestos (modelo híbrido CSV + presupuestos/*.md).
Relación 1:1 con proyectos vía id_proyecto.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_PRESUPUESTO = [
    "id",
    "id_proyecto",
    "titulo",
    "descripcion",
    "lugar",
    "necesidades_tecnicas",
    "jornadas",
    "precio_dia",
    "modo_desplazamiento",
    "km_ida",
    "coste_desplazamiento",
    "noches_alojamiento",
    "coste_alojamiento",
    "total_aproximado",
    "ruta",
    "fecha_creacion",
    "fuente",
]

MODOS_DESPLAZAMIENTO_VALIDOS = frozenset(
    {"ninguno", "ida_vuelta_diario", "ida_vuelta_unico", "alojamiento"}
)


@dataclass
class Presupuesto:
    id: str
    id_proyecto: str
    titulo: str
    descripcion: str
    lugar: str
    necesidades_tecnicas: str
    jornadas: str
    precio_dia: str
    modo_desplazamiento: str
    km_ida: str
    coste_desplazamiento: str
    noches_alojamiento: str
    coste_alojamiento: str
    total_aproximado: str
    ruta: str
    fecha_creacion: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "id_proyecto": self.id_proyecto,
            "titulo": self.titulo,
            "descripcion": self.descripcion,
            "lugar": self.lugar,
            "necesidades_tecnicas": self.necesidades_tecnicas,
            "jornadas": self.jornadas,
            "precio_dia": self.precio_dia,
            "modo_desplazamiento": self.modo_desplazamiento,
            "km_ida": self.km_ida,
            "coste_desplazamiento": self.coste_desplazamiento,
            "noches_alojamiento": self.noches_alojamiento,
            "coste_alojamiento": self.coste_alojamiento,
            "total_aproximado": self.total_aproximado,
            "ruta": self.ruta,
            "fecha_creacion": self.fecha_creacion,
            "fuente": self.fuente,
        }


def _fila_a_presupuesto(fila: dict) -> Presupuesto:
    return Presupuesto(
        id=fila.get("id", ""),
        id_proyecto=fila.get("id_proyecto", ""),
        titulo=fila.get("titulo", ""),
        descripcion=fila.get("descripcion", ""),
        lugar=fila.get("lugar", ""),
        necesidades_tecnicas=fila.get("necesidades_tecnicas", ""),
        jornadas=fila.get("jornadas", "0"),
        precio_dia=fila.get("precio_dia", ""),
        modo_desplazamiento=fila.get("modo_desplazamiento", "ninguno") or "ninguno",
        km_ida=fila.get("km_ida", ""),
        coste_desplazamiento=fila.get("coste_desplazamiento", "0"),
        noches_alojamiento=fila.get("noches_alojamiento", "0"),
        coste_alojamiento=fila.get("coste_alojamiento", "0"),
        total_aproximado=fila.get("total_aproximado", "0"),
        ruta=fila.get("ruta", ""),
        fecha_creacion=fila.get("fecha_creacion", ""),
        fuente=fila.get("fuente", "telegram_presu"),
    )


def _asegurar_csv() -> None:
    config.CSV_PRESUPUESTOS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_PRESUPUESTOS.exists():
        return
    with open(config.CSV_PRESUPUESTOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_PRESUPUESTO)
        writer.writeheader()


def leer_presupuestos() -> list[Presupuesto]:
    _asegurar_csv()
    items: list[Presupuesto] = []
    with open(config.CSV_PRESUPUESTOS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_presupuesto(fila))
    return items


def escribir_presupuestos(items: list[Presupuesto]) -> None:
    _asegurar_csv()
    with open(config.CSV_PRESUPUESTOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_PRESUPUESTO)
        writer.writeheader()
        for p in items:
            writer.writerow(p.to_dict())


def añadir_presupuesto(p: Presupuesto) -> None:
    items = leer_presupuestos()
    items.append(p)
    escribir_presupuestos(items)


def buscar_por_id(id_buscar: str) -> Presupuesto | None:
    for p in leer_presupuestos():
        if p.id == id_buscar:
            return p
    return None


def buscar_por_id_proyecto(id_proyecto: str) -> Presupuesto | None:
    if not (id_proyecto or "").strip():
        return None
    for p in leer_presupuestos():
        if p.id_proyecto == id_proyecto:
            return p
    return None


def actualizar_presupuesto(p: Presupuesto) -> bool:
    items = leer_presupuestos()
    for i, x in enumerate(items):
        if x.id == p.id:
            items[i] = p
            escribir_presupuestos(items)
            return True
    return False


def eliminar_por_id(id_buscar: str) -> Presupuesto | None:
    items = leer_presupuestos()
    removed: Presupuesto | None = None
    rest: list[Presupuesto] = []
    for p in items:
        if p.id == id_buscar:
            removed = p
        else:
            rest.append(p)
    if removed is None:
        return None
    escribir_presupuestos(rest)
    return removed
