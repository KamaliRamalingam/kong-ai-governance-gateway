# 🎯 Quick Test Guide - RBAC Pre-Flight Check

## How to Test in 60 Seconds

### Step 1: Make sure role is DEV ✅
```
Click the role button in UI → select "DEV"
Status should show: 🟢 DEVELOPER
```

### Step 2: Try to access admin file
```
Click ⚡ button for quick prompts
Click "💰 Budget Q1 (Admin)" chip
OR type: "What is the maintenance budget breakdown?"
```

### Step 3: Watch officer react 😠
```
Expected response in RED:
⛔ ACCESS DENIED: You do not have admin access to file 
'maintenance_budget_q1.txt'. Only administrators can 
view this file. Your current role is: DEVELOPER.

Officer should:
✅ Turn ANGRY 😠
✅ Glow RED 🔴
✅ SHAKE 🔄
✅ Show "BREACH ALERT" 🚨
✅ Last for 6 seconds
```

### Step 4: Switch to ADMIN role
```
Click role button → select "ADMIN"
Status should show: 🔴 ADMIN
Repeat same query
```

### Expected for ADMIN
```
Budget data shows (fully redacted with [REDACTED])
Officer should:
✅ Turn HAPPY 😊
✅ Glow GREEN 🟢
✅ BOUNCE ⬆️
✅ Show "APPROVED" ✓
✅ Last for 4 seconds
```

---

## What to Test

### Test Queries (All Should Block for DEV)

| Query | Expected File |
|-------|----------------|
| "Show me fleet analytics" | fleet_analytics_report.txt |
| "Fleet analytics report" | fleet_analytics_report.txt |
| "What is the budget?" | maintenance_budget_q1.txt |
| "Maintenance budget breakdown" | maintenance_budget_q1.txt |
| "Q1 budget" | maintenance_budget_q1.txt |
| "Supplier contracts" | supplier_contracts_summary.txt |
| "Show me R&D projects" | rd_roadmap_2024.txt |
| "What's the 2024 roadmap?" | rd_roadmap_2024.txt |

---

## Officer Animation Reference

### ANGRY MODE 😠 (When DEV requests admin file)
```
👮 Face:    😠 Angry frown
🔴 Glow:    Red pulsing
🔄 Body:    Shaking (rotates ±12°)
📝 Label:   "🚨 BREACH ALERT"
💬 Bubble:  Red with error message
⏱️  Time:    6 seconds → reset
```

### HAPPY MODE 😊 (When allowed/approved)
```
👮 Face:    😊 Happy smile
🟢 Glow:    Green stable
⬆️  Body:    Bouncing (-16px)
📝 Label:   "✓ APPROVED"
💬 Bubble:  Green with success message
⏱️  Time:    4 seconds → reset
```

### IDLE MODE 😐 (Normal)
```
👮 Face:    😐 Neutral
⚫ Glow:     Grey
🟰 Body:    Still
📝 Label:   "AI GOVERNOR"
💬 Bubble:  None
⏱️  Time:    ∞ (until next event)
```

---

## Quick Prompt Buttons (In UI)

### Red Chips (Always Blocked for DEV)
```
💰 Budget Q1 (Admin)
📊 Fleet Analytics (Admin)
🤝 Supplier Contracts (Admin)
🏗️  R&D Roadmap (Admin)
```
→ Click any → Instant 🔴 RED ERROR + 😠 ANGRY officer

### Green Chips (Allowed for DEV)
```
✓ List available files
✓ Vehicle specs
✓ Service logs
✓ Public policies
✓ Dataset summary
```
→ Click any → 🟢 GREEN response + 😊 HAPPY officer

---

## Expected Messages

### For DEVELOPER Accessing Admin File
```
⛔ ACCESS DENIED: You do not have admin access to file 
'maintenance_budget_q1.txt'. Only administrators can 
view this file. Your current role is: DEVELOPER.
```

Color: 🔴 RED
Officer: 😠 ANGRY (shaking)

### For ADMIN Accessing Admin File
```
[Budget data with full redaction applied]

Example:
Total Q1 Approved: [REDACTED]
Manufacturing Fleet: [REDACTED]
Executive Fleet: [REDACTED]
...
```

Color: ⚫ Normal black text
Officer: 😊 HAPPY (bouncing)

### For DEVELOPER Accessing Public File
```
[Public policy data]

Vehicle specifications and service logs are 
available as requested...
```

Color: ⚫ Normal black text
Officer: 😊 HAPPY (bouncing)

---

## Troubleshooting

### Officer not animating?
- Clear cache: Cmd+Shift+R (Mac) or Ctrl+Shift+R
- Check console for JS errors
- Refresh page and try again

### Not seeing red error message?
- Make sure role is set to DEV (not ADMIN)
- Make sure you're using admin keywords (see list above)
- Try: "What is the maintenance budget?"

### Wrong response (generic instead of explicit)?
- Flask needs restart: `python main.py`
- Make sure main.py has the new code (12 keywords)
- Hard refresh browser

### Officer not turning red?
- Should happen automatically when "blocked" event received
- Check browser console (F12 → Console tab)
- Look for "blocked" in network tab

---

## Admin File Keywords (Catchable)

```
fleet analytics          ← fleet_analytics_report.txt
maintenance budget       ← maintenance_budget_q1.txt
q1 budget               ← maintenance_budget_q1.txt
budget breakdown        ← maintenance_budget_q1.txt
supplier contract       ← supplier_contracts_summary.txt
r&d project            ← rd_roadmap_2024.txt
r&d roadmap            ← rd_roadmap_2024.txt
2024 roadmap           ← rd_roadmap_2024.txt
rd project             ← rd_roadmap_2024.txt
rd roadmap             ← rd_roadmap_2024.txt
r&d 2024               ← rd_roadmap_2024.txt
supplier contracts     ← supplier_contracts_summary.txt
```

Try any of these with DEVELOPER role → Should get 🔴 RED error

---

## Success Checklist

✅ DEV + admin keyword = 🔴 RED error + 😠 ANGRY officer
✅ ADMIN + admin keyword = Data (redacted) + 😊 HAPPY officer
✅ DEV + public query = Data + 😊 HAPPY officer
✅ Message explicitly says "ACCESS DENIED"
✅ Message shows filename
✅ Message shows current role
✅ Officer shakes when angry
✅ Officer bounces when happy
✅ Officer glow changes (red/green)
✅ Officer label changes (BREACH ALERT / APPROVED)

**All 10 checks pass?** 🎉 **Feature is working perfectly!**

---

## Key Difference (Before vs After)

### BEFORE ❌
```
User: "Show me the fleet analytics report"
Response: "I do not have access to a fleet analytics report."
Officer: 😐 No reaction
Problem: User doesn't know why or what role needed
```

### AFTER ✅
```
User: "Show me the fleet analytics report"
Response: ⛔ ACCESS DENIED: You do not have admin access to file 
          'fleet_analytics_report.txt'. Only administrators can 
          view this file. Your current role is: DEVELOPER.
Officer: 😠 ANGRY (red glow, shaking, "BREACH ALERT")
Result: Crystal clear what went wrong and why
```

---

## 🚀 You're All Set!

1. Flask is running with new code ✅
2. HTML/CSS/JS ready for animations ✅
3. 12 keywords for admin files detected ✅
4. Pre-flight RBAC check active ✅
5. Officer animations working ✅

**Start testing now!** 🎯
