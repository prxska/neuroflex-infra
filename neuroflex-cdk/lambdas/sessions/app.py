"""Rutas /sessions: registrar y listar sesiones VR del silo del usuario."""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from nf_common import (ApiError, caller_from_event, handle, json_body, require_group,
                       respond, tenant_context)

EXPERIENCIAS = {e for e in os.environ.get("EXPERIENCIAS", "").split(",") if e}
ROLES_ORG = ("Specialist", "Administrator")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
sqs_client = boto3.client("sqs")


def _participante(caller, ctx, requested: str | None) -> str:
    if ctx["cfg"].get("tipo_cliente") == "particulares":
        require_group(caller, "Particular")
        return caller.sub
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
    # facil o dificil 
    scene_config_id = str(body.get("scene_config_id") or "").strip()
    if not scene_config_id:
        raise ApiError(400, "Falta scene_config_id (identificador de versión del nivel/recorrido)")

    participante_id = _participante(caller, ctx, body.get("participante_id"))
    
    perfil = ctx["tables"]["users"].get_item(Key={"user_id": participante_id}).get("Item")
    if not perfil:
        raise ApiError(404, "Participante no registrado")

    # MODO A: Encolar en SQS para procesamiento asíncrono masivo
    if SQS_QUEUE_URL:
        payload = {
            "sesion_id": sesion_id,
            "participante_id": participante_id,
            "experiencia": experiencia,
            "scene_config_id": scene_config_id,
            "inicio": str(body.get("inicio") or datetime.now(timezone.utc).isoformat()),
            "duracion_seg": int(body.get("duracion_seg") or 0),
            "metricas": body.get("metricas") or {},
            "telemetria_raw": body.get("telemetria_raw") or [],
            "version_app": str(body.get("version_app") or ""),
            "registrado_por": caller.sub,
            "consentimiento_investigacion": bool(perfil.get("consentimiento_investigacion", False)),
            "tramo_edad": perfil.get("tramo_edad", "sin_dato"),
            "tenant_id": caller.tenant_id,
            "bucket_name": ctx["cfg"].get("bucket"),
            "table_name": ctx["tables"]["sessions"].name
        }
        
        sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(
                payload,
                default=lambda o: float(o) if isinstance(o, Decimal) else str(o)
            )
        )
        return respond(202, {"sesion_id": sesion_id, "status": "queued"})

    # MODO B: Escritura directa sincrónica (Fallback)
    metricas = body.get("metricas") or {}
    telemetria_raw = body.get("telemetria_raw") or []

    if telemetria_raw:
        bucket_name = ctx["cfg"].get("bucket")
        if bucket_name:
            key = f"sessions/{participante_id}/{sesion_id}.json"
            ctx["s3"].put_object(
                Bucket=bucket_name,
                Key=key,
                Body=json.dumps(
                    telemetria_raw,
                    default=lambda o: float(o) if isinstance(o, Decimal) else str(o)
                ),
                ContentType="application/json"
            )

    item = {
        "session_id": sesion_id,
        "sesion_id": sesion_id,
        "participante_id": participante_id,
        "experiencia": experiencia,
        "scene_config_id": scene_config_id,
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
            Item=item, ConditionExpression="attribute_not_exists(session_id)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(200, {"sesion_id": sesion_id, "duplicada": True})
        raise
        
    return respond(201, {"sesion_id": sesion_id, "s3_telemetry": bool(telemetria_raw)})


def _get(event, caller, ctx):
    qs = event.get("queryStringParameters") or {}
    participante_id = _participante(caller, ctx, qs.get("participante_id"))
    
    # Descarga de telemetría pesada desde S3
    if qs.get("telemetria") == "true":
        session_id = qs.get("session_id")
        if not session_id:
            raise ApiError(400, "Falta session_id para obtener la telemetría")
            
        bucket_name = ctx["cfg"].get("bucket")
        key = f"sessions/{participante_id}/{session_id}.json"
        
        try:
            obj = ctx["s3"].get_object(Bucket=bucket_name, Key=key)
            telemetria_data = json.loads(obj["Body"].read().decode("utf-8"))
            return respond(200, {
                "session_id": session_id,
                "participante_id": participante_id,
                "telemetria": telemetria_data
            })
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise ApiError(404, "No existe archivo de telemetría para esta sesión")
            raise

    # Consulta habitual de resúmenes en DynamoDB
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