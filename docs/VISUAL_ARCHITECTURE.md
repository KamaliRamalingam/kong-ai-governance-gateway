# Visual Architecture - DLP Officer & RBAC System

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                              │
│  ┌──────────────┐  ┌──────────────────────────────────────┐        │
│  │ Role Switch  │  │ 120×120 px Animated Officer          │        │
│  │ DEV / ADMIN  │  │  ┌──────────────────────────────┐    │        │
│  └──────────────┘  │  │   SVG Face with Animated     │    │        │
│                    │  │   Mouth Expressions          │    │        │
│                    │  │   • Idle: 😐 Neutral         │    │        │
│                    │  │   • Breach: 😠 Angry         │    │        │
│                    │  │   • Approved: 😊 Happy       │    │        │
│                    │  └──────────────────────────────┘    │        │
│                    │  ┌──────────────────────────────┐    │        │
│                    │  │ Policy Bubble (Dynamic)      │    │        │
│                    │  │ • Red for violations         │    │        │
│                    │  │ • Green for safe passage     │    │        │
│                    │  └──────────────────────────────┘    │        │
│                    └──────────────────────────────────────┘        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Chat Input                              [ SEND ]             │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    KONG AI GATEWAY (Layer 1)                        │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ ai-prompt-guard Plugin                                    │   │
│  │ • Block personnummer, credit cards, GPS coordinates      │   │
│  │ • Block prompt injection attempts                         │   │
│  │ • Rate limiting & security checks                         │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│              PYTHON DLP FILTER (Layer 2 - Enhanced)                 │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 18 Regex Patterns:                                         │   │
│  │ • Original 10 patterns (VIN, VEH-ID, personnummer, etc)  │   │
│  │ • NEW: Currency patterns (SEK, €, $)                      │   │
│  │ • NEW: Financial numbers (1,234,567 → [REDACTED])        │   │
│  │ • NEW: Partial redaction catch ([REDACTED],000)          │   │
│  │ • NEW: JWT/API Key/IBAN patterns                          │   │
│  │                                                             │   │
│  │ All matched data → [REDACTED]                             │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
                         ┌──────────────┐
                         │ Check Block  │
                         │ Policies?    │
                         └──────────────┘
                          ↙           ↘
                    YES (BLOCKED)   NO (ALLOWED)
                         │                    │
                         ↓                    ↓
                  ┌────────────────┐  ┌─────────────────────┐
                  │ Show Officer   │  │ RBAC Filter (Layer 3)│
                  │ 😠 BREACH ALERT│  │ Strict Mode Enabled │
                  │ 🔴 Red Glow    │  │                     │
                  │ 🔄 Shake       │  │ Check User Role:    │
                  │ 6 seconds      │  │                     │
                  └────────────────┘  │ Role = DEVELOPER?   │
                         │            │  ├→ Allow: 3 files  │
                         │            │  │ - vehicle_specs   │
                         │            │  │ - service_logs    │
                         │            │  │ - public_policies │
                         │            │  │                   │
                         │            │  Role = ADMIN?       │
                         │            │  ├→ Allow: 7 files  │
                         │            │  │  (Dev files + 4   │
                         │            │  │   Admin files)    │
                         │            │  │                   │
                         │            │  Role = Unknown?     │
                         │            │  ├→ DENY all admin  │
                         │            │  │  and restricted   │
                         │            └─────────────────────┘
                         │                    │
                         │            ┌────────────────┐
                         │            │ File Found?    │
                         │            └────────────────┘
                         │             ↙              ↘
                         │        YES (ALLOWED)   NO (DENIED)
                         │             │              │
                         │             ↓              ↓
                         │        ┌─────────┐  ┌────────────────┐
                         │        │ Return  │  │ Show Officer   │
                         │        │ Data    │  │ 😠 BREACH ALERT│
                         │        │ (masked)│  │ ⛔ ACCESS      │
                         │        │         │  │ DENIED: You do │
                         │        │         │  │ not have admin │
                         │        │         │  │ access         │
                         │        └─────────┘  │ 6 seconds      │
                         │             │       └────────────────┘
                         │             │              │
                         └─────────────┼──────────────┘
                                       │
                                       ↓
                      ┌──────────────────────────────┐
                      │ Officer Animation Ready      │
                      │ ✓ Reaction Complete         │
                      │ ✓ Next Request Accepted     │
                      └──────────────────────────────┘
```

---

## 🎭 Officer State Machine

```
                          ┌─────────────┐
                          │ IDLE STATE  │
                          │   😐 Neutral │
                          │ Grey border │
                          │ No bubble   │
                          └─────────────┘
                               ↕
                    ┌──────────┴──────────┐
                    ↓                     ↓
            ┌──────────────┐      ┌──────────────┐
            │ BREACH STATE │      │ APPROVED     │
            │   😠 Angry   │      │ STATE        │
            │ 🔴 Red glow  │      │   😊 Happy   │
            │ 🔄 Shaking   │      │ 🟢 Green     │
            │ ⚠ Alert msg  │      │ glow         │
            │ 6 sec timer  │      │ ✓ Approval   │
            └──────────────┘      │ msg          │
                 ↓                 │ 4 sec timer  │
         [After 6 seconds]         └──────────────┘
                 │                      ↓
                 │              [After 4 seconds]
                 │                      │
                 └──────────┬───────────┘
                            ↓
                  ┌─────────────────┐
                  │ Return to IDLE  │
                  │   😐 Neutral    │
                  │ Reset animations│
                  └─────────────────┘
```

---

## 🔄 DLP Enhancement Lifecycle

### Before (10 Patterns)
```
Budget Data: "Q1: SEK 4,200,000"
                    ↓ Apply 10 patterns
         Only currency symbol masked:
         Q1: [REDACTED] 4,200,000  ❌ LEAK
