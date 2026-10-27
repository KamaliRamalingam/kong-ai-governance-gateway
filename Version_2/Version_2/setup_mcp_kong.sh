#!/bin/bash
# setup_mcp_kong.sh — Configure Kong routes for MCP Server
set -e

echo "Waiting for Kong Admin API to be ready..."
until curl -s http://localhost:8001 > /dev/null; do
  sleep 2
done

# ── MCP Service (points to MCP server running on host) ──────────────────────
echo "Creating MCP Service..."
curl -s -X POST http://localhost:8001/services \
  --data name=mcp-service \
  --data url=http://host.docker.internal:5000 || true

# ── Route 1: /mcp → MCP SSE endpoint (strips /mcp prefix) ──────────────────
echo "Creating /mcp route (SSE handshake)..."
curl -s -X POST http://localhost:8001/services/mcp-service/routes \
  --data "paths[]=/mcp" \
  --data name=mcp-route \
  --data "strip_path=true" \
  --data "protocols[]=http" \
  --data "protocols[]=https" || true

# ── Route 2: /messages/ → MCP POST endpoint (keeps /messages/ path) ─────────
# The MCP SSE server tells clients to POST to /messages/?session_id=...
# Kong must proxy this through WITHOUT stripping the path.
echo "Creating /messages/ route (MCP JSON-RPC messages)..."
curl -s -X POST http://localhost:8001/services/mcp-service/routes \
  --data "paths[]=/messages/" \
  --data name=mcp-messages-route \
  --data "strip_path=false" \
  --data "protocols[]=http" \
  --data "protocols[]=https" || true

# ── DLP: Swedish Personnummer + PII guard on LLM route ────────────────────────
# Swedish personnummer: YYYYMMDD-XXXX (long) or YYMMDD-XXXX (short), e.g. 20240504-1234
DENY_PERSONNUMMER="\b\d{8}[-+]\d{4}\b|\b\d{6}[-+]\d{4}\b"
DENY_PII="\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b|\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"

echo "Applying AI Prompt Guard (Personnummer block) to LLM route..."
curl -s -X POST http://localhost:8001/routes/openrouter-route/plugins \
  --data name=ai-prompt-guard \
  --data "config.match_all_roles=true" \
  --data-urlencode "config.deny_patterns[1]=${DENY_PERSONNUMMER}" \
  --data-urlencode "config.deny_patterns[2]=${DENY_PII}" || true

echo ""
echo "✅ MCP Kong setup complete."
echo "   Routes: /mcp (SSE), /messages/ (JSON-RPC)"
