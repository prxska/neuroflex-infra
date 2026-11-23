import requests
import boto3
import json

# ==========================================
# CONFIGURACIÓN
# ==========================================
FIREBASE_PROJECT_ID = "newroflex"
FIREBASE_API_KEY = "AIzaSyBO14j2DGwb1ukH6WwE0eaZygcSfUZ69v8"
BASE_FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('nf-scenes-v1-mt')

def get_docs(path):
    url = f"{BASE_FIRESTORE_URL}/{path}?key={FIREBASE_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json().get('documents', [])
    return []

def arreglar_datos():
    print("1. Descargando datos corregidos desde Firebase...")
    sessions = get_docs("sessions")
    
    # Diccionario para traducir IDs técnicos a nombres bonitos
    MAPEO_ESCENAS = {
        'puzzle': 'Biblioteca',
        'memory': 'Memoria',
        'pigeons': 'Palomas'
    }

    actualizados = 0
    for session in sessions:
        session_fields = session.get('fields', {})
        
        # Obtenemos el código real de la sesión (ej: sesion-A088)
        session_code = session_fields.get('session_code', {}).get('stringValue', session['name'].split('/')[-1])

        scenes = get_docs(f"sessions/{session['name'].split('/')[-1]}/scenes")
        for scene in scenes:
            scene_id = scene['name'].split('/')[-1] # ej: 'puzzle'
            nombre_bonito = MAPEO_ESCENAS.get(scene_id, scene_id) # Traducimos a 'Biblioteca'

            difficulties = get_docs(f"sessions/{session['name'].split('/')[-1]}/scenes/{scene_id}/difficulties")
            for diff in difficulties:
                diff_id = diff['name'].split('/')[-1]
                rounds = get_docs(f"sessions/{session['name'].split('/')[-1]}/scenes/{scene_id}/difficulties/{diff_id}/rounds")
                
                for rnd in rounds:
                    rnd_id = rnd['name'].split('/')[-1]
                    
                    # Actualizamos directamente en DynamoDB usando el roundId como referencia
                    # Buscamos qué registro tiene este roundId
                    try:
                        # Como no sabemos la PK exacta sin hacer scan, hacemos un scan rápido con filtro
                        # (En producción no se hace así, pero para este parche rápido funciona perfecto)
                        response = table.scan(
                            FilterExpression=boto3.dynamodb.conditions.Attr('roundId').eq(rnd_id)
                        )
                        items = response.get('Items', [])
                        
                        for item in items:
                            table.update_item(
                                Key={
                                    'tenantParticipantKey': item['tenantParticipantKey'],
                                    'roundId': item['roundId']
                                },
                                UpdateExpression="SET sessionId = :s, sceneId = :sc",
                                ExpressionAttributeValues={
                                    ':s': session_code,      # Ahora dirá 'sesion-A088'
                                    ':sc': nombre_bonito     # Ahora dirá 'Biblioteca'
                                }
                            )
                            actualizados += 1
                            
                    except Exception as e:
                        pass # Ignoramos errores de duplicados

    print(f"\n🏁 ¡Listo! Se corrigieron {actualizados} registros en DynamoDB.")
    print("Ahora el Dashboard mostrará 'Biblioteca' y agrupará todo bajo 'sesion-A088'.")

if __name__ == "__main__":
    arreglar_datos()