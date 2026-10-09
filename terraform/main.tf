terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

# us-east-1 impuesto por cuotas del Learner Lab. En produccion sa-east-1 (ADR-001).
provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

# Rol predeterminado para el entorno restringido de AWS Academy
data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

# ==============================================================================
# 1. SQS: BUFFER ASÍNCRONO Y TOLERANCIA A FALLOS (DLQ)
# ==============================================================================

resource "aws_sqs_queue" "telemetry_dlq" {
  name                      = "neuroflex-session-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 dias de resguardo forense
}

resource "aws_sqs_queue" "telemetry_queue" {
  name                      = "neuroflex-session-queue-${var.environment}"
  delay_seconds             = 0
  max_message_size          = 262144 # 256 KB
  message_retention_seconds = 345600 # 4 dias de persistencia offline
  receive_wait_time_seconds = 10     # Long polling para optimizacion FinOps

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.telemetry_dlq.arn
    maxReceiveCount     = 3
  })
}

# ==============================================================================
# 2. API GATEWAY HTTP (v2): INGESTA DIRECTA SERVERLESS (ZERO-LAMBDA)
# ==============================================================================

resource "aws_apigatewayv2_api" "telemetry_api" {
  name          = "neuroflex-api-${var.environment}"
  protocol_type = "HTTP"
  description   = "Puerta de entrada de telemetria clinica NeuroFlex VR"
}

resource "aws_apigatewayv2_integration" "sqs_integration" {
  api_id              = aws_apigatewayv2_api.telemetry_api.id
  credentials_arn     = data.aws_iam_role.lab_role.arn
  integration_type    = "AWS_PROXY"
  integration_subtype = "SQS-SendMessage"

  request_parameters = {
    QueueUrl    = aws_sqs_queue.telemetry_queue.url
    MessageBody = "$request.body"
  }
}

resource "aws_apigatewayv2_route" "telemetry_route" {
  api_id    = aws_apigatewayv2_api.telemetry_api.id
  route_key = "POST /telemetry"
  target    = "integrations/${aws_apigatewayv2_integration.sqs_integration.id}"
}

resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.telemetry_api.id
  name        = "$default"
  auto_deploy = true
}

# ==============================================================================
# 3. DYNAMODB: PERSISTENCIA MULTI-TENANT AISLADA
# ==============================================================================

resource "aws_dynamodb_table" "sessions" {
  name         = "neuroflex-sessions-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"
  range_key    = "session_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "session_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Project     = "NeuroFlex VR"
    Environment = var.environment
    Compliance  = "Ley-21719"
  }
}

# ==============================================================================
# 4. LAMBDA: PROCESAMIENTO Y VALIDACIÓN ASÍNCRONA
# ==============================================================================

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../src/process_session.py"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_lambda_function" "session_processor" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "neuroflex-session-processor-${var.environment}"
  role             = data.aws_iam_role.lab_role.arn
  handler          = "process_session.handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime          = "python3.11"
  timeout          = 15
  memory_size      = 256

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.sessions.name
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn = aws_sqs_queue.telemetry_queue.arn
  function_name    = aws_lambda_function.session_processor.arn
  batch_size       = 10
  enabled          = true
}

# ==============================================================================
# OUTPUTS PARA VERIFICACIÓN CLÍNICA Y FORENSE
# ==============================================================================

output "telemetry_endpoint" {
  description = "URL publica HTTPS para que Meta Quest 3 transmita sesiones"
  value       = "${aws_apigatewayv2_api.telemetry_api.api_endpoint}/telemetry"
}

output "sqs_queue_url" {
  value = aws_sqs_queue.telemetry_queue.url
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.sessions.name
}