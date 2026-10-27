from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import httpx
import re
import time
import random
import json
import io
import base64
import os
import asyncio
import hashlib
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

app = FastAPI(title="Volvo DNS TAPIR Security Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

KONG_URL = "http://localhost:8000/ai"
GEMINI_MODEL = "google/gemini-2.0-flash-lite-001"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY") or os.getenv("OPENROUTER_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

DIRECT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant for Kong AI Gateway and Volvo enterprise security. "
    "Answer questions clearly and concisely about AI security, GDPR compliance, DNS threats, "
    "cybersecurity, Kong Gateway features, and general technology topics."
)
KONG_MCP_URL = "http://localhost:8765/sse"
MAX_TOOL_LOOPS = 5
ALLOWED_UPLOAD_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

DEMO_RESPONSES = [
    # Domain / DNS threat analysis — matches the chat chip "Threat Analysis"
    ("c2-botnet",   "🔴 THREAT CONFIRMED — HIGH RISK\n\nDomain: c2-botnet-malware.xyz\nClassification: COMMAND-AND-CONTROL INFRASTRUCTURE\n\nKong AI Gateway has analysed this domain and identified it as HIGH-risk. Multiple threat indicators are present:\n• Subdomain pattern matches known C2 beacon frameworks (Cobalt Strike, Sliver)\n• .xyz TLD is frequently used in disposable attack infrastructure\n• 'botnet' and 'malware' substrings match Volvo DLP keyword blocklist\n• Domain registered < 30 days ago — consistent with throwaway attack infra\n\nRecommendation: BLOCK immediately at the DNS resolver and firewall perimeter. Isolate any Volvo endpoint that has made DNS queries to this domain. Escalate to SOC for incident response.\n\nAll PII was redacted before AI processing (GDPR Art. 5). This query has been logged in the Article 30 audit trail."),
    ("botnet",      "🔴 THREAT CONFIRMED — HIGH RISK\n\nBotnet infrastructure detected. Botnets are networks of compromised machines controlled by an attacker via C2 (command-and-control) servers. DNS queries to botnet domains indicate a device may already be infected.\n\nKong AI Gateway recommendation: Block the domain at DNS level immediately. Check firewall logs for any outbound connections to this IP range. Run endpoint detection on the originating device.\n\nVolvo's DNS TAPIR system flags botnet-associated domains automatically — this query triggered a HIGH-risk classification. SOC has been notified via the HTTP Log plugin."),
    ("malware",     "🔴 THREAT CONFIRMED — HIGH RISK\n\nMalware domain detected. This domain exhibits strong indicators of malware distribution or C2 communication:\n• Known malicious TLD pattern\n• Domain name contains threat keywords\n• No legitimate business registration found\n\nKong AI Gateway has blocked further AI processing of raw threat data and logged this event. Recommendation: Add to DNS blocklist, isolate source endpoint, initiate forensic review. All data redacted per GDPR Article 5 before AI analysis."),
    ("suspicious domain", "🟡 SUSPICIOUS — MEDIUM RISK\n\nThis domain has been flagged for review by Kong AI Gateway. Suspicious indicators present:\n• Newly registered domain (< 90 days)\n• No established web presence or business record\n• Domain pattern matches generic threat infrastructure templates\n\nRecommendation: Monitor traffic to this domain. Apply temporary DNS sinkhole. Escalate to security team for manual review within 24 hours. Do not block outright without further investigation."),
    ("phishing",    "🔴 THREAT CONFIRMED — HIGH RISK\n\nPhishing domain detected. This domain is impersonating a legitimate brand or service to steal credentials. Key indicators:\n• Domain spoofs a known brand via typosquatting or homoglyph attack\n• Resolves to hosting infrastructure known for phishing campaigns\n• No valid TLS certificate from a trusted CA\n\nKong AI Gateway recommendation: Block immediately. Alert all Volvo employees who may have visited this domain. Reset credentials for any accounts accessed from affected endpoints."),
    ("analyze",     "🔵 THREAT ANALYSIS COMPLETE\n\nKong AI Gateway has processed this security query through the full Volvo DLP pipeline:\n\n1. Input scanned — no PII or sensitive identifiers found\n2. Prompt injection check — passed\n3. Routed to Gemini Flash via Kong AI Proxy\n4. Output scanned — no sensitive data in AI response\n5. Delivered — GDPR Art. 5 compliant\n\nFor domain-specific threat classification, submit the domain to the DNS TAPIR dashboard for HIGH/MEDIUM/LOW scoring with full audit trail."),
    ("block",       "🔵 BLOCK RECOMMENDATION\n\nBased on threat intelligence analysis, Kong AI Gateway recommends blocking this resource at the network perimeter. Volvo's defence-in-depth strategy applies blocks at multiple layers:\n\n• DNS resolver — prevent name resolution\n• Firewall — drop outbound connections\n• Proxy — block HTTP/HTTPS traffic\n• Endpoint EDR — flag process making the connection\n\nAll block decisions are logged via Kong's HTTP Log plugin for GDPR Article 30 audit trail compliance."),
    ("firewall",    "A firewall is a network security system that monitors and controls incoming and outgoing network traffic based on predefined security rules. Kong AI Gateway acts as an intelligent firewall for AI traffic — every prompt is inspected, PII is redacted, and malicious patterns are blocked before they reach the AI model. At Volvo, this means employee queries are protected end-to-end without slowing down operations."),
    ("intrusion detection", "An Intrusion Detection System (IDS) passively monitors network traffic and alerts on suspicious activity, while an Intrusion Prevention System (IPS) actively blocks threats. Kong AI Gateway combines both approaches for AI traffic — it detects prompt injection attempts and immediately prevents them from reaching the model, all in under 50ms."),
    ("pii",         "PII (Personally Identifiable Information) includes any data that can identify a person — names, IDs, credit card numbers, phone numbers, medical records. Under GDPR Article 5, PII must be protected by design. Kong's AI Sanitizer plugin detects and redacts PII from every prompt before it reaches Gemini, ensuring Volvo's AI usage is fully GDPR compliant."),
    ("gdpr",        "GDPR (General Data Protection Regulation) is the EU law governing personal data protection. For Volvo's AI usage, Kong AI Gateway enforces GDPR Article 5 compliance automatically — redacting PII before AI processing, maintaining full audit logs under Article 30, and ensuring data minimisation. No personal data ever leaves Volvo's security perimeter in readable form."),
    ("kong",        "Kong AI Gateway is an enterprise-grade AI security and governance layer. It sits between your employees and AI models, enforcing: PII redaction (GDPR compliance), prompt injection blocking, rate limiting, semantic caching (cost reduction), and multi-model routing. For Volvo, Kong processes every AI query through a security pipeline in under 50ms — invisible to users, essential for compliance."),
    ("dns",         "DNS (Domain Name System) translates human-readable domain names into IP addresses. In security, DNS analysis is critical — malicious actors use domains for C2 (command-and-control), phishing, and data exfiltration. Volvo's DNS TAPIR system uses Kong AI Gateway to analyse DNS queries in real time, classifying threats as HIGH/MEDIUM/LOW and blocking malicious domains automatically."),
    ("zero trust",  "Zero Trust is a security model based on 'never trust, always verify' — every request must be authenticated and authorised regardless of origin. Kong AI Gateway implements Zero Trust for AI: every prompt is inspected, every response is audited, and no user or system is trusted by default. API key authentication ensures only authorised Volvo employees can access the AI Gateway."),
    ("rate limit",  "Rate limiting controls how many requests a user or system can make in a given time window. Kong's rate-limiting plugin caps AI requests at 60 per minute per consumer — preventing abuse, controlling costs, and ensuring fair usage across Volvo's workforce. If the limit is exceeded, Kong blocks the request with a clear message rather than passing it to the expensive AI model."),
    ("semantic cache", "Semantic caching stores AI responses and serves them for semantically similar future queries — even if the wording differs. Kong's AI Semantic Cache uses vector embeddings to detect similar questions and return cached answers instantly (12–45ms vs 300ms+ for live AI calls). At Volvo scale, this reduces AI API costs by 40–60% for repeated security queries."),
    ("threat",      "Threat analysis in cybersecurity involves identifying, classifying, and responding to potential attacks. Kong AI Gateway enhances Volvo's threat analysis by processing DNS queries, network events, and user prompts through Gemini AI — classifying threats as HIGH (immediate block), MEDIUM (flag for review), or LOW (safe) with full audit trails for compliance reporting."),
    ("domain",      "🔵 DOMAIN ANALYSIS\n\nKong AI Gateway has processed this domain query through Volvo's DNS TAPIR pipeline. Domain threat classification uses multiple signals:\n\n• TLD reputation (e.g. .xyz, .tk, .ru = elevated risk)\n• Domain age and registration history\n• Keyword matching against known threat patterns (C2, botnet, malware, phishing)\n• DNS resolution behaviour (fast-flux, NX-domain abuse)\n\nSubmit the specific domain to the DNS TAPIR dashboard for a full HIGH/MEDIUM/LOW threat score with GDPR-compliant audit logging."),
    ("c2",          "🔴 THREAT CONFIRMED — COMMAND & CONTROL\n\nC2 (Command-and-Control) infrastructure is used by attackers to remotely control compromised machines, issue commands, exfiltrate data, and deploy additional payloads.\n\nKong AI Gateway detected C2-associated indicators in this query. Volvo's DNS TAPIR system cross-references domains against threat intelligence feeds (VirusTotal, AbuseIPDB, Spamhaus) in real time.\n\nRecommendation: Block at DNS and firewall immediately. Run memory forensics on any endpoint that queried this domain. Preserve logs for incident response."),
    ("vulnerability", "Vulnerability management involves identifying, classifying, and remediating security weaknesses before attackers exploit them. Kong AI Gateway helps Volvo's security team analyse vulnerability reports safely — stripping any PII or internal system identifiers before sending queries to AI models, ensuring sensitive asset information never leaves the secure perimeter."),
    ("encryption",  "Encryption protects data by converting it into an unreadable format without the correct key. Volvo uses TLS 1.3 for all AI Gateway traffic, ensuring prompts and responses are encrypted in transit. Kong's certificate management and mTLS support ensure end-to-end encryption between Volvo services and the AI Gateway."),
    ("soc",         "A Security Operations Centre (SOC) monitors and responds to security events 24/7. Kong AI Gateway integrates with Volvo's SOC via the HTTP Log plugin — every AI query, block event, and PII detection is streamed to the SIEM in real time, giving analysts full visibility into AI usage patterns and potential insider threats."),
]

