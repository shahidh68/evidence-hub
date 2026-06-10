#!/usr/bin/env python3
"""
generate-architecture-diagram.py

Generates a draw.io / diagrams.net (.drawio) architecture diagram for the
AI Decision Evidence Hub — the append-only evidence/compliance layer deployed
on AWS (Lambda + DynamoDB) that reads the immutable AI Audit Ledger over HTTPS.

Source of truth: README.md and infra/cdk/lib/evidence-hub-stack.ts.
Same visual style as the ledger's tools/generate-architecture-diagram.py.

Usage:
    python tools/generate-architecture-diagram.py [output.drawio]

Open the result at https://app.diagrams.net or in the draw.io desktop app.
"""

import sys
from xml.sax.saxutils import escape

# Palette (matches the ledger diagram, + a grey "external" for the ledger box).
C = {
    "client":   {"fill": "#E8F0FE", "stroke": "#3367D6"},  # blue   - clients
    "edge_net": {"fill": "#FCE8E6", "stroke": "#D93025"},  # red    - function url / edge
    "compute":  {"fill": "#FEF7E0", "stroke": "#F9AB00"},  # amber  - lambda compute
    "data":     {"fill": "#F3E8FD", "stroke": "#8430CE"},  # purple - dynamodb/secrets
    "notify":   {"fill": "#E0F7FA", "stroke": "#00838F"},  # teal   - cloudwatch
    "external": {"fill": "#F1F3F4", "stroke": "#5F6368"},  # grey   - the separate ledger
}

HAPPY   = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeWidth=2;strokeColor=#1A73E8;fontSize=10;fontColor=#1A73E8;endArrow=block;"
READP   = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeWidth=2;strokeColor=#8430CE;fontSize=10;fontColor=#8430CE;endArrow=block;"
WRITEP  = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeWidth=2;strokeColor=#188038;fontSize=10;fontColor=#188038;endArrow=block;"
SUPPORT = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeWidth=1;strokeColor=#5F6368;fontSize=9;fontColor=#5F6368;endArrow=open;dashed=1;"

cells = []
_id = [10]


def nid():
    _id[0] += 1
    return "n" + str(_id[0])


def node(label, x, y, w, h, kind="compute", sub=None, dashed=False):
    nodeid = nid()
    col = C[kind]
    raw = "<b>" + label + "</b>"
    if sub:
        raw += "<br/><span style='font-size:9px;color:#5F6368'>" + sub.replace("\n", "<br/>") + "</span>"
    text = escape(raw)
    style = (
        "rounded=1;whiteSpace=wrap;html=1;fillColor=" + col["fill"] + ";strokeColor="
        + col["stroke"] + ";fontSize=11;align=center;verticalAlign=middle;spacingTop=2;"
        + ("dashed=1;" if dashed else "")
    )
    cells.append(
        '<mxCell id="' + nodeid + '" value="' + text + '" style="' + style
        + '" vertex="1" parent="1"><mxGeometry x="' + str(x) + '" y="' + str(y)
        + '" width="' + str(w) + '" height="' + str(h) + '" as="geometry"/></mxCell>'
    )
    return nodeid


def zone(label, x, y, w, h, stroke):
    nodeid = nid()
    style = (
        "rounded=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor=" + stroke
        + ";dashed=1;verticalAlign=top;align=left;fontSize=12;fontStyle=2;fontColor="
        + stroke + ";spacingLeft=8;spacingTop=4;"
    )
    cells.append(
        '<mxCell id="' + nodeid + '" value="' + escape(label) + '" style="' + style
        + '" vertex="1" parent="1"><mxGeometry x="' + str(x) + '" y="' + str(y)
        + '" width="' + str(w) + '" height="' + str(h) + '" as="geometry"/></mxCell>'
    )
    return nodeid


def edge(src, dst, label="", style=HAPPY):
    nodeid = nid()
    cells.append(
        '<mxCell id="' + nodeid + '" value="' + escape(label) + '" style="' + style
        + '" edge="1" parent="1" source="' + src + '" target="' + dst
        + '"><mxGeometry relative="1" as="geometry"/></mxCell>'
    )
    return nodeid


# ── Zones (drawn first so they sit behind the nodes) ──────────────────────────
zone("CLIENTS", 40, 40, 1180, 140, C["client"]["stroke"])
zone("EDGE", 40, 200, 1180, 110, C["edge_net"]["stroke"])
zone("COMPUTE — AWS Lambda (eu-west-1, no VPC, scale-to-zero)", 40, 330, 1180, 300, C["compute"]["stroke"])
zone("DATA STORES (the Hub's own)", 40, 650, 1180, 150, C["data"]["stroke"])
zone("EXTERNAL — AI Audit Ledger (separate stack, read-only over HTTPS)", 40, 820, 1180, 200, C["external"]["stroke"])

