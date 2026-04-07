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

# Versión del bot (armonIA en /ayuda y arranque). Subir el número en cada cambio que despliegues.
APP_VERSION = os.getenv("APP_VERSION", "0.27").strip() or "0.27"
# Zona horaria para fechas relativas y formato en /ver* (defecto España peninsular)
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Madrid").strip() or "Europe/Madrid"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# Chats adicionales para recordatorios (agenda mañana/semana, etc.), separados por coma
_telegram_notify_raw = os.getenv("TELEGRAM_NOTIFY_CHAT_IDS", "").strip()
TELEGRAM_NOTIFY_CHAT_IDS = [
    x.strip() for x in _telegram_notify_raw.split(",") if x.strip()
]

# CalDAV / Nextcloud Calendar
CALDAV_URL = os.getenv("CALDAV_URL", "")
CALDAV_USER = os.getenv("CALDAV_USER", "")
CALDAV_PASS = os.getenv("CALDAV_PASS", "")
_caldav_calendar_name_raw = os.getenv("CALDAV_CALENDAR_NAME", "MolinoLab").strip()
if not _caldav_calendar_name_raw:
    CALDAV_CALENDAR_NAMES = []
    CALDAV_CALENDAR_NAME = ""
else:
    CALDAV_CALENDAR_NAMES = [p.strip() for p in _caldav_calendar_name_raw.split(",") if p.strip()]
    CALDAV_CALENDAR_NAME = CALDAV_CALENDAR_NAMES[0] if CALDAV_CALENDAR_NAMES else ""
# URL completa del calendario (colección), ej. .../remote.php/dav/calendars/usuario/molinolab/
_caldav_calendar_url_raw = os.getenv("CALDAV_CALENDAR_URL", "").strip()
CALDAV_CALENDAR_URL = (
    _caldav_calendar_url_raw.rstrip("/") + "/" if _caldav_calendar_url_raw else ""
)

# Calendarios para lectura de agenda (/informame, recordatorios): nombres/slugs separados por coma.
# Vacío = se usan los mismos que CALDAV_CALENDAR_NAME(S) (p. ej. MolinoLab + molinolab compartidos).
_caldav_agenda_names_raw = os.getenv("CALDAV_AGENDA_CALENDAR_NAMES", "").strip()
CALDAV_AGENDA_CALENDAR_NAMES = (
    [p.strip() for p in _caldav_agenda_names_raw.split(",") if p.strip()]
    if _caldav_agenda_names_raw
    else []
)

# JSON: usuario de Telegram (sin @, minusculas) -> nombre/slug del calendario personal en CalDAV.
# Solo se mezclan eventos de ese calendario cuando el usuario coincide (p. ej. b1tdreamer -> personal).
_personal_cal_raw = os.getenv("CALDAV_PERSONAL_CALENDAR_BY_TELEGRAM", "").strip()
CALDAV_PERSONAL_CALENDAR_BY_TELEGRAM: dict[str, str] = {}
if _personal_cal_raw:
    try:
        _pc_obj = json.loads(_personal_cal_raw)
        if isinstance(_pc_obj, dict):
            CALDAV_PERSONAL_CALENDAR_BY_TELEGRAM = {
                str(k).strip().lstrip("@").lower(): str(v).strip()
                for k, v in _pc_obj.items()
                if str(k).strip() and str(v).strip()
            }
    except json.JSONDecodeError:
        pass

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
DECK_STACK_FABRICAR = os.getenv("DECK_STACK_FABRICAR", "Fabricar").strip()

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
CSV_FABRICA = DATA_DIR / "fabrica.csv"
CSV_RECOMENDACIONES = DATA_DIR / "recomendaciones.csv"

# Descargas de media (yt-dlp) en el servidor
_descargas_dir_env = os.getenv("DESCARGAS_DIR", "").strip()
if _descargas_dir_env:
    DESCARGAS_DIR = Path(_descargas_dir_env)
    if not DESCARGAS_DIR.is_absolute():
        DESCARGAS_DIR = DATA_DIR / DESCARGAS_DIR
else:
    DESCARGAS_DIR = DATA_DIR / "descargas"
DESCARGAS_DIR.mkdir(parents=True, exist_ok=True)
DESCARGAS_TIMEOUT_SEC = max(60, int(os.getenv("DESCARGAS_TIMEOUT_SEC", "600")))
DESCARGAS_MAX_MB = max(1, int(os.getenv("DESCARGAS_MAX_MB", "500")))
DESCARGA_ENVIAR_TELEGRAM_MAX_MB = max(0, int(os.getenv("DESCARGA_ENVIAR_TELEGRAM_MAX_MB", "45")))

# Tuya Cloud (enchufe smart)
TUYA_CLIENT_ID = os.getenv("TUYA_CLIENT_ID", "").strip()
TUYA_CLIENT_SECRET = os.getenv("TUYA_CLIENT_SECRET", "").strip()
TUYA_DEVICE_ID = os.getenv("TUYA_DEVICE_ID", "").strip()
TUYA_SWITCH_CODE = os.getenv("TUYA_SWITCH_CODE", "switch_1").strip() or "switch_1"
TUYA_REGION = os.getenv("TUYA_REGION", "eu").strip() or "eu"
TUYA_API_BASE_URL = os.getenv("TUYA_API_BASE_URL", "").strip()

# BambuLab (estado por MQTT local; apagado vía enchufe asociado)
BAMBU_HOST = os.getenv("BAMBU_HOST", "").strip()
BAMBU_SERIAL = os.getenv("BAMBU_SERIAL", "").strip()
BAMBU_ACCESS_CODE = os.getenv("BAMBU_ACCESS_CODE", "").strip()
BAMBU_MQTT_PORT = max(1, int(os.getenv("BAMBU_MQTT_PORT", "8883")))
BAMBU_STATUS_TIMEOUT_SEC = max(2, int(os.getenv("BAMBU_STATUS_TIMEOUT_SEC", "8")))
BAMBU_POWER_OFF_TUYA_DEVICE_ID = os.getenv("BAMBU_POWER_OFF_TUYA_DEVICE_ID", "").strip()

# Notas Nextcloud (API con credencial del usuario Telegram, no la del bot).
# JSON: { "telegram_username_sin_arroba": { "nc_user": "uid_nextcloud", "app_password": "xxxx" }, ... }
_nc_notes_raw = os.getenv("NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM", "").strip()
NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM: dict[str, dict[str, str]] = {}
if _nc_notes_raw:
    try:
        _nn_obj = json.loads(_nc_notes_raw)
        if isinstance(_nn_obj, dict):
            for k, v in _nn_obj.items():
                ks = str(k).strip().lstrip("@").lower()
                if not ks or not isinstance(v, dict):
                    continue
                nu = str(v.get("nc_user", "")).strip()
                np = str(v.get("app_password", "")).strip()
                if nu and np:
                    NEXTCLOUD_NOTES_CREDENTIALS_BY_TELEGRAM[ks] = {
                        "nc_user": nu,
                        "app_password": np,
                    }
    except json.JSONDecodeError:
        pass

# Credenciales para sincronizar .md locales → Nextcloud Notes (cron/API; sin usuario Telegram).
NEXTCLOUD_NOTES_SYNC_NC_USER = os.getenv("NEXTCLOUD_NOTES_SYNC_NC_USER", "").strip()
NEXTCLOUD_NOTES_SYNC_APP_PASSWORD = os.getenv("NEXTCLOUD_NOTES_SYNC_APP_PASSWORD", "").strip()
NOTES_SYNC_MAP_PATH = DATA_DIR / "nextcloud_notes_sync_map.json"

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
