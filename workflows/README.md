# Workflows n8n para ConvocAUTOrias

Estos workflows orquestan las tareas periódicas del sistema. Importa los JSON en n8n (http://localhost:5678) y actívalos.

## Importar workflows

1. Arranca el stack: `docker compose up -d`
2. Abre n8n: http://localhost:5678
3. Login: usuario `admin`, contraseña la definida en `N8N_PASSWORD` (`.env`)
4. Para cada workflow: Menú → Import from File → selecciona el JSON
5. Activa cada workflow (toggle "Active" en la esquina superior derecha)

## Workflows incluidos

| Archivo | Descripción | Horario |
|---------|-------------|---------|
| `01-scraper-periodico.json` | Scraping y enriquecimiento con Ollama | Cada 6 horas |
| `02-revisar-plazos.json` | Revisa plazos próximos y notifica por Telegram | Diario 9:00 |
| `03-sync-caldav.json` | Sincroniza plazos con calendario CalDAV | Diario 9:15 |

## Requisitos

- El nodo **Execute Command** debe estar habilitado (variable `NODES_EXCLUDE=[]` en docker-compose).
- La imagen n8n custom incluye Python y las dependencias del proyecto.
- Los comandos se ejecutan con `python3` desde `/app` (directorio del proyecto montado).

## Notas

- Los workflows vienen con `active: false` para que los actives manualmente tras revisar la configuración.
- Puedes ajustar los horarios en la UI de n8n (doble clic en el nodo Schedule Trigger).
- Si cambias la expresión cron, usa formato de 6 campos: `segundo minuto hora día mes día_semana`.
