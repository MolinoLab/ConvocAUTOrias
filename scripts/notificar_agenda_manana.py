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
from src.fecha_display import formatear_dia_mes_sin_anio
from src.notifier import enviar_mensaje_a_chats

MADRID = ZoneInfo("Europe/Madrid")
CHUNK = 4000


def _manana_madrid() -> tuple[date, str]:
    d = datetime.now(MADRID).date() + timedelta(days=1)
    return d, d.isoformat()


def _enviar_largo(texto: str) -> bool:
    if not texto.strip():
        return True
    return enviar_mensaje_a_chats(texto, chunk=CHUNK)


def main() -> int:
    d_manana, iso = _manana_madrid()
    win_start = datetime.combine(d_manana, time.min)
    win_end_excl = win_start + timedelta(days=1)

    eventos = listar_eventos_en_ventana(win_start, win_end_excl, agenda_telegram_username=None)
    deck = [t for t in listar_tareas_deck() if (t.get("due") or "") == iso]
    vtodos = [
        t
        for t in listar_tareas(include_completed=False, agenda_telegram_username=None)
        if (t.get("due") or "") == iso
    ]

    if not eventos and not deck and not vtodos:
        print(
            f"Nada pendiente para mañana ({formatear_dia_mes_sin_anio(iso)}, Madrid). "
            "No se envia Telegram."
        )
        return 0

    iso_show = formatear_dia_mes_sin_anio(iso)
    lineas = [
        f"Recordatorio: agenda para mañana ({iso_show}, hora Europa/Madrid).\n",
        "Resumen automático; en el bot usa /informame o /info [días] (calendarios de equipo).\n",
    ]

    if eventos:
        lineas.append("\nEventos (CalDAV):")
        for ev in eventos:
            cal = ev.get("calendario")
            suf = f" ({cal})" if cal else ""
            fh = formatear_dia_mes_sin_anio(ev["start_iso"])
            lineas.append(f"  • [{fh}]{suf} {ev['summary']}")
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
            cal = t.get("calendario")
            suf = f" ({cal})" if cal else ""
            lineas.append(f"  •{suf} {t.get('summary') or '(sin titulo)'}")
        lineas.append("")

    texto = "\n".join(lineas).strip()
    if _enviar_largo(texto):
        print("Mensaje enviado por Telegram.")
        return 0
    print(
        "No se pudo enviar por Telegram (revisa TELEGRAM_BOT_TOKEN y "
        "TELEGRAM_CHAT_ID / TELEGRAM_NOTIFY_CHAT_IDS)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
