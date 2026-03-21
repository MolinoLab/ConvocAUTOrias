"""
Entradas de diario: CSV índice + un .md por día en data/diario/.
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

CAMPOS_DIARIO = [
    "id",
    "fecha_dia",
    "ruta",
    "fecha_ingesta",
    "fuente",
    "telegram_user",
    "resumen",
]


@dataclass
class EntradaDiario:
    id: str
    fecha_dia: str
    ruta: str
    fecha_ingesta: str
    fuente: str
    telegram_user: str
    resumen: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "fecha_dia": self.fecha_dia,
            "ruta": self.ruta,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
            "telegram_user": self.telegram_user,
            "resumen": self.resumen,
        }


def _fila_a_entrada(fila: dict[str, str]) -> EntradaDiario:
    return EntradaDiario(
        id=fila.get("id", ""),
        fecha_dia=fila.get("fecha_dia", ""),
        ruta=fila.get("ruta", ""),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", ""),
        telegram_user=fila.get("telegram_user", ""),
        resumen=fila.get("resumen", ""),
    )


def _asegurar_csv() -> None:
    config.CARPETA_DIARIO.mkdir(parents=True, exist_ok=True)
    if config.CSV_DIARIO.exists():
        return
    with open(config.CSV_DIARIO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_DIARIO)
        w.writeheader()


def listar() -> list[EntradaDiario]:
    _asegurar_csv()
    out: list[EntradaDiario] = []
    with open(config.CSV_DIARIO, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            out.append(_fila_a_entrada(fila))
    return out


def escribir_todo(items: list[EntradaDiario]) -> None:
    _asegurar_csv()
    with open(config.CSV_DIARIO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_DIARIO)
        w.writeheader()
        for it in items:
            w.writerow(it.to_dict())


def añadir_entrada(
    texto: str,
    *,
    fuente: str,
    telegram_user: str = "",
    fecha_dia: str | None = None,
) -> EntradaDiario:
    limpio = (texto or "").strip()
    if not limpio:
        raise ValueError("texto vacio")

    dia = (fecha_dia or datetime.now().strftime("%Y-%m-%d")).strip()
    ts = datetime.now().isoformat()
    config.CARPETA_DIARIO.mkdir(parents=True, exist_ok=True)
    path_abs = config.CARPETA_DIARIO / f"{dia}.md"
    bloque = f"\n## {ts}\n\n{limpio}\n"
    if path_abs.is_file():
        prev = path_abs.read_text(encoding="utf-8", errors="replace")
        path_abs.write_text(prev + bloque, encoding="utf-8")
    else:
        path_abs.write_text(f"# Diario {dia}\n{bloque}", encoding="utf-8")

    try:
        ruta_rel = path_abs.relative_to(config.DIR_PROYECTO).as_posix()
    except Exception:
        ruta_rel = str(path_abs).replace("\\", "/")

    eid = hashlib.sha256(
        f"{uuid.uuid4()}::diario::{dia}::{ts}".encode("utf-8")
    ).hexdigest()[:16]
    resumen = limpio.replace("\n", " ").strip()
    if len(resumen) > 200:
        resumen = resumen[:197] + "..."

    row = EntradaDiario(
        id=eid,
        fecha_dia=dia,
        ruta=ruta_rel.replace("\\", "/"),
        fecha_ingesta=ts,
        fuente=fuente,
        telegram_user=(telegram_user or "").strip(),
        resumen=resumen,
    )
    items = listar()
    items.append(row)
    escribir_todo(items)
    return row
