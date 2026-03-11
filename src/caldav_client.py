"""
Cliente CalDAV para crear eventos con plazos de convocatorias.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import caldav
    from icalendar import Calendar, Event
except ImportError:
    caldav = None
    Calendar = None
    Event = None


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
