"""
Pipeline especializado para investigar convocatorias (fase HTML).
Prepara una interfaz estable para incorporar extracción PDF en una fase posterior.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import requests
from bs4 import BeautifulSoup

import config
from src.buscar_investigacion import buscar_fuentes
from src.scraper import extraer

TIMEOUT = 20
DOMINIOS_PRIORIZADOS = ("cultura.gob.es", "boe.es", "infosubvenciones.es")


@dataclass
class EjemploFinanciado:
    titulo_proyecto: str
    entidad: str
    anio: str
    fuente_url: str
    evidencia: str = "html"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _es_dominio_prioritario(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host.endswith(d) for d in DOMINIOS_PRIORIZADOS)


def _fetch(url: str) -> tuple[str, BeautifulSoup] | tuple[None, None]:
    try:
        r = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": "ConvocAUTOrias/1.0 (investigacion-convocatoria)"},
        )
        r.raise_for_status()
    except requests.RequestException:
        return None, None
    html = r.text or ""
    return html, BeautifulSoup(html, "html.parser")


def _limpiar(s: str, max_len: int = 500) -> str:
    t = re.sub(r"\s+", " ", (s or "")).strip()
    return t[:max_len]


def resolver_convocatoria_objetivo(url: str | None, query: str | None) -> dict[str, Any]:
    if url and url.strip().startswith("http"):
        return {"url": url.strip(), "metodo": "url_directa"}

    q = (query or "").strip()
    if not q:
        return {"url": "", "metodo": "sin_objetivo"}

    resultados = buscar_fuentes(f"{q} convocatoria ayudas industrias culturales")
    if not resultados:
        return {"url": "", "metodo": "busqueda_sin_resultados"}

    candidatos = [r.get("url", "") for r in resultados if r.get("url", "").startswith("http")]
    if not candidatos:
        return {"url": "", "metodo": "busqueda_sin_url"}

    ordenados = sorted(candidatos, key=lambda u: (not _es_dominio_prioritario(u), len(u)))
    return {"url": ordenados[0], "metodo": "busqueda_web"}


def extraer_datos_clave_desde_html(url: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    advertencias: list[str] = []
    fuentes: list[dict[str, Any]] = [{"url": url, "tipo": "ficha", "oficial": _es_dominio_prioritario(url)}]
    datos = {
        "nombre": "",
        "organismo": "",
        "plazo": "",
        "presupuesto": "",
        "beneficiarios": "",
        "sectores": "",
        "enlaces": {"boe": "", "bdns": "", "resolucion_convocatoria": ""},
        "url_objetivo": url,
    }

    html, soup = _fetch(url)
    if not soup:
        advertencias.append("No se pudo descargar o parsear la ficha objetivo.")
        return datos, fuentes, advertencias

    h1 = soup.find("h1")
    datos["nombre"] = _limpiar(h1.get_text(" ", strip=True) if h1 else "")

    texto = _limpiar(soup.get_text(" ", strip=True), max_len=100000)

    m_org = re.search(r"(Ministerio de [^.]{3,120})", texto, re.I)
    if m_org:
        datos["organismo"] = _limpiar(m_org.group(1))

    m_plazo = re.search(r"(Plazo de presentaci[oó]n[^.]{0,250})", texto, re.I)
    if m_plazo:
        datos["plazo"] = _limpiar(m_plazo.group(1), 250)

    m_pres = re.search(r"(importe m[aá]ximo[^.]{0,220}\d[\d\.\, ]+\s*euros?)", texto, re.I)
    if m_pres:
        datos["presupuesto"] = _limpiar(m_pres.group(1), 260)

    m_ben = re.search(r"(Podr[aá]n ser beneficiarios[^.]{0,450})", texto, re.I)
    if m_ben:
        datos["beneficiarios"] = _limpiar(m_ben.group(1), 450)

    m_sec = re.search(r"(sectores?:[^.]{0,500})", texto, re.I)
    if m_sec:
        datos["sectores"] = _limpiar(m_sec.group(1), 500)

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        label = _limpiar(a.get_text(" ", strip=True), 200).lower()
        if not href.startswith("http"):
            continue
        if "boe.es" in href and not datos["enlaces"]["boe"]:
            datos["enlaces"]["boe"] = href
            fuentes.append({"url": href, "tipo": "boe", "oficial": True})
        if ("bdns" in href or "infosubvenciones" in href) and not datos["enlaces"]["bdns"]:
            datos["enlaces"]["bdns"] = href
            fuentes.append({"url": href, "tipo": "bdns", "oficial": True})
        if ("resoluci" in label or "convocan" in label) and not datos["enlaces"]["resolucion_convocatoria"]:
            datos["enlaces"]["resolucion_convocatoria"] = href
            fuentes.append({"url": href, "tipo": "resolucion", "oficial": _es_dominio_prioritario(href)})

    if not datos["nombre"]:
        advertencias.append("No se pudo extraer el nombre de la convocatoria.")
    return datos, _deduplicar_fuentes(fuentes), advertencias


def descubrir_ediciones_anteriores(base_url: str) -> list[dict[str, str]]:
    html, soup = _fetch(base_url)
    if not soup:
        return []
    ediciones: list[dict[str, str]] = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        text = _limpiar(a.get_text(" ", strip=True), 200)
        if not href.startswith("http"):
            continue
        m = re.search(r"(20\d{2})", href) or re.search(r"(20\d{2})", text)
        if not m:
            continue
        if "995758-" not in href and "convocatoria" not in text.lower():
            continue
        ediciones.append({"anio": m.group(1), "url_ficha": href, "estado": "detectada"})
    unicas: dict[str, dict[str, str]] = {}
    for e in ediciones:
        key = f"{e['anio']}::{e['url_ficha']}"
        unicas[key] = e
    return sorted(unicas.values(), key=lambda x: x["anio"], reverse=True)[:8]


def extraer_ejemplos_previos_html(ediciones: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str], list[dict[str, Any]]]:
    ejemplos: list[dict[str, str]] = []
    advertencias: list[str] = []
    fuentes: list[dict[str, Any]] = []

    for ed in ediciones:
        ficha = ed.get("url_ficha", "")
        anio = ed.get("anio", "")
        html, soup = _fetch(ficha)
        if not soup:
            continue
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            label = _limpiar(a.get_text(" ", strip=True), 250).lower()
            if not href.startswith("http"):
                continue
            if ("propuestos" in label or "beneficiarios" in label) and href.lower().endswith(".pdf"):
                pdf_ej = extraer_ejemplos_desde_pdf(href)
                if not pdf_ej:
                    advertencias.append(
                        f"No se extrajeron ejemplos de {anio} desde PDF (pendiente fase PDF): {href}"
                    )
                fuentes.append({"url": href, "tipo": "anexo_pdf", "oficial": _es_dominio_prioritario(href)})

            if "listado" in label and "beneficiarios" in label and not href.lower().endswith(".pdf"):
                datos = extraer(href)
                if not datos:
                    continue
                titulo = _limpiar(datos.titulo, 180) or f"Listado beneficiarios {anio}"
                ejemplos.append(
                    EjemploFinanciado(
                        titulo_proyecto=titulo,
                        entidad="",
                        anio=anio,
                        fuente_url=href,
                        evidencia="html",
                    ).to_dict()
                )
                fuentes.append({"url": href, "tipo": "beneficiarios_html", "oficial": _es_dominio_prioritario(href)})

    if not ejemplos:
        advertencias.append(
            "No se han encontrado ejemplos verificables en HTML para las ediciones detectadas."
        )
    return ejemplos[:10], advertencias, _deduplicar_fuentes(fuentes)


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


def enriquecer_detalle_ayuda_ollama(
    conv: dict[str, Any],
    texto_contexto: str,
    urls_permitidas: list[str],
) -> tuple[dict[str, str], list[str]]:
    """
    Extrae gastos financiables, cofinanciación y documentación a partir del texto oficial.
    Solo debe usar información implícita en el contexto; no inventar URLs.
    """
    advertencias: list[str] = []
    vacio = {
        "gastos_financiables": "",
        "intensidad_cofinanciacion": "",
        "documentacion_clave": "",
        "resumen_ejecutivo": "",
    }
    if not texto_contexto or len(texto_contexto.strip()) < 80:
        return vacio, ["Contexto demasiado corto para enriquecimiento Ollama."]

    try:
        import requests as req_mod
    except ImportError:
        return vacio, ["requests no disponible para Ollama."]

    lista_urls = "\n".join(f"- {u}" for u in urls_permitidas[:20])
    bloque_conv = json.dumps(
        {
            "nombre": conv.get("nombre", ""),
            "plazo": conv.get("plazo", ""),
            "presupuesto": conv.get("presupuesto", ""),
            "beneficiarios": conv.get("beneficiarios", ""),
            "sectores": conv.get("sectores", ""),
        },
        ensure_ascii=False,
    )
    prompt = f"""Eres un asistente que resume convocatorias de ayudas públicas en español.
