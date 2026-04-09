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
   Comandos principales: `/convo <url>`, `/url <url>`, `/listconvo`, `/listurl`, `/idea <texto>`, `/func <texto> [prioridad]`, `/ayuda`.
   Una URL suelta (sin comando) se guarda en `data/enlaces.csv`. Convocatorias solo con `/convo`. Si envías un audio, el bot lo transcribe y lo guarda como idea.

   **Atajos de comandos (Telegram)** — mismos handlers que los comandos largos; la lista detallada está aquí para no alargar `/ayuda`:

   - `/ls…` equivale a `/list…` (ej. `/lsconvo`, `/lscv`, `/lsfn`). `/v…` a `/ver…` (ej. `/vconvo`, `/vcv`).
   - Convocatorias: `/lscv`, `/vcv`; borrar: `/rmcv` → `/rmconvo`.
   - Enlaces: `/lsurl`, `/vurl`; borrar: `/rmu` → `/rmurl`.
   - Ideas: `/lsid`, `/vid`; borrar: `/rmid`, `/rmideas` → `/rmidea`.
   - Memorias: `/lsmm`, `/vmm`; borrar: `/rmm`, `/rmmemorias` → `/rmmemoria`.
   - Proyectos: `/lsproy`, `/lspy`, `/vproy`, `/vpy`; alta `/proy`, `/py`; `/modproy`, `/modpy`; borrar: `/rmproy`, `/rmpy`, `/rmproyectos` → `/rmproyecto`.
   - Tiempos: `/lstm`, `/vtm` (sin comando `rm` equivalente).
   - Investigaciones: `/lsinv`, `/vinv`; borrar: `/rminv`, `/rminvestigaciones` → `/rminvestigacion`.
   - Funcionalidades: `/lsfn`, `/lsfunc`, `/vfn`, `/vfunc`; borrar: `/rmfn`, `/rmfuncionalidades` → `/rmfunc`.
   - Fabricación: `/lsfab`, `/vfab`; borrar: `/rmfb` → `/rmfab`.
   - Eventos: `/lsev`, `/vev`; borrar: `/rmev`, `/rmeventos` → `/rmevento`.
   - Tareas: `/lst`, `/vt`; borrar: `/rmt`, `/rmtareas` → `/rmtarea`.
   - Pendientes: `/lspen`, `/vpen`; borrar: `/rmpen`, `/rmspendientes` → `/rmpendientes`.
   - Facturas: `/fct`, `/vfct`; listado contable: `/lsfct`; borrar: `/rmfct`, `/rmcontabilidad` → `/rmfactura`.

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
# Chats extra para recordatorios agenda (mañana / semana), separados por coma
# TELEGRAM_NOTIFY_CHAT_IDS=id2,id3
TELEGRAM_ALLOWLIST=@b1tdreamer
# Usuarios sin @username en Telegram: añade su ID numérico separado por comas, p. ej.:
# TELEGRAM_ALLOWLIST=@yo,5088114697

# Ollama (en Docker usa http://ollama:11434)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=phi3:mini
# Opcional: modelo solo para /investiga (por defecto = OLLAMA_MODEL)
# OLLAMA_MODEL_INVESTIGACION=qwen2.5:3b

# Investigaciones (/investiga): búsqueda en Python (ver workflow 07 en n8n)
# Si defines SEARXNG_URL se usa en lugar de DuckDuckGo (paquete duckduckgo-search).
# SEARXNG_URL=https://busqueda.ejemplo
# INVESTIGACION_SEARCH_MAX=5
# INVESTIGACION_FETCH_TOP=2
# MAX_INVESTIGACIONES_POR_CICLO=3
# INVESTIGACION_SLEEP_SEC=4

# Whisper (transcripcion de audio)
WHISPER_MODEL=base

# Directorio de datos (opcional). Para Obsidian: apunta a una carpeta dentro del vault
# que sincroniza el cliente Nextcloud, o usa un enlace simbólico / union (Windows: mklink /J).
DATA_DIR=data