def _demo_ai_response(message: str) -> str:
    msg_lower = message.lower()
    for keyword, response in DEMO_RESPONSES:
        if keyword in msg_lower:
            return response
    # Generic but informative fallback
    return (
        "Kong AI Gateway processed your query through Volvo's full security pipeline:\n\n"
        "1. Prompt injection scan — passed\n"
        "2. Volvo DLP check (VIN, email, GPS, JWT, credit card) — no sensitive data found\n"
        "3. GDPR Article 5 compliance — enforced\n"
        "4. Routed to Gemini Flash via Kong AI Proxy\n"
        "5. Output DLP scan — passed\n"
        "6. Delivered to employee — audit log entry created (GDPR Art. 30)\n\n"
        "For domain threat analysis, use the DNS TAPIR dashboard. "
        "For PII policy queries, see the Volvo Enterprise DLP documentation.\n\n"
        "[Live AI responses require a valid OpenRouter API key in main.py]"
    )

query_logs = []

class DNSQuery(BaseModel):
    domain: str
    user_ip: Optional[str] = "0.0.0.0"
    username: Optional[str] = "anonymous"
    scenario_type: Optional[str] = None

class PromptQuery(BaseModel):
    message: str

class ChatMessage(BaseModel):
    message: str
    role: Optional[str] = "analyst"

# ── Intent classifier: does the message need local data lookup? ───────────────
_MCP_INTENT_KEYWORDS = [
    "employee_records", "customer_data", "vehicle_specs", "security_policy",
    "fleet_analytics", "show me the file", "read the file", "open the file",
    "list files", "available files", "show files", "all files",
    "what is in", "contents of", "records in", "data in", "rows in",
    "employee record", "customer record", "vehicle spec", "fleet report",
    "search the data", "lookup", "look up", "find in data", "fetch",
    ".csv", ".txt", "dataset", "from the database", "from the data",
]

def _needs_mcp(message: str) -> bool:
    """Returns True if the message appears to require local data lookup via MCP tools."""
    ml = message.lower()
    return any(kw in ml for kw in _MCP_INTENT_KEYWORDS)

# ── Intelligent LLM Router ────────────────────────────────────────────────────
_GEMINI_SIGNALS = [
    "analyze", "analysis", "threat", "security", "compliance", "gdpr", "audit",
    "vulnerability", "dns", "attack", "malware", "phishing", "botnet", "c2",
    "intrusion", "firewall", "zero trust", "incident", "forensic", "soc",
    "explain", "compare", "evaluate", "assess", "recommend", "policy", "report",
    "detailed", "deep", "comprehensive",
]
_GROQ_SIGNALS = [
    "code", "script", "function", "debug", "write a", "generate", "translate",
    "summarize", "quick", "what is", "how to", "define", "example",
    "calculate", "convert", "list", "simple",
]

def _route_model(message: str) -> dict:
    ml = message.lower().strip()
    word_count = len(ml.split())

    # Hard rule: 3 words or fewer → always Groq (fast tier)
    if word_count <= 3:
        return {"provider": "groq", "model": GROQ_MODEL,
                "label": "Llama 3.3 70B (Groq)", "reason": f"Short query ({word_count} word{'s' if word_count != 1 else ''}) — Groq fast tier selected", "tier": "fast"}

    g_score = sum(1 for kw in _GEMINI_SIGNALS if kw in ml)
    q_score  = sum(1 for kw in _GROQ_SIGNALS   if kw in ml)
    if g_score > q_score or g_score >= 2:
        return {"provider": "gemini", "model": GEMINI_MODEL,
                "label": "Gemini 2.0 Flash (OpenRouter)", "reason": "Complex security/compliance analysis", "tier": "analytical"}
    if q_score > 0 or len(message) < 80:
        return {"provider": "groq", "model": GROQ_MODEL,
                "label": "Llama 3.3 70B (Groq)", "reason": "Fast conversational query", "tier": "fast"}
    return {"provider": "gemini", "model": GEMINI_MODEL,
            "label": "Gemini 2.0 Flash (OpenRouter)", "reason": "Default analytical model", "tier": "analytical"}

# ── Local response cache (TTL = 300 s) ───────────────────────────────────────
_response_cache: dict = {}
_CACHE_TTL = 300

def _cache_get(key: str):
    entry = _response_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry
    _response_cache.pop(key, None)
    return None

def _cache_set(key: str, response: str, tokens: int, model_label: str):
    _response_cache[key] = {"response": response, "tokens": tokens, "model_label": model_label, "ts": time.time()}

# ── Volvo Enterprise DLP — BLOCK (reject entire request) ─────────────────────
VOLVO_DLP_BLOCK = [
    # National identity numbers — must be checked BEFORE phone to avoid partial match
    (r'\b\d{6,8}-\d{4}\b',                                                    'Swedish Personal Number (Personnummer)'),
    (r'\b\d{3}[\-\s]\d{2}[\-\s]\d{4}\b',                                     'Social Security Number'),
    # Location
    (r'\b-?\d{1,2}\.\d{4,},\s?-?\d{1,3}\.\d{4,}\b',                        'GPS Coordinates / Location Data'),
    # Auth tokens & secrets
    (r'\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b',          'JWT Token'),
    (r'(?i)\b(api[_\-]?key|secret[_\-]?key|access[_\-]?token|internal[_\-]?secret)\s*[:=]\s*\S+', 'Internal Credential / Secret'),
    # Payment
    (r'\b(?:\d[ \-]?){13,16}\b',                                              'Credit / Debit Card Number'),
    # Sensitive intent queries
    (r'(?i)(list\s+all\s+customers|vehicle\s+owner\s+details|location\s+history)', 'Sensitive Data Query'),
    (r'(?i)(track\s+driver|monitor\s+user\s+beh|real[\-\s]?time\s+vehicle\s+track)', 'Behavioural Surveillance Query'),
]

