#!/usr/bin/env python3
"""Crea un usuario en Cognito con su tenant_id y grupo.

Ejemplo:
  python scripts/crear_usuario.py habA especialista@hospitala.cl --grupo Specialist

Cognito envía al correo una contraseña temporal que el usuario cambia en su primer ingreso.
El tenant_id solo puede asignarse así (los clientes de la aplicación no pueden modificarlo).
"""
import argparse
import sys

import boto3


def find_user_pool(cognito, name="nf-users") -> str:
    for page in cognito.get_paginator("list_user_pools").paginate(MaxResults=60):
        for pool in page["UserPools"]:
            if pool["Name"] == name:
                return pool["Id"]
    sys.exit(f"No se encontró el User Pool '{name}'. ¿Se desplegó NfAuth?")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant_id")
    ap.add_argument("email")
    ap.add_argument("--grupo", required=True,
                    choices=["Administrator", "Specialist", "Particular"])
    ap.add_argument("--profile")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    tenants = session.resource("dynamodb").Table("nf-tenants")
    item = tenants.get_item(Key={"tenant_id": args.tenant_id}).get("Item")
    if not item:
        sys.exit(f"El tenant '{args.tenant_id}' no está registrado en nf-tenants.")

    cognito = session.client("cognito-idp")
    pool_id = find_user_pool(cognito)
    cognito.admin_create_user(
        UserPoolId=pool_id,
        Username=args.email,
        UserAttributes=[
            {"Name": "email", "Value": args.email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:tenant_id", "Value": args.tenant_id},
        ],
        DesiredDeliveryMediums=["EMAIL"],
    )
    cognito.admin_add_user_to_group(UserPoolId=pool_id, Username=args.email,
                                    GroupName=args.grupo)
    print(f"Usuario {args.email} creado en {args.tenant_id} con grupo {args.grupo}.")


if __name__ == "__main__":
    main()