# Nextcloud WebDAV
NEXTCLOUD_URL=https://tu-nextcloud.com
NEXTCLOUD_USER=tu_usuario
NEXTCLOUD_PASSWORD=tu_password
# Base del vault (Obsidian), ruta bajo el usuario de arriba (p. ej. bot).
# Si el vault está en otra cuenta: comparte la carpeta con ese usuario y usa aquí el path
# que ves al entrar como bot en Archivos (ej. b1tacora/b1tdreamer), no el enlace /f/...
# NEXTCLOUD_VAULT_BASE=Documents/b1tacora/b1tdreamer
# Rutas completas por categoría (opcional; si no las pones, se cuelgan del vault):
# Convocatorias, Ideas, Facturas, Proyectos, Investigaciones, Memorias, Datos (CSVs)
# NEXTCLOUD_CARPETA=Documents/b1tacora/b1tdreamer/Convocatorias
DECK_BOARD_NAME=MolinoLab
# DECK_STACK_NAME=Pendientes
# Asignar tarjetas Deck al crear tareas desde Telegram (uid de usuario en Nextcloud Deck):
# DECK_ASSIGNEE_BY_TELEGRAM_USERNAME={"miusuario":"uid-deck"}
# Si la persona no tiene @username público, usa su id numérico de Telegram:
# DECK_ASSIGNEE_BY_TELEGRAM_ID={"5088114697":"uid-deck"}
# (Las rutas de ideas/facturas/etc. usan el vault por defecto; solo define NEXTCLOUD_IDEAS_PATH si quieres otro sitio.)

# CalDAV (opcional)
CALDAV_URL=https://tu-nextcloud.com/remote.php/dav
CALDAV_USER=tu_usuario
CALDAV_PASS=tu_password
# Nombre(s) del calendario (slug en URL o nombre mostrado). Varios: MolinoLab, Personal
# Deja vacío solo si quieres considerar todos los calendarios de la cuenta.
CALDAV_CALENDAR_NAME=MolinoLab
# Opcional: URL exacta de la colección del calendario (sustituye al filtro por nombre)
# CALDAV_CALENDAR_URL=https://tu-nextcloud.com/remote.php/dav/calendars/usuario/molinolab/
# Si CALDAV_USER es otra cuenta (p. ej. bot de servicio), el segmento .../calendars/USUARIO/...
# debe ser el de CALDAV_USER, o bien comparte el calendario con esa cuenta: el bot resolverá la
# colección real vía CalDAV usando el slug (molinolab) o CALDAV_CALENDAR_NAME.
```

### Sincronización opcional hacia Nextcloud (WebDAV)

Desde la raíz del proyecto: `python scripts/sync_nextcloud_datos.py`. Coloca los CSV en `{vault}/Datos/` y los `.md` en `{vault}/Ideas/`, `Proyectos/`, `Investigaciones/` y `Memorias/` (según `NEXTCLOUD_VAULT_BASE` y las variables `NEXTCLOUD_*_PATH` en `config.py`).

**Vault en la cuenta de b1tdreamer y usuario WebDAV `bot`:** en Nextcloud, como b1tdreamer, comparte la carpeta del vault (o la subcarpeta donde quieras `Ideas/`, `Datos/`, etc.) con el usuario `bot`, con permisos de edición. Cierra sesión y entra como `bot` → Archivos: anota la ruta desde la raíz de “Todos los archivos” hasta esa carpeta (segmentos de la ruta, sin dominio). Esa cadena es el valor de `NEXTCLOUD_VAULT_BASE`. El cliente construye URLs del estilo `/remote.php/dav/files/bot/<NEXTCLOUD_VAULT_BASE>/Ideas/...`; un enlace interno tipo `https://…/f/2343` no sirve como sustituto de esa ruta.

**Errores en el registro de Nextcloud** (`app_api` / `localhost:8780`, `richdocuments` 404, `notes` “Undefined array key node”): son de otras apps (Ex-Apps proxy, Collabora/OnlyOffice, Notes). No son la causa de que falle la subida WebDAV de ConvocAUTOrias; puedes tratarlos aparte en la administración del servidor.

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
│              /app/data (convocatorias + ideas + enlaces + funcionalidad) │
└──────────────────────────────────────────────────────────────────────────┘
```

## Bot de Telegram

El bot permite varios flujos:

1. **Convocatorias**:
   - `/convo <url>` para añadir una convocatoria (scraping cuando sea posible).
   - `/listconvo`, `/verconvo <n>`, `/rmconvo <n> [n ...]`.
   - Se guarda en `data/convocatorias.csv` (o `data/convocatorias.db` si existe SQLite).

2. **Enlaces sin categorizar**:
   - URL suelta en el chat o `/url <https://...> [notas]` → `data/enlaces.csv` (columnas `tags`, `categorias` editables en el CSV).
   - `/listurl`, `/verurl <n>`, `/rmurl <n> [n ...]`.

