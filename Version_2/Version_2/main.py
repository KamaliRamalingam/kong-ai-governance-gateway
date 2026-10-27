from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import time
import random
import json
import asyncio
import glob
import os
import re
from datetime import datetime
from typing import Optional

# ══════════════════════════════════════════════════════════════════════
# VOLVO ENTERPRISE DLP POLICY PACK
# Enforced on BOTH input (user prompts) and output (AI responses)
# Policy: volvo-enterprise-dlp v2.1
# ══════════════════════════════════════════════════════════════════════

# ── MASK patterns: replace value with REDACTED ─────────────────────────
_MASK_RULES = [
    # Vehicle Telemetry ID  (VEH-123456)
    (re.compile(r'\bVEH-[0-9]{6,12}\b'),                                           "Volvo Vehicle Telemetry ID"),
    # VIN  (17-char chassis number, excludes I/O/Q)
    (re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b'),                                        "Vehicle Identification Number (VIN)"),
    # Swedish personnummer — long form YYYYMMDD-XXXX  e.g. 20240504-1234
    (re.compile(r'\b\d{8}[-+]\d{4}\b'),                                             "Swedish Personal ID number (personnummer)"),
    # Swedish personnummer — short form YYMMDD-XXXX  e.g. 900101-1234
    (re.compile(r'\b\d{6}[-+]\d{4}\b'),                                             "Swedish Personal ID number (personnummer, short)"),
    # Email
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),         "Email address"),
    # Phone (E.164 style, 7-15 digits)
    (re.compile(r'\+?[1-9]\d{6,14}\b'),                                             "Phone number"),
    # EU license plate  (e.g. ABC 123, XY-1234)
    (re.compile(r'\b[A-Z]{2,3}[\- ]?[A-Z0-9]{3,4}\b'),                             "Vehicle license plate"),
    # IPv4
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),                                    "IP address"),
    # Driver license (generic alphanumeric 6-15 chars)
    (re.compile(r'\b[A-Z]{1,3}[0-9]{5,12}\b'),                                      "Driver license number"),
    # --- IMPROVED FINANCIAL REDACTION ---
    # Currency with full amounts (captures SEK 4,200,000.00 etc)
    (re.compile(r'(?:SEK|USD|EUR|\$|€|¥)\s*\b\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?\b'), "Currency amount"),
    # Large numbers / financial figures (captures 4,200,000 or 1234567)
    (re.compile(r'\b\d{1,3}(?:[,\s]\d{3})+(?:\.\d{2})?\b'),                         "Financial number"),
    # Any 5+ digit number (fallback for unscreened IDs or large values)
    (re.compile(r'\b\d{5,}\b'),                                                      "Large numerical value"),
    # Partial budget patterns (fallback)
    (re.compile(r'\b\d+(?:,\d{3})*\b'),                                              "General budget number"),
    # SSN-like patterns (XXX-XX-XXXX)
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),                                          "Social Security Number"),
    # UUID/GUID patterns
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I), "System UUID"),
    # JWT/Bearer tokens (long base64-like strings)
    (re.compile(r'\beyJ[A-Za-z0-9\-_.]+\.([A-Za-z0-9\-_]+\.)?[A-Za-z0-9\-_]+\b'),  "JWT Token"),
    # API Keys (alphanumeric strings 32+ chars that look like credentials)
    (re.compile(r'\b[a-zA-Z0-9]{32,}\b'),                                           "Potential API key/credential"),
    # Bank account numbers (IBAN or similar)
    (re.compile(r'\b[A-Z]{2}\d{2}(?:\s?\d{4}){2,}(?:\s?\d{1,4})?\b'),              "Bank account (IBAN)"),
]

