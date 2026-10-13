"""Configuración común y convención de nombres de NeuroFlex.

Los nombres fijos permiten que las pilas se conecten entre sí sin
exportaciones de CloudFormation (que bloquean cambios futuros).
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from constructs import Node

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "nf"

# Nombres fijos de recursos compartidos (cuenta del sistema)
TENANTS_TABLE = f"{PREFIX}-tenants"
SHARED_LAMBDA_ROLE = f"{PREFIX}-shared-lambda-role"
EXPORT_ROLE = f"{PREFIX}-analytics-export-role"
EXPORT_FUNCTION = f"{PREFIX}-analytics-export"
BREAKGLASS_ROLE = f"{PREFIX}-breakglass"
TENANT_ROLE_PREFIX = f"{PREFIX}-tenant-"

TENANT_ID_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9]{2,19}$")
TIPOS_CLIENTE = ("organizacion", "particulares")


@dataclass
class Settings:
    region: str
    system_account: str
    analytics_account: str
    cognito_domain_prefix: str
    dashboard_callback_urls: list
    analytics_bucket_name: str
    analytics_key_arn: str
    breakglass_principal_arns: list
    alert_email: str
    experiencias: list
    terms_version: str
    tenants: list = field(default_factory=list)

    @property
    def analytics_enabled(self) -> bool:
        return bool(self.analytics_bucket_name and self.analytics_key_arn)

    @staticmethod
    def from_context(node: Node) -> "Settings":
        def ctx(key, default=None):
            value = node.try_get_context(key)
            return default if value is None else value

        return Settings(
            region=ctx("region", "us-east-1"),
            system_account=str(ctx("systemAccount")),
            analytics_account=str(ctx("analyticsAccount")),
            cognito_domain_prefix=ctx("cognitoDomainPrefix"),
            dashboard_callback_urls=ctx("dashboardCallbackUrls", []),
            analytics_bucket_name=ctx("analyticsBucketName", ""),
            analytics_key_arn=ctx("analyticsKeyArn", ""),
            breakglass_principal_arns=ctx("breakglassPrincipalArns", []),
            alert_email=ctx("alertEmail", ""),
            experiencias=ctx("experiencias", []),
            terms_version=ctx("termsVersion", "1"),
            tenants=load_tenants(),
        )


def load_tenants(path: Path = ROOT / "config" / "tenants.json") -> list:
    tenants = json.loads(path.read_text(encoding="utf-8"))
    seen = set()
    for t in tenants:
        validate_tenant(t)
        if t["id"] in seen:
            raise ValueError(f"tenant_id duplicado en tenants.json: {t['id']}")
        seen.add(t["id"])
    return tenants


def validate_tenant(t: dict) -> None:
    if not TENANT_ID_PATTERN.match(t.get("id", "")):
        raise ValueError(
            f"tenant_id inválido '{t.get('id')}': use 3 a 20 letras o números, "
            "comenzando con minúscula (ejemplo: habA)."
        )
    if t.get("tipo_cliente") not in TIPOS_CLIENTE:
        raise ValueError(f"tipo_cliente inválido para {t['id']}: {TIPOS_CLIENTE}")
    if t.get("estado", "activo") not in ("activo", "suspendido"):
        raise ValueError(f"estado inválido para {t['id']}")


def tenant_names(tenant_id: str, account: str) -> dict:
    """Nombres de los recursos de un hospital (silo)."""
    p = f"{PREFIX}-{tenant_id}"
    return {
        "sessions": f"{p}-sessions",
        "users": f"{p}-users",
        "professions": f"{p}-professions",
        "bucket": f"{p.lower()}-metrics-{account}",
        "role": f"{TENANT_ROLE_PREFIX}{tenant_id}",
        "key_alias": f"alias/{p}",
    }
