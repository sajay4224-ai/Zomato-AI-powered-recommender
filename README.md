# Zomato AI-Powered Recommender
AI-powered restaurant recommendation service that suggests restaurants based on user preferences.

## Phase 0 status
The project has resolved the implementation decisions required before application scaffolding begins.

- Dataset profile and quality assessment: [docs/phase-0-decisions.md](./docs/phase-0-decisions.md)
- Runtime configuration template: [.env.example](./.env.example)

This phase defines the dataset contract, budget mapping, filtering rules, LLM provider approach, and explicit fallback behavior used for subsequent implementation work.

## Phase 1 quick start

1. Create a virtual environment:
   `python -m venv .venv`
2. Activate it:
   `source .venv/bin/activate`
3. Install dependencies:
   `pip install -e '.[dev]'`
4. Copy the environment template and fill in real values:
   `cp .env.example .env`
5. Run the app:
   `uvicorn app.main:app --reload`
6. Run tests:
   `pytest`

The app exposes a health endpoint at `/health` and a readiness endpoint at `/ready`.
The `/api/recommend` route validates preferences, filters the catalog deterministically, ranks eligible candidates with the Gemini adapter when available, and transparently falls back to top deterministic matches if the model is unavailable or malformed.

## Release readiness and deployment

See [docs/release-readiness.md](./docs/release-readiness.md) for the deployment checklist, smoke test procedure, environment configuration, and production-readiness validation matrix.
