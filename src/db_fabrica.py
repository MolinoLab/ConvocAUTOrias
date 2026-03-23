"""
Registro de ítems de fabricación (CSV): enlace a tarjeta Deck columna Fabricar.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_FABRICA = [
    "id",
    "titulo",
    "medidas",
    "fecha_due",
    "tipo",
    "notas",
    "board_id",
    "stack_id",
    "card_id",
    "fecha_creacion",
    "fuente",
]


@dataclass
class ItemFabrica:
    id: str
    titulo: str
    medidas: str
    fecha_due: str
    tipo: str
    notas: str
    board_id: str
    stack_id: str
    card_id: str
    fecha_creacion: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "medidas": self.medidas,
            "fecha_due": self.fecha_due,
            "tipo": self.tipo,
            "notas": self.notas,
            "board_id": self.board_id,
            "stack_id": self.stack_id,
            "card_id": self.card_id,
            "fecha_creacion": self.fecha_creacion,
            "fuente": self.fuente,
        }


def _fila_a_item(fila: dict) -> ItemFabrica:
    return ItemFabrica(
        id=fila.get("id", ""),
        titulo=fila.get("titulo", ""),
        medidas=fila.get("medidas", ""),
        fecha_due=fila.get("fecha_due", ""),
        tipo=fila.get("tipo", ""),
        notas=fila.get("notas", ""),
        board_id=fila.get("board_id", ""),
        stack_id=fila.get("stack_id", ""),
        card_id=fila.get("card_id", ""),
        fecha_creacion=fila.get("fecha_creacion", ""),
        fuente=fila.get("fuente", ""),
    )


def _asegurar_csv() -> None:
    config.CSV_FABRICA.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_FABRICA.exists():
        return
    with open(config.CSV_FABRICA, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_FABRICA)
        writer.writeheader()


def leer_fabrica() -> list[ItemFabrica]:
    _asegurar_csv()
    items: list[ItemFabrica] = []
    with open(config.CSV_FABRICA, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_item(fila))
    return items


def escribir_fabrica(items: list[ItemFabrica]) -> None:
    _asegurar_csv()
    with open(config.CSV_FABRICA, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_FABRICA)
        writer.writeheader()
        for it in items:
            writer.writerow(it.to_dict())


def añadir_item(it: ItemFabrica) -> None:
    items = leer_fabrica()
    items.append(it)
    escribir_fabrica(items)


def buscar_por_id(id_buscar: str) -> ItemFabrica | None:
    for it in leer_fabrica():
        if it.id == id_buscar:
            return it
    return None


def eliminar_por_id(id_buscar: str) -> ItemFabrica | None:
    items = leer_fabrica()
    removed: ItemFabrica | None = None
    rest: list[ItemFabrica] = []
    for it in items:
        if it.id == id_buscar:
            removed = it
        else:
            rest.append(it)
    if removed is None:
        return None
    escribir_fabrica(rest)
    return removed


def actualizar_campos(id_buscar: str, campos: dict[str, str]) -> bool:
    items = leer_fabrica()
    ok = False
    for i, it in enumerate(items):
        if it.id == id_buscar:
            d = it.to_dict()
            for k, v in campos.items():
                if k in CAMPOS_FABRICA and k != "id":
                    d[k] = v
            items[i] = ItemFabrica(**{c: str(d.get(c, "") or "") for c in CAMPOS_FABRICA})
            ok = True
            break
    if ok:
        escribir_fabrica(items)
    return ok
