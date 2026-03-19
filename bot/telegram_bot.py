"""
Bot Telegram que recibe URLs y comandos.
Comandos: /sube <url>, /idea <texto>, /listar, /list, /ver <id|num>, /revisar <id>,
          /func <texto> <prioridad> [estado], /listfunc,
          /tarea "titulo" [fecha] ["desc"], /listtareas, /ayuda.
URL enviada sin comando se interpreta como nueva convocatoria.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Añadir proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.error import Conflict

import config
from src.db import Convocatoria, añadir, buscar_por_id, listar, actualizar
from src.db_ideas import Idea, añadir_idea
from src.db_funcionalidad import (
    Funcionalidad,
    ESTADOS_VALIDOS,
    añadir as añadir_func,
    listar as listar_func,
    buscar_por_id as buscar_func_por_id,
    actualizar as actualizar_func,
)
from src.caldav_client import crear_tarea, listar_tareas, obtener_ultimo_error_tarea
from src.deck_client import crear_tarea_deck, obtener_ultimo_error_deck
from src.plazo import es_futura, clave_orden, parsear_plazo
from src.scraper import extraer

# Regex para detectar URLs
URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)

_WHISPER_MODEL = None


def _esta_autorizado(update: Update) -> bool:
    """Valida si el usuario está en la allowlist configurada."""
    # Si no hay allowlist, se considera abierto (modo debug).
    if not config.TELEGRAM_ALLOWLIST_USERNAMES and not config.TELEGRAM_ALLOWLIST_IDS:
        return True

    usuario = update.effective_user
    if not usuario:
        return False

    username = (usuario.username or "").strip().lower()
    user_id = int(usuario.id)
    if username and username in config.TELEGRAM_ALLOWLIST_USERNAMES:
        return True
    if user_id in config.TELEGRAM_ALLOWLIST_IDS:
        return True
    return False


async def _rechazar_no_autorizado(update: Update) -> None:
    msg = getattr(update, "message", None)
    if msg:
        await msg.reply_text("Este bot está restringido a un usuario autorizado.")


def _es_url(texto: str) -> bool:
    return bool(URL_PATTERN.match(texto.strip()))


def _extraer_url(texto: str) -> str | None:
    m = URL_PATTERN.search(texto)
    return m.group(0).strip() if m else None


def _generar_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _generar_id_idea(texto: str) -> str:
    base = f"{datetime.now().isoformat()}::{texto[:1000]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _resumen_simple(texto: str, max_len: int = 180) -> str:
    limpio = " ".join(texto.split())
    if not limpio:
        return "Idea sin contenido"
    return limpio[:max_len] + ("..." if len(limpio) > max_len else "")


def _normalizar_lista(valor: object) -> str:
    if isinstance(valor, list):
        return ", ".join(str(x).strip() for x in valor if str(x).strip())
    if isinstance(valor, str):
        return valor.strip()
    return ""


def _extraer_metadatos_idea(texto: str) -> dict:
    """
    Extrae metadatos de una idea usando Ollama.
    Siempre retorna claves: resumen, tags, categorias, presupuesto_aproximado.
    """
    defaults = {
        "resumen": _resumen_simple(texto),
        "tags": "",
        "categorias": "",
        "presupuesto_aproximado": "",
    }
    try:
        import requests
    except ImportError:
        return defaults

    prompt = f"""Analiza esta idea de proyecto y responde SOLO en JSON valido.

Campos requeridos:
- resumen: texto breve en espanol (maximo 220 caracteres)
- tags: array de strings cortos
- categorias: array de strings
- presupuesto_aproximado: texto (ej. "15000-20000 EUR") o vacio si no hay datos

