"""
Registro de huevos (CSV): fecha del día, cantidad, ingesta y fuente.
"""
from __future__ import annotations

import csv
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_HUEVO = [
    "id",
    "fecha",
    "cantidad",
    "fecha_ingesta",
    "fuente",
]


@dataclass
class RegistroHuevo:
    id: str
    fecha: str  # YYYY-MM-DD (día al que aplica la cantidad)
    cantidad: int
    fecha_ingesta: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fecha": self.fecha,
            "cantidad": str(self.cantidad),
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
        }


def _fila_a_registro(fila: dict) -> RegistroHuevo:
    try:
        cantidad = int(fila.get("cantidad", 0))
    except (ValueError, TypeError):
        cantidad = 0
    return RegistroHuevo(
        id=fila.get("id", ""),
        fecha=fila.get("fecha", ""),
        cantidad=max(0, cantidad),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "manual"),
    )


def _asegurar_csv() -> None:
    config.CSV_HUEVOS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_HUEVOS.exists():
        return
    with open(config.CSV_HUEVOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_HUEVO)
        writer.writeheader()


def leer_todos() -> list[RegistroHuevo]:
    _asegurar_csv()
    items: list[RegistroHuevo] = []
    with open(config.CSV_HUEVOS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_registro(fila))
    return items


def escribir_todos(items: list[RegistroHuevo]) -> None:
    _asegurar_csv()
    with open(config.CSV_HUEVOS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_HUEVO)
        writer.writeheader()
        for item in items:
            writer.writerow(item.to_dict())


def añadir(cantidad: int, fecha_dia: str, fuente: str) -> RegistroHuevo:
    """fecha_dia: YYYY-MM-DD"""
    reg_id = hashlib.sha256(
        f"{uuid.uuid4()}::{fecha_dia}::{cantidad}".encode("utf-8")
    ).hexdigest()[:16]
    reg = RegistroHuevo(
        id=reg_id,
        fecha=fecha_dia,
        cantidad=cantidad,
        fecha_ingesta=datetime.now().isoformat(),
        fuente=fuente,
    )
    items = leer_todos()
    items.append(reg)
    escribir_todos(items)
    return reg


def total_cantidad_en_fecha(fecha_dia: str) -> int:
    """Suma todas las cantidades registradas para fecha_dia (YYYY-MM-DD)."""
    fecha_dia = (fecha_dia or "").strip()
    if not fecha_dia:
        return 0
    total = 0
    for r in leer_todos():
        if r.fecha.strip() == fecha_dia:
            total += r.cantidad
    return total


def buscar_por_id(id_buscar: str) -> RegistroHuevo | None:
    id_buscar = (id_buscar or "").strip()
    if not id_buscar:
        return None
    for r in leer_todos():
        if r.id == id_buscar:
            return r
    return None


def actualizar_registro(reg: RegistroHuevo) -> bool:
    items = leer_todos()
    for i, r in enumerate(items):
        if r.id == reg.id:
            items[i] = reg
            escribir_todos(items)
            return True
    return False


def eliminar_por_id(id_buscar: str) -> bool:
    id_buscar = (id_buscar or "").strip()
    if not id_buscar:
        return False
    items = leer_todos()
    nuevos = [r for r in items if r.id != id_buscar]
    if len(nuevos) == len(items):
        return False
    escribir_todos(nuevos)
    return True


def listar_registros_recientes(limite: int = 40) -> list[RegistroHuevo]:
    limite = max(1, min(500, int(limite)))
    todos = leer_todos()
    todos.sort(key=lambda r: (r.fecha_ingesta or ""), reverse=True)
    return todos[:limite]


def resumen_ultimos_dias_desde_hoy(num_dias: int) -> list[tuple[str, int]]:
    """
    Devuelve lista (fecha_YYYY-MM-DD, total_cantidad) desde hoy hacia atrás,
    num_dias filas (incluye hoy). Días sin registros aparecen con cantidad 0.
    """
    num_dias = max(1, min(366, int(num_dias)))
    hoy = datetime.now().date()
    registros = leer_todos()
    por_dia: dict[datetime.date, int] = {}
    for r in registros:
        try:
            d = datetime.strptime(r.fecha.strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        por_dia[d] = por_dia.get(d, 0) + r.cantidad

    resultado: list[tuple[str, int]] = []
    for i in range(num_dias):
        d = hoy - timedelta(days=i)
        total = por_dia.get(d, 0)
        resultado.append((d.strftime("%Y-%m-%d"), total))
    return resultado
