"""
Parseo y clasificación de plazos de convocatorias.
Centraliza la lógica para interpretar el campo plazo_fin (texto libre)
y determinar si una convocatoria es futura.
"""
from __future__ import annotations

import re
from datetime import datetime

MESES_ABREV: dict[str, int] = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

MESES_LARGO: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

_MESES_LARGO_RE = "|".join(MESES_LARGO)
_MESES_ABREV_RE = "|".join(MESES_ABREV)


def _safe_date(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day)
    except ValueError:
        try:
            return datetime(year, month, min(day, 28))
        except ValueError:
            return None


def parsear_plazo(plazo_texto: str) -> datetime | None:
    """
    Intenta interpretar plazo_fin (texto libre) como fecha.

    Formatos soportados (orden de prioridad):
      - "DD de mes de YYYY" / "DD de mes del YYYY"   (31 de marzo del 2026)
      - "DD de mes"                                    (4 de mayo)
      - "D mes" / "D mes y D mes"                      (4 mayo, toma la primera)
      - "DD-abrev" / "DD abrev"                        (16-nov)
      - "abrev-DD" / "abrev DD"                        (nov-21)
      - DD/MM/YYYY  o  DD-MM-YYYY                      (20/05/2015)

    Retorna None si no se puede parsear.
    """
    if not plazo_texto or not plazo_texto.strip():
        return None
    s = plazo_texto.strip().lower()
    año_actual = datetime.now().year

    # "DD de mes de YYYY" / "DD de mes del YYYY"
    m = re.search(
        rf"(\d{{1,2}})\s+de\s+({_MESES_LARGO_RE})\s+(?:de|del)\s*(\d{{4}})", s,
    )
    if m:
        return _safe_date(int(m.group(3)), MESES_LARGO[m.group(2)], int(m.group(1)))

    # "DD de mes" (sin año)
    m = re.search(rf"(\d{{1,2}})\s+de\s+({_MESES_LARGO_RE})", s)
    if m:
        return _safe_date(año_actual, MESES_LARGO[m.group(2)], int(m.group(1)))

    # "D mes" (sin preposición) — p.ej. "4 mayo", "4 mayo y 20 julio" toma la primera
    m = re.search(rf"(\d{{1,2}})\s+({_MESES_LARGO_RE})", s)
    if m:
        return _safe_date(año_actual, MESES_LARGO[m.group(2)], int(m.group(1)))

    # "DD-abrev" / "DDabrev" (16-nov, 1nov)
    m = re.search(rf"(\d{{1,2}})[-\s]?({_MESES_ABREV_RE})\b", s)
    if m:
        return _safe_date(año_actual, MESES_ABREV[m.group(2)], int(m.group(1)))

    # "abrev-DD" / "abrev DD" (nov-21, sept 3)
    m = re.search(rf"\b({_MESES_ABREV_RE})[-\s](\d{{1,2}})\b", s)
    if m:
        return _safe_date(año_actual, MESES_ABREV[m.group(1)], int(m.group(2)))

    # DD/MM/YYYY o DD-MM-YYYY
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", s)
    if m:
        d, m_val, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y if y > 100 else 2000 + y
        return _safe_date(y, m_val, d)

    return None


def parsear_plazo_iso(plazo_texto: str) -> str | None:
    """Retorna la fecha en formato YYYY-MM-DD o None."""
    dt = parsear_plazo(plazo_texto)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d")


def es_futura(plazo_texto: str) -> bool:
    """
    True si la convocatoria se considera futura:
    - plazo no parseable → se asume futura (para no ocultarla).
    - plazo parseable → futura si fecha >= hoy (al inicio del día).
    """
    fecha = parsear_plazo(plazo_texto)
    if fecha is None:
        return True
    return fecha.date() >= datetime.now().date()


def clave_orden(plazo_texto: str) -> tuple[int, datetime]:
    """
    Clave de ordenación para sorted(): convocatorias con fecha primero
    (por proximidad ascendente), sin fecha al final.
    """
    fecha = parsear_plazo(plazo_texto)
    if fecha is None:
        return (1, datetime.max)
    return (0, fecha)
