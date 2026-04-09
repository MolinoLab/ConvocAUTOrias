"""
Acceso a datos (CSV/SQLite) para convocatorias.
Esquema ampliado: investigación profunda, estados sin bucle de reprocesado.
"""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

# Estados nuevos: pendiente_investigacion, investigacion_ok, investigacion_parcial
# "pendiente" (legacy) se trata como pendiente_investigacion en worker y listados.
CAMPOS = [
    "id",
    "url",
    "titulo",
    "descripcion",
    "plazo_fin",
    "requisitos",
    "estado",
    "fecha_ingesta",
    "fuente",
    "investigacion_id",
    "investigacion_fecha",
    "investigacion_version",
    "investigacion_intentos",
]


@dataclass
class Convocatoria:
    """Modelo de una convocatoria."""
    id: str
    url: str
    titulo: str
    descripcion: str
    plazo_fin: str
    requisitos: str
    estado: str
    fecha_ingesta: str
    fuente: str
    investigacion_id: str = ""
    investigacion_fecha: str = ""
    investigacion_version: str = ""
    investigacion_intentos: str = ""

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _fila_a_convocatoria(fila: dict) -> Convocatoria:
    """Convierte una fila dict a Convocatoria (columnas opcionales en CSV antiguo)."""
    return Convocatoria(
        id=fila.get("id", ""),
        url=fila.get("url", ""),
        titulo=fila.get("titulo", ""),
        descripcion=fila.get("descripcion", ""),
        plazo_fin=fila.get("plazo_fin", ""),
        requisitos=fila.get("requisitos", ""),
        estado=(fila.get("estado", "") or "pendiente").strip().lower() or "pendiente",
        fecha_ingesta=fila.get("fecha_ingesta", ""),
        fuente=fila.get("fuente", "manual"),
        investigacion_id=(fila.get("investigacion_id") or "").strip(),
        investigacion_fecha=(fila.get("investigacion_fecha") or "").strip(),
        investigacion_version=(fila.get("investigacion_version") or "").strip(),
        investigacion_intentos=(fila.get("investigacion_intentos") or "0").strip() or "0",
    )


def es_convocatoria_en_seguimiento(estado: str) -> bool:
    """Convocatorias que deben aparecer en /listconvo, CalDAV y revisión de plazos."""
    e = (estado or "").strip().lower()
    return e in (
        "pendiente",
        "pendiente_investigacion",
        "investigacion_ok",
        "investigacion_parcial",
    )


def _parse_intentos(s: str) -> int:
    try:
        return max(0, int((s or "0").strip()))
    except ValueError:
        return 0


