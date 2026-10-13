"""Lambda Authorizer (tipo TOKEN) para la API NeuroFlex.

Valida el token de acceso de Cognito y entrega tenant_id, sub y grupos a las Lambdas.
La política devuelta cubre toda la API, porque el resultado queda en caché 5 minutos.
"""
import os

import boto3
import jwt  # PyJWT, capa nf-deps

REGION = os.environ.get("AWS_REGION", "us-east-1")
USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_IDS = set(os.environ["APP_CLIENT_IDS"].split(","))
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"

_jwks = jwt.PyJWKClient(f"{ISSUER}/.well-known/jwks.json", cache_keys=True, lifespan=3600)
_tenants = boto3.resource("dynamodb").Table(os.environ["TENANTS_TABLE"])


def _policy(effect: str, method_arn: str, principal: str = "anon", context=None) -> dict:
    # arn:aws:execute-api:region:account:apiId/stage/METHOD/path -> apiId/stage/*/*
    parts = method_arn.split(":")
    api_stage = "/".join(parts[5].split("/")[:2])
    resource = ":".join(parts[:5] + [f"{api_stage}/*/*"])
    out = {
        "principalId": principal,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{"Action": "execute-api:Invoke", "Effect": effect,
                           "Resource": resource}],
        },
    }
    if context:
        out["context"] = context
    return out


def handler(event, context):
    token = (event.get("authorizationToken") or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise Exception("Unauthorized")  # API Gateway responde 401

    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=ISSUER,
                            options={"require": ["exp", "iss", "sub", "token_use"]})
    except jwt.PyJWTError:
        raise Exception("Unauthorized")

    if claims.get("token_use") != "access" or claims.get("client_id") not in CLIENT_IDS:
        raise Exception("Unauthorized")

    tenant_id = claims.get("tenant_id")
    if not tenant_id:
        return _policy("Deny", event["methodArn"], claims["sub"])

    item = _tenants.get_item(Key={"tenant_id": tenant_id},
                             ProjectionExpression="estado, tipo_cliente").get("Item")
    if not item or item.get("estado") != "activo":
        return _policy("Deny", event["methodArn"], claims["sub"])

    return _policy("Allow", event["methodArn"], claims["sub"], {
        "tenant_id": tenant_id,
        "sub": claims["sub"],
        "groups": ",".join(claims.get("cognito:groups", [])),
        "tipo_cliente": item.get("tipo_cliente", "organizacion"),
    })
