"""
API mínima para que n8n y OpenClaw invoquen las tareas del proyecto vía HTTP.
Endpoints: POST /scrape, POST /revisar, POST /notificar-agenda-manana, POST /notificar-agenda-semana,
           POST /sync-caldav, POST /indexar-ideas, POST /sync-nextcloud-datos, POST /generar-borrador,
           POST /procesar-investigaciones, POST /investigar-convocatoria,
           GET /funcionalidad, POST /funcionalidad
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field

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
    err = (result.stderr or "").strip()
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "stderr_trail": err[-2000:] if err else "",
        "success": result.returncode == 0,
    }


def _parse_json_stdout(stdout: str) -> dict | None:
    lines = [x.strip() for x in (stdout or "").splitlines() if x.strip()]
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


@app.post("/scrape")
def scrape():
    """Ejecuta un ciclo del worker de investigación profunda de convocatorias (--once)."""
    return _run_script("scripts.worker_scraper", "--once")


@app.post("/procesar-investigaciones")
def procesar_investigaciones():
    """Procesa investigaciones pendientes (búsqueda + Ollama + Telegram)."""
    return _run_script("scripts.procesar_investigaciones", "--once")


class InvestigarConvocatoriaRequest(BaseModel):
    url: Optional[str] = ""
    query: Optional[str] = ""
    modo: Optional[str] = "manual"
    chat_id: Optional[str] = ""


@app.post("/investigar-convocatoria")
def investigar_convocatoria(req: InvestigarConvocatoriaRequest):
    """Investiga una convocatoria y genera resumen estructurado (MD+JSON)."""
    args: list[str] = []
    if (req.url or "").strip():
        args.extend(["--url", (req.url or "").strip()])
    if (req.query or "").strip():
        args.extend(["--query", (req.query or "").strip()])
    if (req.chat_id or "").strip():
        args.extend(["--chat-id", (req.chat_id or "").strip()])

    result = _run_script("scripts.procesar_convocatoria", *args)
    parsed = _parse_json_stdout(result.get("stdout", ""))
    if parsed is None:
        return {
            "success": False,
            "error": "No se pudo parsear la salida del script.",
            "modo": req.modo or "manual",
            "raw": result,
        }
    parsed["modo"] = req.modo or "manual"
    parsed["success"] = bool(parsed.get("success"))
    if not parsed["success"]:
        parsed["stderr_trail"] = result.get("stderr_trail", "")
    return parsed


@app.post("/revisar")
def revisar():
    """Revisa plazos y envía notificaciones por Telegram."""
    return _run_script("scripts.revisar_convocatorias")


@app.post("/notificar-agenda-manana")
def notificar_agenda_manana():
    """Eventos y tareas (Deck + VTODO) para mañana (Europa/Madrid); Telegram si hay ítems."""
    return _run_script("scripts.notificar_agenda_manana")


@app.post("/notificar-agenda-semana")
def notificar_agenda_semana():
    """Resumen lunes–domingo siguiente (APP_TIMEZONE); Telegram a todos los chats configurados."""
    return _run_script("scripts.notificar_agenda_semana")


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


import hashlib
from datetime import datetime

import config
from src.db_funcionalidad import (
    Funcionalidad,
    ESTADOS_VALIDOS,
    listar as listar_func,
    añadir as añadir_func,
)
from src.tuya_client import (
    obtener_estado_enchufe,
    obtener_ultimo_error_tuya,
    poner_enchufe,
)
from src.bambulab_client import (
    apagar_impresora,
    obtener_estado_impresion,
    obtener_ultimo_error_bambu,
)


class FuncionalidadRequest(BaseModel):
    texto: str
    prioridad: int = Field(ge=1, le=5)
    estado: Optional[str] = "pendiente"


class SmartPlugRequest(BaseModel):
    on: bool
    device_id: Optional[str] = None


class BambuPowerOffRequest(BaseModel):
    confirmar: bool = False


@app.get("/funcionalidad")
def get_funcionalidad():
    """Lista todas las funcionalidades registradas."""
    items = listar_func()
    items.sort(key=lambda f: (-f.prioridad, f.estado != "pendiente"))
    return [f.to_dict() for f in items]


@app.post("/funcionalidad")
def post_funcionalidad(req: FuncionalidadRequest):
    """Crea una nueva funcionalidad."""
    estado = (req.estado or "pendiente").lower()
    if estado not in ESTADOS_VALIDOS:
        return {"success": False, "error": f"Estado invalido. Validos: {', '.join(sorted(ESTADOS_VALIDOS))}"}
    base = f"{datetime.now().isoformat()}::func::{req.texto[:500]}"
    func_id = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    func = Funcionalidad(
        id=func_id,
        texto=req.texto,
        prioridad=req.prioridad,
        estado=estado,
        fecha_ingesta=datetime.now().isoformat(),
        fuente="api",
    )
    añadir_func(func)
    return {"success": True, "funcionalidad": func.to_dict()}


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}


@app.get("/smartplug/estado")
def smartplug_estado():
    ok, msg = obtener_estado_enchufe()
    if not ok:
        return {"success": False, "error": obtener_ultimo_error_tuya() or "Error Tuya."}
    return {"success": True, "message": msg}


@app.post("/smartplug/set")
def smartplug_set(req: SmartPlugRequest):
    ok, msg = poner_enchufe(req.on, device_id=req.device_id)
    if not ok:
        return {"success": False, "error": obtener_ultimo_error_tuya() or "Error Tuya."}
    return {"success": True, "message": msg}


@app.get("/bambu/estado")
def bambu_estado():
    ok, msg = obtener_estado_impresion()
    if not ok:
        return {"success": False, "error": obtener_ultimo_error_bambu() or "Error BambuLab."}
    return {"success": True, "message": msg}


@app.post("/bambu/apagar")
def bambu_apagar(req: BambuPowerOffRequest):
    if not req.confirmar:
        return {"success": False, "error": "Debes enviar confirmar=true para apagar."}
    ok, msg = apagar_impresora()
    if not ok:
        return {"success": False, "error": obtener_ultimo_error_bambu() or "Error apagando impresora."}
    return {"success": True, "message": msg}
