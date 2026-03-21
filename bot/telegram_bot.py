"""
Bot Telegram: convocatorias (/convo, /listconvo, /verconvo, /rmconvo),
ideas, proyectos, tiempos, enlaces, investigaciones (/investiga), funcionalidades,
tareas Deck, eventos CalDAV, huevos, diario, pendientes (audio), audio. Ver /ayuda.
URL suelta = nuevo enlace (data/enlaces.csv). Convocatoria solo con /convo <url>.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

# Añadir proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.error import Conflict

import config
from src.db import Convocatoria, añadir, buscar_por_id, eliminar_por_id, listar
from src.db_ideas import (
    Idea,
    añadir_idea,
    buscar_por_id as buscar_idea_por_id,
    eliminar_por_id as eliminar_idea_por_id,
    leer_ideas,
)
from src.db_funcionalidad import (
    Funcionalidad,
    ESTADOS_VALIDOS,
    añadir as añadir_func,
    buscar_por_id as buscar_func_por_id,
    listar as listar_func,
    eliminar as eliminar_func_db,
)
from src.db_investigaciones import (
    Investigacion,
    añadir as añadir_investigacion,
    buscar_por_id as buscar_investigacion_por_id,
    eliminar as eliminar_investigacion_db,
    listar as listar_investigaciones,
)
from src.db_enlaces import (
    Enlace,
    añadir_enlace,
    buscar_enlace_por_id,
    buscar_enlace_por_url,
    eliminar_enlace_por_id,
    leer_enlaces,
)
from src.caldav_client import (
    borrar_evento_por_url,
    crear_evento,
    formatear_detalle_evento_por_url,
    listar_eventos_proximos_dias,
    obtener_ultimo_error_evento,
)
from src.deck_client import (
    borrar_tarjeta_deck,
    crear_tarea_deck,
    listar_tareas_deck,
    obtener_tarjeta_deck,
    obtener_ultimo_aviso_asignacion_deck,
    obtener_ultimo_error_deck,
)
from src.db_diario import añadir_entrada as diario_añadir_entrada
from src.db_huevos import (
    añadir as añadir_huevo,
    resumen_ultimos_dias_desde_hoy,
    total_cantidad_en_fecha,
)
from src.db_pendientes import (
    Pendiente,
    añadir as añadir_pendiente,
    buscar_por_id as buscar_pendiente_por_id,
    eliminar as eliminar_pendiente_db,
    listar_recientes_primero as listar_pendientes_recientes,
)
from src.db_proyectos import (
    ESTADOS_PROYECTO_VALIDOS,
    Proyecto,
    añadir_proyecto,
    buscar_por_id as buscar_proyecto_por_id,
    eliminar_por_id as eliminar_proyecto_por_id,
    leer_proyectos,
    tiempo_total_minutos,
)
from src.db_tiempos import (
    Tiempo,
    añadir_tiempo,
    buscar_activo_global,
    buscar_por_id as buscar_tiempo_por_id,
    cerrar_tiempo,
    eliminar_todos_de_proyecto,
    es_activo,
    leer_tiempos,
    sincronizar_tiempo_total_proyecto,
)
from src.fechas_proyecto import (
    formatear_fecha,
    formatear_fecha_hora,
    formatear_minutos_como_texto,
    parsear_fecha_hora,
    parsear_solo_fecha,
)
from src.plazo import es_futura, clave_orden, parsear_plazo
from src.scraper import extraer
from src.fecha_display import (
    extraer_fecha_relativa_dd_mm_yyyy,
    fecha_hoy_relativas,
    formatear_fecha_ver,
    extraer_fecha_relativa_iso_y_resto,
    strip_sufijo_para_el,
)
from src.db_contabilidad import (
    CAMPOS_EDITABLES_MOD,
    FacturaContabilidad,
    añadir_factura,
    buscar_por_id as buscar_factura_por_id,
    eliminar_por_id as eliminar_factura_por_id,
    listar_recientes_primero as listar_facturas_recientes,
    actualizar_campos as actualizar_factura_campos,
    nombre_archivo_seguro,
)
from src.extraccion_factura import (
    extraer_campos_desde_texto,
    normalizar_fecha_iso,
    texto_desde_imagen,
    texto_desde_pdf,
    trimestre_desde_fecha,
)
from src.nextcloud_client import subir_archivo_facturas

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
CACHE_RM_IDEAS = "rm_idea_ids"
CACHE_RM_CONVOS = "rm_conv_ids"
CACHE_RM_ENLACES = "rm_enlace_ids"
CACHE_RM_PROYECTOS = "rm_proyecto_ids"
CACHE_RM_TIEMPOS = "rm_tiempo_ids"
CACHE_RM_INVESTIGACIONES = "rm_investigacion_ids"
CACHE_RM_PENDIENTES_IDS = "rm_pendiente_ids"
CACHE_RM_CONTABILIDAD_IDS = "rm_contabilidad_ids"
WIZARD_PROYECTO_KEY = "proyecto_wizard"
WIZARD_MOD_FACTURA_KEY = "mod_factura_wizard"
ESPERANDO_FACTURA_KEY = "esperando_factura"

# Resumen de texto en /listfunc y /listfuncionalidades (60 + 20 caracteres)
FUNC_RESUMEN_MAX = 80
INV_RESUMEN_LISTA_MAX = 72
PENDIENTE_RESUMEN_LISTA_MAX = 72
_TIPOS_MV_VALIDOS = frozenset(
    {"idea", "tarea", "evento", "funcionalidad", "investiga", "comprar", "diario"}
)
IDEA_RESUMEN_LISTA_MAX = 70
ENLACE_RESUMEN_LISTA_MAX = 72
MAX_TELEGRAM_MSG = 4000
PROYECTO_RESUMEN_LISTA_MAX = 60
TIEMPO_RESUMEN_LISTA_MAX = 55

_EMAIL_PROYECTO_RE = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


def _parsear_tokens_rm(args: list[str]) -> tuple[list[int], list[str]]:
    """Separa argumentos en enteros (indices de listado) y otros tokens."""
    enteros: list[int] = []
    otros: list[str] = []
    for a in args:
        s = (a or "").strip()
        if not s:
            continue
        if s.isdigit():
            enteros.append(int(s))
        else:
            otros.append(s)
    return enteros, otros


async def _reply_texto_largo(update: Update, texto: str) -> None:
    """Envía texto partido en trozos <= MAX_TELEGRAM_MSG."""
    if len(texto) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto)
        return
    i = 0
    while i < len(texto):
        await update.message.reply_text(texto[i : i + MAX_TELEGRAM_MSG])
        i += MAX_TELEGRAM_MSG


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


def _deck_uids_para_update(update: Update | None) -> list[str]:
    """Uids Nextcloud para asignar tarjetas Deck según username de Telegram."""
    if not update or not update.effective_user:
        return []
    u = update.effective_user
    un = (u.username or "").strip().lower()
    if not un:
        return []
    uid = config.DECK_ASSIGNEE_BY_TELEGRAM_USERNAME.get(un)
    if not uid:
        return []
    return [uid]


def _primer_entero_positivo(texto: str) -> int | None:
    m = re.search(r"\b(\d+)\b", texto or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 0 else None


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


_ACCIONES_AUDIO = frozenset(
    {
        "idea",
        "funcionalidad",
        "tarea",
        "evento",
        "comprar",
        "investiga",
        "huevos",
        "diario",
    }
)
_ACCION_AUDIO_SINONIMOS: dict[str, str] = {"eventos": "evento"}


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
    candidato = _ACCION_AUDIO_SINONIMOS.get(candidato, candidato)
    if candidato in _ACCIONES_AUDIO:
        contenido = partes[1].strip() if len(partes) > 1 else ""
        return candidato, contenido
    return None, normalizado


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto = (
        f"ConvocAUTOrias bot v{config.APP_VERSION}\n\n"
        "Comandos por tema (orden sugerido: crear → listar → ver → borrar):\n\n"
        "[Convocatorias]\n"
        "/convo <url> — Añade convocatoria por URL\n"
        "/listconvo — Lista futuras por proximidad\n"
        "/verconvo <numero> — Detalle (numero del ultimo /listconvo en este chat)\n"
        "/rmconvo <num ...> — Elimina una o varias por numero del listado\n\n"
        "[Enlaces sin categorizar]\n"
        "/url <https://...> [notas] — Guardar en enlaces.csv (tags/categorias en el CSV)\n"
        "URL suelta (sin comando) — Se guarda igual que /url\n"
        "/listurl — Listar enlaces\n"
        "/verurl <numero>\n"
        "/rmurl <num ...>\n\n"
        "[Ideas]\n"
        "/idea <texto> — Guardar\n"
        "/listideas — Listar (recientes primero)\n"
        "/veridea <numero>\n"
        "/rmidea <num ...>\n\n"
        "[Proyectos]\n"
        "/proyecto — Alta guiada (titulo, fechas, contacto, estado, descripcion en .md)\n"
        "/cancelarproyecto — Abortar la alta guiada\n"
        "/listproyecto — Listar\n"
        "/verproyecto <numero>\n"
        "/rmproyecto <num ...>\n\n"
        "[Tiempos por proyecto]\n"
        "/tiempo <num_proyecto> — Iniciar (un solo activo global)\n"
        "/tiempofin — Cerrar el tiempo activo\n"
        "/tiempo <num_proyecto> <minutos> — Sumar tiempo (hoy desde 00:00)\n"
        "/listtiempo — Listar registros (indice para /modtiempo)\n"
        "/vertiempo <numero>\n"
        "/modtiempo <num_tiempo> <fecha hora fin> — Corregir fin y duracion\n\n"
        "[Funcionalidades]\n"
        "/func <texto> [prioridad 1-5] — Registrar (prioridad por defecto 3)\n"
        "/listfunc o /listfuncionalidades — Listar por prioridad\n"
        "/verfunc <numero>\n"
        "/rmfunc <num ...>\n\n"
        "[Investigaciones]\n"
        "/investiga <concepto o frase> — Encola investigación (CSV + proceso automático)\n"
        "/listinvestigaciones — Listar (recientes primero)\n"
        "/verinvestigacion <numero|id> — Detalle CSV + contenido del .md si existe\n"
        "/rminvestigacion <numero ...> — Borrar fila y .md asociado\n\n"
        "[Tareas Deck]\n"
        '/tarea "Titulo" [fecha] ["Desc"] — Tarjeta (columna por defecto)\n'
        f'/comprar "Titulo" [fecha] ["Desc"] — Columna "{DECK_STACK_COMPRAR}"\n'
        "/listtareas — Listar por fecha\n"
        "/vertarea <numero> — Detalle de la tarjeta\n"
        "/rmtarea <num ...>\n\n"
        "[Eventos CalDAV]\n"
        "/evento <nombre> <fecha> [HH:MM] — Crear (1 h si hay hora)\n"
        "/listeventos [+ | ++] — 7 / 14 / 21 dias\n"
        "/verevento <numero>\n"
        "/rmevento <num ...>\n\n"
        "[Huevos]\n"
        "/huevos <cantidad> — Registro del dia (la respuesta muestra total acumulado del dia)\n"
        "/listhuevos [dias] — Resumen hacia atras (6 por defecto)\n\n"
        "[Diario]\n"
        "/diario <texto> — Nota del dia (data/diario/AAAA-MM-DD.md + diario.csv)\n\n"
        "[Contabilidad / Facturas]\n"
        "/factura — Luego envia foto o PDF; sube a Nextcloud y fila en contabilidad.csv\n"
        "/cancelarfactura — Cancela espera de archivo tras /factura\n"
        "/listcontabilidad — Listado (indice para /verfactura /rmfactura /modfactura)\n"
        "/verfactura <n|id>\n"
        "/rmfactura <n ...>\n"
        "/modfactura <n|id> — Edicion guiada por campo; /cancelarmodfactura para salir\n\n"
        "[Pendientes]\n"
        "Audio sin comando reconocido -> pendientes.csv\n"
        "/listpendientes — Listar (recientes primero)\n"
        "/verpendiente <n|id>\n"
        "/rmpendientes <n ...>\n"
        "/mvpendiente <n|id> <tipo> [args extra] — idea, tarea, evento, funcionalidad, "
        "investiga, comprar, diario (func = funcionalidad)\n\n"
        "[Audio]\n"
        "Primera palabra: idea, funcionalidad, tarea, comprar, evento, eventos, investiga, "
        "huevos, diario. Si no coincide, se guarda en pendientes (no como idea).\n"
        "Por voz, tarea/compra/evento: usa 'para el' antes de la fecha "
        "(ej. tarea comprar pan para el 25-03). Funcionalidad: 'prioridad' + numero o palabra (uno…cinco).\n\n"
        "Fechas (tarea/evento texto): DD-MM-AAAA; DD-MM = año actual; solo DD = mes actual; "
        "tambien YYYY-MM-DD; y palabras: antier, ayer, hoy, mañana, pasado (pasado mañana).\n"
        "Fechas (proyecto/tiempo): entrada flexible (coma, guion, barra, punto); "
        "se muestran como DD,MM,YYYY y DD,MM,YYYY HH:MM.\n\n"
        "/ayuda — Esta lista"
    )
    await _reply_texto_largo(update, texto)


async def cmd_convo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /convo <url>")
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

    if context.chat_data is not None:
        context.chat_data[CACHE_RM_CONVOS] = [c.id for c in futuras]

    cabecera = f"Hay {len(futuras)} convocatoria(s) futura(s):\n\n"
    lineas: list[str] = []
    for i, c in enumerate(futuras, 1):
        titulo = (c.titulo[:55] + "...") if len(c.titulo) > 55 else c.titulo
        plazo = _formato_plazo(c.plazo_fin)
        lineas.append(f"{i}. [{plazo}] {titulo}")

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


def _formatear_convocatoria(conv: Convocatoria, *, recortar_descripcion: bool = False) -> str:
    """Formatea todos los campos de una convocatoria para mostrar al usuario."""
    plazo = conv.plazo_fin.strip() if conv.plazo_fin.strip() else "No disponible"
    requisitos = conv.requisitos.strip() if conv.requisitos.strip() else "No especificados"

    descripcion = conv.descripcion.strip()
    if recortar_descripcion and len(descripcion) > 1500:
        descripcion = descripcion[:1500] + "... (recortado)"
    if not descripcion:
        descripcion = "No disponible"

    return (
        f"Titulo: {conv.titulo}\n\n"
        f"URL: {conv.url}\n\n"
        f"Plazo: {plazo}\n\n"
        f"Requisitos: {requisitos}\n\n"
        f"Descripcion:\n{descripcion}\n\n"
        f"Fuente: {conv.fuente}\n"
        f"Fecha: {formatear_fecha_ver(conv.fecha_ingesta)}"
    )


async def _cmd_ver_convocatoria(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    nombre_cmd: str,
    listar_hint: str,
) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            f"Uso: {nombre_cmd} <numero>\n"
            f"El numero es el de {listar_hint} en este chat."
        )
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
                f"Usa {listar_hint} para verlas."
            )
            return
    else:
        conv = buscar_por_id(argumento)

    if not conv:
        await update.message.reply_text(
            f"No se encontro convocatoria con ese criterio.\n"
            f"Usa {listar_hint} para ver las disponibles."
        )
        return

    texto = _formatear_convocatoria(conv, recortar_descripcion=False)
    await _reply_texto_largo(update, texto)


async def cmd_verconvo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_ver_convocatoria(
        update,
        context,
        nombre_cmd="/verconvo",
        listar_hint="/listconvo",
    )


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
        f"Resumen: {idea.resumen}"
    )


def _ruta_archivo_idea(ruta: str) -> Path:
    p = Path((ruta or "").strip())
    if p.is_absolute():
        return p
    return (config.DIR_PROYECTO / p).resolve()


def _formatear_idea_completa(idea: Idea, cuerpo_md: str) -> str:
    cuerpo = (cuerpo_md or "").strip()
    if not cuerpo:
        cuerpo = "(archivo vacio o no encontrado)"
    return (
        f"Resumen: {idea.resumen}\n"
        f"Tags: {idea.tags or '(ninguno)'}\n"
        f"Categorias: {idea.categorias or '(ninguna)'}\n"
        f"Presupuesto aprox.: {idea.presupuesto_aproximado or '(no indicado)'}\n"
        f"Fecha: {formatear_fecha_ver(idea.fecha_ingesta)}\n"
        f"Fuente: {idea.fuente}\n\n"
        f"--- Contenido ---\n{cuerpo}"
    )


async def cmd_listideas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    ideas = leer_ideas()
    if not ideas:
        await update.message.reply_text("No hay ideas registradas en ideas.csv.")
        return

    ideas = sorted(ideas, key=lambda i: (i.fecha_ingesta or "", i.id), reverse=True)
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_IDEAS] = [i.id for i in ideas]

    lineas: list[str] = []
    for i, idea in enumerate(ideas, 1):
        res = idea.resumen.strip() or "(sin resumen)"
        if len(res) > IDEA_RESUMEN_LISTA_MAX:
            res = res[:IDEA_RESUMEN_LISTA_MAX] + "..."
        lineas.append(f"{i}. {res}")

    cabecera = f"Ideas ({len(ideas)}), mas recientes primero:\n\n"
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


async def cmd_veridea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /veridea <numero>\n"
            "El numero es el de /listideas en este chat."
        )
        return

    argumento = context.args[0].strip()
    idea: Idea | None = None

    if argumento.isdigit():
        n = int(argumento)
        cache = (context.chat_data or {}).get(CACHE_RM_IDEAS) or []
        if n < 1 or n > len(cache):
            await update.message.reply_text(
                "Indice invalido o lista antigua. Ejecuta /listideas primero en este chat."
            )
            return
        idea = buscar_idea_por_id(cache[n - 1])
    else:
        idea = buscar_idea_por_id(argumento)

    if not idea:
        await update.message.reply_text(
            "No se encontro idea con ese criterio.\nUsa /listideas para ver el listado."
        )
        return

    path = _ruta_archivo_idea(idea.ruta)
    cuerpo = ""
    try:
        if path.is_file():
            cuerpo = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        cuerpo = ""

    texto = _formatear_idea_completa(idea, cuerpo)
    MAX_MSG = 4000
    if len(texto) <= MAX_MSG:
        await update.message.reply_text(texto)
    else:
        await update.message.reply_text(texto[:MAX_MSG])
        resto = texto[MAX_MSG:]
        while resto:
            trozo = resto[:MAX_MSG]
            resto = resto[MAX_MSG:]
            await update.message.reply_text(trozo)


async def cmd_rmidea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmidea <numero> [numero ...]\n"
            "Los numeros son los de /listideas en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros and enteros:
        await update.message.reply_text(
            "Usa solo numeros del listado separados por espacios, o un solo criterio interno."
        )
        return

    ids_objetivo: list[str] = []
    fuera: list[int] = []
    if otros:
        if len(otros) != 1:
            await update.message.reply_text(
                "Para borrar por criterio interno solo se admite un token."
            )
            return
        ids_objetivo = [otros[0].strip()]
    else:
        cache = (context.chat_data or {}).get(CACHE_RM_IDEAS) or []
        vistos: set[str] = set()
        for n in enteros:
            if n < 1 or n > len(cache):
                fuera.append(n)
                continue
            tid = cache[n - 1]
            if tid not in vistos:
                vistos.add(tid)
                ids_objetivo.append(tid)
        if not ids_objetivo:
            msg = "Ningun numero valido."
            if fuera:
                msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listideas en este chat."
            await update.message.reply_text(msg)
            return

    ok_n = 0
    no_encontradas = 0
    error_indice = 0
    archivo_no_borrado = False

    for target_id in ids_objetivo:
        idea = buscar_idea_por_id(target_id)
        if not idea:
            no_encontradas += 1
            continue
        path = _ruta_archivo_idea(idea.ruta)
        removed = eliminar_idea_por_id(idea.id)
        if not removed:
            error_indice += 1
            continue
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                archivo_no_borrado = True
        ok_n += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_IDEAS, None)

    partes = [f"Ideas eliminadas: {ok_n}."]
    if not otros and fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if no_encontradas:
        partes.append(f"No encontradas: {no_encontradas}.")
    if error_indice:
        partes.append(f"Error al quitar del indice: {error_indice}.")
    if archivo_no_borrado:
        partes.append("Revisa la carpeta data/ideas por archivos .md huérfanos.")
    await update.message.reply_text(" ".join(partes))


# --- Proyectos y tiempos ---


def _generar_id_proyecto(titulo: str) -> str:
    base = f"{datetime.now().isoformat()}::proyecto::{titulo[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _generar_id_tiempo(id_proyecto: str, inicio_iso_hint: str) -> str:
    base = f"{datetime.now().isoformat()}::tiempo::{id_proyecto}::{inicio_iso_hint}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ruta_archivo_proyecto(ruta: str) -> Path:
    p = Path(ruta)
    if p.is_absolute():
        return p
    return (config.DIR_PROYECTO / p).resolve()


def _limpiar_wizard_proyecto(context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_PROYECTO_KEY, None)


def _wizard_proyecto_prompt_paso(step: int) -> str:
    if step == 0:
        return "Nuevo proyecto — paso 1/8: Titulo del proyecto (una linea)."
    if step == 1:
        return (
            "Paso 2/8: Fecha de creacion (flexible: DD,MM,YYYY / DD-MM / solo DD…). "
            "Escribe hoy para usar la fecha de hoy."
        )
    if step == 2:
        return "Paso 3/8: Persona de contacto."
    if step == 3:
        return "Paso 4/8: Email de contacto."
    if step == 4:
        return "Paso 5/8: Presupuesto (texto o numero). Escribe - si no aplica."
    if step == 5:
        return (
            "Paso 6/8: Fecha fin prevista (mismo formato flexible) o - si no hay."
        )
    if step == 6:
        return (
            "Paso 7/8: Estado: idea | activo | en_espera | presupuestado | completado | cancelado"
        )
    if step == 7:
        return (
            "Paso 8/8: Descripcion larga (markdown, una o varias lineas) o - si no hay."
        )
    return ""


def _email_valido_proyecto(s: str) -> bool:
    return bool(_EMAIL_PROYECTO_RE.match((s or "").strip()))


def _proyecto_desde_indice_listado(
    context: ContextTypes.DEFAULT_TYPE, indice: int
) -> Proyecto | None:
    cache = (context.chat_data or {}).get(CACHE_RM_PROYECTOS) or []
    if indice < 1 or indice > len(cache):
        return None
    return buscar_proyecto_por_id(cache[indice - 1])


def _ordenar_tiempos_recientes(items: list[Tiempo]) -> list[Tiempo]:
    def clave(t: Tiempo) -> tuple:
        dt = parsear_fecha_hora(t.fecha_hora_inicio)
        if dt is None:
            return (datetime.min, t.id)
        return (dt, t.id)

    return sorted(items, key=clave, reverse=True)


def _formatear_proyecto_lista(p: Proyecto) -> str:
    tit = p.titulo.strip() or "(sin titulo)"
    if len(tit) > PROYECTO_RESUMEN_LISTA_MAX:
        tit = tit[:PROYECTO_RESUMEN_LISTA_MAX] + "..."
    tm = formatear_minutos_como_texto(tiempo_total_minutos(p))
    return f"{tit} [{p.estado}] tiempo {tm}"


def _formatear_proyecto_completo(p: Proyecto, cuerpo_md: str) -> str:
    fc = (p.fecha_creacion or "").strip()
    fc_show = formatear_fecha_ver(fc) if fc else "(sin fecha)"
    ff = (p.fecha_fin or "").strip()
    ff_show = formatear_fecha_ver(ff) if ff else "(sin fecha fin)"
    pres = p.presupuesto.strip() or "(no indicado)"
    return (
        f"Titulo: {p.titulo}\n"
        f"Fecha creacion: {fc_show}\n"
        f"Contacto: {p.persona_contacto}\n"
        f"Email: {p.email_contacto}\n"
        f"Presupuesto: {pres}\n"
        f"Tiempo total: {formatear_minutos_como_texto(tiempo_total_minutos(p))}\n"
        f"Fecha fin: {ff_show}\n"
        f"Estado: {p.estado}\n"
        f"Fuente: {p.fuente}\n\n"
        f"Descripcion / notas:\n{cuerpo_md.strip() or '(vacio)'}"
    )


async def cmd_proyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    user = update.effective_user
    if not user:
        return
    if context.chat_data is None:
        await update.message.reply_text("No se pudo iniciar el asistente en este chat.")
        return

    context.chat_data[WIZARD_PROYECTO_KEY] = {
        "user_id": user.id,
        "step": 0,
        "data": {},
    }
    await update.message.reply_text(
        _wizard_proyecto_prompt_paso(0) + "\n\n/cancelarproyecto para abortar."
    )


async def cmd_cancelarproyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if (context.chat_data or {}).get(WIZARD_PROYECTO_KEY):
        _limpiar_wizard_proyecto(context)
        await update.message.reply_text("Alta de proyecto cancelada.")
    else:
        await update.message.reply_text("No habia un proyecto en curso.")


async def _manejar_wizard_proyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Si consume el mensaje, devuelve True."""
    wizard = (context.chat_data or {}).get(WIZARD_PROYECTO_KEY)
    if not wizard:
        return False
    user = update.effective_user
    if not user or user.id != wizard.get("user_id"):
        return False

    texto_raw = (update.message.text or "").strip()
    if not texto_raw:
        await update.message.reply_text("Envia texto o /cancelarproyecto.")
        return True

    step: int = wizard["step"]
    data: dict = wizard["data"]

    if step == 0:
        if not texto_raw:
            await update.message.reply_text("El titulo no puede estar vacio.")
            return True
        data["titulo"] = texto_raw
        wizard["step"] = 1
        await update.message.reply_text(_wizard_proyecto_prompt_paso(1))
        return True

    if step == 1:
        tnorm = texto_raw.lower()
        if tnorm in ("hoy", "today"):
            dt = datetime.now()
        else:
            dt = parsear_solo_fecha(texto_raw)
            if dt is None:
                await update.message.reply_text(
                    "Fecha no reconocida. Usa DD,MM,YYYY / DD-MM / solo DD… o la palabra hoy."
                )
                return True
        data["fecha_creacion"] = formatear_fecha(dt)
        wizard["step"] = 2
        await update.message.reply_text(_wizard_proyecto_prompt_paso(2))
        return True

    if step == 2:
        data["persona_contacto"] = texto_raw
        wizard["step"] = 3
        await update.message.reply_text(_wizard_proyecto_prompt_paso(3))
        return True

    if step == 3:
        if not _email_valido_proyecto(texto_raw):
            await update.message.reply_text("Email no valido. Vuelve a intentarlo.")
            return True
        data["email_contacto"] = texto_raw.strip()
        wizard["step"] = 4
        await update.message.reply_text(_wizard_proyecto_prompt_paso(4))
        return True

    if step == 4:
        data["presupuesto"] = "" if texto_raw in ("-", "—") else texto_raw
        wizard["step"] = 5
        await update.message.reply_text(_wizard_proyecto_prompt_paso(5))
        return True

    if step == 5:
        if texto_raw in ("-", "—"):
            data["fecha_fin"] = ""
        else:
            dt = parsear_solo_fecha(texto_raw)
            if dt is None:
                await update.message.reply_text("Fecha fin no reconocida. Usa - si no hay.")
                return True
            data["fecha_fin"] = formatear_fecha(dt)
        wizard["step"] = 6
        await update.message.reply_text(_wizard_proyecto_prompt_paso(6))
        return True

    if step == 6:
        est = texto_raw.lower().strip()
        if est not in ESTADOS_PROYECTO_VALIDOS:
            await update.message.reply_text(
                "Estado no valido. Usa uno de: idea, activo, en_espera, presupuestado, "
                "completado, cancelado"
            )
            return True
        data["estado"] = est
        wizard["step"] = 7
        await update.message.reply_text(_wizard_proyecto_prompt_paso(7))
        return True

    if step == 7:
        cuerpo = "" if texto_raw in ("-", "—") else texto_raw
        pid = _generar_id_proyecto(data["titulo"])
        config.CARPETA_PROYECTOS.mkdir(parents=True, exist_ok=True)
        ruta_abs = config.CARPETA_PROYECTOS / f"{pid}.md"
        try:
            ruta_rel = ruta_abs.relative_to(config.DIR_PROYECTO).as_posix()
        except Exception:
            ruta_rel = str(ruta_abs)
        ruta_rel = ruta_rel.replace("\\", "/")

        plantilla = (
            f"# {data['titulo']}\n\n"
            f"**Contacto:** {data['persona_contacto']} <{data['email_contacto']}>\n\n"
        )
        ruta_abs.write_text(plantilla + (cuerpo.strip() + "\n" if cuerpo else ""), encoding="utf-8")

        p = Proyecto(
            id=pid,
            titulo=data["titulo"],
            fecha_creacion=data["fecha_creacion"],
            persona_contacto=data["persona_contacto"],
            email_contacto=data["email_contacto"],
            presupuesto=data.get("presupuesto", ""),
            tiempo_total="0",
            fecha_fin=data.get("fecha_fin", ""),
            estado=data["estado"],
            ruta=ruta_rel,
            fuente="telegram",
        )
        añadir_proyecto(p)
        _limpiar_wizard_proyecto(context)
        await update.message.reply_text(
            f"Proyecto guardado.\nID interno: {pid}\nTitulo: {p.titulo}\n"
            f"Estado: {p.estado}\n\n"
            f"Usa /listproyecto y /tiempo <numero> para registrar tiempo."
        )
        return True

    return False


