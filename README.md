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
   Comandos: `/sube <url>`, `/idea <texto>`, `/listar`, `/revisar <id>`, `/ayuda`.
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

El stack incluye cuatro servicios:

- **ollama**: IA local para análisis y adaptación de borradores
- **bot**: Bot de Telegram
- **api**: API interna (FastAPI) para que n8n invoque scraping, revisar plazos y sync CalDAV
- **n8n**: Orquestador de workflows (llama a la API por HTTP)

```bash
docker compose up -d
```

El **worker** de scraping ya no corre como contenedor 24/7: n8n llama a la API según los workflows configurados. Importa los JSON de `workflows/` en n8n (http://localhost:5678) y actívalos. Ver [workflows/README.md](workflows/README.md).

Los datos de convocatorias e ideas se guardan en `data/` y, en Docker, se persisten con el volumen nombrado `convocauto_data`.

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

# CalDAV (opcional)
CALDAV_URL=https://tu-nextcloud.com/remote.php/dav/calendars/usuario/mi-calendario/
CALDAV_USER=tu_usuario
CALDAV_PASS=tu_password
```

## Arquitectura Docker

```
┌─────────────────────────────────────────────────────────────────┐
│  docker-compose                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │ bot         │  │ api         │  │ n8n         │  │ ollama  │ │
│  │ Telegram    │  │ FastAPI     │  │ workflows   │  │ IA      │ │
│  └─────────────┘  └──────┬──────┘  └──────┬──────┘  └────┬────┘ │
│                          │               │ HTTP         │      │
│                          │               └──────────────┘      │
│                          ▼─────────────────────────────────────┤
│                   /app/data (convocatorias + ideas)              │
└─────────────────────────────────────────────────────────────────┘
```

## Bot de Telegram

El bot permite dos flujos:

1. **Convocatorias**:
   - `/sube <url>` o enviar una URL directamente.
   - Se guarda en `data/convocatorias.csv` (o `data/convocatorias.db` si existe SQLite).

2. **Ideas**:
   - `/idea <texto>` para guardar una idea en modelo hibrido.
   - Enviar **audio** o **nota de voz**: se transcribe y se guarda como idea.
   - Persistencia hibrida:
     - Metadatos en `data/ideas.csv` (`id`, `resumen`, `tags`, `categorias`, `presupuesto_aproximado`, `ruta`, `fuente`).
     - Desarrollo completo en `data/ideas/{id}.md`.

Flujo diario de ideas manuales:
- El workflow `04-indexar-ideas.json` llama al endpoint `POST /indexar-ideas`.
- Ese script revisa `data/ideas/*.md` y `data/ideas/*.txt` no indexados y los añade a `data/ideas.csv`.
