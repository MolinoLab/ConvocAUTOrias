"""
Cliente Deck (Nextcloud) para crear tarjetas como tareas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    requests = None
    HTTPBasicAuth = None


_LAST_DECK_ERROR = ""
_LAST_DECK_ASSIGN_WARN = ""


def _set_last_assign_warn(msg: str) -> None:
    global _LAST_DECK_ASSIGN_WARN
    _LAST_DECK_ASSIGN_WARN = (msg or "").strip()[:400]


def obtener_ultimo_aviso_asignacion_deck() -> str:
    return _LAST_DECK_ASSIGN_WARN


def _set_last_error(msg: str) -> None:
    global _LAST_DECK_ERROR
    _LAST_DECK_ERROR = (msg or "").strip()[:600]


def obtener_ultimo_error_deck() -> str:
    return _LAST_DECK_ERROR


def _norm(s: str) -> str:
    return "".join(c.lower() for c in (s or "") if c.isalnum())


def _auth():
    return HTTPBasicAuth(config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD)


def _base_api() -> str:
    return f"{config.NEXTCLOUD_URL.rstrip('/')}/index.php/apps/deck/api/v1.0"


def _headers() -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OCS-APIRequest": "true",
    }


def _asignar_usuarios_a_tarjeta(
    base: str,
    board_id: int,
    stack_id: int,
    card_id: int,
    uids: list[str],
) -> str:
    """Asigna Nextcloud uids a la tarjeta. Devuelve aviso no vacío si algo falló."""
    avisos: list[str] = []
    for uid in uids:
        u = (uid or "").strip()
        if not u:
            continue
        try:
            ra = requests.put(
                f"{base}/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/assignUser",
                headers=_headers(),
                auth=_auth(),
                json={"userId": u},
                timeout=20,
            )
            if ra.status_code not in (200, 201):
                avisos.append(f"{u}:{ra.status_code}")
        except Exception as exc:
            avisos.append(f"{u}:{str(exc)[:80]}")
    return "; ".join(avisos) if avisos else ""


def crear_tarea_deck(
    titulo: str,
    descripcion: str = "",
    fecha_due: str | None = None,
    board_name: str | None = None,
    stack_name: str | None = None,
    assigned_user_uids: list[str] | None = None,
) -> bool:
    """
    Crea una tarjeta en Deck. Busca tablero por nombre y luego columna/stack.
    Opcional: assigned_user_uids (uid de usuario Nextcloud, string) vía assignUser tras crear.
    """
    _set_last_error("")
    _set_last_assign_warn("")
    if not requests or not HTTPBasicAuth:
        _set_last_error("requests no disponible para Deck API")
        return False

    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        _set_last_error("Configuracion Nextcloud incompleta para Deck API")
        return False

    board_target = (board_name or config.DECK_BOARD_NAME or "MolinoLab").strip()
    stack_target = (stack_name or config.DECK_STACK_NAME or "").strip()
    base = _base_api()

    try:
        rb = requests.get(f"{base}/boards", headers=_headers(), auth=_auth(), timeout=20)
        if rb.status_code != 200:
            _set_last_error(f"Deck boards devolvio {rb.status_code}")
            return False
        boards = rb.json() if rb.text else []
    except Exception as exc:
        _set_last_error(f"Error consultando boards Deck: {str(exc)[:180]}")
        return False

    board = None
    for b in boards if isinstance(boards, list) else []:
        if _norm(str(b.get("title", ""))) == _norm(board_target):
            board = b
            break
    if not board:
        _set_last_error(f"No se encontro board Deck '{board_target}'")
        return False

    board_id = board.get("id")
    try:
        rs = requests.get(
            f"{base}/boards/{board_id}/stacks",
            headers=_headers(),
            auth=_auth(),
            timeout=20,
        )
        if rs.status_code != 200:
            _set_last_error(f"Deck stacks devolvio {rs.status_code}")
            return False
        stacks = rs.json() if rs.text else []
    except Exception as exc:
        _set_last_error(f"Error consultando stacks Deck: {str(exc)[:180]}")
        return False

    stack = None
    if stack_target:
        for s in stacks if isinstance(stacks, list) else []:
            if _norm(str(s.get("title", ""))) == _norm(stack_target):
                stack = s
                break
    if not stack:
        for s in stacks if isinstance(stacks, list) else []:
            if not s.get("archived"):
                stack = s
                break
    if not stack and isinstance(stacks, list) and stacks:
        stack = stacks[0]
    if not stack:
        _set_last_error("No se encontro stack en board Deck")
        return False

    stack_id = stack.get("id")
    payload = {"title": titulo[:255], "description": descripcion or ""}
    if fecha_due:
        payload["duedate"] = f"{fecha_due}T12:00:00+00:00"

    try:
        rc = requests.post(
            f"{base}/boards/{board_id}/stacks/{stack_id}/cards",
            headers=_headers(),
            auth=_auth(),
            json=payload,
            timeout=20,
        )
        if rc.status_code in (200, 201):
            card_id = None
            try:
                data = rc.json() if rc.text else {}
                if isinstance(data, dict):
                    card_id = data.get("id")
            except Exception:
                card_id = None
            uids = [u for u in (assigned_user_uids or []) if (u or "").strip()]
            if uids and card_id is not None:
                warn = _asignar_usuarios_a_tarjeta(
                    base, int(board_id), int(stack_id), int(card_id), uids
                )
                if warn:
                    _set_last_assign_warn(f"Asignacion Deck: {warn}")
            elif uids and card_id is None:
                _set_last_assign_warn(
                    "Asignacion Deck omitida: la API no devolvio id de tarjeta."
                )
            return True
        _set_last_error(f"Crear card Deck devolvio {rc.status_code}")
        return False
    except Exception as exc:
        _set_last_error(f"Error creando card Deck: {str(exc)[:180]}")
        return False


def _obtener_board_id_y_stacks(
    board_name: str | None,
) -> tuple[int, list] | None:
    """Devuelve (board_id, stacks_json) o None si falla."""
    board_target = (board_name or config.DECK_BOARD_NAME or "MolinoLab").strip()
    base = _base_api()
    try:
        rb = requests.get(f"{base}/boards", headers=_headers(), auth=_auth(), timeout=20)
        if rb.status_code != 200:
            _set_last_error(f"Deck boards devolvio {rb.status_code}")
            return None
        boards = rb.json() if rb.text else []
    except Exception as exc:
        _set_last_error(f"Error consultando boards Deck: {str(exc)[:180]}")
        return None

    board = None
    for b in boards if isinstance(boards, list) else []:
        if _norm(str(b.get("title", ""))) == _norm(board_target):
            board = b
            break
    if not board:
        _set_last_error(f"No se encontro board Deck '{board_target}'")
        return None

    board_id = board.get("id")
    try:
        rs = requests.get(
            f"{base}/boards/{board_id}/stacks",
            headers=_headers(),
            auth=_auth(),
            timeout=20,
        )
        if rs.status_code != 200:
            _set_last_error(f"Deck stacks devolvio {rs.status_code}")
            return None
        stacks = rs.json() if rs.text else []
    except Exception as exc:
        _set_last_error(f"Error consultando stacks Deck: {str(exc)[:180]}")
        return None

    return int(board_id), stacks if isinstance(stacks, list) else []


def _duedate_a_fecha_iso(duedate: object) -> str:
    """Convierte duedate API (string ISO o None) a YYYY-MM-DD o cadena vacía."""
    if duedate is None:
        return ""
    s = str(duedate).strip()
    if not s:
        return ""
    if "T" in s:
        return s.split("T", 1)[0]
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s[:10] if len(s) >= 10 else s


def listar_tareas_deck(board_name: str | None = None) -> list[dict]:
    """
    Lista tarjetas no archivadas del tablero configurado (todas las columnas).
    Cada dict: title, due (YYYY-MM-DD o ""), board_id, stack_id, card_id, stack_title.
    """
    _set_last_error("")
    if not requests or not HTTPBasicAuth:
        _set_last_error("requests no disponible para Deck API")
        return []

    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        _set_last_error("Configuracion Nextcloud incompleta para Deck API")
        return []

    got = _obtener_board_id_y_stacks(board_name)
    if not got:
        return []
    board_id, stacks = got
    base = _base_api()
    resultado: list[dict] = []

    for stack in stacks:
        stack_id = stack.get("id")
        stack_title = str(stack.get("title") or "")
        cards = stack.get("cards") if isinstance(stack.get("cards"), list) else []
        for card in cards:
            if not isinstance(card, dict):
                continue
            if card.get("archived"):
                continue
            cid = card.get("id")
            if cid is None:
                continue
            resultado.append(
                {
                    "title": str(card.get("title") or ""),
                    "due": _duedate_a_fecha_iso(card.get("duedate")),
                    "board_id": board_id,
                    "stack_id": int(stack_id) if stack_id is not None else 0,
                    "card_id": int(cid),
                    "stack_title": stack_title,
                }
            )
    return resultado


def obtener_tarjeta_deck(board_id: int, stack_id: int, card_id: int) -> dict | None:
    """
    GET tarjeta individual. Devuelve dict con title, description, duedate (ISO o ""),
    stack_title (si se puede resolver), labels (lista de titulos o []), board_id, stack_id, card_id.
    """
    _set_last_error("")
    if not requests or not HTTPBasicAuth:
        _set_last_error("requests no disponible para Deck API")
        return None
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        _set_last_error("Configuracion Nextcloud incompleta para Deck API")
        return None

    base = _base_api()
    try:
        r = requests.get(
            f"{base}/boards/{board_id}/stacks/{stack_id}/cards/{card_id}",
            headers=_headers(),
            auth=_auth(),
            timeout=20,
        )
        if r.status_code != 200:
            _set_last_error(f"GET card Deck devolvio {r.status_code}")
            return None
        card = r.json() if r.text else None
    except Exception as exc:
        _set_last_error(f"Error leyendo card Deck: {str(exc)[:180]}")
        return None

    if not isinstance(card, dict):
        return None

    stack_title = ""
    got = _obtener_board_id_y_stacks(None)
    if got:
        _, stacks = got
        for s in stacks:
            if int(s.get("id") or 0) == int(stack_id):
                stack_title = str(s.get("title") or "")
                break

    labels_raw = card.get("labels") or card.get("labelsAssigned") or []
    labels: list[str] = []
    if isinstance(labels_raw, list):
        for lb in labels_raw:
            if isinstance(lb, dict):
                t = lb.get("title") or lb.get("label") or lb.get("name")
                if t:
                    labels.append(str(t))
            elif isinstance(lb, str):
                labels.append(lb)

    dd = card.get("duedate")
    due_s = str(dd).strip() if dd is not None and str(dd).strip() else ""

    return {
        "title": str(card.get("title") or ""),
        "description": str(card.get("description") or ""),
        "duedate": due_s,
        "due_date_only": _duedate_a_fecha_iso(dd) if dd else "",
        "stack_title": stack_title,
        "labels": labels,
        "board_id": board_id,
        "stack_id": stack_id,
        "card_id": card_id,
    }


def borrar_tarjeta_deck(board_id: int, stack_id: int, card_id: int) -> bool:
    """Elimina una tarjeta Deck por ids."""
    _set_last_error("")
    if not requests or not HTTPBasicAuth:
        _set_last_error("requests no disponible para Deck API")
        return False
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        _set_last_error("Configuracion Nextcloud incompleta para Deck API")
        return False

    base = _base_api()
    try:
        r = requests.delete(
            f"{base}/boards/{board_id}/stacks/{stack_id}/cards/{card_id}",
            headers=_headers(),
            auth=_auth(),
            timeout=20,
        )
        if r.status_code in (200, 204):
            return True
        _set_last_error(f"Borrar card Deck devolvio {r.status_code}: {(r.text or '')[:120]}")
        return False
    except Exception as exc:
        _set_last_error(f"Error borrando card Deck: {str(exc)[:180]}")
        return False
