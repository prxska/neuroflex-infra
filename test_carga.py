import boto3
import json
import concurrent.futures

sqs = boto3.client('sqs', region_name='us-east-1')
queue_url = "https://sqs.us-east-1.amazonaws.com/496955374955/nf-sessions-queue"

payload = {
    "contractVersion": "scenes-v1",
    "rounds": [{
        "participantId": "P-CARGA-TEST", 
        "sessionId": "S-LOAD", 
        "roundId": "R-LOAD", 
        "scenarioId": "memory", 
        "status": "completed", 
        "activeTimeMs": 45000, 
        "correctPairAttempts": 4, 
        "incorrectPairAttempts": 1
    }]
}
msg = json.dumps(payload)

def enviar_mensaje(i):
    sqs.send_message(QueueUrl=queue_url, MessageBody=msg)
    return i

print("Iniciando inyección de 1.000 peticiones simultáneas...")
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    for result in executor.map(enviar_mensaje, range(1000)):
        pass
print("¡1.000 peticiones enviadas a SQS en tiempo récord!")