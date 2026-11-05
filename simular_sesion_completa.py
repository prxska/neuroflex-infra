import boto3
import json
import uuid
from datetime import datetime, timedelta

sqs = boto3.client('sqs', region_name='us-east-1')
queue_url = "https://sqs.us-east-1.amazonaws.com/058264412508/nf-sessions-queue"

session_id = f"VR-COMPLETA-{str(uuid.uuid4())[:6].upper()}"
now = datetime.utcnow()

def get_iso(offset_seconds):
    return (now + timedelta(seconds=offset_seconds)).isoformat() + "Z"

payload = {
    "contractVersion": "scenes-v1",
    "tenantId": "habaA",
    "rounds": [
        # 1. Escena de Puzzle (Rápido y perfecto)
        {
            "participantId": "P001",
            "sessionId": session_id,
            "roundId": f"puz-{str(uuid.uuid4())[:4]}",
            "scenarioId": "puzzle",
            "difficultyLevel": 2,
            "startedAt": get_iso(0),
            "endedAt": get_iso(40),
            "status": "completed",
            "pausedDurationMs": 0,
            "scenarioVersion": "1.0.0",
            "assessmentMode": "comparison",
            "distractionsEnabled": False,
            "distractionType": "none",
            "distractionCount": 0,
            "distractionIntensity": "none",
            "distractionDurationMs": 0,
            "comparisonGroupId": None,
            "totalPieces": 12,
            "correctPlacements": 12,
            "incorrectPlacements": 1,
            "aidsUsed": 0,
            "activeTimeMs": 40000,
            "puzzleId": "puzzle-c",
            "rotationEnabled": True
        },
        # 2. Escena de Memoria (Le costó un poco, 60% precisión)
        {
            "participantId": "P001",
            "sessionId": session_id,
            "roundId": f"mem-{str(uuid.uuid4())[:4]}",
            "scenarioId": "memory",
            "difficultyLevel": 1,
            "startedAt": get_iso(60),
            "endedAt": get_iso(120),
            "status": "completed",
            "pausedDurationMs": 0,
            "scenarioVersion": "1.0.0",
            "assessmentMode": "comparison",
            "distractionsEnabled": True,
            "distractionType": "visual",
            "distractionCount": 3,
            "distractionIntensity": "medium",
            "distractionDurationMs": 5000,
            "comparisonGroupId": None,
            "totalCards": 10,
            "totalPairs": 5,
            "correctPairAttempts": 3,
            "incorrectPairAttempts": 2,
            "pairsFound": 5,
            "activeTimeMs": 60000,
            "aidsUsed": 1,
            "previewDurationMs": 5000,
            "deckId": "deck-c"
        },
        # 3. Escena de Palomas (Tiempo de reacción rápido y error de -1)
        {
            "participantId": "P001",
            "sessionId": session_id,
            "roundId": f"pig-{str(uuid.uuid4())[:4]}",
            "scenarioId": "pigeons",
            "difficultyLevel": 1,
            "startedAt": get_iso(150),
            "endedAt": get_iso(165),
            "status": "completed",
            "pausedDurationMs": 0,
            "scenarioVersion": "1.0.0",
            "assessmentMode": "comparison",
            "distractionsEnabled": False,
            "distractionType": "none",
            "distractionCount": 0,
            "distractionIntensity": "none",
            "distractionDurationMs": 0,
            "comparisonGroupId": None,
            "actualPigeonCount": 7,
            "userPigeonCount": 6,
            "displayDurationMs": 3000,
            "responseTimeMs": 2500,
            "pigeonsHiddenAt": get_iso(153),
            "answerEnabledAt": get_iso(155),
            "answerSubmittedAt": get_iso(157.5), # 4.5 segundos después de ocultarse
            "movementLevel": "low",
            "retentionDelayMs": 2000
        }
    ]
}

try:
    res = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    print(f"🚀 Sesión COMPLETA enviada. ID: {session_id}")
    print("Espera 10 segundos y revisa Colab para ver cómo la IA procesa las 3 escenas.")
except Exception as e:
    print(f"❌ Error: {e}")