"""
Carga variables de entorno para el sistema de autoconvocatorias.
"""
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
DIR_PROYECTO = Path(__file__).resolve().parent
load_dotenv(DIR_PROYECTO / ".env")

# Versión del bot (mostrar en /ayuda; incrementar manualmente en cada release)
APP_VERSION = os.getenv("APP_VERSION", "0.23").strip() or "0.23"
# Zona horaria para fechas relativas y formato en /ver* (defecto España peninsular)
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Madrid").strip() or "Europe/Madrid"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# CalDAV / Nextcloud Calendar
CALDAV_URL = os.getenv("CALDAV_URL", "")
CALDAV_USER = os.getenv("CALDAV_USER", "")
CALDAV_PASS = os.getenv("CALDAV_PASS", "")
CALDAV_CALENDAR_NAME = os.getenv("CALDAV_CALENDAR_NAME", "MolinoLab").strip()
# URL completa del calendario (colección), ej. .../remote.php/dav/calendars/usuario/molinolab/
_caldav_calendar_url_raw = os.getenv("CALDAV_CALENDAR_URL", "").strip()
CALDAV_CALENDAR_URL = (
    _caldav_calendar_url_raw.rstrip("/") + "/" if _caldav_calendar_url_raw else ""
)

# Ollama (IA local)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
_ollama_inv = os.getenv("OLLAMA_MODEL_INVESTIGACION", "").strip()
OLLAMA_MODEL_INVESTIGACION = _ollama_inv if _ollama_inv else OLLAMA_MODEL

# Nextcloud WebDAV
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "").rstrip("/")
NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER", "")
NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD", "")

# Base del vault Obsidian en WebDAV: siempre bajo files/{NEXTCLOUD_USER}/...
# Si el vault real está en la cuenta de b1tdreamer, comparte esa carpeta con NEXTCLOUD_USER
# (p. ej. bot) con permiso de edición y pon aquí la ruta tal como la ve *ese* usuario en
# Archivos (no uses enlaces internos tipo /f/2343; no son rutas DAV).
NEXTCLOUD_VAULT_BASE = os.getenv(
    "NEXTCLOUD_VAULT_BASE",
    "Documents/b1tacora/b1tdreamer",
).strip().strip("/")
_vault = NEXTCLOUD_VAULT_BASE

# Cada categoría en una subcarpeta del vault (sobrescribible con .env)
NEXTCLOUD_CARPETA = os.getenv(
    "NEXTCLOUD_CARPETA",
    f"{_vault}/Convocatorias",
).strip().strip("/")
NEXTCLOUD_IDEAS_PATH = os.getenv(
    "NEXTCLOUD_IDEAS_PATH",
    f"{_vault}/Ideas",
).strip().strip("/")
NEXTCLOUD_FACTURAS_PATH = os.getenv(
    "NEXTCLOUD_FACTURAS_PATH",
    f"{_vault}/Facturas",
).strip().strip("/")
NEXTCLOUD_PROYECTOS_PATH = os.getenv(
    "NEXTCLOUD_PROYECTOS_PATH",
    f"{_vault}/Proyectos",
).strip().strip("/")
NEXTCLOUD_INVESTIGACIONES_PATH = os.getenv(
    "NEXTCLOUD_INVESTIGACIONES_PATH",
    f"{_vault}/Investigaciones",
).strip().strip("/")
NEXTCLOUD_MEMORIAS_PATH = os.getenv(
    "NEXTCLOUD_MEMORIAS_PATH",
    f"{_vault}/Memorias",
).strip().strip("/")
NEXTCLOUD_DATOS_CSV_PATH = os.getenv(
    "NEXTCLOUD_DATOS_CSV_PATH",
    f"{_vault}/Datos",
).strip().strip("/")
DECK_BOARD_NAME = os.getenv("DECK_BOARD_NAME", "MolinoLab").strip()
DECK_STACK_NAME = os.getenv("DECK_STACK_NAME", "").strip()

# JSON: {"telegram_username_sin_arroba": "nextcloud_uid", ...}
_deck_assign_raw = os.getenv("DECK_ASSIGNEE_BY_TELEGRAM_USERNAME", "").strip()
DECK_ASSIGNEE_BY_TELEGRAM_USERNAME: dict[str, str] = {}
if _deck_assign_raw:
    try:
        obj = json.loads(_deck_assign_raw)
        if isinstance(obj, dict):
            DECK_ASSIGNEE_BY_TELEGRAM_USERNAME = {
                str(k).strip().lstrip("@").lower(): str(v).strip()
                for k, v in obj.items()
                if str(k).strip() and str(v).strip()
            }
    except json.JSONDecodeError:
        pass

