import json
import os
from decimal import Decimal
from datetime import datetime
import boto3

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

# Variables de entorno inyectadas desde CDK
LEGACY_TABLE = os.environ.get("TABLE_NAME")
SCENES_TABLE = os.environ.get("SCENES_TABLE_NAME")
BUCKET_NAME = os.environ.get("BUCKET_NAME")

def float_to_decimal(payload):
    """Convierte los floats generados por las matemáticas al tipo Decimal que exige DynamoDB."""
    return json.loads(json.dumps(payload), parse_float=Decimal)

def handler(event, context):
    records = event.get("Records", [])
    legacy_table = dynamodb.Table(LEGACY_TABLE) if LEGACY_TABLE else None
    scenes_table = dynamodb.Table(SCENES_TABLE) if SCENES_TABLE else None

    for record in records:
        body = json.loads(record["body"])

        # ENRUTAMIENTO: ¿Contrato nuevo de Unity o formato legacy de Expo?
        if body.get("contractVersion") == "scenes-v1":
            process_scenes_v1(body, scenes_table)
        else:
            process_legacy(body, legacy_table)

    return {"statusCode": 200, "processed": len(records)}


def process_scenes_v1(body, table):
    """Procesamiento estricto basado en el contrato de métricas."""
    rounds = body.get("rounds", [])
    if not rounds or not table: return

    processed_rounds = [] # Aquí guardaremos el JSON procesado para S3

    # 1. PRIMERO DynamoDB (Dato clínico prioritario)
    with table.batch_writer() as batch:
        for r in rounds:
            scenario = r.get("scenarioId")
            status = r.get("status")
            metrics = {}

            # CÁLCULOS ESTRICTOS POR ESCENA
            if scenario == "puzzle":
                act_ms = r.get("activeTimeMs", 0)
                metrics["activeTimeSeconds"] = act_ms / 1000.0
                metrics["resolutionTimeSeconds"] = act_ms / 1000.0 if status == "completed" else None
                metrics["incorrectMoves"] = r.get("incorrectPlacements")
                metrics["completedPieces"] = r.get("correctPlacements")
                metrics["totalPieces"] = r.get("totalPieces")

            elif scenario == "memory":
                act_ms = r.get("activeTimeMs", 0)
                metrics["activeTimeSeconds"] = act_ms / 1000.0
                metrics["resolutionTimeSeconds"] = act_ms / 1000.0 if status == "completed" else None
                correct = r.get("correctPairAttempts", 0)
                incorrect = r.get("incorrectPairAttempts", 0)
                total_attempts = correct + incorrect
                metrics["matchingAccuracyPercent"] = round((100.0 * correct / total_attempts), 2) if total_attempts > 0 else None
                metrics["incorrectAttempts"] = incorrect

            elif scenario == "pigeons":
                ans_ms = r.get("responseTimeMs")
                metrics["enabledResponseActiveSeconds"] = ans_ms / 1000.0 if ans_ms is not None else None
                
                user_val = r.get("userPigeonCount")
                real_val = r.get("actualPigeonCount")
                if user_val is not None and real_val is not None:
                    metrics["responseCorrect"] = (user_val == real_val)
                    metrics["signedCountError"] = user_val - real_val
                    metrics["absoluteCountError"] = abs(user_val - real_val)
                else:
                    metrics["responseCorrect"] = None

                hidden = r.get("pigeonsHiddenAt")
                submitted = r.get("answerSubmittedAt")
                if hidden and submitted:
                    try:
                        t1 = datetime.fromisoformat(hidden.replace('Z', '+00:00'))
                        t2 = datetime.fromisoformat(submitted.replace('Z', '+00:00'))
                        metrics["responseTimeSeconds"] = (t2 - t1).total_seconds()
                    except Exception:
                        metrics["responseTimeSeconds"] = None

            # 3. Upsert Idempotente: participantId (PK) + roundId (SK)
            item = {
                "participantId": r.get("participantId"),
                "roundId": r.get("roundId"),
                "sessionId": r.get("sessionId"),
                "scenarioId": scenario,
                "status": status,
                "metrics": metrics
            }
            batch.put_item(Item=float_to_decimal(item))
            
            # Guardamos el item procesado en memoria para el paso 2
            processed_rounds.append(item)

    # 2. DESPUÉS S3 (Cold Data), aislado y enriquecido
    if BUCKET_NAME:
        try:
            participant_id = rounds[0].get("participantId", "unknown")
            session_id = rounds[0].get("sessionId", "unknown")
            now = datetime.utcnow()
            key = f"scenes-v1/{now.year}/{now.month:02d}/{participant_id}/{session_id}.json"
            
            # Estructura clínica: Input original + Métricas calculadas
            enriched_payload = {
                "raw_input": body,
                "processed_rounds": processed_rounds
            }
            
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=json.dumps(enriched_payload, default=str),
                ContentType="application/json"
            )
        except Exception as e:
            print(f"[WARN] Cold data no persistido en S3: {e}")


def process_legacy(body, table):
    """Mantiene vivo el sistema anterior para que Expo no colapse."""
    if not table: return
    participante_id = body.get("participante_id")
    sesion_id = body.get("sesion_id")
    if not participante_id or not sesion_id: return

    item = {
        "session_id": sesion_id,
        "sesion_id_sort": sesion_id,
        "participante_id": participante_id,
        "experiencia": body.get("experiencia", "unknown"),
        "duracion_seg": int(body.get("duracion_seg", 0)),
        "metricas": body.get("metricas", {})
    }
    table.put_item(Item=float_to_decimal(item))
    
    telemetria_raw = body.get("telemetria_raw", [])
    if telemetria_raw and BUCKET_NAME:
        try:
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=f"sessions/{participante_id}/{sesion_id}.json",
                Body=json.dumps(telemetria_raw),
                ContentType="application/json"
            )
        except Exception as e:
            print(f"[WARN] Legacy cold data no persistido en S3: {e}")