import json
import os
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('SCENES_TABLE_NAME', 'nf-scenes-v1-mt'))

def handler(event, context):
    try:
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
                }
            }

        params = event.get('queryStringParameters') or {}
        participant_id = params.get('participantId')
        session_id = params.get('sessionId')
        tenant_id = params.get('tenantId', 'habaA')

        if not participant_id or not session_id:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Faltan parámetros'})
            }

        composite_key = f"{tenant_id}#{participant_id}"
        
        # 1. Buscamos todas las rondas de esta sesión
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('tenantParticipantKey').eq(composite_key)
        )
        
        items_to_delete = [item for item in response.get('Items', []) if item.get('sessionId') == session_id]

        # 2. Las borramos en lote
        with table.batch_writer() as batch:
            for item in items_to_delete:
                batch.delete_item(
                    Key={
                        'tenantParticipantKey': item['tenantParticipantKey'],
                        'roundId': item['roundId']
                    }
                )

        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"},
            "body": json.dumps({"message": "Sesión eliminada", "deleted": len(items_to_delete)})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e)})
        }