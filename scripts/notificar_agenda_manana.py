"""
Notifica por Telegram eventos CalDAV y tareas (Deck + VTODO) con fecha el día siguiente
respecto al calendario Europe/Madrid. Si no hay nada, no envía mensaje.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.caldav_client import listar_eventos_en_ventana, listar_tareas
from src.deck_client import listar_tareas_deck
from src.notifier import enviar_mensaje

MADRID = ZoneInfo("Europe/Madrid")
CHUNK = 4000


def _manana_madrid() -> tuple[date, str]:
    d = datetime.now(MADRID).date() + timedelta(days=1)
    return d, d.isoformat()


def _enviar_largo(texto: str) -> bool:
    if not texto.strip():
        return True
    ok = True
    for i in range(0, len(texto), CHUNK):
        if not enviar_mensaje(texto[i : i + CHUNK]):
            ok = False
    return ok


def main() -> int:
    d_manana, iso = _manana_madrid()
    win_start = datetime.combine(d_manana, time.min)
    win_end_excl = win_start + timedelta(days=1)

    eventos = listar_eventos_en_ventana(win_start, win_end_excl)
    deck = [t for t in listar_tareas_deck() if (t.get("due") or "") == iso]
    vtodos = [t for t in listar_tareas(include_completed=False) if (t.get("due") or "") == iso]

    if not eventos and not deck and not vtodos:
        print(f"Nada pendiente para mañana ({iso}, Madrid). No se envia Telegram.")
        return 0

    lineas = [f"Agenda para mañana ({iso}, hora Europa/Madrid):\n"]

    if eventos:
        lineas.append("Eventos (CalDAV):")
        for ev in eventos:
            lineas.append(f"  • [{ev['start_iso']}] {ev['summary']}")
        lineas.append("")

    if deck:
        lineas.append("Tareas Deck (vencimiento mañana):")
        for t in sorted(deck, key=lambda x: (x.get("stack_title") or "", x.get("title") or "")):
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            lineas.append(f"  •{col} {t.get('title') or '(sin titulo)'}")
        lineas.append("")

    if vtodos:
        lineas.append("Tareas calendario (VTODO, due mañana):")
        for t in vtodos:
            lineas.append(f"  • {t.get('summary') or '(sin titulo)'}")
        lineas.append("")

    texto = "\n".join(lineas).strip()
    if _enviar_largo(texto):
        print("Mensaje enviado por Telegram.")
        return 0
    print("No se pudo enviar por Telegram (revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
