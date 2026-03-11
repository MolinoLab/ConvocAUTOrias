"""Envía resúmenes y notificaciones por Telegram."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import requests
except ImportError:
    requests = None


def enviar_mensaje(texto: str) -> bool:
    """
    Envía un mensaje al chat configurado en TELEGRAM_CHAT_ID.
    Retorna True si se envió correctamente.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    if not requests:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": texto},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False
