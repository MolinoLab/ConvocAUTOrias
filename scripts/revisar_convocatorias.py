"""
Revisa plazos de convocatorias y envía recordatorios por Telegram.
Lista las pendientes y opcionalmente notifica las que tienen plazo próximo.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import es_convocatoria_en_seguimiento, listar
from src.notifier import enviar_mensaje
from src.plazo import parsear_plazo


def main():
    convocatorias = listar()
    pendientes = [c for c in convocatorias if es_convocatoria_en_seguimiento(c.estado)]

    if not pendientes:
        print("No hay convocatorias pendientes.")
        return 0

    # Con plazos parseables y próximos (dentro de 30 días)
    hoy = datetime.now()
    proximas = []
    sin_plazo = []

    for c in pendientes:
        fecha = parsear_plazo(c.plazo_fin)
        if fecha:
            dias = (fecha - hoy).days
            if 0 <= dias <= 30:
                proximas.append((c, dias))
        else:
            sin_plazo.append(c)

    # Salida por consola
    print(f"Convocatorias pendientes: {len(pendientes)}")
    if proximas:
        print("\nPlazos próximos (30 días):")
        for c, dias in sorted(proximas, key=lambda x: x[1]):
            print(f"  - {c.titulo[:50]}... ({dias} días) - {c.url}")
    if sin_plazo:
        print(f"\nSin plazo parseable: {len(sin_plazo)}")

    # Notificación Telegram si hay próximas
    if proximas and enviar_mensaje:
        lineas = ["Recordatorio: convocatorias con plazo próximo:\n"]
        for c, dias in sorted(proximas, key=lambda x: x[1])[:5]:
            lineas.append(f"• {c.titulo[:40]}... ({dias} días)\n{c.url}")
        if enviar_mensaje("\n\n".join(lineas)):
            print("\nNotificación enviada por Telegram.")
        else:
            print("\nNo se pudo enviar notificación (revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
