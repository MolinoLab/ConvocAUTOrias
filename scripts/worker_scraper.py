"""
Worker periódico: investigación profunda de convocatorias pendientes (CSV/SQLite).
Sustituye el antiguo scrape + Ollama mínimo por el pipeline unificado en
src.investigacion_convocatoria (construir_investigacion_convocatoria).

Uso:
  python -m scripts.worker_scraper        # Bucle infinito cada 6h
  python -m scripts.worker_scraper --once # Un solo ciclo (n8n/cron)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.db import (
    Convocatoria,
    actualizar,
    listar_pendientes_investigacion,
    resultado_id_estable_para_convocatoria,
)
from src.db_resumenes_convocatoria import guardar_resultado
from src.investigacion_convocatoria import construir_investigacion_convocatoria
from src.notifier import enviar_mensaje_a_chats

INTERVALO_HORAS = 6


def _mapear_resultado_a_conv(
    conv: Convocatoria,
    resultado: dict,
    rutas: dict[str, str],
) -> Convocatoria:
    ca = resultado.get("convocatoria_actual") or {}
    det = resultado.get("detalle_ayuda") or {}
    meta = resultado.get("metadata") or {}
    adv = resultado.get("advertencias") or []

    titulo = (ca.get("nombre") or "").strip()
    if titulo:
        conv.titulo = titulo[:500]

    plazo = (ca.get("plazo") or "").strip()
    if plazo:
        conv.plazo_fin = plazo[:2000]

    ben = (ca.get("beneficiarios") or "").strip()
    if ben:
        conv.requisitos = ben[:4000]

    parts: list[str] = []
    re = (det.get("resumen_ejecutivo") or "").strip()
    if re:
        parts.append(re[:4000])
    pres = (ca.get("presupuesto") or "").strip()
    if pres:
        parts.append(f"Presupuesto: {pres[:800]}")
    if parts:
        conv.descripcion = "\n\n".join(parts)[:8000]

    pie = f"\n\n[Resumen profundo] {rutas.get('ruta_markdown', '')}"
    base_desc = (conv.descripcion or "").strip()
    if len(base_desc) + len(pie) < 9500:
        conv.descripcion = (base_desc + pie).strip()

    conv.investigacion_id = str(meta.get("resultado_id", "") or "")
    conv.investigacion_fecha = str(meta.get("creado_en", "") or "")
    conv.investigacion_version = str(meta.get("version_pipeline", "") or "")

    critico = any(
        "No se pudo descargar o parsear la ficha objetivo" in (a or "") for a in adv
    )
    sin_titulo = not titulo

    prev = int((conv.investigacion_intentos or "0").strip() or "0")
    if critico and sin_titulo:
        conv.estado = "investigacion_parcial"
        conv.investigacion_intentos = str(prev + 1)
    else:
        conv.estado = "investigacion_ok"
        conv.investigacion_intentos = "0"

    return conv


def _procesar_una(conv: Convocatoria) -> bool:
    if not conv.url or not conv.url.startswith("http"):
        return False
    rid = resultado_id_estable_para_convocatoria(conv.id)
    resultado = construir_investigacion_convocatoria(conv.url.strip(), rid, query="")
    rutas = guardar_resultado(resultado, append_indice=False)
    conv2 = _mapear_resultado_a_conv(conv, resultado, rutas)
    ok = actualizar(conv2)
    if ok and config.NOTIFY_TELEGRAM_INVESTIGACION_CONVOCATORIA:
        titulo = (conv2.titulo or conv.url)[:80]
        resumen = (resultado.get("metadata") or {}).get("resumen_corto", "")[:300]
        msg = (
            f"Investigación convocatoria completada.\n{titulo}\n\n{resumen}\n{rutas.get('ruta_markdown', '')}"
        )[:3900]
        enviar_mensaje_a_chats(msg)
    return ok


def _ejecutar_ciclo() -> int:
    candidatas = listar_pendientes_investigacion()
    hechas = 0
    limite = config.MAX_CONVOCATORIAS_INVESTIGACION_POR_CICLO
    for conv in candidatas:
        if hechas >= limite:
            break
        try:
            if _procesar_una(conv):
                hechas += 1
        except Exception as e:
            print(f"Error investigando id={conv.id}: {e}", flush=True)
            conv.estado = "investigacion_parcial"
            prev = int((conv.investigacion_intentos or "0").strip() or "0")
            conv.investigacion_intentos = str(prev + 1)
            conv.investigacion_fecha = datetime.now().isoformat()
            actualizar(conv)
        time.sleep(max(2, int(config.INVESTIGACION_SLEEP_SEC)))
    return hechas


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de investigación profunda de convocatorias")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar un solo ciclo y terminar (para n8n/cron)",
    )
    args = parser.parse_args()

    if args.once:
        try:
            n = _ejecutar_ciclo()
            print(f"Ciclo completado. Investigadas: {n}")
        except Exception as e:
            print(f"Error en ciclo: {e}", file=sys.stderr)
            sys.exit(1)
        return

    intervalo_seg = INTERVALO_HORAS * 3600
    print(
        f"Worker convocatorias iniciado. Cada {INTERVALO_HORAS}h. "
        f"Máx {config.MAX_CONVOCATORIAS_INVESTIGACION_POR_CICLO} por ciclo. Ctrl+C para detener."
    )
    while True:
        try:
            n = _ejecutar_ciclo()
            print(f"Ciclo completado. Investigadas: {n}")
        except KeyboardInterrupt:
            print("\nWorker detenido.")
            sys.exit(0)
        except Exception as e:
            print(f"Error en ciclo: {e}")
        time.sleep(intervalo_seg)


if __name__ == "__main__":
    main()
