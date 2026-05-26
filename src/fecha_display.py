"""
Formato de fechas solo para mostrar al usuario (CSV/DB siguen en ISO).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
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


def ahora_local() -> datetime:
    """Momento actual en APP_TIMEZONE (naive, hora de pared local)."""
    return datetime.now(_zona()).replace(tzinfo=None)


def ventana_dia_local(fecha: date) -> tuple[datetime, datetime]:
    """
    Ventana [inicio, fin) del día `fecha` en hora local (APP_TIMEZONE).
    Devuelve datetimes naive comparables con listar_eventos_en_ventana.
    """
    win_start = datetime.combine(fecha, time.min)
    win_end_excl = win_start + timedelta(days=1)
    return win_start, win_end_excl


def lunes_semana_entrante(hoy: date) -> date:
    """
    Lunes de la semana entrante según el día de envío:
    - Domingo: lunes siguiente (mañana).
    - Lunes–sábado: lunes de la semana en curso (no saltar +7 días).
    """
    if hoy.weekday() == 6:
        return hoy + timedelta(days=1)
    return hoy - timedelta(days=hoy.weekday())


_MES_NUM_A_NOMBRE: dict[int, str] = {v: k for k, v in MESES_LARGO.items()}


def letra_mes_espanol(mes: int) -> str:
    """Primera letra del nombre del mes en español (mayúscula). mes: 1-12."""
    if not 1 <= mes <= 12:
        return "?"
    nombre = _MES_NUM_A_NOMBRE.get(mes, "")
    return (nombre[:1] or "?").upper()


def _formato_dia_letra_mes(d: int, mo: int, hora_part: str) -> str:
    out = f"{d:02d}{letra_mes_espanol(mo)}"
    if hora_part:
        out = f"{out} {hora_part}"
    return out


def formatear_dia_mes_sin_anio(valor: str) -> str:
    """
    Para listados de agenda: DD + letra del mes (YYYY-MM-DD o YYYY-MM-DD HH:MM).
    Ej.: 2026-03-24 -> 24M; 2026-03-24 14:30 -> 24M 14:30 (marzo -> M).
    """
    s = (valor or "").strip()
    if not s:
        return s
    if " " in s:
        fecha_part, hora_part = s.split(" ", 1)
        hora_part = hora_part.strip()
    else:
        fecha_part, hora_part = s, ""
    partes = fecha_part.split("-")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        return valor
    y, mo, d = (int(partes[0]), int(partes[1]), int(partes[2]))
    try:
        datetime(y, mo, d)
    except ValueError:
        return valor
    return _formato_dia_letra_mes(d, mo, hora_part)


def formatear_fecha_ver(valor: str) -> str:
    """
    Convierte ISO (con o sin Z, con o sin microsegundos) a DD + letra mes o DD + letra HH:MM.
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
    letra = letra_mes_espanol(dt.month)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", base):
        return f"{dt.day:02d}{letra}"
    return f"{dt.day:02d}{letra} {dt.strftime('%H:%M')}"


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


def _dd_mm_yyyy_a_iso(fecha_dd_mm_yyyy: str) -> str | None:
    partes = (fecha_dd_mm_yyyy or "").strip().split("-")
    if len(partes) != 3:
        return None
    d, m, y = partes[0], partes[1], partes[2]
    try:
        yi = _anio_dos_cifras(int(y))
        mo = int(m)
        di = int(d)
        datetime(yi, mo, di)
        return f"{yi:04d}-{mo:02d}-{di:02d}"
    except (ValueError, TypeError):
        return None


def _normalizar_fecha_objetivo_a_yyyy_mm_dd(
    fragmento: str,
) -> str | None:
    """fragmento: texto tras 'para el' / 'para' (una fecha)."""
    frag = (fragmento or "").strip()
    if not frag:
        return None

    m = re.fullmatch(
        r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})",
        frag,
    )
    if m:
        iso = _dd_mm_yyyy_a_iso(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        if iso:
            return iso

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", frag):
        try:
            datetime.strptime(frag, "%Y-%m-%d")
            return frag
        except ValueError:
            pass

    dd_mm_yyyy, _ = extraer_fecha_natural_dd_mm_yyyy_y_resto(frag)
    if dd_mm_yyyy:
        return _dd_mm_yyyy_a_iso(dd_mm_yyyy)

    dd_mm_yyyy2, _ = extraer_fecha_relativa_dd_mm_yyyy(frag)
    if dd_mm_yyyy2:
        return _dd_mm_yyyy_a_iso(dd_mm_yyyy2)

    return None


def extraer_cuerpo_y_fecha_dia_para_el(texto: str) -> tuple[str, str | None]:
    """
    Si el texto termina en 'para el <fecha>' o 'para <fecha>', devuelve (cuerpo sin ese sufijo, YYYY-MM-DD).
    La fecha puede ser DD-MM-AAAA, YYYY-MM-DD, natural (15 de marzo) o relativa (ayer, lunes).
    """
    t = (texto or "").strip()
    if not t:
        return "", None

    for patron in (
        re.compile(r"^(.*)\s+para el\s+(.+)$", re.IGNORECASE | re.DOTALL),
        re.compile(r"^(.*)\s+para\s+(.+)$", re.IGNORECASE | re.DOTALL),
    ):
        m = patron.match(t)
        if not m:
            continue
        cuerpo = (m.group(1) or "").strip()
        frag = (m.group(2) or "").strip()
        fecha_iso = _normalizar_fecha_objetivo_a_yyyy_mm_dd(frag)
        if fecha_iso and cuerpo:
            return cuerpo, fecha_iso
    return t, None
