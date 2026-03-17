"""
Sincroniza convocatorias con plazos parseables al calendario CalDAV.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import listar
from src.caldav_client import crear_evento
from src.plazo import parsear_plazo_iso


def main():
    convocatorias = listar()
    pendientes = [c for c in convocatorias if c.estado == "pendiente"]
    creados = 0
    for c in pendientes:
        fecha = parsear_plazo_iso(c.plazo_fin)
        if fecha:
            if crear_evento(c.titulo, fecha, c.descripcion, c.url):
                creados += 1
                print(f"Evento creado: {c.titulo[:40]}... ({fecha})")
    print(f"Total: {creados} eventos añadidos al calendario.")


if __name__ == "__main__":
    main()