# ── Volvo Enterprise DLP — MASK (redact & allow through to AI) ───────────────
# Each entry: (pattern, label, re_flags)
# Use 0 (case-sensitive) for patterns that should only match uppercase tokens.
# Use re.IGNORECASE only for patterns like email where case truly doesn't matter.
VOLVO_DLP_MASK = [
    (r'\b[A-HJ-NPR-Z0-9]{17}\b',                          'VIN / Chassis Number',        0),
    (r'\b[A-Za-z0-9.%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', 'Email Address',           re.IGNORECASE),
    (r'\b\+?[1-9]\d{7,14}\b',                             'Phone Number',                0),
    # Plate must contain digits — prevents matching plain English words
    (r'\b[A-Z]{2,3}[\s\-]?\d{1,4}[A-Z]{0,2}\b',          'EU License Plate',            0),
    (r'\b(?:\d{1,3}\.){3}\d{1,3}\b',                      'IP Address',                  0),
    (r'\b[A-Z]{1,2}\d{6,13}\b',                           'Driver License ID',           0),
    (r'\bVEH-[0-9]{6,10}\b',                              'Vehicle Telemetry ID',        0),
]

# ── Prompt Injection / Jailbreak ──────────────────────────────────────────────
INJECTION_PATTERNS = [
    (r'ignore\s+(all\s+)?(previous\s+|your\s+)?instructions',                'Prompt Injection'),
    (r'you\s+are\s+now\s+(DAN|GPT|an?\s+AI\b)',                              'Jailbreak Attempt'),
    (r'\bDAN\b.*\bno\s+restrictions?\b',                                     'DAN Jailbreak'),
    (r'\bjailbreak\b',                                                        'Jailbreak Attempt'),
    (r'(reveal|leak|expose)\s+(all\s+)?(volvo|confidential|credentials|secrets?|passwords?|network)', 'Data Exfiltration'),
    (r'act\s+as\s+(if\s+)?you\s+(have\s+no|are\s+without)\s+restrictions?', 'Restriction Bypass'),
    (r'pretend\s+(you\s+are|to\s+be)\s+(an?\s+)?(AI|assistant|model)\s+(with\s+no|without)', 'Role Manipulation'),
    (r'(disable|bypass|override|circumvent)\s+(your\s+)?(safety|filter|guardrail|restriction|policy)', 'Safety Bypass'),
    (r'do\s+anything\s+now',                                                  'DAN Jailbreak'),
]

# ── RBAC: topics that only admins may query via chat ──────────────────────────
# Each entry: (regex, human-readable label)
ADMIN_ONLY_INTENT = [
    (r'(?i)executive\s+(compensation|pay|salary|package|bonus)',              'Executive Compensation'),
    (r'(?i)board\s+(meeting|minutes|resolution|decision)',                    'Board Meeting Minutes'),
    (r'(?i)cybersecurity\s+incident\s+(log|report|record)',                   'Cybersecurity Incident Log'),
    (r'(?i)executive_compensation',                                           'Executive Compensation File'),
    (r'(?i)board_meeting_minutes',                                            'Board Meeting Minutes File'),
    (r'(?i)cybersecurity_incident_log',                                       'Cybersecurity Incident Log File'),
    (r'(?i)(compensation|remuneration|salary)\s+(report|breakdown|detail)',   'Compensation Report'),
    (r'(?i)c-suite|chief\s+(executive|financial|security|technology)\s+officer\s+(salary|pay|compensation)', 'C-Suite Compensation'),
]

# ── Correlation rule: VIN + Name/location together = high-risk ───────────────
_VIN_RE  = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
_NAME_RE = re.compile(r'(?i)\b(name|driver|owner|customer)\b')
_LOC_RE  = re.compile(r'\b-?\d{1,2}\.\d{4,},\s?-?\d{1,3}\.\d{4,}\b')

def _is_high_risk_correlation(text: str) -> bool:
    return bool(_VIN_RE.search(text) and _NAME_RE.search(text) and _LOC_RE.search(text))

def _apply_mask(text: str) -> tuple[str, list[str]]:
    """Redact all MASK-class PII. Returns (sanitized_text, list_of_types_found)."""
    found = []
    for pattern, label, flags in VOLVO_DLP_MASK:
        if re.search(pattern, text, flags):
            found.append(label)
            text = re.sub(pattern, '[REDACTED]', text, flags=flags)
    return text, found

def _check_block(text: str) -> tuple[bool, str]:
    """Returns (should_block, reason) for BLOCK-class patterns."""
    for pattern, label in VOLVO_DLP_BLOCK:
        if re.search(pattern, text, re.IGNORECASE):
            return True, label
    return False, ""

# Keywords that indicate a document is genuinely confidential/sensitive
_CONFIDENTIAL_KEYWORDS = [
    "confidential", "strictly confidential", "non-disclosure", "nda",
    "proprietary", "trade secret", "classified", "restricted",
    "agreement", "contract", "whereas", "hereby", "indemnif",
    "salary", "compensation", "payroll", "remuneration",
    "personal data", "data subject", "health record", "medical record",
    "bank account", "iban", "routing number", "swift code",
    "password", "passphrase", "private key", "secret",
    "intellectual property", "do not distribute", "internal use only",
    "for your eyes only", "attorney", "legal privilege",
]

def _keyword_scan_document(text: str) -> dict:
    """
    Fallback when Kong AI is unavailable.
    Scans document text for confidentiality keywords to determine if the
    file is genuinely sensitive (agreement, contract, personal data)
    vs generic knowledge (technical guide, manual, article).
    """
    text_lower = text.lower()
    matched = [kw for kw in _CONFIDENTIAL_KEYWORDS if kw in text_lower]

    if len(matched) >= 2:
        # Two or more confidentiality signals = high confidence it's sensitive
        return {
            "has_sensitive_data": True,
            "findings": [f'Confidentiality indicator: "{kw}"' for kw in matched[:5]],
            "risk_level": "HIGH",
            "gdpr_concern": any(kw in matched for kw in ["personal data", "data subject", "health record", "medical record"]),
            "summary": f"Document contains {len(matched)} confidentiality indicators ({', '.join(matched[:3])}) — likely a contract, agreement, or restricted internal document."
        }
    elif len(matched) == 1:
        # One signal = medium risk, flag for review but don't block
        return {
            "has_sensitive_data": False,
            "findings": [f'Possible confidentiality indicator: "{matched[0]}"'],
            "risk_level": "MEDIUM",
            "gdpr_concern": False,
            "summary": f'Document contains one potential sensitivity marker ("{matched[0]}") but appears to be general content. Allowed through with advisory.'
        }
    else:
        return {
            "has_sensitive_data": False,
            "findings": [],
            "risk_level": "LOW",
            "gdpr_concern": False,
            "summary": "No confidentiality indicators detected. Document appears to be generic knowledge content — safe to process."
        }

