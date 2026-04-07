"""
Descarga de audio/video con yt-dlp (URL o búsqueda ytsearch1:).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import config


def _comando_yt_dlp() -> list[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    return [sys.executable, "-m", "yt_dlp"]


def _mensaje_dependencia_yt_dlp() -> str:
    return (
        "yt-dlp no disponible en este runtime. "
        "Instala dependencias en el mismo Python que ejecuta el bot "
        "(pip install -r requirements.txt) o usa una imagen Docker actualizada."
    )


def _mensaje_youtube_bloqueado() -> str:
    return (
        "YouTube está pidiendo validación anti-bot.\n"
        "Configura cookies exportadas en .env con DESCARGA_YTDLP_COOKIES_FILE y reintenta.\n"
        "Ejemplo: DESCARGA_YTDLP_COOKIES_FILE=/app/data/youtube_cookies.txt"
    )


def _mensaje_js_runtime() -> str:
    return (
        "yt-dlp avisa que falta runtime JavaScript para YouTube.\n"
        "Instala Node/Deno y define DESCARGA_YTDLP_JS_RUNTIMES (ej. node)."
    )


def _aplicar_flags_youtube(cmd: list[str]) -> list[str]:
    out = list(cmd)
    cookies_file = (config.DESCARGA_YTDLP_COOKIES_FILE or "").strip()
    if cookies_file:
        out.extend(["--cookies", cookies_file])
    js_runtimes = (config.DESCARGA_YTDLP_JS_RUNTIMES or "").strip()
    if js_runtimes:
        out.extend(["--js-runtimes", js_runtimes])
    return out


def normalizar_entrada_descarga(texto: str) -> str:
    s = (texto or "").strip()
    if not s:
        return ""
    if s.lower().startswith("http://") or s.lower().startswith("https://"):
        u = urlparse(s)
        if u.scheme not in ("http", "https") or not u.netloc:
            return ""
        return s
    return f"ytsearch1:{s}"


def ejecutar_descarga(query_completa: str) -> tuple[bool, str, str | None]:
    """
    Devuelve (ok, mensaje, ruta_absoluta del fichero descargado o None).
    """
    q = normalizar_entrada_descarga(query_completa)
    if not q:
        return False, "Indica una URL http(s) o un texto para buscar en YouTube.", None

    config.DESCARGAS_DIR.mkdir(parents=True, exist_ok=True)
    plantilla = str(config.DESCARGAS_DIR / "%(title).200B [%(id)s].%(ext)s")
    cmd_base = _comando_yt_dlp()
    cmd = cmd_base + [
        "-o",
        plantilla,
        "--no-playlist",
        "--restrict-filenames",
        f"--max-filesize={config.DESCARGAS_MAX_MB}M",
        q,
    ]
    cmd = _aplicar_flags_youtube(cmd)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.DESCARGAS_TIMEOUT_SEC,
            cwd=str(config.DESCARGAS_DIR),
        )
    except subprocess.TimeoutExpired:
        return False, f"Tiempo agotado ({config.DESCARGAS_TIMEOUT_SEC}s).", None
    except FileNotFoundError:
        return False, _mensaje_dependencia_yt_dlp(), None
    except Exception as exc:
        return False, str(exc)[:500], None

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Error desconocido").strip()[:800]
        if "No module named yt_dlp" in err:
            return False, _mensaje_dependencia_yt_dlp(), None
        err_low = err.lower()
        if "sign in to confirm you’re not a bot" in err_low or "sign in to confirm you're not a bot" in err_low:
            return False, f"{_mensaje_youtube_bloqueado()}\n\nDetalle:\n{err}", None
        if "no supported javascript runtime could be found" in err_low:
            return False, f"{_mensaje_js_runtime()}\n\nDetalle:\n{err}", None
        if cmd_base[:2] == [sys.executable, "-m"]:
            err = f"(Ejecutado con {sys.executable} -m yt_dlp)\n{err}"
        return False, err, None

    reciente = _archivo_mas_reciente(config.DESCARGAS_DIR)
    if reciente and reciente.is_file():
        return True, "Descarga completada.", str(reciente.resolve())
    return False, "yt-dlp terminó sin error pero no se detectó el fichero.", None


def _archivo_mas_reciente(carpeta: Path) -> Path | None:
    if not carpeta.is_dir():
        return None
    archivos = [p for p in carpeta.iterdir() if p.is_file()]
    if not archivos:
        return None
    return max(archivos, key=lambda p: p.stat().st_mtime)
