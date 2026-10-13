"""Exportación de-identificada de sesiones hacia la cuenta de analítica.

Por cada sesión nueva o modificada (DynamoDB Streams):
1. Descarta las de personas sin consentimiento para investigación.
2. Elimina identificadores y textos libres; conserva solo métricas numéricas.
3. Reemplaza participante y organización por un seudónimo HMAC (KMS).
4. Generaliza la fecha a la semana (lunes) y la edad a tramos.
5. Escribe JSON Lines comprimido, particionado por experiencia y semana.
"""
import base64
import gzip
import io
import json
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer

BUCKET = os.environ["ANALYTICS_BUCKET"]
KMS_KEY_ARN = os.environ["ANALYTICS_KMS_KEY_ARN"]
HMAC_KEY_ID = os.environ["HMAC_KEY_ID"]
EXPERIENCIAS = {e for e in os.environ.get("EXPERIENCIAS", "").split(",") if e}

_kms = boto3.client("kms")
_s3 = boto3.client("s3")
_des = TypeDeserializer()
_pseudo_cache: dict = {}


def pseudonym(value: str) -> str:
    if value not in _pseudo_cache:
        mac = _kms.generate_mac(KeyId=HMAC_KEY_ID, Message=value.encode("utf-8"),
                                MacAlgorithm="HMAC_SHA_256")["Mac"]
        _pseudo_cache[value] = base64.urlsafe_b64encode(mac).decode()[:32]
    return _pseudo_cache[value]


def week_start(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def deidentify(item: dict) -> dict | None:
    if not item.get("consentimiento_investigacion"):
        return None
    experiencia = item.get("experiencia")
    if EXPERIENCIAS and experiencia not in EXPERIENCIAS:
        return None
    metricas = {k: float(v) for k, v in (item.get("metricas") or {}).items()
                if isinstance(v, (int, float, Decimal))}
    tenant = str(item.get("tenant_id", ""))
    return {
        "_experiencia": experiencia,
        "_semana": week_start(str(item.get("inicio", ""))),
        "registro_id": pseudonym(f"sesion:{tenant}:{item.get('sesion_id')}"),
        "participante": pseudonym(f"participante:{tenant}:{item.get('participante_id')}"),
        "organizacion": pseudonym(f"organizacion:{tenant}"),
        "tipo_cliente": item.get("tipo_cliente", "organizacion"),
        "tramo_edad": item.get("tramo_edad", "sin_dato"),
        "duracion_seg": int(item.get("duracion_seg") or 0),
        "version_app": str(item.get("version_app") or ""),
        "metricas": metricas,
    }


def handler(event, context):
    grupos: dict = {}
    for record in event.get("Records", []):
        image = record.get("dynamodb", {}).get("NewImage")
        if not image:
            continue
        item = {k: _des.deserialize(v) for k, v in image.items()}
        row = deidentify(item)
        if row:
            key = (row.pop("_experiencia"), row.pop("_semana"))
            grupos.setdefault(key, []).append(row)

    for (experiencia, semana), rows in grupos.items():
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            for r in rows:
                gz.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
        _s3.put_object(
            Bucket=BUCKET,
            Key=f"sessions/experiencia={experiencia}/semana={semana}/{uuid.uuid4()}.json.gz",
            Body=buf.getvalue(),
            ContentType="application/json",
            ContentEncoding="gzip",
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=KMS_KEY_ARN,
        )
    return {"batchItemFailures": []}
