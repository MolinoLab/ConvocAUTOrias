# Workflows n8n para ConvocAUTOrias

Estos workflows orquestan las tareas periódicas del sistema. n8n llama a la API interna (`api:8888`) que ejecuta los scripts Python.

## Importar workflows

1. Arranca el stack: `docker compose up -d`
2. Abre n8n: http://localhost:5678
3. Login: usuario `admin`, contraseña la definida en `N8N_PASSWORD` (`.env`)
4. Para cada workflow: Menú → Import from File → selecciona el JSON
5. Activa cada workflow (toggle "Active" en la esquina superior derecha)

## Workflows incluidos

| Archivo | Descripción | Horario |
|---------|-------------|---------|
| `04-indexar-ideas.json` | Indexa ideas nuevas de `data/ideas/` hacia `data/ideas.csv` | Diario 8:00 |
| `05-sync-nextcloud-datos.json` | Sube CSV a Datos/ y sincroniza markdown a Nextcloud Notes (no vault WebDAV) | Diario 22:30 |
| `01-scraper-periodico.json` | **Cola principal**: investigación profunda de convocatorias (`POST /scrape` → `worker_scraper --once`) | Cada 6 horas |
| `02-revisar-plazos.json` | Revisa plazos próximos y notifica por Telegram | Diario 9:00 |
| `03-sync-caldav.json` | Sincroniza plazos con calendario CalDAV | Diario 9:15 |
| `06-notificar-agenda-manana.json` | Eventos y tareas (Deck + VTODO) para el día siguiente; Telegram si hay ítems | Diario 18:00 (TZ workflow: Europe/Madrid) |
| `07-procesar-investigaciones.json` | Procesa cola `/investiga`: búsqueda web (Python), Ollama, Markdown y Telegram | 09:00 y 21:00 (TZ: Europe/Madrid) |
| `08-notificar-agenda-semana.json` | Resumen lunes–domingo de la semana entrante (CalDAV + Deck + VTODO) | Domingo 21:00 (TZ: Europe/Madrid) |
| `09-investigar-convocatoria.json` | Disparo manual para investigar una convocatoria y generar resumen estructurado (MD+JSON) | Manual |

## Requisitos

- El servicio **api** debe estar corriendo (expone HTTP en el puerto 8888).
- n8n usa la imagen oficial; las URLs `http://api:8888/...` resuelven en la red Docker interna.

## Notas

- Los workflows vienen con `active: false` para que los actives manualmente tras revisar la configuración.
- Puedes ajustar los horarios en la UI de n8n (doble clic en el nodo Schedule Trigger).
- Si cambias la expresión cron, usa formato de 6 campos: `segundo minuto hora día mes día_semana`.
- El workflow **06** define `settings.timezone: Europe/Madrid` para que las 18:00 sean hora peninsular; el script usa `APP_TIMEZONE` (misma zona que `/info`). La API debe tener `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` (y opcionalmente `TELEGRAM_NOTIFY_CHAT_IDS` para más destinatarios).
- El workflow **08** envía el resumen semanal a los mismos chats (`TELEGRAM_CHAT_ID` + `TELEGRAM_NOTIFY_CHAT_IDS`). Usa `CALDAV_AGENDA_CALENDAR_NAMES` (o `CALDAV_CALENDAR_NAME` con varios nombres separados por coma) para calendarios de equipo/compartidos; los mensajes incluyen hora de generación local.
- **Agenda y zona horaria:** activa cada workflow (`Active`) y confirma `settings.timezone: Europe/Madrid` en el JSON. Si el mensaje llega a una hora inesperada (p. ej. medianoche), revisa que n8n no esté en UTC y que no haya otro disparador manual. El script usa `APP_TIMEZONE` (misma zona que `/info`).
- El workflow **07** usa la misma zona horaria. El script limita cuántas investigaciones trata por ejecución (`MAX_INVESTIGACIONES_POR_CICLO`) y pausa entre pasos; evita lanzar varias ejecuciones del workflow a la vez si tu n8n lo permite (cola / sin solapes).
- El workflow **01** es el disparador programado único para procesar convocatorias con estado `pendiente_investigacion` (o `pendiente` heredado) y `investigacion_parcial` con cooldown. No hace falta duplicar ese cron en el **09**.
- El workflow **09** llama a `POST /investigar-convocatoria` (una URL concreta, manual). Útil para pruebas; la cola normal va por **01** + `/convo`.
- Extracción de ejemplos: HTML; PDF de beneficiarios pendiente de fase futura.
