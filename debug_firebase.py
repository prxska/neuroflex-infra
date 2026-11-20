import requests
import boto3
import json
from datetime import datetime

# ==========================================
# CONFIGURACIÓN
# ==========================================
FIREBASE_PROJECT_ID = "newroflex"
FIREBASE_API_KEY = "AIzaSyBO14j2DGwb1ukH6WwE0eaZygcSfUZ69v8"
BASE_FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('nf-scenes-v1-mt')

# Función para obtener documentos
def get_docs(path):
    url = f"{BASE_FIRESTORE_URL}/{path}?key={FIREBASE_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json().get('documents', [])
    return []

def migrar_datos_reales():
    print("1. Buscando sesiones en Firebase...")
    sessions = get_docs("sessions")
    
    if not sessions:
        print("⚠️ No se encontraron sesiones.")
        return

    print(f"✅ {len(sessions)} sesiones encontradas. Iniciando migración profunda...\n")

    enviados = 0
    for session in sessions:
        session_id = session['name'].split('/')[-1]
        
        # Buscar escenas
        scenes = get_docs(f"sessions/{session_id}/scenes")
        
        for scene in scenes:
            scene_id = scene['name'].split('/')[-1]
            
            # Buscar dificultades
            difficulties = get_docs(f"sessions/{session_id}/scenes/{scene_id}/difficulties")
            
            for diff in difficulties:
                diff_id = diff['name'].split('/')[-1]
                
                # Buscar rondas
                rounds = get_docs(f"sessions/{session_id}/scenes/{scene_id}/difficulties/{diff_id}/rounds")
                
                for rnd in rounds:
                    fields = rnd.get('fields', {})
                    metrics_json_field = fields.get('metrics_json', {}).get('stringValue')
                    
                    if not metrics_json_field:
                        continue # Si no hay métricas, saltamos esta ronda

                    # Convertimos el texto JSON en un diccionario real
                    metrics_data = json.loads(metrics_json_field)
                    
                    # La ronda real está dentro de request -> rounds -> [0]
                    round_info = metrics_data.get('request', {}).get('rounds', [{}])[0]

                    # Extraemos los datos verdaderos
                    participant_id = round_info.get('participantId', 'desconocido')
                    round_id = round_info.get('roundId', rnd['name'].split('/')[-1])
                    scenario_id = round_info.get('scenarioId', scene_id)
                    difficulty_lvl = round_info.get('difficultyLevel', diff_id)
                    
                    response_time = round_info.get('responseTimeMs', 0)
                    actual_pieces = round_info.get('actualPigeonCount', 0)
                    user_pieces = round_info.get('userPigeonCount', 0)
                    status = round_info.get('status', 'unknown')

                    # Armar el item para DynamoDB
                    item = {
                        'tenantParticipantKey': f"habA#{participant_id}",
                        'roundId': round_id,
                        'sceneId': scenario_id,
                        'difficulty': str(difficulty_lvl),
                        'activeTimeMs': int(response_time),
                        'totalPieces': int(actual_pieces),
                        'correctPairAttempts': int(user_pieces),
                        'status': status,
                        'migratedFrom': 'Firebase-JSON',
                        'migrationDate': datetime.now().isoformat()
                    }

                    try:
                        table.put_item(Item=item)
                        enviados += 1
                        print(f"   ✅ {scenario_id} | Ronda: {round_id[:8]}... | Tiempo: {response_time}ms | Aciertos: {user_pieces}/{actual_pieces}")
                    except Exception as e:
                        print(f"   ❌ Error en DynamoDB para ronda {round_id}: {e}")

    print(f"\n🏁 Migración finalizada. {enviados} RONDAS REALES inyectadas en DynamoDB.")

if __name__ == "__main__":
    migrar_datos_reales()