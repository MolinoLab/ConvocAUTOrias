"""
Acceso a datos (CSV) para registros de tiempo por proyecto.
Solo puede haber un tiempo activo global (sin fecha_hora_fin).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from .fechas_proyecto import formatear_fecha_hora, minutos_entre, parsear_fecha_hora
from . import db_proyectos

CAMPOS_TIEMPO = [
    "id",
    "id_proyecto",
    "fecha_hora_inicio",
    "fecha_hora_fin",
    "cantidad_tiempo",
]


@dataclass
class Tiempo:
    id: str
    id_proyecto: str
    fecha_hora_inicio: str
    fecha_hora_fin: str
    cantidad_tiempo: str  # minutos como texto; vacío si activo

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "id_proyecto": self.id_proyecto,
            "fecha_hora_inicio": self.fecha_hora_inicio,
            "fecha_hora_fin": self.fecha_hora_fin,
            "cantidad_tiempo": self.cantidad_tiempo,
        }


def _fila_a_tiempo(fila: dict) -> Tiempo:
    return Tiempo(
        id=fila.get("id", ""),
        id_proyecto=fila.get("id_proyecto", ""),
        fecha_hora_inicio=fila.get("fecha_hora_inicio", ""),
        fecha_hora_fin=fila.get("fecha_hora_fin", ""),
        cantidad_tiempo=fila.get("cantidad_tiempo", ""),
    )


def _asegurar_csv() -> None:
    config.CSV_TIEMPOS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_TIEMPOS.exists():
        return
    with open(config.CSV_TIEMPOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_TIEMPO)
        writer.writeheader()


def leer_tiempos() -> list[Tiempo]:
    _asegurar_csv()
    items: list[Tiempo] = []
    with open(config.CSV_TIEMPOS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_tiempo(fila))
    return items


def escribir_tiempos(items: list[Tiempo]) -> None:
    _asegurar_csv()
    with open(config.CSV_TIEMPOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_TIEMPO)
        writer.writeheader()
        for t in items:
            writer.writerow(t.to_dict())


def buscar_por_id(id_buscar: str) -> Tiempo | None:
    for t in leer_tiempos():
        if t.id == id_buscar:
            return t
    return None


def añadir_tiempo(t: Tiempo) -> None:
    items = leer_tiempos()
    items.append(t)
    escribir_tiempos(items)


def actualizar_tiempo(t: Tiempo) -> bool:
    items = leer_tiempos()
    for i, x in enumerate(items):
        if x.id == t.id:
            items[i] = t
            escribir_tiempos(items)
            return True
    return False


def eliminar_por_id(id_buscar: str) -> Tiempo | None:
    items = leer_tiempos()
    removed: Tiempo | None = None
    rest: list[Tiempo] = []
    for t in items:
        if t.id == id_buscar:
            removed = t
        else:
            rest.append(t)
    if removed is None:
        return None
    escribir_tiempos(rest)
    return removed


def eliminar_todos_de_proyecto(id_proyecto: str) -> int:
    """Elimina todos los registros de tiempo de un proyecto. Devuelve cuántos borró."""
    items = leer_tiempos()
    nuevos = [t for t in items if t.id_proyecto != id_proyecto]
    n = len(items) - len(nuevos)
    if n:
        escribir_tiempos(nuevos)
    return n


def es_activo(t: Tiempo) -> bool:
    return not (t.fecha_hora_fin or "").strip()


def buscar_activo_global() -> Tiempo | None:
    for t in leer_tiempos():
        if es_activo(t):
            return t
    return None


def listar_por_proyecto(id_proyecto: str) -> list[Tiempo]:
    return [t for t in leer_tiempos() if t.id_proyecto == id_proyecto]


def suma_minutos_cerrados_proyecto(id_proyecto: str) -> int:
    total = 0
    for t in listar_por_proyecto(id_proyecto):
        if es_activo(t):
            continue
        try:
            total += int((t.cantidad_tiempo or "0").strip() or 0)
        except ValueError:
            continue
    return total


def sincronizar_tiempo_total_proyecto(id_proyecto: str) -> None:
    """Recalcula tiempo_total del proyecto desde registros cerrados."""
    p = db_proyectos.buscar_por_id(id_proyecto)
    if not p:
        return
    mins = suma_minutos_cerrados_proyecto(id_proyecto)
    p.tiempo_total = str(mins)
    db_proyectos.actualizar_proyecto(p)


def cerrar_tiempo(t: Tiempo, fin: datetime) -> bool:
    """Asigna fin, cantidad en minutos y sincroniza proyecto."""
    ini = parsear_fecha_hora(t.fecha_hora_inicio)
    if ini is None:
        return False
    if fin < ini:
        return False
    mins = minutos_entre(ini, fin)
    t.fecha_hora_fin = formatear_fecha_hora(fin)
    t.cantidad_tiempo = str(mins)
    ok = actualizar_tiempo(t)
    if ok:
        sincronizar_tiempo_total_proyecto(t.id_proyecto)
    return ok


def modificar_fin_y_recalcular(t: Tiempo, fin: datetime) -> bool:
    return cerrar_tiempo(t, fin)
