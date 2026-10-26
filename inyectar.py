import boto3
import json

# Usa la URL de SQS que te arrojó el output de tu despliegue anterior
SQS_URL = "https://sqs.us-east-1.amazonaws.com/496955374955/nf-sessions-queue"

sqs = boto3.client('sqs', region_name='us-east-1')

with open('test_payload.json', 'r') as f:
    payload = f.read()

response = sqs.send_message(
    QueueUrl=SQS_URL,
    MessageBody=payload
)

print(f"Mensaje inyectado. MessageId: {response['MessageId']}")