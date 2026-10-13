#!/usr/bin/env python3
"""Alta de un hospital u organización con un solo comando.

Ejemplo:
  python scripts/alta_hospital.py habB "Hospital B" --admin-email jefa@hospitalb.cl

Pasos que realiza:
  1. Valida el identificador y lo agrega a config/tenants.json.
  2. Despliega SOLO la pila NfTenant-<id> (clave KMS, tablas, bucket, rol y registro).
  3. (Opcional) Crea el primer usuario Administrator con su tenant_id asignado.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from neuroflex.settings import validate_tenant  # noqa: E402

TENANTS = ROOT / "config" / "tenants.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tenant_id", help="Identificador corto, por ejemplo habB")
    ap.add_argument("nombre", help="Nombre visible de la organización")
    ap.add_argument("--tipo", default="organizacion", choices=["organizacion", "particulares"])
    ap.add_argument("--admin-email", help="Correo del primer administrador de la organización")
    ap.add_argument("--profile", help="Perfil de AWS CLI de la cuenta del sistema")
    ap.add_argument("--solo-config", action="store_true",
                    help="Solo agrega la entrada a tenants.json, sin desplegar")
    args = ap.parse_args()

    tenant = {"id": args.tenant_id, "nombre": args.nombre,
              "tipo_cliente": args.tipo, "estado": "activo"}
    validate_tenant(tenant)

    tenants = json.loads(TENANTS.read_text(encoding="utf-8"))
    if any(t["id"] == args.tenant_id for t in tenants):
        print(f"'{args.tenant_id}' ya existe en tenants.json; se volverá a desplegar.")
    else:
        tenants.append(tenant)
        TENANTS.write_text(json.dumps(tenants, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"Agregado '{args.tenant_id}' a config/tenants.json")

    if args.solo_config:
        return

    cmd = ["npx", "aws-cdk@2", "deploy", f"NfTenant-{args.tenant_id}", "--exclusively"]
    if args.profile:
        cmd += ["--profile", args.profile]
    print("Ejecutando:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)

    if args.admin_email:
        cmd = [sys.executable, str(ROOT / "scripts" / "crear_usuario.py"),
               args.tenant_id, args.admin_email, "--grupo", "Administrator"]
        if args.profile:
            cmd += ["--profile", args.profile]
        subprocess.run(cmd, cwd=ROOT, check=True)

    print(f"\nListo: {args.nombre} ({args.tenant_id}) está operativo.")
    print("Recuerde: commit de config/tenants.json para dejar registro del alta.")


if __name__ == "__main__":
    main()
