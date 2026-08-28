"""
Domingo por la noche (previsto vía n8n): resumen de la semana entrante (lunes a domingo)
en APP_TIMEZONE — eventos CalDAV (calendarios de agenda + personales), Deck y VTODO.
Si no hay nada en la ventana, no envía mensaje por Telegram.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.agenda_notificaciones import (
    filtrar_deck_por_rango,
    filtrar_vtodos_por_rango,
    listar_eventos_agenda_programada,
    listar_vtodos_agenda_programada,
    ventana_semana_entrante,
)
from src.deck_client import listar_tareas_deck
from src.fecha_display import ahora_local, formatear_dia_mes_sin_anio
from src.notifier import enviar_mensaje_a_chats

CHUNK = 4000


def _enviar_largo(texto: str) -> bool:
    if not texto.strip():
        return True
    return enviar_mensaje_a_chats(texto, chunk=CHUNK)


def main() -> int:
    hoy = ahora_local().date()
    generado = ahora_local().strftime("%d-%m-%Y %H:%M")
    lunes, domingo, win_start, win_end_excl = ventana_semana_entrante(hoy)
    iso_lun = lunes.isoformat()
    iso_dom = domingo.isoformat()

    eventos = listar_eventos_agenda_programada(win_start, win_end_excl)
    deck_all = listar_tareas_deck()
    deck = filtrar_deck_por_rango(deck_all, iso_lun, iso_dom)
    vtodos_all = listar_vtodos_agenda_programada(include_completed=False)
    vtodos = filtrar_vtodos_por_rango(vtodos_all, iso_lun, iso_dom)

    if not eventos and not deck and not vtodos:
        print(
            f"Nada en la semana {formatear_dia_mes_sin_anio(iso_lun)} a "
            f"{formatear_dia_mes_sin_anio(iso_dom)} ({config.APP_TIMEZONE}). No se envía Telegram."
        )
        return 0

    rango = f"{formatear_dia_mes_sin_anio(iso_lun)} a {formatear_dia_mes_sin_anio(iso_dom)}"
    lineas = [
        f"Agenda de la semana ({rango}, {config.APP_TIMEZONE}).\n",
        f"Generado: {generado}\n",
        "Próximos días en el bot: /informame o /info [n]\n\n",
    ]

    if eventos:
        lineas.append("Eventos (CalDAV):")
        for ev in eventos:
            cal = ev.get("calendario")
            suf = f" ({cal})" if cal else ""
            fh = formatear_dia_mes_sin_anio(ev["start_iso"])
            lineas.append(f"  • [{fh}]{suf} {ev['summary']}")
        lineas.append("")

    if deck:
        lineas.append("Tareas Deck (vencimiento en la semana):")
        for t in sorted(
            deck, key=lambda x: (x.get("due") or "", x.get("stack_title") or "", x.get("title") or "")
        ):
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            due_show = formatear_dia_mes_sin_anio(t.get("due") or "")
            lineas.append(f"  • [{due_show}]{col} {t.get('title') or '(sin titulo)'}")
        lineas.append("")

    if vtodos:
        lineas.append("Tareas calendario (VTODO):")
        for t in sorted(vtodos, key=lambda x: (x.get("due") or "", x.get("summary") or "")):
            cal = t.get("calendario")
            suf = f" ({cal})" if cal else ""
            due_v = formatear_dia_mes_sin_anio(t.get("due") or "")
            lineas.append(f"  • [{due_v}]{suf} {t.get('summary') or '(sin titulo)'}")
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
