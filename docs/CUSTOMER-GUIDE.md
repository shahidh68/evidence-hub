# AI Decision Evidence Hub — Customer Guide

A plain-English guide for compliance, risk, and audit teams. No engineering
background needed.

---

## 1. What the Evidence Hub is

Your organisation records every AI decision in the **AI Audit Ledger** — an
immutable, tamper-evident log. The ledger proves *what happened and that it
wasn't changed*.

The **Evidence Hub** answers the next question an auditor asks:

> "Fine, the decision is recorded — but does it have the **evidence** behind it?
> The approved model, the data lineage, the policy check, the human sign-off?
> What's missing, and who's fixing it?"

For every decision the Hub produces an **audit-readiness score (0–100)**, a list
of exactly what evidence is present vs missing, who owns each gap, and an
**exportable audit pack** you can hand to a regulator.

It **only reads** the ledger — it never changes a recorded decision.

**The family:**
[audit-ledger](https://github.com/shahidh68/audit-ledger) (what happened) ·
[audit-ledger-mcp](https://www.npmjs.com/package/audit-ledger-mcp) (how agents write to it · `npx -y audit-ledger-mcp`) ·
**evidence-hub** (audit-readiness).

---

## 2. Getting in

Open the dashboard URL your admin gave you (it ends in `/ui/`), e.g.
`https://<your-hub>.lambda-url.eu-west-1.on.aws/ui/`.

The first time, it asks for an **admin key** (click the 🔑 badge if it doesn't).
Paste the key from your admin. It's stored in your browser only and sent with
every request. The badge then reads **🔑 key set**.

To jump to the raw ledger records, use the **"Ledger dashboard ↗"** link in the
header — there you can browse records, verify tamper-evidence, and check whether
any record has been deleted (completeness).

---

## 3. The dashboard, tab by tab

### Decisions
Every evaluated decision, **most at-risk first**. Each row shows:

| Column | Meaning |
|---|---|
| Decision | the decision's ID |
| Outcome | approved / declined / etc. |
| Model | the model version (or "unspecified" if the ledger didn't capture one) |
| Integrity | **verified** = the ledger's tamper-check passed |
| Readiness | the 0–100 score (bar + number) |
| Status | complete / ready_with_gaps / partial / incomplete |
| Open gaps | how many required pieces of evidence are still missing |
| Risk | the decision's risk tier |

Click any row to open its **detail drawer** (see §5).

### Gap queue
Every **open gap across all decisions**, highest priority first — your worklist.
Shows the gap, which decision it's on, the **owner** (the team responsible),
priority, status, and due date.

### Models
A roll-up **by model version**: how many decisions used it, their average
readiness, total open gaps, and how many are integrity-verified. Spots a model
whose decisions are systematically under-evidenced.

### Audit packs
Every audit pack generated so far — when, for which decision, its readiness at
the time, and how many sections it contains.

---

## 4. Reading the readiness score

The score is out of 100, weighted across nine evidence categories:

| Category | Weight | Examples of evidence |
|---|---:|---|
| Decision | 10 | decision id, timestamp, tenant, outcome |
| Integrity / archive | 15 | tamper-check verified, immutable archive |
| Model | 15 | model name + version, registry reference, approval |
| Data | 15 | input hash, data lineage, data-quality check |
| Policy | 15 | policy check reference, version, result |
| Human review | 10 | reviewer, outcome, timestamp, rationale |
| Monitoring | 10 | monitoring snapshot, drift status, performance |
| Prompt | 5 | system-prompt hash, prompt version |
| Retention / privacy | 5 | retention class, privacy classification |

**Status bands:** 0–30 incomplete · 31–70 partial · 71–90 ready_with_gaps ·
91–100 complete.

A decision can be **integrity-verified but only partially audit-ready** — that
just means the *record* is sound but some *supporting evidence* hasn't been
attached yet. That's normal, and the gap queue tells you what to chase.

---

## 5. The decision drawer

Clicking a decision opens a panel with:

- **Readiness** score, status, and integrity.
- **Open gaps** (grey chips) — evidence still missing.
- **Resolved gaps** (green ✓ chips) — evidence that's been attached and verified.
- **Evidence graph** — how the decision links to its triage/risk events, its
  archive, and any attached artifacts.
- **Generate audit pack** — builds the exportable pack on the spot.

---

## 6. Audit packs — what's in one

A per-decision JSON package an auditor can read on its own. Sections include:
the decision summary, the original ledger record, the **tamper-evidence result**,
human-review details, model / data / prompt / control evidence, linked
triage/risk events, the evidence evaluation, **open gaps**, the **remediation
history** (who did what, when), and the evidence graph.

Generate one from a decision's drawer, or via the API (your admin can script it).

---

## 7. How gaps get filled

Three ways:

1. **From the dashboard** — open the **Gap queue**, click a gap, add the
   evidence reference or value, choose the status, and save. Evidence Hub records
   the update append-only and recalculates the readiness score.
2. **From the API** — call `/evidence/evidence-update` with the same information
   if you want to wire this into Jira, ServiceNow, MLflow, your model registry, or
   another internal tool.
3. **Automatically** — if your org maintains an *evidence manifest* (a file
   listing which model is approved, which policy applies, etc.), the Hub
   auto-fills the static gaps and tags each with the manifest's version. This is
   why a decision can jump from, say, 41 → 68 the moment it's evaluated.

Some gaps are *dynamic* (e.g. the monitoring snapshot at decision time) and can't
come from a file — those are filled by your monitoring/logging integrations.

---

## 8. Trust & privacy

- **Read-only on the ledger.** The Hub never edits a recorded decision.
- **No personal data.** It works with hashes, references, and metadata — not raw
  inputs or prompts.
- **Append-only.** Evidence and remediation history is never overwritten; you can
  always see the full trail of who changed what.
- **Access-controlled.** Every data view requires the admin key.

---

## 9. FAQ

**A decision says "verified" but only 41/100 — is something wrong?**
No. "Verified" = the record is tamper-evident. 41/100 = supporting evidence is
incomplete. Use the gap queue to close it.

**Why is the model "unspecified"?**
The ledger didn't capture a clean model version for that decision (sometimes
reviewer metadata was logged in the model field). The Hub flags this so it can be
corrected at the source.

**Can I export to PDF?**
Audit packs are JSON today; PDF export is on the roadmap. JSON is the
auditor-friendly, machine-verifiable format. Each pack starts with a plain
`report_summary`, then a `gap_closure_plan`, followed by the raw ledger record,
tamper evidence, remediation history, and graph sections for traceability.

**Who do I contact for access or a new key?**
Your Evidence Hub administrator — see the [Admin Runbook](ADMIN-RUNBOOK.md).
