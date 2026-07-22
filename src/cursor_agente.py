"""
Lanza agentes locales de Cursor (SDK) desde el bot Telegram (/agente).

Runtime local dentro del contenedor: workspace = CURSOR_AGENT_CWD.
MCP: .cursor/mcp.json del proyecto (si setting_sources incluye project) +
opcionalmente Telegram MCP inline y CURSOR_AGENTE_MCP_JSON.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

# Persistencia ligera de agent_id por chat (reanudar conversación)
_STATE_PATH = config.DATA_DIR / "cursor_agente_sesiones.json"


@dataclass
class AgenteResultado:
    texto: str
    agent_id: str | None = None
    run_id: str | None = None
    status: str = "finished"
    error: str | None = None


def _leer_sesiones() -> dict[str, str]:
    if not _STATE_PATH.exists():
        return {}
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if k and v}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        logger.warning("No se pudo leer %s", _STATE_PATH)
    return {}


def _guardar_sesiones(sesiones: dict[str, str]) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps(sesiones, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.exception("No se pudo guardar %s", _STATE_PATH)


def obtener_agent_id(chat_id: int | str) -> str | None:
    return _leer_sesiones().get(str(chat_id))


def guardar_agent_id(chat_id: int | str, agent_id: str) -> None:
    sesiones = _leer_sesiones()
    sesiones[str(chat_id)] = agent_id
    _guardar_sesiones(sesiones)


def borrar_agent_id(chat_id: int | str) -> bool:
    sesiones = _leer_sesiones()
    if str(chat_id) not in sesiones:
        return False
    del sesiones[str(chat_id)]
    _guardar_sesiones(sesiones)
    return True


def _mcp_servers() -> dict[str, Any] | None:
    servers: dict[str, Any] = {}
    if config.CURSOR_AGENTE_MCP_JSON:
        try:
            parsed = json.loads(config.CURSOR_AGENTE_MCP_JSON)
            if isinstance(parsed, dict):
                servers.update(parsed)
        except json.JSONDecodeError:
            logger.warning("CURSOR_AGENTE_MCP_JSON no es JSON válido; se ignora")

    if config.CURSOR_AGENTE_TELEGRAM_MCP and config.TELEGRAM_BOT_TOKEN:
        env: dict[str, str] = {"TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN}
        if config.TELEGRAM_CHAT_ID:
            env["TELEGRAM_CHAT_ID"] = str(config.TELEGRAM_CHAT_ID)
        servers["telegram"] = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "github:pauloFroes/mcp-telegram"],
            "env": env,
        }

    return servers or None


async def ejecutar_prompt(
    prompt: str,
    *,
    chat_id: int | str | None = None,
    agent_id: str | None = None,
    nuevo: bool = False,
) -> AgenteResultado:
    """
    Ejecuta un prompt con un agente local de Cursor.
    Si hay agent_id (o sesión del chat) y nuevo=False, reanuda esa conversación.
    """
    if not config.CURSOR_API_KEY:
        return AgenteResultado(
            texto="",
            status="error",
            error="CURSOR_API_KEY no configurada en .env",
        )

    prompt = (prompt or "").strip()
    if not prompt:
        return AgenteResultado(
            texto="",
            status="error",
            error="Prompt vacío",
        )

    cwd = str(config.CURSOR_AGENT_CWD.resolve())
    if not Path(cwd).is_dir():
        return AgenteResultado(
            texto="",
            status="error",
            error=f"CURSOR_AGENT_CWD no existe: {cwd}",
        )

    resume_id = None if nuevo else (agent_id or (obtener_agent_id(chat_id) if chat_id is not None else None))
    mcp = _mcp_servers()
    sources = list(config.CURSOR_AGENTE_SETTING_SOURCES) or None

    try:
        from cursor_sdk import (
            AsyncClient,
            LocalAgentOptions,
        )
    except ImportError:
        return AgenteResultado(
            texto="",
            status="error",
            error="cursor-sdk no instalado. Añádelo a requirements y reconstruye la imagen Docker.",
        )

    timeout = float(config.CURSOR_AGENT_TIMEOUT_SEC)

    async def _run() -> AgenteResultado:
        async with await AsyncClient.launch_bridge(workspace=cwd) as client:
            create_kwargs: dict[str, Any] = {
                "model": config.CURSOR_MODEL,
                "api_key": config.CURSOR_API_KEY,
                "local": LocalAgentOptions(
                    cwd=cwd,
                    setting_sources=sources,
                ),
            }
            if mcp:
                create_kwargs["mcp_servers"] = mcp

            if resume_id:
                try:
                    resume_kwargs: dict[str, Any] = {
                        "api_key": config.CURSOR_API_KEY,
                        "model": config.CURSOR_MODEL,
                        "local": LocalAgentOptions(
                            cwd=cwd,
                            setting_sources=sources,
                        ),
                    }
                    if mcp:
                        resume_kwargs["mcp_servers"] = mcp
                    agent_cm = await client.agents.resume(resume_id, **resume_kwargs)
                except Exception as exc:
                    logger.warning(
                        "No se pudo reanudar agent_id=%s (%s); se crea uno nuevo",
                        resume_id,
                        exc,
                    )
                    agent_cm = await client.agents.create(**create_kwargs)
            else:
                agent_cm = await client.agents.create(**create_kwargs)

            async with agent_cm as agent:  # noqa: SIM117 — API del SDK
                aid = getattr(agent, "agent_id", None) or getattr(agent, "agentId", None)
                run = await agent.send(prompt)
                run_id = getattr(run, "id", None)
                result = await run.wait()
                status = getattr(result, "status", None) or "finished"
                texto = ""
                # Preferir texto final del run si existe
                text_fn = getattr(run, "text", None)
                if callable(text_fn):
                    try:
                        maybe = text_fn()
                        if asyncio.iscoroutine(maybe):
                            texto = await maybe
                        else:
                            texto = maybe or ""
                    except Exception:
                        texto = ""
                if not texto:
                    texto = getattr(result, "result", None) or ""
                if not isinstance(texto, str):
                    texto = str(texto) if texto is not None else ""

                if chat_id is not None and aid:
                    guardar_agent_id(chat_id, str(aid))

                if status == "error":
                    return AgenteResultado(
                        texto=texto or "El agente terminó con error.",
                        agent_id=str(aid) if aid else None,
                        run_id=str(run_id) if run_id else None,
                        status="error",
                        error=f"run falló (id={run_id})",
                    )
                return AgenteResultado(
                    texto=texto.strip() or "(sin respuesta de texto del agente)",
                    agent_id=str(aid) if aid else None,
                    run_id=str(run_id) if run_id else None,
                    status=str(status),
                )

    try:
        return await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        return AgenteResultado(
            texto="",
            status="error",
            error=f"Timeout tras {int(timeout)}s. Prueba un prompt más corto o sube CURSOR_AGENT_TIMEOUT_SEC.",
        )
    except Exception as exc:
        # CursorAgentError u otros
        name = type(exc).__name__
        msg = str(exc) or name
        retryable = getattr(exc, "is_retryable", getattr(exc, "isRetryable", None))
        extra = f" (reintentable={retryable})" if retryable is not None else ""
        if name == "CursorAgentError" or "CursorAgent" in name:
            return AgenteResultado(
                texto="",
                status="error",
                error=f"No arrancó el agente: {msg}{extra}",
            )
        logger.exception("Error ejecutando agente Cursor")
        return AgenteResultado(
            texto="",
            status="error",
            error=f"{name}: {msg}",
        )
