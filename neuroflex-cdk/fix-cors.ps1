@'
$env:AWS_PAGER=""
$apiId = "4zh475jp96"
$region = "us-east-1"

Write-Host "1. Buscando recurso /sessions en API Gateway..." -ForegroundColor Cyan
$resourcesJson = aws apigateway get-resources --rest-api-id $apiId --region $region --no-cli-pager
$resources = ($resourcesJson | ConvertFrom-Json).items
$sessionsResource = $resources | Where-Object { $_.path -eq "/sessions" }

if (-not $sessionsResource) {
    Write-Host "Error: No se encontró el recurso /sessions" -ForegroundColor Red
    exit
}

$resourceId = $sessionsResource.id
Write-Host "Recurso /sessions encontrado (ID: $resourceId)" -ForegroundColor Green

Write-Host "2. Habilitando método OPTIONS (Preflight) y respuesta MOCK..." -ForegroundColor Cyan

aws apigateway put-method --rest-api-id $apiId --resource-id $resourceId --http-method OPTIONS --authorization-type NONE --region $region --no-cli-pager 2>$null

aws apigateway put-integration --rest-api-id $apiId --resource-id $resourceId --http-method OPTIONS --type MOCK --request-templates '{"application/json":"{\"statusCode\": 200}"}' --region $region --no-cli-pager

aws apigateway put-method-response --rest-api-id $apiId --resource-id $resourceId --http-method OPTIONS --status-code 200 --response-models '{"application/json":"Empty"}' --response-parameters '{"method.response.header.Access-Control-Allow-Headers":true,"method.response.header.Access-Control-Allow-Methods":true,"method.response.header.Access-Control-Allow-Origin":true}' --region $region --no-cli-pager

aws apigateway put-integration-response --rest-api-id $apiId --resource-id $resourceId --http-method OPTIONS --status-code 200 --response-parameters '{"method.response.header.Access-Control-Allow-Headers":"''Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token''","method.response.header.Access-Control-Allow-Methods":"''GET,OPTIONS,POST''","method.response.header.Access-Control-Allow-Origin":"''*''"}' --region $region --no-cli-pager

Write-Host "3. Configurando Gateway Responses para errores 4XX, 5XX y UNAUTHORIZED..." -ForegroundColor Cyan
Set-Content -Path params.json -Value '{"gatewayresponse.header.Access-Control-Allow-Origin":"''*''","gatewayresponse.header.Access-Control-Allow-Headers":"''Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token''"}' -Encoding ASCII

aws apigateway put-gateway-response --rest-api-id $apiId --response-type DEFAULT_4XX --response-parameters file://params.json --region $region --no-cli-pager
aws apigateway put-gateway-response --rest-api-id $apiId --response-type UNAUTHORIZED --response-parameters file://params.json --region $region --no-cli-pager
aws apigateway put-gateway-response --rest-api-id $apiId --response-type DEFAULT_5XX --response-parameters file://params.json --region $region --no-cli-pager

Remove-Item params.json -ErrorAction SilentlyContinue

Write-Host "4. Desplegando los cambios en el Stage v1..." -ForegroundColor Cyan
aws apigateway create-deployment --rest-api-id $apiId --stage-name v1 --region $region --no-cli-pager

Write-Host "¡CORS configurado y desplegado exitosamente!" -ForegroundColor Green
'@ | Set-Content -Path fix-cors.ps1 -Encoding UTF8

.\fix-cors.ps1