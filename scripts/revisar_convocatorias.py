"""
Revisa plazos de convocatorias y envía recordatorios por Telegram.
Lista las pendientes y opcionalmente notifica las que tienen plazo próximo.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import listar
from src.notifier import enviar_mensaje


def _parsear_plazo(plazo_texto: str) -> datetime | None:
    """
    Intenta parsear plazo_fin a fecha.
    Soporta: "16-nov", "4 mayo", "1-nov", formatos DD/MM/YYYY, etc.
    """
    if not plazo_texto or not plazo_texto.strip():
        return None
    s = plazo_texto.strip().lower()
    año_actual = datetime.now().year

    # DD-MM o D-MM (ej. 16-nov, 1-nov)
    m = re.match(r"(\d{1,2})[-]?(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)", s)
    if m:
        dia = int(m.group(1))
        meses = "ene feb mar abr may jun jul ago sep oct nov dic".split()
        try:
            mes = meses.index(m.group(2)) + 1
            return datetime(año_actual, mes, min(dia, 28))
        except (ValueError, IndexError):
            pass

    # DD/MM/YYYY o DD-MM-YYYY
    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", s)
    if m:
        d, m_val, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y if y > 100 else 2000 + y
        try:
            return datetime(y, m_val, min(d, 28))
        except ValueError:
            pass

    return None


def main():
    convocatorias = listar()
    pendientes = [c for c in convocatorias if c.estado == "pendiente"]

    if not pendientes:
        print("No hay convocatorias pendientes.")
        return 0

    # Con plazos parseables y próximos (dentro de 30 días)
    hoy = datetime.now()
    proximas = []
    sin_plazo = []

    for c in pendientes:
        fecha = _parsear_plazo(c.plazo_fin)
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
