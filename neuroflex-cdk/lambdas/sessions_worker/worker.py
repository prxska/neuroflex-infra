import json
import os
from decimal import Decimal
import boto3

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

# INYECCIÓN DE VERDAD: El backend debe saber sus propias tablas, no preguntarle al frontend.
TABLE_NAME = os.environ.get("TABLE_NAME", "nf-sessions")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "nf-sessions-cold-data")

def handler(event, context):
    records = event.get("Records", [])
    for record in records:
        body = json.loads(record["body"])
        
        participante_id = body["participante_id"]
        sesion_id = body["sesion_id"]
        telemetria_raw = body.get("telemetria_raw", [])

        # 1. Almacenar Hot Data en DynamoDB (Cambiamos el orden, Dynamo es prioridad)
        table = dynamodb.Table(TABLE_NAME)
        item = {
            "session_id": sesion_id,
            "sesion_id_sort": sesion_id, # Evita duplicar claves si no es necesario
            "participante_id": participante_id,
            "experiencia": body.get("experiencia", "unknown"),
            "scene_config_id": body.get("scene_config_id", "unknown"),
            "duracion_seg": int(body.get("duracion_seg", 0)),
            "metricas": body.get("metricas", {}),
            # ... el resto de tus campos
        }
        table.put_item(Item=item)

        # 2. Almacenar Cold Data en S3 (Solo si hay telemetría densa)
        if telemetria_raw and BUCKET_NAME != "nf-sessions-cold-data":
            key = f"sessions/{participante_id}/{sesion_id}.json"
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=json.dumps(telemetria_raw, default=lambda o: float(o) if isinstance(o, Decimal) else str(o)),
                ContentType="application/json"
            )

    return {"statusCode": 200, "processed": len(records)}