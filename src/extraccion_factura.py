"""
Texto desde PDF/imagen y extracción estructurada vía Ollama (JSON).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from io import BytesIO
from typing import Any

import config

try:
    import requests
except ImportError:
    requests = None


def texto_desde_pdf(contenido: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(BytesIO(contenido))
        partes: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                partes.append(t)
        return "\n".join(partes).strip()
    except Exception:
        return ""


def texto_desde_imagen(contenido: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        im = Image.open(BytesIO(contenido))
        return pytesseract.image_to_string(im, lang="spa+eng") or ""
    except Exception:
        return ""


def _parse_json_ollama(texto: str) -> dict[str, Any] | None:
    texto = (texto or "").strip()
    i = texto.find("{")
    j = texto.rfind("}") + 1
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(texto[i:j])
    except json.JSONDecodeError:
        return None


def extraer_campos_desde_texto(texto_plano: str) -> dict[str, str]:
    """
    Devuelve claves: numero_factura, fecha_factura (YYYY-MM-DD), nombre_proveedor,
    cif_proveedor, direccion_proveedor, base_imponible, iva, total (strings, pueden vacías).
    """
    vacio = {
        "numero_factura": "",
        "fecha_factura": "",
        "nombre_proveedor": "",
        "cif_proveedor": "",
        "direccion_proveedor": "",
        "base_imponible": "",
        "iva": "",
        "total": "",
    }
    if not (texto_plano or "").strip():
        return vacio
    if not requests:
        return vacio
    prompt = f"""Eres un extractor de datos de facturas españolas. Del texto siguiente extrae campos y responde ÚNICAMENTE con un JSON válido (sin markdown).

Claves obligatorias (string, vacío si no consta):
- "numero_factura"
- "fecha_factura" en formato YYYY-MM-DD si hay fecha clara; si no, ""
- "nombre_proveedor"
- "cif_proveedor" o NIF
- "direccion_proveedor" (una línea o breve)
- "base_imponible" (solo número con punto decimal si aplica)
- "iva"
- "total"

Texto de la factura:
\"\"\"
{texto_plano[:14000]}
\"\"\"
"""
    try:
        r = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )
        if r.status_code != 200:
            return vacio
        resp = r.json().get("response", "")
        data = _parse_json_ollama(resp)
        if not isinstance(data, dict):
            return vacio
        out = vacio.copy()
        for k in out:
            v = data.get(k)
            out[k] = "" if v is None else str(v).strip()
        return out
    except Exception:
        return vacio


def normalizar_fecha_iso(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            chunk = s[:10] if len(s) >= 10 else s
            d = datetime.strptime(chunk, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def trimestre_desde_fecha(y: int, m: int) -> str:
    return f"T{(m - 1) // 3 + 1}"
