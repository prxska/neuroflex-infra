#!/usr/bin/env python3
"""Punto de entrada CDK de la arquitectura NeuroFlex multi-organización.

Pilas (ver README.md para el orden de despliegue):
  NfAnalytics           -> cuenta de analítica del proveedor
  NfAuth                -> Cognito (cuenta del sistema)
  NfCore                -> tabla tenants, Lambdas compartidas, autorizador y API
  NfAnalyticsExport     -> exportación de-identificada (solo si la analítica está configurada)
  NfSecurity            -> acceso de emergencia y alertas
  NfTenant-<id>         -> un silo por cada entrada de config/tenants.json
"""
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

system_env = cdk.Environment(account=settings.system_account, region=settings.region)
analytics_env = cdk.Environment(account=settings.analytics_account, region=settings.region)

cdk.Tags.of(app).add("proyecto", "neuroflex")
cdk.Tags.of(app).add("empresa", "qualialab")

AnalyticsStack(app, "NfAnalytics", settings=settings, env=analytics_env)

auth = AuthStack(app, "NfAuth", settings=settings, env=system_env)

core = CoreStack(
    app, "NfCore",
    settings=settings,
    user_pool_id=auth.user_pool.user_pool_id,
    app_client_ids=[auth.vr_client.user_pool_client_id,
                    auth.dashboard_client.user_pool_client_id],
    env=system_env,
)

export = None
if settings.analytics_enabled:
    export = AnalyticsExportStack(app, "NfAnalyticsExport", settings=settings, env=system_env)

SecurityStack(app, "NfSecurity", settings=settings, env=system_env)

for tenant in settings.tenants:
    stack = TenantStack(
        app, f"NfTenant-{tenant['id']}",
        settings=settings, tenant=tenant, env=system_env,
        description=f"Silo de datos de {tenant['nombre']} ({tenant['id']})",
    )
    # Orden de despliegue: la tabla tenants y el rol compartido deben existir antes.
    stack.add_stack_dependency(core)
    if export is not None:
        stack.add_stack_dependency(export)

app.synth()