3. **Ideas**:
   - `/idea <texto>` para guardar una idea en modelo hibrido.
   - Enviar **audio** o **nota de voz**: se transcribe y se guarda como idea.
   - Persistencia hibrida:
     - Metadatos en `data/ideas.csv` (`id`, `resumen`, `tags`, `categorias`, `presupuesto_aproximado`, `ruta`, `fuente`).
     - Desarrollo completo en `data/ideas/{id}.md`.
   - Restriccion de acceso: el bot solo responde a usuarios permitidos en `TELEGRAM_ALLOWLIST`.

4. **Funcionalidades** (tareas de desarrollo pendientes):
   - `/func <texto> [prioridad 1-5]` para registrar (prioridad por defecto 3; el estado se gestiona en almacenamiento pero no se muestra en el bot).
   - `/listfunc`, `/verfunc <n>`, `/rmfunc <n> [n ...]`.
   - Prioridad: numérica de 1 (baja) a 5 (urgente).
   - Persistencia en `data/funcionalidad.csv` (o `data/funcionalidad.db` si existe SQLite).
   - API: `GET /funcionalidad` (listar), `POST /funcionalidad` (crear).

Otros comandos del bot: tareas Nextcloud Deck (`/tarea`, `/listtareas`, …), eventos CalDAV (`/evento`, `/listeventos`, …), huevos (`/huevos`, `/listhuevos`). Ver `/ayuda` en Telegram.

Flujo diario de ideas manuales:
- El workflow `04-indexar-ideas.json` llama al endpoint `POST /indexar-ideas`.
- Ese script revisa `data/ideas/*.md` y `data/ideas/*.txt` no indexados y los añade a `data/ideas.csv`.

Sincronizacion con Nextcloud:
- El workflow `05-sync-nextcloud-datos.json` llama al endpoint `POST /sync-nextcloud-datos`.
- Sube `data/convocatorias.csv`, `data/ideas.csv`, `data/enlaces.csv` (si existe) y los ficheros de `data/ideas/` a `{NEXTCLOUD_VAULT_BASE}/Ideas` (y el resto de categorías según `config.py`).

Investigación estructurada de convocatorias:
- Endpoint API: `POST /investigar-convocatoria`.
- Request JSON (mínimo): `{"url":"https://...","query":"","modo":"manual","chat_id":""}` (usa `url` o `query`).
- Respuesta: `success`, `resultado_id`, `ruta_markdown`, `ruta_json`, `resumen_corto`, `fuentes_count`, `warning`.
- Persistencia: `data/resumenes_convocatoria/{id}.md`, `data/resumenes_convocatoria/{id}.json` e índice `data/resumenes_convocatoria.csv`.
- Limitación actual: extracción de ejemplos de beneficiarios desde HTML; los anexos PDF quedan marcados como pendiente de fase PDF.

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

Las skills de ConvocAUTOrias están en `openclaw/workspace/skills/convocautorias/SKILL.md`. Enseñan al agente a usar los endpoints de la API (`/scrape`, `/revisar`, `/sync-caldav`, `/indexar-ideas`, `/sync-nextcloud-datos`, `/generar-borrador`, `/investigar-convocatoria`).

Si editas una skill, OpenClaw la recarga automáticamente en el siguiente turno (con `watch: true` en la configuración).

Para añadir nuevas skills, crea una carpeta en `openclaw/workspace/skills/<nombre>/` con su `SKILL.md`.

### Compatibilidad con el bot existente

El bot de Telegram (`bot`) sigue funcionando en paralelo. OpenClaw es un canal adicional; no sustituye al bot sino que amplía las posibilidades de interacción con lenguaje natural.
