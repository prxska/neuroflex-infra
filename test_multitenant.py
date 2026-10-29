import boto3
import json

sqs = boto3.client('sqs', region_name='us-east-1')
queue_url = "https://sqs.us-east-1.amazonaws.com/496955374955/nf-sessions-queue"

def build_payload(tenant_id, aciertos):
    return {
        "contractVersion": "scenes-v1",
        "tenantId": tenant_id,  # <--- AQUI INYECTAMOS EL TENANT
        "rounds": [{
            "participantId": "P001", # Mismo paciente para ambas clínicas
            "sessionId": f"S-{tenant_id}-01",
            "roundId": "r-memory-001",
            "scenarioId": "memory",
            "status": "completed",
            "activeTimeMs": 45000,
            "correctPairAttempts": aciertos, 
            "incorrectPairAttempts": 1
        }]
    }

# 1. Clínica A (habaA): 4 aciertos, 1 error = 80% de precisión
payload_a = build_payload("habaA", 4)
sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload_a))
print("Mensaje inyectado para Clínica A (habaA) - Precisión esperada: 80%")

# 2. Clínica B (clinicaB): 1 acierto, 1 error = 50% de precisión
payload_b = build_payload("clinicaB", 1)
sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload_b))
print("Mensaje inyectado para Clínica B (clinicaB) - Precisión esperada: 50%")