async def cmd_listproyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    proyectos = leer_proyectos()
    if not proyectos:
        await update.message.reply_text("No hay proyectos en proyectos.csv.")
        return
    def _clave_fecha_creacion(p: Proyecto) -> datetime:
        dt = parsear_solo_fecha(p.fecha_creacion)
        return dt if dt is not None else datetime.min

    proyectos.sort(
        key=lambda p: (_clave_fecha_creacion(p), p.titulo.lower()),
        reverse=True,
    )
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_PROYECTOS] = [p.id for p in proyectos]

    lineas = []
    for i, p in enumerate(proyectos, 1):
        lineas.append(f"{i}. {_formatear_proyecto_lista(p)}")
    cabecera = f"Proyectos ({len(proyectos)}), mas recientes primero:\n\n"
    texto_completo = cabecera + "\n".join(lineas)
    if len(texto_completo) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_TELEGRAM_MSG])
        await update.message.reply_text(texto_completo[MAX_TELEGRAM_MSG:])


async def cmd_verproyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /verproyecto <numero>\n"
            "El numero es el de /listproyecto en este chat."
        )
        return
    arg = context.args[0].strip()
    p: Proyecto | None = None
    if arg.isdigit():
        p = _proyecto_desde_indice_listado(context, int(arg))
    else:
        p = buscar_proyecto_por_id(arg)
    if not p:
        await update.message.reply_text(
            "No se encontro ese proyecto.\nUsa /listproyecto para ver el listado."
        )
        return
    path = _ruta_archivo_proyecto(p.ruta)
    try:
        cuerpo = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        cuerpo = ""
    await _reply_texto_largo(update, _formatear_proyecto_completo(p, cuerpo))


