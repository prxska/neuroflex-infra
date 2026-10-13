"""Pruebas de la infraestructura: aislamiento entre hospitales y protecciones básicas."""
import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from neuroflex.auth_stack import AuthStack
from neuroflex.core_stack import CoreStack
from neuroflex.settings import Settings
from neuroflex.tenant_stack import TenantStack

ENV = cdk.Environment(account="111111111111", region="us-east-1")


def settings(analytics=False):
    return Settings(
        region="us-east-1", system_account="111111111111", analytics_account="222222222222",
        cognito_domain_prefix="nf-test", dashboard_callback_urls=["http://localhost:8765/callback"],
        analytics_bucket_name="nf-analytics-222222222222" if analytics else "",
        analytics_key_arn="arn:aws:kms:us-east-1:222222222222:key/x" if analytics else "",
        breakglass_principal_arns=[], alert_email="", experiencias=["neuroflex"],
        terms_version="1", tenants=[])


@pytest.fixture(scope="module")
def tenant_template():
    app = cdk.App()
    st = TenantStack(app, "T", settings=settings(analytics=True), env=ENV,
                     tenant={"id": "habA", "nombre": "Hospital A",
                             "tipo_cliente": "organizacion", "estado": "activo"})
    return Template.from_stack(st)


def test_tablas_cifradas_con_clave_propia_y_protegidas(tenant_template):
    tenant_template.resource_count_is("AWS::DynamoDB::Table", 3)
    tenant_template.all_resources_properties("AWS::DynamoDB::Table", {
        "SSESpecification": {"SSEEnabled": True, "SSEType": "KMS",
                             "KMSMasterKeyId": Match.any_value()},
        "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        "DeletionProtectionEnabled": True,
    })


def test_bucket_privado_y_cifrado(tenant_template):
    tenant_template.has_resource_properties("AWS::S3::Bucket", {
        "BucketName": "nf-haba-metrics-111111111111",
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
    })


def test_rol_del_hospital_solo_asumible_por_lambdas_compartidas(tenant_template):
    roles = tenant_template.find_resources("AWS::IAM::Role", {
        "Properties": {"RoleName": "nf-tenant-habA"}})
    (role,) = roles.values()
    principals = json.dumps(role["Properties"]["AssumeRolePolicyDocument"])
    assert "role/nf-shared-lambda-role" in principals
    assert "lambda.amazonaws.com" not in principals


def test_politica_del_hospital_no_menciona_otros_hospitales(tenant_template):
    policies = tenant_template.find_resources("AWS::IAM::Policy")
    texto = json.dumps(policies)
    assert "habB" not in texto and "nf-*" not in texto
    stmts = [s for p in policies.values()
             for s in p["Properties"]["PolicyDocument"]["Statement"]
             if any(a.startswith("dynamodb:") for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]]))]
    assert stmts, "el rol debe tener acceso a sus tablas"
    for s in stmts:
        assert "*" not in json.dumps(s["Resource"]).replace('"Fn::', '')


def test_registro_en_tabla_tenants(tenant_template):
    (cr,) = tenant_template.find_resources("Custom::AWS").values()
    create = json.dumps(cr["Properties"]["Create"])
    assert "putItem" in create and "nf-tenants" in create and "habA" in create
    assert "suspendido" in cr["Properties"]["Delete"]  # al borrar la pila se suspende


def test_stream_conectado_a_exportacion(tenant_template):
    tenant_template.has_resource_properties("AWS::Lambda::EventSourceMapping", {
        "FunctionName": Match.string_like_regexp("nf-analytics-export"),
    })


@pytest.fixture(scope="module")
def core_and_auth():
    app = cdk.App()
    s = settings()
    auth = AuthStack(app, "A", settings=s, env=ENV)
    core = CoreStack(app, "C", settings=s, user_pool_id=auth.user_pool.user_pool_id,
                     app_client_ids=[auth.vr_client.user_pool_client_id], env=ENV)
    return Template.from_stack(auth), Template.from_stack(core)


def test_tenant_id_no_escribible_por_clientes(core_and_auth):
    auth, _ = core_and_auth
    clients = auth.find_resources("AWS::Cognito::UserPoolClient")
    assert len(clients) == 2
    for c in clients.values():
        assert "custom:tenant_id" not in c["Properties"]["WriteAttributes"]
        assert "custom:tenant_id" in c["Properties"]["ReadAttributes"]


def test_pre_token_v2(core_and_auth):
    auth, _ = core_and_auth
    auth.has_resource_properties("AWS::Cognito::UserPool", {
        "UserPoolTier": "ESSENTIALS",
        "LambdaConfig": {"PreTokenGenerationConfig": {"LambdaVersion": "V2_0"}},
    })


def test_rol_compartido_sin_acceso_directo_a_datos(core_and_auth):
    _, core = core_and_auth
    policies = core.find_resources("AWS::IAM::Policy", {
        "Properties": {"Roles": [{"Ref": Match.string_like_regexp("SharedLambdaRole")}]}})
    texto = json.dumps(policies)
    assert "sts:AssumeRole" in texto
    assert "role/nf-tenant-*" in texto
    assert "dynamodb:PutItem" not in texto  # solo lectura de nf-tenants


def test_todas_las_rutas_requieren_autorizador(core_and_auth):
    _, core = core_and_auth
    methods = core.find_resources("AWS::ApiGateway::Method")
    for m in methods.values():
        if m["Properties"]["HttpMethod"] != "OPTIONS":
            assert m["Properties"]["AuthorizationType"] == "CUSTOM"
