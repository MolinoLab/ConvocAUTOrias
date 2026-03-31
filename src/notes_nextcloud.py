"""
Cliente API REST de Nextcloud Notes (v1) con credenciales del usuario humano.
"""
from __future__ import annotations

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

_LAST_ERR = ""


def obtener_ultimo_error() -> str:
    return _LAST_ERR


def _set_err(msg: str) -> None:
    global _LAST_ERR
    _LAST_ERR = (msg or "").strip()[:400]


def credenciales_para_telegram_username(username: str | None, user_id: int | None) -> tuple[str, str] | None:
    """
    Resuelve (nc_user, app_password) desde NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM.
    username: sin @, minúsculas.
    """
    if config.NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM and username:
        u = username.strip().lstrip("@").lower()
        row = config.NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM.get(u)
        if row:
            nu = (row.get("nc_user") or "").strip()
            pw = (row.get("app_password") or "").strip()
            if nu and pw:
                return nu, pw
    _set_err(
        "Notas Nextcloud: añade tu usuario en NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM en .env "
        '(JSON por username de Telegram: nc_user + app_password).'
    )
    return None


def _base_api() -> str:
    return f"{config.NEXTCLOUD_URL.rstrip('/')}/index.php/apps/notes/api/v1"


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "OCS-APIRequest": "true",
    }


def _auth(nc_user: str, app_password: str):
    return HTTPBasicAuth(nc_user, app_password)


def listar_notas(nc_user: str, app_password: str) -> list[dict] | None:
    _set_err("")
    if not requests or not HTTPBasicAuth:
        _set_err("requests no disponible")
        return None
    if not config.NEXTCLOUD_URL:
        _set_err("NEXTCLOUD_URL no configurada")
        return None
    try:
        r = requests.get(
            f"{_base_api()}/notes",
            auth=_auth(nc_user, app_password),
            headers=_headers(),
            params={"exclude": "etag"},
            timeout=25,
        )
        if r.status_code != 200:
            _set_err(f"Notes list {r.status_code}: {(r.text or '')[:120]}")
            return None
        data = r.json()
        if not isinstance(data, list):
            _set_err("Respuesta Notes inesperada")
            return None
        return data
    except Exception as exc:
        _set_err(str(exc)[:200])
        return None


def obtener_nota(nc_user: str, app_password: str, note_id: int) -> dict | None:
    _set_err("")
    if not requests:
        return None
    try:
        r = requests.get(
            f"{_base_api()}/notes/{note_id}",
            auth=_auth(nc_user, app_password),
            headers=_headers(),
            timeout=25,
        )
        if r.status_code != 200:
            _set_err(f"Notes get {r.status_code}: {(r.text or '')[:120]}")
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        _set_err(str(exc)[:200])
        return None


def crear_nota(nc_user: str, app_password: str, titulo: str, contenido: str = "") -> dict | None:
    _set_err("")
    if not requests:
        return None
    payload = {"title": (titulo or "(sin titulo)")[:400], "content": contenido or ""}
    try:
        r = requests.post(
            f"{_base_api()}/notes",
            auth=_auth(nc_user, app_password),
            headers=_headers(),
            json=payload,
            timeout=25,
        )
        if r.status_code not in (200, 201):
            _set_err(f"Notes create {r.status_code}: {(r.text or '')[:120]}")
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        _set_err(str(exc)[:200])
        return None


def actualizar_nota(
    nc_user: str,
    app_password: str,
    note_id: int,
    *,
    titulo: str | None = None,
    contenido: str | None = None,
) -> dict | None:
    _set_err("")
    if not requests:
        return None
    cur = obtener_nota(nc_user, app_password, note_id)
    if not cur:
        return None
    payload = {
        "title": titulo if titulo is not None else (cur.get("title") or ""),
        "content": contenido if contenido is not None else (cur.get("content") or ""),
    }
    try:
        r = requests.put(
            f"{_base_api()}/notes/{note_id}",
            auth=_auth(nc_user, app_password),
            headers=_headers(),
            json=payload,
            timeout=25,
        )
        if r.status_code != 200:
            _set_err(f"Notes put {r.status_code}: {(r.text or '')[:120]}")
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        _set_err(str(exc)[:200])
        return None


def borrar_nota(nc_user: str, app_password: str, note_id: int) -> bool:
    _set_err("")
    if not requests:
        return False
    try:
        r = requests.delete(
            f"{_base_api()}/notes/{note_id}",
            auth=_auth(nc_user, app_password),
            headers=_headers(),
            timeout=25,
        )
        if r.status_code in (200, 204):
            return True
        _set_err(f"Notes delete {r.status_code}: {(r.text or '')[:120]}")
        return False
    except Exception as exc:
        _set_err(str(exc)[:200])
        return False
