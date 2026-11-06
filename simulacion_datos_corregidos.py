import boto3
import json
import uuid
from datetime import datetime, timedelta

sqs = boto3.client('sqs', region_name='us-east-1')
queue_url = "https://sqs.us-east-1.amazonaws.com/058264412508/nf-sessions-queue"

session_id = f"VR-MEM-PERFECTA-{str(uuid.uuid4())[:6].upper()}"
now = datetime.utcnow()

def get_iso(offset_seconds):
    return (now + timedelta(seconds=offset_seconds)).isoformat() + "Z"

payload = {
    "contractVersion": "scenes-v1",
    "tenantId": "habaA",
    "rounds": [
        {
            "participantId": "P001",
            "sessionId": session_id,
            "roundId": f"mem-{str(uuid.uuid4())[:4]}",
            "scenarioId": "memory",
            "difficultyLevel": 1,
            "startedAt": get_iso(0),
            "endedAt": get_iso(60),
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
            "correctPairAttempts": 5,    # 5 aciertos
            "incorrectPairAttempts": 2,  # 2 errores
            "pairsFound": 5,             # Coincide con aciertos
            "activeTimeMs": 60000,
            "aidsUsed": 1,
            "previewDurationMs": 5000,
            "deckId": "deck-c"
        }
    ]
}

try:
    res = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    print(f"🚀 Sesión de Memoria PERFECTA enviada. ID: {session_id}")
except Exception as e:
    print(f"❌ Error: {e}")