"""Worker asíncrono: Consume batches de SQS y persiste en DynamoDB y S3."""
from aws_cdk import aws_lambda_event_sources as eventsources

import json
import os
from decimal import Decimal
import boto3

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    records = event.get("Records", [])
    for record in records:
        body = json.loads(record["body"])
        
        participante_id = body["participante_id"]
        sesion_id = body["sesion_id"]
        telemetria_raw = body.get("telemetria_raw", [])
        bucket_name = body.get("bucket_name")
        table_name = body.get("table_name")

        # 1. Almacenar Cold Data en S3
        if telemetria_raw and bucket_name:
            key = f"sessions/{participante_id}/{sesion_id}.json"
            s3_client.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=json.dumps(
                    telemetria_raw,
                    default=lambda o: float(o) if isinstance(o, Decimal) else str(o)
                ),
                ContentType="application/json"
            )

        # 2. Almacenar Hot Data en DynamoDB
        if table_name:
            table = dynamodb.Table(table_name)
            item = {
                "session_id": sesion_id,
                "sesion_id": sesion_id,
                "participante_id": participante_id,
                "experiencia": body.get("experiencia"),
                "scene_config_id": body.get("scene_config_id"),
                "inicio": body.get("inicio"),
                "duracion_seg": int(body.get("duracion_seg", 0)),
                "metricas": body.get("metricas", {}),
                "version_app": body.get("version_app", ""),
                "registrado_por": body.get("registrado_por"),
                "consentimiento_investigacion": body.get("consentimiento_investigacion", False),
                "tramo_edad": body.get("tramo_edad", "sin_dato"),
                "tenant_id": body.get("tenant_id"),
            }
            table.put_item(Item=item)

    return {"statusCode": 200, "processed": len(records)}