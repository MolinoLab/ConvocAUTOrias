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


def crear_tarea_deck(
    titulo: str,
    descripcion: str = "",
    fecha_due: str | None = None,
    board_name: str | None = None,
    stack_name: str | None = None,
) -> bool:
    """
    Crea una tarjeta en Deck. Busca tablero por nombre y luego columna/stack.
    """
    _set_last_error("")
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
            return True
        _set_last_error(f"Crear card Deck devolvio {rc.status_code}")
        return False
    except Exception as exc:
        _set_last_error(f"Error creando card Deck: {str(exc)[:180]}")
        return False
