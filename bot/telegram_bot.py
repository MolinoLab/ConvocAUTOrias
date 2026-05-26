"""
Bot Telegram: convocatorias (/convo, /listconvo, /verconvo, /rmconvo),
ideas, memorias, proyectos, tiempos, enlaces, investigaciones (/investiga), funcionalidades,
tareas Deck, fabricación (Fabricar), eventos CalDAV, huevos, diario, pendientes (audio), audio. Ver /ayuda.
URL suelta = nuevo enlace (data/enlaces.csv). Convocatoria solo con /convo <url>.
"""
import asyncio
import hashlib
import json
import os
import re
from dataclasses import replace
import shutil
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
from src.db import (
    Convocatoria,
    añadir,
    actualizar as actualizar_convocatoria_registro,
    buscar_por_id,
    eliminar_por_id,
    es_convocatoria_en_seguimiento,
    listar,
)
from src.db_ideas import (
    Idea,
    actualizar_idea,
    añadir_idea,
    buscar_por_id as buscar_idea_por_id,
    eliminar_por_id as eliminar_idea_por_id,
    leer_ideas,
)
from src.db_memorias import (
    Memoria,
    actualizar_memoria,
    añadir_memoria,
    buscar_por_id as buscar_memoria_por_id,
    eliminar_por_id as eliminar_memoria_por_id,
    leer_memorias,
)
from src.db_funcionalidad import (
    Funcionalidad,
    ESTADOS_VALIDOS,
    añadir as añadir_func,
    actualizar as actualizar_func,
    buscar_por_id as buscar_func_por_id,
    listar as listar_func,
    eliminar as eliminar_func_db,
)
from src.db_investigaciones import (
    ESTADOS_INVESTIGACION,
    Investigacion,
    añadir as añadir_investigacion,
    actualizar as actualizar_investigacion_registro,
    buscar_por_id as buscar_investigacion_por_id,
    eliminar as eliminar_investigacion_db,
    listar as listar_investigaciones,
)
from src.db_enlaces import (
    Enlace,
    actualizar_enlace,
    añadir_enlace,
    buscar_enlace_por_id,
    buscar_enlace_por_url,
    eliminar_enlace_por_id,
    leer_enlaces,
)
from src.agenda_resumen import texto_agenda_proximos_dias
from src.descarga_media import ejecutar_descarga
from src.bambulab_client import (
    apagar_impresora,
    obtener_estado_impresion,
    obtener_ultimo_error_bambu,
)
from src.caldav_client import (
    actualizar_evento_por_url,
    borrar_evento_por_url,
    crear_evento,
    formatear_detalle_evento_por_url,
    listar_eventos_proximos_dias,
    obtener_ultimo_error_evento,
)
from src.deck_client import (
    actualizar_tarjeta_deck,
    borrar_tarjeta_deck,
    crear_tarea_deck,
    listar_tareas_deck,
    obtener_tarjeta_deck,
    obtener_ultimo_aviso_asignacion_deck,
    obtener_ultimo_error_deck,
)
from src.db_fabrica import (
    ItemFabrica,
    añadir_item as añadir_item_fabrica,
    actualizar_campos as actualizar_fabrica_campos,
    buscar_por_id as buscar_fabrica_por_id,
    eliminar_por_id as eliminar_fabrica_por_id,
    leer_fabrica,
)
from src.db_diario import (
    actualizar_entrada as actualizar_diario_entrada,
    añadir_entrada as diario_añadir_entrada,
    buscar_por_id as buscar_diario_por_id,
    eliminar_por_id as eliminar_diario_por_id,
    listar_recientes as listar_diario_recientes,
)
from src.db_huevos import (
    actualizar_registro as actualizar_huevo_registro,
    añadir as añadir_huevo,
    buscar_por_id as buscar_huevo_por_id,
    eliminar_por_id as eliminar_huevo_por_id,
    listar_registros_recientes,
    resumen_ultimos_dias_desde_hoy,
    total_cantidad_en_fecha,
)
from src.db_recomendaciones import (
    actualizar as actualizar_recomendacion,
    añadir as añadir_recomendacion,
    buscar_por_id as buscar_recomendacion_por_id,
    eliminar_por_id as eliminar_recomendacion_por_id,
    listar_recientes as listar_recomendaciones_recientes,
)
from src.db_pendientes import (
    Pendiente,
    actualizar_pendiente,
    añadir as añadir_pendiente,
    buscar_por_id as buscar_pendiente_por_id,
    eliminar as eliminar_pendiente_db,
    listar_recientes_primero as listar_pendientes_recientes,
)
from src.db_proyectos import (
    ESTADOS_PROYECTO_VALIDOS,
    Proyecto,
    actualizar_proyecto,
    añadir_proyecto,
    buscar_por_id as buscar_proyecto_por_id,
    eliminar_por_id as eliminar_proyecto_por_id,
    leer_proyectos,
    tiempo_total_minutos,
)
from src.db_tiempos import (
    Tiempo,
    actualizar_tiempo,
    añadir_tiempo,
    buscar_activo_global,
    buscar_por_id as buscar_tiempo_por_id,
    cerrar_tiempo,
    eliminar_todos_de_proyecto,
    es_activo,
    leer_tiempos,
    sincronizar_tiempo_total_proyecto,
)
from src import notes_nextcloud
from src.fechas_proyecto import (
    formatear_fecha,
    formatear_fecha_hora,
    formatear_minutos_como_texto,
    minutos_entre,
    parsear_fecha_hora,
    parsear_solo_fecha,
)
from src.plazo import es_futura, clave_orden, parsear_plazo
from src.fecha_display import (
    extraer_cuerpo_y_fecha_dia_para_el,
    extraer_fecha_natural_dd_mm_yyyy_y_resto,
    extraer_fecha_relativa_dd_mm_yyyy,
    fecha_hoy_relativas,
    formatear_dia_mes_sin_anio,
    formatear_fecha_ver,
    extraer_fecha_relativa_iso_y_resto,
    strip_sufijo_para_el,
    strip_sufijo_para_fecha,
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
from src.tuya_client import obtener_estado_enchufe, obtener_ultimo_error_tuya, poner_enchufe

# Regex para detectar URLs
URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)

_WHISPER_MODEL = None

# Stack Deck para lista de compras (nombre exacto en Nextcloud Deck)
DECK_STACK_COMPRAR = "Comprar"
DECK_STACK_VOLUNTARIOS = (config.DECK_STACK_VOLUNTARIOS or "Voluntarios").strip()

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
CACHE_RM_MEMORIAS = "rm_memoria_ids"
CACHE_RM_PENDIENTES_IDS = "rm_pendiente_ids"
CACHE_RM_CONTABILIDAD_IDS = "rm_contabilidad_ids"
CACHE_RM_FABRICA = "rm_fabrica_ids"
CACHE_RM_HUEVO_IDS = "rm_huevo_ids"
CACHE_RM_DIARIO_IDS = "rm_diario_ids"
CACHE_RM_NOTAS_IDS = "rm_notas_ids"
CACHE_RM_REC_IDS = "rm_rec_ids"
WIZARD_MOD_TAREA_KEY = "mod_tarea_wizard"
WIZARD_MOD_EVENTO_KEY = "mod_evento_wizard"
WIZARD_MOD_TIEMPO_KEY = "mod_tiempo_wizard"
WIZARD_MOD_NOTA_KEY = "mod_nota_wizard"
WIZARD_PROYECTO_KEY = "proyecto_wizard"
WIZARD_MOD_FACTURA_KEY = "mod_factura_wizard"
WIZARD_MOD_FABRICA_KEY = "mod_fabrica_wizard"
WIZARD_MOD_PROYECTO_KEY = "mod_proyecto_wizard"
WIZARD_MOD_LISTA_KEY = "mod_lista_wizard"
ESPERANDO_FACTURA_KEY = "esperando_factura"

CAMPOS_MOD_FABRICA: list[tuple[str, str]] = [
    ("titulo", "Titulo"),
    ("medidas", "Medidas"),
    ("fecha_due", "Fecha limite (DD-MM-AAAA, mañana, etc.; '-' sin fecha)"),
    ("tipo", "Tipo: laser, 3d o '-' sin tipo"),
    ("notas", "Notas / descripcion"),
]

CAMPOS_MOD_PROYECTO: list[tuple[str, str]] = [
    ("titulo", "Titulo"),
    ("persona_contacto", "Persona de contacto"),
    ("email_contacto", "Email de contacto"),
    ("presupuesto", "Presupuesto (- vaciar)"),
    ("fecha_fin", "Fecha entrega / fin (DD,MM,YYYY flexible; - sin fecha)"),
    ("estado", "Estado (idea|activo|en_espera|presupuestado|completado|cancelado)"),
    ("tags", "Tags (coma separadas; - vaciar)"),
]

# /modconvo, /modidea, … — cache del ultimo /list* en el chat
MOD_LISTA_CAMPOS: dict[str, tuple[str, list[tuple[str, str]], str]] = {
    "convo": (
        CACHE_RM_CONVOS,
        [
            ("url", "URL"),
            ("titulo", "Titulo"),
            ("descripcion", "Descripcion"),
            ("plazo_fin", "Plazo fin (texto o fecha)"),
            ("requisitos", "Requisitos"),
            ("estado", "Estado (ej. pendiente)"),
            ("fuente", "Fuente"),
        ],
        "/listconvo",
    ),
    "idea": (
        CACHE_RM_IDEAS,
        [
            ("resumen", "Resumen"),
            ("tags", "Tags"),
            ("categorias", "Categorias"),
            ("presupuesto_aproximado", "Presupuesto aproximado"),
            ("ruta", "Ruta .md"),
            ("fuente", "Fuente"),
        ],
        "/listideas",
    ),
    "memoria": (
        CACHE_RM_MEMORIAS,
        [
            ("resumen", "Resumen"),
            ("ruta", "Ruta .md"),
            ("fuente", "Fuente"),
        ],
        "/listmemorias",
    ),
    "func": (
        CACHE_RM_FUNC_IDS,
        [
            ("texto", "Texto"),
            ("prioridad", "Prioridad (1-5)"),
            ("estado", "Estado (pendiente|en_progreso|hecha)"),
            ("fuente", "Fuente"),
        ],
        "/listfunc",
    ),
    "inv": (
        CACHE_RM_INVESTIGACIONES,
        [
            ("estado", "Estado (pendiente|investigado|enviado|error)"),
            ("concepto", "Concepto"),
            ("resumen", "Resumen"),
            ("link", "Link"),
            ("archivo", "Archivo .md"),
        ],
        "/listinvestigaciones",
    ),
    "enlace": (
        CACHE_RM_ENLACES,
        [
            ("url", "URL"),
            ("tags", "Tags"),
            ("categorias", "Categorias"),
            ("notas", "Notas"),
            ("fuente", "Fuente"),
        ],
        "/listurl",
    ),
    "pendiente": (
        CACHE_RM_PENDIENTES_IDS,
        [
            ("texto", "Texto transcrito"),
            ("fuente", "Fuente"),
        ],
        "/listpendientes",
    ),
    "rec": (
        CACHE_RM_REC_IDS,
        [
            ("tipo", "Tipo (artista, escritor, ...)"),
            ("nombre", "Nombre"),
            ("notas", "Notas"),
            ("tags", "Tags"),
            ("fuente", "Fuente"),
        ],
        "/listrecomendaciones",
    ),
    "diario": (
        CACHE_RM_DIARIO_IDS,
        [
            ("resumen", "Resumen"),
        ],
        "/listdiario",
    ),
    "huevo": (
        CACHE_RM_HUEVO_IDS,
        [
            ("cantidad", "Cantidad (entero)"),
            ("fecha", "Fecha (YYYY-MM-DD)"),
            ("fuente", "Fuente"),
        ],
        "/listregistroshuevos",
    ),
}

FAB_RESUMEN_LISTA_MAX = 72

_PAT_MEDIDAS_FABRICA = re.compile(
    r"\b\d+\s*[x×]\s*\d+(?:\s*[x×]\s*\d+)?(?:\s*(?:cm|mm|m))?\b",
    re.IGNORECASE,
)

INV_RESUMEN_LISTA_MAX = 72
PENDIENTE_RESUMEN_LISTA_MAX = 72
_TIPOS_MV_VALIDOS = frozenset(
    {
        "idea",
        "memoria",
        "tarea",
        "evento",
        "funcionalidad",
        "investiga",
        "comprar",
        "voluntarios",
        "fabrica",
        "diario",
    }
)
IDEA_RESUMEN_LISTA_MAX = 70
MEMORIA_RESUMEN_LISTA_MAX = 70
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


def _es_mantener_wizard_valor(texto: str) -> bool:
    """Telegram no permite mensaje vacío: . .. igual = mantienen el valor actual."""
    t = (texto or "").strip().lower()
    return t in (".", "..", "igual", "=", "mismo", "ok")


def _username_telegram_para_agenda(update: Update) -> str | None:
    u = update.effective_user
    if not u or not (u.username or "").strip():
        return None
    return u.username.strip().lower().lstrip("@")


def _deck_uids_para_update(update: Update | None) -> list[str]:
    """Uids Nextcloud para asignar tarjetas Deck según id o username de Telegram."""
    if not update or not update.effective_user:
        return []
    u = update.effective_user
    uid = config.DECK_ASSIGNEE_BY_TELEGRAM_ID.get(int(u.id))
    if uid:
        return [uid]
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
    from src.slug_archivo_md import elegir_path_md_unico, texto_a_slug_palabras

    idea_id = _generar_id_idea(texto)
    metadatos = _extraer_metadatos_idea(texto)
    resumen_meta = (metadatos.get("resumen") or "").strip()
    slug_src = resumen_meta if resumen_meta else texto
    slug_base = texto_a_slug_palabras(slug_src, 5)

    config.CARPETA_IDEAS.mkdir(parents=True, exist_ok=True)
    ruta_abs = elegir_path_md_unico(config.CARPETA_IDEAS, slug_base, idea_id)
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
        "memoria",
        "funcionalidad",
        "tarea",
        "evento",
        "comprar",
        "voluntarios",
        "fabrica",
        "fab",
        "investiga",
        "huevos",
        "diario",
    }
)
_ACCION_AUDIO_SINONIMOS: dict[str, str] = {
    "eventos": "evento",
    "compra": "comprar",
    "voluntario": "voluntarios",
}


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
        f"armonIA v{config.APP_VERSION} — comandos (crear → listar → ver → borrar). "
        "Ediciones guiadas: /mod* y /cancelarmod* o /cancelarmodlista según caso.\n\n"
        "[Convocatorias] /convo /listconvo /verconvo /modconvo /rmconvo\n"
        "[Enlaces] URL suelta o /url — /listurl /verurl /modenlace /rmurl\n"
        "[Ideas] /idea /listideas /veridea /modidea /rmidea\n"
        "[Memorias] /memoria /listmemorias /vermemoria /modmemoria /rmmemoria\n"
        "[Proyectos] /proyecto /cancelarproyecto /listproyectos /verproyecto /modproyecto /rmproyecto\n"
        "[Tiempos] /tiempo /tiempofin /listtiempo /vertiempo /modtiempo\n"
        "[Funcionalidades] /func /listfunc /verfunc /modfunc /rmfunc\n"
        "[Investigaciones] /investiga /listinvestigaciones /verinvestigacion /modinv /rminvestigacion\n"
        f"[Deck] /tarea /comprar /voluntarios (columna {DECK_STACK_VOLUNTARIOS}) "
        "/listtareas /vertarea /modtarea /rmtarea\n"
        f"[Fabricar] /fabrica /fab /listfab /verfab /modfab /rmfab (columna {config.DECK_STACK_FABRICAR or 'Fabricar'})\n"
        "[CalDAV] /evento /listeventos /informame /info [dias] /verevento /modevento /rmevento\n"
        "[Huevos] /huevos [para el fecha] /listhuevos — /modhuevo solo corrige registros existentes\n"
        "[Diario] /diario /listdiario /verdiario /moddiario /rmdiario\n"
        "[Recomendaciones] /rec /listrecomendaciones /verrec /modrec /rmrec\n"
        "[Notas NC] /notas /listnotas /vernota /modnota /rmnota (cred. en .env)\n"
        "[Facturas] /factura /cancelarfactura /listcontabilidad /verfactura /rmfactura /modfactura\n"
        "[Pendientes] /listpendientes /verpendiente /modpendiente /rmpendientes /mvpendiente\n"
        "[Descarga VPS] /descarga <url o busqueda> — yt-dlp en carpeta configurada\n"
        "[IoT] /enchufeestado /enchufeen /enchufeapagar /impresoraestado /impresoraapagar\n"
        "[Audio] palabra inicial: idea, memoria, funcionalidad, tarea, comprar, voluntarios, "
        "fabrica, fab, evento, investiga, huevos, diario; si no, pendiente. "
        "Fechas: «para el …» / «para …». "
        "/ayuda — esta lista"
    )
    await _reply_texto_largo(update, texto)


