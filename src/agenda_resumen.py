"""
Resumen de eventos CalDAV y tareas (Deck + VTODO) en una ventana de N días desde hoy.
Usa APP_TIMEZONE vía fecha_hoy_relativas.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from src.caldav_client import (
    listar_eventos_en_ventana,
    listar_tareas,
    obtener_ultimo_error_evento,
)
from src.deck_client import listar_tareas_deck, obtener_ultimo_error_deck
from src.fecha_display import fecha_hoy_relativas


def texto_agenda_proximos_dias(dias: int = 7) -> str:
    """
    Texto listo para Telegram: eventos y tareas con vencimiento/inicio en los próximos `dias`
    días (incluye hoy). `dias` mínimo 1.
    """
    dias = max(1, int(dias))
    hoy = fecha_hoy_relativas()
    win_start = datetime.combine(hoy, time.min)
    win_end_excl = win_start + timedelta(days=dias)
    iso_ini = hoy.isoformat()
    iso_fin_inc = (hoy + timedelta(days=dias - 1)).isoformat()

    eventos = listar_eventos_en_ventana(win_start, win_end_excl)
    deck_all = listar_tareas_deck()
    deck = [
        t
        for t in deck_all
        if (t.get("due") or "") and iso_ini <= t["due"] <= iso_fin_inc
    ]
    vtodos_all = listar_tareas(include_completed=False)
    vtodos = [
        t
        for t in vtodos_all
        if (t.get("due") or "") and iso_ini <= t["due"] <= iso_fin_inc
    ]

    if not eventos and not deck and not vtodos:
        partes = [
            f"Proximos {dias} dias ({iso_ini} a {iso_fin_inc}): "
            "no hay eventos ni tareas con fecha en esa ventana."
        ]
        err_ev = obtener_ultimo_error_evento()
        err_deck = obtener_ultimo_error_deck()
        if err_ev:
            partes.append(f"\n(CalDAV: {err_ev})")
        if err_deck:
            partes.append(f"\n(Deck: {err_deck})")
        return "".join(partes)

    lineas: list[str] = [
        f"Proximos {dias} dias ({iso_ini} a {iso_fin_inc}, hora local segun APP_TIMEZONE):\n"
    ]

    if eventos:
        lineas.append("Eventos (CalDAV):")
        for ev in eventos:
            cal = ev.get("calendario")
            suf = f" ({cal})" if cal else ""
            lineas.append(f"  • [{ev['start_iso']}]{suf} {ev['summary']}")
        lineas.append("")

    if deck:
        lineas.append("Tareas Deck (vencimiento en ventana):")
        for t in sorted(
            deck, key=lambda x: (x.get("due") or "", x.get("stack_title") or "", x.get("title") or "")
        ):
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            lineas.append(f"  • [{t.get('due')}]{col} {t.get('title') or '(sin titulo)'}")
        lineas.append("")

    if vtodos:
        lineas.append("Tareas calendario (VTODO, due en ventana):")
        for t in sorted(vtodos, key=lambda x: (x.get("due") or "", x.get("summary") or "")):
            cal = t.get("calendario")
            suf = f" ({cal})" if cal else ""
            lineas.append(f"  • [{t.get('due')}]{suf} {t.get('summary') or '(sin titulo)'}")
        lineas.append("")

    return "\n".join(lineas).strip()
