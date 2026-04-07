"""
Cliente mínimo Tuya Cloud para consultar y cambiar estado de un enchufe.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import config

try:
    import requests
except ImportError:
    requests = None


_LAST_TUYA_ERROR = ""


def _set_last_error(msg: str) -> None:
    global _LAST_TUYA_ERROR
    _LAST_TUYA_ERROR = (msg or "").strip()[:700]


def obtener_ultimo_error_tuya() -> str:
    return _LAST_TUYA_ERROR


def _base_url() -> str:
    base = (config.TUYA_API_BASE_URL or "").strip().rstrip("/")
    if base:
        return base
    region = (config.TUYA_REGION or "eu").strip().lower()
    return f"https://openapi.tuya{region}.com"


def _sha256_hex(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _sign(
    client_id: str,
    secret: str,
    t_ms: str,
    string_to_sign: str,
    access_token: str = "",
) -> str:
    payload = f"{client_id}{access_token}{t_ms}{string_to_sign}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()


def _request(
    method: str,
    path: str,
    *,
    token: str = "",
    body: dict | None = None,
) -> tuple[bool, dict]:
    _set_last_error("")
    if requests is None:
        _set_last_error("requests no disponible.")
        return False, {}
    if not config.TUYA_CLIENT_ID or not config.TUYA_CLIENT_SECRET:
        _set_last_error("Faltan TUYA_CLIENT_ID o TUYA_CLIENT_SECRET.")
        return False, {}
    base = _base_url()
    url = f"{base}{path}"
    t_ms = str(int(time.time() * 1000))
    body_text = json.dumps(body or {}, separators=(",", ":"), ensure_ascii=False) if body else ""
    content_sha = _sha256_hex(body_text)
    parsed = urlparse(url)
    url_part = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    string_to_sign = f"{method.upper()}\n{content_sha}\n\n{url_part}"
    sign = _sign(
        config.TUYA_CLIENT_ID,
        config.TUYA_CLIENT_SECRET,
        t_ms,
        string_to_sign,
        access_token=token,
    )
    headers = {
        "client_id": config.TUYA_CLIENT_ID,
        "t": t_ms,
        "sign_method": "HMAC-SHA256",
        "sign": sign,
    }
    if token:
        headers["access_token"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        resp = requests.request(
            method.upper(),
            url,
            headers=headers,
            data=body_text if body is not None else None,
            timeout=15,
        )
        data = resp.json() if resp.text else {}
    except Exception as exc:
        _set_last_error(f"Error Tuya request: {str(exc)[:180]}")
        return False, {}
    if not isinstance(data, dict):
        _set_last_error(f"Respuesta Tuya inválida ({resp.status_code}).")
        return False, {}
    if not data.get("success"):
        _set_last_error(str(data.get("msg") or f"HTTP {resp.status_code}"))
        return False, data
    return True, data


def _get_access_token() -> str | None:
    ok, data = _request("GET", "/v1.0/token?grant_type=1")
    if not ok:
        return None
    result = data.get("result") or {}
    tok = str(result.get("access_token") or "").strip()
    if not tok:
        _set_last_error("Tuya no devolvió access_token.")
        return None
    return tok


def obtener_estado_enchufe(device_id: str | None = None) -> tuple[bool, str]:
    did = (device_id or config.TUYA_DEVICE_ID or "").strip()
    if not did:
        _set_last_error("Falta TUYA_DEVICE_ID.")
        return False, ""
    tok = _get_access_token()
    if not tok:
        return False, ""
    ok, data = _request("GET", f"/v1.0/devices/{did}/status", token=tok)
    if not ok:
        return False, ""
    result = data.get("result")
    if not isinstance(result, list):
        return True, "Estado recibido, pero sin lista de propiedades."
    estado = {str(x.get("code")): x.get("value") for x in result if isinstance(x, dict)}
    sw = estado.get(config.TUYA_SWITCH_CODE or "switch_1")
    estado_txt = "encendido" if bool(sw) else "apagado"
    return True, f"Enchufe {estado_txt}."


def poner_enchufe(
    on: bool,
    *,
    device_id: str | None = None,
    switch_code: str | None = None,
) -> tuple[bool, str]:
    did = (device_id or config.TUYA_DEVICE_ID or "").strip()
    if not did:
        _set_last_error("Falta TUYA_DEVICE_ID.")
        return False, ""
    tok = _get_access_token()
    if not tok:
        return False, ""
    cmd_code = (switch_code or config.TUYA_SWITCH_CODE or "switch_1").strip()
    payload = {"commands": [{"code": cmd_code, "value": bool(on)}]}
    ok, _ = _request("POST", f"/v1.0/devices/{did}/commands", token=tok, body=payload)
    if not ok:
        return False, ""
    return True, "Enchufe encendido." if on else "Enchufe apagado."
