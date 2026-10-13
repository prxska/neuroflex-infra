"""Pre Token Generation (V2_0): copia custom:tenant_id al token de acceso como 'tenant_id'."""


def handler(event, context):
    tenant = event["request"]["userAttributes"].get("custom:tenant_id")
    if not tenant:
        # Sin tenant_id el usuario no podrá usar la API (el autorizador lo rechazará).
        return event
    event["response"] = {
        "claimsAndScopeOverrideDetails": {
            "accessTokenGeneration": {"claimsToAddOrOverride": {"tenant_id": tenant}},
            "idTokenGeneration": {"claimsToAddOrOverride": {"tenant_id": tenant}},
        }
    }
    return event