async def cmd_rmproyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmproyecto <numero> [numero ...]\n"
            "Los numeros son los de /listproyecto en este chat."
        )
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text("Solo numeros del listado, separados por espacios.")
        return
    cache = (context.chat_data or {}).get(CACHE_RM_PROYECTOS) or []
    fuera: list[int] = []
    vistos: set[str] = set()
    ids_objetivo: list[str] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        pid = cache[n - 1]
        if pid not in vistos:
            vistos.add(pid)
            ids_objetivo.append(pid)
    if not ids_objetivo:
        msg = "Ningun numero valido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listproyecto en este chat."
        await update.message.reply_text(msg)
        return

    activo = buscar_activo_global()
    if activo and activo.id_proyecto in ids_objetivo:
        await update.message.reply_text(
            "Hay un tiempo activo en uno de esos proyectos. Usa /tiempofin antes de borrar."
        )
        return

    ok_n = 0
    no_md = 0
    for pid in ids_objetivo:
        proyecto = buscar_proyecto_por_id(pid)
        if not proyecto:
            continue
        eliminar_todos_de_proyecto(pid)
        removed = eliminar_proyecto_por_id(pid)
        if not removed:
            continue
        path = _ruta_archivo_proyecto(removed.ruta)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                no_md += 1
        ok_n += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_PROYECTOS, None)
    partes = [f"Proyectos eliminados: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if no_md:
        partes.append(f"Aviso: {no_md} archivo(s) .md no se pudieron borrar.")
    await update.message.reply_text(" ".join(partes))


async def cmd_tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    args = list(context.args or [])
    if not args:
        await update.message.reply_text(
            "Uso:\n"
            "/tiempo <num_proyecto> — Inicia contador (solo uno activo a la vez).\n"
            "/tiempo <num_proyecto> <minutos> — Suma tiempo manual (hoy desde 00:00).\n"
            "Los numeros son los de /listproyecto en este chat."
        )
        return

    if not args[0].isdigit():
        await update.message.reply_text("El primer argumento debe ser el numero de /listproyecto.")
        return
    n = int(args[0])
    p = _proyecto_desde_indice_listado(context, n)
    if not p:
        await update.message.reply_text(
            "Proyecto no encontrado. Ejecuta /listproyecto en este chat primero."
        )
        return

    if len(args) == 1:
        activo = buscar_activo_global()
        if activo:
            await update.message.reply_text(
                "Ya hay un tiempo activo. Usa /tiempofin antes de iniciar otro."
            )
            return
        ahora = datetime.now()
        tid = _generar_id_tiempo(p.id, ahora.isoformat())
        t = Tiempo(
            id=tid,
            id_proyecto=p.id,
            fecha_hora_inicio=formatear_fecha_hora(ahora),
            fecha_hora_fin="",
            cantidad_tiempo="",
        )
        añadir_tiempo(t)
        await update.message.reply_text(
            f"Tiempo iniciado en proyecto: {p.titulo}\n"
            f"Inicio: {t.fecha_hora_inicio}\n"
            f"Usa /tiempofin al terminar."
        )
        return

    if len(args) >= 2:
        try:
            mins = int(args[1])
        except ValueError:
            await update.message.reply_text("Los minutos deben ser un numero entero.")
            return
        if mins < 0:
            await update.message.reply_text("Los minutos no pueden ser negativos.")
            return
        if mins == 0:
            await update.message.reply_text("Usa al menos 1 minuto o omite el segundo argumento.")
            return
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        fin = hoy + timedelta(minutes=mins)
        tid = _generar_id_tiempo(p.id, hoy.isoformat())
        t = Tiempo(
            id=tid,
            id_proyecto=p.id,
            fecha_hora_inicio=formatear_fecha_hora(hoy),
            fecha_hora_fin=formatear_fecha_hora(fin),
            cantidad_tiempo=str(mins),
        )
        añadir_tiempo(t)
        sincronizar_tiempo_total_proyecto(p.id)
        await update.message.reply_text(
            f"Tiempo manual: +{formatear_minutos_como_texto(mins)} en {p.titulo}\n"
            f"{t.fecha_hora_inicio} → {t.fecha_hora_fin}"
        )
        return

    await update.message.reply_text("Argumentos no reconocidos. Usa /ayuda.")


async def cmd_tiempofin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    activo = buscar_activo_global()
    if not activo:
        await update.message.reply_text("No hay ningun tiempo activo.")
        return
    fin = datetime.now()
    ok = cerrar_tiempo(activo, fin)
    if not ok:
        await update.message.reply_text("No se pudo cerrar el tiempo (fecha inicio invalida).")
        return
    p = buscar_proyecto_por_id(activo.id_proyecto)
    tit = p.titulo if p else activo.id_proyecto
    try:
        mins = int((activo.cantidad_tiempo or "0").strip() or 0)
    except ValueError:
        mins = 0
    await update.message.reply_text(
        f"Tiempo cerrado en: {tit}\n"
        f"Fin: {activo.fecha_hora_fin}\n"
        f"Duracion: {formatear_minutos_como_texto(mins)}\n"
        f"Total proyecto: {formatear_minutos_como_texto(tiempo_total_minutos(p) if p else mins)}"
    )


async def cmd_modtiempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    args = list(context.args or [])
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /modtiempo <num_tiempo> <fecha y hora fin>\n"
            "Ejemplo: /modtiempo 3 20,03,2026 18:45\n"
            "El numero es el de /listtiempo en este chat."
        )
        return
    if not args[0].isdigit():
        await update.message.reply_text("El primer argumento debe ser el numero de /listtiempo.")
        return
    n = int(args[0])
    resto = " ".join(args[1:]).strip()
    fin = parsear_fecha_hora(resto)
    if fin is None:
        await update.message.reply_text(
            "Fecha/hora fin no reconocida. Usa DD,MM,YYYY HH:MM (o variaciones con - / /)."
        )
        return
    cache = (context.chat_data or {}).get(CACHE_RM_TIEMPOS) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text(
            "Indice invalido. Ejecuta /listtiempo en este chat primero."
        )
        return
    t = buscar_tiempo_por_id(cache[n - 1])
    if not t:
        await update.message.reply_text("Registro de tiempo no encontrado.")
        return
    ini = parsear_fecha_hora(t.fecha_hora_inicio)
    if ini is None:
        await update.message.reply_text("No se pudo leer la fecha de inicio guardada.")
        return
    if fin < ini:
        await update.message.reply_text("La hora fin debe ser posterior al inicio.")
        return
    ok = cerrar_tiempo(t, fin)
    if not ok:
        await update.message.reply_text("No se pudo actualizar el registro.")
        return
    p = buscar_proyecto_por_id(t.id_proyecto)
    await update.message.reply_text(
        f"Tiempo actualizado.\n"
        f"Nueva fin: {t.fecha_hora_fin}\n"
        f"Duracion: {formatear_minutos_como_texto(int(t.cantidad_tiempo or 0))}\n"
        f"Total proyecto: {formatear_minutos_como_texto(tiempo_total_minutos(p) if p else 0)}"
    )


