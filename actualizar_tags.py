import boto3
from datetime import datetime

# ==========================================
# CONFIGURACIÓN
# ==========================================
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('nf-scenes-v1-mt')

def actualizar_registros():
    print("1. Escaneando la tabla de DynamoDB...")
    # Escaneamos la tabla para obtener todos los registros
    response = table.scan()
    items = response.get('Items', [])
    
    print(f"✅ Se encontraron {len(items)} registros (rondas). Iniciando actualización...\n")
    
    actualizados = 0
    for item in items:
        pk = item['tenantParticipantKey']
        sk = item['roundId']
        
        # Si el registro no tiene sessionId, lo creamos (usando los primeros caracteres de la ronda o un default)
        session_id = item.get('sessionId', f"sesion-{sk[:6]}")
        
        # Le asignamos un TAG de prueba (puedes cambiarlo por "usuario#14" para la demo)
        tag = item.get('tag', 'usuario#1')

        try:
            # Actualizamos el ítem usando la llave primaria (PK y SK)
            table.update_item(
                Key={
                    'tenantParticipantKey': pk,
                    'roundId': sk
                },
                UpdateExpression="SET sessionId = :s, tag = :t, updated_at = :u",
                ExpressionAttributeValues={
                    ':s': session_id,
                    ':t': tag,
                    ':u': datetime.now().isoformat()
                }
            )
            actualizados += 1
            if actualizados % 50 == 0:
                print(f"   ✅ {actualizados} registros actualizados...")
                
        except Exception as e:
            print(f"   ❌ Error actualizando {sk}: {e}")

    print(f"\n🏁 Proceso finalizado. {actualizados} registros ahora tienen 'sessionId' y 'tag'.")

if __name__ == "__main__":
    actualizar_registros()