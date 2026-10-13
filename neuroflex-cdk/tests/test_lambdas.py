"""Pruebas de lógica de las Lambdas (sin AWS)."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name, env=None):
    os.environ.update(env or {})
    spec = importlib.util.spec_from_file_location(
        f"fn_{name}", ROOT / "lambdas" / name / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def export():
    mod = load("analytics_export", {
        "ANALYTICS_BUCKET": "b", "ANALYTICS_KMS_KEY_ARN": "k", "HMAC_KEY_ID": "h",
        "EXPERIENCIAS": "neuroflex,deportistas"})
    mod.pseudonym = lambda v: "P_" + str(abs(hash(v)))
    return mod


def sesion(**kw):
    base = {"tenant_id": "habA", "participante_id": "pac-001", "sesion_id": "s-123456789",
            "experiencia": "neuroflex", "inicio": "2027-03-11T10:00:00+00:00",
            "duracion_seg": 900, "metricas": {"aciertos": 12, "tiempo_reaccion_ms": 540},
            "alias": "Juan P.", "registrado_por": "sub-esp", "consentimiento_investigacion": True,
            "tramo_edad": "60-74", "tipo_cliente": "organizacion", "version_app": "1.0"}
    base.update(kw)
    return base


def test_sin_consentimiento_no_se_exporta(export):
    assert export.deidentify(sesion(consentimiento_investigacion=False)) is None


def test_quita_identificadores_y_generaliza_fecha(export):
    row = export.deidentify(sesion())
    texto = json.dumps(row)
    for dato in ("pac-001", "Juan", "sub-esp", "habA", "s-123456789"):
        assert dato not in texto
    assert row["_semana"] == "2027-03-08"  # lunes de esa semana
    assert row["metricas"] == {"aciertos": 12.0, "tiempo_reaccion_ms": 540.0}


def test_experiencia_desconocida_se_descarta(export):
    assert export.deidentify(sesion(experiencia="otra")) is None


def test_tenant_del_cuerpo_se_ignora():
    from nf_common.http import json_body
    body = json_body({"body": json.dumps({"tenant_id": "habB", "x": 1})})
    assert "tenant_id" not in body


def test_contexto_del_autorizador():
    from nf_common.tenant import caller_from_event
    c = caller_from_event({"requestContext": {"authorizer": {
        "tenant_id": "habA", "sub": "u1", "groups": "Specialist,Administrator"}}})
    assert c.tenant_id == "habA" and c.groups == {"Specialist", "Administrator"}
    with pytest.raises(Exception):
        caller_from_event({"requestContext": {}})


def test_politica_del_autorizador_cubre_toda_la_api():
    mod = load("authorizer", {"USER_POOL_ID": "us-east-1_X", "APP_CLIENT_IDS": "c1",
                              "TENANTS_TABLE": "nf-tenants"})
    p = mod._policy("Allow", "arn:aws:execute-api:us-east-1:111:abc/v1/GET/sessions", "u1",
                    {"tenant_id": "habA"})
    assert p["policyDocument"]["Statement"][0]["Resource"] == \
        "arn:aws:execute-api:us-east-1:111:abc/v1/*/*"
    assert p["context"]["tenant_id"] == "habA"