```

### After (18 Patterns)
```
Budget Data: "Q1: SEK 4,200,000"
                    ↓ Apply 18 patterns
         Currency + financial number:
         Q1: [REDACTED]  ✓ SAFE
```

---

## 📊 RBAC Enforcement Flow

```
┌──────────────────────────────────────┐
│ Request for File: "fleet_analytics"  │
└──────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│ Identify Role                        │
└──────────────────────────────────────┘
           ↓
    ┌──────┴──────┐
    ↓             ↓
┌────────────┐ ┌────────────┐
│  DEVELOPER │ │   ADMIN    │
└────────────┘ └────────────┘
    ↓             ↓
┌──────────────────────────────────────┐
│ Check DEVELOPER_FILES set            │
│ { vehicle_specs, service_logs,       │
│   public_policies }                  │
└──────────────────────────────────────┘
    ↓
   NO ← "fleet_analytics" not in set
    ↓
┌──────────────────────────────────────┐
│ Is role == "admin"?                  │
│ (Check nested condition)             │
└──────────────────────────────────────┘
    ↓
   NO (role is "developer")
    ↓
┌──────────────────────────────────────┐
│ Return Strict Denial Message:        │
│ ⛔ ACCESS DENIED: You do not have     │
│ admin access to file               │
│ 'fleet_analytics_report.txt'.        │
│ Only administrators can view this    │
│ file. Your current role is:          │
│ DEVELOPER.                           │
└──────────────────────────────────────┘
    ↓
┌──────────────────────────────────────┐
│ Trigger Officer Breach Reaction:     │
│ • Face: 😠 Angry                     │
│ • Mouth: Animate to frown            │
│ • Bubble: Red with message           │
│ • Body: Shake animation              │
│ • Duration: 6 seconds                │
└──────────────────────────────────────┘
```

---

## 🎨 Officer Animation Timing

### BREACH Animation Timeline
```
Time    0ms     100ms    200ms    300ms    400ms    500ms+
        │        │        │        │        │        │
        ├────────┼────────┼────────┼────────┼────────┤
        │                                           │
Face 😐  └──────────────→ 😠──────────────────────────┘
        
Mouth    (straight)  (animating)  (angry frown)
        
Body     ────────────[SHAKE LOOP for 6 seconds]──────
        
Glow    OFF    TURN ON   PULSE LOOP
        
Label   AI GOVERNOR → 🚨 BREACH ALERT
        
Bubble  HIDDEN  POP-IN  SHOW  [pulsing red]  HIDE
              .35s
```

### APPROVED Animation Timeline
```
Time    0ms     150ms    350ms    500ms    750ms    1000ms+
        │        │        │        │        │        │
        ├────────┼────────┼────────┼────────┼────────┤
        │                                           │
Face 😐  └──────────────→ 😊──────────────────────────┘
        
Mouth    (straight) (animating) (happy smile)
        
Body     ────────[BOUNCE for .7s]──── → steady
        
Glow    OFF    TURN ON    STABLE GREEN GLOW
        
Label   AI GOVERNOR → ✓ APPROVED
        
Bubble  HIDDEN  POP-IN  SHOW  [stable green]  HIDE
              .35s                    ~4s
```

---

## 💾 File Structure After Changes

```
volvo-dns-tapir-experiment-poc/
│
├── main.py                    [MODIFIED]
│   ├── Lines 26-55:  _MASK_RULES (18 patterns)
│   ├── Lines 181-207: rbac_filter_fetch() strict mode
│   └── (+ existing Kong/MCP logic)
│
├── static/
│   └── index.html             [MODIFIED]
│       ├── Lines 420-440:  SVG officer avatar
│       ├── Lines 245-350:  CSS animations
│       └── Lines 575-620:  JS mouth animation logic
│
├── IMPLEMENTATION_COMPLETE.md [NEW]
├── TEST_IMPROVEMENTS.md       [NEW]
├── CODE_CHANGES_REFERENCE.md  [NEW]
├── QUICK_REFERENCE.md         [NEW]
└── (+ other existing files)
```

---

## 🚀 Deployment Sequence

```
Step 1: Update Files
├── Replace main.py (DLP patterns + RBAC)
└── Replace static/index.html (Officer SVG + animations)

Step 2: Restart Services
├── Kill Flask process (Ctrl+C)
├── python main.py
└── Wait for "Running on..." message

Step 3: Clear Cache
├── Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)
└── Verify HTML/CSS/JS loaded fresh

Step 4: Test Officer
├── Switch role to DEVELOPER
├── Request admin file (e.g., "Show me budget")
├── Observe: 😠 Angry + Red + Message
└── Wait: 6 seconds for reset

Step 5: Test Redaction
├── Ask for budget breakdown
├── Verify: All amounts shown as [REDACTED]
└── Confirm: No budget numbers visible

Step 6: Production Ready ✓
└── Monitor logs for any DLP hits
```

---

## 🎯 Success Criteria

✅ **DLP:**
- No budget amounts visible in outputs
- All currency values redacted
- Partial redactions ([REDACTED],000) fully masked

✅ **RBAC:**
- Developer role cannot access admin files
- Receives explicit "no admin access" message
- Admin role receives full data (with redaction)

✅ **Officer:**
- Displays prominently (120×120 px)
- Animates mouth from neutral → angry/happy
- Shows colored bubble with appropriate message
- Shakes on breach, bounces on approval
- Resets after timeout

✅ **Overall:**
- No unintended data leaks
- Clear user feedback on policy enforcement
- Smooth animations, no jank
- Ready for production deployment
