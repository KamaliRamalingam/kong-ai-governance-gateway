#!/bin/bash
set -e

# 1. Check for .env file
if [ ! -f .env ]; then
  echo "Error: .env file not found!"
  echo "Please copy .env.example to .env and fill in your KONG_LICENSE_PATH and OPENROUTER_API_KEY."
  exit 1
fi

echo "==========================================="
echo "Starting Volvo DNS TAPIR Kong Infrastructure"
echo "==========================================="

# 2. Start Kong infrastructure with Docker Compose
echo "Clearing old Kong setup to apply new Regex rules..."
docker compose down -v --remove-orphans || docker-compose down -v --remove-orphans

echo "Starting Docker Compose (Kong & Postgres)..."
docker compose up -d || docker-compose up -d

# 3. Configure Kong Plugins (wait for Kong to be healthy)
echo "Configuring Kong AI Service and LLM Plugins..."
./setup_kong.sh

echo "Configuring Kong MCP Service and Route..."
./setup_mcp_kong.sh

echo "==========================================="
echo "Infrastructure Ready. Starting Dashboard..."
echo "==========================================="

# 4. Create and activate Python virtual environment
if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

# 5. Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# 6. Start FastAPI Dashboard using uvicorn
echo "Starting Uvicorn web server on http://localhost:8080..."
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
