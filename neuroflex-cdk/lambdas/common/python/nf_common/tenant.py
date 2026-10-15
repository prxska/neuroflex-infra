"""Resolución del hospital (tenant) y acceso a su silo mediante AssumeRole.

Reglas:
- El tenant_id se toma SOLO del contexto entregado por el Lambda Authorizer.
- Se rechaza la llamada si el tenant no existe o está suspendido.
- Las credenciales temporales se reutilizan mientras sigan vigentes.
"""
import os
import time
from dataclasses import dataclass

import boto3

from .http import ApiError

_sts = boto3.client("sts")
_tenants = boto3.resource("dynamodb").Table(os.environ.get("TENANTS_TABLE", "nf-tenants"))
_cache: dict = {}
_CFG_TTL = 300  # segundos que se confía en la configuración leída de nf-tenants


@dataclass
class Caller:
    tenant_id: str
    sub: str
    groups: set


def caller_from_event(event) -> Caller:
    ctx = (event.get("requestContext") or {}).get("authorizer") or {}
    # REST API entrega el contexto directamente; HTTP API lo anida en "lambda".
    ctx = ctx.get("lambda", ctx)
    tenant_id, sub = ctx.get("tenant_id"), ctx.get("sub")
    if not tenant_id or not sub:
        raise ApiError(401, "No autenticado")
    groups = {g for g in (ctx.get("groups") or "").split(",") if g}
    return Caller(tenant_id=tenant_id, sub=sub, groups=groups)


def require_group(caller: Caller, *allowed: str) -> None:
    if not caller.groups.intersection(allowed):
        raise ApiError(403, "No tiene permisos para esta acción")

def tenant_context(caller: Caller) -> dict:
    now = time.time()
    hit = _cache.get(caller.tenant_id)
    if hit and hit["expira"] > now + 60 and hit["cfg_hasta"] > now:
        return hit

    item = _tenants.get_item(Key={"tenant_id": caller.tenant_id}).get("Item")
    if not item:
        raise ApiError(403, "Organización no registrada")
    if item.get("estado") != "activo":
        raise ApiError(403, "Organización suspendida")

    # Bypass de AssumeRole para AWS Learner Lab
    if "LabRole" in item.get("rol_arn", ""):
        ddb = boto3.resource("dynamodb")
        s3_client = boto3.client("s3")
        expira_time = now + 3600
    else:
        cred = _sts.assume_role(
            RoleArn=item["rol_arn"],
            RoleSessionName=f"nf-{caller.tenant_id}-{caller.sub[:24]}",
            DurationSeconds=900,
            Tags=[{"Key": "tenant_id", "Value": caller.tenant_id}],
        )["Credentials"]
        session = boto3.Session(
            aws_access_key_id=cred["AccessKeyId"],
            aws_secret_access_key=cred["SecretAccessKey"],
            aws_session_token=cred["SessionToken"],
        )
        ddb = session.resource("dynamodb")
        s3_client = session.client("s3")
        expira_time = cred["Expiration"].timestamp()

    hit = {
        "cfg": item,
        "tables": {k: ddb.Table(v) for k, v in item["tablas"].items()},
        "s3": s3_client,
        "expira": expira_time,
        "cfg_hasta": now + _CFG_TTL,
    }
    _cache[caller.tenant_id] = hit
    return hit
