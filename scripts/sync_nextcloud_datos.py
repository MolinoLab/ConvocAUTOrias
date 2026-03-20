"""
Sincroniza copias de datos locales a Nextcloud:
- data/convocatorias.csv
- data/ideas.csv
- data/enlaces.csv
- data/ideas/*.md y *.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.nextcloud_client import subir_archivo_ideas


def _subir_si_existe(path_local: Path, nombre_remoto: str) -> bool:
    if not path_local.exists() or not path_local.is_file():
        return False
    try:
        return subir_archivo_ideas(nombre_remoto, path_local.read_bytes())
    except Exception:
        return False


def sync_nextcloud_datos() -> dict:
    resultados: dict[str, bool] = {}

    resultados["convocatorias_csv"] = _subir_si_existe(
        config.CSV_CONVOCATORIAS,
        "convocatorias.csv",
    )
    resultados["ideas_csv"] = _subir_si_existe(
        config.CSV_IDEAS,
        "ideas.csv",
    )
    if config.CSV_ENLACES.exists():
        resultados["enlaces_csv"] = _subir_si_existe(
            config.CSV_ENLACES,
            "enlaces.csv",
        )

    ideas_subidas = 0
    ideas_total = 0
    if config.CARPETA_IDEAS.exists():
        for archivo in sorted(config.CARPETA_IDEAS.glob("*")):
            if not archivo.is_file():
                continue
            if archivo.suffix.lower() not in {".md", ".txt"}:
                continue
            ideas_total += 1
            if _subir_si_existe(archivo, archivo.name):
                ideas_subidas += 1

    return {
        "ok": all(resultados.values()) if resultados else False,
        "resultados": resultados,
        "ideas_total": ideas_total,
        "ideas_subidas": ideas_subidas,
    }


def main() -> None:
    resultado = sync_nextcloud_datos()
    print(resultado)


if __name__ == "__main__":
    main()
