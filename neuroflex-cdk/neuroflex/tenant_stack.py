"""Fase 4: silo de datos de un hospital (o del espacio de particulares).

Crea, para un tenant_id:
- Clave KMS propia con rotación.
- Tablas sessions, users y professions cifradas con esa clave.
- Bucket S3 de métricas cifrado con esa clave.
- Rol nf-tenant-<id> que solo puede usar estos recursos y que solo puede
  asumir el rol de las Lambdas compartidas.
- Registro del hospital en la tabla nf-tenants.
- (Si la analítica está configurada) conexión del stream de sesiones con
  la Lambda de exportación de-identificada.
"""
import json

from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import custom_resources as cr
from constructs import Construct

from .settings import (EXPORT_FUNCTION, EXPORT_ROLE, SHARED_LAMBDA_ROLE, TENANTS_TABLE,
                       Settings, tenant_names)


class TenantStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings,
                 tenant: dict, **kwargs):
        super().__init__(scope, cid, **kwargs)
        tid = tenant["id"]
        names = tenant_names(tid, self.account)
        Tags.of(self).add("nf:tenant", tid)
        Tags.of(self).add("nf:tipo_cliente", tenant["tipo_cliente"])

        shared_role_arn = f"arn:aws:iam::{self.account}:role/{SHARED_LAMBDA_ROLE}"
        export_role_arn = f"arn:aws:iam::{self.account}:role/{EXPORT_ROLE}"

        # ---------- Clave propia del hospital ----------
        key = kms.Key(
            self, "TenantKey",
            alias=names["key_alias"],
            description=f"Clave de datos de {tenant['nombre']} ({tid})",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ---------- Tablas ----------
        def table(logical: str, name: str, pk: str, sk: str | None = None,
                  stream: bool = False) -> ddb.Table:
            return ddb.Table(
                self, logical,
                table_name=name,
                partition_key=ddb.Attribute(name=pk, type=ddb.AttributeType.STRING),
                sort_key=ddb.Attribute(name=sk, type=ddb.AttributeType.STRING) if sk else None,
                billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
                encryption=ddb.TableEncryption.CUSTOMER_MANAGED,
                encryption_key=key,
                point_in_time_recovery_specification=ddb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True),
                stream=ddb.StreamViewType.NEW_IMAGE if stream else None,
                deletion_protection=True,
                removal_policy=RemovalPolicy.RETAIN,
            )

        sessions = table("SessionsTable", names["sessions"], "participante_id",
                         "sesion_id", stream=True)
        users = table("UsersTable", names["users"], "participante_id")
        professions = table("ProfessionsTable", names["professions"], "profession_id")

        # ---------- Bucket de métricas ----------
        bucket = s3.Bucket(
            self, "MetricsBucket",
            bucket_name=names["bucket"],
            encryption=s3.BucketEncryption.KMS,
            encryption_key=key,
            bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ---------- Rol del hospital ----------
        tenant_role = iam.Role(
            self, "TenantRole",
            role_name=names["role"],
            description=f"Acceso limitado a los datos de {tid}",
            # Solo el rol de las Lambdas compartidas puede asumirlo (con etiquetas de sesión).
            assumed_by=iam.SessionTagsPrincipal(iam.ArnPrincipal(shared_role_arn)),
        )
        tenant_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                     "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:BatchGetItem"],
            resources=[t.table_arn for t in (sessions, users, professions)],
        ))
        tenant_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject"],
            resources=[bucket.arn_for_objects("*")],
        ))
        key.grant_encrypt_decrypt(tenant_role)

        # ---------- Registro en nf-tenants ----------
        item = {
            "tenant_id": {"S": tid},
            "nombre": {"S": tenant["nombre"]},
            "estado": {"S": tenant.get("estado", "activo")},
            "tipo_cliente": {"S": tenant["tipo_cliente"]},
            "rol_arn": {"S": tenant_role.role_arn},
            "tablas": {"M": {
                "sessions": {"S": sessions.table_name},
                "users": {"S": users.table_name},
                "professions": {"S": professions.table_name},
            }},
            "bucket": {"S": bucket.bucket_name},
            "kms_key_arn": {"S": key.key_arn},
        }
        put_call = cr.AwsSdkCall(
            service="DynamoDB",
            action="putItem",
            parameters={"TableName": TENANTS_TABLE, "Item": item},
            physical_resource_id=cr.PhysicalResourceId.of(f"nf-tenant-{tid}"),
        )
        tenants_table_arn = (f"arn:aws:dynamodb:{self.region}:{self.account}"
                             f":table/{TENANTS_TABLE}")
        cr.AwsCustomResource(
            self, "RegisterTenant",
            on_create=put_call,
            on_update=put_call,
            # Al eliminar la pila, el hospital queda suspendido (no se borra el registro).
            on_delete=cr.AwsSdkCall(
                service="DynamoDB",
                action="updateItem",
                parameters={
                    "TableName": TENANTS_TABLE,
                    "Key": {"tenant_id": {"S": tid}},
                    "UpdateExpression": "SET estado = :s",
                    "ExpressionAttributeValues": {":s": {"S": "suspendido"}},
                },
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([iam.PolicyStatement(
                actions=["dynamodb:PutItem", "dynamodb:UpdateItem"],
                resources=[tenants_table_arn],
            )]),
            install_latest_aws_sdk=False,
        )

        # ---------- Conexión con la analítica de-identificada ----------
        if settings.analytics_enabled:
            export_fn = lambda_.Function.from_function_arn(
                self, "ExportFn",
                f"arn:aws:lambda:{self.region}:{self.account}:function:{EXPORT_FUNCTION}",
            )
            # La Lambda de exportación necesita descifrar el stream de este hospital.
            key.add_to_resource_policy(iam.PolicyStatement(
                actions=["kms:Decrypt"],
                principals=[iam.AccountRootPrincipal()],
                resources=["*"],
                conditions={"ArnEquals": {"aws:PrincipalArn": export_role_arn}},
            ))
            lambda_.EventSourceMapping(
                self, "SessionsStreamToExport",
                target=export_fn,
                event_source_arn=sessions.table_stream_arn,
                starting_position=lambda_.StartingPosition.TRIM_HORIZON,
                batch_size=100,
                retry_attempts=3,
                bisect_batch_on_error=True,
                report_batch_item_failures=True,
                filters=[lambda_.FilterCriteria.filter({
                    "eventName": lambda_.FilterRule.or_("INSERT", "MODIFY"),
                })],
            )

        CfnOutput(self, "TenantRoleArn", value=tenant_role.role_arn)
        CfnOutput(self, "MetricsBucketName", value=bucket.bucket_name)
        CfnOutput(self, "TenantConfig", value=json.dumps({"tenant_id": tid}))