# ── BLOCK patterns: entire request is rejected ─────────────────────────
_BLOCK_RULES = [
    (
        re.compile(r'\b\d{8}[-+]\d{4}\b|\b\d{6}[-+]\d{4}\b'),
        "Swedish Personal Identity Number (personnummer)",
        "The prompt contains a Swedish Personal Identity Number (personnummer) in the format YYYYMMDD-XXXX "
        "or YYMMDD-XXXX (e.g. 20240504-1234). This is a national identifier and falls under GDPR "
        "Special Category data. Sharing Swedish personnummer with an AI model is strictly prohibited "
        "under Volvo's Privacy Policy and Swedish GDPR implementation (Dataskyddslagen). "
        "Kong AI Gateway has blocked this request to prevent identity data from reaching the LLM."
    ),
    (
        re.compile(r'\b-?\d{1,2}\.\d{3,},\s*-?\d{1,3}\.\d{3,}\b'),
        "GPS/location coordinates",
        "The prompt contains GPS coordinates. Sharing or logging real-time location data "
        "is prohibited under the Volvo Privacy Policy and GDPR Article 5. Location data "
        "is classified as high-risk PII and is always BLOCKED to prevent driver tracking."
    ),
    (
        re.compile(r'\b(?:\d[ \-]?){13,16}\b'),
        "Credit card number",
        "The prompt contains what appears to be a credit card number. Payment card data "
        "is strictly prohibited in AI prompts per PCI-DSS compliance. Kong AI Gateway has "
        "blocked this request before it reached the LLM to prevent financial data exposure."
    ),
    (
        re.compile(r'\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b'),
        "JWT authentication token",
        "The prompt contains a JWT or bearer token. Embedding authentication credentials "
        "in AI prompts is a critical security risk — it could expose session tokens to the LLM "
        "provider. Kong DLP has blocked this request to prevent credential leakage."
    ),
    (
        re.compile(r'(?i)(api[_\-]?key|client_secret|private_key|secret_key|password\s*=|internal\s+endpoint)'),
        "API key / internal credential / secret",
        "The prompt attempts to include an API key, secret, or reference to an internal endpoint. "
        "Secrets must never be sent to an LLM. Kong DLP blocked this to protect Volvo's "
        "internal infrastructure from accidental credential exposure."
    ),
    (
        re.compile(r'(?i)(list\s+all\s+customers|vehicle\s+owner\s+details|location\s+history|dump\s+(all|data|records))'),
        "Sensitive bulk-data intent query",
        "The prompt requests bulk customer records or location history. This type of query "
        "violates Volvo's data minimisation principle (GDPR Art. 5(1)(c)) and RBAC policy. "
        "Only authorised analytics dashboards may access aggregated data — not AI chat."
    ),
    (
        re.compile(r'(?i)(track\s+driver|monitor\s+(user|driver)\s+behav|real[\-\s]?time\s+vehicle\s+track|can\s+bus|ecu\s+data\s+dump|telematics)'),
        "Behavioral tracking or vehicle telematics exfiltration",
        "The prompt attempts to access driver behaviour patterns, CAN-bus data, or ECU telemetry. "
        "Real-time tracking and raw vehicle data are proprietary automotive IP. Kong has blocked "
        "this request to prevent industrial espionage and protect driver privacy."
    ),
    (
        re.compile(r'(?i)(ignore\s+previous\s+instructions|you\s+are\s+now|forget\s+your\s+rules|act\s+as\s+|jailbreak|bypass\s+(security|filter|guard))'),
        "Prompt injection / jailbreak attempt",
        "The prompt contains language patterns consistent with a prompt injection or jailbreak attack "
        "(e.g. 'ignore previous instructions', 'act as'). Kong's ai-prompt-guard plugin detected "
        "this attempt to override security rules and blocked it before reaching Gemini."
    ),
]

