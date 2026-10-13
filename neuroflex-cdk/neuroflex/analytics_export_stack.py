"""Fase 7 (cuenta del sistema): exportación de-identificada hacia la cuenta de analítica.

La de-identificación ocurre AQUÍ, en la cuenta del sistema, para que los datos
identificables nunca salgan de ella. A la cuenta del proveedor solo llegan
registros seudonimizados de personas que consintieron el uso para investigación.
"""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from .settings import EXPORT_FUNCTION, EXPORT_ROLE, ROOT, Settings


class AnalyticsExportStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings, **kwargs):
        super().__init__(scope, cid, **kwargs)

        # Clave HMAC para seudonimizar identificadores (no reversible sin la clave).
        hmac_key = kms.Key(
            self, "PseudonymKey",
            alias="alias/nf-pseudonym",
            description="HMAC para seudonimizar identificadores antes de exportar",
            key_spec=kms.KeySpec.HMAC_256,
            key_usage=kms.KeyUsage.GENERATE_VERIFY_MAC,
            removal_policy=RemovalPolicy.RETAIN,
        )

        role = iam.Role(
            self, "ExportRole",
            role_name=EXPORT_ROLE,
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole")],
        )
        # Lectura de los streams de las tablas de sesiones de todos los hospitales.
        role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:DescribeStream", "dynamodb:GetRecords",
                     "dynamodb:GetShardIterator", "dynamodb:ListStreams"],
            resources=[f"arn:aws:dynamodb:{self.region}:{self.account}"
                       f":table/nf-*-sessions/stream/*"],
        ))
        role.add_to_policy(iam.PolicyStatement(
            actions=["kms:Decrypt"],
            resources=[f"arn:aws:kms:{self.region}:{self.account}:key/*"],
            conditions={"ForAnyValue:StringLike": {"kms:ResourceAliases": "alias/nf-*"}},
        ))
        role.add_to_policy(iam.PolicyStatement(
            actions=["kms:GenerateMac"], resources=[hmac_key.key_arn],
        ))
        # Escritura en el bucket de la cuenta de analítica (solo prefijo sessions/).
        role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=[f"arn:aws:s3:::{settings.analytics_bucket_name}/sessions/*"],
        ))
        role.add_to_policy(iam.PolicyStatement(
            actions=["kms:GenerateDataKey", "kms:Encrypt"],
            resources=[settings.analytics_key_arn],
        ))

        dlq = sqs.Queue(
            self, "ExportDlq",
            queue_name="nf-analytics-export-dlq",
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            retention_period=Duration.days(14),
        )
        dlq.grant_send_messages(role)

        lambda_.Function(
            self, "ExportFn",
            function_name=EXPORT_FUNCTION,
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="app.handler",
            code=lambda_.Code.from_asset(str(ROOT / "lambdas" / "analytics_export")),
            role=role,
            memory_size=256,
            timeout=Duration.seconds(60),
            reserved_concurrent_executions=5,
            dead_letter_queue=dlq,
            environment={
                "ANALYTICS_BUCKET": settings.analytics_bucket_name,
                "ANALYTICS_KMS_KEY_ARN": settings.analytics_key_arn,
                "HMAC_KEY_ID": hmac_key.key_arn,
                "EXPERIENCIAS": ",".join(settings.experiencias),
            },
            log_group=logs.LogGroup(
                self, "ExportLogs",
                log_group_name=f"/aws/lambda/{EXPORT_FUNCTION}",
                retention=logs.RetentionDays.THREE_MONTHS,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        CfnOutput(self, "ExportRoleArn", value=role.role_arn)
