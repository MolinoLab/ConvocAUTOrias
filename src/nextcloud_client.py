"""
Cliente WebDAV para subir borradores a Nextcloud.
"""
import sys
from pathlib import Path

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
        auth = HTTPBasicAuth(config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD)
        r = requests.put(url, data=contenido.encode("utf-8"), auth=auth, timeout=30)
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
        auth = HTTPBasicAuth(config.NEXTCLOUD_USER, config.NEXTCLOUD_PASSWORD)
        r = requests.request("MKCOL", url, auth=auth, timeout=10)
        return r.status_code in (200, 201, 204, 405)  # 405 = ya existe
    except Exception:
        return False
