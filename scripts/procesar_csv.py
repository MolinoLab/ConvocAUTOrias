#!/usr/bin/env python3
"""
Migra el CSV de subvenciones (Excel subvenciones act 3 feb.xlsx - convocatorias.csv)
al esquema esperado por el sistema: id, url, titulo, descripcion, plazo_fin, requisitos,
estado, fecha_ingesta, fuente.
"""
import csv
import hashlib
import os
from datetime import datetime
from pathlib import Path

# Rutas relativas al directorio del proyecto
DIR_PROYECTO = Path(__file__).resolve().parent.parent
CSV_ORIGEN = DIR_PROYECTO / "Excel subvenciones act 3 feb.xlsx - convocatorias.csv"
CSV_DESTINO = DIR_PROYECTO / "convocatorias.csv"

# Mapeo de columnas del CSV origen (índice)
COL_FECHA = 0
COL_ENTIDAD = 1
COL_LINK = 2
COL_OBJETO = 3
COL_LINK2 = 4
COL_BASES = 5
COL_COMENTARIOS = 6


def _es_url(valor: str) -> bool:
    """Comprueba si el valor parece una URL válida."""
    if not valor or not isinstance(valor, str):
        return False
    s = valor.strip()
    return s.startswith("http://") or s.startswith("https://")


def _generar_id(url: str) -> str:
    """Genera un ID único basado en la URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _limpiar(valor: str) -> str:
    """Limpia y normaliza un valor de texto."""
    if valor is None:
        return ""
    return str(valor).strip()


def procesar_fila(fila: list) -> dict | None:
    """
    Convierte una fila del CSV origen al esquema destino.
    Retorna None si la fila no tiene URL y debe omitirse.
    """
    # Asegurar que la fila tiene suficientes columnas
    while len(fila) <= COL_COMENTARIOS:
        fila.append("")

    link = _limpiar(fila[COL_LINK])
    link2 = _limpiar(fila[COL_LINK2])
    url = link if _es_url(link) else (link2 if _es_url(link2) else "")

    if not url:
        return None

    entidad = _limpiar(fila[COL_ENTIDAD])
    objeto = _limpiar(fila[COL_OBJETO])
    titulo = f"{entidad} - {objeto}".strip(" -") if entidad or objeto else url

    descripcion = objeto or entidad or ""

    fecha = _limpiar(fila[COL_FECHA])
    bases = _limpiar(fila[COL_BASES])
    comentarios = _limpiar(fila[COL_COMENTARIOS])
    requisitos = " | ".join(filter(None, [bases, comentarios]))

    return {
        "id": _generar_id(url),
        "url": url,
        "titulo": titulo,
        "descripcion": descripcion,
        "plazo_fin": fecha,  # Texto; parseo inteligente en fases posteriores
        "requisitos": requisitos,
        "estado": "pendiente",
        "fecha_ingesta": datetime.now().isoformat(),
        "fuente": "csv",
    }


def main():
    if not CSV_ORIGEN.exists():
        print(f"Error: No se encuentra el archivo {CSV_ORIGEN}")
        return 1

    registros = []
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    for enc in encodings:
        try:
            with open(CSV_ORIGEN, encoding=enc, newline="") as f:
                reader = csv.reader(f)
                next(reader)  # Saltar cabecera
                for fila in reader:
                    if not fila:
                        continue
                    conv = procesar_fila(fila)
                    if conv:
                        registros.append(conv)
            break
        except UnicodeDecodeError:
            continue
    else:
        print("Error: No se pudo decodificar el CSV con los encodings probados.")
        return 1

    campos = ["id", "url", "titulo", "descripcion", "plazo_fin", "requisitos", "estado", "fecha_ingesta", "fuente"]

    with open(CSV_DESTINO, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(registros)

    print(f"Migración completada: {len(registros)} convocatorias escritas en {CSV_DESTINO}")
    return 0


if __name__ == "__main__":
    exit(main())
