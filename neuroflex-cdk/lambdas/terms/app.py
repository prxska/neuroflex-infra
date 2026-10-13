"""Rutas /terms: versión vigente de términos y registro de consentimiento.

El consentimiento para investigación es OPCIONAL e independiente del uso del
servicio (Ley 21.719): rechazarlo no limita el acceso a la plataforma.
"""
import os
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from nf_common import (ApiError, caller_from_event, handle, json_body, require_group,
                       respond, tenant_context)

TERMS_VERSION = os.environ.get("TERMS_VERSION", "1")


@handle
def handler(event, context):
    caller = caller_from_event(event)
    if event.get("httpMethod") == "GET":
        return respond(200, {"version": TERMS_VERSION})

    ctx = tenant_context(caller)
    body = json_body(event)
    if not isinstance(body.get("investigacion"), bool):
        raise ApiError(400, "investigacion debe ser true o false")
    if ctx["cfg"].get("tipo_cliente") == "particulares":
        require_group(caller, "Particular")
        participante_id = caller.sub
    else:
        require_group(caller, "Specialist", "Administrator")
        participante_id = body.get("participante_id")
        if not participante_id:
            raise ApiError(400, "Falta participante_id")

    try:
        _update(ctx, participante_id, body["investigacion"], caller.sub)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(404, "Participante no registrado")
        raise
    return respond(200, {"participante_id": participante_id,
                         "investigacion": body["investigacion"], "version": TERMS_VERSION})


def _update(ctx, participante_id, investigacion, sub):
    ctx["tables"]["users"].update_item(
        Key={"participante_id": str(participante_id)},
        UpdateExpression=("SET consentimiento_investigacion = :c, consentimiento_version = :v, "
                          "consentimiento_fecha = :f, consentimiento_registrado_por = :r"),
        ConditionExpression="attribute_exists(participante_id)",
        ExpressionAttributeValues={
            ":c": investigacion, ":v": TERMS_VERSION,
            ":f": datetime.now(timezone.utc).isoformat(), ":r": sub,
        },
    )