async def cmd_listtiempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    todos = leer_tiempos()
    if not todos:
        await update.message.reply_text("No hay registros en tiempos.csv.")
        return
    ordenados = _ordenar_tiempos_recientes(todos)
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_TIEMPOS] = [t.id for t in ordenados]

    lineas: list[str] = []
    for i, t in enumerate(ordenados, 1):
        p = buscar_proyecto_por_id(t.id_proyecto)
        tit = (p.titulo if p else t.id_proyecto)[:TIEMPO_RESUMEN_LISTA_MAX]
        suf = " (activo)" if es_activo(t) else ""
        dur = (
            formatear_minutos_como_texto(int(t.cantidad_tiempo or 0))
            if not es_activo(t)
            else "..."
        )
        lineas.append(
            f"{i}. {tit}{suf} | {t.fecha_hora_inicio} | {dur}"
        )
    texto = f"Tiempos ({len(ordenados)}), mas recientes primero:\n\n" + "\n".join(lineas)
    if len(texto) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto)
    else:
        await update.message.reply_text(texto[:MAX_TELEGRAM_MSG])
        await update.message.reply_text(texto[MAX_TELEGRAM_MSG:])


async def cmd_vertiempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /vertiempo <numero>\nEl numero es el de /listtiempo en este chat."
        )
        return
    arg = context.args[0].strip()
    t: Tiempo | None = None
    if arg.isdigit():
        cache = (context.chat_data or {}).get(CACHE_RM_TIEMPOS) or []
        n = int(arg)
        if n < 1 or n > len(cache):
            await update.message.reply_text(
                "Indice invalido. Ejecuta /listtiempo en este chat primero."
            )
            return
        t = buscar_tiempo_por_id(cache[n - 1])
    else:
        t = buscar_tiempo_por_id(arg)
    if not t:
        await update.message.reply_text("No se encontro ese registro.")
        return
    p = buscar_proyecto_por_id(t.id_proyecto)
    tit = p.titulo if p else t.id_proyecto
    fin_raw = t.fecha_hora_fin.strip()
    fin_txt = formatear_fecha_ver(fin_raw) if fin_raw else "(activo)"
    cant = t.cantidad_tiempo.strip() or ("—" if es_activo(t) else "0")
    body = (
        f"Proyecto: {tit}\n"
        f"ID tiempo: {t.id}\n"
        f"Inicio: {formatear_fecha_ver(t.fecha_hora_inicio)}\n"
        f"Fin: {fin_txt}\n"
        f"Minutos: {cant}\n"
    )
    if not es_activo(t):
        try:
            m = int(cant)
            body += f"Texto: {formatear_minutos_como_texto(m)}\n"
        except ValueError:
            pass
    await update.message.reply_text(body)


def _generar_id_func(texto: str) -> str:
    base = f"{datetime.now().isoformat()}::func::{texto[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _generar_id_investigacion(texto: str) -> str:
    base = f"{datetime.now().isoformat()}::inv::{texto[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


_PRIORIDAD_EMOJI = {1: "⬜", 2: "🟦", 3: "🟨", 4: "🟧", 5: "🟥"}


def _prioridad_desde_token_grupo(token: str) -> int | None:
    t = (token or "").strip().lower()
    if not t:
        return None
    if t.isdigit() and len(t) == 1:
        n = int(t)
        if 1 <= n <= 5:
            return n
    palabras = {
        "uno": 1,
        "una": 1,
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
    }
    return palabras.get(t)


def _parsear_funcionalidad_audio(contenido: str) -> tuple[str, int]:
    """
    Separa texto y prioridad: 'prioridad N' con N dígito o palabra (uno…cinco), en cualquier sitio.
    Respaldo: un único dígito 1-5 al final (voz/transcripción antigua).
    Por defecto prioridad 3.
    """
    texto = " ".join(contenido.split()).strip()
    prioridad = 3
    if not texto:
        return "", prioridad

    patron_pri = re.compile(
        r"\bprioridad\s+([1-5]|uno|una|dos|tres|cuatro|cinco)\b",
        re.IGNORECASE,
    )
    matches = list(patron_pri.finditer(texto))
    if matches:
        m = matches[-1]
        pv = _prioridad_desde_token_grupo(m.group(1))
        if pv is not None:
            prioridad = pv
        texto = (texto[: m.start()] + texto[m.end() :]).strip()
        texto = " ".join(texto.split())
    else:
        m2 = re.search(r"\s+([1-5])\s*$", texto)
        if m2:
            texto = texto[: m2.start()].strip()
            prioridad = int(m2.group(1))

    return strip_sufijo_para_el(texto.strip()), prioridad


async def cmd_func(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    if not context.args:
        await update.message.reply_text(
            "Uso: /func <texto> [prioridad 1-5]\n"
            "Ejemplo: /func mejorar parser del scraper 4\n"
            "Sin prioridad se usa 3 por defecto.\n"
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
        f"Texto: {func.texto}\n"
        f"Prioridad: {emoji} {func.prioridad}/5"
    )


async def cmd_investiga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /investiga <concepto o frase>\n"
            "Se guarda en investigaciones.csv como pendiente; el proceso automático "
            "completará resumen, enlace y un .md en data/investigaciones/."
        )
        return
    concepto = " ".join(context.args).strip()
    if not concepto:
        await update.message.reply_text("El concepto no puede estar vacío.")
        return
    inv = Investigacion(
        id=_generar_id_investigacion(concepto),
        fecha=datetime.now().isoformat(),
        estado="pendiente",
        concepto=concepto,
        resumen="",
        link="",
    )
    añadir_investigacion(inv)
    await update.message.reply_text(
        f"Investigación encolada (pendiente).\n"
        f"ID: {inv.id}\n"
        f"Concepto: {inv.concepto}"
    )


def _ruta_md_investigacion(inv_id: str) -> Path:
    return config.CARPETA_INVESTIGACIONES / f"{inv_id}.md"


def _leer_cuerpo_md_investigacion(inv_id: str) -> str | None:
    p = _ruta_md_investigacion(inv_id)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _formatear_investigacion_completa(inv: Investigacion) -> str:
    bloque_csv = (
        f"ID: {inv.id}\n"
        f"Fecha: {formatear_fecha_ver(inv.fecha)}\n"
        f"Estado: {inv.estado}\n"
        f"Concepto: {inv.concepto}\n"
        f"Resumen: {inv.resumen or '(vacío)'}\n"
        f"Link: {inv.link or '(vacío)'}\n"
    )
    md = _leer_cuerpo_md_investigacion(inv.id)
    if md is None:
        return bloque_csv + "\n--- Markdown ---\n(Aún no hay archivo .md; estado pendiente o sin generar.)"
    return bloque_csv + "\n--- Markdown ---\n" + md


async def cmd_listinvestigaciones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    todas = listar_investigaciones()
    if not todas:
        await update.message.reply_text("No hay investigaciones registradas.")
        return

    todas.sort(key=lambda x: (x.fecha or "", x.concepto.lower()), reverse=True)

    if context.chat_data is not None:
        context.chat_data[CACHE_RM_INVESTIGACIONES] = [x.id for x in todas]

    lineas: list[str] = []
    for i, inv in enumerate(todas, 1):
        c = (
            (inv.concepto[:INV_RESUMEN_LISTA_MAX] + "...")
            if len(inv.concepto) > INV_RESUMEN_LISTA_MAX
            else inv.concepto
        )
        lineas.append(f"{i}. [{inv.estado}] {c}")

    cabecera = f"Investigaciones ({len(todas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    if len(texto_completo) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_TELEGRAM_MSG])
        await update.message.reply_text(texto_completo[MAX_TELEGRAM_MSG:])


async def cmd_verinvestigacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /verinvestigacion <numero|id>\n"
            "El número es el de /listinvestigaciones en este chat."
        )
        return

    argumento = context.args[0].strip()
    inv: Investigacion | None = None
    if argumento.isdigit():
        n = int(argumento)
        cache = (context.chat_data or {}).get(CACHE_RM_INVESTIGACIONES) or []
        if n < 1 or n > len(cache):
            await update.message.reply_text(
                "Índice inválido o lista antigua. Ejecuta /listinvestigaciones primero en este chat."
            )
            return
        inv = buscar_investigacion_por_id(cache[n - 1])
    else:
        inv = buscar_investigacion_por_id(argumento)

    if not inv:
        await update.message.reply_text(
            "No se encontró esa investigación.\nUsa /listinvestigaciones para ver el listado."
        )
        return

    await _reply_texto_largo(update, _formatear_investigacion_completa(inv))


async def cmd_rminvestigacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rminvestigacion <numero> [numero ...]\n"
            "Los números son los de /listinvestigaciones en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text(
            "Solo números del listado, separados por espacios."
        )
        return

    cache = (context.chat_data or {}).get(CACHE_RM_INVESTIGACIONES) or []
    fuera: list[int] = []
    vistos: set[str] = set()
    ids_objetivo: list[str] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        iid = cache[n - 1]
        if iid not in vistos:
            vistos.add(iid)
            ids_objetivo.append(iid)

    if not ids_objetivo:
        msg = "Ningún número válido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listinvestigaciones en este chat."
        await update.message.reply_text(msg)
        return

    ok_n = 0
    fallo_almacen = 0
    for iid in ids_objetivo:
        if eliminar_investigacion_db(iid):
            ok_n += 1
            p = _ruta_md_investigacion(iid)
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        else:
            fallo_almacen += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_INVESTIGACIONES, None)

    partes = [f"Investigaciones eliminadas: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if fallo_almacen:
        partes.append(f"No se pudieron borrar: {fallo_almacen}.")
    await update.message.reply_text(" ".join(partes))


async def cmd_listfunc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    todas = listar_func()
    if not todas:
        await update.message.reply_text("No hay funcionalidades registradas.")
        return

    todas.sort(key=lambda f: (-f.prioridad, f.texto.lower()))

    if context.chat_data is not None:
        context.chat_data[CACHE_RM_FUNC_IDS] = [f.id for f in todas]

    lineas: list[str] = []
    for i, f in enumerate(todas, 1):
        emoji = _PRIORIDAD_EMOJI.get(f.prioridad, "")
        txt = (
            (f.texto[:FUNC_RESUMEN_MAX] + "...")
            if len(f.texto) > FUNC_RESUMEN_MAX
            else f.texto
        )
        lineas.append(f"{i}. {emoji} P{f.prioridad} {txt}")

    cabecera = f"Funcionalidades ({len(todas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


def _formatear_funcionalidad_completa(f: Funcionalidad) -> str:
    emoji = _PRIORIDAD_EMOJI.get(f.prioridad, "")
    return (
        f"Prioridad: {emoji} {f.prioridad}/5\n"
        f"Fecha: {formatear_fecha_ver(f.fecha_ingesta)}\n"
        f"Fuente: {f.fuente}\n\n"
        f"Texto:\n{f.texto}"
    )


async def cmd_verfunc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /verfunc <numero>\n"
            "El numero es el de /listfunc en este chat."
        )
        return

    argumento = context.args[0].strip()
    func: Funcionalidad | None = None
    if argumento.isdigit():
        n = int(argumento)
        cache = (context.chat_data or {}).get(CACHE_RM_FUNC_IDS) or []
        if n < 1 or n > len(cache):
            await update.message.reply_text(
                "Indice invalido o lista antigua. Ejecuta /listfunc primero en este chat."
            )
            return
        func = buscar_func_por_id(cache[n - 1])
    else:
        func = buscar_func_por_id(argumento)

    if not func:
        await update.message.reply_text(
            "No se encontro esa funcionalidad.\nUsa /listfunc para ver el listado."
        )
        return

    await _reply_texto_largo(update, _formatear_funcionalidad_completa(func))


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

    iso_rel, resto_rel = extraer_fecha_relativa_iso_y_resto(texto)
    if iso_rel:
        return iso_rel, resto_rel

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
    rel, resto_rel = extraer_fecha_relativa_dd_mm_yyyy(texto)
    if rel:
        return rel, resto_rel

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