# JSON: {"5088114697": "nextcloud_deck_uid", ...} para usuarios sin @username en Telegram
_deck_assign_id_raw = os.getenv("DECK_ASSIGNEE_BY_TELEGRAM_ID", "").strip()
DECK_ASSIGNEE_BY_TELEGRAM_ID: dict[int, str] = {}
if _deck_assign_id_raw:
    try:
        obj_id = json.loads(_deck_assign_id_raw)
        if isinstance(obj_id, dict):
            for k, v in obj_id.items():
                ks = str(k).strip()
                vs = str(v).strip()
                if ks.isdigit() and vs:
                    DECK_ASSIGNEE_BY_TELEGRAM_ID[int(ks)] = vs
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

def _parse_allowlist(raw: str) -> tuple[set[str], set[int]]:
    usernames: set[str] = set()
    user_ids: set[int] = set()
    for token in (raw or "").split(","):
        item = token.strip()
        if not item:
            continue
        if item.startswith("@"):
            item = item[1:]
        if item.isdigit():
            user_ids.add(int(item))
        else:
            usernames.add(item.lower())
    return usernames, user_ids


TELEGRAM_ALLOWLIST_RAW = os.getenv("TELEGRAM_ALLOWLIST", "@b1tdreamer")
TELEGRAM_ALLOWLIST_USERNAMES, TELEGRAM_ALLOWLIST_IDS = _parse_allowlist(
    TELEGRAM_ALLOWLIST_RAW
)

# Rutas de datos (persistencia)
_data_dir_env = os.getenv("DATA_DIR", "data").strip()
DATA_DIR = Path(_data_dir_env) if _data_dir_env else DIR_PROYECTO / "data"
if not DATA_DIR.is_absolute():
    DATA_DIR = DIR_PROYECTO / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

CSV_CONVOCATORIAS = DATA_DIR / "convocatorias.csv"
CSV_IDEAS = DATA_DIR / "ideas.csv"
CSV_FUNCIONALIDAD = DATA_DIR / "funcionalidad.csv"
CSV_ENLACES = DATA_DIR / "enlaces.csv"
CSV_HUEVOS = DATA_DIR / "huevos.csv"
CSV_PROYECTOS = DATA_DIR / "proyectos.csv"
CSV_TIEMPOS = DATA_DIR / "tiempos.csv"
DB_SQLITE = DATA_DIR / "convocatorias.db"
DB_FUNCIONALIDAD = DATA_DIR / "funcionalidad.db"
CARPETA_IDEAS = DATA_DIR / "ideas"
CARPETA_IDEAS.mkdir(parents=True, exist_ok=True)
CARPETA_PROYECTOS = DATA_DIR / "proyectos"
CARPETA_PROYECTOS.mkdir(parents=True, exist_ok=True)
CSV_INVESTIGACIONES = DATA_DIR / "investigaciones.csv"
CARPETA_INVESTIGACIONES = DATA_DIR / "investigaciones"
CARPETA_INVESTIGACIONES.mkdir(parents=True, exist_ok=True)
CSV_PENDIENTES = DATA_DIR / "pendientes.csv"
CSV_DIARIO = DATA_DIR / "diario.csv"
CARPETA_DIARIO = DATA_DIR / "diario"
CARPETA_DIARIO.mkdir(parents=True, exist_ok=True)
CSV_CONTABILIDAD = DATA_DIR / "contabilidad.csv"
CSV_MEMORIAS = DATA_DIR / "memorias.csv"
CARPETA_MEMORIAS = DATA_DIR / "memorias"
CARPETA_MEMORIAS.mkdir(parents=True, exist_ok=True)

# Investigaciones (/investiga + worker)
SEARXNG_URL = os.getenv("SEARXNG_URL", "").strip().rstrip("/")
INVESTIGACION_SEARCH_MAX = max(1, int(os.getenv("INVESTIGACION_SEARCH_MAX", "5")))
INVESTIGACION_FETCH_TOP = max(0, int(os.getenv("INVESTIGACION_FETCH_TOP", "2")))
INVESTIGACION_FETCH_MAX_CHARS = max(500, int(os.getenv("INVESTIGACION_FETCH_MAX_CHARS", "6000")))
MAX_INVESTIGACIONES_POR_CICLO = max(1, int(os.getenv("MAX_INVESTIGACIONES_POR_CICLO", "3")))
INVESTIGACION_SLEEP_SEC = max(0.0, float(os.getenv("INVESTIGACION_SLEEP_SEC", "4")))
TIMEOUT_OLLAMA_INVESTIGACION = max(30, int(os.getenv("TIMEOUT_OLLAMA_INVESTIGACION", "180")))
TIMEOUT_BUSQUEDA_INVESTIGACION = max(5, int(os.getenv("TIMEOUT_BUSQUEDA_INVESTIGACION", "25")))

# Migración ligera desde instalaciones previas (solo convocatorias.csv)
_csv_legacy = DIR_PROYECTO / "convocatorias.csv"
if not CSV_CONVOCATORIAS.exists() and _csv_legacy.exists():
    try:
        shutil.copy2(_csv_legacy, CSV_CONVOCATORIAS)
    except Exception:
        pass