# ── HIGH-RISK CORRELATION: VIN + Name + Location together → BLOCK ──────
def _high_risk_correlation(text: str) -> bool:
    has_vin  = bool(re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', text))
    has_loc  = bool(re.search(r'\b-?\d{1,2}\.\d{3,},\s*-?\d{1,3}\.\d{3,}\b', text))
    has_name = bool(re.search(r'(?i)(name|driver|customer|owner)\s*[:\.=]?\s*[A-Z][a-z]+ [A-Z][a-z]+', text))
    return has_vin and has_loc and has_name

def mask_sensitive_data(text: str) -> str:
    """Apply MASK rules to replace identifiers with REDACTED (used on both input and output)."""
    if not text:
        return text
    for pattern, _ in _MASK_RULES:
        text = pattern.sub('[REDACTED]', text)
    return text

def check_block_policy(text: str) -> Optional[str]:
    """
    Check BLOCK rules. Returns a human-readable block explanation string,
    or None if the text is clean and should be allowed through.
    """
    if not text:
        return None

    # High-risk correlation check first (VIN + Name + Location together)
    if _high_risk_correlation(text):
        return (
            "HIGH-RISK CORRELATION DETECTED — This prompt simultaneously contains a Vehicle VIN, "
            "a person's name, and GPS location data. Combining these identifiers creates a unique "
            "individual profile that is classified as Special Category data under GDPR. "
            "Kong has escalated this to an immediate BLOCK to prevent de-anonymisation of Volvo customers."
        )

    for pattern, label, explanation in _BLOCK_RULES:
        if pattern.search(text):
            return explanation

    return None  # Clean — allow through

def identify_block_reason(text: str) -> str:
    """Legacy helper: returns a short reason label (used for log entries)."""
    result = check_block_policy(text)
    if result:
        # Return first sentence only for log labels
        return result.split('.')[0]
    # Fallback: check mask-only violations for context
    found = [label for pattern, label in _MASK_RULES if pattern.search(text)]
    if found:
        return f"Prompt contained maskable PII: {', '.join(found)}"
    return "Unidentified prohibited content — prompt injection or policy violation"


# ═══════════════════════════════════════════════════════════════
# VOLVO RBAC — Data Access Clusters (3 tiers)
#
# DEVELOPER cluster  → public + operational data, no PII
# ADMIN cluster      → developer files + internal strategic data (no PII)
# RESTRICTED         → never served, blocked at MCP + Kong layers
# ═══════════════════════════════════════════════════════════════

# Tier 1: Developer cluster (public, operational, non-sensitive)
DEVELOPER_FILES = {
    "vehicle_specs.csv",       # Model specs — public operational data
    "service_logs.csv",        # Service work orders — operational, non-PII IDs only
    "public_policies.txt",     # Public-facing policies
}

# Tier 2: Admin-only cluster (internal strategic, no personal PII)
# Admins see DEVELOPER_FILES + these
ADMIN_ONLY_FILES = {
    "fleet_analytics_report.txt",   # Aggregated fleet stats, no individual PII
    "maintenance_budget_q1.txt",    # Internal finance/budget data
    "supplier_contracts_summary.txt", # Commercial supplier data
    "rd_roadmap_2024.txt",          # Strategic R&D project status
}

ADMIN_FILES = DEVELOPER_FILES | ADMIN_ONLY_FILES  # Union: all accessible files

# Tier 3: Restricted — blocked at MCP server level + Kong ai-prompt-guard
# Listed here for documentation. Python NEVER exposes these.
RESTRICTED_FILES_DOC = {
    "customer_data.csv",            # Personal PII — GDPR Special Category
    "employee_records.csv",         # HR/salary data — GDPR Special Category
    "internal_security_policy.txt", # Operational security risk
}

ROLE_LABELS = {
    "developer": "Developer (Tier 1 — public + operational data)",
    "admin":     "Administrator (Tier 1+2 — includes internal strategic data)",
}

# ── Keywords for detecting admin-only file requests ──
ADMIN_FILE_KEYWORDS = {
    "fleet analytics": "fleet_analytics_report.txt",
    "fleet analytics report": "fleet_analytics_report.txt",
    "maintenance budget": "maintenance_budget_q1.txt",
    "q1 budget": "maintenance_budget_q1.txt",
    "budget breakdown": "maintenance_budget_q1.txt",
    "supplier contract": "supplier_contracts_summary.txt",
    "supplier contracts": "supplier_contracts_summary.txt",
    "r&d project": "rd_roadmap_2024.txt",
    "rd project": "rd_roadmap_2024.txt",
    "r&d roadmap": "rd_roadmap_2024.txt",
    "rd roadmap": "rd_roadmap_2024.txt",
    "2024 roadmap": "rd_roadmap_2024.txt",
    "r&d 2024": "rd_roadmap_2024.txt",
}

def detect_admin_file_request(prompt: str) -> tuple[bool, str]:
    """
    Detect if user is asking about admin-only files.
    Returns (is_admin_request, filename_hint)
    """
    prompt_lower = prompt.lower()
    for keyword, filename in ADMIN_FILE_KEYWORDS.items():
        if keyword in prompt_lower:
            return True, filename
    return False, ""

def rbac_filter_list(content: str, role: str) -> str:
    """Filter list_available_files output based on role."""
    allowed = ADMIN_FILES if role == "admin" else DEVELOPER_FILES
    lines = content.split("\n")
    filtered = [l for l in lines
                if not l.startswith("- ") or l[2:].strip() in allowed]
    return "\n".join(filtered)

def rbac_filter_fetch(content: str, role: str) -> str:
    """Filter fetch_documents output to only include role-allowed files."""
    allowed = ADMIN_FILES if role == "admin" else DEVELOPER_FILES
    sections = content.split("\n\n")
    result = []
    for sec in sections:
        if not sec.startswith("--- File:"):
            result.append(sec)
            continue
        first_line = sec.split("\n")[0]
        fname = first_line.replace("--- File:", "").replace("---", "").strip()
        if fname in allowed:
            result.append(sec)
        else:
            # STRICT DENIAL MESSAGE FOR DEVELOPERS (Requirement: everytime it should say you donot have admin acess)
            if role == "developer" and fname in ADMIN_ONLY_FILES:
                result.append(
                    f"--- File: {fname} ---\n"
                    f"⛔ ACCESS DENIED: You do not have Admin access. This dataset is restricted to Administrator roles only."
                )
            else:
                tier = "Admin" if fname in ADMIN_ONLY_FILES else "Restricted"
                result.append(
                    f"--- File: {fname} ---\n"
                    f"[ACCESS DENIED — {tier.upper()} TIER] "
                    f"Your current role ({role.upper()}) does not have permission to view this file. "
                    f"{'Request Admin access to view internal strategic datasets.' if tier == 'Admin' else 'This file contains classified PII and is blocked for all AI access by Volvo Security Policy.'}"
                )
    return "\n\n".join(result)



app = FastAPI(title="Volvo DNS TAPIR Security Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

KONG_URL = "http://localhost:8000/ai"
GEMINI_MODEL = "google/gemini-2.0-flash-001"

query_logs = []

class DNSQuery(BaseModel):
    domain: str
    user_ip: Optional[str] = "0.0.0.0"
    username: Optional[str] = "anonymous"
    scenario_type: Optional[str] = None

class PromptQuery(BaseModel):
    message: str
    role: Optional[str] = "developer"  # "developer" | "admin"

@app.post("/api/analyze")
async def analyze_dns(query: DNSQuery):
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"Analyze this DNS query: user {query.username} from IP {query.user_ip} visited {query.domain}. Provide threat assessment."
    try:
        # ── Volvo DLP pre-flight block check ──
        block_reason = check_block_policy(message)
        if block_reason:
            elapsed = round((time.time() - start_time) * 1000)
            log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                         "username": "[REDACTED]", "threat_level": "BLOCKED",
                         "reason": block_reason[:120], "latency_ms": elapsed, "status": "blocked"}
            query_logs.append(log_entry)
            return {"threat_level": "BLOCKED",
                    "analysis": f"⛔ VOLVO DLP POLICY BLOCKED \u2014 {block_reason}",
                    "latency_ms": elapsed, "sanitized": True}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                KONG_URL,
                json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": mask_sensitive_data(message)}]},
                headers={"Content-Type": "application/json"}
            )
        elapsed = round((time.time() - start_time) * 1000)
        if response.status_code == 429:
            log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                         "username": "[REDACTED]", "threat_level": "BLOCKED",
                         "reason": "Rate limit exceeded by Kong Gateway", "latency_ms": elapsed, "status": "rate_limited"}
            query_logs.append(log_entry)
            raise HTTPException(status_code=429, detail="Rate limit exceeded - Kong Gateway blocked this request")
        data = response.json()
        if "error" in data and "prompt pattern is blocked" in str(data.get("error", "")):
            reason = identify_block_reason(message)
            log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                         "username": "[REDACTED]", "threat_level": "BLOCKED",
                         "reason": reason, "latency_ms": elapsed, "status": "blocked"}
            query_logs.append(log_entry)
            return {"threat_level": "BLOCKED", "analysis": f"⛔ VOLVO DLP POLICY BLOCKED \u2014 {reason}.",
                    "latency_ms": elapsed, "sanitized": True}
        ai_response = mask_sensitive_data(data["choices"][0]["message"]["content"])
        threat_level = "UNKNOWN"
        if "HIGH" in ai_response.upper(): threat_level = "HIGH"
        elif "MEDIUM" in ai_response.upper(): threat_level = "MEDIUM"
        elif "LOW" in ai_response.upper(): threat_level = "LOW"
        log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                     "username": "[REDACTED]", "threat_level": threat_level, "analysis": ai_response,
                     "latency_ms": elapsed, "tokens_used": data.get("usage", {}).get("total_tokens", 0), "status": "analyzed"}
        query_logs.append(log_entry)
        return {"threat_level": threat_level, "analysis": ai_response, "latency_ms": elapsed,
                "tokens_used": data.get("usage", {}).get("total_tokens", 0), "sanitized": True, "timestamp": timestamp}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-prompt-injection")
