"""
Sincroniza ficheros .md/.txt de ideas, proyectos, investigaciones y memorias
hacia Nextcloud Notes (API), con mapeo estable por fichero local.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config
from src.notes_nextcloud import actualizar_nota, crear_nota


def obtener_credenciales_notes_sync() -> tuple[str, str] | None:
    u = config.NEXTCLOUD_NOTES_SYNC_NC_USER
    p = config.NEXTCLOUD_NOTES_SYNC_APP_PASSWORD
    if u and p:
        return u, p
    for row in config.NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM.values():
        nu = (row.get("nc_user") or "").strip()
        pw = (row.get("app_password") or "").strip()
        if nu and pw:
            return nu, pw
    return None


def _cargar_mapa() -> dict[str, dict]:
    p = config.NOTES_SYNC_MAP_PATH
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _guardar_mapa(m: dict[str, dict]) -> None:
    config.NOTES_SYNC_MAP_PATH.write_text(
        json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_PREFIX: dict[str, str] = {
    "ideas": "[Ideas]",
    "proyectos": "[Proyectos]",
    "investigaciones": "[Investigaciones]",
    "memorias": "[Memorias]",
}

_CARPETAS: list[tuple[str, Path]] = [
    ("ideas", config.CARPETA_IDEAS),
    ("proyectos", config.CARPETA_PROYECTOS),
    ("investigaciones", config.CARPETA_INVESTIGACIONES),
    ("memorias", config.CARPETA_MEMORIAS),
]


def sincronizar_markdown_a_nextcloud_notes() -> dict[str, int | str]:
    """
    Crea o actualiza notas en Nextcloud según ficheros locales.
    """
    creds = obtener_credenciales_notes_sync()
    if not creds:
        return {
            "ok": 0,
            "error": "Sin credenciales Notes: NEXTCLOUD_NOTES_SYNC_* o NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM",
            "creadas": 0,
            "actualizadas": 0,
            "sin_cambios": 0,
            "errores": 0,
        }
    nc_user, app_pw = creds
    mapa = _cargar_mapa()
    procesados: set[str] = set()
    creadas = actualizadas = sin_cambios = errores = 0

    for clave_carpeta, carpeta in _CARPETAS:
        pref = _PREFIX.get(clave_carpeta, f"[{clave_carpeta}]")
        if not carpeta.is_dir():
            continue
        for archivo in sorted(carpeta.glob("*")):
            if not archivo.is_file():
                continue
            if archivo.suffix.lower() not in {".md", ".txt"}:
                continue
            rel = f"{clave_carpeta}/{archivo.name}"
            procesados.add(rel)
            try:
                contenido = archivo.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errores += 1
                continue
            titulo = f"{pref} {archivo.stem}"[:400]
            entrada = mapa.get(rel) or {}
            note_id = entrada.get("note_id")
            h_actual = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
            if entrada.get("hash") == h_actual and note_id:
                sin_cambios += 1
                continue
            if note_id:
                res = actualizar_nota(
                    nc_user, app_pw, int(note_id), contenido=contenido
                )
                if res:
                    mapa[rel] = {"note_id": int(note_id), "hash": h_actual}
                    actualizadas += 1
                else:
                    errores += 1
            else:
                res = crear_nota(nc_user, app_pw, titulo, contenido)
                nid = res.get("id") if res else None
                if nid is not None:
                    mapa[rel] = {"note_id": int(nid), "hash": h_actual}
                    creadas += 1
                else:
                    errores += 1

    for clave in list(mapa.keys()):
        if clave not in procesados:
            del mapa[clave]

    _guardar_mapa(mapa)
    return {
        "ok": 1,
        "creadas": creadas,
        "actualizadas": actualizadas,
        "sin_cambios": sin_cambios,
        "errores": errores,
    }
