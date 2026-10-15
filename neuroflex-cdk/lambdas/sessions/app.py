"""Rutas /sessions: registrar y listar sesiones VR del silo del usuario."""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Attr
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
    telemetria_raw = body.get("telemetria_raw") or []  # Array de eventos masivos de VR

    participante_id = _participante(caller, ctx, body.get("participante_id"))
    
    # Búsqueda por la Partition Key real de la tabla users (user_id)
    perfil = ctx["tables"]["users"].get_item(Key={"user_id": participante_id}).get("Item")
    if not perfil:
        raise ApiError(404, "Participante no registrado")

    # 1. Almacenamiento masivo asíncrono en S3 (Cold Data / Raw Telemetry)
    if telemetria_raw:
        bucket_name = ctx["cfg"].get("bucket")
        if bucket_name:
            key = f"sessions/{participante_id}/{sesion_id}.json"
            ctx["s3"].put_object(
                Bucket=bucket_name,
                Key=key,
                Body=json.dumps(
                    telemetria_raw,
                    default=lambda o: float(o) if isinstance(o , Decimal) else str(o)),
                ContentType="application/json"
            )

    # 2. Almacenamiento liviano en DynamoDB (Hot Data / Summary)
    item = {
        "session_id": sesion_id,         # Key principal requerida por DynamoDB
        "sesion_id": sesion_id,          # Mantenido por compatibilidad si la API lo requiere
        "participante_id": participante_id,
        "experiencia": experiencia,
        "inicio": str(body.get("inicio") or datetime.now(timezone.utc).isoformat()),
        "duracion_seg": int(body.get("duracion_seg") or 0),
        "metricas": metricas,
        "version_app": str(body.get("version_app") or ""),
        "registrado_por": caller.sub,
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
        
    return respond(201, {"sesion_id": sesion_id, "s3_telemetry": bool(telemetria_raw)})


def _get(event, caller, ctx):
    qs = event.get("queryStringParameters") or {}
    participante_id = _participante(caller, ctx, qs.get("participante_id"))
    
    resp = ctx["tables"]["sessions"].scan(
        FilterExpression=Attr("participante_id").eq(participante_id),
        Limit=50
    )
    return respond(200, {"items": resp.get("Items", [])})


@handle
def handler(event, context):
    caller = caller_from_event(event)
    ctx = tenant_context(caller)
    if event.get("httpMethod") == "POST":
        return _post(event, caller, ctx)
    return _get(event, caller, ctx)