Idea:
\"\"\"{texto[:5000]}\"\"\"
"""
    try:
        r = requests.post(
            f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=90,
        )
        if r.status_code != 200:
            return defaults
        raw = (r.json().get("response") or "").strip()
        inicio = raw.find("{")
        fin = raw.rfind("}")
        if inicio == -1 or fin == -1:
            return defaults
        payload = json.loads(raw[inicio:fin + 1])
        return {
            "resumen": str(payload.get("resumen") or defaults["resumen"]).strip(),
            "tags": _normalizar_lista(payload.get("tags")),
            "categorias": _normalizar_lista(payload.get("categorias")),
            "presupuesto_aproximado": str(payload.get("presupuesto_aproximado") or "").strip(),
        }
    except Exception:
        return defaults


def _guardar_idea(texto: str, fuente: str) -> Idea:
    idea_id = _generar_id_idea(texto)
    metadatos = _extraer_metadatos_idea(texto)

    config.CARPETA_IDEAS.mkdir(parents=True, exist_ok=True)
    ruta_abs = config.CARPETA_IDEAS / f"{idea_id}.md"
    try:
        ruta_rel = ruta_abs.relative_to(config.DIR_PROYECTO).as_posix()
    except Exception:
        ruta_rel = str(ruta_abs)
    ruta_abs.write_text(texto.strip() + "\n", encoding="utf-8")

    idea = Idea(
        id=idea_id,
        resumen=metadatos["resumen"] or _resumen_simple(texto),
        tags=metadatos["tags"],
        categorias=metadatos["categorias"],
        presupuesto_aproximado=metadatos["presupuesto_aproximado"],
        ruta=ruta_rel.replace("\\", "/"),
        fecha_ingesta=datetime.now().isoformat(),
        fuente=fuente,
    )
    añadir_idea(idea)
    return idea


def _transcribir_audio(ruta_audio: Path) -> str:
    global _WHISPER_MODEL
    modelo = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    try:
        import whisper
    except Exception as exc:
        raise RuntimeError("No se pudo importar whisper. Instala openai-whisper y ffmpeg.") from exc

    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = whisper.load_model(modelo)

    resultado = _WHISPER_MODEL.transcribe(str(ruta_audio), language="es")
    texto = (resultado.get("text") or "").strip()
    if not texto:
        raise RuntimeError("No se pudo extraer texto del audio.")
    return texto


_ACCIONES_AUDIO = {"idea", "funcionalidad", "tarea"}


def _parsear_accion_audio(texto: str) -> tuple[str | None, str]:
    """Extrae la acción (primera palabra) y el contenido restante de una transcripción.

    Retorna (accion, contenido). Si la primera palabra no es una acción
    reconocida, retorna (None, texto_original_completo).
    """
    normalizado = " ".join(texto.split())
    if not normalizado:
        return None, ""
    partes = normalizado.split(None, 1)
    candidato = re.sub(r"[,.:;!?]+$", "", partes[0]).lower()
    if candidato in _ACCIONES_AUDIO:
        contenido = partes[1].strip() if len(partes) > 1 else ""
        return candidato, contenido
    return None, normalizado


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/sube <url> - Sube una convocatoria por URL\n"
        "/idea <texto> - Guarda una idea en data/ideas y data/ideas.csv\n"
        "/func <texto> <prioridad 1-5> [estado] - Registra una funcionalidad pendiente\n"
        "/listfunc - Lista funcionalidades ordenadas por prioridad\n"
        '/tarea "Titulo" [YYYY-MM-DD] ["Descripcion"] - Crea tarea en Nextcloud\n'
        "/listtareas - Lista tareas de Nextcloud por prioridad\n"
        "/listar o /list - Lista convocatorias futuras por proximidad\n"
        "/ver <id o numero> - Ver toda la info de una convocatoria\n"
        "/revisar <id> - Marca una convocatoria como procesada\n"
        "/ayuda - Muestra esta ayuda\n\n"
        "Tambien puedes enviar una URL directamente para subirla.\n\n"
        "Audio: la primera palabra determina la accion:\n"
        "  idea <descripcion> - Guarda una idea\n"
        "  funcionalidad <descripcion> - Registra funcionalidad (P3, pendiente)\n"
        "  tarea <descripcion> - Crea tarea en Nextcloud\n"
        "  Si no se reconoce accion, se guarda como idea."
    )


async def cmd_añadir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /sube <url>")
        return
    url = " ".join(context.args).strip()
    if not _es_url(url):
        await update.message.reply_text("Por favor, envía una URL válida (https://...)")
        return
    await _procesar_url(update, url)


def _obtener_futuras_ordenadas() -> list[Convocatoria]:
    """Filtra convocatorias pendientes futuras y las ordena por proximidad."""
    pendientes = [c for c in listar() if c.estado == "pendiente"]
    futuras = [c for c in pendientes if es_futura(c.plazo_fin)]
    futuras.sort(key=lambda c: clave_orden(c.plazo_fin))
    return futuras


def _formato_plazo(plazo_fin: str) -> str:
    fecha = parsear_plazo(plazo_fin)
    if fecha:
        return fecha.strftime("%d/%m/%Y")
    return plazo_fin.strip() if plazo_fin.strip() else "Sin fecha"


async def cmd_listar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    futuras = _obtener_futuras_ordenadas()

    if not futuras:
        total_pendientes = sum(1 for c in listar() if c.estado == "pendiente")
        if total_pendientes:
            await update.message.reply_text(
                f"No hay convocatorias futuras.\n"
                f"Hay {total_pendientes} convocatorias con plazo pasado."
            )
        else:
            await update.message.reply_text("No hay convocatorias pendientes.")
        return

    cabecera = f"Hay {len(futuras)} convocatoria(s) futura(s):\n\n"
    lineas: list[str] = []
    for i, c in enumerate(futuras, 1):
        titulo = (c.titulo[:55] + "...") if len(c.titulo) > 55 else c.titulo
        plazo = _formato_plazo(c.plazo_fin)
        lineas.append(f"{i}. [{plazo}] {titulo}\n   /ver {c.id}")

    texto_completo = cabecera + "\n\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await update.message.reply_text(texto_completo)
    else:
        partes: list[str] = [cabecera]
        bloque_actual = ""
        for linea in lineas:
            if len(partes[-1]) + len(bloque_actual) + len(linea) + 2 > MAX_MSG:
                partes[-1] += bloque_actual
                partes.append("")
                bloque_actual = ""
            bloque_actual += linea + "\n\n"
        partes[-1] += bloque_actual
        for parte in partes:
            if parte.strip():
                await update.message.reply_text(parte.strip())


def _formatear_convocatoria(conv: Convocatoria) -> str:
    """Formatea todos los campos de una convocatoria para mostrar al usuario."""
    plazo = conv.plazo_fin.strip() if conv.plazo_fin.strip() else "No disponible"
    requisitos = conv.requisitos.strip() if conv.requisitos.strip() else "No especificados"

    descripcion = conv.descripcion.strip()
    if len(descripcion) > 1500:
        descripcion = descripcion[:1500] + "... (recortado)"
    if not descripcion:
        descripcion = "No disponible"

    return (
        f"Titulo: {conv.titulo}\n\n"
        f"URL: {conv.url}\n\n"
        f"Plazo: {plazo}\n\n"
        f"Requisitos: {requisitos}\n\n"
        f"Descripcion:\n{descripcion}\n\n"
        f"(Estado: {conv.estado} | Fuente: {conv.fuente} | Ingesta: {conv.fecha_ingesta})"
    )


async def cmd_ver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /ver <id o numero>\nEjemplo: /ver 3  o  /ver c4ececba4acfc373")
        return

    argumento = context.args[0].strip()
    conv: Convocatoria | None = None

    if argumento.isdigit():
        indice = int(argumento)
        futuras = _obtener_futuras_ordenadas()
        if 1 <= indice <= len(futuras):
            conv = futuras[indice - 1]
        else:
            await update.message.reply_text(
                f"Numero fuera de rango. Hay {len(futuras)} convocatoria(s) futura(s).\n"
                f"Usa /listar para verlas."
            )
            return
    else:
        conv = buscar_por_id(argumento)

    if not conv:
        await update.message.reply_text(
            f"No se encontro convocatoria con id '{argumento}'.\n"
            f"Usa /listar para ver las disponibles."
        )
        return

    texto = _formatear_convocatoria(conv)
    MAX_MSG = 4000
    if len(texto) <= MAX_MSG:
        await update.message.reply_text(texto)
    else:
        await update.message.reply_text(texto[:MAX_MSG])
        await update.message.reply_text(texto[MAX_MSG:])


async def cmd_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /idea <descripcion>\n"
            "Ejemplo: /idea laboratorio artistico itinerante con impacto rural"
        )
        return
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("La idea no puede estar vacia.")
        return

    msg = await update.message.reply_text("Guardando idea...")
    idea = _guardar_idea(texto, fuente="telegram_texto")
    await msg.edit_text(
        f"Idea guardada.\n"
        f"ID: {idea.id}\n"
        f"Resumen: {idea.resumen}\n"
        f"Ruta: {idea.ruta}"
    )


def _generar_id_func(texto: str) -> str:
    base = f"{datetime.now().isoformat()}::func::{texto[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


_PRIORIDAD_EMOJI = {1: "⬜", 2: "🟦", 3: "🟨", 4: "🟧", 5: "🟥"}


async def cmd_func(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    if not context.args:
        await update.message.reply_text(
            "Uso: /func <texto> <prioridad 1-5> [estado]\n"
            "Ejemplo: /func mejorar parser del scraper 4 pendiente\n\n"
            "Estados validos: pendiente, en_progreso, hecha\n"
            "Si no indicas estado, se asume 'pendiente'.\n"
            "La prioridad (1-5) debe ser el penultimo o ultimo argumento numerico."
        )
        return

    args = list(context.args)
    estado = "pendiente"
    prioridad: int | None = None

    if args[-1].lower() in ESTADOS_VALIDOS:
        estado = args.pop().lower()

    if args and args[-1].isdigit():
        val = int(args.pop())
        if 1 <= val <= 5:
            prioridad = val
        else:
            await update.message.reply_text("La prioridad debe estar entre 1 y 5.")
            return

    if prioridad is None:
        await update.message.reply_text(
            "Falta la prioridad (1-5).\n"
            "Uso: /func <texto> <prioridad> [estado]"
        )
        return

    texto = " ".join(args).strip()
    if not texto:
        await update.message.reply_text("El texto de la funcionalidad no puede estar vacio.")
        return

    func = Funcionalidad(
        id=_generar_id_func(texto),
        texto=texto,
        prioridad=prioridad,
        estado=estado,
        fecha_ingesta=datetime.now().isoformat(),
        fuente="telegram",
    )
    añadir_func(func)

    emoji = _PRIORIDAD_EMOJI.get(prioridad, "")
    await update.message.reply_text(
        f"Funcionalidad guardada.\n"
        f"ID: {func.id}\n"
        f"Texto: {func.texto}\n"
        f"Prioridad: {emoji} {func.prioridad}/5\n"
        f"Estado: {func.estado}"
    )


async def cmd_listfunc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    todas = listar_func()
    if not todas:
        await update.message.reply_text("No hay funcionalidades registradas.")
        return

    todas.sort(key=lambda f: (-f.prioridad, f.estado != "pendiente"))

    lineas: list[str] = []
    for i, f in enumerate(todas, 1):
        emoji = _PRIORIDAD_EMOJI.get(f.prioridad, "")
        estado_tag = f"[{f.estado}]"
        txt = (f.texto[:60] + "...") if len(f.texto) > 60 else f.texto
        lineas.append(f"{i}. {emoji} P{f.prioridad} {estado_tag} {txt}")

    cabecera = f"Funcionalidades ({len(todas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


def _parsear_args_tarea(texto_raw: str) -> tuple[str, str | None, str]:
    """Parsea: "Titulo" [YYYY-MM-DD] ["Descripcion"]

    Sin comillas, todo el texto (excepto una posible fecha) se trata como titulo.
    """
    texto = texto_raw.strip()
    if not texto:
        return "", None, ""

    fecha = None
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", texto)
    if date_match:
        fecha = date_match.group(1)
        texto = (texto[:date_match.start()] + texto[date_match.end():]).strip()

    partes_quoted = re.findall(r'"([^"]*)"', texto)

    if partes_quoted:
        titulo = partes_quoted[0]
        descripcion = partes_quoted[1] if len(partes_quoted) > 1 else ""
    else:
        titulo = texto
        descripcion = ""

    return titulo.strip(), fecha, descripcion.strip()


async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/tarea"):
        texto_raw = texto_raw[len("/tarea"):].strip()

    if not texto_raw:
        await update.message.reply_text(
            'Uso: /tarea "Titulo" [YYYY-MM-DD] ["Descripcion"]\n'
            'Ejemplo: /tarea "Comprar material" 2026-03-25 "Para laboratorio"\n'
            "La fecha y descripcion son opcionales."
        )
        return

    titulo, fecha, descripcion = _parsear_args_tarea(texto_raw)

    if not titulo:
        await update.message.reply_text("El titulo de la tarea no puede estar vacio.")
        return

    if fecha:
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                f"Fecha invalida: {fecha}\nUsa formato YYYY-MM-DD (ej. 2026-03-25)"
            )
            return

    msg = await update.message.reply_text("Creando tarea en Nextcloud...")
    ok = crear_tarea(titulo, descripcion=descripcion, fecha_due=fecha)

    if ok:
        partes = [f"Tarea creada: {titulo}"]
        if fecha:
            partes.append(f"Fecha: {fecha}")
        if descripcion:
            partes.append(f"Descripcion: {descripcion}")
        await msg.edit_text("\n".join(partes))
    else:
        caldav_error = obtener_ultimo_error_tarea()
        ok_deck = crear_tarea_deck(titulo, descripcion=descripcion, fecha_due=fecha)
        if ok_deck:
            await msg.edit_text(
                f"Tarea creada en Deck ({config.DECK_BOARD_NAME}).\n"
                f"Titulo: {titulo}"
            )
            return

        deck_error = obtener_ultimo_error_deck()
        await msg.edit_text(
            "No se pudo crear la tarea.\n"
            f"CalDAV: {caldav_error or 'sin detalle'}\n"
            f"Deck: {deck_error or 'sin detalle'}"
        )


_TAREA_PRI_EMOJI = {1: "\U0001f534", 2: "\U0001f534", 3: "\U0001f7e0", 4: "\U0001f7e0",
                    5: "\U0001f7e1", 6: "\U0001f7e2", 7: "\U0001f535", 8: "\U0001f535", 9: "\u26aa"}


async def cmd_listtareas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    msg = await update.message.reply_text("Consultando tareas...")

    try:
        tareas = listar_tareas()
    except Exception as exc:
        await msg.edit_text(f"Error al consultar tareas: {exc}")
        return

    if not tareas:
        await msg.edit_text("No hay tareas pendientes.")
        return

    tareas.sort(key=lambda t: (t["priority"] == 0, t["priority"], t["due"] or "9999-99-99"))

    lineas: list[str] = []
    for i, t in enumerate(tareas, 1):
        emoji = _TAREA_PRI_EMOJI.get(t["priority"], "\u2b1c")
        fecha = f" [{t['due']}]" if t["due"] else ""
        titulo = (t["summary"][:60] + "...") if len(t["summary"]) > 60 else t["summary"]
        lineas.append(f"{i}. {emoji}{fecha} {titulo}")

    cabecera = f"Tareas ({len(tareas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await msg.edit_text(texto_completo)
    else:
        await msg.edit_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


async def cmd_revisar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
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
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    texto = update.message.text or ""
    url = _extraer_url(texto)
    if url:
        await _procesar_url(update, url)
    else:
        await update.message.reply_text("Envía una URL o usa /ayuda para ver comandos.")


async def manejar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe audio y enruta según la primera palabra (idea/funcionalidad/fallback)."""
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    mensaje = update.message
    if not mensaje:
        return

    archivo = None
    sufijo = ".ogg"
    if mensaje.voice:
        archivo = await context.bot.get_file(mensaje.voice.file_id)
        sufijo = ".ogg"
    elif mensaje.audio:
        archivo = await context.bot.get_file(mensaje.audio.file_id)
        mime = (mensaje.audio.mime_type or "").lower()
        if "mpeg" in mime or "mp3" in mime:
            sufijo = ".mp3"
        elif "wav" in mime:
            sufijo = ".wav"
        else:
            sufijo = ".m4a"

    if archivo is None:
        await mensaje.reply_text("No he podido leer el audio recibido.")
        return

    estado = await mensaje.reply_text("Procesando audio y transcribiendo...")
    ruta_tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
            ruta_tmp = Path(tmp.name)
        await archivo.download_to_drive(custom_path=str(ruta_tmp))

        texto = _transcribir_audio(ruta_tmp)
        accion, contenido = _parsear_accion_audio(texto)

        if accion == "idea":
            if not contenido:
                await estado.edit_text("La idea no puede estar vacia. Di: idea <descripcion>")
                return
            idea = _guardar_idea(contenido, fuente="telegram_audio")
            await estado.edit_text(
                f"Idea guardada desde audio.\n"
                f"ID: {idea.id}\n"
                f"Resumen: {idea.resumen}\n"
                f"Ruta: {idea.ruta}"
            )

        elif accion == "funcionalidad":
            if not contenido:
                await estado.edit_text(
                    "La funcionalidad no puede estar vacia. Di: funcionalidad <descripcion>"
                )
                return
            func = Funcionalidad(
                id=_generar_id_func(contenido),
                texto=contenido,
                prioridad=3,
                estado="pendiente",
                fecha_ingesta=datetime.now().isoformat(),
                fuente="telegram_audio",
            )
            añadir_func(func)
            emoji = _PRIORIDAD_EMOJI.get(func.prioridad, "")
            await estado.edit_text(
                f"Funcionalidad guardada desde audio.\n"
                f"ID: {func.id}\n"
                f"Texto: {func.texto}\n"
                f"Prioridad: {emoji} {func.prioridad}/5\n"
                f"Estado: {func.estado}"
            )

        elif accion == "tarea":
            if not contenido:
                await estado.edit_text(
                    "La tarea no puede estar vacia. Di: tarea <descripcion>"
                )
                return
            ok = crear_tarea(contenido)
            if ok:
                await estado.edit_text(
                    f"Tarea creada desde audio.\n"
                    f"Titulo: {contenido}"
                )
            else:
                caldav_error = obtener_ultimo_error_tarea()
                ok_deck = crear_tarea_deck(contenido)
                if ok_deck:
                    await estado.edit_text(
                        f"Tarea creada en Deck ({config.DECK_BOARD_NAME}) desde audio.\n"
                        f"Titulo: {contenido}"
                    )
                else:
                    deck_error = obtener_ultimo_error_deck()
                    await estado.edit_text(
                        "No se pudo crear la tarea desde audio.\n"
                        f"CalDAV: {caldav_error or 'sin detalle'}\n"
                        f"Deck: {deck_error or 'sin detalle'}"
                    )

        else:
            idea = _guardar_idea(contenido, fuente="telegram_audio")
            await estado.edit_text(
                f"Idea guardada desde audio (sin accion detectada).\n"
                f"ID: {idea.id}\n"
                f"Resumen: {idea.resumen}\n"
                f"Ruta: {idea.ruta}"
            )

    except Exception as exc:
        await estado.edit_text(f"No se pudo procesar el audio: {exc}")
    finally:
        if ruta_tmp and ruta_tmp.exists():
            try:
                ruta_tmp.unlink()
            except Exception:
                pass


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
    app.add_handler(CommandHandler("idea", cmd_idea))
    app.add_handler(CommandHandler("listar", cmd_listar))
    app.add_handler(CommandHandler("list", cmd_listar))
    app.add_handler(CommandHandler("ver", cmd_ver))
    app.add_handler(CommandHandler("func", cmd_func))
    app.add_handler(CommandHandler("listfunc", cmd_listfunc))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("listtareas", cmd_listtareas))
    app.add_handler(CommandHandler("revisar", cmd_revisar))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, manejar_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_error_handler(error_handler)

    print("Bot iniciado. Pulsa Ctrl+C para detener.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
