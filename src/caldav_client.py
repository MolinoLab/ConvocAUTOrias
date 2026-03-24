"""
Cliente CalDAV para crear eventos con plazos de convocatorias y tareas (VTODO).
"""
import sys
import uuid
from datetime import date as _date_type, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse

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


_LAST_TAREA_ERROR = ""
_LAST_EVENTO_ERROR = ""

def _set_last_evento_error(message: str) -> None:
    global _LAST_EVENTO_ERROR
    _LAST_EVENTO_ERROR = (message or "").strip()[:600]


def obtener_ultimo_error_evento() -> str:
    return _LAST_EVENTO_ERROR


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


def _calendar_owner_segment_from_url(url: str) -> str | None:
    """Segmento de usuario en .../calendars/{este}/{calendario}/."""
    path = urlparse(str(url)).path.strip("/")
    parts = [p for p in path.split("/") if p]
    try:
        i = parts.index("calendars")
        if i + 1 < len(parts):
            return parts[i + 1]
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


def _matches_calendar_live_display_name(cal, name: str) -> bool:
    """Compara el nombre mostrado del calendario en el servidor (útil en calendarios compartidos)."""
    name = (name or "").strip()
    if not name:
        return False
    try:
        dn = cal.get_display_name()
    except Exception:
        return False
    if not dn:
        return False
    return _norm_calendar_token(str(dn)) == _norm_calendar_token(name)


def _etiqueta_calendario(cal) -> str:
    try:
        dn = cal.get_display_name()
        if dn:
            return str(dn).strip()
    except Exception:
        pass
    slug = _calendar_slug_from_dav_url(str(getattr(cal, "url", "")))
    return slug or "CalDAV"


def _calendarios_filtrados_por_nombres(calendars, nombres: list[str]) -> list:
    """Unión de calendarios cuyo slug o nombre visible coincide con algún nombre."""
    if not nombres:
        return list(calendars)
    seen: set[str] = set()
    out: list = []
    for c in calendars:
        url = str(getattr(c, "url", "") or "")
        if not url or url in seen:
            continue
        for name in nombres:
            nm = (name or "").strip()
            if not nm:
                continue
            if _matches_calendar_display_name(url, nm) or _matches_calendar_live_display_name(c, nm):
                seen.add(url)
                out.append(c)
                break
    return out


def _principal_calendars_matching_config_url(client, url_cal: str) -> list:
    """
    Lista calendarios del usuario autenticado que corresponden a la URL de referencia
    (mismo slug en path o mismo nombre mostrado que CALDAV_CALENDAR_NAME).
    """
    target_slug = _calendar_slug_from_dav_url(url_cal)
    try:
        principal = client.principal()
        all_cals = list(principal.calendars())
    except Exception:
        return []

    by_slug: list = []
    for c in all_cals:
        slug = _calendar_slug_from_dav_url(str(getattr(c, "url", "")))
        if (
            target_slug
            and slug
            and _norm_calendar_token(slug) == _norm_calendar_token(target_slug)
        ):
            by_slug.append(c)
    if by_slug:
        return by_slug

    nombres = list(config.CALDAV_CALENDAR_NAMES or [])
    if not nombres and (config.CALDAV_CALENDAR_NAME or "").strip():
        nombres = [(config.CALDAV_CALENDAR_NAME or "").strip()]
    if not nombres:
        return []
    by_name = _calendarios_filtrados_por_nombres(all_cals, nombres)
    if by_name:
        return by_name
    return []


def _resolve_target_calendars(client) -> list:
    """
    Calendarios objetivo: CALDAV_CALENDAR_URL, o filtro por CALDAV_CALENDAR_NAME en el path,
    o todos si no hay nombre. OJO: no filtrar con 'in url' porque el dominio contiene molinolab.org.
    """
    if config.CALDAV_CALENDAR_URL:
        url_cal = config.CALDAV_CALENDAR_URL
        owner_in_url = (_calendar_owner_segment_from_url(url_cal) or "").strip()
        auth_user = (config.CALDAV_USER or "").strip()
        if (
            owner_in_url
            and auth_user
            and owner_in_url.lower() != auth_user.lower()
        ):
            return _principal_calendars_matching_config_url(client, url_cal)
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

    if config.CALDAV_CALENDAR_NAMES:
        return _calendarios_filtrados_por_nombres(calendars, config.CALDAV_CALENDAR_NAMES)

    return calendars


