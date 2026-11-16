# TP2 DevOps - Catalog microservice (Step 1)

## Run locally
    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --port 8000

Endpoints: /health, /metrics, /items (GET, POST), /items/{id} (GET, DELETE),
/checkout (POST, slow), /flaky (GET, ~30% HTTP 500).

## Tests + coverage (fails below 85 %)
    pytest -v
Reports: coverage.xml (Cobertura) and coverage.lcov (LCOV).
