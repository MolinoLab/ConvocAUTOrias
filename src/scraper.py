"""
Extracción de datos de URLs de convocatorias.
Usa requests + BeautifulSoup para HTML estático y trafilatura para contenido principal.
"""
import re
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup
import trafilatura

USER_AGENT = "ConvocAUTOrias/1.0 (monitor convocatorias artisticas; +https://github.com/molinolab)"
TIMEOUT = 15


@dataclass
class DatosExtraidos:
    """Datos extraídos de una página de convocatoria."""
    titulo: str
    descripcion: str
    plazo_fin: str
    contenido: str
    url: str


def _extraer_titulo(soup: BeautifulSoup, url: str) -> str:
    """Extrae el título: h1, luego title."""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    title = soup.find("title")
    if title and title.get_text(strip=True):
        return title.get_text(strip=True)
    return url.split("/")[-1] or url


def _extraer_fechas(texto: str) -> str:
    """
    Busca patrones de fecha en el texto.
    Patrones: DD/MM/YYYY, DD-MM-YYYY, DD de mes YYYY, "plazo hasta", "fecha límite", etc.
    """
    if not texto:
        return ""

    # DD/MM/YYYY o DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b", texto)
    if m:
        return m.group(0)

    # DD de mes YYYY (español)
    meses = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre"
    m = re.search(rf"\b(\d{{1,2}})\s+de\s+({meses})\s+de?\s*(\d{{2,4}})\b", texto, re.I)
    if m:
        return m.group(0)

    # "plazo hasta", "fecha límite", "hasta el"
    m = re.search(
        r"(?:plazo\s+hasta|fecha\s+l[ií]mite|hasta\s+el)\s*[:\s]*([^.\n]{10,60})",
        texto,
        re.I,
    )
    if m:
        return m.group(1).strip()

    return ""


def _extraer_contenido_principal(html: str, url: str) -> str:
    """Usa trafilatura para extraer el contenido principal del artículo."""
    try:
        contenido = trafilatura.extract(html, url=url, include_comments=False)
        if contenido and len(contenido.strip()) > 100:
            return contenido.strip()
    except Exception:
        pass
    return ""


def _extraer_parrafos(soup: BeautifulSoup, max_chars: int = 2000) -> str:
    """Extrae párrafos principales como fallback."""
    parrafos = []
    total = 0
    for p in soup.find_all("p"):
        t = p.get_text(strip=True)
        if t and len(t) > 30:
            parrafos.append(t)
            total += len(t)
            if total >= max_chars:
                break
    return " ".join(parrafos)[:max_chars] if parrafos else ""


def extraer(url: str) -> DatosExtraidos | None:
    """
    Extrae título, descripción, fechas y contenido de una URL.
    Retorna None si la petición falla.
    """
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        return None

    soup = BeautifulSoup(html, "html.parser")
    titulo = _extraer_titulo(soup, url)
    contenido_traf = _extraer_contenido_principal(html, url)
    contenido = contenido_traf or _extraer_parrafos(soup)
    plazo_fin = _extraer_fechas(contenido) or _extraer_fechas(html)
    descripcion = (contenido[:500] + "...") if len(contenido) > 500 else contenido

    return DatosExtraidos(
        titulo=titulo,
        descripcion=descripcion,
        plazo_fin=plazo_fin,
        contenido=contenido,
        url=url,
    )
