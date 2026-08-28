"""
Filas de facturas en contabilidad.csv (id estable para listar/ver/borrar/modificar).
"""
from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterable

import config

CAMPOS_CSV = [
    "id",
    "numero_factura",
    "fecha_factura",
    "nombre_proveedor",
    "cif_proveedor",
    "direccion_proveedor",
    "base_imponible",
    "iva",
    "total",
    "ruta_nextcloud",
    "fecha_subida",
    "fuente",
]


@dataclass
class FacturaContabilidad:
    id: str
    numero_factura: str
    fecha_factura: str
    nombre_proveedor: str
    cif_proveedor: str
    direccion_proveedor: str
    base_imponible: str
    iva: str
    total: str
    ruta_nextcloud: str
    fecha_subida: str
    fuente: str

    def to_row(self) -> dict[str, str]:
        return {f.name: str(getattr(self, f.name) or "") for f in fields(self)}

    @classmethod
    def from_row(cls, row: dict[str, str]) -> FacturaContabilidad:
        return cls(
            id=(row.get("id") or "").strip(),
            numero_factura=(row.get("numero_factura") or "").strip(),
            fecha_factura=(row.get("fecha_factura") or "").strip(),
            nombre_proveedor=(row.get("nombre_proveedor") or "").strip(),
            cif_proveedor=(row.get("cif_proveedor") or "").strip(),
            direccion_proveedor=(row.get("direccion_proveedor") or "").strip(),
            base_imponible=(row.get("base_imponible") or "").strip(),
            iva=(row.get("iva") or "").strip(),
            total=(row.get("total") or "").strip(),
            ruta_nextcloud=(row.get("ruta_nextcloud") or "").strip(),
            fecha_subida=(row.get("fecha_subida") or "").strip(),
            fuente=(row.get("fuente") or "").strip(),
        )


def _path() -> Path:
    return config.CSV_CONTABILIDAD


def _asegurar_cabecera() -> None:
    p = _path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
            w.writeheader()


def leer_todas() -> list[FacturaContabilidad]:
    p = _path()
    if not p.is_file():
        return []
    out: list[FacturaContabilidad] = []
    with p.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if not row:
                continue
            out.append(FacturaContabilidad.from_row(row))
    return out


def listar_recientes_primero() -> list[FacturaContabilidad]:
    rows = leer_todas()
    rows.sort(key=lambda x: (x.fecha_subida or "", x.id), reverse=True)
    return rows


def buscar_por_id(fid: str) -> FacturaContabilidad | None:
    fid = (fid or "").strip()
    if not fid:
        return None
    for r in leer_todas():
        if r.id == fid:
            return r
    return None


def _escribir_todas(rows: Iterable[FacturaContabilidad]) -> None:
    _asegurar_cabecera()
    p = _path()
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row.to_row())


def añadir_factura(
    *,
    numero_factura: str = "",
    fecha_factura: str = "",
    nombre_proveedor: str = "",
    cif_proveedor: str = "",
    direccion_proveedor: str = "",
    base_imponible: str = "",
    iva: str = "",
    total: str = "",
    ruta_nextcloud: str = "",
    fecha_subida: str = "",
    fuente: str = "telegram",
) -> FacturaContabilidad:
    _asegurar_cabecera()
    fid = uuid.uuid4().hex[:16]
    row = FacturaContabilidad(
        id=fid,
        numero_factura=numero_factura,
        fecha_factura=fecha_factura,
        nombre_proveedor=nombre_proveedor,
        cif_proveedor=cif_proveedor,
        direccion_proveedor=direccion_proveedor,
        base_imponible=base_imponible,
        iva=iva,
        total=total,
        ruta_nextcloud=ruta_nextcloud,
        fecha_subida=fecha_subida,
        fuente=fuente,
    )
    todas = leer_todas()
    todas.append(row)
    _escribir_todas(todas)
    return row


def eliminar_por_id(fid: str) -> bool:
    fid = (fid or "").strip()
    if not fid:
        return False
    todas = leer_todas()
    nueva = [r for r in todas if r.id != fid]
    if len(nueva) == len(todas):
        return False
    _escribir_todas(nueva)
    return True


def actualizar_campos(fid: str, cambios: dict[str, str]) -> bool:
    """Solo claves presentes en FacturaContabilidad (excepto id)."""
    fid = (fid or "").strip()
    if not fid or not cambios:
        return False
    permitidas = {f.name for f in fields(FacturaContabilidad)} - {"id"}
    todas = leer_todas()
    ok = False
    nuevas: list[FacturaContabilidad] = []
    for r in todas:
        if r.id != fid:
            nuevas.append(r)
            continue
        ok = True
        d = r.to_row()
        for k, v in cambios.items():
            if k in permitidas:
                d[k] = v if v is not None else ""
        nuevas.append(FacturaContabilidad.from_row(d))
    if not ok:
        return False
    _escribir_todas(nuevas)
    return True


# Campos editables en /modfactura (orden del menú)
CAMPOS_EDITABLES_MOD: list[tuple[str, str]] = [
    ("numero_factura", "Número factura"),
    ("fecha_factura", "Fecha factura (YYYY-MM-DD)"),
    ("nombre_proveedor", "Nombre proveedor"),
    ("cif_proveedor", "CIF proveedor"),
    ("direccion_proveedor", "Dirección proveedor"),
    ("base_imponible", "Base imponible"),
    ("iva", "IVA"),
    ("total", "Total"),
    ("ruta_nextcloud", "Ruta Nextcloud (bajo files del usuario WebDAV)"),
]


def nombre_archivo_seguro(nombre: str) -> str:
    base = (nombre or "").strip() or "factura"
    base = re.sub(r"[^\w.\-]", "_", base, flags=re.UNICODE)
    if len(base) > 120:
        base = base[:120]
    return base or "factura"
