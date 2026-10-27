# Kong AI Gateway — Enterprise AI Chat & DLP Firewall & MCP Server

This repository contains a complete Proof of Concept (PoC) demonstrating how to secure AI Chat systems and Agentic workflows using the **Kong AI Gateway** as an enterprise perimeter. Initially built for Volvo Cars (DNS TAPIR experiment), this project uses Kong to enforce strict Data Loss Prevention (DLP) rules, log AI usage for GDPR, intelligently route large language model requests, and securely proxy Model Context Protocol (MCP) tool calls to local datasets.

## 🚀 Getting Started (How to Run)

Follow these steps to initialize the environment, start the AI gateway, run the web dashboard, and test the MCP agent loop.

### 1. Environment Setup

First, configure your environment variables:
```bash
cp .env.example .env
```
Edit `.env` and fill in your `OPENROUTER_API_KEY` and the path to your Kong license file (`KONG_LICENSE_PATH`).

### 2. Start the Infrastructure & Dashboard

The master script will start Docker containers, configure Kong, create a Python virtual environment, install dependencies, and launch the web dashboard:
```bash
./start.sh
```
Once running, access the Chat Dashboard locally at `http://localhost:8080`.

### 3. Manual Python Environment Setup (Optional)

If you need to manually activate the virtual environment and install requirements (e.g., to run the agent separately):
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 4. Running the Secure MCP Server and Agent

To test the agentic tool-calling loop, you need to run the MCP server and the agent in separate terminal windows.

**Terminal 1: Start the MCP Server**
This server reads from the `data/` folder and exposes tools via SSE on port 5000.
```bash
source .venv/bin/activate
python mcp_server.py
```

**Terminal 2: Run the Agent CLI**
This connects to the LLM and the MCP server *through* the secure Kong proxy.
```bash
source .venv/bin/activate
python mcp_agent.py
```
You can now ask the agent questions like: "What is in the employee records?"

---

## 📂 Architecture & Directory Structure

This project is divided into several interconnected layers:

### 📁 Root Configuration & Scripts
- **`docker-compose.yml`**: Spins up the core infrastructure (Kong API Gateway and PostgreSQL). Mounts the required Kong license file securely.
- **`start.sh`**: The master orchestration script. Starts Docker, configures Kong, sets up the virtual environment, and boots the FastAPI web server.
- **`setup_kong.sh`**: Programmatically configures the Kong AI Gateway via its Admin API. Creates routes and injects core plugins: `rate-limiting`, `ai-prompt-guard` (DLP), `ai-prompt-decorator`, and `file-log`.
- **`setup_mcp_kong.sh`**: Configures Kong routes specifically for the MCP server, allowing SSE handshake and JSON-RPC messages to securely pass through the gateway.
- **`test_mcp_kong.sh`**: Test script to verify the Kong MCP proxy route functionality.
- **`requirements.txt`**: Declares the Python packages necessary (e.g., `fastapi`, `uvicorn`, `mcp`) for the application.
- **`.env` / `.env.example`**: Environment variables holding secrets. `.env` is ignored by git.

### 📁 Application Backend & Agent Loop
- **`main.py`**: The FastAPI Python backend serving as a bridge between the frontend and the Kong proxy. It exposes the `/api/chat` route.
- **`mcp_server.py`**: An MCP (Model Context Protocol) server built with FastMCP. It exposes local file search capabilities from the `data/` folder as tools for the LLM.
- **`mcp_agent.py`**: A CLI agent that connects to the LLM via Kong and securely queries the MCP server. It handles the iterative tool-calling agentic loop.
- **`agent_output.txt`**: A log file where agent outputs or traces might be logged or demonstrated.

### 📁 Frontend UI
- **`static/index.html`**: The sleek, modern frontend Chat UI. It displays the chat interface and the dynamic **Live Request Journey Pipeline**, polling the backend for real-time trace updates.
- **`static/` (folder)**: Contains the frontend assets for the web dashboard.

### 📁 Documentation & Data
- **`data/` (folder)**: Contains mock dataset files (CSV, TXT) such as employee records, vehicle specs, and security policies for the MCP server to query.
- **`dlp_test_cases.md`**: A collection of prompts used to test the `ai-prompt-guard` configurations (PII, IP leaks, Prompt Injections).
- **`ARCHITECTURE_FLOW.md`**: Detailed flow document explaining the architecture pipeline in depth.

---

## 🔒 Security Capabilities (Kong Plugins)

All AI traffic flows through Kong's active plugins defined in the setup scripts:

1. **`ai-prompt-decorator`**: Automatically injects enterprise system instructions so the AI responds as a helpful assistant.
2. **`ai-prompt-guard`**: The DLP bouncer. Using optimized Regular Expressions, it instantly scans payloads for Credit Cards, Swedish Identity Numbers, Volvo VINs, automotive IP ("ecu data dump"), and Prompt Injections ("ignore previous instructions"). Dropped requests never reach the public internet.
3. **`rate-limiting`**: Restricts users to 5 prompts per minute natively at the gateway.
4. **`file-log`**: Dumps successful traffic and dropped threats to `/tmp/kong-dns-tapir.log` for GDPR Article 30 auditing.

---

**Built as part of the Volvo DNS TAPIR internal evaluation for Securing AI Systems.**