def _partir_audio_para_el(contenido: str) -> tuple[str, str]:
    """
    Divide el payload de voz en (antes, despues) usando la frase 'para el'.
    Si no aparece, (contenido.strip(), '').
    """
    texto = " ".join((contenido or "").split()).strip()
    if not texto:
        return "", ""
    m = re.search(r"\bpara el\b", texto, flags=re.IGNORECASE)
    if not m:
        return texto, ""
    antes = texto[: m.start()].strip()
    despues = texto[m.end() :].strip()
    return antes, despues


def _parsear_tarea_audio_payload(contenido: str) -> tuple[str, str | None, str]:
    """
    Tarea por voz: con 'para el', el título va antes y la fecha (y resto) después.
    Sin 'para el', mismo criterio que _parsear_args_tarea sobre el texto completo.
    """
    antes, despues = _partir_audio_para_el(contenido)
    if despues.strip():
        titulo, _, desc_titulo = _parsear_args_tarea(antes)
        fecha, resto_tras_fecha = _extraer_fecha_iso_y_resto(despues.strip())
        partes_desc = [
            (desc_titulo or "").strip(),
            (resto_tras_fecha or "").strip() if resto_tras_fecha else "",
        ]
        descripcion = " ".join(x for x in partes_desc if x).strip()
        return strip_sufijo_para_el(titulo.strip()), fecha, descripcion
    tit, fec, desc = _parsear_args_tarea(contenido)
    return strip_sufijo_para_el(tit), fec, desc


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


def _parsear_evento_audio_payload(contenido: str) -> tuple[str, str | None, str | None]:
    """Evento por voz: con 'para el', nombre antes y fecha/hora después."""
    antes, despues = _partir_audio_para_el(contenido)
    if despues.strip():
        n2, fecha_ev, hora_ev = _parsear_args_evento(despues)
        nombre = (antes.strip() or n2.strip()).strip()
        return strip_sufijo_para_el(nombre), fecha_ev, hora_ev
    nom, fe, ho = _parsear_args_evento(contenido)
    if not fe:
        nom = strip_sufijo_para_el(nom)
    return nom, fe, ho


async def _ejecutar_creacion_tarea_deck(
    update: Update,
    texto_raw: str,
    *,
    stack_name: str | None = None,
    prefijo_exito: str = "Tarea creada",
) -> bool:
    titulo, fecha, descripcion = _parsear_args_tarea(texto_raw)
    if not titulo:
        await update.message.reply_text("El titulo de la tarea no puede estar vacio.")
        return False

    if fecha:
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                f"Fecha invalida: {fecha}\n"
                "Usa DD-MM-AAAA, DD-MM, solo DD (mes actual) o YYYY-MM-DD."
            )
            return False

    msg = await update.message.reply_text("Creando tarea en Deck...")
    ok = crear_tarea_deck(
        titulo,
        descripcion=descripcion,
        fecha_due=fecha,
        stack_name=stack_name,
        assigned_user_uids=_deck_uids_para_update(update),
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
        aviso_asg = obtener_ultimo_aviso_asignacion_deck()
        if aviso_asg:
            partes.append(aviso_asg)
        await msg.edit_text("\n".join(partes))
        return True
    deck_error = obtener_ultimo_error_deck()
    await msg.edit_text(
        "No se pudo crear la tarea en Deck.\n"
        f"{deck_error or 'sin detalle'}"
    )
    return False


async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/tarea"):
        texto_raw = texto_raw[len("/tarea") :].strip()

    if not texto_raw:
        await update.message.reply_text(
            'Uso: /tarea "Titulo" [fecha] ["Descripcion"]\n'
            'Ejemplo: /tarea "Comprar material" 25-03-2026 "Para laboratorio"\n'
            "Fecha: DD-MM-AAAA, DD-MM, DD, YYYY-MM-DD, o antier/ayer/hoy/mañana/pasado.\n"
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
            "Fecha: DD-MM-AAAA, DD-MM, DD, YYYY-MM-DD o antier/ayer/hoy/mañana/pasado (opcional)."
        )
        return

    await _ejecutar_creacion_tarea_deck(
        update,
        texto_raw,
        stack_name=DECK_STACK_COMPRAR,
        prefijo_exito="Compra anotada",
    )


async def _ejecutar_creacion_evento_desde_texto(update: Update, texto_raw: str) -> bool:
    """Crea evento CalDAV desde texto ya sin prefijo /evento. Devuelve True si se creó."""
    nombre, fecha_ev, hora_ev = _parsear_args_evento(texto_raw)

    if not nombre:
        await update.message.reply_text("El nombre del evento no puede estar vacio.")
        return False
    if not fecha_ev:
        await update.message.reply_text(
            "Falta una fecha reconocible (ej. 20-03-2026, 20-03, 20/3/26, dia unico 1-31, "
            "o antier/ayer/hoy/mañana/pasado)."
        )
        return False

    fecha_iso = _fecha_evento_ddmmyyyy_a_iso(fecha_ev)
    if fecha_iso is None:
        await update.message.reply_text(
            f"Fecha invalida: {fecha_ev}\n"
            "Usa dia-mes-año con / o -; año de 2 cifras; sin año = año actual; "
            "un solo numero 1-31 = dia en el mes actual."
        )
        return False

    if hora_ev:
        try:
            datetime.strptime(hora_ev, "%H:%M")
        except ValueError:
            await update.message.reply_text(
                f"Hora invalida: {hora_ev}\nUsa formato HH:MM en 24 h (ej. 14:30)"
            )
            return False

    msg = await update.message.reply_text("Creando evento en el calendario...")
    ok = crear_evento(nombre, fecha_iso, hora=hora_ev)

    if ok:
        partes = [f"Evento creado: {nombre}", f"Fecha: {fecha_ev}"]
        if hora_ev:
            partes.append(f"Hora inicio: {hora_ev} (duracion 1 h)")
        await msg.edit_text("\n".join(partes))
        return True
    err = obtener_ultimo_error_evento()
    await msg.edit_text("No se pudo crear el evento en CalDAV.\n" + (err or "sin detalle"))
    return False


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
            "Fecha: DD-MM-AAAA o DD/MM/AAAA; año 2 cifras -> 20YY; DD-MM sin año = año actual; "
            "solo DD (1-31, unico en el texto) = mes actual; o antier/ayer/hoy/mañana/pasado.\n"
            "Ejemplo: /evento Reunion 20-03-26 14:30"
        )
        return

    await _ejecutar_creacion_evento_desde_texto(update, texto_raw)


async def cmd_listeventos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmevento <numero> [numero ...]\n"
            "Los numeros son los de la ultima lista de /listeventos en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text(
            "Solo numeros del listado, separados por espacios."
        )
        return

    cache = (context.chat_data or {}).get(CACHE_RM_EVENTOS) or []
    fuera: list[int] = []
    pares: list[tuple[int, str]] = []
    vistos: set[int] = set()
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        if n in vistos:
            continue
        vistos.add(n)
        u = (cache[n - 1] or "").strip()
        pares.append((n, u))

    if not pares:
        msg = "Ningun numero valido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listeventos en este chat."
        await update.message.reply_text(msg)
        return

    ok_n = 0
    sin_url = 0
    fallo_borrar = 0
    ultimo_err = ""
    for n, url in pares:
        if not url:
            sin_url += 1
            continue
        if borrar_evento_por_url(url):
            ok_n += 1
        else:
            fallo_borrar += 1
            ultimo_err = obtener_ultimo_error_evento() or ""

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_EVENTOS, None)

    partes = [f"Eventos eliminados del calendario: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if sin_url:
        partes.append(f"Sin enlace interno para borrar: {sin_url}.")
    if fallo_borrar:
        partes.append(f"No se pudieron borrar: {fallo_borrar}.")
        if ultimo_err:
            partes.append(ultimo_err[:200])
    await update.message.reply_text(" ".join(partes))


async def cmd_verevento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /verevento <numero>\n"
            "El numero es el de la ultima lista de /listeventos en este chat."
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
            "Indice invalido o lista antigua. Ejecuta /listeventos primero en este chat."
        )
        return

    url = (cache[n - 1] or "").strip()
    if not url:
        await update.message.reply_text("No se pudo obtener el evento para mostrar.")
        return

    detalle = formatear_detalle_evento_por_url(url)
    if not detalle:
        err = obtener_ultimo_error_evento()
        await update.message.reply_text(
            "No se pudo leer el evento.\n" + (err or "sin detalle")
        )
        return

    await _reply_texto_largo(update, detalle)


async def cmd_rmfunc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmfunc <numero> [numero ...]\n"
            "Los numeros son los de /listfunc en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text(
            "Solo numeros del listado, separados por espacios."
        )
        return

    cache = (context.chat_data or {}).get(CACHE_RM_FUNC_IDS) or []
    fuera: list[int] = []
    vistos: set[str] = set()
    ids_objetivo: list[str] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        fid = cache[n - 1]
        if fid not in vistos:
            vistos.add(fid)
            ids_objetivo.append(fid)

    if not ids_objetivo:
        msg = "Ningun numero valido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listfunc en este chat."
        await update.message.reply_text(msg)
        return

    ok_n = 0
    fallo_almacen = 0
    for fid in ids_objetivo:
        if eliminar_func_db(fid):
            ok_n += 1
        else:
            fallo_almacen += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_FUNC_IDS, None)

    partes = [f"Funcionalidades eliminadas: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if fallo_almacen:
        partes.append(f"No se pudieron borrar: {fallo_almacen}.")
    await update.message.reply_text(" ".join(partes))


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
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmtarea <numero> [numero ...]\n"
            "Los numeros son los de la ultima lista de /listtareas en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text(
            "Solo numeros del listado, separados por espacios."
        )
        return

    cache = (context.chat_data or {}).get(CACHE_RM_TAREAS_DECK) or []
    fuera: list[int] = []
    items_a_borrar: list[tuple[int, dict]] = []
    vistos: set[int] = set()
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        if n in vistos:
            continue
        vistos.add(n)
        items_a_borrar.append((n, cache[n - 1]))

    if not items_a_borrar:
        msg = "Ningun numero valido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listtareas en este chat."
        await update.message.reply_text(msg)
        return

    ok_n = 0
    fallo = 0
    ultimo_err = ""
    for _n, item in items_a_borrar:
        ok = borrar_tarjeta_deck(
            int(item["board_id"]),
            int(item["stack_id"]),
            int(item["card_id"]),
        )
        if ok:
            ok_n += 1
        else:
            fallo += 1
            ultimo_err = obtener_ultimo_error_deck() or ""

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_TAREAS_DECK, None)

    partes = [f"Tareas eliminadas de Deck: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if fallo:
        partes.append(f"No se pudieron borrar: {fallo}.")
        if ultimo_err:
            partes.append(ultimo_err[:200])
    await update.message.reply_text(" ".join(partes))


def _formatear_tarjeta_deck_detalle(d: dict) -> str:
    labels = ", ".join(d.get("labels") or []) or "(ninguna)"
    return (
        f"Titulo: {d.get('title') or '(sin titulo)'}\n"
        f"Columna: {d.get('stack_title') or '(desconocida)'}\n"
        f"Vencimiento (Deck): {d.get('duedate') or '(sin fecha)'}\n"
        f"Etiquetas: {labels}\n\n"
        f"Descripcion:\n{d.get('description') or '(vacia)'}"
    )


async def cmd_vertarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /vertarea <numero>\n"
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
    d = obtener_tarjeta_deck(
        int(item["board_id"]),
        int(item["stack_id"]),
        int(item["card_id"]),
    )
    if not d:
        err = obtener_ultimo_error_deck()
        await update.message.reply_text(
            "No se pudo leer la tarjeta.\n" + (err or "sin detalle")
        )
        return

    await _reply_texto_largo(update, _formatear_tarjeta_deck_detalle(d))


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
    añadir_huevo(cantidad, hoy, fuente="telegram")
    total_dia = total_cantidad_en_fecha(hoy)
    await update.message.reply_text(
        f"Registro de huevos guardado.\n"
        f"Fecha: {hoy}\n"
        f"Esta vez: {cantidad}\n"
        f"Total del dia: {total_dia}"
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


async def cmd_diario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /diario <texto>\nGuarda una entrada en el diario del dia (y en diario.csv).")
        return
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("El texto del diario no puede estar vacio.")
        return
    usr = update.effective_user
    etiqueta = (usr.username or str(usr.id)) if usr else ""
    try:
        ent = diario_añadir_entrada(texto, fuente="telegram_texto", telegram_user=etiqueta)
    except ValueError:
        await update.message.reply_text("El texto del diario no puede estar vacio.")
        return
    await update.message.reply_text(
        f"Entrada de diario guardada.\nDia: {ent.fecha_dia}\nArchivo: {ent.ruta}"
    )


async def cmd_listpendientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    items = listar_pendientes_recientes()
    if not items:
        await update.message.reply_text("No hay pendientes en pendientes.csv.")
        return
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_PENDIENTES_IDS] = [p.id for p in items]
    lineas: list[str] = []
    for i, p in enumerate(items, 1):
        res = (p.texto or "").strip() or "(vacio)"
        if len(res) > PENDIENTE_RESUMEN_LISTA_MAX:
            res = res[:PENDIENTE_RESUMEN_LISTA_MAX] + "..."
        u = (p.username or "").strip() or p.user_id
        lineas.append(f"{i}. [{p.id}] @{u}: {res}")
    cabecera = f"Pendientes ({len(items)}), mas recientes primero:\n\n"
    texto_completo = cabecera + "\n\n".join(lineas)
    if len(texto_completo) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_TELEGRAM_MSG])


