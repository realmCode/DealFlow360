# DealFlow360 — 7-minute demo runbook

One idea carries the whole demo:

> **The backend decides. The interface explains.**
> Nothing on screen is typed in — every number, every routing decision and every
> block is computed by the engine and rendered as-is.

---

## Pre-flight (do this 2 minutes before you present)

```bash
# 1. infrastructure
docker compose up -d                                    # PostgreSQL :5433
uvicorn app.main:app --port 8010                        # API
cd frontend && PORT=3000 npm run dev                    # UI on :3000

# 2. put the tenant into a known state — ALWAYS run this
python -m scripts.demo_reset
```

`demo_reset` restores stock to 60 Main / 40 East and creates a fresh DRAFT
quotation on the canonical configuration. It prints the exact builder URL —
**copy it, that is your starting page.** It talks to the API over HTTP with the
seeded accounts; it does not touch the database directly.

It should print:

```
net revenue   132710.00
margin        32510.00  (24.4970%)
blended risk  32.4440  (MEDIUM)
routes to     SALES_MANAGER then FINANCE
```

If those numbers differ, stop and re-run — the script below quotes them out loud.

**Browser setup:** one window, zoom 90%, ~1440px wide. Have two tabs ready:
the login page, and the builder URL from the reset.

**The one control that saves the demo:** top-right **"Switch role"**. It
re-authenticates as another seeded account in place. Use it for every hop —
signing out and back in costs ~10 seconds each time and you do not have it.

---

## The run

Timings are cumulative. The two protected slices are the **Quote Builder** and
the **Stale Approval** — if you are running long, cut from elsewhere.

### 0:00 – 0:35 · Sign in, establish that this is real

**Click** `localhost:3000/login` → **Demo accounts** → **Enter as Sales**

> "DealFlow360 is a commercial operations platform. Six real roles, and this is
> the real login — every card here posts seeded credentials to the actual auth
> endpoint. Nothing is mocked. Let's start as Sam in sales."

