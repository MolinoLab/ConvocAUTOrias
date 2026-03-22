"""Envía resúmenes y notificaciones por Telegram."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import requests
except ImportError:
    requests = None


def chat_ids_para_notificaciones() -> list[str]:
    """TELEGRAM_CHAT_ID primero, luego TELEGRAM_NOTIFY_CHAT_IDS sin duplicados."""
    out: list[str] = []
    principal = (config.TELEGRAM_CHAT_ID or "").strip()
    if principal:
        out.append(principal)
    for x in config.TELEGRAM_NOTIFY_CHAT_IDS:
        xs = (x or "").strip()
        if xs and xs not in out:
            out.append(xs)
    return out


def enviar_mensaje(texto: str, chat_id: str | None = None) -> bool:
    """
    Envía un mensaje a un chat de Telegram.
    Si chat_id es None, usa TELEGRAM_CHAT_ID.
    Retorna True si se envió correctamente.
    """
    cid = (chat_id or config.TELEGRAM_CHAT_ID or "").strip()
    if not config.TELEGRAM_BOT_TOKEN or not cid:
        return False
    if not requests:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": cid, "text": texto},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def enviar_mensaje_a_chats(texto: str, chunk: int = 4000) -> bool:
    """
    Envía el mismo texto (partido en trozos) a todos los chats de
    chat_ids_para_notificaciones(). True si al menos un envío tuvo éxito.
    """
    ids = chat_ids_para_notificaciones()
    if not ids:
        return False
    t = texto or ""
    ok_any = False
    for cid in ids:
        for i in range(0, len(t), chunk):
            if enviar_mensaje(t[i : i + chunk], chat_id=cid):
                ok_any = True
    return ok_any
