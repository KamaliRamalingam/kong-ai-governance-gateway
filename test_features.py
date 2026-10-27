"""
Quick feature verification script.
Run AFTER starting the server:  python -m uvicorn main:app --port 8080 --reload

Tests:  1) Intelligent Routing  2) Cache Memory  3) Sensitive Data Masking
"""

import httpx, json, time

BASE = "http://localhost:8080"

def pretty(label, data):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    keys = ["blocked", "routed_model", "routing_reason", "routing_tier",
            "local_cache_hit", "cache_hit", "tokens_saved",
            "input_masked", "output_masked", "latency_ms", "tokens", "stage"]
    for k in keys:
        if k in data:
            print(f"  {k:<20}: {data[k]}")
    if "message" in data and data.get("blocked"):
        print(f"  {'block message':<20}: {data['message'][:80]}...")
    elif "response" in data:
        snippet = (data["response"] or "")[:120].replace("\n", " ")
        print(f"  {'response snippet':<20}: {snippet}...")


def test(label, message):
    r = httpx.post(f"{BASE}/api/chat", json={"message": message, "role": "analyst"}, timeout=30)
    pretty(label, r.json())
    return r.json()


print("\n" + "★"*60)
print("  FEATURE DEMO: Intelligent Proxy + Cache + Masking")
print("★"*60)

# ── 1. ROUTING: fast/code query → Groq ──────────────────────────────────────
print("\n[1] ROUTING TEST — short/code prompt → expect Groq (fast tier)")
test("Write a Python function to sort a list", "Write a quick Python function to sort a list.")

# ── 2. ROUTING: analytical query → Gemini ────────────────────────────────────
print("\n[2] ROUTING TEST — security analysis prompt → expect Gemini (analytical tier)")
test("Analyze zero-trust compliance", "Analyze the security compliance posture of a zero-trust AI gateway deployment.")

# ── 3. CACHE: first call (miss), second call (hit) ───────────────────────────
print("\n[3a] CACHE TEST — first send (should be MISS)")
msg = "Explain how Kong AI Gateway enforces GDPR Article 5 compliance."
r1 = test("Cache MISS — first send", msg)

print("\n[3b] CACHE TEST — same message again (should be LOCAL CACHE HIT, 0 tokens)")
time.sleep(0.5)
r2 = test("Cache HIT — second send", msg)

if r2.get("local_cache_hit"):
    print("\n  ✅ CACHE WORKS — tokens_saved:", r2.get("tokens_saved", "?"))
else:
    print("\n  ⚠️  Cache did not fire — check server logs")

# ── 4. MASKING: PII in prompt ─────────────────────────────────────────────────
print("\n[4] MASKING TEST — prompt contains email + license plate")
test("PII masking demo", "My email is erik.johansson@volvo.com and my plate is ABC-1234, can you help?")

# ── 5. MASKING: GPS → BLOCK ───────────────────────────────────────────────────
print("\n[5] DLP BLOCK TEST — GPS coordinates trigger hard block")
test("GPS block demo", "Share telematics at GPS 59.3293,18.0686 for this vehicle.")

print("\n" + "★"*60)
print("  ALL TESTS DONE  —  check results above")
print("★"*60 + "\n")