def debe_investigar_convocatoria(conv: Convocatoria) -> bool:
    """True si el worker debe intentar investigación profunda en este ciclo."""
    e = (conv.estado or "").strip().lower()
    if e == "investigacion_ok":
        return False
    if e in ("pendiente", "pendiente_investigacion", ""):
        return True
    if e == "investigacion_parcial":
        if _parse_intentos(conv.investigacion_intentos) >= config.CONVOCATORIA_MAX_INVESTIGACION_INTENTOS:
            return False
        fecha_s = (conv.investigacion_fecha or "").strip()
        if not fecha_s:
            return True
        try:
            dt = datetime.fromisoformat(fecha_s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = (now - dt).total_seconds()
            return delta >= float(config.CONVOCATORIA_INVESTIGACION_COOLDOWN_SEC)
        except ValueError:
            return True
    return False


def listar_pendientes_investigacion() -> list[Convocatoria]:
    """Convocatorias candidatas a investigación profunda (respeta intentos y cooldown)."""
    return [c for c in listar() if debe_investigar_convocatoria(c)]


def resultado_id_estable_para_convocatoria(conv_id: str) -> str:
    """ID determinista del JSON/MD de investigación asociado a una fila de convocatoria."""
    import hashlib

    return hashlib.sha256(f"convocatoria::{conv_id}".encode("utf-8")).hexdigest()[:16]


# --- CSV ---


def leer_csv() -> list[Convocatoria]:
    """Lee todas las convocatorias desde el CSV."""
    if not config.CSV_CONVOCATORIAS.exists():
        return []
    convocatorias = []
    with open(config.CSV_CONVOCATORIAS, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for fila in reader:
            convocatorias.append(_fila_a_convocatoria(fila))
    return convocatorias


def escribir_csv(convocatorias: list[Convocatoria]) -> None:
    """Escribe todas las convocatorias al CSV."""
    config.CSV_CONVOCATORIAS.parent.mkdir(parents=True, exist_ok=True)
    with open(config.CSV_CONVOCATORIAS, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        for c in convocatorias:
            writer.writerow(c.to_dict())


def añadir_csv(conv: Convocatoria) -> None:
    """Añade una convocatoria al CSV."""
    convocatorias = leer_csv()
    convocatorias.append(conv)
    escribir_csv(convocatorias)


def buscar_por_id_csv(id_buscar: str) -> Convocatoria | None:
    """Busca una convocatoria por ID en CSV."""
    for c in leer_csv():
        if c.id == id_buscar:
            return c
    return None


def actualizar_csv(conv: Convocatoria) -> bool:
    """Actualiza una convocatoria existente en CSV. Retorna True si se encontró."""
    convocatorias = leer_csv()
    for i, c in enumerate(convocatorias):
        if c.id == conv.id:
            convocatorias[i] = conv
            escribir_csv(convocatorias)
            return True
    return False


def eliminar_por_id_csv(id_buscar: str) -> Convocatoria | None:
    convocatorias = leer_csv()
    removed: Convocatoria | None = None
    rest: list[Convocatoria] = []
    for c in convocatorias:
        if c.id == id_buscar:
            removed = c
        else:
            rest.append(c)
    if removed is None:
        return None
    escribir_csv(rest)
    return removed


# --- SQLite ---

_SQLITE_COLS: list[tuple[str, str]] = [
    ("investigacion_id", "TEXT"),
    ("investigacion_fecha", "TEXT"),
    ("investigacion_version", "TEXT"),
    ("investigacion_intentos", "TEXT"),
]


def _crear_tabla(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS convocatorias (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            titulo TEXT,
            descripcion TEXT,
            plazo_fin TEXT,
            requisitos TEXT,
            estado TEXT DEFAULT 'pendiente',
            fecha_ingesta TEXT,
            fuente TEXT
        )
    """)


def _migrar_sqlite_columnas(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(convocatorias)")
    existentes = {row[1] for row in cur.fetchall()}
    for nombre, sql_type in _SQLITE_COLS:
        if nombre not in existentes:
            conn.execute(
                f"ALTER TABLE convocatorias ADD COLUMN {nombre} {sql_type} DEFAULT ''"
            )


def _conexion_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_SQLITE)
    conn.row_factory = sqlite3.Row
    _crear_tabla(conn)
    _migrar_sqlite_columnas(conn)
    conn.commit()
    return conn


def leer_sqlite() -> list[Convocatoria]:
    """Lee todas las convocatorias desde SQLite."""
    conn = _conexion_sqlite()
    try:
        cur = conn.execute("SELECT * FROM convocatorias")
        return [_fila_a_convocatoria(dict(row)) for row in cur.fetchall()]
    finally:
        conn.close()


def añadir_sqlite(conv: Convocatoria) -> None:
    """Añade una convocatoria a SQLite."""
    conn = _conexion_sqlite()
    try:
        conn.execute(
            """INSERT INTO convocatorias (
                id, url, titulo, descripcion, plazo_fin, requisitos, estado, fecha_ingesta, fuente,
                investigacion_id, investigacion_fecha, investigacion_version, investigacion_intentos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                conv.id,
                conv.url,
                conv.titulo,
                conv.descripcion,
                conv.plazo_fin,
                conv.requisitos,
                conv.estado,
                conv.fecha_ingesta,
                conv.fuente,
                conv.investigacion_id,
                conv.investigacion_fecha,
                conv.investigacion_version,
                conv.investigacion_intentos,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def buscar_por_id_sqlite(id_buscar: str) -> Convocatoria | None:
    """Busca una convocatoria por ID en SQLite."""
    conn = _conexion_sqlite()
    try:
        cur = conn.execute("SELECT * FROM convocatorias WHERE id = ?", (id_buscar,))
        row = cur.fetchone()
        return _fila_a_convocatoria(dict(row)) if row else None
    finally:
        conn.close()


def actualizar_sqlite(conv: Convocatoria) -> bool:
    """Actualiza una convocatoria en SQLite. Retorna True si se encontró."""
    conn = _conexion_sqlite()
    try:
        cur = conn.execute(
            """UPDATE convocatorias SET url=?, titulo=?, descripcion=?, plazo_fin=?, requisitos=?,
               estado=?, fecha_ingesta=?, fuente=?, investigacion_id=?, investigacion_fecha=?,
               investigacion_version=?, investigacion_intentos=? WHERE id=?""",
            (
                conv.url,
                conv.titulo,
                conv.descripcion,
                conv.plazo_fin,
                conv.requisitos,
                conv.estado,
                conv.fecha_ingesta,
                conv.fuente,
                conv.investigacion_id,
                conv.investigacion_fecha,
                conv.investigacion_version,
                conv.investigacion_intentos,
                conv.id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def eliminar_por_id_sqlite(id_buscar: str) -> Convocatoria | None:
    conv = buscar_por_id_sqlite(id_buscar)
    if not conv:
        return None
    conn = _conexion_sqlite()
    try:
        cur = conn.execute("DELETE FROM convocatorias WHERE id = ?", (id_buscar,))
        conn.commit()
        if cur.rowcount > 0:
            return conv
        return None
    finally:
        conn.close()


# --- API unificada (usa CSV por defecto) ---


def usar_sqlite() -> bool:
    """True si existe convocatorias.db y debe usarse SQLite."""
    return config.DB_SQLITE.exists()


def listar() -> list[Convocatoria]:
    """Lista todas las convocatorias (CSV o SQLite según exista .db)."""
    return leer_sqlite() if usar_sqlite() else leer_csv()


def añadir(conv: Convocatoria) -> None:
    """Añade una convocatoria."""
    if usar_sqlite():
        añadir_sqlite(conv)
    else:
        añadir_csv(conv)


def buscar_por_id(id_buscar: str) -> Convocatoria | None:
    """Busca por ID."""
    if usar_sqlite():
        return buscar_por_id_sqlite(id_buscar)
    return buscar_por_id_csv(id_buscar)


def actualizar(conv: Convocatoria) -> bool:
    """Actualiza una convocatoria."""
    if usar_sqlite():
        return actualizar_sqlite(conv)
    return actualizar_csv(conv)


def eliminar_por_id(id_buscar: str) -> Convocatoria | None:
    """Elimina por ID. Retorna la convocatoria eliminada o None."""
    if usar_sqlite():
        return eliminar_por_id_sqlite(id_buscar)
    return eliminar_por_id_csv(id_buscar)
