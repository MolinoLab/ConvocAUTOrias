"""
Formato de fechas solo para mostrar al usuario (CSV/DB siguen en ISO).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import config
from src.plazo import MESES_LARGO, _MESES_LARGO_RE


def _anio_dos_cifras(y: int) -> int:
    if 0 <= y < 100:
        return 2000 + y
    return y


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


def extraer_fecha_natural_dd_mm_yyyy_y_resto(texto: str) -> tuple[str | None, str]:
    """
    Fechas en español coloquial: devuelve (DD-MM-YYYY, texto sin el fragmento de fecha).

    Cubre:
      - DD de mes de YYYY / DD de mes del YYYY
      - DD de mes (sin año, año según APP_TIMEZONE)
      - DD del MM del YYYY / DD del MM de YYYY (mes numérico; año 2 cifras -> 20YY)
    """
    t = (texto or "").strip()
    if not t:
        return None, t
    s = t.lower()
    hoy = fecha_hoy_relativas()

    m = re.search(
        rf"\b(\d{{1,2}})\s+de\s+({_MESES_LARGO_RE})\s+(?:de|del)\s*(\d{{2}}|\d{{4}})\b",
        s,
    )
    if m:
        d, mes_nombre, y_raw = int(m.group(1)), m.group(2), int(m.group(3))
        y = _anio_dos_cifras(y_raw)
        mo = MESES_LARGO[mes_nombre]
        try:
            datetime(y, mo, d)
        except ValueError:
            return None, t
        fecha = f"{d:02d}-{mo:02d}-{y}"
        resto = (t[: m.start()] + t[m.end() :]).strip()
        resto = " ".join(resto.split())
        return fecha, resto

    m = re.search(rf"\b(\d{{1,2}})\s+de\s+({_MESES_LARGO_RE})\b", s)
    if m:
        d, mes_nombre = int(m.group(1)), m.group(2)
        mo = MESES_LARGO[mes_nombre]
        y = hoy.year
        try:
            datetime(y, mo, d)
        except ValueError:
            return None, t
        fecha = f"{d:02d}-{mo:02d}-{y}"
        resto = (t[: m.start()] + t[m.end() :]).strip()
        resto = " ".join(resto.split())
        return fecha, resto

    m = re.search(
        r"\b(\d{1,2})\s+del\s+(\d{1,2})\s+(?:del|de)\s*(\d{2}|\d{4})\b",
        s,
    )
    if m:
        d, mo, y_raw = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not 1 <= mo <= 12:
            return None, t
        y = _anio_dos_cifras(y_raw)
        try:
            datetime(y, mo, d)
        except ValueError:
            return None, t
        fecha = f"{d:02d}-{mo:02d}-{y}"
        resto = (t[: m.start()] + t[m.end() :]).strip()
        resto = " ".join(resto.split())
        return fecha, resto

    return None, t


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

    dia_fecha, dia_resto = extraer_dia_semana_proximo_dd_mm_yyyy_y_resto(t)
    if dia_fecha:
        return dia_fecha, dia_resto

    return None, t


# Nombres de día (normalizado sin tildes para lookup)
_DIA_SEMANA_A_WEEKDAY: dict[str, int] = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}

_DIA_SEMANA_TOKEN_RE = (
    r"lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo"
)


def _token_dia_a_weekday(token: str) -> int | None:
    t = (token or "").lower().replace("á", "a").replace("é", "e")
    return _DIA_SEMANA_A_WEEKDAY.get(t)


def extraer_dia_semana_proximo_dd_mm_yyyy_y_resto(texto: str) -> tuple[str | None, str]:
    """
    Próximo día con ese nombre de semana respecto a hoy (APP_TIMEZONE).
    Si hoy es ese día, cuenta hoy. Devuelve (DD-MM-YYYY, texto sin el fragmento).
    Acepta opcional 'el' delante del nombre del día.
    """
    t = (texto or "").strip()
    if not t:
        return None, t
    m = re.search(
        rf"\b(?:el\s+)?({_DIA_SEMANA_TOKEN_RE})\b",
        t,
        flags=re.IGNORECASE,
    )
    if not m:
        return None, t
    wd = _token_dia_a_weekday(m.group(1))
    if wd is None:
        return None, t
    hoy = fecha_hoy_relativas()
    delta = (wd - hoy.weekday()) % 7
    f = hoy + timedelta(days=delta)
    fecha = f"{f.day:02d}-{f.month:02d}-{f.year}"
    resto = (t[: m.start()] + t[m.end() :]).strip()
    resto = " ".join(resto.split())
    return fecha, resto


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


def strip_sufijo_para_fecha(texto: str) -> str:
    """Quita un sufijo final 'para el' o 'para' (p. ej. tras extraer la fecha del resto)."""
    t = (texto or "").strip()
    t = re.sub(r"\s+para el\s*$", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s+para\s*$", "", t, flags=re.IGNORECASE).strip()
    return t


def strip_sufijo_para_el(texto: str) -> str:
    return strip_sufijo_para_fecha(texto)
