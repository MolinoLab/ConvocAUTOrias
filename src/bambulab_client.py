"""
Integración mínima con BambuLab:
- estado de impresión por MQTT local
- apagado delegando en enchufe (Tuya) si está configurado
"""
from __future__ import annotations

import json
import ssl
import time

import config
from src.tuya_client import poner_enchufe

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


_LAST_BAMBU_ERROR = ""


def _set_last_error(msg: str) -> None:
    global _LAST_BAMBU_ERROR
    _LAST_BAMBU_ERROR = (msg or "").strip()[:700]


def obtener_ultimo_error_bambu() -> str:
    return _LAST_BAMBU_ERROR


def obtener_estado_impresion() -> tuple[bool, str]:
    _set_last_error("")
    if mqtt is None:
        _set_last_error("Falta dependencia paho-mqtt.")
        return False, ""
    host = (config.BAMBU_HOST or "").strip()
    serial = (config.BAMBU_SERIAL or "").strip()
    access_code = (config.BAMBU_ACCESS_CODE or "").strip()
    if not host or not serial or not access_code:
        _set_last_error("Faltan BAMBU_HOST, BAMBU_SERIAL o BAMBU_ACCESS_CODE.")
        return False, ""

    report_topic = f"device/{serial}/report"
    request_topic = f"device/{serial}/request"
    got_payload: dict = {}

    def _on_message(_client, _userdata, msg) -> None:
        nonlocal got_payload
        try:
            got_payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        except Exception:
            got_payload = {}

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.username_pw_set("bblp", access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_message = _on_message
    try:
        client.connect(host, int(config.BAMBU_MQTT_PORT), keepalive=15)
        client.subscribe(report_topic, qos=0)
        client.loop_start()
        pushall = {"pushing": {"command": "pushall", "sequence_id": "0", "version": 1}}
        client.publish(request_topic, json.dumps(pushall), qos=0, retain=False)
        inicio = time.time()
        while time.time() - inicio < max(2, int(config.BAMBU_STATUS_TIMEOUT_SEC)):
            if got_payload:
                break
            time.sleep(0.2)
    except Exception as exc:
        _set_last_error(f"Error MQTT Bambu: {str(exc)[:200]}")
        return False, ""
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    if not got_payload:
        _set_last_error("Sin respuesta de estado de la impresora.")
        return False, ""

    print_data = got_payload.get("print") if isinstance(got_payload, dict) else {}
    if not isinstance(print_data, dict):
        return True, "Estado recibido, pero no se pudo parsear el bloque de impresión."
    progreso = print_data.get("mc_percent")
    etapa = print_data.get("gcode_state") or print_data.get("stg_cur")
    nombre = print_data.get("subtask_name") or print_data.get("project_id")
    partes: list[str] = []
    if nombre:
        partes.append(f"Trabajo: {nombre}")
    if etapa is not None:
        partes.append(f"Estado: {etapa}")
    if progreso is not None:
        partes.append(f"Progreso: {progreso}%")
    if not partes:
        return True, "Estado recibido, pero sin campos de progreso conocidos."
    return True, "\n".join(partes)


def apagar_impresora() -> tuple[bool, str]:
    _set_last_error("")
    did = (config.BAMBU_POWER_OFF_TUYA_DEVICE_ID or config.TUYA_DEVICE_ID or "").strip()
    if not did:
        _set_last_error("Falta BAMBU_POWER_OFF_TUYA_DEVICE_ID (o TUYA_DEVICE_ID).")
        return False, ""
    ok, msg = poner_enchufe(False, device_id=did, switch_code=config.TUYA_SWITCH_CODE)
    if not ok:
        _set_last_error("No se pudo apagar el enchufe asociado a la impresora.")
        return False, ""
    return True, f"Solicitud de apagado enviada.\n{msg}"
