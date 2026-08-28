"""
Sincroniza CSV al vault en Nextcloud (WebDAV bajo NEXTCLOUD_DATOS_CSV_PATH).
Los .md/.txt de ideas, proyectos, investigaciones y memorias van a Nextcloud Notes (API), no al vault.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.nextcloud_client import subir_archivo_bajo_raiz
from src.notes_sync_markdown import sincronizar_markdown_a_nextcloud_notes


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
    resultados["contabilidad_csv"] = _subir_csv_si_existe(
        config.CSV_CONTABILIDAD,
        "contabilidad.csv",
    )

    notas_md = sincronizar_markdown_a_nextcloud_notes()

    todos_bool = list(resultados.values())
    return {
        "ok": all(todos_bool) if todos_bool else False,
        "resultados": resultados,
        "notes_md_sync": notas_md,
    }


def main() -> None:
    resultado = sync_nextcloud_datos()
    print(resultado)


if __name__ == "__main__":
    main()