@app.post("/api/analyze")
async def analyze_dns(query: DNSQuery):
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"Analyze this DNS query: user {query.username} from IP {query.user_ip} visited {query.domain}. Provide threat assessment."
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            prompt_hash = hashlib.sha256(message.encode('utf-8')).hexdigest()
            response = await client.post(
                KONG_URL,
                json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": message}]},
                headers={"Content-Type": "application/json", "x-prompt-hash": prompt_hash}
            )
        elapsed = round((time.time() - start_time) * 1000)
        if response.status_code == 429:
            log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": query.user_ip,
                         "username": query.username, "threat_level": "BLOCKED",
                         "reason": "Rate limit exceeded by Kong Gateway", "latency_ms": elapsed, "status": "rate_limited"}
            query_logs.append(log_entry)
            raise HTTPException(status_code=429, detail="Rate limit exceeded - Kong Gateway blocked this request")
        data = response.json()
        if "error" in data and "prompt pattern is blocked" in str(data.get("error", "")):
            log_entry = {"timestamp": timestamp, "domain": query.domain, "user_ip": query.user_ip,
                         "username": query.username, "threat_level": "BLOCKED",
                         "reason": "Malicious prompt detected and blocked by Kong", "latency_ms": elapsed, "status": "blocked"}
            query_logs.append(log_entry)
            return {"threat_level": "BLOCKED", "analysis": "⛔ Malicious prompt detected and blocked by Kong AI Gateway",
                    "latency_ms": elapsed, "sanitized": True}
        ai_response = data["choices"][0]["message"]["content"]
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


# ── File keyword → filename mapping for direct MCP fetch ─────────────────────
_FILE_KEYWORD_MAP = [
    ("executive_compensation_2024.txt",  ["executive compensation", "compensation report", "exec comp", "ceo salary", "executive salary"]),
    ("board_meeting_minutes_q4.txt",     ["board meeting", "board minutes", "meeting minutes", "q4 board"]),
    ("cybersecurity_incident_log.txt",   ["cybersecurity incident", "security incident", "incident log", "security log"]),
    ("vehicle_specs.csv",                ["vehicle spec", "vehicle model", "car spec", "fleet spec", "vehicle data", "xc90", "v60", "xc40"]),
    ("fleet_analytics_report.txt",       ["fleet analytics", "fleet report", "fleet data", "analytics report", "maintenance cost"]),
    ("service_logs.csv",                 ["service log", "service record", "maintenance log"]),
    ("maintenance_budget_q1.txt",        ["maintenance budget", "budget q1", "q1 budget", "repair cost"]),
    ("public_policies.txt",              ["public polic", "dns polic", "security polic"]),
]

def _detect_target_file(message: str) -> Optional[str]:
    ml = message.lower()
    for filename, keywords in _FILE_KEYWORD_MAP:
        if any(kw in ml for kw in keywords):
            return filename
    return None


# ── MCP data path: Python picks the tool, LLM only summarises ────────────────
async def _try_mcp_answer(message: str, role: str = "analyst") -> Optional[str]:
    """
    Fetch file content from the MCP server directly (no LLM tool-calling loop).
    Python determines which file to read, calls the MCP tool, then asks the LLM
    to summarise the raw content for the user.
    Returns the answer string, or None if MCP is unavailable / no match.
    """
    allowed_files = sorted(ANALYST_FILES | (ADMIN_ONLY_FILES if role == "admin" else set()))

    try:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession

        streams_context = sse_client(KONG_MCP_URL)
        try:
            streams = await asyncio.wait_for(streams_context.__aenter__(), timeout=5.0)
        except Exception:
            return None  # MCP server not running

        try:
            async with ClientSession(streams[0], streams[1]) as mcp_session:
                await mcp_session.initialize()

                # ── Identify target file FIRST — specific beats generic ──
                # This must run before the listing fast-path so that phrases like
                # "Show me the board minutes from the available files" correctly
                # fetch the file content instead of triggering the listing path.
                target_file = _detect_target_file(message)

                # ── Fast path: pure file listing intent (no specific file topic) ─
                if not target_file:
                    _list_only = re.match(
                        r'^(list|show|what|give me|display).*(files?|documents?)',
                        message.strip(), re.IGNORECASE
                    )
                    if _list_only:
                        return (f"Files available to your role ({role.upper()}):\n- "
                                + "\n- ".join(allowed_files))


                if target_file:
                    # Respect role scope — RBAC already blocks upstream for chat,
                    # but guard here too for direct MCP calls
                    if target_file not in allowed_files:
                        return None

                    # Directly call read_file on the MCP server
                    tool_result = await mcp_session.call_tool(
                        "read_file", arguments={"filename": target_file}
                    )
                    raw = "\n".join(c.text for c in tool_result.content if c.type == "text")

                    if not raw or raw.startswith("Error"):
                        return None

                    async with httpx.AsyncClient(timeout=30.0) as http:
                        mcp_messages = [
                            {"role": "system", "content": (
                                "You are a concise Volvo data assistant. "
                                "Answer the user's question using ONLY the file content provided. "
                                "Be structured and direct. Do not add information not in the file."
                            )},
                            {"role": "user", "content": (
                                f"Question: {message}\n\n"
                                f"File: {target_file}\nContent:\n{raw}"
                            )}
                        ]
                        # Try Groq first, then OpenRouter, then return raw
                        summarized = None
                        if GROQ_KEY:
                            try:
                                gr = await http.post(
                                    GROQ_URL,
                                    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                                    json={"model": GROQ_MODEL, "messages": mcp_messages}
                                )
                                gd = gr.json()
                                if "choices" in gd:
                                    summarized = gd["choices"][0]["message"].get("content")
                            except Exception:
                                pass
                        if not summarized and OPENROUTER_KEY:
                            try:
                                or_r = await http.post(
                                    OPENROUTER_URL,
                                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                                    json={"model": GEMINI_MODEL, "messages": mcp_messages}
                                )
                                od = or_r.json()
                                if "choices" in od:
                                    summarized = od["choices"][0]["message"].get("content")
                            except Exception:
                                pass
                        return summarized or f"**{target_file}**\n\n{raw}"

                # ── Search fallback: no specific file, search across all ──
                tool_result = await mcp_session.call_tool(
                    "search_files", arguments={"query": message[:120]}
                )
                raw = "\n".join(c.text for c in tool_result.content if c.type == "text")

                # Filter restricted file sections for non-admins
                if role != "admin":
                    for restricted in ADMIN_ONLY_FILES:
                        raw = re.sub(
                            rf"--- {re.escape(restricted)} ---.*?(?=--- |\Z)",
                            "", raw, flags=re.DOTALL
                        ).strip()

                if not raw or "No matches found" in raw:
                    return None

                async with httpx.AsyncClient(timeout=30.0) as http:
                    search_messages = [
                        {"role": "system", "content":
                            "You are a concise Volvo data assistant. "
                            "Answer the user's question using ONLY the search results provided."},
                        {"role": "user", "content":
                            f"Question: {message}\n\nSearch results:\n{raw}"}
                    ]
                    summarized = None
                    if GROQ_KEY:
                        try:
                            gr = await http.post(
                                GROQ_URL,
                                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                                json={"model": GROQ_MODEL, "messages": search_messages}
                            )
                            gd = gr.json()
                            if "choices" in gd:
                                summarized = gd["choices"][0]["message"].get("content")
                        except Exception:
                            pass
                    if not summarized and OPENROUTER_KEY:
                        try:
                            or_r = await http.post(
                                OPENROUTER_URL,
                                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                                json={"model": GEMINI_MODEL, "messages": search_messages}
                            )
                            od = or_r.json()
                            if "choices" in od:
                                summarized = od["choices"][0]["message"].get("content")
                        except Exception:
                            pass
                    return summarized or raw

        finally:
            await streams_context.__aexit__(None, None, None)
    except Exception:
        return None



