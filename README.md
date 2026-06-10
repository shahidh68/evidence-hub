# AI Decision Evidence Hub

An append-only **evidence and compliance layer** that sits *above* the
[AI Audit Ledger](../ai-audit-ledger). The ledger is the immutable record of
*what happened* at decision time. The Evidence Hub answers the next question:

> Does this decision have the evidence it needs to survive an audit — what's
> present, what's missing, who owns the gaps, and what's been remediated?

The Hub **only reads** the ledger. It never modifies ledger records (the ledger
stays the canonical, tamper-evident source of truth). All evidence and
remediation state lives in the Hub's own append-only store.

## What it does (MVP)

- **Reads** AI decision events from the ledger (live, sandbox, or local fixtures).
- **Normalizes** the minimal ledger record — including fields buried inside the
  free-form `ai_decision_output` — and flags schema misuse (e.g. a reviewer name
  stuffed into `model_version`).
- **Evaluates** each decision against nine evidence categories and produces a
  weighted **audit-readiness score** (0–100) and status band.
- **Tracks remediation** via an append-only evidence registry with a gap
  lifecycle (open → in_progress → submitted → verified → closed).
- **Rolls up** a current readiness view per decision.
- **Builds** an evidence graph linking the decision to triage/risk events,
  its archive, and attached artifacts.
- **Generates** a per-decision JSON audit pack.
- **Serves** a dashboard (decisions, gap queue, model rollup, audit packs) at `/ui/`.

Out of scope for this MVP (deferred): external connectors (MLflow, Great
Expectations, OPA, Evidently, Atlas, Jira), PDF packs, and model-/date-/incident-
scoped packs, plus SSO/RBAC.

## Architecture

```
Immutable Audit Ledger  ──read──▶  Evidence Evaluator ──▶ Evidence Registry (append-only)
 (DynamoDB + S3 Lock)                     │                       │
                                          ▼                       ▼
                                  Readiness View          Evidence Graph
                                          │                       │
                                          ▼                       ▼
                                  Audit Pack Generator / FastAPI API
```

## Setup

Requires Python 3.10+.

```bash
cd "C:/Users/AI Data Logger/evidence-hub"
python -m venv .venv
.venv/Scripts/activate        # Windows ; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

For `sandbox`/`live` ledger reads, also install the ledger SDK (pulls in aiohttp):

```bash
pip install -e "../ai-audit-ledger/sdk/python"
```

## Ledger source modes

Set `LEDGER_SOURCE` (see `.env.example`):

| Mode       | Reads from                               | Needs |
|------------|------------------------------------------|-------|
| `fixtures` | local JSON in `tests/fixtures/`          | nothing (offline) |
| `sandbox`  | public ledger sandbox (`sandbox-public`) | the ledger SDK |
| `live`     | your deployed ledger                     | the SDK + `AUDIT_API_URL` + `AUDIT_READ_KEY` |

## Run the API

```bash
# Offline against bundled fixtures:
LEDGER_SOURCE=fixtures uvicorn evidence_hub.api:app --reload   # set env via your shell

# Against the public sandbox:
LEDGER_SOURCE=sandbox uvicorn evidence_hub.api:app --reload
```

Then open the **dashboard** at `http://127.0.0.1:8000/ui/` (or the API docs at
`/docs`). In `fixtures` mode, enter a fixture `event_id` and click Evaluate; in
`sandbox`/`live` mode, click **Pull recent** to evaluate recent ledger events.

### Example

```bash
curl -X POST localhost:8000/evidence/evaluate \
  -H 'content-type: application/json' \
  -d '{"event_id":"a92ffa42-27a8-4e46-81d6-b9b1a654077f"}'
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/evidence/evaluate` | Read a ledger event, normalize, evaluate, persist |
| POST | `/evidence/evidence-update` | Append a remediation update (gap lifecycle enforced) |
| GET | `/evidence/readiness/{decision_id}` | Current readiness roll-up |
| GET | `/evidence/graph/{decision_id}` | Evidence graph edges |
| POST | `/audit-pack` | Per-decision JSON audit pack |
| POST | `/evidence/resolve` | Auto-fill resolvable gaps from the configured resolver |
| GET | `/dashboard/decisions` `/dashboard/gaps` `/dashboard/models` `/dashboard/audit-packs` | Dashboard roll-ups |
| GET | `/ui/` | Dashboard UI (static, vanilla JS) |
| GET | `/ledger/decisions` | Read-only passthrough to browse the ledger |
| GET | `/health` | Liveness + active ledger source |

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Tests run with `LEDGER_SOURCE=fixtures` (fully offline). They assert the spec's
worked example scores `partial`, the `model_version` misuse is flagged, the
registry is append-only with enforced transitions, and readiness improves as
gaps resolve.

## Resolving evidence from a repo manifest

Most missing references are *static* properties of a model, dataset, policy, or
prompt — not facts unique to one decision. Rather than re-instrument every
customer app, the customer keeps an **evidence manifest** in their repo and the
Hub resolves references from it, joining only on fields the ledger already
records: `model_version`, `system_prompt_hash`, and `tenant_id`.

```yaml
# evidence-manifest.yaml  (JSON also supported; YAML needs the [manifest] extra)
models:
  "claims-risk-model:12":
    model_name: claims-risk-model
    model_registry_reference: mlflow:model:claims-risk-model:12
    model_approval_reference: change-ticket:CR-4471
prompts:                       # keyed by the system_prompt_hash already in the ledger
  "c28dd58c...fefa":
    prompt_version_reference: git:prompts/triage.md@a1b2c3
tenants:
  acme-corp:
    data_lineage_reference: atlas:lineage:dataset_12345
    data_quality_check_reference: great_expectations:run_67890
    privacy_classification: pii-pseudonymised
    retention_classification: 7y
    policy_check_reference: opa:policy:loan-triage
    policy_version: "2026.05"
```

Point it at the Hub with `EVIDENCE_MANIFEST_PATH`. When set, `/evidence/evaluate`
auto-resolves; you can also call `/evidence/resolve` explicitly.

Each resolved reference becomes an **append-only `verified` evidence update**
tagged with the manifest's source and a `sha256` content signature (its
version pin), so resolution never touches the ledger and stays fully auditable.
Resolution is idempotent and skips gaps a human already closed.

What a manifest *cannot* fill — facts unique to one decision's instant
(`monitoring_snapshot_reference`, `drift_status`, the specific `policy_result`
that fired) — is left for richer decision-time logging or a future connector. A
connector is just another `Resolver` (`src/evidence_hub/resolvers/`) that
*verifies* what the manifest *asserts*.

## Storage

SQLite by default (`EVIDENCE_DB_URL=sqlite:///./data/evidence.db`). Models are
SQLAlchemy, so switching to Postgres is a connection-string change.