async def cmd_descarga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /descarga <url https://... o texto para buscar en YouTube>\n"
            f"Se guarda en: {config.DESCARGAS_DIR}"
        )
        return
    query = " ".join(context.args).strip()
    aviso = await update.message.reply_text("Descargando…")
    loop = asyncio.get_event_loop()

    def _run() -> tuple[bool, str, str | None]:
        return ejecutar_descarga(query)

    ok, msg, ruta = await loop.run_in_executor(None, _run)
    try:
        await aviso.delete()
    except Exception:
        pass
    if not ok:
        await update.message.reply_text(f"No se pudo descargar.\n{msg[:3500]}")
        return
    if ruta:
        rp = Path(ruta)
        await update.message.reply_text(f"{msg}\n{rp}")
        max_b = config.DESCARGA_ENVIAR_TELEGRAM_MAX_MB * 1024 * 1024
        if max_b > 0 and rp.is_file() and rp.stat().st_size <= max_b:
            try:
                with rp.open("rb") as f:
                    await update.message.reply_document(document=f, filename=rp.name)
            except Exception as exc:
                await update.message.reply_text(f"(No se pudo enviar el archivo: {exc})")


async def cmd_enchufeestado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    ok, msg = obtener_estado_enchufe()
    if not ok:
        await update.message.reply_text(f"No se pudo consultar Tuya.\n{obtener_ultimo_error_tuya()}")
        return
    await update.message.reply_text(msg)


async def cmd_enchufeen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    ok, msg = poner_enchufe(True)
    if not ok:
        await update.message.reply_text(f"No se pudo encender el enchufe.\n{obtener_ultimo_error_tuya()}")
        return
    await update.message.reply_text(msg)


async def cmd_enchufeapagar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    ok, msg = poner_enchufe(False)
    if not ok:
        await update.message.reply_text(f"No se pudo apagar el enchufe.\n{obtener_ultimo_error_tuya()}")
        return
    await update.message.reply_text(msg)


async def cmd_impresoraestado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    aviso = await update.message.reply_text("Consultando estado de impresora…")
    loop = asyncio.get_event_loop()

    def _run() -> tuple[bool, str]:
        return obtener_estado_impresion()

    ok, msg = await loop.run_in_executor(None, _run)
    try:
        await aviso.delete()
    except Exception:
        pass
    if not ok:
        await update.message.reply_text(
            f"No se pudo consultar BambuLab.\n{obtener_ultimo_error_bambu()}"
        )
        return
    await update.message.reply_text(msg)


async def cmd_impresoraapagar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.args and context.args[0].strip().lower() == "confirmar":
        loop = asyncio.get_event_loop()

        def _run() -> tuple[bool, str]:
            return apagar_impresora()

        ok, msg = await loop.run_in_executor(None, _run)
        if not ok:
            await update.message.reply_text(
                f"No se pudo apagar la impresora.\n{obtener_ultimo_error_bambu()}"
            )
            return
        await update.message.reply_text(msg)
        return
    await update.message.reply_text(
        "Esta acción apaga la impresora mediante su enchufe asociado.\n"
        "Confirma con: /impresoraapagar confirmar"
    )


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
    pendientes = [c for c in listar() if es_convocatoria_en_seguimiento(c.estado)]
    futuras = [c for c in pendientes if es_futura(c.plazo_fin)]
    futuras.sort(key=lambda c: clave_orden(c.plazo_fin))
    return futuras


def _formato_plazo(plazo_fin: str) -> str:
    fecha = parsear_plazo(plazo_fin)
    if fecha:
        return f"{fecha.day:02d}, {fecha.month:02d}"
    return plazo_fin.strip() if plazo_fin.strip() else "Sin fecha"


async def cmd_listar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    futuras = _obtener_futuras_ordenadas()

    if not futuras:
        total_pendientes = sum(1 for c in listar() if es_convocatoria_en_seguimiento(c.estado))
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


def _generar_id_memoria(texto: str) -> str:
    base = f"{datetime.now().isoformat()}::mem::{texto[:1000]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _guardar_memoria(texto: str, fuente: str) -> Memoria:
    from src.slug_archivo_md import elegir_path_md_unico, texto_a_slug_palabras

    limpio = texto.strip()
    mem_id = _generar_id_memoria(limpio)
    resumen = _resumen_simple(limpio)
    slug_base = texto_a_slug_palabras(limpio, 5)
    config.CARPETA_MEMORIAS.mkdir(parents=True, exist_ok=True)
    ruta_abs = elegir_path_md_unico(config.CARPETA_MEMORIAS, slug_base, mem_id)
    try:
        ruta_rel = ruta_abs.relative_to(config.DIR_PROYECTO).as_posix()
    except Exception:
        ruta_rel = str(ruta_abs)
    ruta_abs.write_text(limpio + "\n", encoding="utf-8")
    m = Memoria(
        id=mem_id,
        resumen=resumen,
        ruta=ruta_rel.replace("\\", "/"),
        fecha_ingesta=datetime.now().isoformat(),
        fuente=fuente,
    )
    añadir_memoria(m)
    return m


async def cmd_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /memoria <texto>\n"
            "Ejemplo: /memoria apuntes API rate limits y backoff exponencial"
        )
        return
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("La memoria no puede estar vacia.")
        return
    msg = await update.message.reply_text("Guardando memoria...")
    mem = _guardar_memoria(texto, fuente="telegram_texto")
    await msg.edit_text(f"Memoria guardada.\nResumen: {mem.resumen}")


def _ruta_archivo_memoria(ruta: str) -> Path:
    return _ruta_archivo_idea(ruta)


def _formatear_memoria_completa(mem: Memoria, cuerpo_md: str) -> str:
    cuerpo = (cuerpo_md or "").strip()
    if not cuerpo:
        cuerpo = "(archivo vacio o no encontrado)"
    return (
        f"Resumen: {mem.resumen}\n"
        f"Fecha: {formatear_fecha_ver(mem.fecha_ingesta)}\n"
        f"Fuente: {mem.fuente}\n\n"
        f"--- Contenido ---\n{cuerpo}"
    )


async def cmd_listmemorias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    memorias = leer_memorias()
    if not memorias:
        await update.message.reply_text("No hay memorias registradas en memorias.csv.")
        return
    memorias = sorted(
        memorias, key=lambda m: (m.fecha_ingesta or "", m.id), reverse=True
    )
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_MEMORIAS] = [m.id for m in memorias]
    lineas: list[str] = []
    for i, mem in enumerate(memorias, 1):
        res = mem.resumen.strip() or "(sin resumen)"
        if len(res) > MEMORIA_RESUMEN_LISTA_MAX:
            res = res[:MEMORIA_RESUMEN_LISTA_MAX] + "..."
        lineas.append(f"{i}. {res}")
    cabecera = f"Memorias ({len(memorias)}), mas recientes primero:\n\n"
    texto_completo = cabecera + "\n\n".join(lineas)
    if len(texto_completo) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_TELEGRAM_MSG])


async def cmd_vermemoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /vermemoria <numero>\n"
            "El numero es el de /listmemorias en este chat."
        )
        return
    argumento = context.args[0].strip()
    mem: Memoria | None = None
    if argumento.isdigit():
        n = int(argumento)
        cache = (context.chat_data or {}).get(CACHE_RM_MEMORIAS) or []
        if n < 1 or n > len(cache):
            await update.message.reply_text(
                "Indice invalido o lista antigua. Ejecuta /listmemorias primero en este chat."
            )
            return
        mem = buscar_memoria_por_id(cache[n - 1])
    else:
        mem = buscar_memoria_por_id(argumento)
    if not mem:
        await update.message.reply_text(
            "No se encontro memoria con ese criterio.\nUsa /listmemorias para ver el listado."
        )
        return
    path = _ruta_archivo_memoria(mem.ruta)
    cuerpo = ""
    try:
        if path.is_file():
            cuerpo = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        cuerpo = ""
    texto = _formatear_memoria_completa(mem, cuerpo)
    await _reply_texto_largo(update, texto)


async def cmd_rmmemoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmmemoria <numero> [numero ...]\n"
            "Los numeros son los de /listmemorias en este chat."
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
        cache = (context.chat_data or {}).get(CACHE_RM_MEMORIAS) or []
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
                msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listmemorias en este chat."
            await update.message.reply_text(msg)
            return
    ok_n = 0
    no_encontradas = 0
    error_indice = 0
    archivo_no_borrado = False
    for target_id in ids_objetivo:
        m = buscar_memoria_por_id(target_id)
        if not m:
            no_encontradas += 1
            continue
        path = _ruta_archivo_memoria(m.ruta)
        removed = eliminar_memoria_por_id(m.id)
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
        context.chat_data.pop(CACHE_RM_MEMORIAS, None)
    partes = [f"Memorias eliminadas: {ok_n}."]
    if not otros and fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if no_encontradas:
        partes.append(f"No encontradas: {no_encontradas}.")
    if error_indice:
        partes.append(f"Error al quitar del indice: {error_indice}.")
    if archivo_no_borrado:
        partes.append("Revisa la carpeta data/memorias por archivos .md huerfanos.")
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
        return "Paso 2/8: Persona de contacto."
    if step == 2:
        return "Paso 3/8: Email de contacto."
    if step == 3:
        return "Paso 4/8: Presupuesto (texto o numero). Escribe - si no aplica."
    if step == 4:
        return (
            "Paso 5/8: Fecha de entrega / fin prevista (DD,MM,YYYY flexible) o - si no hay."
        )
    if step == 5:
        return (
            "Paso 6/8: Estado: idea | activo | en_espera | presupuestado | completado | cancelado"
        )
    if step == 6:
        return "Paso 7/8: Tags (separados por comas) o - si no hay."
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
    tg = (getattr(p, "tags", None) or "").strip()
    suf_tags = f" | {tg}" if tg else ""
    return f"{tit} [{p.estado}] tiempo {tm}{suf_tags}"


