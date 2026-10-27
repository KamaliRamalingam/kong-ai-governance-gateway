#!/bin/bash

# Test RBAC enforcement with developer role

echo "Testing RBAC RBAC - Developer trying to access admin files"
echo "============================================================"

# Test 1: Fleet Analytics
echo ""
echo "Test 1: Developer requesting 'Show me the fleet analytics report'"
curl -s -X POST http://localhost:8000/api/agent-chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me the fleet analytics report", "role": "developer"}' | head -100

echo ""
echo ""
echo "Test 2: Developer requesting 'What is the maintenance budget breakdown?'"
curl -s -X POST http://localhost:8000/api/agent-chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the maintenance budget breakdown?", "role": "developer"}' | head -100

echo ""
echo ""
echo "Test 3: Admin requesting 'What is the maintenance budget breakdown?' (should work)"
curl -s -X POST http://localhost:8000/api/agent-chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the maintenance budget breakdown?", "role": "admin"}' | head -100

echo ""
echo ""
echo "Test 4: Developer with safe query 'Show me public vehicle policies'"
curl -s -X POST http://localhost:8000/api/agent-chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me public vehicle policies", "role": "developer"}' | head -100
