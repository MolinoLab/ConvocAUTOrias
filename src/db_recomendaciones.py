"""
Recomendaciones (artistas, escritores, etc.): CSV local.
"""
from __future__ import annotations

import csv
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS = [
    "id",
    "tipo",
    "nombre",
    "notas",
    "tags",
    "fecha_ingesta",
    "fuente",
    "telegram_user",
]


@dataclass
class Recomendacion:
    id: str
    tipo: str
    nombre: str
    notas: str
    tags: str
    fecha_ingesta: str
    fuente: str
    telegram_user: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "nombre": self.nombre,
            "notas": self.notas,
            "tags": self.tags,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
            "telegram_user": self.telegram_user,
        }


def _fila_a_obj(fila: dict[str, str]) -> Recomendacion:
    return Recomendacion(
        id=fila.get("id", ""),
        tipo=fila.get("tipo", ""),
        nombre=fila.get("nombre", ""),
        notas=fila.get("notas", ""),
        tags=fila.get("tags", ""),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", ""),
        telegram_user=fila.get("telegram_user", ""),
    )


def _asegurar_csv() -> None:
    config.CSV_RECOMENDACIONES.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_RECOMENDACIONES.exists():
        return
    with open(config.CSV_RECOMENDACIONES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()


def listar() -> list[Recomendacion]:
    _asegurar_csv()
    out: list[Recomendacion] = []
    with open(config.CSV_RECOMENDACIONES, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            out.append(_fila_a_obj(fila))
    return out


def escribir_todo(items: list[Recomendacion]) -> None:
    _asegurar_csv()
    with open(config.CSV_RECOMENDACIONES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for it in items:
            w.writerow(it.to_dict())


def buscar_por_id(rid: str) -> Recomendacion | None:
    rid = (rid or "").strip()
    if not rid:
        return None
    for r in listar():
        if r.id == rid:
            return r
    return None


def listar_recientes(limite: int = 80) -> list[Recomendacion]:
    limite = max(1, min(500, int(limite)))
    items = listar()
    items.sort(key=lambda x: (x.fecha_ingesta or ""), reverse=True)
    return items[:limite]


def añadir(
    *,
    tipo: str,
    nombre: str,
    notas: str = "",
    tags: str = "",
    fuente: str = "",
    telegram_user: str = "",
) -> Recomendacion:
    tipo = (tipo or "").strip()
    nombre = (nombre or "").strip()
    if not tipo or not nombre:
        raise ValueError("tipo y nombre obligatorios")
    rid = hashlib.sha256(
        f"{uuid.uuid4()}::rec::{tipo}::{nombre}".encode("utf-8")
    ).hexdigest()[:16]
    r = Recomendacion(
        id=rid,
        tipo=tipo,
        nombre=nombre,
        notas=(notas or "").strip(),
        tags=(tags or "").strip(),
        fecha_ingesta=datetime.now().isoformat(),
        fuente=(fuente or "").strip() or "telegram",
        telegram_user=(telegram_user or "").strip(),
    )
    items = listar()
    items.append(r)
    escribir_todo(items)
    return r


def actualizar(r: Recomendacion) -> bool:
    items = listar()
    for i, x in enumerate(items):
        if x.id == r.id:
            items[i] = r
            escribir_todo(items)
            return True
    return False


def eliminar_por_id(rid: str) -> bool:
    rid = (rid or "").strip()
    if not rid:
        return False
    items = listar()
    nuevos = [x for x in items if x.id != rid]
    if len(nuevos) == len(items):
        return False
    escribir_todo(nuevos)
    return True
