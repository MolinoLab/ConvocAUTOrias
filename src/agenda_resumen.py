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
from src.fecha_display import fecha_hoy_relativas, formatear_dia_mes_sin_anio


def texto_agenda_proximos_dias(
    dias: int = 7,
    telegram_username: str | None = None,
    *,
    mostrar_calendario: bool = True,
) -> str:
    """
    Texto listo para Telegram: eventos y tareas con vencimiento/inicio en los próximos `dias`
    días (incluye hoy). `dias` mínimo 1.
    Si `mostrar_calendario` es False, no se muestra el nombre del calendario CalDAV (p. ej. /info).
    """
    dias = max(1, int(dias))
    hoy = fecha_hoy_relativas()
    win_start = datetime.combine(hoy, time.min)
    win_end_excl = win_start + timedelta(days=dias)
    iso_ini = hoy.isoformat()
    iso_fin_inc = (hoy + timedelta(days=dias - 1)).isoformat()
    rango_txt = (
        f"{formatear_dia_mes_sin_anio(iso_ini)} a {formatear_dia_mes_sin_anio(iso_fin_inc)}"
    )

    eventos = listar_eventos_en_ventana(
        win_start, win_end_excl, agenda_telegram_username=telegram_username
    )
    deck_all = listar_tareas_deck()
    deck = [
        t
        for t in deck_all
        if (t.get("due") or "") and iso_ini <= t["due"] <= iso_fin_inc
    ]
    vtodos_all = listar_tareas(
        include_completed=False, agenda_telegram_username=telegram_username
    )
    vtodos = [
        t
        for t in vtodos_all
        if (t.get("due") or "") and iso_ini <= t["due"] <= iso_fin_inc
    ]

    if not eventos and not deck and not vtodos:
        partes = [
            f"Proximos {dias} dias ({rango_txt}): "
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
        f"Proximos {dias} dias ({rango_txt}, hora local segun APP_TIMEZONE):\n"
    ]

    if eventos:
        lineas.append("Eventos (CalDAV):")
        for ev in eventos:
            cal = ev.get("calendario")
            suf = f" ({cal})" if (mostrar_calendario and cal) else ""
            fh = formatear_dia_mes_sin_anio(ev["start_iso"])
            lineas.append(f"  • [{fh}]{suf} {ev['summary']}")
        lineas.append("")
    elif deck or vtodos:
        err_ev = obtener_ultimo_error_evento()
        if err_ev:
            lineas.append(
                f"(Sin eventos CalDAV en esta ventana; si esperabas alguno: {err_ev})\n"
            )

    if deck:
        lineas.append("Tareas Deck (vencimiento en ventana):")
        for t in sorted(
            deck, key=lambda x: (x.get("due") or "", x.get("stack_title") or "", x.get("title") or "")
        ):
            col = f" ({t.get('stack_title')})" if t.get("stack_title") else ""
            due_show = formatear_dia_mes_sin_anio(t.get("due") or "")
            lineas.append(f"  • [{due_show}]{col} {t.get('title') or '(sin titulo)'}")
        lineas.append("")

    if vtodos:
        lineas.append("Tareas calendario (VTODO, due en ventana):")
        for t in sorted(vtodos, key=lambda x: (x.get("due") or "", x.get("summary") or "")):
            cal = t.get("calendario")
            suf = f" ({cal})" if (mostrar_calendario and cal) else ""
            due_v = formatear_dia_mes_sin_anio(t.get("due") or "")
            lineas.append(f"  • [{due_v}]{suf} {t.get('summary') or '(sin titulo)'}")
        lineas.append("")

    return "\n".join(lineas).strip()
