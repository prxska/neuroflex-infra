import boto3
import json

sqs = boto3.client('sqs', region_name='us-east-1')

# Buscamos la URL dinámicamente para que nunca falle
try:
    response = sqs.get_queue_url(QueueName='nf-sessions-queue')
    queue_url = response['QueueUrl']
    print(f"Conectado a la cola: {queue_url}")
except Exception as e:
    print(f"Error al buscar la cola: {e}")
    exit(1)

def build_payload(tenant_id, aciertos):
    return {
        "contractVersion": "scenes-v1",
        "tenantId": tenant_id,
        "rounds": [{
            "participantId": "P001",
            "sessionId": f"S-{tenant_id}-01",
            "roundId": "r-memory-001",
            "scenarioId": "memory",
            "status": "completed",
            "activeTimeMs": 45000,
            "correctPairAttempts": aciertos, 
            "incorrectPairAttempts": 1
        }]
    }

try:
    # 1. Clínica A (habaA)
    payload_a = build_payload("habaA", 4)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload_a))
    print("✅ Mensaje inyectado para Clínica A (habaA) - Precisión esperada: 80%")

    # 2. Clínica B (clinicaB)
    payload_b = build_payload("clinicaB", 1)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload_b))
    print("✅ Mensaje inyectado para Clínica B (clinicaB) - Precisión esperada: 50%")

except Exception as e:
    print(f"❌ Error al enviar mensaje: {e}")