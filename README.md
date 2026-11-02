# Documento de Arquitectura de Software (SAD)
## Plataforma SaaS NeuroFlex VR


**Fecha:** Octubre 2026  
**Modalidad:** Innovación / Desarrollo  
**Repositorio:** `prxska/neuroflex-infra`  

---

### 1. Contexto de Negocio y Alcance Clínico

#### 1.1. Problemática
En Chile, la población de 60 años o más aumentará del 18,1% al 32,1% (INE). La prevalencia de demencia es significativamente mayor en zonas rurales (10,3%) frente a zonas urbanas (6,3%), y apenas 28 de cada 100 personas detectadas logran mantener su tratamiento continuo.

#### 1.2. Solución Propuesta
NeuroFlex VR es una plataforma SaaS diseñada para ejercitar y evaluar la memoria y la atención mediante realidad virtual en centros como CESFAM, ELEAM y clínicas privadas. La arquitectura garantiza tolerancia a conexiones inestables, almacenamiento inmutable y aislamiento estricto entre instituciones médicas bajo el marco de la Ley N.º 21.719.

# NeuroFlex VR - Infraestructura Cloud (Backend)

Este repositorio contiene la Infraestructura como Código (IaC) y las funciones Serverless (Lambdas) de la plataforma NeuroFlex VR. Está construido usando **AWS CDK (Python)**.

## 🏗️ Arquitectura
- **API Gateway:** Punto de entrada para el tráfico del Meta Quest y el Dashboard.
- **Amazon SQS:** Cola de mensajes para absorber picos de tráfico de telemetría (Hasta 10.000 peticiones simultáneas sin caídas).
- **AWS Lambda (Worker):** Procesa los JSON de Unity (`scenes-v1`), calcula las métricas clínicas y guarda los datos.
- **Amazon DynamoDB:** Almacenamiento de datos calientes (Multi-Tenant: llave `tenantId#participantId`).
- **Amazon S3:** Almacenamiento de datos fríos (Cold Data) particionado por año/mes/clínica.
- **Amazon Cognito:** Autenticación y autorización de usuarios.
- **AWS KMS:** Cifrado de datos clínicos.

## 🚀 Despliegue (AWS Learner Lab)
Debido a las restricciones del entorno de AWS Academy, el despliegue requiere seguir estos pasos:

1. Configurar credenciales de AWS en la terminal (`$env:AWS_ACCESS_KEY_ID=...`).
2. Inicializar el entorno de CDK (solo la primera vez):
   ```bash
   cd neuroflex-cdk
   npx aws-cdk bootstrap

