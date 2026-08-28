"""
Resultados de búsqueda web para investigaciones (sin Ollama).
Prioridad: SEARXNG_URL si está definido; si no, paquete ddgs (antes duckduckgo-search).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import requests
except ImportError:
    requests = None

DDGS: Any = None

try:
    from ddgs import DDGS as _DDGS_CLS

    DDGS = _DDGS_CLS
except ImportError:
    try:
        from duckduckgo_search import DDGS as _DDGS_CLS

        DDGS = _DDGS_CLS
    except ImportError:
        pass

BUSCADOR_DDG_DISPONIBLE = DDGS is not None


def _normalizar(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return u


def buscar_fuentes(concepto: str) -> list[dict[str, str]]:
    """
    Devuelve lista de {title, url, snippet} (como máximo INVESTIGACION_SEARCH_MAX).
    """
    q = concepto.strip()
    if not q:
        return []
    if config.SEARXNG_URL and requests:
        return _buscar_searxng(q)
    if DDGS is not None:
        return _buscar_ddg(q)
    return []


def _buscar_searxng(q: str) -> list[dict[str, str]]:
    assert requests is not None
    url = f"{config.SEARXNG_URL}/search"
    try:
        r = requests.get(
            url,
            params={"q": q, "format": "json"},
            timeout=config.TIMEOUT_BUSQUEDA_INVESTIGACION,
            headers={"User-Agent": "ConvocAUTOrias/1.0 (investigacion)"},
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    results = data.get("results") or []
    out: list[dict[str, str]] = []
    for item in results[: config.INVESTIGACION_SEARCH_MAX]:
        if not isinstance(item, dict):
            continue
        href = _normalizar(str(item.get("url") or item.get("link") or ""))
        if not href.startswith("http"):
            continue
        out.append(
            {
                "title": str(item.get("title") or "")[:300],
                "url": href,
                "snippet": str(item.get("content") or item.get("snippet") or "")[:800],
            }
        )
    return out


def _iter_ddg_results(ddgs: Any, q: str) -> Any:
    gen = ddgs.text(q, max_results=config.INVESTIGACION_SEARCH_MAX)
    if gen is None:
        return
    if hasattr(gen, "__iter__") and not isinstance(gen, (str, bytes, dict)):
        yield from gen
        return
    yield gen


def _buscar_ddg(q: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        with DDGS() as ddgs:
            for item in _iter_ddg_results(ddgs, q):
                if not isinstance(item, dict):
                    continue
                href = _normalizar(str(item.get("href") or item.get("url") or ""))
                if not href.startswith("http"):
                    continue
                snippet = item.get("body") or item.get("snippet") or item.get("content") or ""
                out.append(
                    {
                        "title": str(item.get("title") or "")[:300],
                        "url": href,
                        "snippet": str(snippet)[:800],
                    }
                )
                if len(out) >= config.INVESTIGACION_SEARCH_MAX:
                    break
    except Exception:
        return []
    return out


def fuentes_a_texto(fuentes: list[dict[str, str]]) -> str:
    lineas: list[str] = []
    for i, f in enumerate(fuentes, 1):
        lineas.append(
            f"[{i}] {f.get('title', '')}\nURL: {f.get('url', '')}\nResumen: {f.get('snippet', '')}"
        )
    return "\n\n".join(lineas)
