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

Out of scope for this MVP (deferred): external connectors (MLflow, Great
Expectations, OPA, Evidently, Atlas, Jira), PDF packs, model-/date-/incident-
scoped packs, SSO/RBAC, and a dashboard UI.

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

Then explore at `http://127.0.0.1:8000/docs`.

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

## Storage

SQLite by default (`EVIDENCE_DB_URL=sqlite:///./data/evidence.db`). Models are
SQLAlchemy, so switching to Postgres is a connection-string change.
