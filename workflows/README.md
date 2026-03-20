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
| `05-sync-nextcloud-datos.json` | Sube `convocatorias.csv`, `ideas.csv` e ideas markdown/texto a Nextcloud | Diario 22:30 |
| `01-scraper-periodico.json` | Scraping y enriquecimiento con Ollama | Cada 6 horas |
| `02-revisar-plazos.json` | Revisa plazos próximos y notifica por Telegram | Diario 9:00 |
| `03-sync-caldav.json` | Sincroniza plazos con calendario CalDAV | Diario 9:15 |
| `06-notificar-agenda-manana.json` | Eventos y tareas (Deck + VTODO) para el día siguiente; Telegram si hay ítems | Diario 22:00 (TZ workflow: Europe/Madrid) |
| `07-procesar-investigaciones.json` | Procesa cola `/investiga`: búsqueda web (Python), Ollama, Markdown y Telegram | 09:00 y 21:00 (TZ: Europe/Madrid) |

## Requisitos

- El servicio **api** debe estar corriendo (expone HTTP en el puerto 8888).
- n8n usa la imagen oficial; las URLs `http://api:8888/...` resuelven en la red Docker interna.

## Notas

- Los workflows vienen con `active: false` para que los actives manualmente tras revisar la configuración.
- Puedes ajustar los horarios en la UI de n8n (doble clic en el nodo Schedule Trigger).
- Si cambias la expresión cron, usa formato de 6 campos: `segundo minuto hora día mes día_semana`.
- El workflow **06** define `settings.timezone: Europe/Madrid` para que las 22:00 sean hora peninsular; el script usa la fecha “mañana” en esa misma zona. La API debe tener `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` como en `revisar_convocatorias`.
- El workflow **07** usa la misma zona horaria. El script limita cuántas investigaciones trata por ejecución (`MAX_INVESTIGACIONES_POR_CICLO`) y pausa entre pasos; evita lanzar varias ejecuciones del workflow a la vez si tu n8n lo permite (cola / sin solapes).
