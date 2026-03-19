"""
Cliente CalDAV para crear eventos con plazos de convocatorias y tareas (VTODO).
"""
import sys
import uuid
from datetime import date as _date_type
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import caldav
    from icalendar import Calendar, Event, Todo as IcalTodo
except ImportError:
    caldav = None
    Calendar = None
    Event = None
    IcalTodo = None


def _conectar_calendario():
    """Conecta al primer calendario CalDAV disponible. Retorna calendar o None."""
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        return None
    if not caldav or not Calendar:
        return None
    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        principal = client.principal()
        calendars = principal.calendars()
        return calendars[0] if calendars else None
    except Exception:
        return None


def crear_evento(titulo: str, fecha_fin: str, descripcion: str = "", url: str = "") -> bool:
    """
    Crea un evento en el calendario Nextcloud/CalDAV.
    fecha_fin: ISO date o datetime string (ej. 2025-11-16 o 2025-11-16T23:59:59)
    """
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        return False
    if not caldav or not Calendar or not Event:
        return False
    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return False
        calendar = calendars[0]

        # Crear evento iCalendar
        cal = Calendar()
        cal.add("prodid", "-//ConvocAUTOrias//ES")
        cal.add("version", "2.0")

        event = Event()
        event.add("uid", str(uuid.uuid4()))
        event.add("summary", titulo[:255])
        if descripcion or url:
            event.add("description", f"{descripcion}\n\nURL: {url}" if url else descripcion)

        # Parsear fecha
        dt_str = fecha_fin.replace("-", "").replace(":", "").replace("T", "")[:15]
        if len(dt_str) == 8:
            event.add("dtstart", dt_str + "T090000")
            event.add("dtend", dt_str + "T235959")
        else:
            event.add("dtstart", dt_str[:8] + "T090000")
            event.add("dtend", dt_str)

        cal.add_component(event)
        calendar.add_event(cal.to_ical())
        return True
    except Exception:
        return False


def crear_tarea(
    titulo: str,
    descripcion: str = "",
    fecha_due: str | None = None,
    prioridad: int | None = None,
) -> bool:
    """
    Crea una tarea (VTODO) en el calendario Nextcloud/CalDAV.
    fecha_due: ISO date string opcional (ej. 2026-03-25)
    prioridad: 1-9 opcional (1 = máxima prioridad en RFC 5545)
    """
    if not IcalTodo:
        return False
    calendar = _conectar_calendario()
    if not calendar:
        return False
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
        calendar.add_todo(cal.to_ical())
        return True
    except Exception:
        return False


def listar_tareas(include_completed: bool = False) -> list[dict]:
    """
    Recupera tareas (VTODO) del calendario CalDAV.
    Retorna lista de dicts con: summary, description, due, priority, status.
    """
    calendar = _conectar_calendario()
    if not calendar or not Calendar:
        return []
    try:
        todos_raw = calendar.todos(include_completed=include_completed)
    except Exception:
        return []

    resultado: list[dict] = []
    for todo_obj in todos_raw:
        try:
            data = todo_obj.data
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            cal = Calendar.from_ical(data)
            for comp in cal.walk():
                if comp.name == "VTODO":
                    due_raw = comp.get("due")
                    due_str = ""
                    if due_raw:
                        dt = due_raw.dt if hasattr(due_raw, "dt") else due_raw
                        due_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)

                    pri_raw = comp.get("priority")
                    pri_val = int(pri_raw) if pri_raw else 0

                    resultado.append({
                        "summary": str(comp.get("summary") or ""),
                        "description": str(comp.get("description") or ""),
                        "due": due_str,
                        "priority": pri_val,
                        "status": str(comp.get("status") or ""),
                    })
        except Exception:
            continue
    return resultado
