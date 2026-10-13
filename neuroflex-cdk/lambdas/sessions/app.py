"""Rutas /sessions: registrar y listar sesiones VR del silo del usuario."""
import os
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from nf_common import (ApiError, caller_from_event, handle, json_body, require_group,
                       respond, tenant_context)

EXPERIENCIAS = {e for e in os.environ.get("EXPERIENCIAS", "").split(",") if e}
ROLES_ORG = ("Specialist", "Administrator")


def _participante(caller, ctx, requested: str | None) -> str:
    if ctx["cfg"].get("tipo_cliente") == "particulares":
        require_group(caller, "Particular")
        return caller.sub  # un particular solo accede a sus propios datos
    require_group(caller, *ROLES_ORG)
    if not requested:
        raise ApiError(400, "Falta participante_id")
    return str(requested)


def _post(event, caller, ctx):
    body = json_body(event)
    sesion_id = str(body.get("sesion_id") or "")
    if not (8 <= len(sesion_id) <= 64):
        raise ApiError(400, "sesion_id debe ser un identificador generado por el visor")
    experiencia = body.get("experiencia")
    if EXPERIENCIAS and experiencia not in EXPERIENCIAS:
        raise ApiError(400, f"experiencia debe ser una de: {sorted(EXPERIENCIAS)}")
    metricas = body.get("metricas") or {}
    if not isinstance(metricas, dict) or not all(
            isinstance(v, (int, Decimal)) for v in metricas.values()):
        raise ApiError(400, "metricas debe ser un objeto con valores numéricos")

    participante_id = _participante(caller, ctx, body.get("participante_id"))
    perfil = ctx["tables"]["users"].get_item(Key={"participante_id": participante_id}).get("Item")
    if not perfil:
        raise ApiError(404, "Participante no registrado")

    item = {
        "participante_id": participante_id,
        "sesion_id": sesion_id,
        "experiencia": experiencia,
        "inicio": str(body.get("inicio") or datetime.now(timezone.utc).isoformat()),
        "duracion_seg": int(body.get("duracion_seg") or 0),
        "metricas": metricas,
        "version_app": str(body.get("version_app") or ""),
        "registrado_por": caller.sub,
        # Se copian del perfil al momento de registrar (los usa la analítica).
        "consentimiento_investigacion": bool(perfil.get("consentimiento_investigacion", False)),
        "tramo_edad": perfil.get("tramo_edad", "sin_dato"),
        "tipo_cliente": ctx["cfg"].get("tipo_cliente", "organizacion"),
        "tenant_id": caller.tenant_id,
    }
    try:
        ctx["tables"]["sessions"].put_item(
            Item=item, ConditionExpression="attribute_not_exists(sesion_id)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(200, {"sesion_id": sesion_id, "duplicada": True})
        raise
    return respond(201, {"sesion_id": sesion_id})


def _get(event, caller, ctx):
    qs = event.get("queryStringParameters") or {}
    participante_id = _participante(caller, ctx, qs.get("participante_id"))
    resp = ctx["tables"]["sessions"].query(
        KeyConditionExpression=Key("participante_id").eq(participante_id),
        ScanIndexForward=False, Limit=50)
    return respond(200, {"items": resp.get("Items", [])})


@handle
def handler(event, context):
    caller = caller_from_event(event)
    ctx = tenant_context(caller)
    if event.get("httpMethod") == "POST":
        return _post(event, caller, ctx)
    return _get(event, caller, ctx)
