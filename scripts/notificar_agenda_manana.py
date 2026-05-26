"""
Notifica por Telegram eventos CalDAV y tareas (Deck + VTODO) para mañana
y tareas vencidas pendientes (due anterior a mañana), en APP_TIMEZONE.
Si no hay nada, no envía mensaje.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.caldav_client import listar_eventos_en_ventana, listar_tareas
from src.deck_client import listar_tareas_deck
from src.fecha_display import (
    ahora_local,
    fecha_hoy_relativas,
    formatear_dia_mes_sin_anio,
    ventana_dia_local,
)
from src.notifier import enviar_mensaje_a_chats

CHUNK = 4000


def _manana_local() -> tuple:
    d = fecha_hoy_relativas() + timedelta(days=1)
    return d, d.isoformat()


def _enviar_largo(texto: str) -> bool:
    if not texto.strip():
        return True
    return enviar_mensaje_a_chats(texto, chunk=CHUNK)


def _deck_vencidas(deck_all: list, iso_manana: str) -> list:
    return sorted(
        [
            t
            for t in deck_all
            if (due := (t.get("due") or "").strip()) and due < iso_manana
        ],
        key=lambda x: (x.get("due") or "", x.get("stack_title") or "", x.get("title") or ""),
    )


def _vtodos_vencidas(vtodos_all: list, iso_manana: str) -> list:
    return sorted(
        [
            t
            for t in vtodos_all
            if (due := (t.get("due") or "").strip()) and due < iso_manana
        ],
        key=lambda x: (x.get("due") or "", x.get("summary") or ""),
    )


def main() -> int:
    d_manana, iso = _manana_local()
    generado = ahora_local().strftime("%d-%m-%Y %H:%M")
    win_start, win_end_excl = ventana_dia_local(d_manana)

    eventos = listar_eventos_en_ventana(win_start, win_end_excl, agenda_telegram_username=None)
    deck_all = listar_tareas_deck()
    deck_manana = [t for t in deck_all if (t.get("due") or "") == iso]
    deck_vencidas = _deck_vencidas(deck_all, iso)

    vtodos_all = listar_tareas(include_completed=False, agenda_telegram_username=None)
    vtodos_manana = [t for t in vtodos_all if (t.get("due") or "") == iso]
    vtodos_vencidas = _vtodos_vencidas(vtodos_all, iso)

    if not eventos and not deck_manana and not deck_vencidas and not vtodos_manana and not vtodos_vencidas:
        print(
            f"Nada pendiente para mañana ni vencidas ({formatear_dia_mes_sin_anio(iso)}, "
            f"{config.APP_TIMEZONE}). No se envia Telegram."
        )
        return 0

    iso_show = formatear_dia_mes_sin_anio(iso)
    lineas = [
        f"Recordatorio: agenda para mañana ({iso_show}, {config.APP_TIMEZONE}).\n",
        f"Generado: {generado}\n",
    ]

    if deck_vencidas or vtodos_vencidas:
        lineas.append("\nTareas vencidas (pendientes):")
        for t in deck_vencidas:
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            due_show = formatear_dia_mes_sin_anio(t.get("due") or "")
            lineas.append(f"  • [{due_show}]{col} {t.get('title') or '(sin titulo)'}")
        for t in vtodos_vencidas:
            cal = t.get("calendario")
            suf = f" ({cal})" if cal else ""
            due_v = formatear_dia_mes_sin_anio(t.get("due") or "")
            lineas.append(f"  • [{due_v}]{suf} {t.get('summary') or '(sin titulo)'}")
        lineas.append("")

    if eventos:
        lineas.append("\nEventos mañana (CalDAV):")
        for ev in eventos:
            cal = ev.get("calendario")
            suf = f" ({cal})" if cal else ""
            fh = formatear_dia_mes_sin_anio(ev["start_iso"])
            lineas.append(f"  • [{fh}]{suf} {ev['summary']}")
        lineas.append("")

    if deck_manana:
        lineas.append("Tareas Deck (vencimiento mañana):")
        for t in sorted(deck_manana, key=lambda x: (x.get("stack_title") or "", x.get("title") or "")):
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            lineas.append(f"  •{col} {t.get('title') or '(sin titulo)'}")
        lineas.append("")

    if vtodos_manana:
        lineas.append("Tareas calendario (VTODO, due mañana):")
        for t in vtodos_manana:
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