def _formatear_proyecto_completo(p: Proyecto, cuerpo_md: str) -> str:
    fc = (p.fecha_creacion or "").strip()
    fc_show = formatear_fecha_ver(fc) if fc else "(sin fecha)"
    ff = (p.fecha_fin or "").strip()
    ff_show = formatear_fecha_ver(ff) if ff else "(sin fecha entrega)"
    pres = p.presupuesto.strip() or "(no indicado)"
    tg = (getattr(p, "tags", None) or "").strip() or "(sin tags)"
    return (
        f"Titulo: {p.titulo}\n"
        f"Fecha creacion: {fc_show}\n"
        f"Contacto: {p.persona_contacto}\n"
        f"Email: {p.email_contacto}\n"
        f"Presupuesto: {pres}\n"
        f"Tiempo total: {formatear_minutos_como_texto(tiempo_total_minutos(p))}\n"
        f"Fecha entrega: {ff_show}\n"
        f"Estado: {p.estado}\n"
        f"Tags: {tg}\n"
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
        data["persona_contacto"] = texto_raw
        wizard["step"] = 2
        await update.message.reply_text(_wizard_proyecto_prompt_paso(2))
        return True

    if step == 2:
        if not _email_valido_proyecto(texto_raw):
            await update.message.reply_text("Email no valido. Vuelve a intentarlo.")
            return True
        data["email_contacto"] = texto_raw.strip()
        wizard["step"] = 3
        await update.message.reply_text(_wizard_proyecto_prompt_paso(3))
        return True

    if step == 3:
        data["presupuesto"] = "" if texto_raw in ("-", "—") else texto_raw
        wizard["step"] = 4
        await update.message.reply_text(_wizard_proyecto_prompt_paso(4))
        return True

    if step == 4:
        if texto_raw in ("-", "—"):
            data["fecha_fin"] = ""
        else:
            dt = parsear_solo_fecha(texto_raw)
            if dt is None:
                await update.message.reply_text(
                    "Fecha de entrega no reconocida. Usa - si no hay."
                )
                return True
            data["fecha_fin"] = formatear_fecha(dt)
        wizard["step"] = 5
        await update.message.reply_text(_wizard_proyecto_prompt_paso(5))
        return True

    if step == 5:
        est = texto_raw.lower().strip()
        if est not in ESTADOS_PROYECTO_VALIDOS:
            await update.message.reply_text(
                "Estado no valido. Usa uno de: idea, activo, en_espera, presupuestado, "
                "completado, cancelado"
            )
            return True
        data["estado"] = est
        wizard["step"] = 6
        await update.message.reply_text(_wizard_proyecto_prompt_paso(6))
        return True

    if step == 6:
        data["tags"] = "" if texto_raw in ("-", "—") else texto_raw.strip()
        wizard["step"] = 7
        await update.message.reply_text(_wizard_proyecto_prompt_paso(7))
        return True

    if step == 7:
        from src.slug_archivo_md import elegir_path_md_unico, texto_a_slug_palabras

        cuerpo = "" if texto_raw in ("-", "—") else texto_raw
        pid = _generar_id_proyecto(data["titulo"])
        config.CARPETA_PROYECTOS.mkdir(parents=True, exist_ok=True)
        slug_p = texto_a_slug_palabras(data["titulo"], 5)
        ruta_abs = elegir_path_md_unico(config.CARPETA_PROYECTOS, slug_p, pid)
        try:
            ruta_rel = ruta_abs.relative_to(config.DIR_PROYECTO).as_posix()
        except Exception:
            ruta_rel = str(ruta_abs)
        ruta_rel = ruta_rel.replace("\\", "/")

        d0 = fecha_hoy_relativas()
        fecha_creacion_auto = formatear_fecha(datetime(d0.year, d0.month, d0.day))

        plantilla = (
            f"# {data['titulo']}\n\n"
            f"**Contacto:** {data['persona_contacto']} <{data['email_contacto']}>\n\n"
        )
        ruta_abs.write_text(plantilla + (cuerpo.strip() + "\n" if cuerpo else ""), encoding="utf-8")

        p = Proyecto(
            id=pid,
            titulo=data["titulo"],
            fecha_creacion=fecha_creacion_auto,
            persona_contacto=data["persona_contacto"],
            email_contacto=data["email_contacto"],
            presupuesto=data.get("presupuesto", ""),
            tiempo_total="0",
            fecha_fin=data.get("fecha_fin", ""),
            estado=data["estado"],
            tags=data.get("tags", ""),
            ruta=ruta_rel,
            fuente="telegram",
        )
        añadir_proyecto(p)
        _limpiar_wizard_proyecto(context)
        await update.message.reply_text(
            f"Proyecto guardado.\nID interno: {pid}\nTitulo: {p.titulo}\n"
            f"Estado: {p.estado}\n\n"
            f"Usa /listproyectos y /tiempo <numero> para registrar tiempo."
        )
        return True

    return False


async def cmd_listproyectos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            "El numero es el de /listproyectos en este chat."
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
            "No se encontro ese proyecto.\nUsa /listproyectos para ver el listado."
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
            "Los numeros son los de /listproyectos en este chat."
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
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listproyectos en este chat."
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
            "Los numeros son los de /listproyectos en este chat."
        )
        return

    if not args[0].isdigit():
        await update.message.reply_text("El primer argumento debe ser el numero de /listproyectos.")
        return
    n = int(args[0])
    p = _proyecto_desde_indice_listado(context, n)
    if not p:
        await update.message.reply_text(
            "Proyecto no encontrado. Ejecuta /listproyectos en este chat primero."
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
    if len(args) == 1:
        await _iniciar_mod_tiempo_wizard(update, context)
        return
    if len(args) < 2:
        await update.message.reply_text(
            "Uso: /modtiempo <num_tiempo> — wizard (inicio/fin/proyecto), o\n"
            "/modtiempo <num_tiempo> <fecha y hora fin> — solo corregir fin\n"
            "Ejemplo rapido: /modtiempo 3 20,03,2026 18:45"
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


def _nueva_investigacion_pendiente(
    concepto: str, telegram_chat_id: str = ""
) -> Investigacion:
    from src.slug_archivo_md import elegir_path_md_unico, texto_a_slug_palabras

    c = concepto.strip()
    iid = _generar_id_investigacion(c)
    slug = texto_a_slug_palabras(c, 5)
    config.CARPETA_INVESTIGACIONES.mkdir(parents=True, exist_ok=True)
    p = elegir_path_md_unico(config.CARPETA_INVESTIGACIONES, slug, iid)
    return Investigacion(
        id=iid,
        fecha=datetime.now().isoformat(),
        estado="pendiente",
        concepto=c,
        resumen="",
        link="",
        archivo=p.name,
        telegram_chat_id=(telegram_chat_id or "").strip(),
    )


_PRIORIDAD_EMOJI = {1: "⬜", 2: "🟦", 3: "🟨", 4: "🟧", 5: "🟥"}

_HORA_PALABRA_A_NUM: dict[str, int] = {
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
}


def _limpiar_prioridad_residual_func(texto: str) -> str:
    """Quita la palabra suelta 'prioridad' que queda al extraer el numero final en /func."""
    t = " ".join((texto or "").split())
    if not t:
        return t
    t = re.sub(r"\bprioridad\b", " ", t, flags=re.IGNORECASE)
    return " ".join(t.split())


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

    texto = _limpiar_prioridad_residual_func(texto.strip())
    return strip_sufijo_para_el(texto), prioridad


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

    texto = _limpiar_prioridad_residual_func(" ".join(args).strip())
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
    cid = str(update.effective_chat.id) if update.effective_chat else ""
    inv = _nueva_investigacion_pendiente(concepto, telegram_chat_id=cid)
    añadir_investigacion(inv)
    await update.message.reply_text(
        f"Investigación encolada (pendiente).\n"
        f"ID: {inv.id}\n"
        f"Concepto: {inv.concepto}\n"
        f"Archivo .md previsto: {inv.archivo}"
    )


def _path_md_investigacion(inv: Investigacion) -> Path:
    nombre = (inv.archivo or "").strip()
    if nombre:
        return config.CARPETA_INVESTIGACIONES / nombre
    return config.CARPETA_INVESTIGACIONES / f"{inv.id}.md"


def _leer_cuerpo_md_investigacion(inv: Investigacion) -> str | None:
    p = _path_md_investigacion(inv)
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
        f"Chat Telegram: {inv.telegram_chat_id or '(no guardado)'}\n"
    )
    md = _leer_cuerpo_md_investigacion(inv)
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
        inv_del = buscar_investigacion_por_id(iid)
        if eliminar_investigacion_db(iid):
            ok_n += 1
            p = (
                _path_md_investigacion(inv_del)
                if inv_del
                else (config.CARPETA_INVESTIGACIONES / f"{iid}.md")
            )
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
        lineas.append(f"{i}. {emoji} {f.texto}")

    cabecera = f"Funcionalidades ({len(todas)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)
    await _reply_texto_largo(update, texto_completo)


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

    nat, resto_nat = extraer_fecha_natural_dd_mm_yyyy_y_resto(texto)
    if nat:
        return nat, resto_nat

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

    titulo = strip_sufijo_para_fecha(titulo.strip())
    return titulo, fecha, descripcion.strip()


_INICIO_FECHA_AUDIO_DIA = re.compile(
    r"^(?:el\s+)?(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b",
    re.IGNORECASE,
)


def _inicio_parece_fecha_bloque(s: str) -> bool:
    """True si el texto (tras normalizar) empieza por algo que el parseo de fechas suele reconocer."""
    s = " ".join((s or "").split())
    if not s:
        return False
    if s[0].isdigit():
        return True
    low = s.lower()
    if low.startswith("el "):
        low = low[3:].lstrip()
    if low.startswith(("pasado mañana", "pasado manana")):
        return True
    if low.startswith(("antier", "ayer", "hoy", "mañana", "manana")):
        return True
    if re.match(r"pasado\b", low) and not low.startswith(("pasado mañana", "pasado manana")):
        return True
    return _INICIO_FECHA_AUDIO_DIA.match(low) is not None


def _partir_audio_titulo_y_fecha(contenido: str) -> tuple[str, str]:
    """
    Divide el payload de voz en (antes, despues) usando 'para el' o 'para' + inicio de fecha.
    Si no hay separador, (contenido.strip(), '').
    """
    texto = " ".join((contenido or "").split()).strip()
    if not texto:
        return "", ""
    m = re.search(r"\bpara el\b", texto, flags=re.IGNORECASE)
    if m:
        return texto[: m.start()].strip(), texto[m.end() :].strip()
    for m2 in re.finditer(r"\bpara\b", texto, flags=re.IGNORECASE):
        despues = texto[m2.end() :].strip()
        if _inicio_parece_fecha_bloque(despues):
            return texto[: m2.start()].strip(), despues
    return texto, ""


def _extraer_duracion_evento_y_resto(texto: str) -> tuple[timedelta | None, str]:
    """Quita 'durante X horas/días/minutos' (o una/media hora) y devuelve timedelta."""
    s = " ".join((texto or "").split())
    if not s:
        return None, s
    low = s.lower()

    def cut(m: re.Match) -> str:
        frag = (s[: m.start()] + s[m.end() :]).strip()
        return " ".join(frag.split())

    m = re.search(r"\bdurante\s+(\d+)\s*horas?\b", s, flags=re.IGNORECASE)
    if m:
        return timedelta(hours=int(m.group(1))), cut(m)
    m = re.search(r"\bdurante\s+(\d+)\s*d[ií]as?\b", s, flags=re.IGNORECASE)
    if m:
        return timedelta(days=int(m.group(1))), cut(m)
    m = re.search(r"\bdurante\s+(\d+)\s*minutos?\b", s, flags=re.IGNORECASE)
    if m:
        return timedelta(minutes=int(m.group(1))), cut(m)
    if re.search(r"\bdurante\s+una\s+hora\b", low):
        m = re.search(r"\bdurante\s+una\s+hora\b", s, flags=re.IGNORECASE)
        if m:
            return timedelta(hours=1), cut(m)
    if re.search(r"\bdurante\s+media\s+hora\b", low):
        m = re.search(r"\bdurante\s+media\s+hora\b", s, flags=re.IGNORECASE)
        if m:
            return timedelta(minutes=30), cut(m)
    return None, s


def _ajustar_hora_12_periodo(h: int, periodo: str) -> int:
    pl = periodo.lower().replace("ñ", "n")
    if pl in ("manana", "madrugada"):
        return h
    if pl in ("tarde", "noche"):
        if h == 12:
            return 12
        if 1 <= h <= 11:
            return h + 12
    return h


def _token_a_hora_base(tok: str) -> int | None:
    t = tok.strip().lower()
    if t.isdigit():
        n = int(t)
        if 0 <= n <= 23:
            return n
        return None
    return _HORA_PALABRA_A_NUM.get(t)


def _extraer_hora_evento_coloquial_y_resto(s: str) -> tuple[str | None, str]:
    """Quita hora (HH:MM o 'a las …' / '… de la tarde') y devuelve (HH:MM, resto)."""
    s = " ".join((s or "").split())
    if not s:
        return None, s

    m = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", s)
    if m:
        hora = m.group(0)
        resto = (s[: m.start()] + s[m.end() :]).strip()
        return hora, " ".join(resto.split())

    pat_a_las = re.compile(
        r"\ba\s+las\s+"
        r"(\d{1,2}|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)"
        r"(?P<mc1>\s+menos\s+cuarto)?"
        r"(?P<ym>\s+y\s+(media|cuarto))?"
        r"(?P<per>\s+de\s+la\s+(mañana|manana|madrugada|tarde|noche))?",
        re.IGNORECASE,
    )
    m2 = pat_a_las.search(s)
    if m2:
        tok = m2.group(1)
        hb = _token_a_hora_base(tok)
        if hb is None:
            return None, s
        menos = m2.group("mc1") is not None
        y_m = m2.group("ym") or ""
        y_kind = None
        my = re.search(r"y\s+(media|cuarto)\b", y_m, re.IGNORECASE)
        if my:
            y_kind = my.group(1).lower()
        per_raw = m2.group("per") or ""
        periodo = None
        if per_raw:
            mper = re.search(
                r"de\s+la\s+(mañana|manana|madrugada|tarde|noche)", per_raw, re.IGNORECASE
            )
            if mper:
                periodo = mper.group(1)

        if menos:
            if hb > 12:
                return None, s
            h12 = hb
            total = h12 * 60 - 15
            if total < 0:
                total += 24 * 60
            h = (total // 60) % 24
            minute = total % 60
        else:
            minute = 0
            if y_kind == "media":
                minute = 30
            elif y_kind == "cuarto":
                minute = 15
            if hb > 12:
                h = hb
            elif periodo:
                h = _ajustar_hora_12_periodo(hb, periodo)
            else:
                h = hb

        hora_str = f"{h % 24:02d}:{minute:02d}"
        resto = (s[: m2.start()] + s[m2.end() :]).strip()
        return hora_str, " ".join(resto.split())

    pat_de_la = re.compile(
        r"\b(\d{1,2}|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)"
        r"(?:\s+y\s+(media|cuarto))?\s+de\s+la\s+(mañana|manana|madrugada|tarde|noche)\b",
        re.IGNORECASE,
    )
    m3 = pat_de_la.search(s)
    if m3:
        tok = m3.group(1)
        hb = _token_a_hora_base(tok)
        if hb is None or hb > 12:
            return None, s
        y_kind = m3.group(2).lower() if m3.group(2) else None
        periodo = m3.group(3)
        minute = 0
        if y_kind == "media":
            minute = 30
        elif y_kind == "cuarto":
            minute = 15
        h = _ajustar_hora_12_periodo(hb, periodo)
        hora_str = f"{h % 24:02d}:{minute:02d}"
        resto = (s[: m3.start()] + s[m3.end() :]).strip()
        return hora_str, " ".join(resto.split())

    return None, s


def _formatear_duracion_usuario(d: timedelta) -> str:
    sec = int(d.total_seconds())
    if sec <= 0:
        return "0 min"
    if sec % 86400 == 0:
        n = sec // 86400
        return f"{n} dia(s)" if n != 1 else "1 dia"
    if sec % 3600 == 0:
        n = sec // 3600
        return f"{n} hora(s)" if n != 1 else "1 hora"
    if sec % 60 == 0:
        n = sec // 60
        return f"{n} minutos" if n != 1 else "1 minuto"
    return str(d)


def _parsear_tarea_audio_payload(contenido: str) -> tuple[str, str | None, str]:
    """
    Tarea por voz: con 'para el' o 'para' + fecha, el título va antes y la fecha (y resto) después.
    Sin separador, mismo criterio que _parsear_args_tarea sobre el texto completo.
    """
    antes, despues = _partir_audio_titulo_y_fecha(contenido)
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


def _parsear_args_evento(
    texto_raw: str,
) -> tuple[str, str | None, str | None, timedelta | None]:
    """Parsea titulo, fecha, hora HH:MM (tambien coloquial) y duracion opcional."""
    texto = texto_raw.strip()
    if not texto:
        return "", None, None, None

    dur, texto = _extraer_duracion_evento_y_resto(texto)
    fecha, titulo_raw = _extraer_fecha_formato_espanol(texto)
    hora, titulo_sin_hora = _extraer_hora_evento_coloquial_y_resto(titulo_raw)

    partes_quoted = re.findall(r'"([^"]*)"', titulo_sin_hora)
    if partes_quoted:
        titulo = partes_quoted[0]
    else:
        titulo = titulo_sin_hora

    titulo = strip_sufijo_para_fecha(titulo.strip())
    return titulo, fecha, hora, dur


def _parsear_evento_audio_payload(
    contenido: str,
) -> tuple[str, str | None, str | None, timedelta | None]:
    """Evento por voz: con 'para el' o 'para' + fecha, nombre antes y fecha/hora después."""
    antes, despues = _partir_audio_titulo_y_fecha(contenido)
    if despues.strip():
        n2, fecha_ev, hora_ev, dur_ev = _parsear_args_evento(despues)
        nombre = (antes.strip() or n2.strip()).strip()
        return strip_sufijo_para_el(nombre), fecha_ev, hora_ev, dur_ev
    nom, fe, ho, du = _parsear_args_evento(contenido)
    if not fe:
        nom = strip_sufijo_para_el(nom)
    return nom, fe, ho, du


def _extraer_tipo_fabrica(texto: str) -> tuple[str, str]:
    """Devuelve (tipo: laser|3d|'', texto sin la mención)."""
    t = texto
    tipo = ""
    low = t.lower()
    if re.search(r"\bl[aá]ser\b", low):
        tipo = "laser"
        t = re.sub(r"\bl[aá]ser\b", " ", t, flags=re.IGNORECASE)
    elif re.search(r"\b3\s*d\b|\b3d\b", low):
        tipo = "3d"
        t = re.sub(r"\b3\s*d\b|\b3d\b", " ", t, flags=re.IGNORECASE)
    elif re.search(r"\bimpresi[oó]n\b", low):
        tipo = "3d"
        t = re.sub(r"\bimpresi[oó]n\b", " ", t, flags=re.IGNORECASE)
    return tipo, " ".join(t.split())


def _partir_titulo_fabrica_ocho_palabras(titulo: str) -> tuple[str, str]:
    """Titulo Deck corto (max 8 palabras); el resto pasa a descripcion."""
    w = (titulo or "").strip().split()
    if len(w) <= 8:
        return (titulo or "").strip(), ""
    return " ".join(w[:8]).strip(), " ".join(w[8:]).strip()


def _parsear_texto_fabrica(texto_raw: str) -> tuple[str, str, str, str | None, str]:
    """titulo, medidas, tipo (laser|3d|''), fecha_iso YYYY-MM-DD|None, notas."""
    t = texto_raw.strip()
    if not t:
        return "", "", "", None, ""
    tipo, t = _extraer_tipo_fabrica(t)
    medidas = ""
    m = _PAT_MEDIDAS_FABRICA.search(t)
    if m:
        medidas = m.group(0).strip()
        t = (t[: m.start()] + t[m.end() :]).strip()
        t = " ".join(t.split())
    titulo_largo, fecha_iso, notas = _parsear_args_tarea(t)
    titulo, resto_tit = _partir_titulo_fabrica_ocho_palabras(titulo_largo.strip())
    bloques = [x for x in (resto_tit, notas.strip()) if x]
    notas_f = "\n".join(bloques) if bloques else ""
    return titulo, medidas, tipo, fecha_iso, notas_f.strip()


def _descripcion_deck_fabrica(medidas: str, tipo: str, notas: str) -> str:
    lineas: list[str] = []
    if (medidas or "").strip():
        lineas.append(f"Medidas: {medidas.strip()}")
    if (tipo or "").strip():
        tl = tipo.strip().lower()
        etiqueta = "Láser" if tl == "laser" else ("3D" if tl == "3d" else tipo.strip())
        lineas.append(f"Tipo: {etiqueta}")
    if (notas or "").strip():
        lineas.append(notas.strip())
    return "\n".join(lineas)


def _normalizar_fecha_input_fabrica(texto: str) -> str | None:
    """Cadena vacía = sin fecha; ISO si válido; None si inválido."""
    t = (texto or "").strip()
    if not t or t == "-":
        return ""
    iso, _ = _extraer_fecha_iso_y_resto(t)
    if not iso:
        return None
    try:
        datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return None
    return iso


def _normalizar_tipo_input_fabrica(texto: str) -> str | None:
    t = (texto or "").strip().lower()
    if not t or t == "-":
        return ""
    if t in ("laser", "láser"):
        return "laser"
    if t in ("3d", "3 d", "impresion", "impresión"):
        return "3d"
    return None


def _fabrica_desde_indice_listado(
    context: ContextTypes.DEFAULT_TYPE, indice: int
) -> ItemFabrica | None:
    cache = (context.chat_data or {}).get(CACHE_RM_FABRICA) or []
    if indice < 1 or indice > len(cache):
        return None
    return buscar_fabrica_por_id(cache[indice - 1])


def _formatear_fabrica_lista(it: ItemFabrica) -> str:
    tit = (it.titulo or "").strip() or "(sin titulo)"
    if len(tit) > FAB_RESUMEN_LISTA_MAX:
        tit = tit[:FAB_RESUMEN_LISTA_MAX] + "..."
    extras: list[str] = []
    if (it.tipo or "").strip():
        extras.append(it.tipo.strip())
    if (it.fecha_due or "").strip():
        extras.append(f"vence {it.fecha_due}")
    suf = f" ({', '.join(extras)})" if extras else ""
    return f"{tit}{suf}"


def _formatear_fabrica_completa(it: ItemFabrica) -> str:
    tl = (it.tipo or "").strip()
    tipo_d = "Láser" if tl == "laser" else ("3D" if tl == "3d" else (tl or "(sin tipo)"))
    fd = (it.fecha_due or "").strip()
    fd_disp = fd if fd else "(sin fecha limite)"
    return (
        f"Titulo: {it.titulo or '(vacio)'}\n"
        f"Medidas: {it.medidas or '(vacias)'}\n"
        f"Tipo: {tipo_d}\n"
        f"Fecha limite: {fd_disp}\n"
        f"Notas: {it.notas or '(vacias)'}\n"
        f"Deck: board={it.board_id} stack={it.stack_id} card={it.card_id}\n"
        f"ID: {it.id}"
    )


async def _sincronizar_fabrica_a_deck(it: ItemFabrica) -> bool:
    if not it.board_id or not it.stack_id or not it.card_id:
        return False
    try:
        bid = int(it.board_id)
        sid = int(it.stack_id)
        cid = int(it.card_id)
    except ValueError:
        return False
    desc = _descripcion_deck_fabrica(it.medidas, it.tipo, it.notas)
    fe = (it.fecha_due or "").strip()
    if fe:
        return actualizar_tarjeta_deck(
            bid, sid, cid,
            titulo=it.titulo,
            descripcion=desc,
            fecha_due=fe,
        )
    return actualizar_tarjeta_deck(
        bid, sid, cid,
        titulo=it.titulo,
        descripcion=desc,
        quitar_fecha=True,
    )


def _generar_id_fabrica(titulo: str) -> str:
    base = f"{datetime.now().isoformat()}::fab::{titulo[:400]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


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
    ok, _, _, _ = crear_tarea_deck(
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
    elif texto_raw.startswith("/compra"):
        texto_raw = texto_raw[len("/compra") :].strip()

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


async def cmd_voluntarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/voluntarios"):
        texto_raw = texto_raw[len("/voluntarios") :].strip()
    elif texto_raw.startswith("/voluntario"):
        texto_raw = texto_raw[len("/voluntario") :].strip()

    if not texto_raw:
        await update.message.reply_text(
            f'Uso: /voluntarios "Titulo" [fecha] ["Descripcion"] — tarea en columna Deck '
            f'"{DECK_STACK_VOLUNTARIOS}".\n'
            "Fecha: DD-MM-AAAA, DD-MM, DD, YYYY-MM-DD o antier/ayer/hoy/mañana/pasado (opcional)."
        )
        return

    await _ejecutar_creacion_tarea_deck(
        update,
        texto_raw,
        stack_name=DECK_STACK_VOLUNTARIOS,
        prefijo_exito="Tarea de voluntarios anotada",
    )


async def _crear_fabrica_desde_texto(
    update: Update,
    texto_raw: str,
    *,
    fuente: str,
    msg_trabajo,
) -> bool:
    titulo, medidas, tipo, fecha_iso, notas = _parsear_texto_fabrica(texto_raw)
    if not titulo:
        await msg_trabajo.edit_text(
            "El titulo no puede estar vacio. Ej: soporte motor 10x20 cm laser para 25-03"
        )
        return False
    if fecha_iso:
        try:
            datetime.strptime(fecha_iso, "%Y-%m-%d")
        except ValueError:
            await msg_trabajo.edit_text(f"Fecha invalida: {fecha_iso}")
            return False

    desc = _descripcion_deck_fabrica(medidas, tipo, notas)
    stack_fab = (config.DECK_STACK_FABRICAR or "Fabricar").strip()
    ok, bid, sid, cid = crear_tarea_deck(
        titulo,
        descripcion=desc,
        fecha_due=fecha_iso,
        stack_name=stack_fab,
        assigned_user_uids=_deck_uids_para_update(update),
    )
    if not ok:
        await msg_trabajo.edit_text(
            "No se pudo crear la tarjeta en Deck.\n"
            + (obtener_ultimo_error_deck() or "sin detalle")
        )
        return False

    fid = _generar_id_fabrica(titulo)
    it = ItemFabrica(
        id=fid,
        titulo=titulo,
        medidas=medidas or "",
        fecha_due=fecha_iso or "",
        tipo=tipo or "",
        notas=notas or "",
        board_id=str(bid) if bid is not None else "",
        stack_id=str(sid) if sid is not None else "",
        card_id=str(cid) if cid is not None else "",
        fecha_creacion=datetime.now().isoformat(),
        fuente=fuente,
    )
    añadir_item_fabrica(it)
    partes = [
        f"Fabricacion registrada en Deck [{stack_fab}]: {titulo}",
        f"ID registro: {fid}",
    ]
    if medidas:
        partes.append(f"Medidas: {medidas}")
    if tipo:
        partes.append(f"Tipo: {tipo}")
    if fecha_iso:
        partes.append(f"Fecha limite: {fecha_iso}")
    aviso_asg = obtener_ultimo_aviso_asignacion_deck()
    if aviso_asg:
        partes.append(aviso_asg)
    if not cid:
        partes.append(
            "(Aviso: Deck no devolvio id de tarjeta; /rmfab no podra borrar la tarjeta en la nube.)"
        )
    await msg_trabajo.edit_text("\n".join(partes))
    return True


async def cmd_fabrica(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/fabrica"):
        texto_raw = texto_raw[len("/fabrica") :].strip()
    if not texto_raw:
        await update.message.reply_text(
            "Uso: /fabrica <texto libre>\n"
            "Opcional en el texto: medidas (ej. 10x20 cm), tipo (laser, 3d, impresion), "
            "fecha como en /tarea (DD-MM-AAAA, mañana, martes, etc.).\n"
            f"Columna Deck: {config.DECK_STACK_FABRICAR or 'Fabricar'}."
        )
        return
    msg = await update.message.reply_text("Creando en Fabricar...")
    await _crear_fabrica_desde_texto(update, texto_raw, fuente="telegram_texto", msg_trabajo=msg)


async def cmd_fab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    texto_raw = (update.message.text or "").strip()
    if texto_raw.startswith("/fab"):
        texto_raw = texto_raw[len("/fab") :].strip()
    if not texto_raw:
        await update.message.reply_text(
            "Uso: /fab <igual que /fabrica> — atajo para la columna Fabricar."
        )
        return
    msg = await update.message.reply_text("Creando en Fabricar...")
    await _crear_fabrica_desde_texto(update, texto_raw, fuente="telegram_texto", msg_trabajo=msg)


async def cmd_listfab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    items = leer_fabrica()
    if not items:
        await update.message.reply_text("No hay registros en fabrica.csv.")
        return

    def _clave_fc(it: ItemFabrica) -> datetime:
        raw = (it.fecha_creacion or "").strip()
        if not raw:
            return datetime.min
        if "T" in raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        dt = parsear_solo_fecha(raw)
        return dt if dt is not None else datetime.min

    items.sort(key=lambda x: (_clave_fc(x), x.titulo.lower()), reverse=True)
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_FABRICA] = [x.id for x in items]

    lineas = [f"{i}. {_formatear_fabrica_lista(x)}" for i, x in enumerate(items, 1)]
    cab = f"Fabricacion ({len(items)}), mas recientes primero:\n\n"
    texto_completo = cab + "\n".join(lineas)
    if len(texto_completo) <= MAX_TELEGRAM_MSG:
        await update.message.reply_text(texto_completo)
    else:
        await update.message.reply_text(texto_completo[:MAX_TELEGRAM_MSG])
        await update.message.reply_text(texto_completo[MAX_TELEGRAM_MSG:])


async def cmd_verfab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /verfab <numero>\nEl numero es el de /listfab en este chat."
        )
        return
    arg = context.args[0].strip()
    it: ItemFabrica | None = None
    if arg.isdigit():
        it = _fabrica_desde_indice_listado(context, int(arg))
    else:
        it = buscar_fabrica_por_id(arg)
    if not it:
        await update.message.reply_text(
            "No se encontro ese registro.\nUsa /listfab para ver el listado."
        )
        return
    await _reply_texto_largo(update, _formatear_fabrica_completa(it))


async def cmd_rmfab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text(
            "Uso: /rmfab <numero> [numero ...]\nLos numeros son los de /listfab en este chat."
        )
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text("Solo numeros del listado, separados por espacios.")
        return
    cache = (context.chat_data or {}).get(CACHE_RM_FABRICA) or []
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
            msg += f" Fuera de rango: {sorted(set(fuera))}. Ejecuta /listfab en este chat."
        await update.message.reply_text(msg)
        return

    ok_n = 0
    deck_fail = 0
    for fid in ids_objetivo:
        row = eliminar_fabrica_por_id(fid)
        if not row:
            continue
        if row.board_id and row.stack_id and row.card_id:
            try:
                if not borrar_tarjeta_deck(
                    int(row.board_id), int(row.stack_id), int(row.card_id)
                ):
                    deck_fail += 1
            except (ValueError, TypeError):
                deck_fail += 1
        ok_n += 1

    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_FABRICA, None)
    partes = [f"Registros fabrica eliminados del CSV: {ok_n}."]
    if fuera:
        partes.append(f"Ignorados (fuera de rango): {sorted(set(fuera))}.")
    if deck_fail:
        partes.append(
            f"Aviso: {deck_fail} tarjeta(s) Deck no se pudieron borrar (revisa en Nextcloud)."
        )
    await update.message.reply_text(" ".join(partes))


def _texto_menu_mod_fabrica(item_id: str) -> str:
    lineas = [
        f"Modificando fabricacion (id {item_id}). Elige campo (0 = salir):",
    ]
    for i, (_k, label) in enumerate(CAMPOS_MOD_FABRICA, 1):
        lineas.append(f"{i}. {label}")
    return "\n".join(lineas)


async def _manejar_wizard_mod_fabrica(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    wizard = context.chat_data.get(WIZARD_MOD_FABRICA_KEY)
    if not wizard:
        return False
    user = update.effective_user
    if not user or wizard.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        return False
    iid = wizard["item_id"]
    fase = wizard.get("fase", "menu")

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_FABRICA_KEY, None)
            await update.message.reply_text("Listo (sin mas cambios).")
            return True
        if not text.isdigit():
            await update.message.reply_text("Envia un numero de campo o 0 para salir.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_MOD_FABRICA):
            await update.message.reply_text("Numero invalido.")
            return True
        key, label = CAMPOS_MOD_FABRICA[n - 1]
        wizard["fase"] = "valor"
        wizard["campo_key"] = key
        await update.message.reply_text(
            f"Nuevo valor para: {label}\n"
            f"(una linea; '-' vaciar fecha/tipo; . o = mantener)\n/cancelarmodfab para abortar."
        )
        return True

    key = wizard.get("campo_key")
    if not key:
        wizard["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_fabrica(iid))
        return True

    if _es_mantener_wizard_valor(text):
        wizard["fase"] = "menu"
        wizard.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios en ese campo.\n\n" + _texto_menu_mod_fabrica(iid)
        )
        return True

    it0 = buscar_fabrica_por_id(iid)
    if not it0:
        context.chat_data.pop(WIZARD_MOD_FABRICA_KEY, None)
        await update.message.reply_text("Registro no encontrado; wizard cerrado.")
        return True

    val_raw = "" if text == "-" else text
    if key == "fecha_due":
        norm = _normalizar_fecha_input_fabrica(val_raw)
        if norm is None:
            await update.message.reply_text(
                "Fecha no reconocida. Prueba DD-MM-AAAA, mañana, martes, etc., o '-' sin fecha."
            )
            return True
        val_store = norm
    elif key == "tipo":
        if not val_raw:
            val_store = ""
        else:
            nt = _normalizar_tipo_input_fabrica(val_raw)
            if nt is None:
                await update.message.reply_text("Tipo invalido. Usa: laser, 3d o '-'")
                return True
            val_store = nt
    else:
        val_store = val_raw

    if not actualizar_fabrica_campos(iid, {key: val_store}):
        await update.message.reply_text("No se pudo guardar.")
        context.chat_data.pop(WIZARD_MOD_FABRICA_KEY, None)
        return True

    it1 = buscar_fabrica_por_id(iid)
    if it1:
        deck_ok = await _sincronizar_fabrica_a_deck(it1)
        if not deck_ok and (it1.board_id and it1.card_id):
            await update.message.reply_text(
                "(Aviso: no se pudo actualizar la tarjeta en Deck; datos guardados en CSV.)"
            )

    wizard["fase"] = "menu"
    wizard.pop("campo_key", None)
    await update.message.reply_text(
        "Campo actualizado.\n\n" + _texto_menu_mod_fabrica(iid)
    )
    return True


async def cmd_modfab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or context.chat_data is None:
        await update.message.reply_text(
            "Uso: /modfab <numero>\nEl numero es el de /listfab en este chat."
        )
        return
    arg = context.args[0].strip()
    it: ItemFabrica | None = None
    if arg.isdigit():
        it = _fabrica_desde_indice_listado(context, int(arg))
    if it is None:
        it = buscar_fabrica_por_id(arg)
    if not it:
        await update.message.reply_text(
            "No se encontro ese registro.\nUsa /listfab en este chat."
        )
        return
    user = update.effective_user
    if not user:
        return
    context.chat_data[WIZARD_MOD_FABRICA_KEY] = {
        "user_id": user.id,
        "item_id": it.id,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_fabrica(it.id) + "\n\n/cancelarmodfab para salir."
    )


async def cmd_cancelarmodfab(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_FABRICA_KEY, None)
    await update.message.reply_text("Edicion de fabricacion cancelada.")


def _texto_menu_mod_proyecto(proyecto_id: str) -> str:
    lineas = [
        f"Modificando proyecto (id {proyecto_id}). Elige campo (0 = salir):",
    ]
    for i, (_k, label) in enumerate(CAMPOS_MOD_PROYECTO, 1):
        lineas.append(f"{i}. {label}")
    return "\n".join(lineas)


async def _manejar_wizard_mod_proyecto(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    wizard = context.chat_data.get(WIZARD_MOD_PROYECTO_KEY)
    if not wizard:
        return False
    user = update.effective_user
    if not user or wizard.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        return False
    pid = wizard["proyecto_id"]
    fase = wizard.get("fase", "menu")

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_PROYECTO_KEY, None)
            await update.message.reply_text("Listo (sin mas cambios).")
            return True
        if not text.isdigit():
            await update.message.reply_text("Envia un numero de campo o 0 para salir.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_MOD_PROYECTO):
            await update.message.reply_text("Numero invalido.")
            return True
        _key, label = CAMPOS_MOD_PROYECTO[n - 1]
        wizard["fase"] = "valor"
        wizard["campo_key"] = _key
        await update.message.reply_text(
            f"Nuevo valor para: {label}\n"
            f"(una linea; '-' vaciar; . o = mantener)\n/cancelarmodproyecto para abortar."
        )
        return True

    key = wizard.get("campo_key")
    if not key:
        wizard["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_proyecto(pid))
        return True

    if _es_mantener_wizard_valor(text):
        wizard["fase"] = "menu"
        wizard.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios en ese campo.\n\n" + _texto_menu_mod_proyecto(pid)
        )
        return True

    p0 = buscar_proyecto_por_id(pid)
    if not p0:
        context.chat_data.pop(WIZARD_MOD_PROYECTO_KEY, None)
        await update.message.reply_text("Proyecto no encontrado; wizard cerrado.")
        return True

    val_raw = "" if text in ("-", "—") else text
    if key == "fecha_fin":
        if not val_raw:
            val_store = ""
        else:
            dt = parsear_solo_fecha(val_raw)
            if dt is None:
                await update.message.reply_text(
                    "Fecha no reconocida. Usa el mismo formato que en el alta o '-'."
                )
                return True
            val_store = formatear_fecha(dt)
    elif key == "estado":
        est = val_raw.lower().strip()
        if est not in ESTADOS_PROYECTO_VALIDOS:
            await update.message.reply_text(
                "Estado no valido: idea, activo, en_espera, presupuestado, completado, cancelado"
            )
            return True
        val_store = est
    elif key == "email_contacto":
        if not val_raw:
            await update.message.reply_text("El email no puede quedar vacio.")
            return True
        if not _email_valido_proyecto(val_raw):
            await update.message.reply_text("Email no valido.")
            return True
        val_store = val_raw.strip()
    elif key in ("presupuesto", "tags"):
        val_store = val_raw
    else:
        if not val_raw and key == "titulo":
            await update.message.reply_text("El titulo no puede estar vacio.")
            return True
        val_store = val_raw

    p1 = replace(p0, **{key: val_store})
    if not actualizar_proyecto(p1):
        await update.message.reply_text("No se pudo guardar.")
        context.chat_data.pop(WIZARD_MOD_PROYECTO_KEY, None)
        return True

    wizard["fase"] = "menu"
    wizard.pop("campo_key", None)
    await update.message.reply_text(
        "Campo actualizado.\n\n" + _texto_menu_mod_proyecto(pid)
    )
    return True


async def cmd_modproyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or context.chat_data is None:
        await update.message.reply_text(
            "Uso: /modproyecto <numero>\nEl numero es el de /listproyectos en este chat."
        )
        return
    arg = context.args[0].strip()
    p: Proyecto | None = None
    if arg.isdigit():
        p = _proyecto_desde_indice_listado(context, int(arg))
    if p is None:
        p = buscar_proyecto_por_id(arg)
    if not p:
        await update.message.reply_text(
            "No se encontro ese proyecto.\nUsa /listproyectos en este chat."
        )
        return
    user = update.effective_user
    if not user:
        return
    context.chat_data[WIZARD_MOD_PROYECTO_KEY] = {
        "user_id": user.id,
        "proyecto_id": p.id,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_proyecto(p.id) + "\n\n/cancelarmodproyecto para salir."
    )


async def cmd_cancelarmodproyecto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_PROYECTO_KEY, None)
    await update.message.reply_text("Edicion de proyecto cancelada.")


async def _ejecutar_creacion_evento_desde_texto(update: Update, texto_raw: str) -> bool:
    """Crea evento CalDAV desde texto ya sin prefijo /evento. Devuelve True si se creó."""
    nombre, fecha_ev, hora_ev, dur_ev = _parsear_args_evento(texto_raw)

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

    dur_kw = dur_ev if hora_ev else None
    msg = await update.message.reply_text("Creando evento en el calendario...")
    ok = crear_evento(nombre, fecha_iso, hora=hora_ev, duracion=dur_kw)

    if ok:
        partes = [f"Evento creado: {nombre}", f"Fecha: {fecha_ev}"]
        if hora_ev:
            if dur_ev:
                partes.append(
                    f"Hora inicio: {hora_ev} (duracion {_formatear_duracion_usuario(dur_ev)})"
                )
            else:
                partes.append(f"Hora inicio: {hora_ev} (duracion 1 h)")
        elif dur_ev:
            partes.append(
                "Nota: sin hora concreta el evento es de dia completo; la duracion no se aplico."
            )
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
            "Uso: /evento <nombre> <fecha> [hora] [duracion]\n"
            "Fecha: DD-MM-AAAA o DD/MM/AAAA; año 2 cifras -> 20YY; DD-MM sin año = año actual; "
            "solo DD (1-31, unico en el texto) = mes actual; antier/ayer/hoy/mañana/pasado; "
            "o nombre de dia (proximo lunes, martes, …).\n"
            "Hora: HH:MM o coloquial (a las 5 y media de la tarde, siete de la tarde).\n"
            "Duracion: durante 2 horas, durante 3 dias, durante 30 minutos, durante una hora.\n"
            "Ejemplo: /evento Reunion 20-03-26 a las 14:30 durante 2 horas"
        )
        return

    await _ejecutar_creacion_evento_desde_texto(update, texto_raw)


async def cmd_listeventos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return

    dias = _dias_ventana_eventos(list(context.args or []))
    msg = await update.message.reply_text("Consultando eventos en CalDAV...")

    un_ag = _username_telegram_para_agenda(update)
    eventos = listar_eventos_proximos_dias(dias, agenda_telegram_username=un_ag)
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
        fh = formatear_dia_mes_sin_anio(ev["start_iso"])
        lineas.append(f"{i}. [{fh}] {tit}")

    cabecera = f"Eventos proximos {dias} dias ({len(eventos)}):\n\n"
    texto_completo = cabecera + "\n".join(lineas)

    MAX_MSG = 4000
    if len(texto_completo) <= MAX_MSG:
        await msg.edit_text(texto_completo)
    else:
        await msg.edit_text(texto_completo[:MAX_MSG])
        await update.message.reply_text(texto_completo[MAX_MSG:])


async def cmd_informame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    msg = await update.message.reply_text("Consultando agenda (7 dias)...")
    un_ag = _username_telegram_para_agenda(update)
    texto = texto_agenda_proximos_dias(7, telegram_username=un_ag)
    await msg.delete()
    await _reply_texto_largo(update, texto)


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    dias = 7
    if context.args:
        a0 = (context.args[0] or "").strip()
        if a0.isdigit():
            dias = max(1, min(90, int(a0)))
        else:
            await update.message.reply_text(
                "Uso: /info [numero de dias]\nPor defecto 7 dias (maximo 90)."
            )
            return
    msg = await update.message.reply_text(f"Consultando agenda ({dias} dias)...")
    un_ag = _username_telegram_para_agenda(update)
    texto = texto_agenda_proximos_dias(
        dias, telegram_username=un_ag, mostrar_calendario=False
    )
    await msg.delete()
    await _reply_texto_largo(update, texto)


def _texto_menu_mod_lista(kind: str, entity_id: str) -> str:
    _cache_key, campos, lista_cmd = MOD_LISTA_CAMPOS[kind]
    lineas = [
        f"Modificando {kind} (id {entity_id}). Elige campo (0 = salir):",
    ]
    for i, (_k, label) in enumerate(campos, 1):
        lineas.append(f"{i}. {label}")
    return "\n".join(lineas)


def _entidad_mod_lista_por_id(kind: str, eid: str):
    if kind == "convo":
        return buscar_por_id(eid)
    if kind == "idea":
        return buscar_idea_por_id(eid)
    if kind == "memoria":
        return buscar_memoria_por_id(eid)
    if kind == "func":
        return buscar_func_por_id(eid)
    if kind == "inv":
        return buscar_investigacion_por_id(eid)
    if kind == "enlace":
        return buscar_enlace_por_id(eid)
    if kind == "pendiente":
        return buscar_pendiente_por_id(eid)
    if kind == "rec":
        return buscar_recomendacion_por_id(eid)
    if kind == "diario":
        return buscar_diario_por_id(eid)
    if kind == "huevo":
        return buscar_huevo_por_id(eid)
    return None


def _guardar_entidad_mod_lista(kind: str, ent) -> bool:
    if kind == "convo":
        return actualizar_convocatoria_registro(ent)
    if kind == "idea":
        return actualizar_idea(ent)
    if kind == "memoria":
        return actualizar_memoria(ent)
    if kind == "func":
        return actualizar_func(ent)
    if kind == "inv":
        return actualizar_investigacion_registro(ent)
    if kind == "enlace":
        return actualizar_enlace(ent)
    if kind == "pendiente":
        return actualizar_pendiente(ent)
    if kind == "rec":
        return actualizar_recomendacion(ent)
    if kind == "diario":
        return actualizar_diario_entrada(ent)
    if kind == "huevo":
        return actualizar_huevo_registro(ent)
    return False


def _id_desde_indice_mod_lista(context: ContextTypes.DEFAULT_TYPE, kind: str, indice: int) -> str | None:
    cache_key, _, _ = MOD_LISTA_CAMPOS[kind]
    cache = (context.chat_data or {}).get(cache_key) or []
    if indice < 1 or indice > len(cache):
        return None
    return str(cache[indice - 1])


async def _iniciar_mod_lista(
    update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, cmd_name: str
) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or context.chat_data is None:
        _ck, _cf, lista_cmd = MOD_LISTA_CAMPOS[kind]
        await update.message.reply_text(
            f"Uso: /{cmd_name} <numero>\nEl numero es el de {lista_cmd} en este chat."
        )
        return
    arg = context.args[0].strip()
    ent = None
    eid: str | None = None
    if arg.isdigit():
        eid = _id_desde_indice_mod_lista(context, kind, int(arg))
        if eid:
            ent = _entidad_mod_lista_por_id(kind, eid)
    if ent is None:
        ent = _entidad_mod_lista_por_id(kind, arg)
        if ent:
            eid = ent.id
    if not ent or not eid:
        _ck, _cf, lista_cmd = MOD_LISTA_CAMPOS[kind]
        extra = ""
        if kind == "huevo":
            extra = "\nPara un dia olvidado sin registro: /huevos <cantidad> para el <fecha>."
        await update.message.reply_text(
            f"No se encontro ese registro.\nUsa {lista_cmd} en este chat.{extra}"
        )
        return
    user = update.effective_user
    if not user:
        return
    context.chat_data[WIZARD_MOD_LISTA_KEY] = {
        "user_id": user.id,
        "kind": kind,
        "entity_id": eid,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_lista(kind, eid) + "\n\n/cancelarmodlista para salir."
    )


async def _manejar_wizard_mod_lista(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    wizard = context.chat_data.get(WIZARD_MOD_LISTA_KEY)
    if not wizard:
        return False
    user = update.effective_user
    if not user or wizard.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Envia texto, o /cancelarmodlista.")
        return True
    kind: str = wizard["kind"]
    eid: str = wizard["entity_id"]
    fase = wizard.get("fase", "menu")
    _ck, campos, _lc = MOD_LISTA_CAMPOS[kind]

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_LISTA_KEY, None)
            await update.message.reply_text("Listo (sin mas cambios).")
            return True
        if not text.isdigit():
            await update.message.reply_text("Envia un numero de campo o 0 para salir.")
            return True
        n = int(text)
        if n < 1 or n > len(campos):
            await update.message.reply_text("Numero invalido.")
            return True
        _key, label = campos[n - 1]
        wizard["fase"] = "valor"
        wizard["campo_key"] = _key
        await update.message.reply_text(
            f"Nuevo valor para: {label}\n"
            f"(una linea; '-' vacia donde aplique; . o = deja el valor actual)\n"
            f"/cancelarmodlista para abortar."
        )
        return True

    key = wizard.get("campo_key")
    if not key:
        wizard["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_lista(kind, eid))
        return True

    if _es_mantener_wizard_valor(text):
        wizard["fase"] = "menu"
        wizard.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios en ese campo.\n\n" + _texto_menu_mod_lista(kind, eid)
        )
        return True

    ent0 = _entidad_mod_lista_por_id(kind, eid)
    if not ent0:
        context.chat_data.pop(WIZARD_MOD_LISTA_KEY, None)
        await update.message.reply_text("Registro no encontrado; wizard cerrado.")
        return True

    val_raw = "" if text in ("-", "—") else text
    err: str | None = None
    ent1 = ent0

    if kind == "convo":
        if key == "titulo" and not val_raw:
            err = "El titulo no puede estar vacio."
        elif key == "url" and not val_raw:
            err = "La URL no puede estar vacia."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "idea":
        if key == "resumen" and not val_raw:
            err = "El resumen no puede estar vacio."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "memoria":
        if key == "resumen" and not val_raw:
            err = "El resumen no puede estar vacio."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "func":
        if key == "texto" and not val_raw:
            err = "El texto no puede estar vacio."
        elif key == "prioridad":
            try:
                pr = max(1, min(5, int(val_raw)))
            except ValueError:
                err = "Prioridad invalida (1-5)."
            else:
                ent1 = replace(ent0, prioridad=pr)
        elif key == "estado":
            est = val_raw.lower().strip()
            if est not in ESTADOS_VALIDOS:
                err = f"Estado invalido: {', '.join(sorted(ESTADOS_VALIDOS))}"
            else:
                ent1 = replace(ent0, estado=est)
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "inv":
        if key == "concepto" and not val_raw:
            err = "El concepto no puede estar vacio."
        elif key == "estado":
            est = val_raw.lower().strip()
            if est not in ESTADOS_INVESTIGACION:
                err = f"Estado invalido: {', '.join(sorted(ESTADOS_INVESTIGACION))}"
            else:
                ent1 = replace(ent0, estado=est)
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "enlace":
        if key == "url" and not val_raw:
            err = "La URL no puede estar vacia."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "pendiente":
        if key == "texto" and not val_raw:
            err = "El texto no puede estar vacio."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "rec":
        if key in ("tipo", "nombre") and not val_raw:
            err = "Tipo y nombre no pueden quedar vacios."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "diario":
        if key == "resumen" and not val_raw:
            err = "El resumen no puede estar vacio."
        else:
            ent1 = replace(ent0, **{key: val_raw})
    elif kind == "huevo":
        if key == "cantidad":
            try:
                c = max(0, int(val_raw))
            except ValueError:
                err = "Cantidad invalida."
            else:
                ent1 = replace(ent0, cantidad=c)
        elif key == "fecha":
            try:
                datetime.strptime(val_raw.strip(), "%Y-%m-%d")
            except ValueError:
                err = "Fecha invalida (YYYY-MM-DD)."
            else:
                ent1 = replace(ent0, fecha=val_raw.strip())
        else:
            ent1 = replace(ent0, **{key: val_raw})

    if err:
        await update.message.reply_text(err)
        return True

    if not _guardar_entidad_mod_lista(kind, ent1):
        await update.message.reply_text("No se pudo guardar.")
        context.chat_data.pop(WIZARD_MOD_LISTA_KEY, None)
        return True

    wizard["fase"] = "menu"
    wizard.pop("campo_key", None)
    await update.message.reply_text(
        "Campo actualizado.\n\n" + _texto_menu_mod_lista(kind, eid)
    )
    return True


async def cmd_cancelarmodlista(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_LISTA_KEY, None)
    await update.message.reply_text("Edicion cancelada.")


async def cmd_modconvo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "convo", "modconvo")


