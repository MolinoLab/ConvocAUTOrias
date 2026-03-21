"""
CSV para investigaciones encoladas desde Telegram (/investiga).
Esquema: id, fecha, estado, concepto, resumen, link.
Estados: pendiente, investigado (listo pero Telegram falló), enviado.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_INVESTIGACION = [
    "id",
    "fecha",
    "estado",
    "concepto",
    "resumen",
    "link",
    "archivo",
]

ESTADOS_INVESTIGACION = {"pendiente", "investigado", "enviado"}


@dataclass
class Investigacion:
    id: str
    fecha: str
    estado: str
    concepto: str
    resumen: str
    link: str
    archivo: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "fecha": self.fecha,
            "estado": self.estado,
            "concepto": self.concepto,
            "resumen": self.resumen,
            "link": self.link,
            "archivo": self.archivo,
        }


def _fila_a_investigacion(fila: dict[str, str]) -> Investigacion:
    return Investigacion(
        id=fila.get("id", ""),
        fecha=fila.get("fecha", ""),
        estado=(fila.get("estado", "pendiente") or "pendiente").lower(),
        concepto=fila.get("concepto", ""),
        resumen=fila.get("resumen", ""),
        link=fila.get("link", ""),
        archivo=(fila.get("archivo") or "").strip(),
    )


def _asegurar_csv() -> None:
    config.CSV_INVESTIGACIONES.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_INVESTIGACIONES.exists():
        return
    with open(config.CSV_INVESTIGACIONES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_INVESTIGACION)
        w.writeheader()


def listar() -> list[Investigacion]:
    _asegurar_csv()
    out: list[Investigacion] = []
    with open(config.CSV_INVESTIGACIONES, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            out.append(_fila_a_investigacion(fila))
    return out


def escribir_todo(items: list[Investigacion]) -> None:
    _asegurar_csv()
    with open(config.CSV_INVESTIGACIONES, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_INVESTIGACION)
        w.writeheader()
        for it in items:
            w.writerow(it.to_dict())


def añadir(inv: Investigacion) -> None:
    items = listar()
    items.append(inv)
    escribir_todo(items)


def actualizar(inv: Investigacion) -> bool:
    items = listar()
    for i, x in enumerate(items):
        if x.id == inv.id:
            items[i] = inv
            escribir_todo(items)
            return True
    return False


def buscar_por_id(id_buscar: str) -> Investigacion | None:
    for x in listar():
        if x.id == id_buscar:
            return x
    return None


def eliminar(id_buscar: str) -> bool:
    items = listar()
    nuevos = [x for x in items if x.id != id_buscar]
    if len(nuevos) == len(items):
        return False
    escribir_todo(nuevos)
    return True