async def cmd_verpendiente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /verpendiente <n|id>\nEl numero es el de /listpendientes en este chat."
        )
        return
    argumento = context.args[0].strip()
    p: Pendiente | None = None
    if argumento.isdigit():
        n = int(argumento)
        cache = (context.chat_data or {}).get(CACHE_RM_PENDIENTES_IDS) or []
        if 1 <= n <= len(cache):
            p = buscar_pendiente_por_id(cache[n - 1])
    if p is None:
        p = buscar_pendiente_por_id(argumento)
    if not p:
        await update.message.reply_text(
            "No se encontro ese pendiente.\nUsa /listpendientes en este chat."
        )
        return
    u = (p.username or "").strip() or p.user_id
    cuerpo = (
        f"ID: {p.id}\n"
        f"Usuario: @{u} (id {p.user_id})\n"
        f"Fecha: {formatear_fecha_ver(p.fecha_ingesta)}\n"
        f"Fuente: {p.fuente}\n\n"
        f"--- Texto ---\n{p.texto or '(vacio)'}"
    )
    await _reply_texto_largo(update, cuerpo)


async def cmd_rmpendientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmpendientes <numero> [numero ...]\n"
            "Los numeros son los de /listpendientes en este chat."
        )
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros and enteros:
        await update.message.reply_text(
            "Usa solo numeros del listado separados por espacios, o un solo id."
        )
        return
    ids_objetivo: list[str] = []
    fuera: list[int] = []
    if otros:
        if len(otros) != 1:
            await update.message.reply_text("Para borrar por id solo se admite un token.")
            return
        ids_objetivo = [otros[0].strip()]
    else:
        cache = (context.chat_data or {}).get(CACHE_RM_PENDIENTES_IDS) or []
        vistos: set[str] = set()
        for n in enteros:
            if n < 1 or n > len(cache):
                fuera.append(n)
                continue
            tid = cache[n - 1]
            if tid not in vistos:
                vistos.add(tid)
                ids_objetivo.append(tid)
        if not ids_objetivo:
            msg = "Ningun numero valido."
            if fuera:
                msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listpendientes en este chat."
            await update.message.reply_text(msg)
            return
    ok_n = 0
    no_encontrados = 0
    for target_id in ids_objetivo:
        if eliminar_pendiente_db(target_id):
            ok_n += 1
        else:
            no_encontrados += 1
    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_PENDIENTES_IDS, None)
    partes = [f"Pendientes eliminados: {ok_n}."]
    if not otros and fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if no_encontrados:
        partes.append(f"No encontrados: {no_encontrados}.")
    await update.message.reply_text(" ".join(partes))


async def cmd_mvpendiente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    args = list(context.args or [])
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /mvpendiente <n|id> <tipo> [args extra]\n"
            "tipo: idea, tarea, evento, funcionalidad (o func), investiga, comprar, diario\n"
            "Ejemplo: /mvpendiente 1 tarea \"Titulo\" 25-03-2026"
        )
        return
    id_o_n = args[0].strip()
    tipo_in = args[1].strip().lower()
    extras = args[2:]
    tipo = "funcionalidad" if tipo_in == "func" else tipo_in
    if tipo not in _TIPOS_MV_VALIDOS:
        await update.message.reply_text(
            f"Tipo no valido: {tipo_in}. Usa: {', '.join(sorted(_TIPOS_MV_VALIDOS))} o func"
        )
        return

    p: Pendiente | None = None
    if id_o_n.isdigit():
        n = int(id_o_n)
        cache = (context.chat_data or {}).get(CACHE_RM_PENDIENTES_IDS) or []
        if 1 <= n <= len(cache):
            p = buscar_pendiente_por_id(cache[n - 1])
    if p is None:
        p = buscar_pendiente_por_id(id_o_n)
    if not p:
        await update.message.reply_text(
            "No se encontro ese pendiente.\nUsa /listpendientes en este chat."
        )
        return

    combo = p.texto.strip()
    if extras:
        combo = f"{combo} {' '.join(extras)}".strip()

    ok_fin = False
    if tipo == "idea":
        idea = _guardar_idea(combo, fuente="telegram_mvpendiente")
        ok_fin = True
        await update.message.reply_text(f"Movido a idea.\nResumen: {idea.resumen}")
    elif tipo == "tarea":
        if await _ejecutar_creacion_tarea_deck(
            update, combo, stack_name=None, prefijo_exito="Tarea creada"
        ):
            ok_fin = True
    elif tipo == "comprar":
        if await _ejecutar_creacion_tarea_deck(
            update,
            combo,
            stack_name=DECK_STACK_COMPRAR,
            prefijo_exito="Compra anotada",
        ):
            ok_fin = True
    elif tipo == "evento":
        if await _ejecutar_creacion_evento_desde_texto(update, combo):
            ok_fin = True
    elif tipo == "funcionalidad":
        tf, pri = _parsear_funcionalidad_audio(combo)
        if not tf.strip():
            await update.message.reply_text("Texto de funcionalidad vacio.")
            return
        func = Funcionalidad(
            id=_generar_id_func(tf),
            texto=tf,
            prioridad=pri,
            estado="pendiente",
            fecha_ingesta=datetime.now().isoformat(),
            fuente="telegram_mvpendiente",
        )
        añadir_func(func)
        ok_fin = True
        emoji = _PRIORIDAD_EMOJI.get(pri, "")
        await update.message.reply_text(
            f"Movido a funcionalidad.\n{tf}\nPrioridad: {emoji} {pri}/5"
        )
    elif tipo == "investiga":
        inv = Investigacion(
            id=_generar_id_investigacion(combo),
            fecha=datetime.now().isoformat(),
            estado="pendiente",
            concepto=combo,
            resumen="",
            link="",
        )
        añadir_investigacion(inv)
        ok_fin = True
        await update.message.reply_text(
            f"Movido a investigacion encolada.\nID: {inv.id}\nConcepto: {inv.concepto}"
        )
    elif tipo == "diario":
        usr = update.effective_user
        etiqueta = (usr.username or str(usr.id)) if usr else ""
        try:
            ent = diario_añadir_entrada(
                combo, fuente="telegram_mvpendiente", telegram_user=etiqueta
            )
        except ValueError:
            await update.message.reply_text("Texto del diario vacio.")
            return
        ok_fin = True
        await update.message.reply_text(
            f"Movido a diario.\nDia: {ent.fecha_dia}\nArchivo: {ent.ruta}"
        )

    if ok_fin:
        eliminar_pendiente_db(p.id)
        if context.chat_data is not None:
            context.chat_data.pop(CACHE_RM_PENDIENTES_IDS, None)


async def cmd_rmconvo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmconvo <numero> [numero ...]\n"
            "Los numeros son los de /listconvo en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros and enteros:
        await update.message.reply_text(
            "Usa solo numeros del listado separados por espacios, o un solo criterio interno."
        )
        return

    ids_objetivo: list[str] = []
    fuera: list[int] = []
    if otros:
        if len(otros) != 1:
            await update.message.reply_text(
                "Para borrar por criterio interno solo se admite un token."
            )
            return
        ids_objetivo = [otros[0].strip()]
    else:
        cache = (context.chat_data or {}).get(CACHE_RM_CONVOS) or []
        vistos: set[str] = set()
        for n in enteros:
            if n < 1 or n > len(cache):
                fuera.append(n)
                continue
            tid = cache[n - 1]
            if tid not in vistos:
                vistos.add(tid)
                ids_objetivo.append(tid)
        if not ids_objetivo:
            msg = "Ningun numero valido."
            if fuera:
                msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listconvo en este chat."
            await update.message.reply_text(msg)
            return

    ok_n = 0
    no_encontradas = 0
    error_almacen = 0
    for target_id in ids_objetivo:
        conv = buscar_por_id(target_id)
        if not conv:
            no_encontradas += 1
            continue
        if eliminar_por_id(conv.id):
            ok_n += 1
        else:
            error_almacen += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_CONVOS, None)

    partes = [f"Convocatorias eliminadas: {ok_n}."]
    if not otros and fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if no_encontradas:
        partes.append(f"No encontradas: {no_encontradas}.")
    if error_almacen:
        partes.append(f"Error al borrar en almacen: {error_almacen}.")
    await update.message.reply_text(" ".join(partes))


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
    await msg.edit_text(f"Convocatoria añadida: {titulo_show}")


def _formatear_enlace_completo(enlace: Enlace) -> str:
    return (
        f"URL: {enlace.url}\n"
        f"Tags: {enlace.tags or '(ninguno)'}\n"
        f"Categorias: {enlace.categorias or '(ninguna)'}\n"
        f"Notas: {enlace.notas or '(ninguna)'}\n"
        f"Fecha: {formatear_fecha_ver(enlace.fecha_ingesta)}\n"
        f"Fuente: {enlace.fuente}"
    )


async def _procesar_url_enlace_guardar(
    update: Update,
    url: str,
    *,
    notas: str = "",
    fuente: str = "telegram_url_suelta",
) -> None:
    """Guarda una URL en enlaces.csv (sin duplicar por URL exacta)."""
    msg = await update.message.reply_text("Guardando enlace...")
    if buscar_enlace_por_url(url):
        await msg.edit_text("Este enlace ya esta en la lista de enlaces.")
        return
    eid = _generar_id(url)
    enlace = Enlace(
        id=eid,
        url=url.strip(),
        tags="",
        categorias="",
        notas=(notas or "").strip(),
        fecha_ingesta=datetime.now().isoformat(),
        fuente=fuente,
    )
    añadir_enlace(enlace)
    await msg.edit_text("Enlace guardado.")


async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/url"):
        texto_raw = texto_raw[len("/url") :].strip()
    if not texto_raw:
        await update.message.reply_text(
            "Uso: /url <https://...> [notas opcionales]\n"
            "Puedes pegar la URL en el mismo mensaje; el resto se guarda como notas."
        )
        return
    url = _extraer_url(texto_raw)
    if not url:
        await update.message.reply_text("No se detecto una URL valida (https://...).")
        return
    notas = texto_raw.replace(url, "", 1).strip()
    await _procesar_url_enlace_guardar(update, url, notas=notas, fuente="telegram_comando")


