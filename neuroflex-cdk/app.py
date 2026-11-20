#!/usr/bin/env python3
"""Punto de entrada CDK de la arquitectura NeuroFlex multi-organización (modo Learner Lab)."""
import os

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

# Learner Lab: la cuenta cambia entre sesiones. CDK expone la cuenta/región de
# las credenciales activas en CDK_DEFAULT_ACCOUNT / CDK_DEFAULT_REGION, así que
# las usamos como destino y dejamos cdk.json solo como respaldo para synth sin
# credenciales.
target_account = os.environ.get("CDK_DEFAULT_ACCOUNT") or settings.system_account
target_region = os.environ.get("CDK_DEFAULT_REGION") or settings.region

# Toda la infraestructura vive en una sola cuenta: alinear las políticas de
# analítica con la cuenta destino real.
settings.system_account = target_account
settings.analytics_account = target_account

system_env = cdk.Environment(account=target_account, region=target_region)
analytics_env = cdk.Environment(account=target_account, region=target_region)

# Despliega con las credenciales directas del CLI (sin asumir roles de bootstrap),
# pero sí requiere los recursos de staging creados por `cdk bootstrap`.
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