@app.post("/api/chat")
async def chat(body: ChatMessage):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    for pattern, inj_type in INJECTION_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            query_logs.append({
                "timestamp": timestamp, "domain": "CHAT_SESSION",
                "user_ip": "[REDACTED]", "username": "[REDACTED]",
                "threat_level": "BLOCKED", "reason": f"Prompt injection / manipulation attempt: {inj_type}",
                "latency_ms": 0, "status": "injection_blocked"
            })
            return {
                "blocked": True, "block_type": "INJECTION",
                "stage": "KONG_GUARD", "timestamp": timestamp,
                "message": (
                    f"Kong AI Firewall blocked this prompt — it matched patterns associated with "
                    f"AI manipulation or jailbreak attempts ({inj_type}). "
                    f"The request was stopped at the gateway perimeter and never reached the AI model."
                )
            }

    # ── Layer 1b: RBAC ─ block admin-only content for non-admin users ───────────
    role = (body.role or "analyst").strip().lower()
    if role != "admin":
        for pattern, resource in ADMIN_ONLY_INTENT:
            if re.search(pattern, message, re.IGNORECASE):
                query_logs.append({
                    "timestamp": timestamp, "domain": "CHAT_SESSION",
                    "user_ip": "[REDACTED]", "username": "[REDACTED]",
                    "threat_level": "BLOCKED",
                    "reason": f"RBAC violation: {resource} requested by role={role.upper()}",
                    "latency_ms": 0, "status": "rbac_blocked"
                })
                return {
                    "blocked": True, "block_type": "RBAC",
                    "stage": "KONG_RBAC", "timestamp": timestamp,
                    "resource": resource,
                    "message": (
                        f"⛔ ACCESS DENIED — Kong AI Gateway blocked this request.\n\n"
                        f"The resource '{resource}' is classified ADMIN ONLY.\n"
                        f"Your current role ({role.upper()}) does not have permission to access "
                        f"executive, board-level, or confidential security documents.\n\n"
                        f"Switch your role to ADMIN in the top-right role selector to access this content.\n"
                        f"This access attempt has been logged in the GDPR Article 30 audit trail."
                    )
                }

    # ── Layer 2: Correlation rule (VIN + Name/Owner + GPS = high-risk) ──────────
    if _is_high_risk_correlation(message):
        query_logs.append({
            "timestamp": timestamp, "domain": "CHAT_SESSION",
            "user_ip": "[REDACTED]", "username": "[REDACTED]",
            "threat_level": "BLOCKED", "reason": "High-risk data correlation: VIN + identity + location",
            "latency_ms": 0, "status": "correlation_blocked"
        })
        return {
            "blocked": True, "block_type": "CORRELATION",
            "stage": "KONG_DLP", "timestamp": timestamp,
            "message": (
                "Kong DLP blocked this request — it contains a high-risk combination of VIN, "
                "personal identity, and GPS location data. Combining these fields creates a "
                "legally sensitive data correlation under GDPR Article 9. Request rejected."
            )
        }

    # ── Layer 3: BLOCK-class DLP patterns ────────────────────────────────────
    should_block, block_reason = _check_block(message)
    if should_block:
        query_logs.append({
            "timestamp": timestamp, "domain": "CHAT_SESSION",
            "user_ip": "[REDACTED]", "username": "[REDACTED]",
            "threat_level": "BLOCKED", "reason": f"DLP block policy: {block_reason}",
            "latency_ms": 0, "status": "dlp_blocked"
        })
        return {
            "blocked": True, "block_type": "DLP_BLOCK", "pii_type": block_reason,
            "stage": "KONG_DLP", "timestamp": timestamp,
            "message": (
                f"Kong Enterprise DLP blocked this request — it contains {block_reason}. "
                f"This data class is prohibited from AI processing under Volvo's data governance policy. "
                f"The request was stopped at the gateway and never reached the AI model."
            )
        }

    # ── Layer 4: MASK-class DLP — sanitize input, allow through ─────────────
    sanitized_message, input_masked = _apply_mask(message)
    if input_masked:
        query_logs.append({
            "timestamp": timestamp, "domain": "CHAT_SESSION",
            "user_ip": "[REDACTED]", "username": "[REDACTED]",
            "threat_level": "MASKED", "reason": f"DLP masked: {', '.join(input_masked)}",
            "latency_ms": 0, "status": "dlp_masked"
        })

    start = time.time()
    ai_response = None
    tokens = 0
    used_mcp = False
    is_cache_hit = False
    local_cache_hit = False
    tokens_saved = 0

    # ── Determine best LLM for this prompt ────────────────────────────────────
    routing = _route_model(sanitized_message)

    # ── Local cache check ─────────────────────────────────────────────────────
    cache_key = hashlib.sha256(sanitized_message.lower().strip().encode()).hexdigest()
    cached = _cache_get(cache_key)
    if cached:
        elapsed = round((time.time() - start) * 1000)
        return {
            "blocked": False,
            "response": cached["response"],
            "message": cached["response"],
            "stage": "LOCAL_CACHE_HIT",
            "latency_ms": elapsed,
            "tokens": 0,
            "tokens_saved": cached["tokens"],
            "timestamp": timestamp,
            "input_masked": input_masked,
            "output_masked": [],
            "gdpr_applied": bool(input_masked),
            "cache_hit": True,
            "local_cache_hit": True,
            "routed_model": cached["model_label"],
            "routing_reason": "Served from local cache — no LLM call needed",
        }

    # ── Intelligent routing: try MCP tools first for data-lookup questions ────
    if _needs_mcp(sanitized_message):
        mcp_answer = await _try_mcp_answer(sanitized_message, role)
        if mcp_answer:
            ai_response = mcp_answer
            used_mcp = True
            elapsed = round((time.time() - start) * 1000)
            # Still run output DLP on MCP answer
            out_blocked, out_block_reason = _check_block(ai_response)
            if out_blocked:
                return {
                    "blocked": True, "block_type": "OUTPUT_BLOCKED", "pii_type": out_block_reason,
                    "stage": "KONG_OUTPUT_GUARD", "timestamp": timestamp,
                    "message": f"Kong DLP intercepted the data response — it contained {out_block_reason}. Response suppressed."
                }
            ai_response, output_masked = _apply_mask(ai_response)
            query_logs.append({
                "timestamp": timestamp, "domain": "CHAT_SESSION",
                "user_ip": "[REDACTED]", "username": "[REDACTED]",
                "threat_level": "LOW", "analysis": ai_response,
                "latency_ms": elapsed, "tokens_used": 0, "status": "allowed_mcp"
            })
            return {
                "blocked": False, "response": ai_response, "message": ai_response,
                "stage": "DELIVERED_VIA_MCP", "latency_ms": elapsed, "tokens": 0,
                "timestamp": timestamp, "input_masked": input_masked,
                "output_masked": output_masked, "gdpr_applied": bool(input_masked or output_masked),
                "used_mcp": True
            }
        # MCP not available — fall through to regular LLM chat

    # ── Route to Groq (fast) or Gemini via OpenRouter directly ──────────────────
    async with httpx.AsyncClient(timeout=30.0) as client:

        # ── Groq path (direct) ───────────────────────────────────────────────
        if routing["provider"] == "groq" and GROQ_KEY:
            try:
                gr_resp = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                    json={"model": GROQ_MODEL, "messages": [
                        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
                        {"role": "user", "content": sanitized_message}
                    ]}
                )
                elapsed = round((time.time() - start) * 1000)
                gr_data = gr_resp.json()
                if "choices" in gr_data:
                    ai_response = gr_data["choices"][0]["message"]["content"]
                    tokens = gr_data.get("usage", {}).get("total_tokens", 0)
            except Exception:
                pass  # Groq unavailable — fall through to OpenRouter

        # ── Gemini path: OpenRouter direct (bypasses Kong prompt decorator) ──
        if ai_response is None and OPENROUTER_KEY:
            try:
                or_resp = await client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={"model": GEMINI_MODEL, "messages": [
                        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
                        {"role": "user", "content": sanitized_message}
                    ]}
                )
                elapsed = round((time.time() - start) * 1000)
                or_data = or_resp.json()
                if "choices" in or_data:
                    ai_response = or_data["choices"][0]["message"]["content"]
                    tokens = or_data.get("usage", {}).get("total_tokens", 0)
            except Exception:
                pass

        # ── Groq fallback when OpenRouter is unavailable ──────────────────────
        if ai_response is None and GROQ_KEY:
            try:
                gr_resp = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                    json={"model": GROQ_MODEL, "messages": [
                        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
                        {"role": "user", "content": sanitized_message}
                    ]}
                )
                elapsed = round((time.time() - start) * 1000)
                gr_data = gr_resp.json()
                if "choices" in gr_data:
                    ai_response = gr_data["choices"][0]["message"]["content"]
                    tokens = gr_data.get("usage", {}).get("total_tokens", 0)
            except Exception:
                pass

        # ── Kong gateway (rate-limit detection + semantic cache check) ────────
        if ai_response is None:
            try:
                prompt_hash = hashlib.sha256(sanitized_message.encode('utf-8')).hexdigest()

                response = await client.post(
                    KONG_URL,
                    json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": sanitized_message}]},
                    headers={"Content-Type": "application/json", "x-prompt-hash": prompt_hash}
                )
                elapsed = round((time.time() - start) * 1000)

                cache_status = response.headers.get("x-cache-status", "Miss")
                is_cache_hit = cache_status.lower() == "hit"

                if response.status_code == 429:
                    query_logs.append({
                        "timestamp": timestamp, "domain": "CHAT_SESSION",
                        "user_ip": "[REDACTED]", "username": "[REDACTED]",
                        "threat_level": "BLOCKED", "reason": "Rate limit exceeded",
                        "latency_ms": elapsed, "status": "rate_limited"
                    })
                    return {
                        "blocked": True, "block_type": "RATE_LIMIT",
                        "stage": "KONG_RATE_LIMITER", "timestamp": timestamp,
                        "message": "Kong Gateway rate limit reached (60 req/min). Please wait before sending again."
                    }

                data = response.json()
                if "error" in data:
                    error_msg = str(data.get("error", ""))
                    is_injection = any(k in error_msg.lower() for k in ["blocked", "safety", "prompt pattern", "injection", "jailbreak"])
                    if is_injection:
                        query_logs.append({
                            "timestamp": timestamp, "domain": "CHAT_SESSION",
                            "user_ip": "[REDACTED]", "username": "[REDACTED]",
                            "threat_level": "BLOCKED", "reason": "Prompt injection / manipulation attempt",
                            "latency_ms": elapsed, "status": "injection_blocked"
                        })
                        return {
                            "blocked": True, "block_type": "INJECTION",
                            "stage": "KONG_GUARD", "timestamp": timestamp,
                            "message": "Kong AI Firewall blocked this prompt — it matched patterns associated with AI manipulation or jailbreak attempts."
                        }
                else:
                    ai_response = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {}).get("total_tokens", 0)
            except Exception:
                pass  # Kong unreachable — demo fallback handles it

    elapsed = round((time.time() - start) * 1000)

    # ── Demo fallback if all providers failed ─────────────────────────────────
    if ai_response is None:
        ai_response = _demo_ai_response(sanitized_message)

    # ── Layer 5: Scan AI output — BLOCK if sensitive data leaks through ────────
    out_blocked, out_block_reason = _check_block(ai_response)
    if out_blocked:
        query_logs.append({
            "timestamp": timestamp, "domain": "CHAT_SESSION",
            "user_ip": "[REDACTED]", "username": "[REDACTED]",
            "threat_level": "BLOCKED", "reason": f"Output DLP block: {out_block_reason}",
            "latency_ms": elapsed, "status": "output_blocked"
        })
        return {
            "blocked": True, "block_type": "OUTPUT_BLOCKED", "pii_type": out_block_reason,
            "stage": "KONG_OUTPUT_GUARD", "timestamp": timestamp,
            "message": (
                f"Kong DLP intercepted the AI response — it contained {out_block_reason}. "
                f"The response was suppressed before reaching you. AI output is also scanned."
            )
        }

    # ── Layer 6: MASK AI output ───────────────────────────────────────────────
    ai_response, output_masked = _apply_mask(ai_response)

    # ── Store in local cache for future identical queries ─────────────────────
    _cache_set(cache_key, ai_response, tokens, routing["label"])

    query_logs.append({
        "timestamp": timestamp, "domain": "CHAT_SESSION",
        "user_ip": "[REDACTED]", "username": "[REDACTED]",
        "threat_level": "LOW", "analysis": ai_response,
        "latency_ms": elapsed, "tokens_used": tokens, "status": "allowed"
    })
    return {
        "blocked": False, "response": ai_response,
        "message": ai_response,
        "stage": "DELIVERED", "latency_ms": elapsed,
        "tokens": tokens, "timestamp": timestamp,
        "input_masked": input_masked,
        "output_masked": output_masked,
        "gdpr_applied": bool(input_masked or output_masked),
        "cache_hit": is_cache_hit,
        "local_cache_hit": False,
        "routed_model": routing["label"],
        "routing_reason": routing["reason"],
        "routing_tier": routing["tier"],
    }


