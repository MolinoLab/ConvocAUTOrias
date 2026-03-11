"""
Adapta ideas desde archivos .txt a borradores de proyecto para formularios.
Modo plantilla (por defecto) o Ollama si está disponible.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


def _cargar_ideas() -> str:
    """Concatena el contenido de todos los .txt en ideas/."""
    if not config.CARPETA_IDEAS.exists():
        return ""
    textos = []
    for f in sorted(config.CARPETA_IDEAS.glob("*.txt")):
        try:
            textos.append(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n\n---\n\n".join(textos)


def _plantilla(convocatoria_titulo: str, convocatoria_descripcion: str, ideas: str) -> str:
    """Genera un borrador con placeholders."""
    return f"""# Borrador para: {convocatoria_titulo}

## Contexto de la convocatoria
{convocatoria_descripcion[:500] if convocatoria_descripcion else "[Sin descripción]"}

## Ideas del proyecto (desde ideas/)
{ideas[:1000] if ideas else "[Añade archivos .txt en la carpeta ideas/]"}

## Campos a rellenar
- **Título del proyecto**: [PLACEHOLDER]
- **Resumen**: [PLACEHOLDER]
- **Objetivos**: [PLACEHOLDER]
- **Metodología**: [PLACEHOLDER]
- **Presupuesto estimado**: [PLACEHOLDER]
- **Cronograma**: [PLACEHOLDER]
"""


def _generar_con_ollama(convocatoria_titulo: str, convocatoria_descripcion: str, ideas: str) -> str | None:
    """Intenta generar con Ollama. Retorna None si falla."""
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": f"""Adapta las siguientes ideas a una propuesta para la convocatoria "{convocatoria_titulo}".

Descripción de la convocatoria:
{convocatoria_descripcion[:800]}

Ideas del proyecto:
{ideas[:1500]}

Genera un borrador estructurado con: título, resumen, objetivos, metodología y cronograma.""",
                "stream": False,
            },
            timeout=60,
        )
        if r.status_code == 200:
            return r.json().get("response", "")
    except Exception:
        pass
    return None


def adaptar(convocatoria_titulo: str, convocatoria_descripcion: str, usar_ollama: bool = True) -> str:
    """
    Genera un borrador de proyecto adaptado a la convocatoria.
    Si usar_ollama=True y Ollama está disponible, usa el modelo. Si no, usa plantilla.
    """
    ideas = _cargar_ideas()
    if usar_ollama:
        resultado = _generar_con_ollama(convocatoria_titulo, convocatoria_descripcion, ideas)
        if resultado:
            return f"# Borrador para: {convocatoria_titulo}\n\n{resultado}"
    return _plantilla(convocatoria_titulo, convocatoria_descripcion, ideas)


def adaptar_y_subir(convocatoria_titulo: str, convocatoria_descripcion: str, id_conv: str = "") -> tuple[str, bool]:
    """
    Genera borrador y lo sube a Nextcloud (carpeta Convocatorias).
    Retorna (contenido, exito_upload).
    """
    contenido = adaptar(convocatoria_titulo, convocatoria_descripcion)
    # Nombre de archivo seguro
    nombre = "".join(c if c.isalnum() or c in " -_" else "_" for c in convocatoria_titulo[:50])
    nombre = f"borrador_{id_conv or nombre}.md"
    try:
        from .nextcloud_client import asegurar_carpeta, subir_borrador
        asegurar_carpeta()
        ok = subir_borrador(nombre, contenido)
        return contenido, ok
    except Exception:
        return contenido, False