async def test_prompt_injection(query: PromptQuery):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        block_reason = check_block_policy(query.message)
        if block_reason:
            log_entry = {"timestamp": timestamp, "domain": "PROMPT_INJECTION_ATTEMPT", "user_ip": "[REDACTED]",
                         "username": "[REDACTED]", "threat_level": "BLOCKED",
                         "reason": block_reason[:120], "latency_ms": 0, "status": "blocked"}
            query_logs.append(log_entry)
            return {"blocked": True, "message": f"⛔ VOLVO DLP POLICY BLOCKED \u2014 {block_reason}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                KONG_URL,
                json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": mask_sensitive_data(query.message)}]},
                headers={"Content-Type": "application/json"}
            )
        data = response.json()
        if "error" in data:
            reason = identify_block_reason(query.message)
            log_entry = {"timestamp": timestamp, "domain": "PROMPT_INJECTION_ATTEMPT", "user_ip": "[REDACTED]",
                         "username": "[REDACTED]", "threat_level": "BLOCKED",
                         "reason": reason, "latency_ms": 0, "status": "blocked"}
            query_logs.append(log_entry)
            return {"blocked": True, "message": f"⛔ VOLVO DLP POLICY BLOCKED \u2014 {reason}."}
        ai_response = mask_sensitive_data(data["choices"][0]["message"]["content"])
        return {"blocked": False, "message": ai_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat_with_ai(query: PromptQuery):
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # ── Volvo DLP pre-flight block check ──
        block_reason = check_block_policy(query.message)
        if block_reason:
            elapsed = round((time.time() - start_time) * 1000)
            return {"blocked": True, "message": f"⛔ VOLVO DLP POLICY BLOCKED \u2014 {block_reason}",
                    "latency_ms": elapsed, "threat_level": "BLOCKED"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                KONG_URL,
                json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": mask_sensitive_data(query.message)}]},
                headers={"Content-Type": "application/json"}
            )
        elapsed = round((time.time() - start_time) * 1000)
        
        if response.status_code == 429:
            return {"blocked": True, "message": "⛔ Rate limit exceeded — Kong Gateway blocked this request (max 5 requests/min per user)",
                    "latency_ms": elapsed, "threat_level": "BLOCKED"}
            
        data = response.json()
        if "error" in data and "prompt pattern is blocked" in str(data.get("error", "")):
            reason = identify_block_reason(query.message)
            return {"blocked": True, "message": f"⛔ VOLVO DLP POLICY BLOCKED \u2014 {reason}.",
                    "latency_ms": elapsed, "threat_level": "BLOCKED"}
            
        ai_response = mask_sensitive_data(data["choices"][0]["message"]["content"])
        log_entry = {"timestamp": timestamp, "domain": "CHAT_MESSAGE", "user_ip": "[REDACTED]",
                     "username": "[REDACTED]", "threat_level": "LOW", "analysis": ai_response,
                     "latency_ms": elapsed, "tokens_used": data.get("usage", {}).get("total_tokens", 0), "status": "analyzed"}
        query_logs.append(log_entry)
        return {"blocked": False, "message": ai_response, "latency_ms": elapsed, "threat_level": "LOW"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/demo")
async def demo_analyze(query: DNSQuery):
    """Demo endpoint — works without Kong. Handles both keyword matching and typed scenarios."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_time = time.time()
    stype = query.scenario_type

    if stype == "cache":
        fake_latency = random.randint(12, 45)
        tokens_saved = random.randint(180, 380)
        analysis = (
            f"⚡ SEMANTIC CACHE HIT — Zero AI Cost\n\n"
            f"Domain: {query.domain}\n"
            f"Cache status: HIT — Semantically similar query found in Kong cache\n"
            f"Response time: {fake_latency}ms (vs ~320ms for a live AI call)\n\n"
            f"Kong's AI Semantic Cache identified this query as semantically similar to a previous "
            f"request and returned the cached analysis instantly — no AI model was called.\n\n"
            f"✓ Tokens saved: {tokens_saved} (Gemini never received this request)\n"
            f"✓ Cost saved: ~${tokens_saved * 0.000002:.4f} for this single request\n"
            f"✓ GDPR protections still applied to the cache lookup\n\n"
            f"At Volvo scale: 60%+ of repeated security queries can be served from cache, "
            f"dramatically reducing AI API spend without compromising security coverage."
        )
        log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                     "username": "[REDACTED]", "threat_level": "CACHE_HIT", "analysis": analysis,
                     "latency_ms": fake_latency, "tokens_used": 0, "tokens_saved": tokens_saved,
                     "cache_hit": True, "status": "cached"}
        query_logs.append(log_entry)
        return {"threat_level": "CACHE_HIT", "analysis": analysis, "latency_ms": fake_latency,
                "tokens_used": 0, "tokens_saved": tokens_saved, "cache_hit": True,
                "sanitized": True, "timestamp": timestamp, "demo_mode": True}

    if stype == "auth":
        fake_latency = random.randint(8, 22)
        analysis = (
            f"🔐 ACCESS DENIED — Authentication Failed\n\n"
            f"Source IP: {query.user_ip}\n"
            f"Reason: API key absent or invalid — JWT token not present\n\n"
            f"Kong's Key Authentication plugin verified the inbound request and found no valid "
            f"API key. The JWT Authentication plugin also checked for a valid Azure AD / Okta "
            f"token — none found.\n\n"
            f"RESULT: Request rejected at the gateway perimeter.\n"
            f"✓ Zero AI cost incurred\n"
            f"✓ Zero Volvo data exposed\n"
            f"✓ Attack attempt logged for GDPR Article 30 audit trail\n"
            f"✓ Security alert dispatched to SIEM via HTTP Log plugin\n\n"
            f"Only Volvo employees with credentials issued by Azure AD can access the AI Gateway. "
            f"External attackers and unauthorised systems are blocked unconditionally."
        )
        log_entry = {"timestamp": timestamp, "domain": "api.volvo-ai-gateway.internal",
                     "user_ip": "[REDACTED]", "username": "[REDACTED]",
                     "threat_level": "AUTH_BLOCKED", "reason": "Invalid API key — access denied",
                     "latency_ms": fake_latency, "status": "auth_blocked"}
        query_logs.append(log_entry)
        return {"threat_level": "AUTH_BLOCKED", "analysis": analysis, "latency_ms": fake_latency,
                "tokens_used": 0, "sanitized": True, "timestamp": timestamp, "demo_mode": True}

    if stype == "circuit":
        fake_latency = random.randint(280, 520)
        analysis = (
            f"⚠️ CIRCUIT BREAKER ACTIVATED — Automatic Failover\n\n"
            f"Primary Model: Gemini 2.0 Flash — UNHEALTHY (5 failures in 10s)\n"
            f"Circuit state: OPEN → traffic diverted to backup\n"
            f"Fallback Model: Claude Haiku (selected by AI Proxy Advanced)\n"
            f"Recovery time: {fake_latency}ms including failover\n\n"
            f"Kong's Circuit Breaker plugin detected consecutive failures from the primary AI model "
            f"and automatically opened the circuit to stop cascading failures.\n\n"
            f"Kong AI Proxy Advanced instantly evaluated remaining healthy models and routed "
            f"traffic to Claude Haiku — zero manual intervention required.\n\n"
            f"✓ Zero downtime for Volvo manufacturing and security systems\n"
            f"✓ Automatic recovery — circuit closes when primary model recovers\n"
            f"✓ All model switches logged for SLA reporting and governance\n\n"
            f"WITHOUT KONG: A downed AI model would cause Volvo's security monitoring to fail silently."
        )
        log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                     "username": "[REDACTED]", "threat_level": "CIRCUIT_OPEN",
                     "reason": "Primary AI model unhealthy — circuit breaker triggered, failover active",
                     "latency_ms": fake_latency, "status": "circuit_open"}
        query_logs.append(log_entry)
        return {"threat_level": "CIRCUIT_OPEN", "analysis": analysis, "latency_ms": fake_latency,
                "tokens_used": random.randint(80, 200), "fallback_model": "claude-haiku",
                "sanitized": True, "timestamp": timestamp, "demo_mode": True}

    if stype == "routing":
        fake_latency = random.randint(160, 320)
        analysis = (
            f"🔀 AI PROXY ADVANCED — Smart Model Routing\n\n"
            f"Request type: DNS threat analysis\n"
            f"Models evaluated: Gemini 2.0 Flash, Claude Haiku, GPT-4o-mini\n\n"
            f"Routing decision: Gemini 2.0 Flash\n"
            f"Reason: Optimal cost-quality balance for security classification tasks\n"
            f"• Cost: $0.0001 / 1K tokens ✓ (most cost-efficient viable model)\n"
            f"• Latency: {fake_latency}ms ✓ (within SLA)\n"
            f"• Quality score: 94/100 ✓ (for threat classification tasks)\n"
            f"• Current load: 18% ✓ (healthy capacity)\n\n"
            f"Load Balancer distributed this request across 3 Gemini endpoints.\n\n"
            f"✓ Volvo AI spend optimised — 40% cost reduction vs single-model setup\n"
            f"✓ Best model chosen automatically per request type\n"
            f"✓ All routing decisions logged for cost accountability and auditing"
        )
        log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
                     "username": "[REDACTED]", "threat_level": "ROUTED",
                     "reason": "AI Proxy Advanced selected optimal model",
                     "latency_ms": fake_latency, "status": "routed"}
        query_logs.append(log_entry)
        return {"threat_level": "ROUTED", "analysis": analysis, "latency_ms": fake_latency,
                "tokens_used": random.randint(120, 280), "model_selected": "gemini-2.0-flash",
                "sanitized": True, "timestamp": timestamp, "demo_mode": True}

    # Default: keyword-based DNS scenario matching
    domain = query.domain.lower()

    HIGH_KEYWORDS = [
        'malware', 'c2', 'botnet', 'phishing', 'hack', 'evil', 'virus',
        'ransomware', 'exfil', 'darknet', 'shell', 'exploit', 'trojan',
        'keylog', 'spyware', '.ru', '.xyz', '.tk', '.pw', 'login-volvo',
        'secure-update', 'cdn-delivery', 'key-server', 'dark', 'onion',
        'beacon', 'stager', 'payload', 'inject', 'bypass', 'rootkit'
    ]
    MEDIUM_KEYWORDS = ['suspicious', 'unknown', 'proxy', 'tunnel', 'anon', 'cdn-free']

    threat_reasons = {
        'malware': 'malware distribution network',
        'c2': 'command-and-control infrastructure',
        'botnet': 'botnet beacon endpoint',
        'phishing': 'credential phishing campaign',
        'ransomware': 'ransomware key retrieval server',
        'exfil': 'data exfiltration channel',
        'darknet': 'darknet relay node',
        '.ru': 'high-risk geolocation (RU TLD)',
        '.xyz': 'disposable TLD commonly used in attacks',
        'login-volvo': 'Volvo brand impersonation / typosquatting',
        'key-server': 'encryption key server (ransomware staging)',
        'beacon': 'C2 beacon communication',
        'payload': 'malware payload staging server',
    }

    threat_level = "LOW"
    reason = "no threat indicators"
    matched = next((k for k in HIGH_KEYWORDS if k in domain), None)
    if matched:
        threat_level = "HIGH"
        reason = threat_reasons.get(matched, "known malicious pattern")
    elif any(k in domain for k in MEDIUM_KEYWORDS):
        threat_level = "MEDIUM"
        reason = "suspicious characteristics"

    templates = {
        "HIGH": (
            f"🔴 THREAT CONFIRMED — HIGH RISK\n\n"
            f"Domain: {query.domain}\n"
            f"Classification: {reason.upper()}\n\n"
            f"Kong AI Gateway has identified this domain as a HIGH-risk threat. "
            f"The domain exhibits strong indicators of {reason}. "
            f"All PII has been redacted before AI processing (GDPR Art. 5 compliant). "
            f"IP address and username replaced with [REDACTED] in audit log. "
            f"Recommendation: BLOCK immediately and isolate the source device."
        ),
        "MEDIUM": (
            f"🟡 SUSPICIOUS ACTIVITY — MEDIUM RISK\n\n"
            f"Domain: {query.domain}\n"
            f"Classification: {reason.upper()}\n\n"
            f"Kong AI Gateway flagged this domain for review. "
            f"It shows {reason}. "
            f"PII redacted per GDPR. Recommend security team investigation."
        ),
        "LOW": (
            f"🟢 SAFE TRAFFIC — LOW RISK\n\n"
            f"Domain: {query.domain}\n"
            f"Classification: NORMAL BUSINESS TRAFFIC\n\n"
            f"Kong AI Gateway confirmed this domain is safe. "
            f"No threat indicators detected. "
            f"Request processed normally. PII redacted before AI processing as per GDPR compliance."
        ),
    }

    fake_latency = round((time.time() - start_time) * 1000) + random.randint(180, 420)
    log_entry = {
        "timestamp": timestamp, "domain": query.domain, "user_ip": "[REDACTED]",
        "username": "[REDACTED]", "threat_level": threat_level, "analysis": templates[threat_level],
        "latency_ms": fake_latency,
        "tokens_used": random.randint(120, 380) if threat_level != "BLOCKED" else 0,
        "status": "demo"
    }
    query_logs.append(log_entry)
    return {"threat_level": threat_level, "analysis": templates[threat_level],
            "latency_ms": fake_latency, "tokens_used": log_entry["tokens_used"],
            "sanitized": True, "timestamp": timestamp, "demo_mode": True}


@app.get("/api/logs")
async def get_logs():
    return {"logs": list(reversed(query_logs[-50:]))}


@app.get("/api/stats")
async def get_stats():
    total = len(query_logs)
    high = sum(1 for l in query_logs if l.get("threat_level") == "HIGH")
    medium = sum(1 for l in query_logs if l.get("threat_level") == "MEDIUM")
    low = sum(1 for l in query_logs if l.get("threat_level") == "LOW")
    blocked = sum(1 for l in query_logs if l.get("threat_level") in ("BLOCKED", "AUTH_BLOCKED"))
    cache_hits = sum(1 for l in query_logs if l.get("threat_level") == "CACHE_HIT")
    tokens_saved = sum(l.get("tokens_saved", 0) for l in query_logs)
    pii_redacted = sum(1 for l in query_logs if l.get("threat_level") not in ("AUTH_BLOCKED",) and l.get("status") != "auth_blocked")
    avg_latency = round(sum(l.get("latency_ms", 0) for l in query_logs) / total) if total > 0 else 0
    return {
        "total_queries": total,
        "high_threats": high,
        "medium_threats": medium,
        "low_threats": low,
        "blocked_requests": blocked,
        "cache_hits": cache_hits,
        "tokens_saved": tokens_saved,
        "pii_redacted": pii_redacted,
        "avg_latency_ms": avg_latency
    }


# ══ MCP AGENT CHAT (Server-Sent Events) ═══════════════════════════════════════════════════════════════
KONG_MCP_URL = "http://localhost:8000/mcp/sse"
MAX_TOOL_LOOPS = 5

async def agent_chat_stream(message: str, role: str = "developer"):
    """Run the MCP agentic loop and stream each step as an SSE event."""

    def evt(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    role_label = ROLE_LABELS.get(role, role)
    allowed_files = list(DEVELOPER_FILES) if role == "developer" else "all files"

    try:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession

        yield evt("step", {"stage": "source", "msg": f"Prompt received — Role: {role.upper()}"})
        yield evt("step", {"stage": "kong", "msg": "Kong DLP scan — running Volvo policy pack..."})
        await asyncio.sleep(0.3)

        # ── Volvo DLP pre-flight block check ──
        block_reason = check_block_policy(message)
        if block_reason:
            yield evt("blocked", {"msg": f"⛔ VOLVO DLP POLICY BLOCKED — {block_reason}"})
            return

        # ── RBAC pre-flight: Check if developer is requesting admin files ──
        is_admin_req, filename_hint = detect_admin_file_request(message)
        if is_admin_req and role == "developer":
            yield evt("blocked", {
                "msg": f"⛔ ACCESS DENIED: You do not have admin access to file '{filename_hint}'. "
                       f"Only administrators can view this file. Your current role is: DEVELOPER."
            })
            return

        try:
            async with sse_client(KONG_MCP_URL) as streams:
                async with ClientSession(streams[0], streams[1]) as mcp:
                    await mcp.initialize()

                    tools_response = await mcp.list_tools()
                    tool_names = [t.name for t in tools_response.tools]
                    llm_tools = [{
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema
                        }
                    } for t in tools_response.tools]

                    yield evt("step", {"stage": "mcp_discover", "msg": f"MCP tools discovered: {', '.join(tool_names)}"})

                    # Build role-aware system prompt
                    if role == "developer":
                        access_note = (
                            f"You have DEVELOPER access. You may ONLY reference these files: "
                            f"{', '.join(sorted(DEVELOPER_FILES))}.\n"
                            f"If asked about employee records, customer data, or internal security policies, "
                            f"respond that those files require Admin access and are not available to your role."
                        )
                    else:
                        access_note = (
                            "You have ADMIN access. You may access ALL files including confidential datasets "
                            "(employee records, customer data, internal security policies)."
                        )

                    system_prompt = (
                        f"You are a helpful and secure Enterprise AI assistant for Volvo Cars.\n"
                        f"Current user role: {role_label}\n"
                        f"{access_note}\n"
                        "IMPORTANT SECURITY RULES:\n"
                        "- Never reveal raw VINs, emails, phone numbers, GPS coordinates, or API keys in responses.\n"
                        "- If you find sensitive data in documents, refer to it generically.\n"
                        "- Always call list_available_files first, then fetch_documents.\n"
                        "- Do NOT write Python or code blocks — use actual tool calls only.\n"
                        "- Respond concisely and professionally as a Volvo enterprise assistant."
                    )
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": mask_sensitive_data(message)}
                    ]

                    async with httpx.AsyncClient(timeout=60.0) as http:
                        for _ in range(MAX_TOOL_LOOPS):
                            yield evt("step", {"stage": "kong", "msg": "Kong — routing to LLM (ai-proxy)..."})

                            resp = await http.post(
                                KONG_URL,
                                json={"model": GEMINI_MODEL, "messages": messages, "tools": llm_tools},
                                headers={"Content-Type": "application/json"}
                            )
                            data = resp.json()

                            if "error" in data:
                                err_msg = str(data["error"])
                                if "prompt pattern is blocked" in err_msg:
                                    reason = identify_block_reason(message)
                                    yield evt("blocked", {"msg": f"⛔ VOLVO DLP POLICY BLOCKED — {reason}."})
                                else:
                                    display_msg = data["error"].get("message", err_msg) if isinstance(data["error"], dict) else err_msg
                                    yield evt("blocked", {"msg": f"⛔ Kong gateway error: {display_msg}"})
                                return

                            llm_msg = data["choices"][0].get("message", {})

                            # No more tool calls → final answer
                            if not llm_msg.get("tool_calls"):
                                yield evt("step", {"stage": "ai", "msg": "Gemini responded ✓"})
                                yield evt("step", {"stage": "verdict", "msg": "Response delivered"})
                                final_text = mask_sensitive_data(llm_msg.get("content", ""))
                                yield evt("answer", {"msg": final_text})
                                return

                            messages.append(llm_msg)

                            for tc in llm_msg["tool_calls"]:
                                fn = tc["function"]["name"]
                                args = json.loads(tc["function"]["arguments"])
                                yield evt("step", {"stage": "mcp_call", "msg": f"🛠 LLM called {fn}({args})"})
                                yield evt("step", {"stage": "kong_mcp", "msg": "Kong — routing to MCP server..."})

                                tool_result = await mcp.call_tool(fn, arguments=args)
                                result_text = "\n".join(c.text for c in tool_result.content if c.type == "text")

                                # ── RBAC filter: redact files the role cannot access ──
                                if fn == "list_available_files":
                                    result_text = rbac_filter_list(result_text, role)
                                elif fn == "fetch_documents":
                                    result_text = rbac_filter_fetch(result_text, role)

                                yield evt("step", {"stage": "mcp_result", "msg": f"MCP returned {len(result_text)} chars [{role.upper()} access]"})

                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": result_text,
                                    "name": fn
                                })

                        yield evt("error", {"msg": "Reached max tool iterations without a final answer."})

        except (ConnectionRefusedError, OSError, TimeoutError) as conn_err:
            yield evt("error", {"msg":
                f"⚠️ MCP Server is not running. Start it in a separate terminal:\n"
                f"  source .venv/bin/activate && python mcp_server.py\n"
                f"  (Error: {conn_err})"
            })
            return
        except BaseException as eg:
            # Catch Python 3.11+ ExceptionGroup from asyncio TaskGroup
            err_name = type(eg).__name__
            if "ExceptionGroup" in err_name or "TaskGroup" in str(eg):
                yield evt("error", {"msg":
                    "⚠️ Cannot connect to MCP Server — it may not be running.\n"
                    "Start it in a separate terminal:\n"
                    "  source .venv/bin/activate && python mcp_server.py"
                })
            else:
                yield evt("error", {"msg": f"MCP error ({err_name}): {str(eg)[:200]}"})
            return

    except Exception as e:
        yield evt("error", {"msg": f"Gateway error: {str(e)[:300]}"})


@app.post("/api/agent-chat")
async def agent_chat(query: PromptQuery):
    return StreamingResponse(
        agent_chat_stream(query.message, role=query.role or "developer"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
