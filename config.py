"""
Carga variables de entorno para el sistema de autoconvocatorias.
"""
import os
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

# Ollama (IA local)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")

# Nextcloud WebDAV
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "").rstrip("/")
NEXTCLOUD_USER = os.getenv("NEXTCLOUD_USER", "")
NEXTCLOUD_PASSWORD = os.getenv("NEXTCLOUD_PASSWORD", "")
NEXTCLOUD_CARPETA = os.getenv("NEXTCLOUD_CARPETA", "Convocatorias")

# Rutas del proyecto
CSV_CONVOCATORIAS = DIR_PROYECTO / "convocatorias.csv"
DB_SQLITE = DIR_PROYECTO / "convocatorias.db"
CARPETA_IDEAS = DIR_PROYECTO / "ideas"
