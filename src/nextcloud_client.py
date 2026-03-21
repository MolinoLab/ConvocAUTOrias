"""
Cliente WebDAV para subir borradores a Nextcloud.
"""
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    requests = None


def _url_webdav(ruta: str) -> str:
    base = config.NEXTCLOUD_URL.rstrip("/")
    path = f"/remote.php/dav/files/{config.NEXTCLOUD_USER}/{config.NEXTCLOUD_CARPETA}/{ruta}"
    return base + path


def _url_webdav_ideas(ruta_relativa: str) -> str:
    base = config.NEXTCLOUD_URL.rstrip("/")
    path = (
        f"/remote.php/dav/files/{config.NEXTCLOUD_USER}/"
        f"{config.NEXTCLOUD_IDEAS_PATH}/{ruta_relativa.strip('/')}"
    )
    return base + path


def _url_webdav_ideas_carpeta() -> str:
    base = config.NEXTCLOUD_URL.rstrip("/")
    path = f"/remote.php/dav/files/{config.NEXTCLOUD_USER}/{config.NEXTCLOUD_IDEAS_PATH}"
    return base + path


def _auth():
    return HTTPBasicAuth(config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD)


def _mkcol(url: str) -> bool:
    try:
        r = requests.request("MKCOL", url, auth=_auth(), timeout=10)
        return r.status_code in (200, 201, 204, 405)
    except Exception:
        return False


def _split_path_parts(path: str) -> Iterable[str]:
    return [p for p in path.strip("/").split("/") if p]


def subir_borrador(nombre_archivo: str, contenido: str) -> bool:
    """
    Sube un borrador (texto) a la carpeta Convocatorias en Nextcloud.
    nombre_archivo: ej. "propuesta_ibermemoria.md"
    """
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        return False
    if not requests:
        return False
    try:
        url = _url_webdav(nombre_archivo)
        r = requests.put(url, data=contenido.encode("utf-8"), auth=_auth(), timeout=30)
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def asegurar_carpeta() -> bool:
    """Crea la carpeta Convocatorias si no existe."""
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        return False
    if not requests:
        return False
    try:
        base = config.NEXTCLOUD_URL.rstrip("/")
        path = f"/remote.php/dav/files/{config.NEXTCLOUD_USER}/{config.NEXTCLOUD_CARPETA}"
        url = base + path
        return _mkcol(url)
    except Exception:
        return False


def asegurar_carpeta_ideas() -> bool:
    """Crea la ruta de ideas en Nextcloud si no existe."""
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        return False
    if not requests:
        return False
    try:
        base_url = f"{config.NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/files/{config.NEXTCLOUD_USER}"
        current = base_url
        for part in _split_path_parts(config.NEXTCLOUD_IDEAS_PATH):
            current = f"{current}/{part}"
            if not _mkcol(current):
                return False
        return True
    except Exception:
        return False


def subir_archivo_ideas(nombre_archivo: str, contenido: bytes) -> bool:
    """Sube un archivo binario a la ruta de ideas en Nextcloud."""
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        return False
    if not requests:
        return False
    try:
        if not asegurar_carpeta_ideas():
            return False
        url = _url_webdav_ideas(nombre_archivo)
        r = requests.put(url, data=contenido, auth=_auth(), timeout=30)
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def subir_idea(nombre_archivo: str, contenido: str) -> bool:
    """Sube una idea markdown/texto a la carpeta de ideas."""
    return subir_archivo_ideas(nombre_archivo, contenido.encode("utf-8"))


def _url_webdav_facturas(ruta_relativa: str) -> str:
    base = config.NEXTCLOUD_URL.rstrip("/")
    path = (
        f"/remote.php/dav/files/{config.NEXTCLOUD_USER}/"
        f"{config.NEXTCLOUD_FACTURAS_PATH}/{ruta_relativa.strip('/')}"
    )
    return base + path


def asegurar_directorios_facturas(rel_dir: str) -> bool:
    """
    Crea NEXTCLOUD_FACTURAS_PATH y rel_dir (sin nombre de archivo).
    rel_dir ej. 2026/Gastos/T1
    """
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        return False
    if not requests:
        return False
    try:
        base_url = f"{config.NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/files/{config.NEXTCLOUD_USER}"
        partes = list(_split_path_parts(config.NEXTCLOUD_FACTURAS_PATH)) + list(
            _split_path_parts(rel_dir)
        )
        current = base_url
        for part in partes:
            current = f"{current}/{part}"
            if not _mkcol(current):
                return False
        return True
    except Exception:
        return False


def subir_archivo_facturas(ruta_relativa_completa: str, contenido: bytes) -> bool:
    """
    ruta_relativa_completa: p.ej. 2026/Gastos/T1/factura.pdf (bajo NEXTCLOUD_FACTURAS_PATH).
    """
    if not all([config.NEXTCLOUD_URL, config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD]):
        return False
    if not requests:
        return False
    ruta = ruta.strip().lstrip("/")
    if not ruta:
        return False
    segmentos = [p for p in ruta.split("/") if p]
    if not segmentos:
        return False
    rel_dir = "/".join(segmentos[:-1])
    try:
        if not asegurar_directorios_facturas(rel_dir):
            return False
        url = _url_webdav_facturas(ruta)
        r = requests.put(url, data=contenido, auth=_auth(), timeout=60)
        return r.status_code in (200, 201, 204)
    except Exception:
        return False
