"""
Sincroniza datos locales al vault en Nextcloud (WebDAV bajo NEXTCLOUD_VAULT_BASE):
- CSV en .../Datos/
- Ideas: .../Ideas/
- Proyectos: .../Proyectos/
- Investigaciones: .../Investigaciones/
- Memorias: .../Memorias/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.nextcloud_client import subir_archivo_bajo_raiz, subir_archivo_ideas


def _subir_csv_si_existe(path_local: Path, nombre_remoto: str) -> bool:
    if not path_local.exists() or not path_local.is_file():
        return False
    try:
        return subir_archivo_bajo_raiz(
            config.NEXTCLOUD_DATOS_CSV_PATH,
            nombre_remoto,
            path_local.read_bytes(),
        )
    except Exception:
        return False


def _subir_md_carpeta(carpeta: Path, path_raiz_nc: str) -> tuple[int, int]:
    total, subidas = 0, 0
    if not carpeta.exists():
        return 0, 0
    for archivo in sorted(carpeta.glob("*")):
        if not archivo.is_file():
            continue
        if archivo.suffix.lower() not in {".md", ".txt"}:
            continue
        total += 1
        try:
            if subir_archivo_bajo_raiz(
                path_raiz_nc, archivo.name, archivo.read_bytes()
            ):
                subidas += 1
        except Exception:
            pass
    return total, subidas


def sync_nextcloud_datos() -> dict:
    resultados: dict[str, bool] = {}

    resultados["convocatorias_csv"] = _subir_csv_si_existe(
        config.CSV_CONVOCATORIAS,
        "convocatorias.csv",
    )
    resultados["ideas_csv"] = _subir_csv_si_existe(
        config.CSV_IDEAS,
        "ideas.csv",
    )
    if config.CSV_ENLACES.exists():
        resultados["enlaces_csv"] = _subir_csv_si_existe(
            config.CSV_ENLACES,
            "enlaces.csv",
        )
    if config.CSV_PROYECTOS.exists():
        resultados["proyectos_csv"] = _subir_csv_si_existe(
            config.CSV_PROYECTOS,
            "proyectos.csv",
        )
    if config.CSV_INVESTIGACIONES.exists():
        resultados["investigaciones_csv"] = _subir_csv_si_existe(
            config.CSV_INVESTIGACIONES,
            "investigaciones.csv",
        )
    if config.CSV_MEMORIAS.exists():
        resultados["memorias_csv"] = _subir_csv_si_existe(
            config.CSV_MEMORIAS,
            "memorias.csv",
        )
    if config.CSV_FABRICA.exists():
        resultados["fabrica_csv"] = _subir_csv_si_existe(
            config.CSV_FABRICA,
            "fabrica.csv",
        )

    ideas_total, ideas_subidas = 0, 0
    if config.CARPETA_IDEAS.exists():
        for archivo in sorted(config.CARPETA_IDEAS.glob("*")):
            if not archivo.is_file():
                continue
            if archivo.suffix.lower() not in {".md", ".txt"}:
                continue
            ideas_total += 1
            try:
                if subir_archivo_ideas(archivo.name, archivo.read_bytes()):
                    ideas_subidas += 1
            except Exception:
                pass

    proy_total, proy_subidas = _subir_md_carpeta(
        config.CARPETA_PROYECTOS, config.NEXTCLOUD_PROYECTOS_PATH
    )
    inv_total, inv_subidas = _subir_md_carpeta(
        config.CARPETA_INVESTIGACIONES, config.NEXTCLOUD_INVESTIGACIONES_PATH
    )
    mem_total, mem_subidas = _subir_md_carpeta(
        config.CARPETA_MEMORIAS, config.NEXTCLOUD_MEMORIAS_PATH
    )

    todos_bool = list(resultados.values())
    return {
        "ok": all(todos_bool) if todos_bool else False,
        "resultados": resultados,
        "ideas_total": ideas_total,
        "ideas_subidas": ideas_subidas,
        "proyectos_total": proy_total,
        "proyectos_subidas": proy_subidas,
        "investigaciones_total": inv_total,
        "investigaciones_subidas": inv_subidas,
        "memorias_total": mem_total,
        "memorias_subidas": mem_subidas,
    }


def main() -> None:
    resultado = sync_nextcloud_datos()
    print(resultado)


if __name__ == "__main__":
    main()
