import boto3
import json
import uuid

sqs = boto3.client('sqs', region_name='us-east-1')
queue_url = "https://sqs.us-east-1.amazonaws.com/058264412508/nf-sessions-queue"

session_id = f"VR-FULL-IA-{str(uuid.uuid4())[:6].upper()}"

# Payload con TODOS los campos obligatorios del contrato
payload = {
    "contractVersion": "scenes-v1",
    "tenantId": "habaA",
    "rounds": [
        {
            "participantId": "P001",
            "sessionId": session_id,
            "roundId": f"r-memory-{str(uuid.uuid4())[:4]}",
            "scenarioId": "memory",
            "difficultyLevel": 1,
            "startedAt": "2026-11-03T14:05:00.000Z",
            "endedAt": "2026-11-03T14:06:00.000Z",
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
            "totalCards": 8,
            "totalPairs": 4,
            "correctPairAttempts": 4,
            "incorrectPairAttempts": 1,
            "pairsFound": 4,
            "activeTimeMs": 45000,
            "aidsUsed": 0,
            "previewDurationMs": 5000,
            "deckId": "deck-b"
        }
    ]
}

try:
    res = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    print(f"🚀 Sesión perfecta enviada. ID: {session_id}")
except Exception as e:
    print(f"❌ Error: {e}")