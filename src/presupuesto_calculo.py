"""
Cálculo de presupuestos: costes, geocodificación, markdown y alta de proyecto.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import config
from src.db_ideas import Idea, buscar_por_id as buscar_idea_por_id
from src.db_presupuestos import Presupuesto, actualizar_presupuesto
from src.db_presupuestos_ideas import listar_ideas_de_presupuesto
from src.db_proyectos import (
    Proyecto,
    actualizar_proyecto,
    añadir_proyecto,
    buscar_por_id as buscar_proyecto_por_id,
    leer_proyectos,
)
from src.fecha_display import fecha_hoy_relativas
from src.fechas_proyecto import formatear_fecha
from src.slug_archivo_md import elegir_path_md_unico, texto_a_slug_palabras

MODO_NINGUNO = "ninguno"
MODO_DIARIO = "ida_vuelta_diario"
MODO_UNICO = "ida_vuelta_unico"
MODO_ALOJAMIENTO = "alojamiento"

_ALIAS_MODO: dict[str, str] = {
    "ninguno": MODO_NINGUNO,
    "n": MODO_NINGUNO,
    "no": MODO_NINGUNO,
    "diario": MODO_DIARIO,
    "ida_vuelta_diario": MODO_DIARIO,
    "ida-vuelta-diario": MODO_DIARIO,
    "unico": MODO_UNICO,
    "único": MODO_UNICO,
    "ida_vuelta_unico": MODO_UNICO,
    "ida-vuelta-unico": MODO_UNICO,
    "alojamiento": MODO_ALOJAMIENTO,
    "hotel": MODO_ALOJAMIENTO,
}

_ETIQUETA_MODO = {
    MODO_NINGUNO: "sin desplazamiento",
    MODO_DIARIO: "ida y vuelta diaria",
    MODO_UNICO: "ida y vuelta unica",
    MODO_ALOJAMIENTO: "alojamiento (ida y vuelta unica)",
}

_NOMINATIM_UA = "ConvocAUTOrias/0.29 (https://molinolab.org)"


@dataclass
class ResultadoCalculo:
    coste_jornadas: float
    coste_desplazamiento: float
    coste_alojamiento: float
    total: float
    km_ida: float
    viajes: int


def parsear_float(s: str, default: float = 0.0) -> float:
    t = (
        (s or "")
        .strip()
        .replace("€", "")
        .replace("EUR", "")
        .replace("eur", "")
        .replace(",", ".")
        .strip()
    )
    if not t:
        return default
    try:
        return float(t)
    except ValueError:
        return default


def parsear_entero(s: str, default: int = 0) -> int:
    t = (s or "").strip()
    if not t:
        return default
    try:
        return int(float(t.replace(",", ".")))
    except ValueError:
        return default


def formatear_numero(n: float) -> str:
    if abs(n - round(n)) < 0.005:
        return str(int(round(n)))
    return f"{n:.2f}"


def formatear_euros(n: float) -> str:
    return f"{formatear_numero(n)} EUR"


def normalizar_titulo(titulo: str) -> str:
    return " ".join((titulo or "").casefold().split())


def resolver_modo(texto: str) -> str | None:
    t = (texto or "").strip().casefold()
    return _ALIAS_MODO.get(t)


def etiqueta_modo(modo: str) -> str:
    return _ETIQUETA_MODO.get(modo, modo or MODO_NINGUNO)


def calcular_costes(
    jornadas: float,
    precio_dia: float,
    modo: str,
    km_ida: float,
    noches: float = 0.0,
    precio_noche: float = 0.0,
    coste_km: float | None = None,
    coste_alojamiento_fijo: float | None = None,
) -> ResultadoCalculo:
    """
    Gasolina a coste_km €/km.
    diario: km_ida * 2 * jornadas
    unico / alojamiento: km_ida * 2
    alojamiento: + noches * precio_noche (o coste_alojamiento_fijo si se pasa)
    """
    euro_km = config.PRESU_COSTE_KM if coste_km is None else coste_km
    jor = max(0.0, float(jornadas or 0))
    p_dia = max(0.0, float(precio_dia or 0))
    km = max(0.0, float(km_ida or 0))
    modo_n = modo if modo in _ETIQUETA_MODO else MODO_NINGUNO

    if modo_n == MODO_DIARIO:
        viajes = max(0, int(round(jor)))
    elif modo_n in (MODO_UNICO, MODO_ALOJAMIENTO):
        viajes = 1 if km > 0 else 0
    else:
        viajes = 0

    km_totales = km * 2 * viajes if modo_n != MODO_NINGUNO else 0.0
    coste_desp = round(km_totales * euro_km, 2)
    if coste_alojamiento_fijo is not None:
        coste_alo = max(0.0, round(float(coste_alojamiento_fijo), 2))
    else:
        coste_alo = round(max(0.0, float(noches or 0)) * max(0.0, float(precio_noche or 0)), 2)
    if modo_n != MODO_ALOJAMIENTO:
        coste_alo = 0.0

    coste_jor = round(jor * p_dia, 2)
    total = round(coste_jor + coste_desp + coste_alo, 2)
    return ResultadoCalculo(
        coste_jornadas=coste_jor,
        coste_desplazamiento=coste_desp,
        coste_alojamiento=coste_alo,
        total=total,
        km_ida=km,
        viajes=viajes,
    )


def geocodificar(lugar: str) -> tuple[float, float] | None:
    """Nominatim: (lat, lon) o None."""
    q = (lugar or "").strip()
    if not q:
        return None
    try:
        import requests
    except ImportError:
        return None
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 1},
            headers={"User-Agent": _NOMINATIM_UA, "Accept-Language": "es"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


def distancia_km_osrm(
    origen: tuple[float, float], destino: tuple[float, float]
) -> float | None:
    """OSRM driving distance in km. Coords are (lat, lon)."""
    try:
        import requests
    except ImportError:
        return None
    lat1, lon1 = origen
    lat2, lon2 = destino
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}"
    )
    try:
        r = requests.get(url, params={"overview": "false"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        metros = float(routes[0].get("distance") or 0)
        if metros <= 0:
            return None
        return round(metros / 1000.0, 1)
    except Exception:
        return None


def km_desde_origen(lugar: str) -> float | None:
    orig = geocodificar(config.PRESU_ORIGEN_DESPLAZAMIENTO)
    dest = geocodificar(lugar)
    if not orig or not dest:
        return None
    return distancia_km_osrm(orig, dest)


def buscar_proyecto_por_titulo(titulo: str) -> Proyecto | None:
    n = normalizar_titulo(titulo)
    if not n:
        return None
    for p in leer_proyectos():
        if normalizar_titulo(p.titulo) == n:
            return p
    return None


def _generar_id_proyecto(titulo: str) -> str:
    base = f"{datetime.now().isoformat()}::proyecto::{titulo[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def generar_id_presupuesto(titulo: str) -> str:
    base = f"{datetime.now().isoformat()}::presupuesto::{titulo[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ruta_relativa(path: Path) -> str:
    try:
        return path.relative_to(config.DIR_PROYECTO).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def asegurar_proyecto(titulo: str, descripcion: str = "") -> tuple[Proyecto, bool]:
    """
    Devuelve (proyecto, creado). Si no existe un proyecto con el mismo titulo
    (normalizado), crea uno minimo en estado presupuestado.
    """
    tit = " ".join((titulo or "").split()) or "(sin titulo)"
    existente = buscar_proyecto_por_titulo(tit)
    if existente:
        return existente, False

    pid = _generar_id_proyecto(tit)
    config.CARPETA_PROYECTOS.mkdir(parents=True, exist_ok=True)
    slug_p = texto_a_slug_palabras(tit, 5)
    ruta_abs = elegir_path_md_unico(config.CARPETA_PROYECTOS, slug_p, pid)
    d0 = fecha_hoy_relativas()
    fecha_creacion = formatear_fecha(datetime(d0.year, d0.month, d0.day))
    cuerpo = f"# {tit}\n\n**Contacto:**  <>\n\n"
    if descripcion.strip():
        cuerpo += descripcion.strip() + "\n"
    ruta_abs.write_text(cuerpo, encoding="utf-8")
    p = Proyecto(
        id=pid,
        titulo=tit,
        fecha_creacion=fecha_creacion,
        persona_contacto="",
        email_contacto="",
        presupuesto="",
        tiempo_total="0",
        fecha_fin="",
        estado="presupuestado",
        tags="",
        ruta=_ruta_relativa(ruta_abs),
        fuente="telegram_presu",
    )
    añadir_proyecto(p)
    return p, True


def actualizar_proyecto_desde_presupuesto(presu: Presupuesto) -> None:
    p = buscar_proyecto_por_id(presu.id_proyecto)
    if not p:
        return
    total = parsear_float(presu.total_aproximado, 0.0)
    nuevo_estado = p.estado
    if (p.estado or "").strip() == "idea":
        nuevo_estado = "presupuestado"
    p1 = replace(
        p,
        presupuesto=formatear_euros(total),
        estado=nuevo_estado,
    )
    actualizar_proyecto(p1)


def generar_markdown(presu: Presupuesto, ideas: list[Idea] | None = None) -> str:
    jor = parsear_float(presu.jornadas, 0.0)
    p_dia = parsear_float(presu.precio_dia, config.PRESU_PRECIO_DIA_DEFAULT)
    km = parsear_float(presu.km_ida, 0.0)
    modo = presu.modo_desplazamiento or MODO_NINGUNO
    calc = calcular_costes(
        jornadas=jor,
        precio_dia=p_dia,
        modo=modo,
        km_ida=km,
        coste_alojamiento_fijo=parsear_float(presu.coste_alojamiento, 0.0),
    )
    origen = config.PRESU_ORIGEN_DESPLAZAMIENTO
    lineas = [
        f"# Presupuesto: {presu.titulo or '(sin titulo)'}",
        "",
        f"**Proyecto:** {presu.titulo or '(sin titulo)'}",
        f"**Lugar:** {presu.lugar.strip() or '(no indicado)'}",
        f"**Jornadas:** {formatear_numero(jor)} x {formatear_euros(p_dia)}/dia = **{formatear_euros(calc.coste_jornadas)}**",
        "",
    ]
    if (presu.descripcion or "").strip():
        lineas.extend(["## Descripcion", "", presu.descripcion.strip(), ""])
    if (presu.necesidades_tecnicas or "").strip():
        lineas.extend(
            ["## Necesidades tecnicas", "", presu.necesidades_tecnicas.strip(), ""]
        )

    lineas.append("## Desplazamiento")
    if modo == MODO_NINGUNO or km <= 0:
        lineas.append("- Sin desplazamiento (o 0 km).")
        lineas.append("- Coste gasolina: **0 EUR**")
    else:
        lineas.append(f"- Origen: {origen}")
        lineas.append(f"- Destino: {presu.lugar.strip() or '(no indicado)'}")
        lineas.append(f"- Distancia ida: {formatear_numero(km)} km")
        lineas.append(f"- Modo: {etiqueta_modo(modo)}")
        lineas.append(
            f"- Viajes (ida y vuelta): {calc.viajes} "
            f"({formatear_numero(km)} x 2 x {calc.viajes} x {formatear_numero(config.PRESU_COSTE_KM)} EUR/km)"
        )
        lineas.append(f"- Coste gasolina: **{formatear_euros(calc.coste_desplazamiento)}**")
    lineas.append("")

    noches = parsear_entero(presu.noches_alojamiento, 0)
    if modo == MODO_ALOJAMIENTO:
        lineas.append("## Alojamiento")
        lineas.append(f"- Noches: {noches}")
        lineas.append(f"- Coste: **{formatear_euros(calc.coste_alojamiento)}**")
        lineas.append("")

    lineas.append(f"## Total aproximado: **{formatear_euros(calc.total)}**")
    lineas.append("")

    ideas = ideas if ideas is not None else _ideas_de_presupuesto(presu.id)
    if ideas:
        lineas.append("## Ideas vinculadas")
        for idea in ideas:
            res = (idea.resumen or "").strip() or "(sin resumen)"
            lineas.append(f"- {res} (`{idea.id}`)")
        lineas.append("")

    return "\n".join(lineas)


def _ideas_de_presupuesto(id_presupuesto: str) -> list[Idea]:
    out: list[Idea] = []
    for iid in listar_ideas_de_presupuesto(id_presupuesto):
        idea = buscar_idea_por_id(iid)
        if idea:
            out.append(idea)
    return out


def escribir_markdown(presu: Presupuesto, ideas: list[Idea] | None = None) -> Path:
    config.CARPETA_PRESUPUESTOS.mkdir(parents=True, exist_ok=True)
    contenido = generar_markdown(presu, ideas)
    if (presu.ruta or "").strip():
        path = Path(presu.ruta)
        if not path.is_absolute():
            path = (config.DIR_PROYECTO / path).resolve()
    else:
        slug = texto_a_slug_palabras(presu.titulo or "proyecto", 5)
        path = elegir_path_md_unico(
            config.CARPETA_PRESUPUESTOS, f"presupuesto_{slug}", presu.id
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contenido, encoding="utf-8")
    return path


def aplicar_calculo_a_presupuesto(
    presu: Presupuesto,
    precio_noche: float | None = None,
) -> Presupuesto:
    jor = parsear_float(presu.jornadas, 0.0)
    p_dia = parsear_float(presu.precio_dia, config.PRESU_PRECIO_DIA_DEFAULT)
    km = parsear_float(presu.km_ida, 0.0)
    modo = presu.modo_desplazamiento or MODO_NINGUNO
    noches = parsear_float(presu.noches_alojamiento, 0.0)
    if precio_noche is None:
        calc = calcular_costes(
            jornadas=jor,
            precio_dia=p_dia,
            modo=modo,
            km_ida=km,
            coste_alojamiento_fijo=parsear_float(presu.coste_alojamiento, 0.0),
        )
    else:
        calc = calcular_costes(
            jornadas=jor,
            precio_dia=p_dia,
            modo=modo,
            km_ida=km,
            noches=noches,
            precio_noche=precio_noche,
        )
    return replace(
        presu,
        jornadas=formatear_numero(jor),
        precio_dia=formatear_numero(p_dia),
        km_ida=formatear_numero(km) if km else "",
        coste_desplazamiento=formatear_numero(calc.coste_desplazamiento),
        noches_alojamiento=formatear_numero(noches) if modo == MODO_ALOJAMIENTO else "0",
        coste_alojamiento=formatear_numero(calc.coste_alojamiento),
        total_aproximado=formatear_numero(calc.total),
        modo_desplazamiento=modo,
    )


def regenerar_tras_edicion(presu: Presupuesto) -> Presupuesto:
    """Recalcula importes, reescribe .md y actualiza el proyecto vinculado."""
    p1 = aplicar_calculo_a_presupuesto(presu)
    path = escribir_markdown(p1)
    p1 = replace(p1, ruta=_ruta_relativa(path))
    actualizar_presupuesto(p1)
    actualizar_proyecto_desde_presupuesto(p1)
    return p1


def persistir_presupuesto_nuevo(
    data: dict,
    ids_ideas: list[str],
) -> tuple[Presupuesto, Proyecto, bool]:
    """
    Crea proyecto si no existe, persiste presupuesto + markdown.
    Lanza ValueError si ya hay presupuesto para ese proyecto.
    """
    from src.db_presupuestos import añadir_presupuesto, buscar_por_id_proyecto
    from src.db_presupuestos_ideas import reemplazar_ideas

    tit = " ".join((data.get("titulo") or "").split()) or "(sin titulo)"
    proyecto, creado = asegurar_proyecto(tit, data.get("descripcion") or "")
    ya = buscar_por_id_proyecto(proyecto.id)
    if ya:
        raise ValueError(
            f"Ya existe un presupuesto para este proyecto (id {ya.id}). "
            "Usa /listpresu y /modpresu <n>."
        )

    pid = generar_id_presupuesto(tit)
    modo = data.get("modo_desplazamiento") or MODO_NINGUNO
    presu = Presupuesto(
        id=pid,
        id_proyecto=proyecto.id,
        titulo=tit,
        descripcion=(data.get("descripcion") or "").strip(),
        lugar=(data.get("lugar") or "").strip(),
        necesidades_tecnicas=(data.get("necesidades_tecnicas") or "").strip(),
        jornadas=str(data.get("jornadas") or "0"),
        precio_dia=str(data.get("precio_dia") or config.PRESU_PRECIO_DIA_DEFAULT),
        modo_desplazamiento=modo,
        km_ida=str(data.get("km_ida") or ""),
        coste_desplazamiento="0",
        noches_alojamiento=str(data.get("noches_alojamiento") or "0"),
        coste_alojamiento="0",
        total_aproximado="0",
        ruta="",
        fecha_creacion=datetime.now().isoformat(),
        fuente="telegram_presu",
    )
    precio_noche = parsear_float(str(data.get("precio_noche") or "0"), 0.0)
    presu = aplicar_calculo_a_presupuesto(presu, precio_noche=precio_noche)
    path = escribir_markdown(presu, ideas=None)
    presu = replace(presu, ruta=_ruta_relativa(path))
    añadir_presupuesto(presu)
    if ids_ideas:
        reemplazar_ideas(presu.id, ids_ideas)
        path = escribir_markdown(presu)
        presu = replace(presu, ruta=_ruta_relativa(path))
        actualizar_presupuesto(presu)
    actualizar_proyecto_desde_presupuesto(presu)
    return presu, proyecto, creado


def intentar_sync_notes() -> tuple[bool, str]:
    try:
        from src.notes_sync_markdown import sincronizar_markdown_a_nextcloud_notes

        res = sincronizar_markdown_a_nextcloud_notes()
        if res.get("error"):
            return False, str(res["error"])
        if int(res.get("errores") or 0) > 0 and int(res.get("creadas") or 0) == 0:
            return False, f"Sync con {res.get('errores')} error(es)."
        return True, (
            f"Notas NC: creadas {res.get('creadas', 0)}, "
            f"actualizadas {res.get('actualizadas', 0)}."
        )
    except Exception as exc:
        return False, str(exc)[:200]
