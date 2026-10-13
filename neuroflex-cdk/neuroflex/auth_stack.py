"""Fase 2: autenticación con Amazon Cognito.

- User Pool con plan Essentials (necesario para personalizar el token de acceso).
- Atributo custom:tenant_id que la aplicación NO puede escribir.
- Grupos Administrator, Specialist y Particular.
- Clientes vr-unity y dashboard-django.
- Trigger Pre Token Generation V2_0 que copia tenant_id al token de acceso.
"""
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from .settings import ROOT, Settings

GROUPS = {
    "Administrator": "Administra usuarios y profesionales de su organización",
    "Specialist": "Registra y revisa sesiones de su organización",
    "Particular": "Cliente particular (versión freemium/premium)",
}


class AuthStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings, **kwargs):
        super().__init__(scope, cid, **kwargs)

        self.user_pool = cognito.UserPool(
            self, "UserPool",
            user_pool_name="nf-users",
            feature_plan=cognito.FeaturePlan.ESSENTIALS,
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True)
            ),
            custom_attributes={
                # Mutable solo por administradores (AdminUpdateUserAttributes);
                # los clientes de aplicación no tienen permiso de escritura.
                "tenant_id": cognito.StringAttribute(min_len=3, max_len=20, mutable=True),
            },
            password_policy=cognito.PasswordPolicy(
                min_length=12, require_digits=True, require_lowercase=True,
                require_uppercase=True, require_symbols=True,
                temp_password_validity=Duration.days(3),
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            deletion_protection=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        for name, desc in GROUPS.items():
            cognito.CfnUserPoolGroup(
                self, f"Group{name}",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=name, description=desc,
            )

        # La aplicación puede leer tenant_id pero no escribirlo.
        read_attrs = cognito.ClientAttributes().with_standard_attributes(
            email=True, email_verified=True
        ).with_custom_attributes("tenant_id")
        write_attrs = cognito.ClientAttributes().with_standard_attributes(email=True)

        self.vr_client = self.user_pool.add_client(
            "VrUnityClient",
            user_pool_client_name="vr-unity",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True, user_password=True),
            access_token_validity=Duration.minutes(60),
            id_token_validity=Duration.minutes(60),
            refresh_token_validity=Duration.days(30),
            prevent_user_existence_errors=True,
            enable_token_revocation=True,
            read_attributes=read_attrs,
            write_attributes=write_attrs,
        )

        self.dashboard_client = self.user_pool.add_client(
            "DashboardClient",
            user_pool_client_name="dashboard-django",
            generate_secret=False,  # aplicación instalada: usar PKCE
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL,
                        cognito.OAuthScope.PROFILE],
                callback_urls=settings.dashboard_callback_urls,
                logout_urls=settings.dashboard_callback_urls,
            ),
            access_token_validity=Duration.minutes(30),
            id_token_validity=Duration.minutes(30),
            refresh_token_validity=Duration.days(7),
            prevent_user_existence_errors=True,
            enable_token_revocation=True,
            read_attributes=read_attrs,
            write_attributes=write_attrs,
        )

        self.user_pool.add_domain(
            "Domain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=settings.cognito_domain_prefix
            ),
        )

        pre_token = lambda_.Function(
            self, "PreTokenFn",
            function_name="nf-pre-token",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="app.handler",
            code=lambda_.Code.from_asset(str(ROOT / "lambdas" / "pre_token")),
            timeout=Duration.seconds(5),
            log_group=logs.LogGroup(
                self, "PreTokenLogs", retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        self.user_pool.add_trigger(
            cognito.UserPoolOperation.PRE_TOKEN_GENERATION_CONFIG,
            pre_token,
            cognito.LambdaVersion.V2_0,
        )

        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "VrClientId", value=self.vr_client.user_pool_client_id)
        CfnOutput(self, "DashboardClientId", value=self.dashboard_client.user_pool_client_id)
