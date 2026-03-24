"""
Cola de transcripciones de audio sin acción reconocida (pendientes.csv).
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

CAMPOS_PENDIENTE = [
    "id",
    "texto",
    "user_id",
    "username",
    "fecha_ingesta",
    "fuente",
]


@dataclass
class Pendiente:
    id: str
    texto: str
    user_id: str
    username: str
    fecha_ingesta: str
    fuente: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "texto": self.texto,
            "user_id": self.user_id,
            "username": self.username,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
        }


def _fila_a_pendiente(fila: dict[str, str]) -> Pendiente:
    return Pendiente(
        id=fila.get("id", ""),
        texto=fila.get("texto", ""),
        user_id=fila.get("user_id", ""),
        username=fila.get("username", ""),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "telegram_audio"),
    )


def _asegurar_csv() -> None:
    config.CSV_PENDIENTES.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_PENDIENTES.exists():
        return
    with open(config.CSV_PENDIENTES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_PENDIENTE)
        w.writeheader()


def listar() -> list[Pendiente]:
    _asegurar_csv()
    out: list[Pendiente] = []
    with open(config.CSV_PENDIENTES, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            out.append(_fila_a_pendiente(fila))
    return out


def listar_recientes_primero() -> list[Pendiente]:
    items = listar()
    return sorted(
        items,
        key=lambda p: (p.fecha_ingesta or "", p.id),
        reverse=True,
    )


def escribir_todo(items: list[Pendiente]) -> None:
    _asegurar_csv()
    with open(config.CSV_PENDIENTES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_PENDIENTE)
        w.writeheader()
        for it in items:
            w.writerow(it.to_dict())


def buscar_por_id(id_buscar: str) -> Pendiente | None:
    for x in listar():
        if x.id == id_buscar:
            return x
    return None


def actualizar_pendiente(p: Pendiente) -> bool:
    items = listar()
    for i, x in enumerate(items):
        if x.id == p.id:
            items[i] = p
            escribir_todo(items)
            return True
    return False


def añadir(texto: str, *, user_id: int, username: str, fuente: str) -> Pendiente:
    limpio = (texto or "").strip()
    pid = hashlib.sha256(
        f"{uuid.uuid4()}::pendiente::{limpio[:800]}".encode("utf-8")
    ).hexdigest()[:16]
    p = Pendiente(
        id=pid,
        texto=limpio,
        user_id=str(int(user_id)),
        username=(username or "").strip(),
        fecha_ingesta=datetime.now().isoformat(),
        fuente=fuente,
    )
    items = listar()
    items.append(p)
    escribir_todo(items)
    return p


def eliminar(id_buscar: str) -> bool:
    items = listar()
    nuevos = [x for x in items if x.id != id_buscar]
    if len(nuevos) == len(items):
        return False
    escribir_todo(nuevos)
    return True
