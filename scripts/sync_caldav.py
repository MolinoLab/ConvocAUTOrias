"""
Sincroniza convocatorias con plazos parseables al calendario CalDAV.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import es_convocatoria_en_seguimiento, listar
from src.caldav_client import crear_evento, evento_convocatoria_ya_en_calendario_escritura
from src.plazo import parsear_plazo_iso


def main():
    convocatorias = listar()
    pendientes = [c for c in convocatorias if es_convocatoria_en_seguimiento(c.estado)]
    creados = 0
    omitidos = 0
    for c in pendientes:
        fecha = parsear_plazo_iso(c.plazo_fin)
        if fecha:
            if evento_convocatoria_ya_en_calendario_escritura(fecha, c.url, c.titulo):
                omitidos += 1
                print(f"Omitido (ya existe en calendario): {c.titulo[:40]}... ({fecha})")
                continue
            if crear_evento(c.titulo, fecha, c.descripcion, c.url):
                creados += 1
                print(f"Evento creado: {c.titulo[:40]}... ({fecha})")
    print(f"Total: {creados} eventos añadidos; {omitidos} omitidos por duplicado.")


if __name__ == "__main__":
    main()
