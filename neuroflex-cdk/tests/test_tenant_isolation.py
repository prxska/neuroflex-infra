"""Script de prueba de seguridad: Aislamiento Multi-tenant y detección de accesos cruzados."""
import json
import urllib.request
import urllib.error
import boto3

REGION = "us-east-1"
CLIENT_ID = "1eto1qkukfh681a7v9bic56mka"
API_URL = "https://4zh475jp96.execute-api.us-east-1.amazonaws.com/v1"

cognito = boto3.client("cognito-idp", region_name=REGION)


def obtener_token(username, password):
    """Autentica un usuario en Cognito y retorna su AccessToken."""
    try:
        resp = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password}
        )
        return resp["AuthenticationResult"]["AccessToken"]
    except Exception as e:
        print(f"[-] Error autenticando usuario {username}: {e}")
        return None


def probar_acceso(token, endpoint, descripcion):
    """Realiza una petición HTTP GET con el token dado y valida la respuesta."""
    req = urllib.request.Request(
        f"{API_URL}{endpoint}",
        headers={
            "Authorization": token,
            "Content-Type": "application/json"
        },
        method="GET"
    )
    
    print(f"\n[Ejecutando] {descripcion}...")
    try:
        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            body = json.loads(response.read().decode())
            print(f"  --> Resultado: HTTP {status}")
            print(f"  --> Payload recibido: {json.dumps(body, indent=2)}")
            return status, body
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode()
        print(f"  --> Bloqueado correctamente: HTTP {status}")
        print(f"  --> Mensaje de error: {body}")
        return status, body


def main():
    print("=" * 60)
    print("  SUITE DE PRUEBAS DE AISLAMIENTO MULTI-TENANT (LEY 21.719)")
    print("=" * 60)

    # 1. Obtener Token del Especialista habA
    token_habA = obtener_token("especialista@haba.test", "NeuroFlex2026!")
    
    # 2. Obtener Token del Usuario Particular
    token_particular = obtener_token("particular@test.com", "NeuroFlex2026!")

    if token_habA:
        print("\n--- TEST 1: Lectura Legítima dentro del Silo habA ---")
        probar_acceso(
            token_habA,
            "/sessions?participante_id=P001",
            "Especialista habA consulta participante P001 de su propio hospital"
        )

    if token_particular:
        print("\n--- TEST 2: Intento de Acceso Cruzado (Ataque Multi-Tenant) ---")
        status, body = probar_acceso(
            token_particular,
            "/sessions?participante_id=P001",
            "Usuario Particular intenta leer datos del participante P001 de habA"
        )

        items = body.get("items", []) if isinstance(body, dict) else []

        if status in (403, 401) or (status == 200 and len(items) == 0):
            print("\n[SUCCESS] El aislamiento multi-tenant funcionó correctamente.")
            print("          El usuario de 'particulares' no pudo ver los datos del silo 'habA'.")
        else:
            print("\n[CRITICAL FAILURE] Se detectó fuga de datos entre instituciones!")
    else:
        print("\n[-] Omite TEST 2: No se obtuvo token de particular@test.com.")

    print("\n--- TEST 3: Intento con Token Corrupto (Rechazo en Custom Authorizer) ---")
    probar_acceso(
        "Bearer token_invalido_12345",
        "/sessions?participante_id=P001",
        "Petición enviando un token manipulado"
    )


if __name__ == "__main__":
    main()