*(The picker shows all six roles with their real emails. Don't linger.)*

---

### 0:35 – 1:15 · Command Center — work, not dashboards

**Land on** `/` (Sales lands here automatically)

> "This isn't a dashboard of vanity metrics. It's a ranked queue of everything
> that needs a decision, worst first."

**Point at** the severity ledger across the top, then the first queue item.

> "Every item answers four questions the backend already computed:
> **why** it fired, what the **impact** is in revenue, who **owns** it, and what
> to **do** next. That text is not written by me — it comes from the engine."

---

### 1:15 – 2:45 · Quote Builder — the flagship *(protect this slice)*

**Click** into your builder tab (the URL from `demo_reset`)

> "This is where a deal gets shaped. Workspace on the left, decision
> intelligence on the right."

**Do this — the single most important interaction:**
Change the **Business Laptop discount from 18 to 22**, press Tab.

> "Watch the right-hand column."

Everything recomputes. Then set it **back to 18**.

> "I didn't calculate any of that. Every edit posts to the backend and the
> backend returns the authoritative totals. The client renders strings — it
> never does money arithmetic."

**Point at** *Commercial position*:

> "Net revenue **132,710**. Margin **32,510**, that's **24.5%**. The waterfall
> shows exactly where the money went: gross, discount, net, cost, margin."

**Point at** *Blended risk*:

> "Risk **32.44**, MEDIUM. And it's not a magic number — it decomposes into four
> weighted components. Discount over ceiling contributes 7.5 of a possible 45.
> Violation breadth is maxed at 15 because three separate lines breach. Each one
> explains its own arithmetic."

**Scroll to** *Policy evaluation*:

> "Four violations. The laptop is 18% against a Gold-tier hardware ceiling of
> 15% — over by 3 points. Installation is 18% against a 10% services ceiling —
> over by 8. And the total discount of 28,090 exceeds the 20,000 signing
> authority."

**Point at** the amber *Approval this will need* panel:

> "So the engine has already decided who must approve: Sales Manager, then
> Finance. Nobody chose that from a dropdown."

**Click** **Submit for approval**.

---

### 2:45 – 3:30 · Manager approval

**Click** *Switch role* → **Sales Manager**  → lands on `/approvals`

> "Morgan is the sales manager. His inbox only shows what's routed to *him*."

**Click** the quotation row.

> "The progression is explicit — submitted, sales manager, finance, confirmation.
> He's the active step."

**Point at** *Why this quotation was flagged*:

> "Rule, subject, actual, limit, over-by, and the risk each one contributed.
> This is the audit trail, not a summary."

**Click** **Approve** → reason *"Strategic account, margin holds"* → **Approve**.

---

### 3:30 – 3:55 · Finance approval, then send

**Switch role** → **Finance** → click the row → **Approve** → reason → **Approve**.

> "Two-step chain complete. The version is now APPROVED."

**Switch role** → **Sales** → open the quotation → **Send to customer**.

---

### 3:55 – 4:35 · Customer portal — a different product

**Switch role** → **Customer** → lands on `/portal`

> "This is Acme, the buyer. Different application entirely — no sidebar, no
> density, no internal chrome."

**Open** the proposal.

> "And critically: no cost, no margin, no risk, no approval chain. Not hidden by
> CSS — those fields don't exist in the payload the portal receives. We have a
> test that fails the build if one ever appears."

**Type 25** into the laptop's *Request* field → **Submit request**.

> "Acme pushes for 25% off the laptops."

---

### 4:35 – 5:45 · Stale approval — the centrepiece *(protect this slice)*

**Switch role** → **Sales** → open the quotation.

> "And here's the thing most systems get wrong."

**Point at** the red banner.

> "That approval we just collected is **dead**. The terms moved after it was
> given."

**Click** **Review what changed**.

> "The whole story, in order: approved, terms changed, material change detected,
> approval invalidated, **confirmation blocked** — and that's where we are."

**Point at** the version comparison:

> "Version 1 against version 2. Revenue down **8,400**. Margin down **8,400**.
> Margin percentage down **5.1 points**. And risk up **18.9** — from 32 MEDIUM to
> **51 HIGH**."

**Point at** *What changed*:

> "Field-level. Was 18%, now 25%, severity HIGH, and the engine's own reason for
> why that's material."

**Point at** the right rail:

> "One previous approval invalidated, and the required next action. The customer
> physically cannot confirm — the API returns a STALE_APPROVAL conflict, and we
> render it as this, not as a red toast saying 'something went wrong'."

---

### 5:45 – 6:15 · Re-approval and confirmation

**Switch role** → **Sales Manager** → approve. **Switch role** → **Finance** → approve.
**Switch role** → **Sales** → **Send to customer**.
**Switch role** → **Customer** → **Accept proposal** → **Accept and create order**.

> "Re-approved at the new terms, and now — and only now — Acme can confirm."

---

### 6:15 – 6:45 · Operations — multi-warehouse allocation

**Switch role** → **Operations** → lands on `/orders` → open the newest order →
**Allocate stock**.

> "One hundred laptops. No single warehouse has them."

**Point at** the split bar:

> "**Sixty from Main, forty from East.** Two shipments, 420 of shipping. The
> allocator walked warehouses by priority under a row lock — and it wrote that
> sentence, not me."

---

### 6:45 – 7:00 · Close on governance

**Switch role** → **Admin** → sidebar **Governance**.

> "And none of the routing is hardcoded. These are the live risk weights and the
> finance escalation threshold. Change this number and different quotes escalate.
> The backend is the source of truth — the interface just makes it legible."

---

## If you are running long — cut in this order

1. The Finance approval narration (approve silently, 15s)
2. Billing (skip entirely, 20s)
3. The Command Center detail (30s → 15s)
4. Operations allocation (30s → 15s, just point at the split)

**Never cut:** the builder recompute, or the stale-approval diff.

## If you have 9–10 minutes, add these

| Add | Where | Worth |
|---|---|---|
| **What-if** — type 5 into the builder's *What if* box, hit *Score it* | Builder, +25s | Shows scoring a hypothetical without saving |
| **Recommendations** — delete the *Annual Support Plan* line first | Builder, +30s | The cross-sell only appears when a category is missing; on the canonical quote it is correctly empty |
| **Billing** — Finance → Billing | +20s | 3 one-time + 1 yearly recurring on one order |
| **Deal Health** — Intelligence → Deal health, expand a row | +25s | Per-signal point deductions |
| **Activity** — Intelligence → Activity | +15s | Append-only audit, every actor and role |

## Recovery

| If | Do |
|---|---|
| The builder shows different numbers | You skipped `demo_reset`. Run it, use the new URL. |
| Allocation backorders everything | Stock is exhausted. Run `demo_reset` again. |
| A role switch seems stuck | The spinner is on the *Switch role* button; give it a second. Worst case, sign out and use the demo picker. |
| The approval row isn't in the inbox | You are the author. Sales cannot approve its own quote — that's the separation-of-duties rule, and it's a feature. Say so. |
| Something 403s on screen | Point at it. "That's the backend refusing, not the UI hiding a button." |

## Numbers to know cold

| | |
|---|---|
| v1 | net **132,710.00** · margin **32,510.00** · **24.50%** · risk **32.44 MEDIUM** |
| Violations | laptop +3pp · monitor +1pp · install +8pp · authority +8,090 |
| Risk parts | overage 7.51/45 · breadth **15/15** · margin 0/40 · depth 6.99/15 |
| Routing | SALES_MANAGER → FINANCE |
| v2 after 25% counter | net **124,310.00** · margin **24,110.00** · **19.40%** · risk **51.36 HIGH** |
| Deltas | revenue −8,400 · margin −8,400 · margin% −5.10pp · risk +18.91 |
| Allocation | **60 Main / 40 East** · 2 shipments · 420 shipping |
| Billing | 3 one-time (124,010.00) + 1 yearly (300.00) |

## Seeded accounts (all `Password123!`)

| Role | Email | Lands on |
|---|---|---|
| Sales | sales@techsupply.com | Command Center |
| Sales Manager | manager@techsupply.com | Approvals |
| Finance | finance@techsupply.com | Approvals |
| Operations | ops@techsupply.com | Orders |
| Admin | admin@techsupply.com | Command Center |
| Customer | customer@acme.com | Portal |
