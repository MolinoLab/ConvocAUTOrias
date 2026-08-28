"""
Tabla puente presupuesto ↔ ideas (1 presupuesto : N ideas).
CSV: id_presupuesto, id_idea.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_VINCULO = ["id_presupuesto", "id_idea"]


@dataclass
class VinculoPresupuestoIdea:
    id_presupuesto: str
    id_idea: str

    def to_dict(self) -> dict:
        return {
            "id_presupuesto": self.id_presupuesto,
            "id_idea": self.id_idea,
        }


def _fila_a_vinculo(fila: dict) -> VinculoPresupuestoIdea:
    return VinculoPresupuestoIdea(
        id_presupuesto=fila.get("id_presupuesto", ""),
        id_idea=fila.get("id_idea", ""),
    )


def _asegurar_csv() -> None:
    config.CSV_PRESUPUESTOS_IDEAS.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_PRESUPUESTOS_IDEAS.exists():
        return
    with open(config.CSV_PRESUPUESTOS_IDEAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_VINCULO)
        writer.writeheader()


def leer_vinculos() -> list[VinculoPresupuestoIdea]:
    _asegurar_csv()
    items: list[VinculoPresupuestoIdea] = []
    with open(config.CSV_PRESUPUESTOS_IDEAS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_vinculo(fila))
    return items


def escribir_vinculos(items: list[VinculoPresupuestoIdea]) -> None:
    _asegurar_csv()
    with open(config.CSV_PRESUPUESTOS_IDEAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_VINCULO)
        writer.writeheader()
        for v in items:
            writer.writerow(v.to_dict())


def listar_ideas_de_presupuesto(id_presupuesto: str) -> list[str]:
    return [
        v.id_idea
        for v in leer_vinculos()
        if v.id_presupuesto == id_presupuesto and v.id_idea
    ]


def listar_presupuestos_de_idea(id_idea: str) -> list[str]:
    return [
        v.id_presupuesto
        for v in leer_vinculos()
        if v.id_idea == id_idea and v.id_presupuesto
    ]


def desvincular_todas(id_presupuesto: str) -> int:
    items = leer_vinculos()
    rest = [v for v in items if v.id_presupuesto != id_presupuesto]
    quitados = len(items) - len(rest)
    if quitados:
        escribir_vinculos(rest)
    return quitados


def vincular_ideas(id_presupuesto: str, ids_idea: list[str]) -> None:
    """Añade vínculos (sin duplicar). No borra los existentes."""
    if not id_presupuesto:
        return
    items = leer_vinculos()
    existentes = {(v.id_presupuesto, v.id_idea) for v in items}
    cambio = False
    for iid in ids_idea:
        iid = (iid or "").strip()
        if not iid:
            continue
        clave = (id_presupuesto, iid)
        if clave in existentes:
            continue
        items.append(VinculoPresupuestoIdea(id_presupuesto=id_presupuesto, id_idea=iid))
        existentes.add(clave)
        cambio = True
    if cambio:
        escribir_vinculos(items)


def reemplazar_ideas(id_presupuesto: str, ids_idea: list[str]) -> None:
    desvincular_todas(id_presupuesto)
    vincular_ideas(id_presupuesto, ids_idea)
