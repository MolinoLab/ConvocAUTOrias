# ConvocAUTOrias

Sistema para monitorizar convocatorias artísticas: ingesta vía Telegram, extracción web, análisis con IA local (Ollama), transcripción de audios y adaptación de ideas a formularios.

## Requisitos

- Python 3.11+
- [Ollama](https://ollama.ai) (opcional, para adaptador de ideas y worker de scraping)

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

1. **Migrar CSV existente** (si tienes datos en formato Excel):
   ```bash
   python scripts/procesar_csv.py
   ```

2. **Ejecutar el bot de Telegram**:
   ```bash
   python -m bot.telegram_bot
   ```
   Comandos: `/sube <url>`, `/idea <texto>`, `/func <texto> <prioridad> [estado]`, `/listfunc`, `/listar`, `/revisar <id>`, `/ayuda`.
   También puedes enviar una URL directamente. Si envías un audio, el bot lo transcribe y lo guarda como idea.

3. **Revisar plazos y notificaciones**:
   ```bash
   python scripts/revisar_convocatorias.py
   ```

4. **Generar borrador y subir a Nextcloud**:
   ```bash
   python scripts/generar_borrador.py <id_convocatoria>
   ```

5. **Sincronizar plazos con calendario CalDAV**:
   ```bash
   python scripts/sync_caldav.py
   ```

## Docker

El stack incluye cinco servicios:

- **ollama**: IA local para análisis y adaptación de borradores
- **bot**: Bot de Telegram
- **api**: API interna (FastAPI) para que n8n y OpenClaw invoquen scraping, revisar plazos, sync CalDAV y generar borradores
- **n8n**: Orquestador de workflows (llama a la API por HTTP)
- **openclaw**: Asistente IA conversacional que usa Ollama y llama a la API mediante skills

```bash
docker compose up -d
```

El **worker** de scraping ya no corre como contenedor 24/7: n8n llama a la API según los workflows configurados. Importa los JSON de `workflows/` en n8n (http://localhost:5678) y actívalos. Ver [workflows/README.md](workflows/README.md).

Los datos de convocatorias e ideas se guardan en `data/` dentro del proyecto (sin volumen Docker dedicado para bot/api), para facilitar backup y versionado con git.

### Primera vez: descargar modelo en Ollama

```bash
docker exec -it convocauto-ollama ollama pull phi3:mini
# o para mayor calidad (más RAM): ollama pull mistral:7b
```

## Despliegue en VPS (Portainer)

1. **Clonar el repositorio** en el VPS:
   ```bash
   git clone https://github.com/TU_USUARIO/ConvocAUTOrias.git
   cd ConvocAUTOrias
   ```

2. **Crear `.env`** con las variables necesarias (ver Configuración).

3. **Desplegar con Portainer**:
   - Stacks → Add stack
   - Nombre: `convocauto`
   - Web editor: pegar el contenido de `docker-compose.yml`
   - O Git repository: URL del repo, Compose path: `docker-compose.yml`
   - Deploy

4. **Descargar modelo** en Ollama (ver arriba).

### Actualizar desde GitHub

Tras hacer cambios locales y `git push`:

```bash
cd ~/ConvocAUTOrias
git pull
docker compose build --no-cache
docker compose up -d
```

O crear un script `actualizar_convocauto.sh`:

```bash
#!/bin/bash
cd ~/ConvocAUTOrias
git pull
docker compose build --no-cache
docker compose up -d
echo "ConvocAUTOrias actualizado."
```

## Configuración

Crear `.env` en la raíz del proyecto:

```env
# n8n (orquestador)
N8N_PASSWORD=contraseña_segura_para_admin

# Telegram
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
TELEGRAM_ALLOWLIST=@b1tdreamer

# Ollama (en Docker usa http://ollama:11434)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=phi3:mini

# Whisper (transcripcion de audio)
WHISPER_MODEL=base

# Directorio de datos (opcional)
DATA_DIR=data

# Nextcloud WebDAV
NEXTCLOUD_URL=https://tu-nextcloud.com
NEXTCLOUD_USER=tu_usuario
NEXTCLOUD_PASSWORD=tu_password
NEXTCLOUD_CARPETA=Convocatorias
DECK_BOARD_NAME=MolinoLab
# DECK_STACK_NAME=Pendientes
NEXTCLOUD_IDEAS_PATH=Documents/b1tacora/b1tdreamer/Ideas

# CalDAV (opcional)
CALDAV_URL=https://tu-nextcloud.com/remote.php/dav
CALDAV_USER=tu_usuario
CALDAV_PASS=tu_password
# Nombre del calendario (se compara con el segmento de la URL, ej. .../calendars/usuario/molinolab/)
# No uses coincidencia en la URL completa: un dominio como hub.molinolab.org contiene "molinolab".
CALDAV_CALENDAR_NAME=MolinoLab
# Opcional: URL exacta de la colección del calendario (sustituye al filtro por nombre)
# CALDAV_CALENDAR_URL=https://tu-nextcloud.com/remote.php/dav/calendars/usuario/molinolab/
# Si CALDAV_USER es otra cuenta (p. ej. bot de servicio), el segmento .../calendars/USUARIO/...
# debe ser el de CALDAV_USER, o bien comparte el calendario con esa cuenta: el bot resolverá la
# colección real vía CalDAV usando el slug (molinolab) o CALDAV_CALENDAR_NAME.
```

## Arquitectura Docker

```
┌──────────────────────────────────────────────────────────────────────────┐
│  docker-compose                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ bot      │  │ api      │  │ n8n      │  │ ollama   │  │ openclaw   │ │
│  │ Telegram │  │ FastAPI  │  │ workflows│  │ IA local │  │ Asistente  │ │
│  └──────────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──┬───┬────┘ │
│                     │             │ HTTP        │           │   │      │
│                     │             └─────────────┘           │   │      │
│                     │◄──────────────────────────────────────┘   │      │
│                     │         http_request (skills)              │      │
│                     │◄──────────────────────────────────────────┘      │
│                     ▼                          Ollama (modelo local)   │
│              /app/data (convocatorias + ideas + funcionalidad)          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Bot de Telegram

El bot permite tres flujos:

1. **Convocatorias**:
   - `/sube <url>` o enviar una URL directamente.
   - Se guarda en `data/convocatorias.csv` (o `data/convocatorias.db` si existe SQLite).

2. **Ideas**:
   - `/idea <texto>` para guardar una idea en modelo hibrido.
   - Enviar **audio** o **nota de voz**: se transcribe y se guarda como idea.
   - Persistencia hibrida:
     - Metadatos en `data/ideas.csv` (`id`, `resumen`, `tags`, `categorias`, `presupuesto_aproximado`, `ruta`, `fuente`).
     - Desarrollo completo en `data/ideas/{id}.md`.
   - Restriccion de acceso: el bot solo responde a usuarios permitidos en `TELEGRAM_ALLOWLIST`.

3. **Funcionalidades** (tareas de desarrollo pendientes):
   - `/func <texto> <prioridad 1-5> [estado]` para registrar una funcionalidad.
   - `/listfunc` para listar todas las funcionalidades ordenadas por prioridad (mayor primero).
   - Prioridad: numérica de 1 (baja) a 5 (urgente).
   - Estados válidos: `pendiente`, `en_progreso`, `hecha` (por defecto: `pendiente`).
   - Persistencia en `data/funcionalidad.csv` (o `data/funcionalidad.db` si existe SQLite).
   - Esquema: `id`, `texto`, `prioridad`, `estado`, `fecha_ingesta`, `fuente`.
   - Ejemplo: `/func mejorar parser del scraper 4 pendiente`
   - API: `GET /funcionalidad` (listar), `POST /funcionalidad` (crear).

Flujo diario de ideas manuales:
- El workflow `04-indexar-ideas.json` llama al endpoint `POST /indexar-ideas`.
- Ese script revisa `data/ideas/*.md` y `data/ideas/*.txt` no indexados y los añade a `data/ideas.csv`.

Sincronizacion con Nextcloud:
- El workflow `05-sync-nextcloud-datos.json` llama al endpoint `POST /sync-nextcloud-datos`.
- Sube `data/convocatorias.csv`, `data/ideas.csv` y los ficheros de `data/ideas/` a `Documents/b1tacora/b1tdreamer/Ideas`.

## OpenClaw (asistente conversacional)

OpenClaw es un asistente IA de código abierto que funciona como interfaz conversacional para ConvocAUTOrias. Usa exclusivamente Ollama (sin APIs de pago) y llama a la API interna mediante skills.

### Primera vez: configurar OpenClaw

1. Copiar la plantilla de configuración:

   ```bash
   cp openclaw/openclaw.json.example openclaw/openclaw.json
   ```

2. (Opcional) Editar `openclaw/openclaw.json` para:
   - Cambiar el modelo por defecto (por ejemplo `ollama/mistral:7b` en lugar de `ollama/phi3:mini`).
   - Configurar `gateway.auth.token` con un token secreto propio.
   - Habilitar canales de mensajería (Telegram, Discord, etc.) en la sección `channels`.

3. Levantar el stack completo:

   ```bash
   docker compose up -d
   ```

4. El gateway de OpenClaw estará disponible en `http://localhost:18789`.

### Skills

Las skills de ConvocAUTOrias están en `openclaw/workspace/skills/convocautorias/SKILL.md`. Enseñan al agente a usar los endpoints de la API (`/scrape`, `/revisar`, `/sync-caldav`, `/indexar-ideas`, `/sync-nextcloud-datos`, `/generar-borrador`).

Si editas una skill, OpenClaw la recarga automáticamente en el siguiente turno (con `watch: true` en la configuración).

Para añadir nuevas skills, crea una carpeta en `openclaw/workspace/skills/<nombre>/` con su `SKILL.md`.

### Compatibilidad con el bot existente

El bot de Telegram (`bot`) sigue funcionando en paralelo. OpenClaw es un canal adicional; no sustituye al bot sino que amplía las posibilidades de interacción con lenguaje natural.
