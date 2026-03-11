"""
Worker que scrapea periódicamente las URLs de convocatorias y las enriquece con IA (Ollama).
Actualiza título, descripción, plazo_fin y requisitos en la base de datos.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.db import listar, actualizar
from src.scraper import extraer

INTERVALO_HORAS = 6
TIMEOUT_OLLAMA = 90


def _analizar_con_ollama(titulo: str, contenido: str) -> dict | None:
    """
    Envía el contenido a Ollama para extraer plazo_fin, requisitos y resumen.
    Retorna dict con las claves o None si falla.
    """
    if not contenido or len(contenido.strip()) < 50:
        return None
    try:
        import requests
    except ImportError:
        return None
    prompt = f"""Analiza esta convocatoria y extrae la información en formato JSON.

Título: {titulo[:200]}

Contenido:
{contenido[:4000]}

Responde ÚNICAMENTE con un JSON válido con estas claves (usa strings vacíos si no encuentras):
- "plazo_fin": fecha límite o plazo de presentación
- "requisitos": requisitos principales para optar
- "resumen": resumen en 1-2 frases

Ejemplo: {{"plazo_fin": "15 de noviembre", "requisitos": "Entidad sin ánimo de lucro", "resumen": "Ayudas para proyectos culturales."}}"""
    try:
        r = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=TIMEOUT_OLLAMA,
        )
        if r.status_code != 200:
            return None
        texto = r.json().get("response", "").strip()
        # Intentar extraer JSON del texto (puede venir con markdown o texto extra)
        inicio = texto.find("{")
        fin = texto.rfind("}") + 1
        if inicio >= 0 and fin > inicio:
            return json.loads(texto[inicio:fin])
    except Exception:
        pass
    return None


def _ejecutar_ciclo() -> int:
    """Ejecuta un ciclo de scraping y análisis. Retorna número de convocatorias actualizadas."""
    convocatorias = listar()
    pendientes = [c for c in convocatorias if c.estado == "pendiente"]
    actualizadas = 0
    for conv in pendientes:
        if not conv.url or not conv.url.startswith("http"):
            continue
        datos = extraer(conv.url)
        if not datos:
            continue
        # Actualizar con datos del scraper
        conv.titulo = datos.titulo or conv.titulo
        conv.descripcion = datos.descripcion or conv.descripcion
        conv.plazo_fin = datos.plazo_fin or conv.plazo_fin
        # Intentar enriquecer con Ollama
        analisis = _analizar_con_ollama(conv.titulo, datos.contenido)
        if analisis:
            if analisis.get("plazo_fin"):
                conv.plazo_fin = analisis["plazo_fin"]
            if analisis.get("requisitos"):
                conv.requisitos = analisis["requisitos"]
            if analisis.get("resumen") and not conv.descripcion:
                conv.descripcion = analisis["resumen"]
        if actualizar(conv):
            actualizadas += 1
        time.sleep(2)  # Pausa entre peticiones para no saturar
    return actualizadas


def main() -> None:
    intervalo_seg = INTERVALO_HORAS * 3600
    print(f"Worker iniciado. Scraping cada {INTERVALO_HORAS}h. Ctrl+C para detener.")
    while True:
        try:
            n = _ejecutar_ciclo()
            print(f"Ciclo completado. Actualizadas: {n}")
        except KeyboardInterrupt:
            print("\nWorker detenido.")
            sys.exit(0)
        except Exception as e:
            print(f"Error en ciclo: {e}")
        time.sleep(intervalo_seg)


if __name__ == "__main__":
    main()
