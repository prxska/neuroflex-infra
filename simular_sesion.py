import boto3
import json

sqs = boto3.client('sqs', region_name='us-east-1')
# Usamos la URL de tu nueva cuenta
queue_url = "https://sqs.us-east-1.amazonaws.com/058264412508/nf-sessions-queue"

# Payload completo con todos los campos que pide el contrato scenes-v1
payload = {
    "contractVersion": "scenes-v1",
    "tenantId": "habaA",
    "rounds": [
        {
            "participantId": "P001",
            "sessionId": "S-PUZZLE-NUEVO",
            "roundId": "r-puzzle-99",
            "scenarioId": "puzzle",
            "difficultyLevel": 1,
            "startedAt": "2026-11-02T14:00:00.000Z",
            "endedAt": "2026-11-02T14:01:05.000Z",
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
            "totalPieces": 8,
            "correctPlacements": 8,
            "incorrectPlacements": 1,
            "aidsUsed": 0,
            "activeTimeMs": 35000,
            "puzzleId": "puzzle-a",
            "rotationEnabled": False
        }
    ]
}

try:
    response = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    print(f"✅ Mensaje enviado exitosamente. MessageId: {response['MessageId']}")
except Exception as e:
    print(f"❌ Error al enviar: {e}")