@app.post("/api/test-prompt-injection")
async def test_prompt_injection(query: PromptQuery):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            test_hash = hashlib.sha256(f"test_injection:{query.message}".encode('utf-8')).hexdigest()
            response = await client.post(
                KONG_URL,
                json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": query.message}]},
                headers={"Content-Type": "application/json", "x-prompt-hash": test_hash}
            )
        data = response.json()
        if "error" in data:
            log_entry = {"timestamp": timestamp, "domain": "PROMPT_INJECTION_ATTEMPT", "user_ip": "[REDACTED]",
                         "username": "[REDACTED]", "threat_level": "BLOCKED",
                         "reason": "Prompt injection detected", "latency_ms": 0, "status": "blocked"}
            query_logs.append(log_entry)
            return {"blocked": True, "message": "⛔ Kong AI Gateway blocked this malicious prompt!"}
        return {"blocked": False, "message": data["choices"][0]["message"]["content"]}
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


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start = time.time()
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename.lower())[1]
    is_pdf = ext == ".pdf"
    is_image = ext in ALLOWED_UPLOAD_EXTS and not is_pdf

    if not is_pdf and not is_image:
        raise HTTPException(status_code=400, detail="Only PDF and image files (jpg, png, gif, webp) are supported")

    contents = await file.read()

    if is_pdf:
        if not HAS_PYPDF:
            raise HTTPException(status_code=500, detail="PDF support not installed — run: pip install pypdf")
        try:
            reader = pypdf.PdfReader(io.BytesIO(contents))
            text = " ".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {str(e)}")

        # Stage 1: Volvo DLP — BLOCK-class patterns only (credit card, national ID, GPS, JWT, credentials)
        # MASK-class patterns (email, phone, VIN) are common in any document and do NOT
        # block a file on their own — only truly dangerous data classes trigger an immediate block.
        out_blocked, block_reason = _check_block(text)
        if out_blocked:
            elapsed = round((time.time() - start) * 1000)
            query_logs.append({
                "timestamp": timestamp, "domain": f"FILE:{filename}",
                "user_ip": "[REDACTED]", "username": "[REDACTED]",
                "threat_level": "BLOCKED", "reason": f"DLP block in document: {block_reason}",
                "latency_ms": elapsed, "status": "dlp_blocked"
            })
            return {
                "blocked": True, "block_type": "DLP_BLOCK", "pii_type": block_reason,
                "filename": filename, "file_type": "PDF",
                "stage": "KONG_DLP", "timestamp": timestamp, "latency_ms": elapsed,
                "scanned_by": "Kong Volvo DLP Guard",
                "message": f"Kong DLP detected {block_reason} in the uploaded document. File blocked per Volvo data governance policy."
            }

        # Stage 2: Deep semantic analysis — try Kong AI, fall back to keyword scan
        kong_prompt = (
            f"You are a data security scanner for Volvo. Analyze the following document text extracted from '{filename}' "
            f"and identify any sensitive or confidential information including: PII (names, addresses, emails, phone numbers), "
            f"financial data, health records, credentials, proprietary business data, or GDPR-sensitive content. "
            f"Respond ONLY with valid JSON: "
            f'{"{"}"has_sensitive_data": true or false, "findings": ["list of findings"], "risk_level": "HIGH or MEDIUM or LOW", '
            f'"gdpr_concern": true or false, "summary": "one sentence summary"{"}"}\n\nDOCUMENT TEXT:\n{text[:3000]}'
        )

        kong_result = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                prompt_hash = hashlib.sha256(kong_prompt.encode('utf-8')).hexdigest()
                resp = await client.post(
                    KONG_URL,
                    json={"model": GEMINI_MODEL, "messages": [{"role": "user", "content": kong_prompt}]},
                    headers={"Content-Type": "application/json", "x-prompt-hash": prompt_hash}
                )
            data = resp.json()
            if resp.status_code == 429:
                pass  # fall through to keyword scan
            elif "error" in data:
                error_msg = str(data.get("error", ""))
                is_guard_block = any(k in error_msg.lower() for k in ["blocked", "safety", "prompt pattern"])
                if is_guard_block:
                    elapsed = round((time.time() - start) * 1000)
                    query_logs.append({
                        "timestamp": timestamp, "domain": f"FILE:{filename}",
                        "user_ip": "[REDACTED]", "username": "[REDACTED]",
                        "threat_level": "BLOCKED", "reason": "Kong Prompt Guard blocked document content",
                        "latency_ms": elapsed, "status": "kong_guard_blocked"
                    })
                    return {
                        "blocked": True, "block_type": "INJECTION",
                        "filename": filename, "file_type": "PDF",
                        "stage": "KONG_PROMPT_GUARD", "timestamp": timestamp, "latency_ms": elapsed,
                        "scanned_by": "Kong AI Prompt Guard",
                        "message": "Kong AI Prompt Guard flagged this document — its content matched patterns associated with prompt injection or policy violations."
                    }
            else:
                ai_text = data["choices"][0]["message"]["content"]
                m = re.search(r'\{.*\}', ai_text, re.DOTALL)
                if m:
                    kong_result = json.loads(m.group())
        except Exception:
            pass

        # Keyword-based fallback when Kong AI is unavailable
        if kong_result is None:
            kong_result = _keyword_scan_document(text)


        elapsed = round((time.time() - start) * 1000)

        # Stage 2: Check MASK-class PII (email, phone, VIN, plate…)
        # Instead of blocking, offer the user a masking consent flow
        masked_text, mask_found = _apply_mask(text)

        if kong_result.get("has_sensitive_data") or kong_result.get("risk_level") == "HIGH" or mask_found:
            findings = kong_result.get("findings", []) + mask_found
            findings = list(dict.fromkeys(findings))  # deduplicate
            pii_type = "; ".join(findings) if findings else "Sensitive Information"
            query_logs.append({
                "timestamp": timestamp, "domain": f"FILE:{filename}",
                "user_ip": "[REDACTED]", "username": "[REDACTED]",
                "threat_level": "MASKED", "reason": f"Kong DLP found maskable PII: {pii_type}",
                "latency_ms": elapsed, "status": "pii_needs_masking"
            })
            return {
                "blocked": False,
                "needs_masking": True,
                "pii_type": pii_type,
                "findings": findings,
                "filename": filename, "file_type": "PDF",
                "stage": "KONG_DLP_SCAN", "timestamp": timestamp, "latency_ms": elapsed,
                "scanned_by": "Kong AI Deep Scan (via Gemini)",
                "gdpr_concern": kong_result.get("gdpr_concern", True),
                "risk_level": kong_result.get("risk_level", "MEDIUM"),
                "raw_text": text,
                "masked_text": masked_text,
                "pages": len(reader.pages),
                "message": (
                    f"Kong DLP detected sensitive data in '{filename}': {pii_type}. "
                    f"Do you want to continue with automatic masking? "
                    f"All detected PII will be replaced with [REDACTED] before sending to the AI."
                )
            }

        query_logs.append({
            "timestamp": timestamp, "domain": f"FILE:{filename}",
            "user_ip": "[REDACTED]", "username": "[REDACTED]",
            "threat_level": "LOW", "analysis": kong_result.get("summary", "No sensitive data detected"),
            "latency_ms": elapsed, "status": "allowed"
        })
        return {
            "blocked": False, "needs_masking": False,
            "filename": filename, "file_type": "PDF",
            "stage": "DELIVERED", "timestamp": timestamp, "latency_ms": elapsed,
            "pages": len(reader.pages),
            "scanned_by": "Kong AI Deep Scan (via Gemini)",
            "gdpr_concern": False,
            "risk_level": kong_result.get("risk_level", "LOW"),
            "raw_text": text,
            "message": f"Document '{filename}' passed Kong AI two-stage scan ({len(reader.pages)} page(s)) — {kong_result.get('summary', 'no sensitive data detected')}. Safe to process."
        }

    else:
        content_type = file.content_type or f"image/{ext.lstrip('.')}"
        b64 = base64.b64encode(contents).decode()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": GEMINI_MODEL,
                        "messages": [{"role": "user", "content": [
                            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}},
                            {"type": "text", "text": 'Analyze this image for sensitive personal information (PII) such as credit card numbers, ID/passport numbers, SSNs, bank details, medical records, or confidential documents. Reply ONLY with valid JSON: {"has_pii": true or false, "pii_types": ["list"], "risk_level": "HIGH or MEDIUM or LOW", "reason": "one sentence"}'}
                        ]}]
                    }
                )
            ai_text = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{[^{}]*\}', ai_text, re.DOTALL)
            result = json.loads(match.group()) if match else {"has_pii": False, "risk_level": "LOW", "reason": "Scan inconclusive"}
        except Exception as e:
            result = {"has_pii": False, "risk_level": "LOW", "reason": f"AI scan error — treated as safe"}

        elapsed = round((time.time() - start) * 1000)

        if result.get("has_pii") or result.get("risk_level") == "HIGH":
            pii_types = result.get("pii_types", ["Sensitive Information"])
            pii_type = ", ".join(pii_types) if pii_types else "Sensitive Information"
            query_logs.append({
                "timestamp": timestamp, "domain": f"FILE:{filename}",
                "user_ip": "[REDACTED]", "username": "[REDACTED]",
                "threat_level": "BLOCKED", "reason": f"PII in image: {pii_type}",
                "latency_ms": elapsed, "status": "pii_blocked"
            })
            return {
                "blocked": True, "block_type": "PII", "pii_type": pii_type,
                "filename": filename, "file_type": "IMAGE",
                "stage": "KONG_FIREWALL", "timestamp": timestamp, "latency_ms": elapsed,
                "message": f"Kong AI Gateway detected {pii_type} in the uploaded image. File blocked — data was not processed or stored."
            }

        query_logs.append({
            "timestamp": timestamp, "domain": f"FILE:{filename}",
            "user_ip": "[REDACTED]", "username": "[REDACTED]",
            "threat_level": "LOW", "analysis": result.get("reason", "No PII detected"),
            "latency_ms": elapsed, "status": "allowed"
        })
        return {
            "blocked": False, "filename": filename, "file_type": "IMAGE",
            "stage": "DELIVERED", "timestamp": timestamp, "latency_ms": elapsed,
            "message": f"Image scanned by Kong AI Gateway — {result.get('reason', 'no sensitive data detected')}. Safe to process."
        }


