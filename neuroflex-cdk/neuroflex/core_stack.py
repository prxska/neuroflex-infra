"""Fases 3, 5 y 6: tabla tenants, Lambdas compartidas, cola SQS, autorizador y API Gateway (modo Learner Lab)."""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as eventsources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from .settings import (ROOT, SHARED_LAMBDA_ROLE, TENANT_ROLE_PREFIX, TENANTS_TABLE,
                       Settings)

DEPS_LAYER = ROOT / "layers" / "deps"


class CoreStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings,
                 user_pool_id: str, app_client_ids: list, **kwargs):
        super().__init__(scope, cid, **kwargs)

            
# Referencia al rol pre-existente del Learner Lab (inmutable para evitar iam:PutRolePolicy)
        lab_role = iam.Role.from_role_arn(
            self, "LearnerLabRole",
            f"arn:aws:iam::{self.account}:role/LabRole",
            mutable=False
        )

        # ---------- Fase 3: registro de organizaciones ----------
        self.tenants_table = ddb.Table(
            self, "TenantsTable",
            table_name=TENANTS_TABLE,
            partition_key=ddb.Attribute(name="tenant_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=ddb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True),
            stream=ddb.StreamViewType.NEW_AND_OLD_IMAGES,
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ---------- Desacople de Ingesta VR: Cola SQS y DLQ ----------
        self.sessions_dlq = sqs.Queue(
            self, "SessionsDLQ",
            queue_name="nf-sessions-dlq",
            retention_period=Duration.days(14)
        )

        self.sessions_queue = sqs.Queue(
            self, "SessionsQueue",
            queue_name="nf-sessions-queue",
            visibility_timeout=Duration.seconds(60),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.sessions_dlq
            )
        )

        # ---------- Fase 5: rol de las Lambdas compartidas ----------
        self.shared_role = lab_role

        common_layer = lambda_.LayerVersion(
            self, "CommonLayer",
            layer_version_name="nf-common",
            code=lambda_.Code.from_asset(str(ROOT / "lambdas" / "common")),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Resolución de tenant, AssumeRole con caché y respuestas HTTP",
        )

        common_env = {
            "TENANTS_TABLE": TENANTS_TABLE,
            "TERMS_VERSION": settings.terms_version,
            "EXPERIENCIAS": ",".join(settings.experiencias),
            "POWERTOOLS_SERVICE_NAME": "neuroflex",
            "SQS_QUEUE_URL": self.sessions_queue.queue_url,
        }

        def shared_fn(name: str) -> lambda_.Function:
            return lambda_.Function(
                self, f"{name.capitalize()}Fn",
                function_name=f"nf-{name}",
                runtime=lambda_.Runtime.PYTHON_3_12,
                architecture=lambda_.Architecture.ARM_64,
                handler="app.handler",
                code=lambda_.Code.from_asset(str(ROOT / "lambdas" / name)),
                layers=[common_layer],
                role=self.shared_role,
                memory_size=256,
                timeout=Duration.seconds(10),
                environment=common_env,
                log_group=logs.LogGroup(
                    self, f"{name.capitalize()}Logs",
                    log_group_name=f"/aws/lambda/nf-{name}",
                    retention=logs.RetentionDays.THREE_MONTHS,
                    removal_policy=RemovalPolicy.DESTROY,
                ),
            )

        fns = {n: shared_fn(n) for n in ("sessions", "users", "professions", "terms")}

        # ---------- Worker asíncrono consumidor de SQS ----------
        worker_fn = lambda_.Function(
            self, "SessionsWorkerFn",
            function_name="nf-sessions-worker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="app.handler",
            code=lambda_.Code.from_asset(str(ROOT / "lambdas" / "sessions_worker")),
            role=lab_role,
            memory_size=256,
            timeout=Duration.seconds(30),
            log_group=logs.LogGroup(
                self, "SessionsWorkerLogs",
                log_group_name="/aws/lambda/nf-sessions-worker",
                retention=logs.RetentionDays.THREE_MONTHS,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )

        worker_fn.add_event_source(eventsources.SqsEventSource(
            self.sessions_queue,
            batch_size=10,
            max_batching_window=Duration.seconds(5)
        ))

        # ---------- Fase 6: autorizador ----------
        if not (DEPS_LAYER / "python").exists():
            raise RuntimeError(
                "Falta la capa de dependencias del autorizador. Ejecute primero:\n"
                "  ./scripts/build_layer.sh"
            )
        deps_layer = lambda_.LayerVersion(
            self, "DepsLayer",
            layer_version_name="nf-deps",
            code=lambda_.Code.from_asset(str(DEPS_LAYER)),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            compatible_architectures=[lambda_.Architecture.X86_64],
            description="PyJWT[crypto] para validar tokens de Cognito",
        )
        authorizer_fn = lambda_.Function(
            self, "AuthorizerFn",
            function_name="nf-authorizer",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.X86_64,
            handler="app.handler",
            code=lambda_.Code.from_asset(str(ROOT / "lambdas" / "authorizer")),
            layers=[deps_layer],
            role=lab_role,
            memory_size=256,
            timeout=Duration.seconds(5),
            environment={
                "USER_POOL_ID": user_pool_id,
                "APP_CLIENT_IDS": ",".join(app_client_ids),
                "TENANTS_TABLE": TENANTS_TABLE,
            },
            log_group=logs.LogGroup(
                self, "AuthorizerLogs",
                log_group_name="/aws/lambda/nf-authorizer",
                retention=logs.RetentionDays.THREE_MONTHS,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )

        authorizer = apigw.TokenAuthorizer(
            self, "TokenAuthorizer",
            handler=authorizer_fn,
            identity_source=apigw.IdentitySource.header("Authorization"),
            results_cache_ttl=Duration.minutes(5),
        )

        self.api = apigw.RestApi(
            self, "Api",
            rest_api_name="nf-api",
            description="API NeuroFlex multi-organización",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            cloud_watch_role=False,
            deploy_options=apigw.StageOptions(
                stage_name="v1",
                throttling_rate_limit=20,
                throttling_burst_limit=40,
            ),
            default_method_options=apigw.MethodOptions(
                authorizer=authorizer,
                authorization_type=apigw.AuthorizationType.CUSTOM,
            ),
        )

        routes = {
            "sessions": ["GET", "POST"],
            "users": ["GET", "POST"],
            "professions": ["GET"],
            "terms": ["GET"],
        }
        for name, methods in routes.items():
            res = self.api.root.add_resource(name)
            integ = apigw.LambdaIntegration(fns[name])
            for m in methods:
                res.add_method(m, integ)
        consent = self.api.root.get_resource("terms").add_resource("consent")
        consent.add_method("POST", apigw.LambdaIntegration(fns["terms"]))

        CfnOutput(self, "ApiUrl", value=self.api.url)
        CfnOutput(self, "TenantsTableName", value=self.tenants_table.table_name)
        CfnOutput(self, "SessionsQueueUrl", value=self.sessions_queue.queue_url)