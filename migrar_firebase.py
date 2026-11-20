import requests
import json

# ==========================================
# CONFIGURACIÓN
# ==========================================
# PEGA EL TOKEN QUE ACABAS DE COPIAR ENTRE LAS COMILLAS
AWS_TOKEN = "eyJraWQiOiJzTk5EMzN1ZWp4bXBpSXNYY3RGMitHRDIwaWdnOUtsa2xmWGkvZEZaN3RRPSIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiI0NGM4NTRiOC1jMGIxLTcwNjUtZGM5YS1jYTFiYTFjNWQ4ZDMiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiYW1yIjpbInB3ZCJdLCJpc3MiOiJodHRwczovL2NvZ25pdG8taWRwLnVzLWVhc3QtMS5hbWF6b25hd3MuY29tL3VzLWVhc3QtMV9rN3cwaGl4ZWMiLCJjb2duaXRvOnVzZXJuYW1lIjoiNDRjODU0YjgtYzBiMS03MDY1LWRjOWEtY2ExYmExYzVkOGQzIiwib3JpZ2luX2p0aSI6Ijk4NzI4MTgwLTcxM2MtNGY3MC1iZmYzLWQyNGY0MGU3MDIzYiIsImF1ZCI6IjQ0ZTgzYTZ2OTA4ZWZjZWw2ZWhsc3R1cDU5IiwiYWNyIjoidXJuOmNvZ25pdG86bG9hOjEiLCJldmVudF9pZCI6IjA4ZTg5NDc0LTYxYmEtNGEyMi1hN2EwLTgwMTlmMzhmMmJkYSIsInRva2VuX3VzZSI6ImlkIiwiYXV0aF90aW1lIjoxNzk1MjA3NTQ5LCJleHAiOjE3OTUyMTExNDksImlhdCI6MTc5NTIwNzU0OSwianRpIjoiYTExYzIzNTktNjg0ZC00YTA0LTgyNWEtZTI2NTBmODE5MmJkIiwiZW1haWwiOiJlcXVpcG8udW5pdHlAbmV1cm9mbGV4LnRlc3QifQ.IHTPjm51H0MKpp3dvrwpRVbHJNEQsIYwxyQE21azfiR6N5peowRM8RHP-dEYwNlWsdjdmStXVKxPsyWIhu8ly_CC6o8PXLdZgjfJtojDXXQvi8SMFYHObGIe-Twd-sng-vK5pHZZ9HSoZfjsOtUioq6iNBxcEW2IQj9atueMKj5j7ACyqDeqtENksYPaLLe32z7fCRZQT7ObwO_xu1HcYoKDeTTi1W_R5Ds_YrgRTCsejOTqrc1dhtLzPetnyDpSKdt0BZcu3bfK0eo5WHPfQiRgBsRI8ZL79d-2uEmdLwBsQqi92-NHel8CDiD7mD-4CgF_pyKR-OFuMfyZCtZElw"

# Limpieza extrema: quita espacios, saltos de línea o retornos de carro
AWS_TOKEN = AWS_TOKEN.strip().replace('\n', '').replace('\r', '').replace('"', '')

AWS_API_URL = "https://ucgkiesz19.execute-api.us-east-1.amazonaws.com/v1/sessions"

# Credenciales de Firebase
FIREBASE_PROJECT_ID = "newroflex"
FIREBASE_API_KEY = "AIzaSyBO14j2DGwb1ukH6WwE0eaZygcSfUZ69v8"

FIREBASE_URL = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/sessions?key={FIREBASE_API_KEY}"

def migrar_datos():
    print("1. Descargando lista de sesiones desde Firestore...")
    response = requests.get(FIREBASE_URL)
    
    if response.status_code != 200:
        print(f"❌ Error al leer Firebase. Código: {response.status_code}")
        print(response.text)
        return

    data = response.json()
    documentos = data.get('documents', [])
    
    if not documentos:
        print("⚠️ No se encontraron sesiones en Firestore.")
        return

    print(f"✅ Se encontraron {len(documentos)} sesiones en Firebase. Iniciando envío a AWS...\n")

    enviados = 0
    for doc in documentos:
        session_id = doc['name'].split('/')[-1]
        print(f"📦 Procesando sesión: {session_id}")

        payload = {
            "contractVersion": "1.0",
            "tenantId": "habA",
            "participantId": f"paciente-{session_id}",
            "rounds": [
                {
                    "roundId": f"{session_id}-ronda-01",
                    "sceneId": "Biblioteca",
                    "difficulty": "Nivel 1",
                    "correctPairAttempts": 4,
                    "totalPieces": 6,
                    "incorrectPlacements": 0,
                    "activeTimeMs": 2100,
                    "puzzleId": "library-level-1",
                    "rotationEnabled": False
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {AWS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        try:
            aws_response = requests.post(AWS_API_URL, headers=headers, json=payload)
            if aws_response.status_code in [200, 201, 202]:
                print(f"   ✅ Enviado a AWS. Status: {aws_response.status_code}")
                enviados += 1
            else:
                print(f"   ❌ Error en AWS ({aws_response.status_code}): {aws_response.text}")
        except Exception as e:
            print(f"   ❌ Error al conectar con AWS: {e}")

    print(f"\n🏁 Migración finalizada. {enviados} paquetes enviados a AWS.")

if __name__ == "__main__":
    migrar_datos()