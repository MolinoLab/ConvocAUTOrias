FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema (Node para MCP vía npx + herramientas del agente)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código ( .env se inyecta vía env_file en docker-compose )
COPY . .

# Ejecutar bot por defecto
CMD ["python", "-m", "bot.telegram_bot"]