async def cmd_modidea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "idea", "modidea")


async def cmd_modmemoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "memoria", "modmemoria")


async def cmd_modfunc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "func", "modfunc")


async def cmd_modinv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "inv", "modinv")


async def cmd_modenlace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "enlace", "modenlace")


async def cmd_modpendiente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "pendiente", "modpendiente")


async def cmd_modrec(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "rec", "modrec")


async def cmd_moddiario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "diario", "moddiario")


async def cmd_modhuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_lista(update, context, "huevo", "modhuevo")


def _notas_credenciales(update: Update) -> tuple[str, str] | None:
    u = update.effective_user
    if not u:
        return None
    un = (u.username or "").strip().lstrip("@").lower()
    return notes_nextcloud.credenciales_para_telegram_username(un, u.id)


CAMPOS_MOD_TAREA: list[tuple[str, str]] = [
    ("titulo", "Titulo"),
    ("descripcion", "Descripcion"),
    ("due", "Fecha vencimiento (YYYY-MM-DD; '-' quitar; . mantener)"),
]


def _texto_menu_mod_tarea() -> str:
    lineas = ["Modificar tarea Deck. Campo (0 = salir):"]
    for i, (_k, lab) in enumerate(CAMPOS_MOD_TAREA, 1):
        lineas.append(f"{i}. {lab}")
    return "\n".join(lineas)


