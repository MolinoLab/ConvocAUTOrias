"""
Formato de fechas solo para mostrar al usuario (CSV/DB siguen en ISO).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import config


def _zona() -> ZoneInfo:
    tz_name = (config.APP_TIMEZONE or "Europe/Madrid").strip()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def fecha_hoy_relativas() -> date:
    """Fecha local según APP_TIMEZONE (defecto Europe/Madrid)."""
    return datetime.now(_zona()).date()


def formatear_fecha_ver(valor: str) -> str:
    """
    Convierte ISO (con o sin Z, con o sin microsegundos) a DD-MM-YYYY o DD-MM-YYYY HH:MM.
    Si no parsea como ISO, devuelve el string original.
    """
    s = (valor or "").strip()
    if not s:
        return s
    raw = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return s
    if dt.tzinfo is not None:
        dt = dt.astimezone(_zona())
    else:
        dt = dt.replace(tzinfo=_zona())
    base = raw.split("+", 1)[0].strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", base):
        return dt.strftime("%d-%m-%Y")
    return dt.strftime("%d-%m-%Y %H:%M")


def _match_span(texto: str, pattern: re.Pattern) -> re.Match | None:
    m = pattern.search(texto)
    return m


def extraer_fecha_relativa_dd_mm_yyyy(texto: str) -> tuple[str | None, str]:
    """
    Busca una palabra/frase de fecha relativa y devuelve (DD-MM-YYYY, texto_sin_match).
    Orden: frases largas primero.
    """
    t = (texto or "").strip()
    if not t:
        return None, t
    hoy = fecha_hoy_relativas()
    patrones: list[tuple[re.Pattern, date]] = [
        (re.compile(r"\bpasado\s+mañana\b", re.IGNORECASE), hoy + timedelta(days=2)),
        (re.compile(r"\bpasado\s+manana\b", re.IGNORECASE), hoy + timedelta(days=2)),
        (re.compile(r"\bantier\b", re.IGNORECASE), hoy - timedelta(days=2)),
        (re.compile(r"\bayer\b", re.IGNORECASE), hoy - timedelta(days=1)),
        (re.compile(r"\bhoy\b", re.IGNORECASE), hoy),
        (re.compile(r"\bmañana\b", re.IGNORECASE), hoy + timedelta(days=1)),
        (re.compile(r"\bmanana\b", re.IGNORECASE), hoy + timedelta(days=1)),
        (re.compile(r"\bpasado\b", re.IGNORECASE), hoy + timedelta(days=2)),
    ]
    for pat, d in patrones:
        m = pat.search(t)
        if m:
            fecha = f"{d.day:02d}-{d.month:02d}-{d.year}"
            resto = (t[: m.start()] + t[m.end() :]).strip()
            resto = " ".join(resto.split())
            return fecha, resto
    return None, t


def extraer_fecha_relativa_iso_y_resto(texto: str) -> tuple[str | None, str]:
    """Como extraer_fecha_relativa_dd_mm_yyyy pero ISO YYYY-MM-DD para tareas."""
    ddmmyyyy, resto = extraer_fecha_relativa_dd_mm_yyyy(texto)
    if not ddmmyyyy:
        return None, texto.strip()
    try:
        d, m, y = ddmmyyyy.split("-")
        iso = f"{y}-{m}-{d}"
        datetime.strptime(iso, "%Y-%m-%d")
        return iso, resto
    except ValueError:
        return None, texto.strip()


def strip_sufijo_para_el(texto: str) -> str:
    return re.sub(r"\s+para el\s*$", "", (texto or "").strip(), flags=re.IGNORECASE).strip()
