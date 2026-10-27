import boto3
import json

sqs = boto3.client('sqs', region_name='us-east-1')
queue_url = "https://sqs.us-east-1.amazonaws.com/496955374955/nf-sessions-queue"

payload = {
    "contractVersion": "scenes-v1",
    "rounds": [
        {
            "participantId": "P001",
            "sessionId": "VR-SESS-2026-0002",
            "roundId": "r-puzzle-002",
            "scenarioId": "puzzle",
            "status": "completed",
            "activeTimeMs": 30000,
            "correctPlacements": 8,
            "incorrectPlacements": 0,
            "totalPieces": 8
        },
        {
            "participantId": "P001",
            "sessionId": "VR-SESS-2026-0002",
            "roundId": "r-memory-002",
            "scenarioId": "memory",
            "status": "completed",
            "activeTimeMs": 20000,
            "correctPairAttempts": 4,
            "incorrectPairAttempts": 0
        }
    ]
}

response = sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(payload)
)

print(f"Mensaje inyectado con éxito. MessageId: {response['MessageId']}")