async def cmd_listurl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    enlaces = leer_enlaces()
    if not enlaces:
        await update.message.reply_text("No hay enlaces en enlaces.csv.")
        return

    enlaces.sort(key=lambda e: (e.fecha_ingesta or "", e.id), reverse=True)
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_ENLACES] = [e.id for e in enlaces]

    lineas: list[str] = []
    for i, e in enumerate(enlaces, 1):
        u = e.url.strip()
        if len(u) > ENLACE_RESUMEN_LISTA_MAX:
            u = u[:ENLACE_RESUMEN_LISTA_MAX] + "..."
        lineas.append(f"{i}. {u}")

    cabecera = f"Enlaces ({len(enlaces)}), mas recientes primero:\n\n"
    texto_completo = cabecera + "\n\n".join(lineas)
    if len(texto_completo) <= 4000:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:4000])
        await update.message.reply_text(texto_completo[4000:])


async def cmd_verurl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Uso: /verurl <numero>\n"
            "El numero es el de /listurl en este chat."
        )
        return
    argumento = context.args[0].strip()
    if not argumento.isdigit():
        await update.message.reply_text("El numero debe ser un entero (ej. 1).")
        return
    n = int(argumento)
    cache = (context.chat_data or {}).get(CACHE_RM_ENLACES) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text(
            "Indice invalido o lista antigua. Ejecuta /listurl primero en este chat."
        )
        return
    enlace = buscar_enlace_por_id(cache[n - 1])
    if not enlace:
        await update.message.reply_text(
            "No se encontro ese enlace.\nUsa /listurl para refrescar el listado."
        )
        return
    await _reply_texto_largo(update, _formatear_enlace_completo(enlace))


async def cmd_rmurl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmurl <numero> [numero ...]\n"
            "Los numeros son los de /listurl en este chat."
        )
        return

    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text(
            "Solo numeros del listado, separados por espacios."
        )
        return

    cache = (context.chat_data or {}).get(CACHE_RM_ENLACES) or []
    fuera: list[int] = []
    vistos: set[str] = set()
    ids_objetivo: list[str] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        eid = cache[n - 1]
        if eid not in vistos:
            vistos.add(eid)
            ids_objetivo.append(eid)

    if not ids_objetivo:
        msg = "Ningun numero valido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listurl en este chat."
        await update.message.reply_text(msg)
        return

    ok_n = 0
    fallo = 0
    for eid in ids_objetivo:
        if eliminar_enlace_por_id(eid):
            ok_n += 1
        else:
            fallo += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_ENLACES, None)

    partes = [f"Enlaces eliminados: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if fallo:
        partes.append(f"No se pudieron borrar: {fallo}.")
    await update.message.reply_text(" ".join(partes))


CONTABILIDAD_RESUMEN_LISTA_MAX = 52


def _formatear_factura_completa(f: FacturaContabilidad) -> str:
    ff = (f.fecha_factura or "").strip()
    ff_disp = formatear_fecha_ver(ff) if ff else "(sin fecha)"
    fs = (f.fecha_subida or "").strip()
    fs_disp = formatear_fecha_ver(fs) if fs else "(sin fecha subida)"
    return (
        f"ID: {f.id}\n"
        f"Numero factura: {f.numero_factura or '(vacio)'}\n"
        f"Fecha factura: {ff_disp}\n"
        f"Proveedor: {f.nombre_proveedor or '(vacio)'}\n"
        f"CIF: {f.cif_proveedor or '(vacio)'}\n"
        f"Direccion: {f.direccion_proveedor or '(vacio)'}\n"
        f"Base: {f.base_imponible or '(vacio)'}\n"
        f"IVA: {f.iva or '(vacio)'}\n"
        f"Total: {f.total or '(vacio)'}\n"
        f"Ruta Nextcloud: {f.ruta_nextcloud or '(vacio)'}\n"
        f"Fecha subida: {fs_disp}\n"
        f"Fuente: {f.fuente or '(vacio)'}"
    )


def _texto_menu_mod_factura(factura_id: str) -> str:
    lineas = [
        f"Modificando factura (id {factura_id}). Elige campo (0 = salir):",
    ]
    for i, (_k, label) in enumerate(CAMPOS_EDITABLES_MOD, 1):
        lineas.append(f"{i}. {label}")
    return "\n".join(lineas)


async def _manejar_wizard_mod_factura(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    wizard = context.chat_data.get(WIZARD_MOD_FACTURA_KEY)
    if not wizard:
        return False
    user = update.effective_user
    if not user or wizard.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        return False
    fid = wizard["factura_id"]
    fase = wizard.get("fase", "menu")

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_FACTURA_KEY, None)
            await update.message.reply_text("Listo (sin mas cambios).")
            return True
        if not text.isdigit():
            await update.message.reply_text("Envia un numero de campo o 0 para salir.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_EDITABLES_MOD):
            await update.message.reply_text("Numero invalido.")
            return True
        key, label = CAMPOS_EDITABLES_MOD[n - 1]
        wizard["fase"] = "valor"
        wizard["campo_key"] = key
        await update.message.reply_text(
            f"Nuevo valor para: {label}\n"
            f"(una linea; envia '-' para dejar vacio)\n/cancelarmodfactura para abortar."
        )
        return True

    key = wizard.get("campo_key")
    if not key:
        wizard["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_factura(fid))
        return True
    val = "" if text == "-" else text
    if not actualizar_factura_campos(fid, {key: val}):
        await update.message.reply_text("No se pudo guardar (id invalido?).")
        context.chat_data.pop(WIZARD_MOD_FACTURA_KEY, None)
        return True
    wizard["fase"] = "menu"
    wizard.pop("campo_key", None)
    await update.message.reply_text(
        "Campo actualizado.\n\n" + _texto_menu_mod_factura(fid)
    )
    return True


async def cmd_factura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is None:
        await update.message.reply_text("No se pudo guardar estado en este chat.")
        return
    context.chat_data[ESPERANDO_FACTURA_KEY] = True
    await update.message.reply_text(
        "Envia una foto de la factura o un documento PDF. "
        "Se subira a Nextcloud y se registrara en contabilidad.csv.\n"
        "/cancelarfactura si cambias de idea."
    )


async def cmd_cancelarfactura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(ESPERANDO_FACTURA_KEY, None)
    await update.message.reply_text("Cancelado: ya no espero archivo de factura.")


async def cmd_cancelarmodfactura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_FACTURA_KEY, None)
    await update.message.reply_text("Edicion de factura cancelada.")


async def manejar_archivo_factura(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    msg = update.message
    if not msg or context.chat_data is None:
        return
    if not context.chat_data.get(ESPERANDO_FACTURA_KEY):
        return

    archivo = None
    sufijo = ".bin"
    nombre_sugerido: str | None = None

    if msg.photo:
        archivo = await context.bot.get_file(msg.photo[-1].file_id)
        sufijo = ".jpg"
        nombre_sugerido = f"factura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    elif msg.document:
        mime = (msg.document.mime_type or "").lower()
        if "pdf" not in mime:
            await msg.reply_text("Solo se acepta PDF o imagen (foto).")
            return
        archivo = await context.bot.get_file(msg.document.file_id)
        sufijo = ".pdf"
        raw_name = (msg.document.file_name or "").strip()
        nombre_sugerido = raw_name if raw_name.lower().endswith(".pdf") else None
        if not nombre_sugerido:
            nombre_sugerido = f"factura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    else:
        return

    context.chat_data[ESPERANDO_FACTURA_KEY] = False
    estado = await msg.reply_text("Descargando y procesando factura...")
    ruta_tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
            ruta_tmp = Path(tmp.name)
        await archivo.download_to_drive(custom_path=str(ruta_tmp))
        data = ruta_tmp.read_bytes()

        texto_plano = ""
        if sufijo == ".pdf":
            texto_plano = texto_desde_pdf(data)
        else:
            texto_plano = texto_desde_imagen(data)

        campos = extraer_campos_desde_texto(texto_plano)
        fecha_norm = normalizar_fecha_iso(campos.get("fecha_factura") or "")
        if fecha_norm:
            d_parts = fecha_norm.split("-")
            y, mo, da = int(d_parts[0]), int(d_parts[1]), int(d_parts[2])
            d = date(y, mo, da)
        else:
            d = fecha_hoy_relativas()
        tq = trimestre_desde_fecha(d.year, d.month)
        nombre_nc = nombre_archivo_seguro(nombre_sugerido or f"factura{sufijo}")
        rel_nc = f"{d.year}/Gastos/{tq}/{nombre_nc}"
        ok_up = subir_archivo_facturas(rel_nc, data)
        ruta_completa = (
            f"{config.NEXTCLOUD_FACTURAS_PATH}/{rel_nc}" if ok_up else ""
        )
        fecha_subida = datetime.now().isoformat()
        row = añadir_factura(
            numero_factura=campos.get("numero_factura") or "",
            fecha_factura=fecha_norm or "",
            nombre_proveedor=campos.get("nombre_proveedor") or "",
            cif_proveedor=campos.get("cif_proveedor") or "",
            direccion_proveedor=campos.get("direccion_proveedor") or "",
            base_imponible=campos.get("base_imponible") or "",
            iva=campos.get("iva") or "",
            total=campos.get("total") or "",
            ruta_nextcloud=ruta_completa,
            fecha_subida=fecha_subida,
            fuente="telegram_factura",
        )
        lineas = [
            f"Factura registrada (id {row.id}).",
            f"CSV: contabilidad.csv",
        ]
        if ok_up:
            lineas.append(f"Nextcloud: {ruta_completa}")
        else:
            lineas.append(
                "Aviso: no se pudo subir a Nextcloud (revisa URL/usuario/clave y ruta)."
            )
        lineas.append("")
        lineas.append("Datos extraidos (revisa con /modfactura si hace falta):")
        lineas.append(_formatear_factura_completa(row))
        await estado.edit_text("\n".join(lineas)[:MAX_TELEGRAM_MSG])
    except Exception as exc:
        await estado.edit_text(f"No se pudo procesar la factura: {exc}")
    finally:
        if ruta_tmp and ruta_tmp.exists():
            try:
                ruta_tmp.unlink()
            except OSError:
                pass


async def cmd_listcontabilidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    todas = listar_facturas_recientes()
    if not todas:
        await update.message.reply_text("No hay filas en contabilidad.csv.")
        return
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_CONTABILIDAD_IDS] = [x.id for x in todas]
    lineas: list[str] = []
    for i, r in enumerate(todas, 1):
        prov = (r.nombre_proveedor or "(sin proveedor)")[:CONTABILIDAD_RESUMEN_LISTA_MAX]
        num = (r.numero_factura or "?")[:20]
        lineas.append(f"{i}. [{num}] {prov}")
    texto = f"Contabilidad ({len(todas)}), recientes primero:\n\n" + "\n".join(lineas)
    if len(texto) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto)
    else:
        await update.message.reply_text(texto[:MAX_TELEGRAM_MSG])


async def cmd_verfactura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /verfactura <n|id>\nEl numero es el de /listcontabilidad en este chat."
        )
        return
    arg = context.args[0].strip()
    frow: FacturaContabilidad | None = None
    if arg.isdigit():
        n = int(arg)
        cache = (context.chat_data or {}).get(CACHE_RM_CONTABILIDAD_IDS) or []
        if 1 <= n <= len(cache):
            frow = buscar_factura_por_id(cache[n - 1])
    if frow is None:
        frow = buscar_factura_por_id(arg)
    if not frow:
        await update.message.reply_text(
            "No se encontro esa factura.\nUsa /listcontabilidad en este chat."
        )
        return
    await _reply_texto_largo(update, _formatear_factura_completa(frow))


async def cmd_rmfactura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmfactura <n> [n ...]\nLos numeros son los de /listcontabilidad en este chat."
        )
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text(
            "Solo numeros del listado, separados por espacios."
        )
        return
    cache = (context.chat_data or {}).get(CACHE_RM_CONTABILIDAD_IDS) or []
    fuera: list[int] = []
    vistos: set[str] = set()
    ids_objetivo: list[str] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        fid = cache[n - 1]
        if fid not in vistos:
            vistos.add(fid)
            ids_objetivo.append(fid)
    if not ids_objetivo:
        msg = "Ningun numero valido."
        if fuera:
            msg += f" Fuera de rango: {sorted(set(fuera))}."
        await update.message.reply_text(msg)
        return
    ok_n = 0
    for fid in ids_objetivo:
        if eliminar_factura_por_id(fid):
            ok_n += 1
    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_CONTABILIDAD_IDS, None)
    partes = [f"Filas eliminadas de contabilidad: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados: {sorted(set(fuera))}.")
    await update.message.reply_text(" ".join(partes))


