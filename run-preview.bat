@echo off
cd /d "C:\Users\AI Data Logger\evidence-hub"
set LEDGER_SOURCE=fixtures
set EVIDENCE_DB_URL=sqlite:///./data/preview.db
set EVIDENCE_MANIFEST_PATH=tests\evidence-manifest.json
".venv\Scripts\python.exe" -m uvicorn evidence_hub.api:app --host 127.0.0.1 --port 8077
