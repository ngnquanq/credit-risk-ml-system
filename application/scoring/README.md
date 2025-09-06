# Credit Risk Scoring (BentoML)

Small, modular BentoML service for real-time scoring.

## Endpoints
- `GET /healthz` — service health and model metadata
- `POST /v1/score` — request body: `{ "features": {"f1": 1.2, ...}, "user_id": 123 }`

## Configuration (env)
- `SCORING_MODEL_SOURCE` — `local|mlflow` (default `local`)
- `SCORING_MODEL_PATH` — path to pickle/joblib when `local`
- `SCORING_MLFLOW_MODEL_URI` — MLflow model URI when `mlflow`
- `SCORING_PREDICTION_THRESHOLD` — default `0.5`
- `SCORING_FEATURE_NAMES` — comma-separated feature order (optional)
- `SCORING_LOG_FORMAT` — `json|text` (default `json`)
- `SCORING_LOG_LEVEL` — `INFO|DEBUG|...` (default `INFO`)

## Build & Serve
```
cd application/scoring
bentoml serve . --port 3000 --reload

# (Optional) Build a Bento and container image
bentoml build
bentoml containerize credit_risk_scoring:latest -t bentoml/credit-risk-model:latest
```

## Notes
- Keep feature order stable via `SCORING_FEATURE_NAMES` for deterministic inference.
- Swap model backend by changing envs without code changes.
- Extend with Feast/DB logging by adding small modules without touching `service.py`.
