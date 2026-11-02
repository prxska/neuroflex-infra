#!/usr/bin/env python3
"""Punto de entrada CDK de la arquitectura NeuroFlex multi-organización (modo Learner Lab)."""
import aws_cdk as cdk

from neuroflex.analytics_export_stack import AnalyticsExportStack
from neuroflex.analytics_stack import AnalyticsStack
from neuroflex.auth_stack import AuthStack
from neuroflex.core_stack import CoreStack
from neuroflex.security_stack import SecurityStack
from neuroflex.settings import Settings
from neuroflex.tenant_stack import TenantStack

app = cdk.App()
settings = Settings.from_context(app.node)

# CAMBIO CRÍTICO: Forzamos la nueva cuenta de AWS (058264412508) y la región.
# Esto evita que CDK siga leyendo la cuenta vieja desde settings.py o cdk.json
system_env = cdk.Environment(account="058264412508", region="us-east-1")
analytics_env = cdk.Environment(account="058264412508", region="us-east-1")

# Sintetizador para desplegar con credenciales directas de CLI sin requerir roles globales de CDK Bootstrap
synthesizer = cdk.CliCredentialsStackSynthesizer()

cdk.Tags.of(app).add("proyecto", "neuroflex")
cdk.Tags.of(app).add("empresa", "qualialab")

AnalyticsStack(
    app, "NfAnalytics",
    settings=settings,
    env=analytics_env,
    synthesizer=synthesizer,
)

auth = AuthStack(
    app, "NfAuth",
    settings=settings,
    env=system_env,
    synthesizer=synthesizer,
)

core = CoreStack(
    app, "NfCore",
    settings=settings,
    user_pool_id=auth.user_pool.user_pool_id,
    app_client_ids=[
        auth.vr_client.user_pool_client_id,
        auth.dashboard_client.user_pool_client_id,
    ],
    env=system_env,
    synthesizer=synthesizer,
)

export = None
if settings.analytics_enabled:
    export = AnalyticsExportStack(
        app, "NfAnalyticsExport",
        settings=settings,
        env=system_env,
        synthesizer=synthesizer,
    )

SecurityStack(
    app, "NfSecurity",
    settings=settings,
    env=system_env,
    synthesizer=synthesizer,
)

for tenant in settings.tenants:
    stack = TenantStack(
        app, f"NfTenant-{tenant['id']}",
        settings=settings,
        tenant=tenant,
        env=system_env,
        description=f"Silo de datos de {tenant['nombre']} ({tenant['id']})",
        synthesizer=synthesizer,
    )
    stack.add_stack_dependency(core)
    if export is not None:
        stack.add_stack_dependency(export)

app.synth()