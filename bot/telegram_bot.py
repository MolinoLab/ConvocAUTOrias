"""
Bot Telegram que recibe URLs y comandos.
Comandos: /sube <url>, /listar, /revisar <id>, /ayuda.
URL enviada sin comando se interpreta como nueva convocatoria.
"""
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

# Añadir proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.error import Conflict

import config
from src.db import Convocatoria, añadir, buscar_por_id, listar, actualizar
from src.scraper import extraer

# Regex para detectar URLs
URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)


def _es_url(texto: str) -> bool:
    return bool(URL_PATTERN.match(texto.strip()))


def _extraer_url(texto: str) -> str | None:
    m = URL_PATTERN.search(texto)
    return m.group(0).strip() if m else None


def _generar_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/sube <url> - Sube una convocatoria por URL\n"
        "/listar - Lista las convocatorias pendientes\n"
        "/revisar <id> - Marca una convocatoria como procesada\n"
        "/ayuda - Muestra esta ayuda\n\n"
        "También puedes enviar una URL directamente para subirla."
    )


async def cmd_añadir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /sube <url>")
        return
    url = " ".join(context.args).strip()
    if not _es_url(url):
        await update.message.reply_text("Por favor, envía una URL válida (https://...)")
        return
    await _procesar_url(update, url)


async def cmd_listar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    convocatorias = listar()
    pendientes = [c for c in convocatorias if c.estado == "pendiente"]
    if not pendientes:
        await update.message.reply_text("No hay convocatorias pendientes.")
        return
    lineas = []
    for c in pendientes[:15]:
        titulo = (c.titulo[:50] + "...") if len(c.titulo) > 50 else c.titulo
        lineas.append(f"• {c.id}: {titulo}\n  {c.url}")
    if len(pendientes) > 15:
        lineas.append(f"\n... y {len(pendientes) - 15} más")
    await update.message.reply_text("\n\n".join(lineas))


async def cmd_revisar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /revisar <id>")
        return
    id_buscar = context.args[0].strip()
    conv = buscar_por_id(id_buscar)
    if not conv:
        await update.message.reply_text(f"No se encontró convocatoria con id '{id_buscar}'")
        return
    conv.estado = "procesada"
    actualizar(conv)
    await update.message.reply_text(f"Convocatoria '{conv.titulo[:40]}...' marcada como procesada.")


async def _procesar_url(update: Update, url: str) -> None:
    """Añade una convocatoria desde URL, opcionalmente scrapeando."""
    msg = await update.message.reply_text("Procesando URL...")
    id_conv = _generar_id(url)

    # Comprobar si ya existe
    existente = buscar_por_id(id_conv)
    if existente:
        await msg.edit_text(f"Esta convocatoria ya está en la lista:\n{existente.titulo}")
        return

    # Intentar extraer datos
    datos = extraer(url)
    if datos:
        conv = Convocatoria(
            id=id_conv,
            url=url,
            titulo=datos.titulo or url,
            descripcion=datos.descripcion,
            plazo_fin=datos.plazo_fin,
            requisitos="",
            estado="pendiente",
            fecha_ingesta=datetime.now().isoformat(),
            fuente="telegram",
        )
    else:
        conv = Convocatoria(
            id=id_conv,
            url=url,
            titulo=url,
            descripcion="",
            plazo_fin="",
            requisitos="",
            estado="pendiente",
            fecha_ingesta=datetime.now().isoformat(),
            fuente="telegram",
        )

    añadir(conv)
    titulo_show = (conv.titulo[:60] + "...") if len(conv.titulo) > 60 else conv.titulo
    await msg.edit_text(f"Añadida: {titulo_show}\nID: {conv.id}")


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Si el mensaje contiene una URL, la procesa como nueva convocatoria."""
    texto = update.message.text or ""
    url = _extraer_url(texto)
    if url:
        await _procesar_url(update, url)
    else:
        await update.message.reply_text("Envía una URL o usa /ayuda para ver comandos.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja errores no capturados, incluyendo Conflict por múltiples instancias."""
    import logging

    if isinstance(context.error, Conflict):
        msg = (
            "\nConflict: Hay otra instancia del bot ejecutandose.\n"
            "   Deten todas las instancias (Ctrl+C en cada terminal) y ejecuta solo una.\n"
            "   O verifica si el token se usa en otro servidor/maquina."
        )
        sys.stderr.write(msg + "\n")
        sys.exit(1)
    logging.exception("Excepción no manejada mientras procesaba una actualización")


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN no configurado en .env")
        sys.exit(1)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("sube", cmd_añadir))
    app.add_handler(CommandHandler("listar", cmd_listar))
    app.add_handler(CommandHandler("revisar", cmd_revisar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_error_handler(error_handler)

    print("Bot iniciado. Pulsa Ctrl+C para detener.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
