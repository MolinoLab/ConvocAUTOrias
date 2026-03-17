"""
API mínima para que n8n y OpenClaw invoquen las tareas del proyecto vía HTTP.
Endpoints: POST /scrape, POST /revisar, POST /sync-caldav, POST /indexar-ideas,
           POST /sync-nextcloud-datos, POST /generar-borrador
"""
import subprocess
import sys
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel

# Asegurar que el proyecto está en el path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

app = FastAPI(title="ConvocAUTOrias API", version="1.0")


def _run_script(module: str, *args: str) -> dict:
    """Ejecuta un script del proyecto y retorna resultado."""
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "success": result.returncode == 0,
    }


@app.post("/scrape")
def scrape():
    """Ejecuta un ciclo del worker scraper (--once)."""
    return _run_script("scripts.worker_scraper", "--once")


@app.post("/revisar")
def revisar():
    """Revisa plazos y envía notificaciones por Telegram."""
    return _run_script("scripts.revisar_convocatorias")


@app.post("/sync-caldav")
def sync_caldav():
    """Sincroniza plazos con el calendario CalDAV."""
    return _run_script("scripts.sync_caldav")


@app.post("/indexar-ideas")
def indexar_ideas():
    """Indexa ideas nuevas desde data/ideas hacia data/ideas.csv."""
    return _run_script("scripts.indexar_ideas")


@app.post("/sync-nextcloud-datos")
def sync_nextcloud_datos():
    """Sube copias de ideas/convocatorias a Nextcloud."""
    return _run_script("scripts.sync_nextcloud_datos")


class GenerarBorradorRequest(BaseModel):
    id: str


@app.post("/generar-borrador")
def generar_borrador(req: GenerarBorradorRequest):
    """Genera un borrador adaptado para una convocatoria y lo sube a Nextcloud."""
    return _run_script("scripts.generar_borrador", req.id)


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}
