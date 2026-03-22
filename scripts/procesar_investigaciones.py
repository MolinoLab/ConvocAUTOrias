"""
Procesa filas pendientes de data/investigaciones.csv: búsqueda web, Ollama, .md y Telegram.
Uso: python -m scripts.procesar_investigaciones --once
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.buscar_investigacion import DDGS, buscar_fuentes, fuentes_a_texto
from src.db_investigaciones import Investigacion, actualizar, listar
from src.notifier import enviar_mensaje
from src.scraper import extraer

try:
    import requests
except ImportError:
    requests = None


def _modelo_investigacion() -> str:
    return config.OLLAMA_MODEL_INVESTIGACION


def _parse_json_ollama(texto: str) -> dict | None:
    texto = (texto or "").strip()
    i = texto.find("{")
    j = texto.rfind("}") + 1
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(texto[i:j])
    except json.JSONDecodeError:
        return None


def _llamada_ollama(concepto: str, contexto_fuentes: str, urls_permitidas: list[str]) -> dict | None:
    if not requests:
        return None
    lista_urls = "\n".join(f"- {u}" for u in urls_permitidas)
    prompt = f"""Eres un asistente de investigación. Tienes resultados de búsqueda web sobre el concepto (español).

Concepto: {concepto[:500]}

Fuentes y extractos:
{contexto_fuentes[:12000]}

URLs permitidas para el campo link (debes elegir UNA exactamente de esta lista, copiada carácter a carácter):
{lista_urls}

Responde ÚNICAMENTE con un JSON válido con estas claves:
- "resumen": 2-4 frases en español
- "link": una URL exactamente igual a una de la lista permitida
- "cuerpo_markdown": informe en Markdown (secciones, listas si aplica) citando ideas de las fuentes; no inventes URLs nuevas

