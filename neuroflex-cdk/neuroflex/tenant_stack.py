"""Fase 4: silo de datos por organización/tenant (modo Learner Lab)."""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .settings import Settings


class TenantStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings,
                 tenant: dict, **kwargs):
        super().__init__(scope, cid, **kwargs)

        tenant_id = tenant["id"]
        tenant_id_clean = tenant_id.lower()

        # Referencia al rol pre-existente del Learner Lab
        lab_role = iam.Role.from_role_arn(
            self, "LearnerLabRole",
            f"arn:aws:iam::{self.account}:role/LabRole"
        )

        self.role = lab_role

        # Clave KMS para el silo
        self.key = kms.Key(
            self, "TenantKey",
            alias=f"alias/nf-{tenant_id_clean}",
            description=f"Clave KMS para el silo {tenant_id}",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Tablas DynamoDB del silo
        tables_config = (
            ("sessions", "session_id"),
            ("users", "user_id"),
            ("professions", "profession_id"),
        )
        self.tables = {}
        for name, pk in tables_config:
            t = ddb.Table(
                self, f"Table{name.capitalize()}",
                table_name=f"nf-{tenant_id}-{name}",
                partition_key=ddb.Attribute(name=pk, type=ddb.AttributeType.STRING),
                billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
                encryption=ddb.TableEncryption.CUSTOMER_MANAGED,
                encryption_key=self.key,
                stream=ddb.StreamViewType.NEW_IMAGE if name == "sessions" else None,
                point_in_time_recovery_specification=ddb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True),
                deletion_protection=False,
                removal_policy=RemovalPolicy.DESTROY,
            )
            self.tables[name] = t

        # Bucket S3 del silo (S3 exige nombres en minúsculas)
        self.bucket = s3.Bucket(
            self, "MetricsBucket",
            bucket_name=f"nf-{tenant_id_clean}-metrics-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.key,
            bucket_key_enabled=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=False,
        )

        CfnOutput(self, "RoleArn", value=self.role.role_arn)
        CfnOutput(self, "KeyArn", value=self.key.key_arn)
        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)