def _comps_includes_vevent(comps: list) -> bool:
    for item in comps or []:
        if item == "VEVENT":
            return True
        if isinstance(item, dict) and item.get("name") == "VEVENT":
            return True
        name = getattr(item, "name", None)
        if name == "VEVENT":
            return True
    return False


def _calendar_supports_vevent(cal) -> bool | None:
    """
    True si el calendario declara VEVENT; False si declara otros tipos pero no VEVENT;
    None si no se pudo saber (lista vacía o error PROPFIND).
    """
    try:
        comps = cal.get_supported_components()
    except Exception:
        return None
    if not comps:
        return None
    return _comps_includes_vevent(comps)


def _sort_calendars_for_events(calendars: list) -> list:
    """Prioriza colecciones que declaran VEVENT (evita listas solo VTODO que suelen dar 404 a VEVENT)."""

    def key(c):
        path = urlparse(str(getattr(c, "url", ""))).path
        sup = _calendar_supports_vevent(c)
        if sup is True:
            tier = 0
        elif sup is None:
            tier = 1
        else:
            tier = 2
        return (tier, path)

    return sorted(calendars, key=key)


def _try_put_ics_http(calendar_url: str, ical_payload: bytes) -> tuple[bool, int, str]:
    """PUT directo de un .ics en la colección CalDAV (respaldo si add_* falla)."""
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
        return None
    if not caldav or not Calendar:
        return None
    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        calendars = _resolve_target_calendars(client)
        return calendars[0] if calendars else None
    except Exception:
        return None