Ejemplo: {{"resumen": "...", "link": "https://...", "cuerpo_markdown": "## ...\\n..."}}"""
    try:
        r = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": _modelo_investigacion(),
                "prompt": prompt,
                "stream": False,
            },
            timeout=config.TIMEOUT_OLLAMA_INVESTIGACION,
        )
        if r.status_code != 200:
            return None
        resp = r.json().get("response", "")
        return _parse_json_ollama(resp)
    except Exception:
        return None


def _front_matter(inv: Investigacion, link: str) -> str:
    c = inv.concepto.replace("\n", " ").replace("\r", "").strip()
    if '"' in c:
        c = c.replace('"', "'")
    link_esc = link.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f"---\n"
        f'id: {inv.id}\n'
        f"fecha: {inv.fecha}\n"
        f'concepto: "{c}"\n'
        f'link: "{link_esc}"\n'
        f"---\n\n"
    )


def _mensaje_telegram(inv: Investigacion) -> str:
    return (
        f"Investigación: {inv.concepto}\n\n"
        f"{inv.resumen}\n\n"
        f"{inv.link}"
    )[:4000]


def _marcar_error(inv: Investigacion, mensaje: str) -> None:
    inv.estado = "error"
    inv.resumen = (mensaje or "").strip()[:2000]
    actualizar(inv)


def _notificar_y_actualizar(inv: Investigacion) -> None:
    time.sleep(config.INVESTIGACION_SLEEP_SEC)
    cid = (inv.telegram_chat_id or "").strip() or None
    if enviar_mensaje(_mensaje_telegram(inv), chat_id=cid):
        inv.estado = "enviado"
    else:
        inv.estado = "investigado"
    actualizar(inv)


def _procesar_reintento_telegram(inv: Investigacion) -> None:
    _notificar_y_actualizar(inv)


def _procesar_completo(inv: Investigacion) -> None:
    if not config.SEARXNG_URL and DDGS is None:
        print(
            "Aviso: define SEARXNG_URL en .env o instala duckduckgo-search "
            "(pip install duckduckgo-search) para obtener resultados.",
            flush=True,
        )
        _marcar_error(
            inv,
            "Sin buscador: define SEARXNG_URL o instala duckduckgo-search en el entorno.",
        )
        return

    fuentes = buscar_fuentes(inv.concepto)
    time.sleep(config.INVESTIGACION_SLEEP_SEC)

    if not fuentes:
        print(f"Sin fuentes para id={inv.id} concepto={inv.concepto!r}", flush=True)
        _marcar_error(inv, "Sin resultados de busqueda web para este concepto.")
        return

    urls = [f["url"] for f in fuentes if f.get("url")]
    if not urls:
        _marcar_error(inv, "La busqueda no devolvio URLs utilizables.")
        return

    bloque = fuentes_a_texto(fuentes)
    permitidas = list(dict.fromkeys(urls))

    for idx, url in enumerate(permitidas[: config.INVESTIGACION_FETCH_TOP]):
        if idx > 0:
            time.sleep(config.INVESTIGACION_SLEEP_SEC)
        datos = extraer(url)
        if datos and datos.contenido:
            cap = max(
                800,
                config.INVESTIGACION_FETCH_MAX_CHARS
                // max(1, config.INVESTIGACION_FETCH_TOP),
            )
            chunk = datos.contenido[:cap]
            bloque += f"\n\n--- Ampliación de {url} ---\n{chunk}"

    time.sleep(config.INVESTIGACION_SLEEP_SEC)
    parsed = _llamada_ollama(inv.concepto, bloque, permitidas)
    if not parsed:
        print(f"Ollama no devolvió JSON util id={inv.id}", flush=True)
        _marcar_error(
            inv,
            "Ollama no devolvio JSON valido (revisa modelo y TIMEOUT_OLLAMA_INVESTIGACION).",
        )
        return

    resumen = str(parsed.get("resumen", "")).strip()
    link = str(parsed.get("link", "")).strip()
    cuerpo = str(parsed.get("cuerpo_markdown", "")).strip()

    permitidas_set = set(permitidas)
    if link not in permitidas_set:
        link = permitidas[0]

    if not resumen and cuerpo:
        resumen = cuerpo[:500] + ("..." if len(cuerpo) > 500 else "")
    if not cuerpo:
        cuerpo = resumen or "(Sin cuerpo)"

    nombre_md = (inv.archivo or "").strip() or f"{inv.id}.md"
    path_md = config.CARPETA_INVESTIGACIONES / nombre_md
    path_md.write_text(_front_matter(inv, link) + cuerpo, encoding="utf-8")

    inv.resumen = resumen[:2000]
    inv.link = link
    inv.estado = "investigado"
    actualizar(inv)

    _notificar_y_actualizar(inv)


def _cola_trabajo(items: list[Investigacion]) -> list[tuple[str, Investigacion]]:
    cola: list[tuple[str, Investigacion]] = []
    for x in items:
        if (
            x.estado == "investigado"
            and x.resumen.strip()
            and x.link.strip()
        ):
            cola.append(("retry", x))
    for x in items:
        if x.estado == "pendiente":
            cola.append(("full", x))
    return cola


def ejecutar_ciclo() -> None:
    items = listar()
    cola = _cola_trabajo(items)
    hechos = 0
    for tipo, inv in cola:
        if hechos >= config.MAX_INVESTIGACIONES_POR_CICLO:
            break
        if tipo == "retry":
            _procesar_reintento_telegram(inv)
        else:
            _procesar_completo(inv)
        hechos += 1
        if hechos < config.MAX_INVESTIGACIONES_POR_CICLO:
            time.sleep(config.INVESTIGACION_SLEEP_SEC)


def main() -> int:
    p = argparse.ArgumentParser(description="Procesar investigaciones pendientes")
    p.add_argument("--once", action="store_true", help="Un ciclo y salir")
    args = p.parse_args()
    if not args.once:
        print("Usa --once (invocado desde la API / n8n).", flush=True)
        return 2
    ejecutar_ciclo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
