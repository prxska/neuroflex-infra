import requests
import boto3
import json
import time
from datetime import datetime

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
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"      ⚠️ Error {res.status_code} en {path}: {res.text[:100]}")
            return []
        return res.json().get('documents', [])
    except Exception as e:
        print(f"      ❌ Excepción obteniendo {path}: {e}")
        return []

def migrar_datos_reales():
    print("1. Buscando sesiones en Firebase...")
    sessions = get_docs("sessions")
    
    if not sessions:
        print("⚠️ No se encontraron sesiones.")
        return

    print(f"✅ {len(sessions)} sesiones encontradas. Iniciando migración...\n")

    enviados = 0
    for session in sessions:
        session_id = session['name'].split('/')[-1]
        print(f"📦 Procesando sesión: {session_id}")
        
        # Buscamos escenas
        scenes = get_docs(f"sessions/{session_id}/scenes")
        print(f"   Escenas encontradas: {len(scenes)}")
        
        for scene in scenes:
            scene_id = scene['name'].split('/')[-1]
            print(f"      🔍 Analizando escena: {scene_id}")
            
            # Buscamos dificultades
            difficulties = get_docs(f"sessions/{session_id}/scenes/{scene_id}/difficulties")
            print(f"         Dificultades encontradas: {len(difficulties)}")
            
            for diff in difficulties:
                diff_id = diff['name'].split('/')[-1]
                
                # Buscamos rondas
                rounds = get_docs(f"sessions/{session_id}/scenes/{scene_id}/difficulties/{diff_id}/rounds")
                print(f"            Rondas encontradas: {len(rounds)}")
                
                for rnd in rounds:
                    fields = rnd.get('fields', {})
                    metrics_json_field = fields.get('metrics_json', {}).get('stringValue')
                    
                    if not metrics_json_field:
                        print(f"               ⚠️ Ronda sin metrics_json: {rnd['name'].split('/')[-1]}")
                        continue 

                    metrics_data = json.loads(metrics_json_field)
                    round_info = metrics_data.get('request', {}).get('rounds', [{}])[0]

                    participant_id = round_info.get('participantId', 'desconocido')
                    round_id = round_info.get('roundId', rnd['name'].split('/')[-1])
                    scenario_id = round_info.get('scenarioId', scene_id)
                    difficulty_lvl = round_info.get('difficultyLevel', diff_id)
                    
                    response_time = round_info.get('responseTimeMs')
                    response_time = int(response_time) if response_time is not None else 0
                    
                    actual_pieces = round_info.get('actualPigeonCount')
                    actual_pieces = int(actual_pieces) if actual_pieces is not None else 0
                    
                    user_pieces = round_info.get('userPigeonCount')
                    user_pieces = int(user_pieces) if user_pieces is not None else 0

                    item = {
                        'tenantParticipantKey': f"habA#{participant_id}",
                        'roundId': round_id,
                        'sceneId': scenario_id,
                        'difficulty': str(difficulty_lvl),
                        'activeTimeMs': response_time,
                        'totalPieces': actual_pieces,
                        'correctPairAttempts': user_pieces,
                        'status': round_info.get('status', 'unknown'),
                        'migratedFrom': 'Firebase-JSON',
                        'migrationDate': datetime.now().isoformat()
                    }

                    try:
                        table.put_item(Item=item)
                        enviados += 1
                        print(f"               ✅ Guardada ronda: Tiempo {response_time}ms | Aciertos: {user_pieces}/{actual_pieces}")
                    except Exception as e:
                        print(f"               ❌ Error en DynamoDB: {e}")
                
                # Pequeña pausa para no saturar la API de Firebase
                time.sleep(0.5)

    print(f"\n🏁 Migración finalizada. {enviados} RONDAS REALES inyectadas en DynamoDB.")

if __name__ == "__main__":
    migrar_datos_reales()