async def _iniciar_mod_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or not context.args[0].isdigit() or context.chat_data is None:
        await update.message.reply_text(
            "Uso: /modtarea <numero>\nEl numero es el de /listtareas en este chat."
        )
        return
    n = int(context.args[0].strip())
    cache = (context.chat_data or {}).get(CACHE_RM_TAREAS_DECK) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text("Indice invalido. Ejecuta /listtareas en este chat.")
        return
    item = cache[n - 1]
    usr = update.effective_user
    if not usr:
        return
    context.chat_data[WIZARD_MOD_TAREA_KEY] = {
        "user_id": usr.id,
        "board_id": int(item["board_id"]),
        "stack_id": int(item["stack_id"]),
        "card_id": int(item["card_id"]),
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_tarea() + "\n\n/cancelarmodtarea para salir."
    )


async def cmd_cancelarmodtarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_TAREA_KEY, None)
    await update.message.reply_text("Edicion de tarea cancelada.")


async def _manejar_wizard_mod_tarea(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    w = context.chat_data.get(WIZARD_MOD_TAREA_KEY)
    if not w:
        return False
    user = update.effective_user
    if not user or w.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Envia texto o /cancelarmodtarea.")
        return True
    fase = w.get("fase", "menu")
    bid, sid, cid = w["board_id"], w["stack_id"], w["card_id"]
    cur = obtener_tarjeta_deck(bid, sid, cid)
    if not cur:
        context.chat_data.pop(WIZARD_MOD_TAREA_KEY, None)
        await update.message.reply_text(
            "Tarjeta no encontrada.\n" + (obtener_ultimo_error_deck() or "")
        )
        return True

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_TAREA_KEY, None)
            await update.message.reply_text("Listo.")
            return True
        if not text.isdigit():
            await update.message.reply_text("Numero de campo o 0.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_MOD_TAREA):
            await update.message.reply_text("Opcion invalida.")
            return True
        key, label = CAMPOS_MOD_TAREA[n - 1]
        w["fase"] = "valor"
        w["campo_key"] = key
        await update.message.reply_text(
            f"Nuevo valor: {label}\n(una linea; '-' vaciar donde aplique; . o = mantener)\n"
            "/cancelarmodtarea para abortar."
        )
        return True

    key = w.get("campo_key")
    if not key:
        w["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_tarea())
        return True

    if _es_mantener_wizard_valor(text):
        w["fase"] = "menu"
        w.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios en ese campo.\n\n" + _texto_menu_mod_tarea()
        )
        return True

    ok_up = False
    if key == "titulo":
        tit = "" if text in ("-", "—") else text
        if not tit:
            await update.message.reply_text("El titulo no puede quedar vacio.")
            return True
        ok_up = actualizar_tarjeta_deck(bid, sid, cid, titulo=tit)
    elif key == "descripcion":
        ok_up = actualizar_tarjeta_deck(
            bid, sid, cid, descripcion="" if text in ("-", "—") else text
        )
    elif key == "due":
        if text in ("-", "—"):
            ok_up = actualizar_tarjeta_deck(bid, sid, cid, quitar_fecha=True)
        else:
            raw = text.strip()
            try:
                datetime.strptime(raw[:10], "%Y-%m-%d")
            except ValueError:
                await update.message.reply_text("Usa YYYY-MM-DD o '-' para quitar fecha.")
                return True
            ok_up = actualizar_tarjeta_deck(bid, sid, cid, fecha_due=raw[:10])

    if not ok_up:
        await update.message.reply_text(
            "No se pudo actualizar.\n" + (obtener_ultimo_error_deck() or "")
        )
        return True

    w["fase"] = "menu"
    w.pop("campo_key", None)
    await update.message.reply_text(
        "Campo actualizado.\n\n" + _texto_menu_mod_tarea()
    )
    return True


CAMPOS_MOD_EVENTO: list[tuple[str, str]] = [
    ("titulo", "Titulo"),
    ("descripcion", "Descripcion"),
    ("fecha", "Fecha inicio (YYYY-MM-DD)"),
    ("hora", "Hora (HH:MM) o 'dia' para todo el dia"),
    ("duracion", "Duracion (ej. durante 2 horas; . mantener)"),
]


def _texto_menu_mod_evento() -> str:
    lineas = ["Modificar evento CalDAV. Campo (0 = salir):"]
    for i, (_k, lab) in enumerate(CAMPOS_MOD_EVENTO, 1):
        lineas.append(f"{i}. {lab}")
    return "\n".join(lineas)


async def _iniciar_mod_evento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or not context.args[0].isdigit() or context.chat_data is None:
        await update.message.reply_text(
            "Uso: /modevento <numero>\nEl numero es el de /listeventos en este chat."
        )
        return
    n = int(context.args[0].strip())
    cache = (context.chat_data or {}).get(CACHE_RM_EVENTOS) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text("Indice invalido. Ejecuta /listeventos en este chat.")
        return
    url_ev = (cache[n - 1] or "").strip()
    if not url_ev:
        await update.message.reply_text("URL de evento vacia en la cache.")
        return
    usr = update.effective_user
    if not usr:
        return
    context.chat_data[WIZARD_MOD_EVENTO_KEY] = {
        "user_id": usr.id,
        "event_url": url_ev,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_evento() + "\n\n/cancelarmodevento para salir."
    )


async def cmd_cancelarmodevento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_EVENTO_KEY, None)
    await update.message.reply_text("Edicion de evento cancelada.")


