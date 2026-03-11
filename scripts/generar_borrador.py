"""
Genera un borrador para una convocatoria y opcionalmente lo sube a Nextcloud.
Uso: python scripts/generar_borrador.py <id>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import buscar_por_id
from src.adaptador import adaptar_y_subir


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/generar_borrador.py <id_convocatoria>")
        sys.exit(1)
    id_conv = sys.argv[1].strip()
    conv = buscar_por_id(id_conv)
    if not conv:
        print(f"No se encontró convocatoria con id '{id_conv}'")
        sys.exit(1)
    contenido, ok = adaptar_y_subir(conv.titulo, conv.descripcion, conv.id)
    print(contenido[:500] + "...\n" if len(contenido) > 500 else contenido)
    if ok:
        print("\nBorrador subido a Nextcloud.")
    else:
        print("\nBorrador generado pero no se pudo subir a Nextcloud.")


if __name__ == "__main__":
    main()