Tienes EXTRACTO de la convocatoria (puede estar incompleto). No inventes cifras ni URLs.

Datos estructurados parciales:
{bloque_conv}

Texto de la convocatoria (fragmento):
{texto_contexto[:10000]}

Responde ÚNICAMENTE con un JSON válido con estas claves (strings; usa cadena vacía si no hay datos suficientes):
- "gastos_financiables": qué gastos o conceptos son financiables (lista en texto, viñetas con "- ")
- "intensidad_cofinanciacion": porcentajes, límites, cofinanciación obligatoria si constan
- "documentacion_clave": memoria, presupuesto, certificados, etc. que se citen
- "resumen_ejecutivo": 2-4 frases objetivas

Referencias de enlaces oficiales conocidos (solo informativo; no repitas como si fueran cuerpo del texto):
{lista_urls}
"""
    try:
        r = req_mod.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": config.OLLAMA_MODEL_CONVOCATORIA,
                "prompt": prompt,
                "stream": False,
            },
            timeout=config.TIMEOUT_OLLAMA_CONVOCATORIA,
        )
        if r.status_code != 200:
            advertencias.append("Ollama respondió con código distinto de 200.")
            return vacio, advertencias
        resp = r.json().get("response", "")
        parsed = _parse_json_ollama(resp)
        if not parsed:
            advertencias.append("Ollama no devolvió JSON válido para detalle de ayuda.")
            return vacio, advertencias
        out = {
            "gastos_financiables": str(parsed.get("gastos_financiables", "")).strip(),
            "intensidad_cofinanciacion": str(parsed.get("intensidad_cofinanciacion", "")).strip(),
            "documentacion_clave": str(parsed.get("documentacion_clave", "")).strip(),
            "resumen_ejecutivo": str(parsed.get("resumen_ejecutivo", "")).strip(),
        }
        return out, advertencias
    except Exception:
        advertencias.append("Error de red o timeout al llamar a Ollama (detalle ayuda).")
        return vacio, advertencias


def construir_investigacion_convocatoria(
    url: str,
    resultado_id: str,
    *,
    query: str = "",
) -> dict[str, Any]:
    """
    Núcleo del pipeline: datos HTML, enriquecimiento Ollama, ediciones anteriores, ejemplos, MD+JSON.
    `query` se reserva para trazabilidad en metadata (opcional).
    """
    convocatoria_actual, fuentes_1, adv_1 = extraer_datos_clave_desde_html(url)
    urls_p = [url]
    for _k, v in (convocatoria_actual.get("enlaces") or {}).items():
        if isinstance(v, str) and v.startswith("http") and v not in urls_p:
            urls_p.append(v)

    html, soup = _fetch(url)
    texto_ctx = ""
    if soup:
        texto_ctx = _limpiar(soup.get_text(" ", strip=True), max_len=12000)

    detalle, adv_det = enriquecer_detalle_ayuda_ollama(convocatoria_actual, texto_ctx, urls_p)
    adv_1 = adv_1 + adv_det

    ediciones = descubrir_ediciones_anteriores(url)
    ejemplos, adv_2, fuentes_2 = extraer_ejemplos_previos_html(ediciones)
    advertencias = adv_1 + adv_2
    fuentes = _deduplicar_fuentes(fuentes_1 + fuentes_2)

    return generar_resumen_estructurado(
        convocatoria_actual=convocatoria_actual,
        ediciones_anteriores=ediciones,
        ejemplos_financiados=ejemplos,
        advertencias=advertencias,
        fuentes=fuentes,
        resultado_id=resultado_id,
        detalle_ayuda=detalle,
        query_traza=query,
    )


def extraer_ejemplos_desde_pdf(url_pdf: str) -> list[dict[str, str]]:
    """
    Stub preparado para fase 2.
    Devuelve lista vacía de forma explícita para mantener contrato estable.
    """
    _ = url_pdf
    return []


def generar_resumen_estructurado(
    convocatoria_actual: dict[str, Any],
    ediciones_anteriores: list[dict[str, str]],
    ejemplos_financiados: list[dict[str, str]],
    advertencias: list[str],
    fuentes: list[dict[str, Any]],
    resultado_id: str,
    detalle_ayuda: dict[str, str] | None = None,
    query_traza: str = "",
) -> dict[str, Any]:
    creado_en = datetime.now().isoformat()
    detalle = detalle_ayuda or {}
    md = _render_markdown(
        convocatoria_actual=convocatoria_actual,
        ediciones_anteriores=ediciones_anteriores,
        ejemplos_financiados=ejemplos_financiados,
        advertencias=advertencias,
        fuentes=fuentes,
        detalle_ayuda=detalle,
    )
    resumen_corto = (
        detalle.get("resumen_ejecutivo")
        or convocatoria_actual.get("nombre")
        or "Investigación de convocatoria completada."
    )
    return {
        "convocatoria_actual": convocatoria_actual,
        "detalle_ayuda": detalle,
        "ediciones_anteriores": ediciones_anteriores,
        "ejemplos_financiados": ejemplos_financiados,
        "advertencias": advertencias,
        "fuentes": fuentes,
        "metadata": {
            "resultado_id": resultado_id,
            "creado_en": creado_en,
            "version_pipeline": "convocatoria-html-v2",
            "resumen_corto": _limpiar(resumen_corto, 180),
            "query_traza": (query_traza or "")[:500],
        },
        "markdown": md,
    }


def _render_markdown(
    convocatoria_actual: dict[str, Any],
    ediciones_anteriores: list[dict[str, str]],
    ejemplos_financiados: list[dict[str, str]],
    advertencias: list[str],
    fuentes: list[dict[str, Any]],
    detalle_ayuda: dict[str, str],
) -> str:
    nombre = convocatoria_actual.get("nombre") or "Convocatoria sin título"
    lines = [f"# {nombre}", ""]
    lines.append("## Resumen de la convocatoria")
    lines.append(f"- Nombre: {convocatoria_actual.get('nombre') or 'N/D'}")
    lines.append(f"- Organismo: {convocatoria_actual.get('organismo') or 'N/D'}")
    lines.append(f"- Plazo: {convocatoria_actual.get('plazo') or 'N/D'}")
    lines.append("")
    lines.append("## Datos clave")
    lines.append(f"- Presupuesto: {convocatoria_actual.get('presupuesto') or 'N/D'}")
    lines.append(f"- Beneficiarios: {convocatoria_actual.get('beneficiarios') or 'N/D'}")
    lines.append(f"- Sectores: {convocatoria_actual.get('sectores') or 'N/D'}")
    enlaces = convocatoria_actual.get("enlaces", {})
    lines.append(f"- BOE: {enlaces.get('boe') or 'N/D'}")
    lines.append(f"- BDNS: {enlaces.get('bdns') or 'N/D'}")
    lines.append(f"- Resolución: {enlaces.get('resolucion_convocatoria') or 'N/D'}")
    lines.append("")
    lines.append("## Gastos financiables y ayuda (resumen)")
    gf = (detalle_ayuda or {}).get("gastos_financiables") or ""
    ic = (detalle_ayuda or {}).get("intensidad_cofinanciacion") or ""
    dc = (detalle_ayuda or {}).get("documentacion_clave") or ""
    re = (detalle_ayuda or {}).get("resumen_ejecutivo") or ""
    if re:
        lines.append(re)
        lines.append("")
    lines.append("### Gastos financiables")
    lines.append(gf if gf else "N/D (sin datos suficientes en el extracto).")
    lines.append("")
    lines.append("### Intensidad y cofinanciación")
    lines.append(ic if ic else "N/D.")
    lines.append("")
    lines.append("### Documentación clave")
    lines.append(dc if dc else "N/D.")
    lines.append("")
    lines.append("## Ediciones anteriores")
    if ediciones_anteriores:
        for e in ediciones_anteriores:
            lines.append(f"- {e.get('anio', 'N/D')}: {e.get('url_ficha', 'N/D')}")
    else:
        lines.append("- No detectadas.")
    lines.append("")
    lines.append("## Ejemplos de proyectos financiados")
    if ejemplos_financiados:
        for ej in ejemplos_financiados:
            lines.append(
                f"- {ej.get('anio', 'N/D')} | {ej.get('titulo_proyecto', 'N/D')} | {ej.get('fuente_url', 'N/D')}"
            )
    else:
        lines.append("- No disponibles en esta fase (solo HTML).")
    lines.append("")
    lines.append("## Nivel de evidencia")
    if advertencias:
        for w in advertencias:
            lines.append(f"- Advertencia: {w}")
    else:
        lines.append("- Alto: fuentes oficiales detectadas sin advertencias.")
    lines.append("")
    lines.append("## Fuentes")
    for f in fuentes:
        tipo = f.get("tipo", "fuente")
        of = "oficial" if f.get("oficial") else "no_oficial"
        lines.append(f"- [{tipo}][{of}] {f.get('url', '')}")
    return "\n".join(lines).strip() + "\n"


def _deduplicar_fuentes(fuentes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for f in fuentes:
        u = (f.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(f)
    return out
