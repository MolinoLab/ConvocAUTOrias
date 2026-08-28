# ConvocAUTOrias

Sistema de automatización (bot de Telegram + API FastAPI + IA local Ollama) para monitorizar convocatorias artísticas. Persistencia basada en ficheros (CSV/Markdown/SQLite) bajo `data/`; no requiere servidor de base de datos externo. Ver `README.md` para la descripción funcional y los comandos completos.

## Cursor Cloud specific instructions

### Entorno Python
- Las dependencias se instalan en un virtualenv en `.venv/` (está en `.gitignore`). Usa siempre `.venv/bin/python`, `.venv/bin/pip`, `.venv/bin/uvicorn`, etc. (o `source .venv/bin/activate`). El `python3` del sistema NO tiene las dependencias instaladas.
- El proyecto declara Python 3.11+ (`Dockerfile` usa `python:3.11-slim`); en el entorno cloud corre bajo Python 3.12 sin problemas.
- `openai-whisper` arrastra `torch` (instalación grande); la primera resolución de dependencias es lenta. El import del bot carga whisper/torch, así que su arranque tarda unos segundos.

### Servicios
- **api** (FastAPI, requerido para automatización y el flujo más fácil de probar): `.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8888 --reload`. Swagger interactivo en `http://localhost:8888/docs`. Endpoints útiles sin dependencias externas: `GET /health`, `GET /funcionalidad`, `POST /funcionalidad` (escriben/leen `data/funcionalidad.csv`).
- **bot** (Telegram, interfaz principal): `.venv/bin/python -m bot.telegram_bot`. **Sale inmediatamente con `Error: TELEGRAM_BOT_TOKEN no configurado`** si no existe `.env` con `TELEGRAM_BOT_TOKEN` (y `TELEGRAM_CHAT_ID`). Para el flujo E2E completo del bot también hace falta Ollama corriendo (features de IA).
- **ollama / n8n / openclaw**: opcionales; se levantan vía `docker compose up -d` (requiere `.env`). No son necesarios para tests ni para el flujo básico de la API.
- La configuración se lee de un `.env` en la raíz (no versionado; `config.py` lo carga con `python-dotenv`). La mayoría de integraciones (Nextcloud, CalDAV, Tuya, BambuLab, etc.) degradan de forma limpia si sus variables no están definidas.

### Tests y lint
- Tests: `.venv/bin/python -m unittest discover -s tests -v`. No hay `pytest` ni linter (ruff/flake8/black) configurados en el repo; para chequeo rápido de sintaxis usa `.venv/bin/python -m py_compile <archivos>`.

### Datos
- `data/` está versionado en git (CSV/Markdown). Al probar endpoints que escriben (p. ej. `POST /funcionalidad`) se modifican esos ficheros; revierte los cambios de prueba (`git checkout -- data/...`) antes de commitear.