async def cmd_modtarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_tarea(update, context)


async def cmd_modevento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_evento(update, context)


async def _manejar_wizard_mod_evento(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    w = context.chat_data.get(WIZARD_MOD_EVENTO_KEY)
    if not w:
        return False
    user = update.effective_user
    if not user or w.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Envia texto o /cancelarmodevento.")
        return True
    url_ev = (w.get("event_url") or "").strip()
    fase = w.get("fase", "menu")

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_EVENTO_KEY, None)
            await update.message.reply_text("Listo.")
            return True
        if not text.isdigit():
            await update.message.reply_text("Numero de campo o 0.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_MOD_EVENTO):
            await update.message.reply_text("Opcion invalida.")
            return True
        _key, label = CAMPOS_MOD_EVENTO[n - 1]
        w["fase"] = "valor"
        w["campo_key"] = _key
        await update.message.reply_text(
            f"Nuevo valor: {label}\n(una linea; '-' vaciar descripcion; . mantener)\n"
            "/cancelarmodevento para abortar."
        )
        return True

    key = w.get("campo_key")
    if not key:
        w["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_evento())
        return True

    if _es_mantener_wizard_valor(text):
        w["fase"] = "menu"
        w.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios.\n\n" + _texto_menu_mod_evento()
        )
        return True

    ok = False
    if key == "duracion":
        du, _rest = _extraer_duracion_evento_y_resto(text)
        if du is None:
            await update.message.reply_text(
                "No se entendio la duracion. Ej: durante 2 horas, durante 30 minutos."
            )
            return True
        ok = actualizar_evento_por_url(url_ev, duracion=du)
    elif key == "titulo":
        tit = "" if text in ("-", "—") else text
        if not tit:
            await update.message.reply_text("El titulo no puede quedar vacio.")
            return True
        ok = actualizar_evento_por_url(url_ev, titulo=tit)
    elif key == "descripcion":
        ok = actualizar_evento_por_url(
            url_ev, descripcion="" if text in ("-", "—") else text
        )
    elif key == "fecha":
        try:
            datetime.strptime(text.strip()[:10], "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("Usa YYYY-MM-DD.")
            return True
        ok = actualizar_evento_por_url(url_ev, fecha_yyyy_mm_dd=text.strip()[:10])
    elif key == "hora":
        tstrip = text.strip().lower()
        if tstrip in ("dia", "día", "todoeldia", "dia_completo"):
            ok = actualizar_evento_por_url(url_ev, todo_el_dia=True)
        else:
            try:
                datetime.strptime(text.strip(), "%H:%M")
            except ValueError:
                await update.message.reply_text("Usa HH:MM o la palabra 'dia' (todo el dia).")
                return True
            ok = actualizar_evento_por_url(url_ev, hora_hhmm=text.strip())

    if not ok:
        await update.message.reply_text(
            "No se pudo actualizar el evento.\n" + (obtener_ultimo_error_evento() or "")
        )
        return True

    w["fase"] = "menu"
    w.pop("campo_key", None)
    await update.message.reply_text("Campo actualizado.\n\n" + _texto_menu_mod_evento())
    return True


CAMPOS_MOD_TIEMPO: list[tuple[str, str]] = [
    ("proyecto", "Proyecto (numero de /listproyectos en este chat)"),
    ("inicio", "Fecha y hora inicio (texto flexible, ver /modtiempo)"),
    ("fin", "Fecha y hora fin (solo registros cerrados; editable)"),
]


def _texto_menu_mod_tiempo() -> str:
    lineas = ["Modificar tiempo (CSV). Campo (0 = salir):"]
    for i, (_k, lab) in enumerate(CAMPOS_MOD_TIEMPO, 1):
        lineas.append(f"{i}. {lab}")
    return "\n".join(lineas)


async def _iniciar_mod_tiempo_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args or not context.args[0].isdigit() or context.chat_data is None:
        await update.message.reply_text(
            "Uso: /modtiempo <numero>\nSin fecha/hora: abre wizard. "
            "Con argumentos extra: mismo uso rapido que antes."
        )
        return
    n = int(context.args[0].strip())
    cache = (context.chat_data or {}).get(CACHE_RM_TIEMPOS) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text("Indice invalido. Ejecuta /listtiempo en este chat.")
        return
    tid = cache[n - 1]
    t = buscar_tiempo_por_id(tid)
    if not t:
        await update.message.reply_text("Registro no encontrado.")
        return
    usr = update.effective_user
    if not usr:
        return
    context.chat_data[WIZARD_MOD_TIEMPO_KEY] = {
        "user_id": usr.id,
        "tiempo_id": t.id,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_tiempo() + "\n\n/cancelarmodtiempo para salir."
    )


async def cmd_cancelarmodtiempo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_TIEMPO_KEY, None)
    await update.message.reply_text("Edicion de tiempo cancelada.")


async def _manejar_wizard_mod_tiempo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    w = context.chat_data.get(WIZARD_MOD_TIEMPO_KEY)
    if not w:
        return False
    user = update.effective_user
    if not user or w.get("user_id") != user.id:
        return False
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Envia texto o /cancelarmodtiempo.")
        return True
    tid = w.get("tiempo_id")
    t = buscar_tiempo_por_id(tid) if tid else None
    if not t:
        context.chat_data.pop(WIZARD_MOD_TIEMPO_KEY, None)
        await update.message.reply_text("Registro de tiempo ya no existe.")
        return True
    fase = w.get("fase", "menu")

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_TIEMPO_KEY, None)
            await update.message.reply_text("Listo.")
            return True
        if not text.isdigit():
            await update.message.reply_text("Numero de campo o 0.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_MOD_TIEMPO):
            await update.message.reply_text("Opcion invalida.")
            return True
        _key, label = CAMPOS_MOD_TIEMPO[n - 1]
        w["fase"] = "valor"
        w["campo_key"] = _key
        await update.message.reply_text(
            f"Nuevo valor: {label}\n/cancelarmodtiempo para abortar."
        )
        return True

    key = w.get("campo_key")
    if not key:
        w["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_tiempo())
        return True

    if _es_mantener_wizard_valor(text):
        w["fase"] = "menu"
        w.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios.\n\n" + _texto_menu_mod_tiempo()
        )
        return True

    t2 = replace(t)
    if key == "proyecto":
        if not text.isdigit():
            await update.message.reply_text("Indice numerico de /listproyectos.")
            return True
        n = int(text)
        pc = (context.chat_data or {}).get(CACHE_RM_PROYECTOS) or []
        if n < 1 or n > len(pc):
            await update.message.reply_text("Ejecuta /listproyectos en este chat antes.")
            return True
        old_pid = t.id_proyecto
        t2 = replace(t2, id_proyecto=pc[n - 1])
        if not actualizar_tiempo(t2):
            await update.message.reply_text("No se pudo guardar.")
            return True
        sincronizar_tiempo_total_proyecto(old_pid)
        sincronizar_tiempo_total_proyecto(t2.id_proyecto)
    elif key == "inicio":
        ini = parsear_fecha_hora(text)
        if ini is None:
            await update.message.reply_text("Fecha/hora inicio no reconocida.")
            return True
        t2 = replace(t2, fecha_hora_inicio=formatear_fecha_hora(ini))
        fin_d = parsear_fecha_hora(t2.fecha_hora_fin)
        if fin_d and fin_d >= ini:
            t2 = replace(
                t2,
                cantidad_tiempo=str(minutos_entre(ini, fin_d)),
            )
        if not actualizar_tiempo(t2):
            await update.message.reply_text("No se pudo guardar.")
            return True
        sincronizar_tiempo_total_proyecto(t2.id_proyecto)
    elif key == "fin":
        if es_activo(t):
            await update.message.reply_text(
                "Este tiempo sigue activo (sin fin). Usa /tiempofin o /modtiempo n <fecha fin>."
            )
            return True
        fin = parsear_fecha_hora(text)
        if fin is None:
            await update.message.reply_text("Fecha/hora fin no reconocida.")
            return True
        ini = parsear_fecha_hora(t2.fecha_hora_inicio)
        if ini is None or fin < ini:
            await update.message.reply_text("Fin invalida respecto al inicio.")
            return True
        t2 = replace(
            t2,
            fecha_hora_fin=formatear_fecha_hora(fin),
            cantidad_tiempo=str(minutos_entre(ini, fin)),
        )
        if not actualizar_tiempo(t2):
            await update.message.reply_text("No se pudo guardar.")
            return True
        sincronizar_tiempo_total_proyecto(t2.id_proyecto)

    w["fase"] = "menu"
    w.pop("campo_key", None)
    await update.message.reply_text(
        "Campo actualizado.\n\n" + _texto_menu_mod_tiempo()
    )
    return True


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
            "Uso: /rmfunc o /rmfn <numero> [numero ...]\n"
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
    if not context.args:
        await update.message.reply_text(
            "Uso: /huevos <cantidad> [para el <fecha>]\n"
            "Ejemplos: /huevos 12 | /huevos 12 para ayer | /huevos 12 para el 2026-04-01"
        )
        return
    texto = " ".join(context.args).strip()
    partes = texto.split(None, 1)
    try:
        cantidad = int(partes[0].strip())
    except ValueError:
        await update.message.reply_text("La cantidad debe ser un numero entero.")
        return
    if cantidad <= 0:
        await update.message.reply_text("La cantidad debe ser mayor que cero.")
        return

    fecha_objetivo = datetime.now().strftime("%Y-%m-%d")
    resto = partes[1].strip() if len(partes) > 1 else ""
    if resto:
        if not resto.lower().startswith("para "):
            resto = f"para {resto}"
        _, fecha_parseada = extraer_cuerpo_y_fecha_dia_para_el(f"x {resto}")
        if not fecha_parseada:
            await update.message.reply_text(
                "No pude interpretar la fecha. Usa formatos como: "
                "ayer, lunes, 15-03-2026 o 2026-03-15."
            )
            return
        fecha_objetivo = fecha_parseada
    añadir_huevo(cantidad, fecha_objetivo, fuente="telegram")
    total_dia = total_cantidad_en_fecha(fecha_objetivo)
    await update.message.reply_text(
        f"Registro de huevos guardado.\n"
        f"Fecha: {fecha_objetivo}\n"
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
        await update.message.reply_text(
            "Uso: /diario <texto>\n"
            "Al final puedes poner 'para el <fecha>' para guardar en un dia concreto (ej. para el 15-03-2026)."
        )
        return
    texto = " ".join(context.args).strip()
    if not texto:
        await update.message.reply_text("El texto del diario no puede estar vacio.")
        return
    usr = update.effective_user
    etiqueta = (usr.username or str(usr.id)) if usr else ""
    cuerpo, fecha_dia = extraer_cuerpo_y_fecha_dia_para_el(texto)
    if not cuerpo.strip():
        await update.message.reply_text("El texto del diario no puede estar vacio (sin contar la fecha).")
        return
    try:
        ent = diario_añadir_entrada(
            cuerpo.strip(),
            fuente="telegram_texto",
            telegram_user=etiqueta,
            fecha_dia=fecha_dia,
        )
    except ValueError:
        await update.message.reply_text("El texto del diario no puede estar vacio.")
        return
    await update.message.reply_text(
        f"Entrada de diario guardada.\nDia: {ent.fecha_dia}\nArchivo: {ent.ruta}"
    )


async def cmd_listdiario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    lim = 25
    if context.args and context.args[0].strip().isdigit():
        lim = max(1, min(100, int(context.args[0].strip())))
    items = listar_diario_recientes(lim)
    if not items:
        await update.message.reply_text("No hay entradas en diario.csv.")
        return
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_DIARIO_IDS] = [e.id for e in items]
    lineas = []
    for i, e in enumerate(items, 1):
        rs = (e.resumen or "").strip() or "(vacio)"
        if len(rs) > 72:
            rs = rs[:69] + "..."
        lineas.append(f"{i}. [{e.fecha_dia}] {rs}")
    await update.message.reply_text(
        f"Diario ({len(items)} ultimas):\n\n" + "\n".join(lineas)
    )


async def cmd_verdiario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /verdiario <numero>\nEl de /listdiario en este chat.")
        return
    arg = context.args[0].strip()
    ent = None
    if arg.isdigit():
        cache = (context.chat_data or {}).get(CACHE_RM_DIARIO_IDS) or []
        n = int(arg)
        if 1 <= n <= len(cache):
            ent = buscar_diario_por_id(cache[n - 1])
    if ent is None:
        ent = buscar_diario_por_id(arg)
    if not ent:
        await update.message.reply_text("No encontrado. Usa /listdiario.")
        return
    body = (
        f"ID: {ent.id}\n"
        f"Dia: {ent.fecha_dia}\n"
        f"Ingesta: {formatear_fecha_ver(ent.fecha_ingesta)}\n"
        f"Fuente: {ent.fuente}\n"
        f"Usuario: {ent.telegram_user or '(n/d)'}\n\n"
        f"Resumen:\n{ent.resumen or '(vacio)'}"
    )
    await _reply_texto_largo(update, body)


async def cmd_rmdiario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /rmdiario <numero ...>\nIndices de /listdiario.")
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text("Solo numeros del listado.")
        return
    cache = (context.chat_data or {}).get(CACHE_RM_DIARIO_IDS) or []
    ok = 0
    fuera: list[int] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        if eliminar_diario_por_id(cache[n - 1]):
            ok += 1
    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_DIARIO_IDS, None)
    msg = f"Entradas eliminadas del indice diario: {ok}."
    if fuera:
        msg += f" Fuera de rango: {sorted(set(fuera))}."
    await update.message.reply_text(msg)


async def cmd_rec(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /rec <tipo> <nombre> [notas...]\n"
            "Ej: /rec escritor Ursula K. Le Guin ciencia ficcion"
        )
        return
    tipo = context.args[0].strip()
    nombre = context.args[1].strip()
    notas = " ".join(context.args[2:]).strip() if len(context.args) > 2 else ""
    usr = update.effective_user
    etiqueta = (usr.username or str(usr.id)) if usr else ""
    try:
        r = añadir_recomendacion(
            tipo=tipo,
            nombre=nombre,
            notas=notas,
            fuente="telegram",
            telegram_user=etiqueta,
        )
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    await update.message.reply_text(
        f"Recomendacion guardada.\nID: {r.id}\n{r.tipo}: {r.nombre}"
    )