# ── Clients ──────────────────────────────────────────────────────────────────
operator = node("Operator / Browser", 90, 80, 250, 90, "client",
                sub="Dashboard at /ui/\nenters admin key (stored locally, sent as x-api-key)")
apiclient = node("API client / scripts", 430, 80, 250, 90, "client",
                 sub="curl / Invoke-RestMethod\nx-api-key header")

# ── Edge ─────────────────────────────────────────────────────────────────────
furl = node("Lambda Function URL (HTTPS)", 90, 235, 400, 60, "edge_net",
            sub="AuthType NONE — admin x-api-key enforced in-app (auth.py)")

# ── Compute: the Lambda container + its logical pipeline ─────────────────────
lam = node("Container image: FastAPI + AWS Lambda Web Adapter (uvicorn :8080)",
           90, 370, 1080, 55, "compute",
           sub="App code unchanged; the adapter proxies the event to a local HTTP server")

reader = node("Ledger Reader", 90, 450, 165, 66, "compute", sub="urllib GET\nREAD-ONLY")
norm   = node("Normalizer", 265, 450, 165, 66, "compute", sub="parse ai_decision_output\nflag schema misuse")
evaln  = node("Evaluator", 440, 450, 165, 66, "compute", sub="9 evidence categories\nscore /100")
reg    = node("Registry", 615, 450, 165, 66, "compute", sub="append-only\ngap lifecycle")
ready  = node("Readiness", 790, 450, 165, 66, "compute", sub="current roll-up")
pack   = node("Audit Pack", 965, 450, 205, 66, "compute", sub="per-decision JSON")

resolver = node("Resolver (repo manifest)", 90, 540, 290, 66, "compute",
                sub="auto-fills STATIC gaps; verified updates\ntagged with source + sha256", dashed=True)
dash = node("Dashboard API", 440, 540, 230, 66, "compute", sub="/dashboard/* roll-ups")

# ── Data stores (the Hub's own) ──────────────────────────────────────────────
ddb = node("DynamoDB — EvidenceHubTable", 90, 685, 340, 90, "data",
           sub="single-table, append-only\nPAY_PER_REQUEST · PITR · RETAIN")
sec = node("Secrets Manager — EvidenceHubSecret", 470, 685, 360, 90, "data",
           sub="{ admin_api_key, ledger_read_key }\nread once at cold start")
cw  = node("CloudWatch Logs", 870, 685, 300, 90, "notify", sub="1-week retention")

# ── External: the immutable ledger (separate stack) ──────────────────────────
ledapi = node("Ledger API Gateway (prod)", 90, 870, 340, 70, "external",
              sub="GET /audit/logs\nGET /audit/events/{id}/history")
ledddb = node("Ledger DynamoDB", 470, 865, 230, 55, "data", sub="queryable copy")
leds3  = node("Ledger S3 Object Lock", 470, 945, 300, 55, "data",
             sub="WORM archive — tamper-evidence")

# ── Edges ────────────────────────────────────────────────────────────────────
edge(operator, furl, "x-api-key", HAPPY)
edge(apiclient, furl, "x-api-key", HAPPY)
edge(furl, lam, "invoke", HAPPY)

# request pipeline (left to right inside the Lambda)
edge(lam, reader, "", SUPPORT)
edge(reader, norm, "", HAPPY)
edge(norm, evaln, "", HAPPY)
edge(evaln, reg, "", HAPPY)
edge(reg, ready, "", HAPPY)
edge(ready, pack, "", HAPPY)

# the Hub reads the ledger over HTTPS (never writes to it)
edge(reader, ledapi, "reads decisions over HTTPS (read-only)", READP)
edge(ledapi, ledddb, "current copy", READP)
edge(ledapi, leds3, "archived copy + integrity", READP)

# evidence persistence
edge(reg, ddb, "append-only writes", WRITEP)
edge(ready, ddb, "reads", READP)
edge(dash, ddb, "roll-ups", READP)
edge(resolver, reg, "verified updates", WRITEP)

# supporting wiring
edge(lam, sec, "keys at cold start", SUPPORT)
edge(lam, cw, "logs", SUPPORT)

# ── Wrap + write ─────────────────────────────────────────────────────────────
XML = (
    '<mxfile host="app.diagrams.net">\n'
    '  <diagram name="Evidence Hub Architecture" id="evidence-hub">\n'
    '    <mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
    'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
    'pageWidth="1300" pageHeight="1100" math="0" shadow="0">\n'
    '      <root>\n'
    '        <mxCell id="0"/>\n'
    '        <mxCell id="1" parent="0"/>\n'
    '        ' + "\n        ".join(cells) + "\n"
    '      </root>\n'
    '    </mxGraphModel>\n'
    '  </diagram>\n'
    '</mxfile>\n'
)

out = sys.argv[1] if len(sys.argv) > 1 else "evidence-hub-architecture.drawio"
with open(out, "w", encoding="utf-8") as fh:
    fh.write(XML)
print(f"wrote {out} ({len(cells)} cells)")
