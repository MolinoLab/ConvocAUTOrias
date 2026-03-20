"""
Carga variables de entorno para el sistema de autoconvocatorias.
"""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Cargar .env desde el directorio del proyecto
DIR_PROYECTO = Path(__file__).resolve().parent
load_dotenv(DIR_PROYECTO / ".env")

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

# Nextcloud WebDAV
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "").rstrip("/")
NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER", "")
NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD", "")
NEXTCLOUD_CARPETA = os.getenv("NEXTCLOUD_CARPETA", "Convocatorias")
DECK_BOARD_NAME = os.getenv("DECK_BOARD_NAME", "MolinoLab").strip()
DECK_STACK_NAME = os.getenv("DECK_STACK_NAME", "").strip()
NEXTCLOUD_IDEAS_PATH = os.getenv(
    "NEXTCLOUD_IDEAS_PATH",
    "Documents/b1tacora/b1tdreamer/Ideas",
).strip().strip("/")


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
CSV_HUEVOS = DATA_DIR / "huevos.csv"
DB_SQLITE = DATA_DIR / "convocatorias.db"
DB_FUNCIONALIDAD = DATA_DIR / "funcionalidad.db"
CARPETA_IDEAS = DATA_DIR / "ideas"
CARPETA_IDEAS.mkdir(parents=True, exist_ok=True)

# Migración ligera desde instalaciones previas (solo convocatorias.csv)
_csv_legacy = DIR_PROYECTO / "convocatorias.csv"
if not CSV_CONVOCATORIAS.exists() and _csv_legacy.exists():
    try:
        shutil.copy2(_csv_legacy, CSV_CONVOCATORIAS)
    except Exception:
        pass