async def cmd_listrecomendaciones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    items = listar_recomendaciones_recientes(80)
    if not items:
        await update.message.reply_text("No hay recomendaciones.")
        return
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_REC_IDS] = [x.id for x in items]
    lineas = []
    for i, x in enumerate(items, 1):
        nom = (x.nombre or "")[:50]
        lineas.append(f"{i}. [{x.tipo}] {nom}")
    await update.message.reply_text(
        f"Recomendaciones ({len(items)}):\n\n" + "\n".join(lineas)
    )


async def cmd_verrec(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /verrec <numero>\nEl de /listrecomendaciones.")
        return
    arg = context.args[0].strip()
    r = None
    if arg.isdigit():
        cache = (context.chat_data or {}).get(CACHE_RM_REC_IDS) or []
        n = int(arg)
        if 1 <= n <= len(cache):
            r = buscar_recomendacion_por_id(cache[n - 1])
    if r is None:
        r = buscar_recomendacion_por_id(arg)
    if not r:
        await update.message.reply_text("No encontrado.")
        return
    body = (
        f"ID: {r.id}\n"
        f"Tipo: {r.tipo}\n"
        f"Nombre: {r.nombre}\n"
        f"Notas: {r.notas or '(vacias)'}\n"
        f"Tags: {r.tags or '(ninguno)'}\n"
        f"Fecha: {formatear_fecha_ver(r.fecha_ingesta)}\n"
        f"Fuente: {r.fuente} @{r.telegram_user or ''}"
    )
    await _reply_texto_largo(update, body)


async def cmd_rmrec(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /rmrec <numero ...>")
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text("Solo numeros del listado.")
        return
    cache = (context.chat_data or {}).get(CACHE_RM_REC_IDS) or []
    ok = 0
    fuera: list[int] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        if eliminar_recomendacion_por_id(cache[n - 1]):
            ok += 1
    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_REC_IDS, None)
    msg = f"Recomendaciones eliminadas: {ok}."
    if fuera:
        msg += f" Fuera de rango: {sorted(set(fuera))}."
    await update.message.reply_text(msg)


async def cmd_listregistroshuevos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    lim = 40
    if context.args and context.args[0].strip().isdigit():
        lim = max(1, min(100, int(context.args[0].strip())))
    items = listar_registros_recientes(lim)
    if not items:
        await update.message.reply_text("No hay registros de huevos.")
        return
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_HUEVO_IDS] = [r.id for r in items]
    lineas = []
    for i, r in enumerate(items, 1):
        lineas.append(f"{i}. {r.fecha} | {r.cantidad} u. | {r.fuente}")
    await update.message.reply_text(
        f"Registros huevos ({len(items)}):\n\n" + "\n".join(lineas)
    )


async def cmd_verhuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /verhuevo <numero> (de /listregistroshuevos).")
        return
    arg = context.args[0].strip()
    r = None
    if arg.isdigit():
        cache = (context.chat_data or {}).get(CACHE_RM_HUEVO_IDS) or []
        n = int(arg)
        if 1 <= n <= len(cache):
            r = buscar_huevo_por_id(cache[n - 1])
    if r is None:
        r = buscar_huevo_por_id(arg)
    if not r:
        await update.message.reply_text("No encontrado.")
        return
    await update.message.reply_text(
        f"ID: {r.id}\nFecha: {r.fecha}\nCantidad: {r.cantidad}\n"
        f"Ingesta: {formatear_fecha_ver(r.fecha_ingesta)}\nFuente: {r.fuente}"
    )


async def cmd_rmhuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if not context.args:
        await update.message.reply_text("Uso: /rmhuevo <numero ...>")
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text("Solo numeros del listado.")
        return
    cache = (context.chat_data or {}).get(CACHE_RM_HUEVO_IDS) or []
    ok = 0
    fuera: list[int] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        if eliminar_huevo_por_id(cache[n - 1]):
            ok += 1
    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_HUEVO_IDS, None)
    msg = f"Registros huevos eliminados: {ok}."
    if fuera:
        msg += f" Fuera de rango: {sorted(set(fuera))}."
    await update.message.reply_text(msg)


CAMPOS_MOD_NOTA: list[tuple[str, str]] = [
    ("title", "Titulo"),
    ("content", "Contenido (texto de la nota)"),
]


def _texto_menu_mod_nota() -> str:
    lineas = ["Modificar nota Nextcloud. Campo (0 = salir):"]
    for i, (_k, lab) in enumerate(CAMPOS_MOD_NOTA, 1):
        lineas.append(f"{i}. {lab}")
    return "\n".join(lineas)


async def cmd_cancelarmodnota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    if context.chat_data is not None:
        context.chat_data.pop(WIZARD_MOD_NOTA_KEY, None)
    await update.message.reply_text("Edicion de nota cancelada.")


async def _iniciar_mod_nota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cred = _notas_credenciales(update)
    if not cred:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error())
        return
    if not context.args or not context.args[0].isdigit() or context.chat_data is None:
        await update.message.reply_text("Uso: /modnota <numero>\nEl de /listnotas.")
        return
    n = int(context.args[0].strip())
    cache = (context.chat_data or {}).get(CACHE_RM_NOTAS_IDS) or []
    if n < 1 or n > len(cache):
        await update.message.reply_text("Indice invalido. Ejecuta /listnotas.")
        return
    nid = int(cache[n - 1])
    usr = update.effective_user
    if not usr:
        return
    context.chat_data[WIZARD_MOD_NOTA_KEY] = {
        "user_id": usr.id,
        "note_id": nid,
        "fase": "menu",
    }
    await update.message.reply_text(
        _texto_menu_mod_nota() + "\n\n/cancelarmodnota para salir."
    )


async def _manejar_wizard_mod_nota(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if context.chat_data is None:
        return False
    w = context.chat_data.get(WIZARD_MOD_NOTA_KEY)
    if not w:
        return False
    user = update.effective_user
    if not user or w.get("user_id") != user.id:
        return False
    cred = _notas_credenciales(update)
    if not cred:
        context.chat_data.pop(WIZARD_MOD_NOTA_KEY, None)
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error())
        return True
    nu, pw = cred
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Envia texto o /cancelarmodnota.")
        return True
    nid = int(w["note_id"])
    fase = w.get("fase", "menu")

    if fase == "menu":
        if text == "0":
            context.chat_data.pop(WIZARD_MOD_NOTA_KEY, None)
            await update.message.reply_text("Listo.")
            return True
        if not text.isdigit():
            await update.message.reply_text("Numero o 0.")
            return True
        n = int(text)
        if n < 1 or n > len(CAMPOS_MOD_NOTA):
            await update.message.reply_text("Opcion invalida.")
            return True
        key, label = CAMPOS_MOD_NOTA[n - 1]
        w["fase"] = "valor"
        w["campo_key"] = key
        await update.message.reply_text(
            f"Nuevo valor: {label}\n/cancelarmodnota para abortar."
        )
        return True

    key = w.get("campo_key")
    if not key:
        w["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_nota())
        return True

    if _es_mantener_wizard_valor(text):
        w["fase"] = "menu"
        w.pop("campo_key", None)
        await update.message.reply_text(_texto_menu_mod_nota())
        return True

    if key == "title":
        out = notes_nextcloud.actualizar_nota(nu, pw, nid, titulo=text)
    else:
        out = notes_nextcloud.actualizar_nota(nu, pw, nid, contenido=text)
    if not out:
        await update.message.reply_text(
            "Error: " + (notes_nextcloud.obtener_ultimo_error() or "?")
        )
        return True
    w["fase"] = "menu"
    w.pop("campo_key", None)
    await update.message.reply_text("Actualizado.\n\n" + _texto_menu_mod_nota())
    return True


async def cmd_notas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    cred = _notas_credenciales(update)
    if not cred:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error())
        return
    nu, pw = cred
    resto = " ".join(context.args or []).strip()
    if not resto:
        await update.message.reply_text(
            "Uso: /notas <titulo> [| cuerpo opcional]\n"
            "O: /notas titulo | primer parrafo"
        )
        return
    titulo, _, body = resto.partition("|")
    titulo = titulo.strip() or "(sin titulo)"
    body = body.strip()
    created = notes_nextcloud.crear_nota(nu, pw, titulo, body)
    if not created:
        await update.message.reply_text(
            "No se pudo crear: " + (notes_nextcloud.obtener_ultimo_error() or "")
        )
        return
    await update.message.reply_text(
        f"Nota creada en Nextcloud.\nID: {created.get('id')}\nTitulo: {created.get('title')}"
    )


async def cmd_listnotas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    cred = _notas_credenciales(update)
    if not cred:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error())
        return
    nu, pw = cred
    notas = notes_nextcloud.listar_notas(nu, pw)
    if notas is None:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error() or "Error listando.")
        return
    if not notas:
        await update.message.reply_text("No hay notas (o carpeta vacia).")
        return
    def _mod_key(x: dict) -> int:
        try:
            return int(float(x.get("modified") or 0))
        except (TypeError, ValueError):
            return 0

    notas.sort(key=_mod_key, reverse=True)
    ids: list[int] = []
    lineas: list[str] = []
    idx = 0
    for n in notas[:80]:
        nid = n.get("id")
        if nid is None:
            continue
        try:
            nid_i = int(nid)
        except (TypeError, ValueError):
            continue
        idx += 1
        ids.append(nid_i)
        tit = str(n.get("title") or "(sin titulo)")[:55]
        lineas.append(f"{idx}. [{nid_i}] {tit}")
        if idx >= 60:
            break
    if context.chat_data is not None:
        context.chat_data[CACHE_RM_NOTAS_IDS] = ids
    await update.message.reply_text(
        f"Notas Nextcloud ({len(lineas)}):\n\n" + "\n".join(lineas)
    )


async def cmd_vernota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    cred = _notas_credenciales(update)
    if not cred:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error())
        return
    nu, pw = cred
    if not context.args:
        await update.message.reply_text("Uso: /vernota <numero>\nEl de /listnotas.")
        return
    arg = context.args[0].strip()
    nid = None
    if arg.isdigit():
        cache = (context.chat_data or {}).get(CACHE_RM_NOTAS_IDS) or []
        n = int(arg)
        if 1 <= n <= len(cache):
            nid = int(cache[n - 1])
    if nid is None:
        try:
            nid = int(arg)
        except ValueError:
            nid = None
    if nid is None:
        await update.message.reply_text("Indice o id invalido.")
        return
    note = notes_nextcloud.obtener_nota(nu, pw, nid)
    if not note:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error() or "No encontrada.")
        return
    body = f"ID: {note.get('id')}\nTitulo: {note.get('title')}\n\n{note.get('content') or ''}"
    await _reply_texto_largo(update, body)


async def cmd_modnota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _iniciar_mod_nota(update, context)


