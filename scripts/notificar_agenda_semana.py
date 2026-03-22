"""
Domingo por la noche (previsto vía n8n): resumen de la semana siguiente (lunes a domingo)
en APP_TIMEZONE — eventos CalDAV (todos los calendarios configurados), Deck y VTODO.
Si no hay nada en la ventana, no envía mensaje por Telegram.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.caldav_client import listar_eventos_en_ventana, listar_tareas
from src.deck_client import listar_tareas_deck
from src.notifier import enviar_mensaje_a_chats

CHUNK = 4000


def _zona() -> ZoneInfo:
    name = (config.APP_TIMEZONE or "Europe/Madrid").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Madrid")


def _lunes_semana_siguiente(hoy: date) -> date:
    """Desde un domingo devuelve el lunes siguiente; otros días: próximo lunes."""
    if hoy.weekday() == 6:
        return hoy + timedelta(days=1)
    dias = (7 - hoy.weekday()) % 7
    if dias == 0:
        dias = 7
    return hoy + timedelta(days=dias)


def _enviar_largo(texto: str) -> bool:
    if not texto.strip():
        return True
    return enviar_mensaje_a_chats(texto, chunk=CHUNK)


def main() -> int:
    tz = _zona()
    hoy = datetime.now(tz).date()
    lunes = _lunes_semana_siguiente(hoy)
    domingo = lunes + timedelta(days=6)
    iso_lun = lunes.isoformat()
    iso_dom = domingo.isoformat()

    win_start = datetime.combine(lunes, time.min)
    win_end_excl = win_start + timedelta(days=7)

    eventos = listar_eventos_en_ventana(win_start, win_end_excl)
    deck_all = listar_tareas_deck()
    deck = [
        t
        for t in deck_all
        if (t.get("due") or "") and iso_lun <= t["due"] <= iso_dom
    ]
    vtodos_all = listar_tareas(include_completed=False)
    vtodos = [
        t
        for t in vtodos_all
        if (t.get("due") or "") and iso_lun <= t["due"] <= iso_dom
    ]

    if not eventos and not deck and not vtodos:
        print(
            f"Nada en la semana {iso_lun}–{iso_dom} ({tz.key}). No se envía Telegram."
        )
        return 0

    lineas = [
        f"Agenda de la semana ({iso_lun} a {iso_dom}, {tz.key}).\n",
        "Calendarios MolinoLab / personales según CALDAV_CALENDAR_NAME (varios separados por coma).\n",
        "Próximos 7 días en el bot: /informame\n\n",
    ]

    if eventos:
        lineas.append("Eventos (CalDAV):")
        for ev in eventos:
            cal = ev.get("calendario")
            suf = f" ({cal})" if cal else ""
            lineas.append(f"  • [{ev['start_iso']}]{suf} {ev['summary']}")
        lineas.append("")

    if deck:
        lineas.append("Tareas Deck (vencimiento en la semana):")
        for t in sorted(
            deck, key=lambda x: (x.get("due") or "", x.get("stack_title") or "", x.get("title") or "")
        ):
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            lineas.append(f"  • [{t.get('due')}]{col} {t.get('title') or '(sin titulo)'}")
        lineas.append("")

    if vtodos:
        lineas.append("Tareas calendario (VTODO):")
        for t in sorted(vtodos, key=lambda x: (x.get("due") or "", x.get("summary") or "")):
            cal = t.get("calendario")
            suf = f" ({cal})" if cal else ""
            lineas.append(f"  • [{t.get('due')}]{suf} {t.get('summary') or '(sin titulo)'}")
        lineas.append("")

    texto = "\n".join(lineas).strip()
    if _enviar_largo(texto):
        print("Mensaje semanal enviado por Telegram.")
        return 0
    print(
        "No se pudo enviar por Telegram (TELEGRAM_BOT_TOKEN y "
        "TELEGRAM_CHAT_ID / TELEGRAM_NOTIFY_CHAT_IDS)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
