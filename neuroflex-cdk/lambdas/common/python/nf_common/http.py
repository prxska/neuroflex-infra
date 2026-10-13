"""Respuestas HTTP y manejo uniforme de errores (sin filtrar datos personales a los logs)."""
import json
import logging
from decimal import Decimal

log = logging.getLogger("neuroflex")
log.setLevel(logging.INFO)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(type(o))


def respond(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=_default, ensure_ascii=False),
    }


def json_body(event) -> dict:
    try:
        data = json.loads(event.get("body") or "{}", parse_float=Decimal)
    except json.JSONDecodeError:
        raise ApiError(400, "El cuerpo no es JSON válido")
    if not isinstance(data, dict):
        raise ApiError(400, "Se esperaba un objeto JSON")
    # El tenant nunca se toma del cuerpo de la solicitud.
    data.pop("tenant_id", None)
    return data


def handle(fn):
    """Decorador: convierte ApiError en respuestas y registra solo metadatos."""
    def wrapper(event, context):
        route = f"{event.get('httpMethod')} {event.get('resource')}"
        tenant = ((event.get("requestContext") or {}).get("authorizer") or {}).get("tenant_id")
        try:
            result = fn(event, context)
            log.info(json.dumps({"route": route, "tenant_id": tenant, "status": result["statusCode"]}))
            return result
        except ApiError as e:
            log.info(json.dumps({"route": route, "tenant_id": tenant, "status": e.status}))
            return respond(e.status, {"error": e.message})
        except Exception:  # noqa: BLE001
            log.exception(json.dumps({"route": route, "tenant_id": tenant, "status": 500}))
            return respond(500, {"error": "Error interno"})
    return wrapper
