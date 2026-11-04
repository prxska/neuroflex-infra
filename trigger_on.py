#Encender el trigger

import boto3

def reparar_trigger():
    client = boto3.client('lambda', region_name='us-east-1')
    try:
        mappings = client.list_event_source_mappings(FunctionName='nf-sessions-worker')
        for m in mappings['EventSourceMappings']:
            if m['State'] == 'Disabled':
                print(f"Trigger apagado detectado. Encendiendo...")
                client.update_event_source_mapping(UUID=m['UUID'], Enabled=True)
                print("✅ Trigger encendido con éxito.")
            else:
                print("✅ El trigger ya está encendido.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reparar_trigger()