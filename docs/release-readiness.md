# Phase 6: Release readiness and verification

This document captures the operational checks and deployment guardrails for the Zomato AI-powered recommender.

## 1. Runtime configuration

Required environment variables are defined in [.env.example](../.env.example). Fill in real values before deployment:

- `DATASET_URL` — the dataset CSV location used for the active catalog
- `GEMINI_API_KEY` — the provider credential, never committed to source control
- `GEMINI_MODEL` — the model identifier, for example `gemini-3.5-flash-lite`
- `REQUEST_TIMEOUT_SECONDS` — maximum wait time for provider calls
- `DEFAULT_CANDIDATE_LIMIT` — number of candidates sent to the LLM
- `DEFAULT_RESULT_LIMIT` — number of recommendations shown to the user
- `SERVER_HOST` / `SERVER_PORT` — runtime bind values

Never print a secret value in logs or error output. The application logs operational metadata only, such as catalog status, candidate counts, and fallback events.

## 2. Smoke-test checklist

Run the following checks before release:

1. `python -m venv .venv`
2. `source .venv/bin/activate`
3. `pip install -e '.[dev]'`
4. `cp .env.example .env`
5. `uvicorn app.main:app --host 0.0.0.0 --port 8000`
6. `curl http://localhost:8000/health`
7. `curl http://localhost:8000/ready`
8. `curl -X POST http://localhost:8000/api/recommend -H 'Content-Type: application/json' -d '{"location":"Bangalore","budget":"medium","cuisine":["Italian"],"min_rating":4.0}'`

The application should return either a successful result set or a clear `no_results`/`invalid_request`/`service_error` response, never a misleading success-shaped empty payload.

## 3. Verification matrix

The project should satisfy the following release gates before deployment:

- Dataset loads successfully or reports a clear catalog failure.
- `/ready` reflects the current catalog status and does not claim readiness while the catalog is empty or unavailable.
- Validation errors distinguish malformed input from true no-match results.
- A provider failure produces an explicit fallback outcome instead of hiding the issue behind a false success state.
- Restaurant name, location, cuisine, rating, and cost are sourced from the catalog.
- Duplicate, unknown, or malformed LLM IDs are rejected and do not reach the final response.
- The active catalog version is preserved for the duration of a recommendation request.

## 4. Release checklist

- [ ] Required runtime variables are set in the target environment.
- [ ] The app starts successfully with the selected dataset URL.
- [ ] `/health` and `/ready` behave as expected.
- [ ] A representative recommendation request succeeds or fails with a clear state.
- [ ] The app logs candidate counts and fallback events without leaking secrets.
- [ ] A stale or missing dataset is handled as a service error, not as a false empty success.
- [ ] Tests pass in the release environment.

## 5. Production deployment notes

- Keep the app stateless at the boundary and store configuration in the environment, not in source control.
- Use the in-memory catalog as the default for the prototype and refresh it atomically at startup or on explicit rebuilds.
- Favor explicit fallback behavior over silent model masking when the ranking provider is unavailable.
- Keep the result cards catalog-grounded: the LLM only ranks candidate IDs and supplies explanations; the UI renders dataset fields from the catalog.
