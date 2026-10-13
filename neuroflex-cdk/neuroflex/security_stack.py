"""Fase 8: acceso de emergencia (break-glass) auditado.

- Rol nf-breakglass, asumible solo con MFA y por las personas indicadas.
- Alerta por correo cada vez que alguien lo asume (EventBridge + SNS).

Requisito: un trail de CloudTrail activo (por ejemplo, el trail de la
organización creado en la fase 1), para que EventBridge reciba los eventos.
"""
from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

from .settings import BREAKGLASS_ROLE, Settings


class SecurityStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, settings: Settings, **kwargs):
        super().__init__(scope, cid, **kwargs)

        topic = sns.Topic(self, "SecurityAlerts", topic_name="nf-security-alerts")
        if settings.alert_email:
            topic.add_subscription(subs.EmailSubscription(settings.alert_email))

        principals = settings.breakglass_principal_arns
        if principals:
            role = iam.Role(
                self, "BreakGlassRole",
                role_name=BREAKGLASS_ROLE,
                description="Acceso de emergencia auditado. Documentar cada uso.",
                assumed_by=iam.CompositePrincipal(
                    *[iam.ArnPrincipal(a) for a in principals]
                ).with_conditions({"Bool": {"aws:MultiFactorAuthPresent": "true"}}),
                max_session_duration=Duration.hours(1),
            )
            role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name(
                "ReadOnlyAccess"))

        events.Rule(
            self, "BreakGlassAssumed",
            rule_name="nf-breakglass-assumed",
            description="Alerta cuando se asume el rol de emergencia",
            event_pattern=events.EventPattern(
                source=["aws.sts"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventName": ["AssumeRole"],
                    "requestParameters": {"roleArn": [
                        f"arn:aws:iam::{self.account}:role/{BREAKGLASS_ROLE}"]},
                },
            ),
            targets=[targets.SnsTopic(topic)],
        )
