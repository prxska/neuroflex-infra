import json
import os
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('SCENES_TABLE_NAME', 'nf-scenes-v1-mt'))

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def handler(event, context):
    try:
        # CORS Preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'OPTIONS,GET'
                }
            }

        params = event.get('queryStringParameters') or {}
        participant_id = params.get('participantId')
        
        # Extraemos el Tenant de la URL (o por defecto 'habaA' si no viene)
        tenant_id = params.get('tenantId', 'habaA')

        if not participant_id:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'participantId es requerido'})
            }

        # AISLAMIENTO: Construimos la llave compuesta "clinica#paciente"
        composite_key = f"{tenant_id}#{participant_id}"

        # Consultamos usando la nueva Partition Key
        response = table.query(
            KeyConditionExpression=Key('tenantParticipantKey').eq(composite_key)
        )
        items = response.get('Items', [])
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            },
            "body": json.dumps({"items": items}, default=decimal_default)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)})
        }