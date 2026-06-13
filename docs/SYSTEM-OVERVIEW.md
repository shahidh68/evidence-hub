# The whole system, in plain English

This explains how the **AI Audit Ledger family** fits together and — the part most
people ask for — exactly **what you need (keys, URLs, env vars) to run it**.

No deep technical background assumed.

---

## 1. What the system is for

When an AI makes a decision (approve a loan, screen a CV, route a claim), regulators
increasingly expect you to prove three things later:

1. **What the AI decided** — and that the record hasn't been changed.
2. **That no record was deleted.**
3. **That the decision had proper evidence behind it** (an approved model, checked
   data, a policy check, human review where required).

This system does all three, without storing anyone's personal data.

---

## 2. The moving parts

| Piece | Plain English | Repo |
|---|---|---|
| **AI Audit Ledger** | The tamper-proof logbook. Every decision is written once and sealed for 7 years (can't be edited or deleted). | [audit-ledger](https://github.com/shahidh68/audit-ledger) |
| **audit-ledger-mcp** | The adapter that lets any AI agent (Claude, Cursor, LangGraph…) write to the ledger with one line of config. | [npm: audit-ledger-mcp](https://www.npmjs.com/package/audit-ledger-mcp) |
| **AI Decision Evidence Hub** | Sits *above* the ledger (read-only). Scores each decision's **audit-readiness 0–100**, lists what evidence is missing and who owns it, and generates audit packs. | [evidence-hub](https://github.com/shahidh68/evidence-hub) |
| **Two dashboards** | The **Ledger dashboard** (browse records, verify tamper-evidence, check for deleted records). The **Evidence Hub dashboard** (readiness scores, gaps, audit packs). They cross-link. | — |
| **LangGraph loan-triage demo** *(optional)* | A worked example: two AI agents + a human reviewer that write real decisions to the ledger. | langgraph-loan-triage |

---

## 3. How one decision flows (end to end)

1. Your AI app (or an agent via the MCP) makes a decision.
2. Before anything leaves your machine, the **personal data is hashed locally** —
   the ledger only ever sees fingerprints, never names or documents.
3. The decision is written to the **ledger**: stored in a fast database for queries
   **and** sealed in immutable S3 storage for 7 years. Each record gets a sequence
   number so deletions are detectable.
4. The **Evidence Hub** reads that decision over the ledger's API (read-only),
   works out which evidence is present vs missing, and gives it a **0–100 score**.
5. You view it: the **Ledger dashboard** for the raw record + integrity, the
   **Evidence Hub dashboard** for audit-readiness and audit packs.

The ledger is the source of truth. The Evidence Hub never changes it.

---

## 4. What you need to run it (keys, URLs, env vars)

There are three credential "zones." Here's each, what it is, and where it comes from.

### A. The Ledger (the foundation — deploy once)
After you deploy the ledger (`cdk deploy`), CloudFormation prints **stack outputs**,
and you populate two secrets. These are the values everything else points at:

| Value | What it is | Where it comes from |
|---|---|---|
| **API base URL** | the ledger's HTTPS endpoint | stack output `ApiBaseUrl` (e.g. `https://xxxx.execute-api.eu-west-1.amazonaws.com/prod`) |
| **Write key** | lets an app/agent *record* decisions | you create it, store in `TenantKeyMapSecret` (Secrets Manager) as `{ "<write-key>": "<tenant>" }` |
| **Read key** | lets a tool *read* one tenant's records | you create it, store in `ReadKeyMapSecret` as `{ "<read-key>": "<tenant>" }` |
| **Admin read key** | reads *all* tenants | same secret, mapped to `"*"` |
| **HMAC key** | the secret used to hash PII locally (recommended) | you generate it (`node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`) and keep it on the writing side only |

> **Just trying it?** Skip all of this — the MCP has a **public sandbox**: run
> `npx -y audit-ledger-mcp` with no config and it writes to a shared demo tenant.

### B. Writing decisions (your app / the MCP / the demo)
Whatever writes to the ledger needs these environment variables:

| Env var | What |
|---|---|
| `AUDIT_API_URL` | the ledger API base URL (A) |
| `AUDIT_WRITE_KEY` | a write key (A) |
| `AUDIT_READ_KEY` | a read key (A) — for verify/list |
| `AUDIT_HMAC_KEY` | your HMAC secret (A) — strongly recommended |
| `ANTHROPIC_API_KEY` | only for the **LangGraph demo** (the agents call Claude) |

The MCP is wired into an agent with exactly these (see its
[npm page](https://www.npmjs.com/package/audit-ledger-mcp)). With none set, it runs
in sandbox mode.

### C. The Evidence Hub (the audit-readiness layer)
Runs locally or on AWS. Its settings:

| Env var | What | Typical value |
|---|---|---|
| `LEDGER_SOURCE` | where it reads decisions from | `fixtures` (offline) · `sandbox` · `live` |
| `AUDIT_API_URL` | the ledger to read (when `live`) | the ledger API base URL (A) |
| `AUDIT_READ_KEY` | how it reads the ledger | an **admin** read key (A), so it can see all tenants |
| `EVIDENCE_STORE` | where it stores its own data | `sqlite` (local) · `dynamodb` (AWS) |
| `EVIDENCE_TABLE_NAME` | the DynamoDB table | (AWS only) |
| `EVIDENCE_ADMIN_KEY` | the key dashboard/API callers must send as `x-api-key` | you choose it |
| `EVIDENCE_SECRET_ARN` | on AWS, a secret holding `{admin_api_key, ledger_read_key}` | from its CDK stack |

On AWS the Hub fetches the admin key + ledger read key from `EVIDENCE_SECRET_ARN`
at startup, so you don't pass them as plain env vars.

---

## 5. Using the two dashboards

| Dashboard | URL | What you enter to log in |
|---|---|---|
| **Ledger** | its CloudFront URL (stack output `DashboardUrl`) | the **API base URL** + a **read key** |
| **Evidence Hub** | its Function URL + `ui/` | the **admin key** (`EVIDENCE_ADMIN_KEY`), entered once and stored in your browser |

Each links to the other. Credentials are stored only in your browser.

---

## 6. Running each piece (quick reference)

**Try the MCP with zero setup (sandbox):**
```bash
npx -y audit-ledger-mcp
```

**Run the LangGraph demo (writes 3 real decisions):**
```bash
# .env has ANTHROPIC_API_KEY + AUDIT_API_URL + AUDIT_WRITE_KEY + AUDIT_READ_KEY
loan-triage examples/borderline.json          # or LOAN_TRIAGE_AUTO_APPROVE=1 for non-interactive
```

**Run the Evidence Hub locally:**
```bash
LEDGER_SOURCE=sandbox uvicorn evidence_hub.api:app    # then open http://127.0.0.1:8000/ui/
```

**Deploy the Evidence Hub to AWS:** see [ADMIN-RUNBOOK.md](ADMIN-RUNBOOK.md).
**Deploy the Ledger:** see the ledger repo's `DEPLOYMENT.md`.

---

## 7. The security model in one paragraph

Personal data is **hashed before it leaves your machine** — the ledger stores
fingerprints, not people. Records are **immutable** (S3 Object Lock, 7 years) so
they can't be altered or deleted, and **sequence numbers** make any deletion
detectable. **Write keys can't read; read keys can't write.** The Evidence Hub is
**read-only** on the ledger and gated by an **admin key**. The HMAC key (which makes
the hashing un-reversible) is the one secret that **never leaves your side** — not
even the system operator can reverse it.

---

## 8. Where the actual values live (not in this repo)

This guide is generic on purpose. Your deployment's **real URLs, table names, and
secret ARNs** are in the [Admin Runbook](ADMIN-RUNBOOK.md); the **secret values
themselves** (keys) live only in AWS Secrets Manager and your local `.env` files —
never committed to any repo.
