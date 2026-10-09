import json
import os
import boto3
from decimal import Decimal

# Cliente DynamoDB inicializado fuera del handler (reutilizacion en warm start)
dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("DYNAMODB_TABLE", "neuroflex-sessions-dev")
table = dynamodb.Table(table_name)

def float_to_decimal(obj):
    """DynamoDB no soporta floats nativos de Python; requiere conversion a Decimal."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [float_to_decimal(i) for i in obj]
    return obj

def handler(event, context):
    records = event.get("Records", [])
    processed_count = 0

    for record in records:
        try:
            # SQS entrega el body enviado originalmente desde API Gateway
            body_raw = record.get("body", "{}")
            body = json.loads(body_raw)
            
            # Sanitizacion de tipos para DynamoDB
            item = float_to_decimal(body)

            # Persistencia con particion multi-tenant (tenant_id, session_id)
            table.put_item(Item=item)
            processed_count += 1
            print(f"Sesion persistida con exito: {item.get('session_id')}")

        except Exception as e:
            print(f"Error procesando registro SQS: {str(e)}")
            # Relanzar error para que SQS reintente o mande el paquete a la DLQ
            raise e

    return {
        "statusCode": 200,
        "body": json.dumps({"processed_records": processed_count})
    }