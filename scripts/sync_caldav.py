"""
Sincroniza convocatorias con plazos parseables al calendario CalDAV.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import listar
from src.caldav_client import crear_evento


def _parsear_plazo(plazo_texto: str) -> str | None:
    """Retorna fecha en formato YYYY-MM-DD o None."""
    if not plazo_texto or not plazo_texto.strip():
        return None
    s = plazo_texto.strip().lower()
    año = datetime.now().year

    m = re.match(r"(\d{1,2})[-]?(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)", s)
    if m:
        dia = int(m.group(1))
        meses = "ene feb mar abr may jun jul ago sep oct nov dic".split()
        try:
            mes = meses.index(m.group(2)) + 1
            return f"{año}-{mes:02d}-{min(dia, 28):02d}"
        except (ValueError, IndexError):
            pass

    m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", s)
    if m:
        d, m_val, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y if y > 100 else 2000 + y
        try:
            return f"{y}-{m_val:02d}-{min(d, 28):02d}"
        except ValueError:
            pass
    return None


def main():
    convocatorias = listar()
    pendientes = [c for c in convocatorias if c.estado == "pendiente"]
    creados = 0
    for c in pendientes:
        fecha = _parsear_plazo(c.plazo_fin)
        if fecha:
            if crear_evento(c.titulo, fecha, c.descripcion, c.url):
                creados += 1
                print(f"Evento creado: {c.titulo[:40]}... ({fecha})")
    print(f"Total: {creados} eventos añadidos al calendario.")


if __name__ == "__main__":
    main()