async def cmd_rmnota(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _esta_autorizado(update):
        await _rechazar_no_autorizado(update)
        return
    cred = _notas_credenciales(update)
    if not cred:
        await update.message.reply_text(notes_nextcloud.obtener_ultimo_error())
        return
    nu, pw = cred
    if not context.args:
        await update.message.reply_text("Uso: /rmnota <numero ...>\nIndices de /listnotas.")
        return
    enteros, otros = _parsear_tokens_rm(list(context.args))
    if otros:
        await update.message.reply_text("Solo numeros del listado.")
        return
    cache = (context.chat_data or {}).get(CACHE_RM_NOTAS_IDS) or []
    ok = 0
    fuera: list[int] = []
    for n in enteros:
        if n < 1 or n > len(cache):
            fuera.append(n)
            continue
        if notes_nextcloud.borrar_nota(nu, pw, int(cache[n - 1])):
            ok += 1
    if context.chat_data is not None:
        context.chat_data.pop(CACHE_RM_NOTAS_IDS, None)
    msg = f"Notas eliminadas: {ok}."
    if fuera:
        msg += f" Fuera de rango: {sorted(set(fuera))}."
    await update.message.reply_text(msg)


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
            "tipo: idea, memoria, tarea, evento, funcionalidad (o func), investiga, "
            "comprar, voluntarios, fabrica (o fab), diario\n"
            "Ejemplo: /mvpendiente 1 tarea \"Titulo\" 25-03-2026"
        )
        return
    id_o_n = args[0].strip()
    tipo_in = args[1].strip().lower()
    extras = args[2:]
    tipo = "funcionalidad" if tipo_in == "func" else tipo_in
    if tipo == "fab":
        tipo = "fabrica"
    if tipo == "compra":
        tipo = "comprar"
    if tipo == "voluntario":
        tipo = "voluntarios"
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
    elif tipo == "memoria":
        mem = _guardar_memoria(combo, fuente="telegram_mvpendiente")
        ok_fin = True
        await update.message.reply_text(f"Movido a memoria.\nResumen: {mem.resumen}")
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
    elif tipo == "voluntarios":
        if await _ejecutar_creacion_tarea_deck(
            update,
            combo,
            stack_name=DECK_STACK_VOLUNTARIOS,
            prefijo_exito="Tarea de voluntarios anotada",
        ):
            ok_fin = True
    elif tipo == "fabrica":
        msg_f = await update.message.reply_text("Creando fabricacion...")
        if await _crear_fabrica_desde_texto(
            update, combo, fuente="telegram_mvpendiente", msg_trabajo=msg_f
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
        cid = str(update.effective_chat.id) if update.effective_chat else ""
        inv = _nueva_investigacion_pendiente(combo, telegram_chat_id=cid)
        añadir_investigacion(inv)
        ok_fin = True
        await update.message.reply_text(
            f"Movido a investigacion encolada.\nID: {inv.id}\nConcepto: {inv.concepto}"
        )
    elif tipo == "diario":
        usr = update.effective_user
        etiqueta = (usr.username or str(usr.id)) if usr else ""
        cuerpo, fecha_dia = extraer_cuerpo_y_fecha_dia_para_el(combo)
        if not (cuerpo or "").strip():
            await update.message.reply_text("Texto del diario vacio.")
            return
        try:
            ent = diario_añadir_entrada(
                cuerpo.strip(),
                fuente="telegram_mvpendiente",
                telegram_user=etiqueta,
                fecha_dia=fecha_dia,
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

    part = url.rstrip("/").split("/")[-1]
    titulo_ini = (
        part.replace("-", " ").replace("_", " ").replace("%20", " ")[:120]
        if part
        else url[:120]
    )
    conv = Convocatoria(
        id=id_conv,
        url=url,
        titulo=titulo_ini or url[:120],
        descripcion="",
        plazo_fin="",
        requisitos="",
        estado="pendiente_investigacion",
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
            f"(una linea; '-' vacio; . o = mantener)\n/cancelarmodfactura para abortar."
        )
        return True

    key = wizard.get("campo_key")
    if not key:
        wizard["fase"] = "menu"
        await update.message.reply_text(_texto_menu_mod_factura(fid))
        return True

    if _es_mantener_wizard_valor(text):
        wizard["fase"] = "menu"
        wizard.pop("campo_key", None)
        await update.message.reply_text(
            "Sin cambios en ese campo.\n\n" + _texto_menu_mod_factura(fid)
        )
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
    if await _manejar_wizard_mod_tarea(update, context):
        return
    if await _manejar_wizard_mod_evento(update, context):
        return
    if await _manejar_wizard_mod_tiempo(update, context):
        return
    if await _manejar_wizard_mod_nota(update, context):
        return
    if await _manejar_wizard_mod_lista(update, context):
        return
    if await _manejar_wizard_mod_fabrica(update, context):
        return
    if await _manejar_wizard_mod_proyecto(update, context):
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

        elif accion == "memoria":
            if not contenido:
                await estado.edit_text("La memoria no puede estar vacia. Di: memoria <texto>")
                return
            mem = _guardar_memoria(contenido, fuente="telegram_audio")
            try:
                md_path = _ruta_archivo_memoria(mem.ruta)
                stem = md_path.stem
                dest_audio = md_path.parent / f"{stem}{sufijo}"
                if dest_audio.exists():
                    dest_audio = md_path.parent / f"{stem}_audio{sufijo}"
                shutil.copy2(ruta_tmp, dest_audio)
            except OSError:
                pass
            await estado.edit_text(
                f"Memoria guardada desde audio.\nResumen: {mem.resumen}"
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
                    "La tarea no puede estar vacia. Di: tarea <titulo> [para|para el fecha o dia]"
                )
                return
            if fecha_t:
                try:
                    datetime.strptime(fecha_t, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_t}\n"
                        "Tras 'para'/'para el': DD-MM-AAAA, DD-MM, DD, YYYY-MM-DD, hoy/mañana o día de la semana"
                    )
                    return
            ok, _, _, _ = crear_tarea_deck(
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
                    f'La compra no puede estar vacia. Di: comprar <titulo> [para|para el fecha]\n'
                    f'(columna Deck "{DECK_STACK_COMPRAR}")'
                )
                return
            if fecha_c:
                try:
                    datetime.strptime(fecha_c, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_c}\n"
                        "Tras 'para'/'para el': DD-MM-AAAA, DD-MM, DD, YYYY-MM-DD, hoy/mañana o día de la semana"
                    )
                    return
            ok, _, _, _ = crear_tarea_deck(
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

        elif accion == "voluntarios":
            titulo_v, fecha_v, descripcion_v = _parsear_tarea_audio_payload(contenido)
            if not titulo_v:
                await estado.edit_text(
                    f'Indica la tarea tras "voluntarios", ej. voluntarios preparar merienda.\n'
                    f'(columna Deck "{DECK_STACK_VOLUNTARIOS}")'
                )
                return
            if fecha_v:
                try:
                    datetime.strptime(fecha_v, "%Y-%m-%d")
                except ValueError:
                    await estado.edit_text(
                        f"Fecha invalida en audio: {fecha_v}\n"
                        "Tras 'para'/'para el': DD-MM-AAAA, DD-MM, DD, YYYY-MM-DD, hoy/mañana o día de la semana"
                    )
                    return
            ok, _, _, _ = crear_tarea_deck(
                titulo_v,
                descripcion=descripcion_v,
                fecha_due=fecha_v,
                stack_name=DECK_STACK_VOLUNTARIOS,
                assigned_user_uids=_deck_uids_para_update(update),
            )
            if ok:
                lineas = [
                    f'Tarea de voluntarios en Deck ({config.DECK_BOARD_NAME}) '
                    f"[{DECK_STACK_VOLUNTARIOS}] desde audio.",
                    f"Titulo: {titulo_v}",
                ]
                if fecha_v:
                    lineas.append(f"Fecha limite: {fecha_v}")
                aviso_asg = obtener_ultimo_aviso_asignacion_deck()
                if aviso_asg:
                    lineas.append(aviso_asg)
                await estado.edit_text("\n".join(lineas))
            else:
                deck_error = obtener_ultimo_error_deck()
                await estado.edit_text(
                    "No se pudo crear la tarjeta de voluntarios en Deck desde audio.\n"
                    f"{deck_error or 'sin detalle'}"
                )

        elif accion in ("fabrica", "fab"):
            if not contenido.strip():
                await estado.edit_text(
                    "Di fabrica o fab seguido del encargo (medidas, laser o 3d y fecha opcionales)."
                )
                return
            await _crear_fabrica_desde_texto(
                update,
                contenido.strip(),
                fuente="telegram_audio",
                msg_trabajo=estado,
            )
            return

        elif accion == "evento":
            nombre_ev, fecha_ev, hora_ev, dur_ev = _parsear_evento_audio_payload(contenido)
            if not fecha_ev:
                await estado.edit_text(
                    "El evento necesita fecha. Por voz: evento <nombre> para|para el 20-03 [15:30], "
                    "para mañana o para el viernes.\n"
                    "Sin separador: nombre y fecha en una frase (ej. reunion 20-03 15:30)."
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
            dur_kw = dur_ev if hora_ev else None
            ok = crear_evento(nombre_ev, fecha_iso_ev, hora=hora_ev, duracion=dur_kw)
            if ok:
                partes = [
                    f"Evento creado desde audio: {nombre_ev}",
                    f"Fecha: {fecha_ev}",
                ]
                if hora_ev:
                    if dur_ev:
                        partes.append(
                            f"Hora inicio: {hora_ev} (duracion {_formatear_duracion_usuario(dur_ev)})"
                        )
                    else:
                        partes.append(f"Hora inicio: {hora_ev} (duracion 1 h)")
                elif dur_ev:
                    partes.append(
                        "Nota: sin hora, evento de dia completo; duracion no aplicada."
                    )
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
            cid = str(update.effective_chat.id) if update.effective_chat else ""
            inv = _nueva_investigacion_pendiente(
                contenido.strip(), telegram_chat_id=cid
            )
            añadir_investigacion(inv)
            await estado.edit_text(
                f"Investigacion encolada desde audio (pendiente).\n"
                f"ID: {inv.id}\n"
                f"Concepto: {inv.concepto}\n"
                f"Archivo .md: {inv.archivo}"
            )

        elif accion == "huevos":
            cant_h = _primer_entero_positivo(contenido)
            if cant_h is None:
                await estado.edit_text(
                    "Di huevos y un numero entero positivo, ej. huevos 12 o huevos 8 para ayer"
                )
                return
            fecha_h = fecha_hoy_relativas().isoformat()
            resto_h = contenido.strip()
            if resto_h:
                num_match = re.search(r"\b\d+\b", resto_h)
                if num_match:
                    resto_h = (resto_h[num_match.end() :] or "").strip()
                if resto_h:
                    if not resto_h.lower().startswith("para "):
                        resto_h = f"para {resto_h}"
                    _, fecha_parseada = extraer_cuerpo_y_fecha_dia_para_el(f"x {resto_h}")
                    if fecha_parseada:
                        fecha_h = fecha_parseada
            añadir_huevo(cant_h, fecha_h, fuente="telegram_audio")
            total_h = total_cantidad_en_fecha(fecha_h)
            await estado.edit_text(
                f"Huevos registrados desde audio.\n"
                f"Fecha: {fecha_h}\n"
                f"Esta vez: {cant_h}\n"
                f"Total del dia: {total_h}"
            )

        elif accion == "diario":
            if not contenido.strip():
                await estado.edit_text("Di diario seguido del texto (o nota) que quieras guardar.")
                return
            usr = update.effective_user
            etiqueta_u = (usr.username or str(usr.id)) if usr else ""
            cuerpo_d, fecha_d = extraer_cuerpo_y_fecha_dia_para_el(contenido.strip())
            if not cuerpo_d.strip():
                await estado.edit_text("El texto del diario no puede estar vacio.")
                return
            try:
                ent = diario_añadir_entrada(
                    cuerpo_d.strip(),
                    fuente="telegram_audio",
                    telegram_user=etiqueta_u,
                    fecha_dia=fecha_d,
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
                f"Tipos: idea, memoria, tarea, evento, funcionalidad, func, investiga, comprar, fabrica, fab, diario"
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
    app.add_handler(CommandHandler("descarga", cmd_descarga))
    app.add_handler(CommandHandler("enchufeestado", cmd_enchufeestado))
    app.add_handler(CommandHandler("enchufeen", cmd_enchufeen))
    app.add_handler(CommandHandler("enchufeapagar", cmd_enchufeapagar))
    app.add_handler(CommandHandler("impresoraestado", cmd_impresoraestado))
    app.add_handler(CommandHandler("impresoraapagar", cmd_impresoraapagar))
    app.add_handler(CommandHandler("convo", cmd_convo))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("listurl", cmd_listurl))
    app.add_handler(CommandHandler("verurl", cmd_verurl))
    app.add_handler(CommandHandler("rmurl", cmd_rmurl))
    app.add_handler(CommandHandler("idea", cmd_idea))
    app.add_handler(CommandHandler("listideas", cmd_listideas))
    app.add_handler(CommandHandler("veridea", cmd_veridea))
    app.add_handler(CommandHandler("rmidea", cmd_rmidea))
    app.add_handler(CommandHandler("memoria", cmd_memoria))
    app.add_handler(CommandHandler("listmemorias", cmd_listmemorias))
    app.add_handler(CommandHandler("vermemoria", cmd_vermemoria))
    app.add_handler(CommandHandler("rmmemoria", cmd_rmmemoria))
    app.add_handler(CommandHandler("proyecto", cmd_proyecto))
    app.add_handler(CommandHandler("cancelarproyecto", cmd_cancelarproyecto))
    app.add_handler(CommandHandler("listproyectos", cmd_listproyectos))
    app.add_handler(CommandHandler("listproyecto", cmd_listproyectos))
    app.add_handler(CommandHandler("verproyecto", cmd_verproyecto))
    app.add_handler(CommandHandler("rmproyecto", cmd_rmproyecto))
    app.add_handler(CommandHandler("modproyecto", cmd_modproyecto))
    app.add_handler(CommandHandler("cancelarmodproyecto", cmd_cancelarmodproyecto))
    app.add_handler(CommandHandler("modconvo", cmd_modconvo))
    app.add_handler(CommandHandler("modidea", cmd_modidea))
    app.add_handler(CommandHandler("modmemoria", cmd_modmemoria))
    app.add_handler(CommandHandler("modfunc", cmd_modfunc))
    app.add_handler(CommandHandler("modinv", cmd_modinv))
    app.add_handler(CommandHandler("modenlace", cmd_modenlace))
    app.add_handler(CommandHandler("modpendiente", cmd_modpendiente))
    app.add_handler(CommandHandler("modrec", cmd_modrec))
    app.add_handler(CommandHandler("moddiario", cmd_moddiario))
    app.add_handler(CommandHandler("modhuevo", cmd_modhuevo))
    app.add_handler(CommandHandler("cancelarmodlista", cmd_cancelarmodlista))
    app.add_handler(CommandHandler("modtarea", cmd_modtarea))
    app.add_handler(CommandHandler("cancelarmodtarea", cmd_cancelarmodtarea))
    app.add_handler(CommandHandler("modevento", cmd_modevento))
    app.add_handler(CommandHandler("cancelarmodevento", cmd_cancelarmodevento))
    app.add_handler(CommandHandler("cancelarmodtiempo", cmd_cancelarmodtiempo))
    app.add_handler(CommandHandler("notas", cmd_notas))
    app.add_handler(CommandHandler("listnotas", cmd_listnotas))
    app.add_handler(CommandHandler("vernota", cmd_vernota))
    app.add_handler(CommandHandler("modnota", cmd_modnota))
    app.add_handler(CommandHandler("rmnota", cmd_rmnota))
    app.add_handler(CommandHandler("cancelarmodnota", cmd_cancelarmodnota))
    app.add_handler(CommandHandler("rec", cmd_rec))
    app.add_handler(CommandHandler("recomendacion", cmd_rec))
    app.add_handler(CommandHandler("listrecomendaciones", cmd_listrecomendaciones))
    app.add_handler(CommandHandler("verrec", cmd_verrec))
    app.add_handler(CommandHandler("rmrec", cmd_rmrec))
    app.add_handler(CommandHandler("listdiario", cmd_listdiario))
    app.add_handler(CommandHandler("verdiario", cmd_verdiario))
    app.add_handler(CommandHandler("rmdiario", cmd_rmdiario))
    app.add_handler(CommandHandler("listregistroshuevos", cmd_listregistroshuevos))
    app.add_handler(CommandHandler("verhuevo", cmd_verhuevo))
    app.add_handler(CommandHandler("rmhuevo", cmd_rmhuevo))
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
    app.add_handler(CommandHandler("compra", cmd_comprar))
    app.add_handler(CommandHandler("voluntarios", cmd_voluntarios))
    app.add_handler(CommandHandler("voluntario", cmd_voluntarios))
    app.add_handler(CommandHandler("fabrica", cmd_fabrica))
    app.add_handler(CommandHandler("fab", cmd_fab))
    app.add_handler(CommandHandler("listfab", cmd_listfab))
    app.add_handler(CommandHandler("verfab", cmd_verfab))
    app.add_handler(CommandHandler("modfab", cmd_modfab))
    app.add_handler(CommandHandler("rmfab", cmd_rmfab))
    app.add_handler(CommandHandler("cancelarmodfab", cmd_cancelarmodfab))
    app.add_handler(CommandHandler("evento", cmd_evento))
    app.add_handler(CommandHandler("listeventos", cmd_listeventos))
    app.add_handler(CommandHandler("informame", cmd_informame))
    app.add_handler(CommandHandler("info", cmd_info))
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
    # Alias: /ls* = /list*, /v* = /ver*, /rm* abreviado = mismo handler que /rm… largo
    for _alias, _cmd in (
        ("dl", cmd_descarga),
        ("lsconvo", cmd_listar),
        ("lscv", cmd_listar),
        ("vconvo", cmd_verconvo),
        ("vcv", cmd_verconvo),
        ("rmcv", cmd_rmconvo),
        ("lsurl", cmd_listurl),
        ("vurl", cmd_verurl),
        ("rmu", cmd_rmurl),
        ("lsideas", cmd_listideas),
        ("lsid", cmd_listideas),
        ("videa", cmd_veridea),
        ("vid", cmd_veridea),
        ("rmid", cmd_rmidea),
        ("rmideas", cmd_rmidea),
        ("lsmemorias", cmd_listmemorias),
        ("lsmm", cmd_listmemorias),
        ("vmm", cmd_vermemoria),
        ("rmm", cmd_rmmemoria),
        ("rmmemorias", cmd_rmmemoria),
        ("proy", cmd_proyecto),
        ("py", cmd_proyecto),
        ("lsproyectos", cmd_listproyectos),
        ("lsproy", cmd_listproyectos),
        ("lspy", cmd_listproyectos),
        ("vproyecto", cmd_verproyecto),
        ("vproy", cmd_verproyecto),
        ("vpy", cmd_verproyecto),
        ("rmproy", cmd_rmproyecto),
        ("rmpy", cmd_rmproyecto),
        ("rmproyectos", cmd_rmproyecto),
        ("modproy", cmd_modproyecto),
        ("modpy", cmd_modproyecto),
        ("lstm", cmd_listtiempo),
        ("vtm", cmd_vertiempo),
        ("lsinvestigaciones", cmd_listinvestigaciones),
        ("lsinv", cmd_listinvestigaciones),
        ("vinvestigacion", cmd_verinvestigacion),
        ("vinv", cmd_verinvestigacion),
        ("rminv", cmd_rminvestigacion),
        ("rminvestigaciones", cmd_rminvestigacion),
        ("lsfunc", cmd_listfunc),
        ("lsfn", cmd_listfunc),
        ("fn", cmd_func),
        ("vfunc", cmd_verfunc),
        ("vfn", cmd_verfunc),
        ("rmfn", cmd_rmfunc),
        ("modfn", cmd_modfunc),
        ("rmfuncionalidades", cmd_rmfunc),
        ("lsfab", cmd_listfab),
        ("vfab", cmd_verfab),
        ("rmfb", cmd_rmfab),
        ("lseventos", cmd_listeventos),
        ("lsev", cmd_listeventos),
        ("vevento", cmd_verevento),
        ("vev", cmd_verevento),
        ("rmev", cmd_rmevento),
        ("rmeventos", cmd_rmevento),
        ("modev", cmd_modevento),
        ("msev", cmd_modevento),
        ("lstareas", cmd_listtareas),
        ("lst", cmd_listtareas),
        ("lstr", cmd_listtareas),
        ("lscomprar", cmd_listtareas),
        ("tr", cmd_tarea),
        ("vtarea", cmd_vertarea),
        ("vt", cmd_vertarea),
        ("vtr", cmd_vertarea),
        ("rmt", cmd_rmtarea),
        ("rmtareas", cmd_rmtarea),
        ("rmtr", cmd_rmtarea),
        ("mtr", cmd_modtarea),
        ("lsrec", cmd_listrecomendaciones),
        ("vrec", cmd_verrec),
        ("modrec", cmd_modrec),
        ("lsdiario", cmd_listdiario),
        ("vdiario", cmd_verdiario),
        ("lshuevos", cmd_listhuevos),
        ("lshv", cmd_listhuevos),
        ("lshue", cmd_listregistroshuevos),
        ("vhuevo", cmd_verhuevo),
        ("vhv", cmd_verhuevo),
        ("nt", cmd_notas),
        ("lsnt", cmd_listnotas),
        ("vnt", cmd_vernota),
        ("modnt", cmd_modnota),
        ("rmnt", cmd_rmnota),
        ("lspendientes", cmd_listpendientes),
        ("lspen", cmd_listpendientes),
        ("vpendiente", cmd_verpendiente),
        ("vpen", cmd_verpendiente),
        ("rmpen", cmd_rmpendientes),
        ("rmspendientes", cmd_rmpendientes),
        ("fct", cmd_factura),
        ("vfct", cmd_verfactura),
        ("rmfct", cmd_rmfactura),
        ("rmcontabilidad", cmd_rmfactura),
        ("lscontabilidad", cmd_listcontabilidad),
        ("lsfct", cmd_listcontabilidad),
    ):
        app.add_handler(CommandHandler(_alias, _cmd))
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