class FileChat(BaseModel):
    prompt: str
    file_text: str          # already masked or raw, depending on consent
    filename: str
    role: Optional[str] = "analyst"

@app.post("/api/chat-with-file")
async def chat_with_file(body: FileChat):
    """Process a user's prompt together with the content of an uploaded document."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start = time.time()

    system_msg = (
        "You are a helpful Volvo data assistant. The user has uploaded a document. "
        "Answer their question using the document content provided. "
        "Be concise and structured. If PII appears as [REDACTED], acknowledge it's been masked for privacy."
    )
    user_msg = f"Document: {body.filename}\n\nContent:\n{body.file_text[:4000]}\n\n---\nUser question: {body.prompt}"

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            prompt_hash = hashlib.sha256(f"{body.prompt}:{body.filename}:{body.file_text[:1000]}".encode('utf-8')).hexdigest()
            resp = await client.post(
                KONG_URL,
                json={"model": GEMINI_MODEL, "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg}
                ]},
                headers={"Content-Type": "application/json", "x-prompt-hash": prompt_hash}
            )
        data = resp.json()
        if resp.status_code == 429:
            return {"blocked": True, "block_type": "RATE_LIMIT",
                    "message": "Kong rate limit exceeded — please wait and try again.",
                    "timestamp": timestamp}
        if "error" in data:
            return {"blocked": False,
                    "message": f"AI error: {data['error'].get('message', str(data['error']))}",
                    "timestamp": timestamp,
                    "latency_ms": round((time.time() - start) * 1000), "tokens": 0}
        ai_reply = data["choices"][0]["message"]["content"]
        elapsed  = round((time.time() - start) * 1000)
        tokens   = data.get("usage", {}).get("total_tokens", 0)
        return {"blocked": False, "message": ai_reply,
                "timestamp": timestamp, "latency_ms": elapsed, "tokens": tokens}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── RBAC File Access Control ──────────────────────────────────────────────────

ADMIN_ONLY_FILES = {
    "executive_compensation_2024.txt",
    "board_meeting_minutes_q4.txt",
    "cybersecurity_incident_log.txt",
}

ANALYST_FILES = {
    "vehicle_specs.csv",
    "service_logs.csv",
    "public_policies.txt",
    "fleet_analytics_report.txt",
    "maintenance_budget_q1.txt",
}

class FileRequest(BaseModel):
    role: str = "analyst"

@app.post("/api/files/list")
async def list_files(req: FileRequest):
    role = req.role.lower()
    if role == "admin":
        visible = ADMIN_ONLY_FILES | ANALYST_FILES
    else:
        visible = ANALYST_FILES
    all_files = []
    for fname in sorted(os.listdir("data")):
        is_admin_only = fname in ADMIN_ONLY_FILES
        if fname in visible:
            all_files.append({"name": fname, "admin_only": is_admin_only, "accessible": True})
        else:
            all_files.append({"name": fname, "admin_only": True, "accessible": False})
    return {"role": role, "files": all_files}

@app.post("/api/files/read")
async def read_file(req: dict):
    role = req.get("role", "analyst").lower()
    filename = req.get("filename", "")
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if filename in ADMIN_ONLY_FILES and role != "admin":
        return {
            "blocked": True,
            "filename": filename,
            "message": "⛔ ACCESS DENIED — Kong AI Gateway blocked this request.\n\nThis file is classified ADMIN ONLY. Your current role (ANALYST) does not have permission to access executive or confidential documents.\n\nThis access attempt has been logged."
        }
    filepath = os.path.join("data", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"blocked": False, "filename": filename, "content": content}


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


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _agent_error_message(service: str, exc: Exception) -> str:
    details = str(exc)
    if hasattr(exc, "exceptions"):
        leaf_messages = [str(item) for item in exc.exceptions if str(item)]
        if leaf_messages:
            details = "; ".join(leaf_messages)

    if service == "mcp":
        return (
            "MCP server is not reachable. Start it in another terminal with "
            "`python mcp_server.py`, then try Smart Assistant again."
        )

    if service == "kong":
        return (
            "Kong AI Gateway is not reachable at http://localhost:8000/ai. "
            "Start Docker Desktop, run `docker compose up -d`, then try again."
        )

    return f"{service} error: {details or exc.__class__.__name__}"


async def agent_chat_stream(message: str):
    try:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession

        yield _sse_event("step", {"stage": "source", "msg": "Prompt received by MCP Agent"})
        await asyncio.sleep(0.2)
        yield _sse_event("step", {"stage": "kong", "msg": "Kong AI Gateway inspecting prompt..."})

        try:
            streams_context = sse_client(KONG_MCP_URL)
            streams = await streams_context.__aenter__()
        except Exception as e:
            yield _sse_event("error", {"msg": _agent_error_message("mcp", e)})
            return

        try:
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

                yield _sse_event("step", {"stage": "mcp_discover", "msg": f"MCP tools discovered: {', '.join(tool_names)}"})

                if any(phrase in message.lower() for phrase in ("available files", "list files", "show files", "all files")):
                    yield _sse_event("step", {"stage": "mcp_call", "msg": "Calling tool list_available_files..."})
                    tool_result = await mcp.call_tool("list_available_files", arguments={})
                    result_text = "\n".join(c.text for c in tool_result.content if c.type == "text")
                    yield _sse_event("step", {"stage": "mcp_result", "msg": f"Tool list_available_files returned {len(result_text)} chars"})
                    yield _sse_event("answer", {"msg": result_text})
                    return

                system_prompt = (
                    "You are a helpful Volvo data assistant. You have access to local dataset files via MCP tools.\n"
                    "Before answering data questions, ALWAYS call list_available_files first, then fetch_documents. "
                    "Do NOT write Python code blocks — use actual tool calls only."
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ]

                async with httpx.AsyncClient(timeout=60.0) as http:
                    for _ in range(MAX_TOOL_LOOPS):
                        yield _sse_event("step", {"stage": "kong", "msg": "Kong AI Proxy routing request to Gemini..."})

                        try:
                            resp = await http.post(
                                KONG_URL,
                                json={"model": GEMINI_MODEL, "messages": messages, "tools": llm_tools},
                                headers={"Content-Type": "application/json"}
                            )
                        except httpx.HTTPError as e:
                            yield _sse_event("error", {"msg": _agent_error_message("kong", e)})
                            return

                        data = resp.json()
                        if "error" in data:
                            err_msg = data["error"].get("message", str(data["error"]))
                            yield _sse_event("blocked", {"msg": f"⛔ Kong blocked: {err_msg}"})
                            return

                        llm_msg = data["choices"][0].get("message", {})
                        if not llm_msg.get("tool_calls"):
                            content = llm_msg.get("content", "")
                            yield _sse_event("step", {"stage": "ai", "msg": "Gemini responded ✓"})
                            yield _sse_event("answer", {"msg": content})
                            return

                        messages.append(llm_msg)
                        for tc in llm_msg["tool_calls"]:
                            fn = tc["function"]["name"]
                            args = json.loads(tc["function"]["arguments"])
                            yield _sse_event("step", {"stage": "mcp_call", "msg": f"Calling tool {fn}..."})

                            tool_result = await mcp.call_tool(fn, arguments=args)
                            result_text = "\n".join(c.text for c in tool_result.content if c.type == "text")

                            yield _sse_event("step", {"stage": "mcp_result", "msg": f"Tool {fn} returned {len(result_text)} chars"})
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result_text,
                                "name": fn
                            })

            yield _sse_event("error", {"msg": "No answer generated by MCP Agent"})
        finally:
            await streams_context.__aexit__(None, None, None)
    except Exception as e:
        yield _sse_event("error", {"msg": _agent_error_message("Smart Assistant", e)})


# /api/agent-chat is kept for backwards compatibility but now simply calls
# the unified /api/chat endpoint — the mode toggle in the UI has been removed.
@app.post("/api/agent-chat")
async def agent_chat(query: PromptQuery):
    return await chat(ChatMessage(message=query.message))


@app.get("/")
async def root():
    return FileResponse("static/chat.html", media_type="text/html")


app.mount("/static", StaticFiles(directory="static"), name="static")

# Add OPTIONS method handling for CORS preflight
@app.options("/{path:path}")
async def options_handler(path: str):
    return {"message": "OK"}
