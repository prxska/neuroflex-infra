"""Fase 7 (cuenta de analítica del proveedor): bucket, catálogo y Athena.

Se despliega en la cuenta qualialab-analitica. Usa proyección de particiones,
por lo que no requiere crawlers ni trabajos de Glue ETL.
"""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_athena as athena
from aws_cdk import aws_glue as glue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .settings import EXPORT_ROLE, Settings

GLUE_DB = "nf_analytics"


class AnalyticsStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings, **kwargs):
        super().__init__(scope, cid, **kwargs)
        export_role_arn = f"arn:aws:iam::{settings.system_account}:role/{EXPORT_ROLE}"
        system_root = iam.AccountPrincipal(settings.system_account)

        key = kms.Key(
            self, "AnalyticsKey",
            alias="alias/nf-analytics",
            description="Cifrado de datos de-identificados de NeuroFlex",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        # Se usa la cuenta como principal + condición sobre el rol exacto, para que la
        # política sea válida aunque el rol aún no exista en la cuenta del sistema.
        key.add_to_resource_policy(iam.PolicyStatement(
            actions=["kms:GenerateDataKey", "kms:Encrypt"],
            principals=[system_root],
            resources=["*"],
            conditions={"ArnEquals": {"aws:PrincipalArn": export_role_arn}},
        ))

        bucket = s3.Bucket(
            self, "AnalyticsBucket",
            bucket_name=f"nf-analytics-{self.account}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=key,
            bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.RETAIN,
        )
        bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            principals=[system_root],
            resources=[bucket.arn_for_objects("sessions/*")],
            conditions={"ArnEquals": {"aws:PrincipalArn": export_role_arn}},
        ))

        results = s3.Bucket(
            self, "AthenaResults",
            bucket_name=f"nf-athena-results-{self.account}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=key,
            bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[s3.LifecycleRule(expiration=Duration.days(30))],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        glue.CfnDatabase(
            self, "GlueDb",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=GLUE_DB,
                description="Datos de-identificados de sesiones NeuroFlex",
            ),
        )
        location = f"s3://{bucket.bucket_name}/sessions/"
        table = glue.CfnTable(
            self, "SessionsTable",
            catalog_id=self.account,
            database_name=GLUE_DB,
            table_input=glue.CfnTable.TableInputProperty(
                name="sesiones",
                table_type="EXTERNAL_TABLE",
                parameters={
                    "classification": "json",
                    "projection.enabled": "true",
                    "projection.experiencia.type": "enum",
                    "projection.experiencia.values": ",".join(settings.experiencias),
                    "projection.semana.type": "date",
                    "projection.semana.format": "yyyy-MM-dd",
                    "projection.semana.range": "2026-01-05,NOW",
                    "projection.semana.interval": "1",
                    "projection.semana.interval.unit": "WEEKS",
                    "storage.location.template":
                        location + "experiencia=${experiencia}/semana=${semana}/",
                },
                partition_keys=[
                    glue.CfnTable.ColumnProperty(name="experiencia", type="string"),
                    glue.CfnTable.ColumnProperty(name="semana", type="string"),
                ],
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    location=location,
                    input_format="org.apache.hadoop.mapred.TextInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.openx.data.jsonserde.JsonSerDe"),
                    columns=[
                        glue.CfnTable.ColumnProperty(name="registro_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="participante", type="string"),
                        glue.CfnTable.ColumnProperty(name="organizacion", type="string"),
                        glue.CfnTable.ColumnProperty(name="tipo_cliente", type="string"),
                        glue.CfnTable.ColumnProperty(name="tramo_edad", type="string"),
                        glue.CfnTable.ColumnProperty(name="duracion_seg", type="int"),
                        glue.CfnTable.ColumnProperty(name="version_app", type="string"),
                        glue.CfnTable.ColumnProperty(name="metricas", type="map<string,double>"),
                    ],
                ),
            ),
        )
        table.add_resource_dependency(self.node.find_child("GlueDb"))

        athena.CfnWorkGroup(
            self, "WorkGroup",
            name="nf-analytics",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                enforce_work_group_configuration=True,
                bytes_scanned_cutoff_per_query=1024 ** 3,  # 1 GB por consulta
                publish_cloud_watch_metrics_enabled=True,
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{results.bucket_name}/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_KMS", kms_key=key.key_arn),
                ),
            ),
        )

        CfnOutput(self, "AnalyticsBucketName", value=bucket.bucket_name)
        CfnOutput(self, "AnalyticsKeyArn", value=key.key_arn)