def crear_evento(
    titulo: str,
    fecha: str,
    descripcion: str = "",
    url: str = "",
    hora: str | None = None,
    duracion: timedelta | None = None,
) -> bool:
    """
    Crea un evento en el calendario Nextcloud/CalDAV (colección según CALDAV_*).
    fecha: YYYY-MM-DD, o legado: datetime ISO compacto si no coincide con solo fecha.
    hora: opcional HH:MM (24 h); sin duracion el evento dura 1 h desde ese inicio.
    duracion: opcional; si hay hora, define DTEND (o se usa 1 h por defecto).
    """
    _set_last_evento_error("")
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        _set_last_evento_error("Configuracion CalDAV incompleta")
        return False
    if not caldav or not Calendar or not Event:
        _set_last_evento_error("Dependencia caldav/icalendar no disponible")
        return False

    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        calendars = _resolve_target_calendars(client)
    except Exception as exc:
        _set_last_evento_error(f"Error conectando CalDAV: {str(exc)[:180]}")
        return False

    if not calendars:
        url_cal = (config.CALDAV_CALENDAR_URL or "").strip()
        own_url = _calendar_owner_segment_from_url(url_cal) if url_cal else ""
        auth_u = (config.CALDAV_USER or "").strip()
        if (
            url_cal
            and own_url
            and auth_u
            and own_url.lower() != auth_u.lower()
        ):
            _set_last_evento_error(
                "Cuenta CalDAV distinta del propietario en CALDAV_CALENDAR_URL: no hay calendario "
                "visible con ese slug ni con CALDAV_CALENDAR_NAME. Comparte el calendario con "
                "CALDAV_USER o pon CALDAV_CALENDAR_URL bajo .../calendars/<CALDAV_USER>/..."
            )
        else:
            _set_last_evento_error("No se encontro calendario objetivo en CalDAV")
        return False

    fecha_norm = (fecha or "").strip()

    cal = Calendar()
    cal.add("prodid", "-//ConvocAUTOrias//ES")
    cal.add("version", "2.0")

    event = Event()
    event.add("uid", str(uuid.uuid4()))
    event.add("summary", titulo[:255])
    if descripcion or url:
        event.add("description", f"{descripcion}\n\nURL: {url}" if url else descripcion)

    try:
        if hora:
            h = hora.strip()
            datetime.strptime(h, "%H:%M")
            d0 = datetime.strptime(f"{fecha_norm} {h}", "%Y-%m-%d %H:%M")
            delta = duracion if duracion is not None else timedelta(hours=1)
            if delta.total_seconds() <= 0:
                delta = timedelta(hours=1)
            d1 = d0 + delta
            event.add("dtstart", d0)
            event.add("dtend", d1)
        else:
            try:
                d_only = datetime.strptime(fecha_norm, "%Y-%m-%d").date()
                d0 = datetime.combine(d_only, time(9, 0, 0))
                d1 = datetime.combine(d_only, time(23, 59, 59))
                event.add("dtstart", d0)
                event.add("dtend", d1)
            except ValueError:
                dt_str = fecha_norm.replace("-", "").replace(":", "").replace("T", "")[:15]
                if len(dt_str) == 8:
                    d_only = datetime.strptime(dt_str, "%Y%m%d").date()
                else:
                    d_only = datetime.strptime(dt_str[:8], "%Y%m%d").date()
                d0 = datetime.combine(d_only, time(9, 0, 0))
                d1 = datetime.combine(d_only, time(23, 59, 59))
                event.add("dtstart", d0)
                event.add("dtend", d1)
    except ValueError as exc:
        _set_last_evento_error(f"Fecha u hora invalida: {str(exc)[:120]}")
        return False

    cal.add_component(event)
    ical_raw = cal.to_ical()
    if isinstance(ical_raw, str):
        ical_payload = ical_raw.encode("utf-8")
    else:
        ical_payload = ical_raw

    ordered = _sort_calendars_for_events(calendars)
    ultimo_detalle = ""

    for calendar in ordered:
        cal_url = str(getattr(calendar, "url", ""))
        path_log = urlparse(cal_url).path[-160:]
        vev = _calendar_supports_vevent(calendar)
        try:
            calendar.add_event(ical_payload)
            return True
        except Exception as exc_add:
            ultimo_detalle = str(exc_add)[:200]
            try:
                calendar.save_event(ical_payload)
                return True
            except Exception as exc_save:
                ok_put, status_put, body_put = _try_put_ics_http(cal_url, ical_payload)
                if ok_put:
                    return True
                ultimo_detalle = f"{exc_save}; PUT {status_put}: {body_put[:120]}"
    hint = (
        " Revisa CALDAV_CALENDAR_URL (coleccion de calendario con eventos) o "
        "CALDAV_CALENDAR_NAME; una lista solo de tareas (VTODO) no acepta eventos."
    )
    _set_last_evento_error((ultimo_detalle or "CalDAV rechazo el evento")[:180] + hint[:200])
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
    _set_last_tarea_error("")
    if not IcalTodo:
        _set_last_tarea_error("Dependencia icalendar no disponible")
        return False
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]) or not caldav or not Calendar:
        _set_last_tarea_error("Configuracion CalDAV incompleta")
        return False

    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        calendars = _resolve_target_calendars(client)
    except Exception as exc:
        _set_last_tarea_error(f"Error conectando CalDAV: {str(exc)[:180]}")
        return False

    if not calendars:
        url_cal = (config.CALDAV_CALENDAR_URL or "").strip()
        own_url = _calendar_owner_segment_from_url(url_cal) if url_cal else ""
        auth_u = (config.CALDAV_USER or "").strip()
        if url_cal and own_url and auth_u and own_url.lower() != auth_u.lower():
            _set_last_tarea_error(
                "Cuenta CalDAV distinta del propietario en CALDAV_CALENDAR_URL: no hay calendario "
                "visible con ese slug ni con CALDAV_CALENDAR_NAME. Comparte el calendario con "
                "CALDAV_USER o ajusta la URL bajo .../calendars/<CALDAV_USER>/..."
            )
        else:
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
                    ok_put, status_put, body_put = _try_put_ics_http(calendar_url, ical_payload)
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
    Recupera tareas (VTODO) de todos los calendarios objetivo CalDAV.
    Retorna lista de dicts con: summary, description, due, priority, status, uid, href, calendario.
    """
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        return []
    if not caldav or not Calendar:
        return []
    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        calendars = _resolve_target_calendars(client)
    except Exception:
        return []

    if not calendars:
        return []

    resultado: list[dict] = []
    seen_uid: set[str] = set()

    for calendar in calendars:
        cal_label = _etiqueta_calendario(calendar)
        try:
            todos_raw = calendar.todos(include_completed=include_completed)
        except Exception:
            continue

        for todo_obj in todos_raw:
            try:
                data = todo_obj.data
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                cal = Calendar.from_ical(data)
                for comp in cal.walk():
                    if comp.name != "VTODO":
                        continue
                    due_raw = comp.get("due")
                    due_str = ""
                    if due_raw:
                        dt = due_raw.dt if hasattr(due_raw, "dt") else due_raw
                        due_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)

                    pri_raw = comp.get("priority")
                    pri_val = int(pri_raw) if pri_raw else 0
                    uid = str(comp.get("uid") or "")
                    href = str(getattr(todo_obj, "url", "") or "")
                    dedupe = uid or href
                    if dedupe and dedupe in seen_uid:
                        continue
                    if dedupe:
                        seen_uid.add(dedupe)

                    resultado.append(
                        {
                            "summary": str(comp.get("summary") or ""),
                            "description": str(comp.get("description") or ""),
                            "due": due_str,
                            "priority": pri_val,
                            "status": str(comp.get("status") or ""),
                            "uid": uid,
                            "href": href,
                            "calendario": cal_label,
                        }
                    )
            except Exception:
                continue
    return resultado


def _vevent_start_local_naive(comp) -> datetime | None:
    """
    Inicio del VEVENT como datetime naive en hora local (APP_TIMEZONE).
    Los DTSTART con TZ (p. ej. UTC) se convierten antes de comparar con la ventana local.
    """
    from src.fecha_display import _zona

    ds = comp.get("dtstart")
    if not ds:
        return None
    dt = ds.dt if hasattr(ds, "dt") else ds
    tz = _zona()
    if hasattr(dt, "hour"):
        if getattr(dt, "tzinfo", None):
            return dt.astimezone(tz).replace(tzinfo=None)
        return dt
    if hasattr(dt, "year"):
        return datetime.combine(dt, time.min)
    return None


def _vevent_start_for_sort(comp) -> datetime | None:
    """Compat: mismo que _vevent_start_local_naive."""
    return _vevent_start_local_naive(comp)


def _vevent_summary_uid(comp) -> tuple[str, str]:
    summ = str(comp.get("summary") or "").strip()
    uid = str(comp.get("uid") or "").strip()
    return summ, uid


def listar_eventos_en_ventana(win_start: datetime, win_end_excl: datetime) -> list[dict]:
    """
    VEVENT con inicio en [win_start, win_end_excl). Misma forma de dict que listar_eventos_proximos_dias.
    win_start / win_end_excl: datetime naive (fecha-hora local del entorno).
    """
    _set_last_evento_error("")
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        _set_last_evento_error("Configuracion CalDAV incompleta")
        return []
    if not caldav or not Calendar:
        _set_last_evento_error("Dependencia caldav/icalendar no disponible")
        return []

    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        calendars = _resolve_target_calendars(client)
    except Exception as exc:
        _set_last_evento_error(f"Error conectando CalDAV: {str(exc)[:180]}")
        return []

    if not calendars:
        _set_last_evento_error("No se encontro calendario objetivo en CalDAV")
        return []

    ordered = _sort_calendars_for_events(calendars)
    seen_uid: set[str] = set()
    resultado: list[dict] = []

    for calendar in ordered:
        if _calendar_supports_vevent(calendar) is False:
            continue
        cal_label = _etiqueta_calendario(calendar)
        try:
            found = calendar.date_search(
                win_start,
                win_end_excl,
                expand=False,
                compfilter="VEVENT",
            )
        except Exception:
            continue
        if not found:
            continue

        for ev in found:
            url = str(getattr(ev, "url", "") or "").strip()
            try:
                raw = ev.data
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                cal = Calendar.from_ical(raw)
            except Exception:
                continue

            for comp in cal.walk():
                if comp.name != "VEVENT":
                    continue
                summ, uid = _vevent_summary_uid(comp)
                st = _vevent_start_for_sort(comp)
                if st is None:
                    continue
                if st < win_start or st >= win_end_excl:
                    continue
                dedupe = uid or url
                if dedupe and dedupe in seen_uid:
                    continue
                if dedupe:
                    seen_uid.add(dedupe)

                if hasattr(st, "hour") and (st.hour, st.minute) != (0, 0):
                    start_iso = st.strftime("%Y-%m-%d %H:%M")
                else:
                    start_iso = st.strftime("%Y-%m-%d")

                resultado.append(
                    {
                        "summary": summ or "(sin titulo)",
                        "start_iso": start_iso,
                        "sort_key": st,
                        "uid": uid,
                        "url": url,
                        "calendario": cal_label,
                    }
                )

    resultado.sort(key=lambda x: x["sort_key"])
    return resultado


def listar_eventos_proximos_dias(dias: int) -> list[dict]:
    """
    Eventos VEVENT con inicio en la ventana [hoy 00:00 local, hoy + dias) (dias = 7 -> 7 días desde hoy).
    Consulta todos los calendarios objetivo que declaran VEVENT (orden _sort_calendars_for_events).
    Cada dict: summary, start_iso (YYYY-MM-DD o YYYY-MM-DD HH:MM), sort_key (datetime), uid, url
    """
    if dias < 1:
        dias = 1
    from src.fecha_display import fecha_hoy_relativas

    today_d = fecha_hoy_relativas()
    win_start = datetime.combine(today_d, time.min)
    win_end_excl = win_start + timedelta(days=int(dias))
    return listar_eventos_en_ventana(win_start, win_end_excl)


def _vevent_dtend_or_duration(comp) -> str:
    de = comp.get("dtend")
    if de:
        dt = de.dt if hasattr(de, "dt") else de
        if hasattr(dt, "hour"):
            return dt.strftime("%Y-%m-%d %H:%M") if (dt.hour, dt.minute) != (0, 0) else dt.strftime("%Y-%m-%d")
        if hasattr(dt, "year"):
            return dt.strftime("%Y-%m-%d")
    dur = comp.get("duration")
    if dur:
        try:
            return f"duracion: {dur.dt}"
        except Exception:
            return f"duracion: {dur}"
    return ""


def formatear_detalle_evento_por_url(resource_url: str) -> str:
    """
    Lee el .ics del evento por URL y devuelve texto con todos los campos principales del VEVENT.
    """
    _set_last_evento_error("")
    u = (resource_url or "").strip()
    if not u:
        _set_last_evento_error("URL de evento vacia")
        return ""
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        _set_last_evento_error("Configuracion CalDAV incompleta")
        return ""
    if not caldav or not Calendar:
        _set_last_evento_error("Dependencia caldav/icalendar no disponible")
        return ""

    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        ev_obj = caldav.Event(client, url=u)
        raw = ev_obj.data
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        cal = Calendar.from_ical(raw)
    except Exception as exc:
        _set_last_evento_error(str(exc)[:300])
        return ""

    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        summ, _ = _vevent_summary_uid(comp)
        st = _vevent_start_for_sort(comp)
        start_s = ""
        if st:
            if hasattr(st, "hour") and (st.hour, st.minute) != (0, 0):
                start_s = st.strftime("%Y-%m-%d %H:%M")
            else:
                start_s = st.strftime("%Y-%m-%d")
        end_s = _vevent_dtend_or_duration(comp)
        desc = str(comp.get("description") or "").strip()
        loc = str(comp.get("location") or "").strip()
        partes = [
            f"Titulo: {summ or '(sin titulo)'}",
            f"Inicio: {start_s or '(desconocido)'}",
        ]
        if end_s:
            partes.append(f"Fin / {end_s}")
        if loc:
            partes.append(f"Ubicacion: {loc}")
        if desc:
            partes.append(f"Descripcion:\n{desc}")
        return "\n\n".join(partes)

    _set_last_evento_error("No se encontro VEVENT en el recurso")
    return ""


def borrar_evento_por_url(resource_url: str) -> bool:
    """Elimina un evento CalDAV por URL del recurso (.ics)."""
    _set_last_evento_error("")
    if not resource_url or not resource_url.strip():
        _set_last_evento_error("URL de evento vacia")
        return False
    if not all([config.CALDAV_URL, config.CALDAV_USER, config.CALDAV_PASS]):
        _set_last_evento_error("Configuracion CalDAV incompleta")
        return False
    if not caldav:
        _set_last_evento_error("Dependencia caldav no disponible")
        return False

    u = resource_url.strip()
    try:
        client = caldav.DAVClient(
            config.CALDAV_URL,
            username=config.CALDAV_USER,
            password=config.CALDAV_PASS,
        )
        ev_obj = caldav.Event(client, url=u)
        ev_obj.delete()
        return True
    except Exception as exc:
        _set_last_evento_error(str(exc)[:300])
        return False
