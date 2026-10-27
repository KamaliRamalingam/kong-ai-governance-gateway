#!/bin/bash
set -e

# Load environment variables robustly
if [ -f .env ]; then
  # Use allexport to export all variables from the sourced file
  set -a
  source .env
  set +a
fi

if [ -z "$KONG_LICENSE_PATH" ] || [ -z "$OPENROUTER_API_KEY" ]; then
  echo "Error: KONG_LICENSE_PATH and OPENROUTER_API_KEY must be set in .env"
  exit 1
fi

echo "Waiting for Kong Admin API to be ready..."
until curl -s http://localhost:8001 > /dev/null; do
  echo "Kong is unavailable - sleeping 2 seconds"
  sleep 2
done
echo "Kong Admin API is up!"

echo "Applying Kong Enterprise License..."
LICENSE_CONTENT=$(cat "$KONG_LICENSE_PATH" | jq -c .)
curl -i -X POST http://localhost:8001/licenses/ \
  --header "Content-Type: application/json" \
  -d "{\"payload\": $(jq -Rs . <<< "$LICENSE_CONTENT")}"

echo "Creating AI Service..."
curl -i -X POST http://localhost:8001/services \
  --data name=openrouter-service \
  --data url=https://openrouter.ai/api/v1/chat/completions

echo "Creating AI Route..."
curl -i -X POST http://localhost:8001/services/openrouter-service/routes \
  --data "paths[]=/ai" \
  --data name=openrouter-route \
  --data "protocols[]=http" \
  --data "protocols[]=https"

echo "Adding Request Transformer Plugin..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=request-transformer \
  --data "config.add.headers[]=Authorization:Bearer $OPENROUTER_API_KEY" \
  --data "config.add.headers[]=Content-Type:application/json"

echo "Adding AI Prompt Decorator Plugin (Volvo Enterprise System Prompt)..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-decorator \
  --data "config.prompts.prepend[1].role=system" \
  --data "config.prompts.prepend[1].content=You are a secure and professional Enterprise AI assistant for Volvo Cars. You help team members with code, analysis, and operational questions. You NEVER reveal raw VINs, emails, GPS coordinates, API keys, or other sensitive data in your responses. If sensitive data appears in retrieved documents, refer to it generically. Always maintain Volvo's enterprise security posture."

echo "--- VOLVO DLP POLICY PACK v2.0 ---"
echo "Adding Kong ai-prompt-guard: BLOCK GPS Coordinates..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=-?\d{1,2}\.\d{3,},\s*-?\d{1,3}\.\d{3,}"

echo "Adding Kong ai-prompt-guard: BLOCK Credit Card Numbers..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=(?:\d[ -]?){13,16}"

echo "Adding Kong ai-prompt-guard: BLOCK JWT Tokens & API Keys..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+" \
  --data-urlencode "config.deny_patterns[2]=api[_-]?key|client_secret|private_key|secret_key|password\s*=|internal\s+endpoint"

echo "Adding Kong ai-prompt-guard: BLOCK Sensitive Intent Queries..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=(?i)(list all customers|vehicle owner details|location history|dump all|dump data|dump records)"

echo "Adding Kong ai-prompt-guard: BLOCK Behavioral Tracking & Vehicle Telematics..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=(?i)(track driver|monitor user behav|monitor driver behav|real.?time vehicle track|can bus|ecu data dump|telematics)"

echo "Adding Kong ai-prompt-guard: BLOCK Prompt Injection & Jailbreak Attempts..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=(?i)(ignore previous instructions|you are now|forget your rules|act as |jailbreak|bypass security|bypass filter|bypass guard)"

echo "Adding Kong ai-prompt-guard: BLOCK requests for RESTRICTED PII files by name..."
# Kong-first protection: deny any prompt that explicitly requests restricted files
# These files contain customer PII, employee records, or security architecture
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=(?i)(customer_data\.csv|employee_records\.csv|internal_security_policy\.txt)"

echo "Adding Rate Limiting Plugin..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=rate-limiting \
  --data config.minute=5 \
  --data config.policy=local

echo "Adding Audit Logging Plugin..."
curl -i -X POST http://localhost:8001/services/openrouter-service/plugins \
  --data name=file-log \
  --data config.path=/tmp/kong-dns-tapir.log \
  --data config.reopen=true

echo "==========================================="
echo "Kong AI Gateway is fully configured!"
echo "==========================================="