async def cmd_modfactura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or context.chat_data is None:
        await update.message.reply_text(
            "Uso: /modfactura <n|id>\nEl numero es el de /listcontabilidad en este chat."
        )
        return
    arg = context.args[0].strip()
    frow: FacturaContabilidad | None = None
    if arg.isdigit():
        n = int(arg)
        cache = (context.chat_data or {}).get(CACHE_RM_CONTABILIDAD_IDS) or []
        if 1 <= n <= len(cache):
            frow = buscar_factura_por_id(cache[n - 1])
    if frow is None:
        frow = buscar_factura_por_id(arg)
    if not frow:
        await update.message.reply_text(
            "No se encontro esa factura.\nUsa /listcontabilidad en este chat."
        )
        return
    user = update.effective_user
    if not user:
        return
    context.chat_data[WIZARD_MOD_FACTURA_KEY] = {
        "user_id": user.id,
        "factura_id": frow.id,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_factura(frow.id) + "\n\n/cancelarmodfactura para salir."
    )


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Si el mensaje contiene una URL suelta, la guarda como enlace sin categorizar."""
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if await _manejar_wizard_mod_factura(update, context):
        return
    if await _manejar_wizard_proyecto(update, context):
        return
    texto = update.message.text or ""
    url = _extraer_url(texto)
    if url:
        await _procesar_url_enlace_guardar(update, url)
    else:
        await update.message.reply_text(
            "Envia una URL para guardarla como enlace, /convo <url> para convocatoria, "
            "o /ayuda para ver comandos."
        )


async def manejar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe audio y enruta según la primera palabra; si no hay acción, pendientes.csv."""
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
                f"Resumen: {idea.resumen}"
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
                f"Texto: {func.texto}\n"
                f"Prioridad: {emoji} {func.prioridad}/5"
            )

        elif accion == "tarea":
            titulo_t, fecha_t, descripcion_t = _parsear_tarea_audio_payload(contenido)
            if not titulo_t:
                await estado.edit_text(
                    "La tarea no puede estar vacia. Di: tarea <titulo> [para el DD-MM-AAAA ...]"
                )
                return
            if fecha_t:
                try:
                    datetime.strptime(fecha_t, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_t}\n"
                        "Tras 'para el': DD-MM-AAAA, DD-MM, DD o YYYY-MM-DD"
                    )
                    return
            ok = crear_tarea_deck(
                titulo_t,
                descripcion=descripcion_t,
                fecha_due=fecha_t,
                assigned_user_uids=_deck_uids_para_update(update),
            )
            if ok:
                lineas = [
                    f"Tarea creada en Deck ({config.DECK_BOARD_NAME}) desde audio.",
                    f"Titulo: {titulo_t}",
                ]
                if fecha_t:
                    lineas.append(f"Fecha limite: {fecha_t}")
                aviso_asg = obtener_ultimo_aviso_asignacion_deck()
                if aviso_asg:
                    lineas.append(aviso_asg)
                await estado.edit_text("\n".join(lineas))
            else:
                deck_error = obtener_ultimo_error_deck()
                await estado.edit_text(
                    "No se pudo crear la tarea en Deck desde audio.\n"
                    f"{deck_error or 'sin detalle'}"
                )

        elif accion == "comprar":
            titulo_c, fecha_c, descripcion_c = _parsear_tarea_audio_payload(contenido)
            if not titulo_c:
                await estado.edit_text(
                    f'La compra no puede estar vacia. Di: comprar <titulo> [para el fecha]\n'
                    f'(columna Deck "{DECK_STACK_COMPRAR}")'
                )
                return
            if fecha_c:
                try:
                    datetime.strptime(fecha_c, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_c}\n"
                        "Tras 'para el': DD-MM-AAAA, DD-MM, DD o YYYY-MM-DD"
                    )
                    return
            ok = crear_tarea_deck(
                titulo_c,
                descripcion=descripcion_c,
                fecha_due=fecha_c,
                stack_name=DECK_STACK_COMPRAR,
                assigned_user_uids=_deck_uids_para_update(update),
            )
            if ok:
                lineas = [
                    f'Compra anotada en Deck ({config.DECK_BOARD_NAME}) [{DECK_STACK_COMPRAR}] desde audio.',
                    f"Titulo: {titulo_c}",
                ]
                if fecha_c:
                    lineas.append(f"Fecha limite: {fecha_c}")
                aviso_asg = obtener_ultimo_aviso_asignacion_deck()
                if aviso_asg:
                    lineas.append(aviso_asg)
                await estado.edit_text("\n".join(lineas))
            else:
                deck_error = obtener_ultimo_error_deck()
                await estado.edit_text(
                    "No se pudo crear la tarjeta de compra en Deck desde audio.\n"
                    f"{deck_error or 'sin detalle'}"
                )

        elif accion == "evento":
            nombre_ev, fecha_ev, hora_ev = _parsear_evento_audio_payload(contenido)
            if not fecha_ev:
                await estado.edit_text(
                    "El evento necesita fecha. Por voz usa: evento <nombre> para el 20-03 [15:30].\n"
                    "Sin 'para el': nombre y fecha en una frase (ej. reunion 20-03 15:30)."
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

        elif accion == "investiga":
            if not contenido.strip():
                await estado.edit_text(
                    "Di investiga seguido del concepto o frase (ej. investiga paneles solares bifaciales)."
                )
                return
            inv = Investigacion(
                id=_generar_id_investigacion(contenido.strip()),
                fecha=datetime.now().isoformat(),
                estado="pendiente",
                concepto=contenido.strip(),
                resumen="",
                link="",
            )
            añadir_investigacion(inv)
            await estado.edit_text(
                f"Investigacion encolada desde audio (pendiente).\n"
                f"ID: {inv.id}\n"
                f"Concepto: {inv.concepto}"
            )

        elif accion == "huevos":
            cant_h = _primer_entero_positivo(contenido)
            if cant_h is None:
                await estado.edit_text(
                    "Di huevos y un numero entero positivo, ej. huevos 12"
                )
                return
            hoy_h = datetime.now().strftime("%Y-%m-%d")
            añadir_huevo(cant_h, hoy_h, fuente="telegram_audio")
            total_h = total_cantidad_en_fecha(hoy_h)
            await estado.edit_text(
                f"Huevos registrados desde audio.\n"
                f"Fecha: {hoy_h}\n"
                f"Esta vez: {cant_h}\n"
                f"Total del dia: {total_h}"
            )

        elif accion == "diario":
            if not contenido.strip():
                await estado.edit_text("Di diario seguido del texto (o nota) que quieras guardar.")
                return
            usr = update.effective_user
            etiqueta_u = (usr.username or str(usr.id)) if usr else ""
            try:
                ent = diario_añadir_entrada(
                    contenido.strip(),
                    fuente="telegram_audio",
                    telegram_user=etiqueta_u,
                )
            except ValueError:
                await estado.edit_text("El texto del diario no puede estar vacio.")
                return
            await estado.edit_text(
                f"Entrada de diario guardada.\n"
                f"Dia: {ent.fecha_dia}\n"
                f"Archivo: {ent.ruta}"
            )

        else:
            usr = update.effective_user
            if not usr:
                await estado.edit_text("No se pudo identificar al usuario de Telegram.")
                return
            pend = añadir_pendiente(
                contenido,
                user_id=int(usr.id),
                username=usr.username or "",
                fuente="telegram_audio",
            )
            await estado.edit_text(
                f"Guardado en pendientes (sin accion reconocida en el audio).\n"
                f"ID: {pend.id}\n"
                f"Usa /listpendientes y /mvpendiente <n|id> <tipo> [args extra]\n"
                f"Tipos: idea, tarea, evento, funcionalidad, func, investiga, comprar, diario"
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
    app.add_handler(CommandHandler("convo", cmd_convo))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("listurl", cmd_listurl))
    app.add_handler(CommandHandler("verurl", cmd_verurl))
    app.add_handler(CommandHandler("rmurl", cmd_rmurl))
    app.add_handler(CommandHandler("idea", cmd_idea))
    app.add_handler(CommandHandler("listideas", cmd_listideas))
    app.add_handler(CommandHandler("veridea", cmd_veridea))
    app.add_handler(CommandHandler("rmidea", cmd_rmidea))
    app.add_handler(CommandHandler("proyecto", cmd_proyecto))
    app.add_handler(CommandHandler("cancelarproyecto", cmd_cancelarproyecto))
    app.add_handler(CommandHandler("listproyecto", cmd_listproyecto))
    app.add_handler(CommandHandler("verproyecto", cmd_verproyecto))
    app.add_handler(CommandHandler("rmproyecto", cmd_rmproyecto))
    app.add_handler(CommandHandler("tiempo", cmd_tiempo))
    app.add_handler(CommandHandler("tiempofin", cmd_tiempofin))
    app.add_handler(CommandHandler("listtiempo", cmd_listtiempo))
    app.add_handler(CommandHandler("vertiempo", cmd_vertiempo))
    app.add_handler(CommandHandler("modtiempo", cmd_modtiempo))
    app.add_handler(CommandHandler("listconvo", cmd_listar))
    app.add_handler(CommandHandler("verconvo", cmd_verconvo))
    app.add_handler(CommandHandler("investiga", cmd_investiga))
    app.add_handler(CommandHandler("listinvestigaciones", cmd_listinvestigaciones))
    app.add_handler(CommandHandler("verinvestigacion", cmd_verinvestigacion))
    app.add_handler(CommandHandler("rminvestigacion", cmd_rminvestigacion))
    app.add_handler(CommandHandler("func", cmd_func))
    app.add_handler(CommandHandler("listfunc", cmd_listfunc))
    app.add_handler(CommandHandler("listfuncionalidades", cmd_listfunc))
    app.add_handler(CommandHandler("verfunc", cmd_verfunc))
    app.add_handler(CommandHandler("rmfunc", cmd_rmfunc))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("comprar", cmd_comprar))
    app.add_handler(CommandHandler("evento", cmd_evento))
    app.add_handler(CommandHandler("listeventos", cmd_listeventos))
    app.add_handler(CommandHandler("verevento", cmd_verevento))
    app.add_handler(CommandHandler("rmevento", cmd_rmevento))
    app.add_handler(CommandHandler("listtareas", cmd_listtareas))
    app.add_handler(CommandHandler("vertarea", cmd_vertarea))
    app.add_handler(CommandHandler("rmtarea", cmd_rmtarea))
    app.add_handler(CommandHandler("huevos", cmd_huevos))
    app.add_handler(CommandHandler("listhuevos", cmd_listhuevos))
    app.add_handler(CommandHandler("diario", cmd_diario))
    app.add_handler(CommandHandler("listpendientes", cmd_listpendientes))
    app.add_handler(CommandHandler("verpendiente", cmd_verpendiente))
    app.add_handler(CommandHandler("rmpendientes", cmd_rmpendientes))
    app.add_handler(CommandHandler("mvpendiente", cmd_mvpendiente))
    app.add_handler(CommandHandler("rmconvo", cmd_rmconvo))
    app.add_handler(CommandHandler("factura", cmd_factura))
    app.add_handler(CommandHandler("cancelarfactura", cmd_cancelarfactura))
    app.add_handler(CommandHandler("cancelarmodfactura", cmd_cancelarmodfactura))
    app.add_handler(CommandHandler("listcontabilidad", cmd_listcontabilidad))
    app.add_handler(CommandHandler("verfactura", cmd_verfactura))
    app.add_handler(CommandHandler("rmfactura", cmd_rmfactura))
    app.add_handler(CommandHandler("modfactura", cmd_modfactura))
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.MimeType("application/pdf"),
            manejar_archivo_factura,
        )
    )
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, manejar_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_error_handler(error_handler)

    print(
        f"ConvocAUTOrias bot v{config.APP_VERSION} iniciado. Pulsa Ctrl+C para detener."
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
