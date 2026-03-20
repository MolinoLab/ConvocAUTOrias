"""
Parseo y formato de fechas en estilo español con comas (DD,MM,YYYY).
Acepta entrada flexible: comas, guiones o barras; abreviaciones DD o DD,MM.
"""
from __future__ import annotations

import re
from datetime import datetime


def _anio_dos_cifras(y: int) -> int:
    if 0 <= y < 100:
        return 2000 + y
    return y


def normalizar_fecha_texto_a_partes(texto: str) -> tuple[int, int, int] | None:
    """
    Devuelve (d, m, y) desde fragmentos flexibles.
    Acepta DD,MM,YYYY / DD-MM-YYYY / DD/MM/YYYY / DD,MM / DD-MM / solo DD (mes y año actuales).
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    now = datetime.now()
    # Unificar separadores de fecha a guion
    t = re.sub(r"\s+", " ", texto)

    m = re.match(
        r"^(\d{1,2})[.,\-/](\d{1,2})[.,\-/](\d{2}|\d{4})$",
        t,
    )
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = _anio_dos_cifras(y)
        try:
            datetime(y, mo, d)
        except ValueError:
            return None
        return d, mo, y

    m2 = re.match(r"^(\d{1,2})[.,\-/](\d{1,2})$", t)
    if m2:
        d, mo = int(m2.group(1)), int(m2.group(2))
        y = now.year
        try:
            datetime(y, mo, d)
        except ValueError:
            return None
        return d, mo, y

    m3 = re.match(r"^(\d{1,2})$", t)
    if m3:
        d = int(m3.group(1))
        if not (1 <= d <= 31):
            return None
        try:
            datetime(now.year, now.month, d)
        except ValueError:
            return None
        return d, now.month, now.year

    return None


def parsear_solo_fecha(texto: str) -> datetime | None:
    partes = normalizar_fecha_texto_a_partes(texto.strip())
    if not partes:
        return None
    d, mo, y = partes
    try:
        return datetime(y, mo, d)
    except ValueError:
        return None


def formatear_fecha(dt: datetime) -> str:
    return f"{dt.day:02d},{dt.month:02d},{dt.year}"


def formatear_fecha_hora(dt: datetime) -> str:
    return f"{dt.day:02d},{dt.month:02d},{dt.year} {dt.hour:02d}:{dt.minute:02d}"


def parsear_fecha_hora(texto: str) -> datetime | None:
    """
    Acepta: 'DD,MM,YYYY HH:MM' o fecha sola (00:00) o 'YYYY-MM-DD HH:MM' legado.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    # Legado ISO fecha + hora
    m_iso = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$",
        texto,
    )
    if m_iso:
        y, mo, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        h, mi = int(m_iso.group(4)), int(m_iso.group(5))
        try:
            return datetime(y, mo, d, h, mi)
        except ValueError:
            return None

    m_time = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\s*$", texto)
    hora = (0, 0)
    resto_fecha = texto
    if m_time:
        hora = (int(m_time.group(1)), int(m_time.group(2)))
        resto_fecha = texto[: m_time.start()].strip()

    partes = normalizar_fecha_texto_a_partes(resto_fecha)
    if not partes:
        return None
    d, mo, y = partes
    try:
        return datetime(y, mo, d, hora[0], hora[1])
    except ValueError:
        return None


def minutos_entre(inicio: datetime, fin: datetime) -> int:
    delta = fin - inicio
    return max(0, int(delta.total_seconds() // 60))


def formatear_minutos_como_texto(minutos: int) -> str:
    if minutos <= 0:
        return "0 min"
    h, m = divmod(minutos, 60)
    if h and m:
        return f"{h}h {m}min"
    if h:
        return f"{h}h"
    return f"{m}min"
