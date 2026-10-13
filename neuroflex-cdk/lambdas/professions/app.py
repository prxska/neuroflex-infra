"""Ruta /professions: listado de profesionales/especialidades de la organización."""
from nf_common import caller_from_event, handle, require_group, respond, tenant_context


@handle
def handler(event, context):
    caller = caller_from_event(event)
    require_group(caller, "Specialist", "Administrator")
    ctx = tenant_context(caller)
    resp = ctx["tables"]["professions"].scan(Limit=200)
    return respond(200, {"items": resp.get("Items", [])})
