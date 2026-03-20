"""
Bot Telegram que recibe URLs y comandos.
Comandos: /sube <url>, /idea <texto>, /listar, /list, /ver <id|num>, /revisar <id>,
          /func <texto> [prioridad] [estado], /listfunc, /listfuncionalidades,
          /tarea, /comprar, /huevos, /listhuevos,
          /evento <nombre> <fecha> [hora], /listevento [+ | ++], /listtareas,
          /rmfunc, /rmtarea, /rmevento <numero> (tras el listado correspondiente), /ayuda.
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
    eliminar as eliminar_func_db,
)
from src.caldav_client import (
    borrar_evento_por_url,
    crear_evento,
    listar_eventos_proximos_dias,
    obtener_ultimo_error_evento,
)
from src.deck_client import (
    borrar_tarjeta_deck,
    crear_tarea_deck,
    listar_tareas_deck,
    obtener_ultimo_error_deck,
)
from src.db_huevos import añadir as añadir_huevo, resumen_ultimos_dias_desde_hoy
from src.plazo import es_futura, clave_orden, parsear_plazo
from src.scraper import extraer

# Regex para detectar URLs
URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)

_WHISPER_MODEL = None

# Stack Deck para lista de compras (nombre exacto en Nextcloud Deck)
DECK_STACK_COMPRAR = "Comprar"

# context.chat_data: caché del último listado para /rm* (mismo chat)
CACHE_RM_FUNC_IDS = "rm_func_ids"
CACHE_RM_TAREAS_DECK = "rm_tareas_deck"
CACHE_RM_EVENTOS = "rm_evento_urls"

# Resumen de texto en /listfunc y /listfuncionalidades (60 + 20 caracteres)
FUNC_RESUMEN_MAX = 80


def _dias_ventana_eventos(args: list[str]) -> int:
    """7 días por defecto; + -> 14; ++ -> 21."""
    if not args:
        return 7
    if any((a or "").strip() == "++" for a in args):
        return 21
    if any((a or "").strip() == "+" for a in args):
        return 14
    return 7


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


_ACCIONES_AUDIO = {"idea", "funcionalidad", "tarea", "evento", "comprar"}


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
        "/func <texto> [prioridad 1-5] [estado] - Funcionalidad (prioridad 3 por defecto)\n"
        "/listfunc o /listfuncionalidades - Lista funcionalidades ordenadas por prioridad\n"
        "/rmfunc <numero> - Borra la funcionalidad N del ultimo listado\n"
        '/tarea "Titulo" [fecha] ["Descripcion"] - Tarjeta en Nextcloud Deck (columna por defecto)\n'
        f'/comprar "Titulo" [fecha] ["Descripcion"] - Igual que /tarea en columna "{DECK_STACK_COMPRAR}"\n'
        "/huevos <cantidad> - Registra huevos del dia en data/huevos.csv\n"
        "/listhuevos [dias] - Resumen por dia (6 dias por defecto, desde hoy hacia atras)\n"
        "/evento <nombre> <fecha> [HH:MM] - Evento en CalDAV "
        "(fecha española: DD-MM-AAAA, DD-MM, DD; hora opcional, 1 h duracion)\n"
        "/listevento - Proximos 7 dias; /listevento + -> 14 dias; /listevento ++ -> 21 dias\n"
        "/rmevento <numero> - Borra el evento N del ultimo /listevento\n"
        "/listtareas - Lista tarjetas pendientes en Nextcloud Deck (fecha mas proxima primero)\n"
        "/rmtarea <numero> - Borra la tarea N del ultimo /listtareas\n"
        "/listar o /list - Lista convocatorias futuras por proximidad\n"
        "/ver <id o numero> - Ver toda la info de una convocatoria\n"
        "/revisar <id> - Marca una convocatoria como procesada\n"
        "/ayuda - Muestra esta ayuda\n\n"
        "Fechas (tarea/evento): formato español DD-MM-AAAA; DD-MM = año actual; "
        "solo DD = mes y año actuales. Tambien se acepta YYYY-MM-DD en tareas.\n\n"
        "Tambien puedes enviar una URL directamente para subirla.\n\n"
        "Audio: la primera palabra determina la accion:\n"
        "  idea <descripcion> - Guarda una idea\n"
        "  funcionalidad <descripcion> [prioridad 1-5] - Registra funcionalidad\n"
        "  tarea <titulo> [fecha] - Crea tarjeta en Deck\n"
        f'  comprar <titulo> [fecha] - Tarjeta en columna "{DECK_STACK_COMPRAR}"\n'
        "  evento <nombre> <fecha> [HH:MM] - Crea evento en calendario\n"
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


def _parsear_funcionalidad_audio(contenido: str) -> tuple[str, int]:
    """
    Separa texto y prioridad opcional al final (1-5): '... prioridad 4' o '... 4'.
    Por defecto prioridad 3.
    """
    texto = " ".join(contenido.split()).strip()
    prioridad = 3
    if not texto:
        return "", prioridad

    m = re.search(r"\bprioridad\s+([1-5])\s*$", texto, re.IGNORECASE)
    if m:
        texto = texto[: m.start()].strip()
        prioridad = int(m.group(1))
    else:
        m2 = re.search(r"\s+([1-5])\s*$", texto)
        if m2:
            texto = texto[: m2.start()].strip()
            prioridad = int(m2.group(1))

    return texto.strip(), prioridad


async def cmd_func(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    if not context.args:
        await update.message.reply_text(
            "Uso: /func <texto> [prioridad 1-5] [estado]\n"
            "Ejemplo: /func mejorar parser del scraper 4 pendiente\n"
            "Sin prioridad se usa 3 por defecto.\n\n"
            "Estados validos: pendiente, en_progreso, hecha\n"
            "Si no indicas estado, se asume 'pendiente'.\n"
            "La prioridad (1-5), si la pones, suele ser el ultimo numero."
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
        prioridad = 3

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

    if context.chat_data is not None:
        context.chat_data[CACHE_RM_FUNC_IDS] = [f.id for f in todas]

    lineas: list[str] = []
    for i, f in enumerate(todas, 1):
        emoji = _PRIORIDAD_EMOJI.get(f.prioridad, "")
        estado_tag = f"[{f.estado}]"
        txt = (
            (f.texto[:FUNC_RESUMEN_MAX] + "...")
            if len(f.texto) > FUNC_RESUMEN_MAX
            else f.texto
        )
        lineas.append(f"{i}. {emoji} P{f.prioridad} {estado_tag} {txt}")

    cabecera = f"Funcionalidades ({len(todas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


def _fecha_evento_ddmmyyyy_a_iso(fecha_dd_mm_yyyy: str) -> str | None:
    """Valida DD-MM-YYYY y devuelve YYYY-MM-DD para CalDAV; None si la fecha no es valida."""
    try:
        d = datetime.strptime(fecha_dd_mm_yyyy.strip(), "%d-%m-%Y")
        return d.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _extraer_fecha_iso_y_resto(texto: str) -> tuple[str | None, str]:
    """
    Extrae una fecha y devuelve (YYYY-MM-DD, texto_sin_fecha).
    Prioridad: formato español día-mes-año (ver _extraer_fecha_formato_espanol);
    si no hay, acepta legado YYYY-MM-DD.
    """
    texto = texto.strip()
    if not texto:
        return None, texto

    fecha_dmY, resto = _extraer_fecha_formato_espanol(texto)
    if fecha_dmY:
        iso = _fecha_evento_ddmmyyyy_a_iso(fecha_dmY)
        if iso:
            return iso, resto

    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", texto)
    if m:
        iso = m.group(1)
        try:
            datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            return None, texto
        resto = (texto[: m.start()] + texto[m.end() :]).strip()
        return iso, resto

    return None, texto


def _anio_evento_dos_cifras(y: int) -> int:
    """26 -> 2026; 99 -> 2099."""
    if 0 <= y < 100:
        return 2000 + y
    return y


def _extraer_fecha_formato_espanol(texto: str) -> tuple[str | None, str]:
    """
    Formato español día-mes-año: devuelve fecha normalizada DD-MM-YYYY y el texto sin ese fragmento.
    - DD-MM-YYYY o DD/MM/YYYY (año 2 cifras -> 20YY)
    - DD-MM o DD/MM sin año -> año actual
    - Solo DD (1-31) si hay un único candidato en el texto -> mes y año actuales
    Separadores / o -.
    """
    now = datetime.now()
    sep = r"[/-]"

    m = re.search(
        rf"\b(\d{{1,2}}){sep}(\d{{1,2}}){sep}(\d{{2}}|\d{{4}})\b",
        texto,
    )
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = _anio_evento_dos_cifras(y)
        try:
            datetime(y, mo, d)
        except ValueError:
            return None, texto
        fecha = f"{d:02d}-{mo:02d}-{y}"
        resto = (texto[: m.start()] + texto[m.end() :]).strip()
        return fecha, resto

    m = re.search(rf"\b(\d{{1,2}}){sep}(\d{{1,2}})\b", texto)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = now.year
        try:
            datetime(y, mo, d)
        except ValueError:
            return None, texto
        fecha = f"{d:02d}-{mo:02d}-{y}"
        resto = (texto[: m.start()] + texto[m.end() :]).strip()
        return fecha, resto

    cands = [
        m
        for m in re.finditer(r"\b(\d{1,2})\b", texto)
        if 1 <= int(m.group(1)) <= 31
    ]
    if len(cands) == 1:
        d = int(cands[0].group(1))
        try:
            datetime(now.year, now.month, d)
        except ValueError:
            return None, texto
        fecha = f"{d:02d}-{now.month:02d}-{now.year}"
        m0 = cands[0]
        resto = (texto[: m0.start()] + texto[m0.end() :]).strip()
        return fecha, resto

    return None, texto


# Alias retrocompatible
def _extraer_fecha_evento_flexible(texto: str) -> tuple[str | None, str]:
    return _extraer_fecha_formato_espanol(texto)


def _parsear_args_tarea(texto_raw: str) -> tuple[str, str | None, str]:
    """Parsea: \"Titulo\" [fecha DD-MM-AAAA, DD-MM, DD o legado YYYY-MM-DD] [\"Descripcion\"].

    Sin comillas, todo el texto (excepto una posible fecha) se trata como titulo.
    """
    texto = texto_raw.strip()
    if not texto:
        return "", None, ""

    fecha, texto = _extraer_fecha_iso_y_resto(texto)

    partes_quoted = re.findall(r'"([^"]*)"', texto)

    if partes_quoted:
        titulo = partes_quoted[0]
        descripcion = partes_quoted[1] if len(partes_quoted) > 1 else ""
    else:
        titulo = texto
        descripcion = ""

    return titulo.strip(), fecha, descripcion.strip()


def _parsear_args_evento(texto_raw: str) -> tuple[str, str | None, str | None]:
    """Parsea nombre del evento, fecha flexible (DD/MM/YY, etc.) y hora opcional HH:MM."""
    texto = texto_raw.strip()
    if not texto:
        return "", None, None

    time_match = re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", texto)
    if time_match:
        hora = time_match.group(0)
        texto_sin_hora = (texto[: time_match.start()] + texto[time_match.end() :]).strip()
    else:
        hora = None
        texto_sin_hora = texto

    fecha, titulo_raw = _extraer_fecha_formato_espanol(texto_sin_hora)

    partes_quoted = re.findall(r'"([^"]*)"', titulo_raw)
    if partes_quoted:
        titulo = partes_quoted[0]
    else:
        titulo = titulo_raw

    return titulo.strip(), fecha, hora


async def _ejecutar_creacion_tarea_deck(
    update: Update,
    texto_raw: str,
    *,
    stack_name: str | None = None,
    prefijo_exito: str = "Tarea creada",
) -> None:
    titulo, fecha, descripcion = _parsear_args_tarea(texto_raw)
    if not titulo:
        await update.message.reply_text("El titulo de la tarea no puede estar vacio.")
        return

    if fecha:
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                f"Fecha invalida: {fecha}\n"
                "Usa DD-MM-AAAA, DD-MM, solo DD (mes actual) o YYYY-MM-DD."
            )
            return

    msg = await update.message.reply_text("Creando tarea en Deck...")
    ok = crear_tarea_deck(
        titulo,
        descripcion=descripcion,
        fecha_due=fecha,
        stack_name=stack_name,
    )

    if ok:
        stack_info = f" [{stack_name}]" if stack_name else ""
        partes = [
            f"{prefijo_exito} en Deck ({config.DECK_BOARD_NAME}){stack_info}: {titulo}"
        ]
        if fecha:
            partes.append(f"Fecha limite: {fecha}")
        if descripcion:
            partes.append(f"Descripcion: {descripcion}")
        await msg.edit_text("\n".join(partes))
    else:
        deck_error = obtener_ultimo_error_deck()
        await msg.edit_text(
            "No se pudo crear la tarea en Deck.\n"
            f"{deck_error or 'sin detalle'}"
        )


async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/tarea"):
        texto_raw = texto_raw[len("/tarea") :].strip()

    if not texto_raw:
        await update.message.reply_text(
            'Uso: /tarea "Titulo" [DD-MM-AAAA | DD-MM | DD | YYYY-MM-DD] ["Descripcion"]\n'
            'Ejemplo: /tarea "Comprar material" 25-03-2026 "Para laboratorio"\n'
            "Formato español: dia-mes-año; sin año = año actual; solo dia = mes actual.\n"
            "La fecha y descripcion son opcionales."
        )
        return

    await _ejecutar_creacion_tarea_deck(
        update,
        texto_raw,
        stack_name=None,
        prefijo_exito="Tarea creada",
    )


async def cmd_comprar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/comprar"):
        texto_raw = texto_raw[len("/comprar") :].strip()

    if not texto_raw:
        await update.message.reply_text(
            f'Uso: /comprar "Titulo" [fecha] ["Descripcion"] — igual que /tarea pero en la '
            f'columna "{DECK_STACK_COMPRAR}".\n'
            "Fecha: DD-MM-AAAA, DD-MM, DD o YYYY-MM-DD (opcional)."
        )
        return

    await _ejecutar_creacion_tarea_deck(
        update,
        texto_raw,
        stack_name=DECK_STACK_COMPRAR,
        prefijo_exito="Compra anotada",
    )


async def cmd_evento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/evento"):
        texto_raw = texto_raw[len("/evento") :].strip()

    if not texto_raw:
        await update.message.reply_text(
            "Uso: /evento <nombre> <fecha> [HH:MM]\n"
            "Fecha (español, dia-mes): DD-MM-AAAA o DD/MM/AAAA; año 2 cifras -> 20YY; "
            "DD-MM sin año = año actual; solo DD (1-31, unico en el texto) = mes y año actuales.\n"
            "Separadores / o -. Ejemplo: /evento Reunion 20-03-26 14:30"
        )
        return

    nombre, fecha_ev, hora_ev = _parsear_args_evento(texto_raw)

    if not nombre:
        await update.message.reply_text("El nombre del evento no puede estar vacio.")
        return
    if not fecha_ev:
        await update.message.reply_text(
            "Falta una fecha reconocible (ej. 20-03-2026, 20-03, 20/3/26, o solo el dia 15 si es el unico numero 1-31)."
        )
        return

    fecha_iso = _fecha_evento_ddmmyyyy_a_iso(fecha_ev)
    if fecha_iso is None:
        await update.message.reply_text(
            f"Fecha invalida: {fecha_ev}\n"
            "Usa dia-mes-año con / o -; año de 2 cifras; sin año = año actual; "
            "un solo numero 1-31 = dia en el mes actual."
        )
        return

    if hora_ev:
        try:
            datetime.strptime(hora_ev, "%H:%M")
        except ValueError:
            await update.message.reply_text(
                f"Hora invalida: {hora_ev}\nUsa formato HH:MM en 24 h (ej. 14:30)"
            )
            return

    msg = await update.message.reply_text("Creando evento en el calendario...")
    ok = crear_evento(nombre, fecha_iso, hora=hora_ev)

    if ok:
        partes = [f"Evento creado: {nombre}", f"Fecha: {fecha_ev}"]
        if hora_ev:
            partes.append(f"Hora inicio: {hora_ev} (duracion 1 h)")
        await msg.edit_text("\n".join(partes))
    else:
        err = obtener_ultimo_error_evento()
        await msg.edit_text(
            "No se pudo crear el evento en CalDAV.\n" + (err or "sin detalle")
        )


async def cmd_listevento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    dias = _dias_ventana_eventos(list(context.args or []))
    msg = await update.message.reply_text("Consultando eventos en CalDAV...")

    eventos = listar_eventos_proximos_dias(dias)
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_EVENTOS] = [str(e.get("url") or "") for e in eventos]

    if not eventos:
        err = obtener_ultimo_error_evento()
        extra = f"\n\nDetalle: {err}" if err else ""
        await msg.edit_text(
            f"No hay eventos en los proximos {dias} dias (desde hoy).{extra}"
        )
        return

    lineas: list[str] = []
    for i, ev in enumerate(eventos, 1):
        tit = ev["summary"][:70] + "..." if len(ev["summary"]) > 70 else ev["summary"]
        lineas.append(f"{i}. [{ev['start_iso']}] {tit}")

    cabecera = f"Eventos proximos {dias} dias ({len(eventos)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await msg.edit_text(texto_completo)
    else:
        await msg.edit_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


async def cmd_rmevento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /rmevento <numero>\n"
            "El numero es el de la ultima lista de /listevento en este chat."
        )
        return
    try:
        n = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("El numero debe ser un entero (ej. 1).")
        return

    cache = (context.chat_data or {}).get(CACHE_RM_EVENTOS) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text(
            "Indice invalido o lista antigua. Ejecuta /listevento primero en este chat."
        )
        return

    url = (cache[n - 1] or "").strip()
    if not url:
        await update.message.reply_text(
            "No hay URL CalDAV para ese evento; no se puede borrar desde el bot."
        )
        return

    ok = borrar_evento_por_url(url)
    if ok:
        if context.chat_data is not None:
            context.chat_data.pop(CACHE_RM_EVENTOS, None)
        await update.message.reply_text(f"Evento {n} eliminado del calendario.")
    else:
        err = obtener_ultimo_error_evento()
        await update.message.reply_text(
            "No se pudo borrar el evento.\n" + (err or "sin detalle")
        )


async def cmd_rmfunc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /rmfunc <numero>\n"
            "El numero es el de /listfunc o /listfuncionalidades en este chat."
        )
        return
    try:
        n = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("El numero debe ser un entero (ej. 1).")
        return

    cache = (context.chat_data or {}).get(CACHE_RM_FUNC_IDS) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text(
            "Indice invalido o lista antigua. Ejecuta /listfunc primero en este chat."
        )
        return

    fid = cache[n - 1]
    if eliminar_func_db(fid):
        if context.chat_data is not None:
            context.chat_data.pop(CACHE_RM_FUNC_IDS, None)
        await update.message.reply_text(f"Funcionalidad {n} eliminada (id {fid}).")
    else:
        await update.message.reply_text(
            "No se pudo eliminar (id no encontrado o error de almacenamiento)."
        )


async def cmd_listtareas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    msg = await update.message.reply_text("Consultando tareas en Deck...")

    tareas = listar_tareas_deck()

    if not tareas:
        err = obtener_ultimo_error_deck()
        extra = f"\n\nDetalle: {err}" if err else ""
        await msg.edit_text(f"No hay tarjetas pendientes en Deck.{extra}")
        return

    tareas.sort(
        key=lambda t: (
            not t["due"],
            t["due"] or "9999-99-99",
            (t.get("stack_title") or "").lower(),
            (t.get("title") or "").lower(),
        )
    )

    if context.chat_data is not None:
        context.chat_data[CACHE_RM_TAREAS_DECK] = [
            {
                "board_id": t["board_id"],
                "stack_id": t["stack_id"],
                "card_id": t["card_id"],
            }
            for t in tareas
        ]

    lineas: list[str] = []
    for i, t in enumerate(tareas, 1):
        fecha = f" [{t['due']}]" if t["due"] else ""
        col = f" ({t['stack_title']})" if t.get("stack_title") else ""
        titulo = t.get("title") or "(sin titulo)"
        titulo = (titulo[:60] + "...") if len(titulo) > 60 else titulo
        lineas.append(f"{i}.{col}{fecha} {titulo}")

    cabecera = f"Tareas Deck ({len(tareas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await msg.edit_text(texto_completo)
    else:
        await msg.edit_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


async def cmd_rmtarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /rmtarea <numero>\n"
            "El numero es el de la ultima lista de /listtareas en este chat."
        )
        return
    try:
        n = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("El numero debe ser un entero (ej. 1).")
        return

    cache = (context.chat_data or {}).get(CACHE_RM_TAREAS_DECK) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text(
            "Indice invalido o lista antigua. Ejecuta /listtareas primero en este chat."
        )
        return

    item = cache[n - 1]
    ok = borrar_tarjeta_deck(
        int(item["board_id"]),
        int(item["stack_id"]),
        int(item["card_id"]),
    )
    if ok:
        if context.chat_data is not None:
            context.chat_data.pop(CACHE_RM_TAREAS_DECK, None)
        await update.message.reply_text(f"Tarea {n} eliminada de Deck.")
    else:
        err = obtener_ultimo_error_deck()
        await update.message.reply_text(
            "No se pudo borrar la tarjeta.\n" + (err or "sin detalle")
        )


async def cmd_huevos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Uso: /huevos <cantidad>\nEjemplo: /huevos 12")
        return
    try:
        cantidad = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("La cantidad debe ser un numero entero.")
        return
    if cantidad <= 0:
        await update.message.reply_text("La cantidad debe ser mayor que cero.")
        return

    hoy = datetime.now().strftime("%Y-%m-%d")
    reg = añadir_huevo(cantidad, hoy, fuente="telegram")
    await update.message.reply_text(
        f"Registro de huevos guardado.\n"
        f"Fecha: {hoy}\n"
        f"Cantidad: {cantidad}\n"
        f"ID: {reg.id}"
    )


async def cmd_listhuevos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    dias = 6
    if context.args:
        if len(context.args) > 1 or not context.args[0].strip().isdigit():
            await update.message.reply_text(
                "Uso: /listhuevos [dias]\n"
                "Sin argumento muestra 6 dias hacia atras desde hoy.\n"
                "Ejemplo: /listhuevos 10"
            )
            return
        dias = int(context.args[0].strip())
        if dias < 1 or dias > 366:
            await update.message.reply_text("El numero de dias debe estar entre 1 y 366.")
            return

    filas = resumen_ultimos_dias_desde_hoy(dias)
    lineas: list[str] = []
    for fecha_iso, total in filas:
        try:
            d = datetime.strptime(fecha_iso, "%Y-%m-%d")
            etiqueta = d.strftime("%d-%m-%Y")
        except ValueError:
            etiqueta = fecha_iso
        lineas.append(f"{etiqueta}: {total}")

    cabecera = f"Huevos (ultimos {dias} dias, desde hoy hacia atras):\n\n"
    texto_completo = cabecera + "\n".join(lineas)
    await update.message.reply_text(texto_completo)


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
            texto_func, pri_func = _parsear_funcionalidad_audio(contenido)
            if not texto_func:
                await estado.edit_text(
                    "La funcionalidad no puede estar vacia tras quitar la prioridad."
                )
                return
            func = Funcionalidad(
                id=_generar_id_func(texto_func),
                texto=texto_func,
                prioridad=pri_func,
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
            titulo_t, fecha_t, descripcion_t = _parsear_args_tarea(contenido)
            if not titulo_t:
                await estado.edit_text(
                    "La tarea no puede estar vacia. Di: tarea <titulo> [fecha DD-MM-AAAA, DD-MM o DD]"
                )
                return
            if fecha_t:
                try:
                    datetime.strptime(fecha_t, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_t}\n"
                        "Usa DD-MM-AAAA, DD-MM, DD o YYYY-MM-DD"
                    )
                    return
            ok = crear_tarea_deck(
                titulo_t, descripcion=descripcion_t, fecha_due=fecha_t
            )
            if ok:
                lineas = [
                    f"Tarea creada en Deck ({config.DECK_BOARD_NAME}) desde audio.",
                    f"Titulo: {titulo_t}",
                ]
                if fecha_t:
                    lineas.append(f"Fecha limite: {fecha_t}")
                await estado.edit_text("\n".join(lineas))
            else:
                deck_error = obtener_ultimo_error_deck()
                await estado.edit_text(
                    "No se pudo crear la tarea en Deck desde audio.\n"
                    f"{deck_error or 'sin detalle'}"
                )

        elif accion == "comprar":
            titulo_c, fecha_c, descripcion_c = _parsear_args_tarea(contenido)
            if not titulo_c:
                await estado.edit_text(
                    f'La compra no puede estar vacia. Di: comprar <titulo> [fecha]\n'
                    f'(columna Deck "{DECK_STACK_COMPRAR}")'
                )
                return
            if fecha_c:
                try:
                    datetime.strptime(fecha_c, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_c}\n"
                        "Usa DD-MM-AAAA, DD-MM, DD o YYYY-MM-DD"
                    )
                    return
            ok = crear_tarea_deck(
                titulo_c,
                descripcion=descripcion_c,
                fecha_due=fecha_c,
                stack_name=DECK_STACK_COMPRAR,
            )
            if ok:
                lineas = [
                    f'Compra anotada en Deck ({config.DECK_BOARD_NAME}) [{DECK_STACK_COMPRAR}] desde audio.',
                    f"Titulo: {titulo_c}",
                ]
                if fecha_c:
                    lineas.append(f"Fecha limite: {fecha_c}")
                await estado.edit_text("\n".join(lineas))
            else:
                deck_error = obtener_ultimo_error_deck()
                await estado.edit_text(
                    "No se pudo crear la tarjeta de compra en Deck desde audio.\n"
                    f"{deck_error or 'sin detalle'}"
                )

        elif accion == "evento":
            nombre_ev, fecha_ev, hora_ev = _parsear_args_evento(contenido)
            if not fecha_ev:
                await estado.edit_text(
                    "El evento necesita una fecha española (ej. 20-03-26, 20-03-2026, 20-03, o solo el dia).\n"
                    "Opcional HH:MM. Ejemplo: evento reunion 20-03 15:30"
                )
                return
            if not nombre_ev:
                await estado.edit_text(
                    "El nombre del evento no puede estar vacio tras la transcripcion."
                )
                return
            fecha_iso_ev = _fecha_evento_ddmmyyyy_a_iso(fecha_ev)
            if fecha_iso_ev is None:
                await estado.edit_text(
                    f"Fecha invalida: {fecha_ev}\n"
                    "Usa dia-mes con / o -; año opcional (2 cifras -> 20xx)."
                )
                return
            if hora_ev:
                try:
                    datetime.strptime(hora_ev, "%H:%M")
                except ValueError:
                    await estado.edit_text(
                        f"Hora invalida: {hora_ev}\nUsa HH:MM en 24 h"
                    )
                    return
            ok = crear_evento(nombre_ev, fecha_iso_ev, hora=hora_ev)
            if ok:
                partes = [
                    f"Evento creado desde audio: {nombre_ev}",
                    f"Fecha: {fecha_ev}",
                ]
                if hora_ev:
                    partes.append(f"Hora inicio: {hora_ev} (duracion 1 h)")
                await estado.edit_text("\n".join(partes))
            else:
                err_ev = obtener_ultimo_error_evento()
                await estado.edit_text(
                    "No se pudo crear el evento desde audio.\n"
                    + (err_ev or "sin detalle")
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
    app.add_handler(CommandHandler("listfuncionalidades", cmd_listfunc))
    app.add_handler(CommandHandler("rmfunc", cmd_rmfunc))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("comprar", cmd_comprar))
    app.add_handler(CommandHandler("evento", cmd_evento))
    app.add_handler(CommandHandler("listevento", cmd_listevento))
    app.add_handler(CommandHandler("rmevento", cmd_rmevento))
    app.add_handler(CommandHandler("listtareas", cmd_listtareas))
    app.add_handler(CommandHandler("rmtarea", cmd_rmtarea))
    app.add_handler(CommandHandler("huevos", cmd_huevos))
    app.add_handler(CommandHandler("listhuevos", cmd_listhuevos))
    app.add_handler(CommandHandler("revisar", cmd_revisar))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, manejar_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_error_handler(error_handler)

    print("Bot iniciado. Pulsa Ctrl+C para detener.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
