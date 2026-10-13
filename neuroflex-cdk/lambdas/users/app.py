"""Rutas /users: participantes (pacientes, deportistas, estudiantes) del silo.

Recomendación: no guardar nombres ni RUT aquí; usar un código interno o alias
que la organización pueda vincular en sus propios sistemas.
"""
import uuid

from botocore.exceptions import ClientError

from nf_common import (ApiError, caller_from_event, handle, json_body, require_group,
                       respond, tenant_context)

TRAMOS = {"<18", "18-29", "30-44", "45-59", "60-74", "75+", "sin_dato"}


@handle
def handler(event, context):
    caller = caller_from_event(event)
    ctx = tenant_context(caller)
    table = ctx["tables"]["users"]
    particulares = ctx["cfg"].get("tipo_cliente") == "particulares"

    if event.get("httpMethod") == "GET":
        if particulares:
            require_group(caller, "Particular")
            item = table.get_item(Key={"participante_id": caller.sub}).get("Item")
            return respond(200, {"items": [item] if item else []})
        require_group(caller, "Specialist", "Administrator")
        resp = table.scan(Limit=200)
        return respond(200, {"items": resp.get("Items", [])})

    body = json_body(event)
    tramo = body.get("tramo_edad", "sin_dato")
    if tramo not in TRAMOS:
        raise ApiError(400, f"tramo_edad debe ser uno de: {sorted(TRAMOS)}")
    if particulares:
        require_group(caller, "Particular")
        participante_id = caller.sub
    else:
        require_group(caller, "Administrator")
        participante_id = str(body.get("participante_id") or uuid.uuid4())
    item = {
        "participante_id": participante_id,
        "alias": str(body.get("alias") or "")[:60],
        "tramo_edad": tramo,
        "consentimiento_investigacion": False,  # se registra solo vía /terms/consent
        "creado_por": caller.sub,
    }
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(participante_id)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(409, "El participante ya existe")
        raise
    return respond(201, item)
