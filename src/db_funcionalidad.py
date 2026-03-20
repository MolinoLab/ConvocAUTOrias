"""
Acceso a datos (CSV/SQLite) para funcionalidades pendientes de desarrollo.
Esquema: id, texto, prioridad, estado, fecha_ingesta, fuente.
"""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

CAMPOS_FUNCIONALIDAD = [
    "id",
    "texto",
    "prioridad",
    "estado",
    "fecha_ingesta",
    "fuente",
]

ESTADOS_VALIDOS = {"pendiente", "en_progreso", "hecha"}


@dataclass
class Funcionalidad:
    id: str
    texto: str
    prioridad: int
    estado: str
    fecha_ingesta: str
    fuente: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "texto": self.texto,
            "prioridad": str(self.prioridad),
            "estado": self.estado,
            "fecha_ingesta": self.fecha_ingesta,
            "fuente": self.fuente,
        }


def _fila_a_funcionalidad(fila: dict) -> Funcionalidad:
    try:
        prioridad = int(fila.get("prioridad", 3))
    except (ValueError, TypeError):
        prioridad = 3
    return Funcionalidad(
        id=fila.get("id", ""),
        texto=fila.get("texto", ""),
        prioridad=max(1, min(5, prioridad)),
        estado=fila.get("estado", "pendiente"),
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "manual"),
    )


# --- CSV ---

def _asegurar_csv() -> None:
    config.CSV_FUNCIONALIDAD.parent.mkdir(parents=True, exist_ok=True)
    if config.CSV_FUNCIONALIDAD.exists():
        return
    with open(config.CSV_FUNCIONALIDAD, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_FUNCIONALIDAD)
        writer.writeheader()


def leer_csv() -> list[Funcionalidad]:
    _asegurar_csv()
    items: list[Funcionalidad] = []
    with open(config.CSV_FUNCIONALIDAD, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            items.append(_fila_a_funcionalidad(fila))
    return items


def escribir_csv(items: list[Funcionalidad]) -> None:
    _asegurar_csv()
    with open(config.CSV_FUNCIONALIDAD, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_FUNCIONALIDAD)
        writer.writeheader()
        for item in items:
            writer.writerow(item.to_dict())


def añadir_csv(func: Funcionalidad) -> None:
    items = leer_csv()
    items.append(func)
    escribir_csv(items)


def buscar_por_id_csv(id_buscar: str) -> Funcionalidad | None:
    for item in leer_csv():
        if item.id == id_buscar:
            return item
    return None


def actualizar_csv(func: Funcionalidad) -> bool:
    items = leer_csv()
    for i, item in enumerate(items):
        if item.id == func.id:
            items[i] = func
            escribir_csv(items)
            return True
    return False


def eliminar_csv(id_buscar: str) -> bool:
    items = leer_csv()
    nuevos = [x for x in items if x.id != id_buscar]
    if len(nuevos) == len(items):
        return False
    escribir_csv(nuevos)
    return True


# --- SQLite ---

def _crear_tabla(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS funcionalidad (
            id TEXT PRIMARY KEY,
            texto TEXT NOT NULL,
            prioridad INTEGER DEFAULT 3,
            estado TEXT DEFAULT 'pendiente',
            fecha_ingesta TEXT,
            fuente TEXT
        )
    """)


def _conexion_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_FUNCIONALIDAD)
    conn.row_factory = sqlite3.Row
    _crear_tabla(conn)
    return conn


def leer_sqlite() -> list[Funcionalidad]:
    conn = _conexion_sqlite()
    try:
        cur = conn.execute("SELECT * FROM funcionalidad")
        return [_fila_a_funcionalidad(dict(row)) for row in cur.fetchall()]
    finally:
        conn.close()


def añadir_sqlite(func: Funcionalidad) -> None:
    conn = _conexion_sqlite()
    try:
        conn.execute(
            """INSERT INTO funcionalidad (id, texto, prioridad, estado, fecha_ingesta, fuente)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (func.id, func.texto, func.prioridad, func.estado,
             func.fecha_ingesta, func.fuente),
        )
        conn.commit()
    finally:
        conn.close()


def buscar_por_id_sqlite(id_buscar: str) -> Funcionalidad | None:
    conn = _conexion_sqlite()
    try:
        cur = conn.execute("SELECT * FROM funcionalidad WHERE id = ?", (id_buscar,))
        row = cur.fetchone()
        return _fila_a_funcionalidad(dict(row)) if row else None
    finally:
        conn.close()


def actualizar_sqlite(func: Funcionalidad) -> bool:
    conn = _conexion_sqlite()
    try:
        cur = conn.execute(
            """UPDATE funcionalidad SET texto=?, prioridad=?, estado=?, fecha_ingesta=?, fuente=?
               WHERE id=?""",
            (func.texto, func.prioridad, func.estado,
             func.fecha_ingesta, func.fuente, func.id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def eliminar_sqlite(id_buscar: str) -> bool:
    conn = _conexion_sqlite()
    try:
        cur = conn.execute("DELETE FROM funcionalidad WHERE id = ?", (id_buscar,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --- API unificada (CSV por defecto, SQLite si existe .db) ---

def usar_sqlite() -> bool:
    return config.DB_FUNCIONALIDAD.exists()


def listar() -> list[Funcionalidad]:
    return leer_sqlite() if usar_sqlite() else leer_csv()


def añadir(func: Funcionalidad) -> None:
    if usar_sqlite():
        añadir_sqlite(func)
    else:
        añadir_csv(func)


def buscar_por_id(id_buscar: str) -> Funcionalidad | None:
    if usar_sqlite():
        return buscar_por_id_sqlite(id_buscar)
    return buscar_por_id_csv(id_buscar)


def actualizar(func: Funcionalidad) -> bool:
    if usar_sqlite():
        return actualizar_sqlite(func)
    return actualizar_csv(func)


def eliminar(id_buscar: str) -> bool:
    """Elimina una funcionalidad por id. True si existía y se borró."""
    if usar_sqlite():
        return eliminar_sqlite(id_buscar)
    return eliminar_csv(id_buscar)
