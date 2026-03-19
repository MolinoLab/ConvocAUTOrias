@ -5,6 +5,7 @@ import sys
import uuid
from datetime import date as _date_type
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

@ -20,6 +21,105 @@ except ImportError:
    IcalTodo = None


_LAST_TAREA_ERROR = ""


def _set_last_tarea_error(message: str) -> None:
    global _LAST_TAREA_ERROR
    _LAST_TAREA_ERROR = (message or "").strip()[:600]


def obtener_ultimo_error_tarea() -> str:
    return _LAST_TAREA_ERROR


def _norm_calendar_token(s: str) -> str:
    """Normaliza nombre/slug del calendario para comparar (sin espacios ni símbolos)."""
    return "".join(c.lower() for c in s if c.isalnum())


def _calendar_slug_from_dav_url(url: str) -> str | None:
    """
    En URLs Nextcloud: .../remote.php/dav/calendars/{user}/{calendar_id}/
    Devuelve calendar_id (segmento tras el usuario), no el dominio.
    """
    path = urlparse(str(url)).path.strip("/")
    parts = [p for p in path.split("/") if p]
    try:
        i = parts.index("calendars")
        if i + 2 < len(parts):
            return parts[i + 2]
    except ValueError:
        pass
    return None


def _matches_calendar_display_name(url: str, name: str) -> bool:
    """True si el calendario en la URL corresponde al nombre configurado (no usa el host)."""
    name = name.strip()
    if not name:
        return True
    slug = _calendar_slug_from_dav_url(url)
    if not slug:
        return False
    return _norm_calendar_token(slug) == _norm_calendar_token(name)


def _resolve_target_calendars(client) -> list:
    """
    Calendarios objetivo: CALDAV_CALENDAR_URL, o filtro por CALDAV_CALENDAR_NAME en el path,
    o todos si no hay nombre. OJO: no filtrar con 'in url' porque el dominio contiene molinolab.org.
    """
    if config.CALDAV_CALENDAR_URL:
        url_cal = config.CALDAV_CALENDAR_URL
        try:
            cal = client.calendar(url=url_cal)
            return [cal]
        except Exception:
            return []

    try:
        principal = client.principal()
        calendars = principal.calendars()
    except Exception:
        return []

    if config.CALDAV_CALENDAR_NAME:
        filtrados = [
            c
            for c in calendars
            if _matches_calendar_display_name(str(getattr(c, "url", "")), config.CALDAV_CALENDAR_NAME)
        ]
        return filtrados

    return calendars


def _try_put_todo_http(calendar_url: str, ical_payload: bytes) -> tuple[bool, int, str]:
    """PUT directo a la colección CalDAV (respaldo si add_todo/save_todo fallan)."""
    try:
        import requests
        from requests.auth import HTTPBasicAuth
    except ImportError:
        return False, 0, "requests no disponible"

    base = str(calendar_url).rstrip("/") + "/"
    put_url = base + f"{uuid.uuid4()}.ics"
    try:
        r = requests.put(
            put_url,
            data=ical_payload,
            auth=HTTPBasicAuth(config.CALDAV_USER, config.CALDAV_PASS),
            headers={"Content-Type": "text/calendar; charset=utf-8"},
            timeout=30,
        )
        body = (r.text or "")[:200]
        ok = r.status_code in (200, 201, 204)
        return ok, r.status_code, body
    except Exception as exc:
        return False, 0, str(exc)[:200]


def _conectar_calendario():
    """Conecta al primer calendario CalDAV disponible. Retorna calendar o None."""
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
@ -32,8 +132,7 @@ def _conectar_calendario():
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        principal = client.principal()
        calendars = principal.calendars()
        calendars = _resolve_target_calendars(client)
        return calendars[0] if calendars else None
    except Exception:
        return None
@ -98,34 +197,74 @@ def crear_tarea(
    fecha_due: ISO date string opcional (ej. 2026-03-25)
    prioridad: 1-9 opcional (1 = máxima prioridad en RFC 5545)
    """
    _set_last_tarea_error("")
    if not IcalTodo:
        _set_last_tarea_error("Dependencia icalendar no disponible")
        return False
    calendar = _conectar_calendario()
    if not calendar:
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]) or not caldav or not Calendar:
        _set_last_tarea_error("Configuracion CalDAV incompleta")
        return False

    try:
        cal = Calendar()
        cal.add("prodid", "-//ConvocAUTOrias//ES")
        cal.add("version", "2.0")
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        calendars = _resolve_target_calendars(client)
    except Exception as exc:
        _set_last_tarea_error(f"Error conectando CalDAV: {str(exc)[:180]}")
        return False

        todo = IcalTodo()
        todo.add("uid", str(uuid.uuid4()))
        todo.add("summary", titulo[:255])
        if descripcion:
            todo.add("description", descripcion)
        if fecha_due:
            y, m, d = (int(p) for p in fecha_due.split("-"))
            todo.add("due", _date_type(y, m, d))
        if prioridad and 1 <= prioridad <= 9:
            todo.add("priority", prioridad)
        todo.add("status", "NEEDS-ACTION")

        cal.add_component(todo)
        calendar.add_todo(cal.to_ical())
        return True
    except Exception:
    if not calendars:
        _set_last_tarea_error("No se encontro calendario objetivo en CalDAV")
        return False

    for idx, calendar in enumerate(calendars):
        try:
            cal = Calendar()
            cal.add("prodid", "-//ConvocAUTOrias//ES")
            cal.add("version", "2.0")

            todo = IcalTodo()
            todo.add("uid", str(uuid.uuid4()))
            todo.add("summary", titulo[:255])
            if descripcion:
                todo.add("description", descripcion)
            if fecha_due:
                y, m, d = (int(p) for p in fecha_due.split("-"))
                todo.add("due", _date_type(y, m, d))
            if prioridad and 1 <= prioridad <= 9:
                todo.add("priority", prioridad)
            todo.add("status", "NEEDS-ACTION")

            cal.add_component(todo)
            ical_payload = cal.to_ical()
            if isinstance(ical_payload, str):
                ical_payload = ical_payload.encode("utf-8")
            calendar_url = str(getattr(calendar, "url", ""))
            try:
                calendar.add_todo(ical_payload)
                return True
            except Exception as exc_add:
                try:
                    calendar.save_todo(ical_payload)
                    return True
                except Exception as exc_save:
                    ok_put, status_put, body_put = _try_put_todo_http(calendar_url, ical_payload)
                    if ok_put:
                        return True
                    _set_last_tarea_error(
                        f"CalDAV rechazo VTODO ({status_put}): {body_put[:140]}"
                    )
                    raise exc_save from exc_add
        except Exception as exc:
            _set_last_tarea_error(str(exc))
            continue
    if not _LAST_TAREA_ERROR:
        _set_last_tarea_error("No se pudo crear la tarea en el calendario CalDAV")
    return False


def listar_tareas(include_completed: bool = False) -> list[dict]:
    """
