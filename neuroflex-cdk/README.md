# NeuroFlex en AWS con CDK (Python)

Infraestructura como código de la arquitectura NeuroFlex multi-organización de
QualiaLab: capa compartida, un silo de datos por hospital y analítica
de-identificada en una cuenta separada.

## Qué crea cada pila

| Pila | Cuenta | Fase de la guía | Contenido |
| --- | --- | --- | --- |
| `NfAnalytics` | analítica | 7 | Bucket cifrado, catálogo Glue con proyección de particiones y grupo de trabajo de Athena |
| `NfAuth` | sistema | 2 | Cognito (plan Essentials), grupos, clientes `vr-unity` y `dashboard-django`, trigger Pre Token V2 |
| `NfCore` | sistema | 3, 5 y 6 | Tabla `nf-tenants`, rol y Lambdas compartidas, Lambda Authorizer y API Gateway |
| `NfAnalyticsExport` | sistema | 7 | Lambda de exportación de-identificada y clave HMAC (solo si la analítica está configurada) |
| `NfSecurity` | sistema | 8 | Rol de emergencia con MFA y alerta por correo cada vez que se usa |
| `NfTenant-<id>` | sistema | 4 | Un silo por hospital: clave KMS, tablas, bucket, rol y registro en `nf-tenants` |

La fase 1 (organización, cuentas, Identity Center, CloudTrail de la organización y
presupuestos) se hace en la consola, siguiendo la guía de implementación.

## Requisitos

- Python 3.12 o superior, Node.js 18 o superior y AWS CLI v2.
- Perfiles de AWS CLI para las dos cuentas (por ejemplo `sistema` y `analitica`),
  configurados con IAM Identity Center (`aws configure sso`).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
./scripts/build_layer.sh          # dependencias del autorizador (PyJWT)
```

## Configuración (`cdk.json`)

| Clave | Qué poner |
| --- | --- |
| `systemAccount` / `analyticsAccount` | Números de las cuentas `qualialab-sistema` y `qualialab-analitica` |
| `cognitoDomainPrefix` | Prefijo único para el inicio de sesión de Cognito |
| `dashboardCallbackUrls` | URL local a la que vuelve el panel de Django tras iniciar sesión |
| `analyticsBucketName` / `analyticsKeyArn` | Salidas de `NfAnalytics` (paso 2) |
| `breakglassPrincipalArns` | ARN de los roles de Identity Center autorizados para emergencias |
| `alertEmail` | Correo que recibe las alertas de seguridad |
| `experiencias` | Experiencias válidas: `neuroflex`, `deportistas`, `estudiantes` |

Los hospitales se listan en `config/tenants.json`.

## Despliegue, en este orden

```bash
# 1. Preparar ambas cuentas (una sola vez)
npx aws-cdk@2 bootstrap aws://<cuenta-sistema>/us-east-1  --profile sistema
npx aws-cdk@2 bootstrap aws://<cuenta-analitica>/us-east-1 --profile analitica

# 2. Analítica (cuenta del proveedor). Copie las salidas AnalyticsBucketName y
#    AnalyticsKeyArn a cdk.json.
npx aws-cdk@2 deploy NfAnalytics --profile analitica

# 3. Capa compartida (cuenta del sistema)
npx aws-cdk@2 deploy NfAuth NfCore NfAnalyticsExport NfSecurity --profile sistema

# 4. Silos de los hospitales que ya están en tenants.json
npx aws-cdk@2 deploy "NfTenant-*" --exclusively --profile sistema
```

Confirme la suscripción de correo de `nf-security-alerts` que llega a `alertEmail`.

## Alta de un hospital con un solo comando

```bash
python scripts/alta_hospital.py habB "Hospital B" --admin-email jefa@hospitalb.cl --profile sistema
```

El script valida el identificador, lo agrega a `config/tenants.json`, despliega
solo `NfTenant-habB` y crea el primer administrador, que recibe una contraseña
temporal por correo. Después, haga commit de `tenants.json`.

Para más usuarios:

```bash
python scripts/crear_usuario.py habB especialista@hospitalb.cl --grupo Specialist --profile sistema
```

**Suspender un hospital:** cambie su `estado` a `suspendido` en `tenants.json` y
vuelva a desplegar su pila. La API lo bloquea en un máximo de 5 minutos (caché del
autorizador). Eliminar la pila también lo suspende, pero **conserva** sus datos:
clave, tablas y bucket tienen política de retención.

## API

Todas las rutas exigen `Authorization: Bearer <token de acceso de Cognito>`.

| Ruta | Grupos | Descripción |
| --- | --- | --- |
| `POST /sessions` | Specialist, Administrator, Particular | Registra una sesión (idempotente por `sesion_id`) |
| `GET /sessions?participante_id=` | Specialist, Administrator, Particular | Últimas 50 sesiones del participante |
| `GET /users`, `POST /users` | Administrator (crear), Specialist (listar), Particular (su perfil) | Participantes, sin nombres ni RUT |
| `GET /professions` | Specialist, Administrator | Profesionales de la organización |
| `GET /terms` | Todos | Versión vigente de los términos |
| `POST /terms/consent` | Specialist, Administrator, Particular | Registra el consentimiento para investigación |

Ejemplo de cuerpo de `POST /sessions` desde el visor:

```json
{
  "sesion_id": "8f6c2a1e-5d4b-4a7e-9c1f-3b2d1e0f9a88",
  "participante_id": "pac-001",
  "experiencia": "neuroflex",
  "inicio": "2027-03-11T10:00:00-03:00",
  "duracion_seg": 900,
  "metricas": {"aciertos": 12, "errores": 3, "tiempo_reaccion_ms": 540},
  "version_app": "1.0.0"
}
```

El `tenant_id` nunca se envía: lo determina el token. Si viene en el cuerpo, se ignora.

## Analítica

Solo se exportan sesiones de participantes con `consentimiento_investigacion = true`.
Se eliminan identificadores y textos libres, los identificadores se reemplazan por
seudónimos HMAC, la fecha se reduce a la semana y la edad a tramos. En Athena
(grupo de trabajo `nf-analytics`):

```sql
SELECT experiencia, semana, tramo_edad,
       avg(metricas['tiempo_reaccion_ms']) AS tr_promedio,
       count(*) AS sesiones
FROM nf_analytics.sesiones
WHERE semana >= '2027-03-01'
GROUP BY 1, 2, 3;
```

El consentimiento se copia a cada sesión al registrarla: si una persona lo retira,
sus sesiones siguientes ya no se exportan. Las ya exportadas permanecen
seudonimizadas; defina en su política de privacidad cómo se tratan.

## Pruebas

```bash
python -m pytest -q        # 16 pruebas: aislamiento, cifrado, autorizador y de-identificación
npx aws-cdk@2 synth        # genera las plantillas en cdk.out/
```

Las pruebas no reemplazan la verificación en una cuenta real: ejecute la lista de la
fase 10 de la guía antes de usar datos de personas.

## Pendiente o a decidir

- **Registro de particulares (freemium):** el User Pool no permite registro abierto.
  Para habilitarlo, active `self_sign_up_enabled` y agregue un trigger Post
  Confirmation que asigne `tenant_id = particulares` y el grupo `Particular`.
- **Vinculación del visor con código de 6 dígitos**, en lugar de escribir la contraseña en el visor.
- **Parquet en lugar de JSON** cuando el volumen crezca (requiere una capa con pyarrow).
- **Región de Chile:** cambie `region` en `cdk.json` cuando esté disponible y migre los datos.
- **Costos:** todos los recursos son de pago por uso; KMS cobra cerca de USD 1 al mes por clave.
