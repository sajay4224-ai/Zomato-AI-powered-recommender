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

# Zomato AI-Powered Restaurant Recommender

An end-to-end AI restaurant recommendation web application built with FastAPI, deterministic catalog filtering, and Google Gemini (`gemini-3.5-flash`).

- **Live Frontend (Vercel):** https://vercel.app
- **Live Backend API (Railway):** https://railway.app

---

## 1. System Prompt
The LLM ranking layer receives pre-filtered, verified restaurant candidates from the Zomato dataset along with the user's preferences and follows a strict system instruction:

> You are a grounded restaurant recommendation assistant. Rank only the candidate restaurants provided in the input JSON based on the user's preferred neighborhood, cuisine, budget tier, minimum rating, and free-text preferences. Return strictly valid JSON matching the required response schema. Do not invent restaurants, prices, ratings, or locations outside the provided candidate list.

---

## 2. Response Schema
The `/api/recommend` endpoint returns a structured JSON response validated via Pydantic:

```json
{
  "query_summary": {
    "location": "Indiranagar",
    "cuisine": "North Indian",
    "budget": "mid",
    "min_rating": 4.0
  },
  "recommendations": [
    {
      "restaurant_name": "Example Bistro",
      "location": "Indiranagar",
      "cuisines": ["North Indian", "Mughlai"],
      "rating": 4.4,
      "approx_cost_for_two": 900,
      "match_score": 94,
      "explanation": "Matches your Indiranagar North Indian preference within a mid-range budget and holds a 4.4 rating."
    }
  ],
  "fallback_used": false,
  "warning": null
}
```

---

## 3. What Changed Across Prompt & Model Versions (and Why)
- **v1 (Open-Ended Prompting):** Initially asked the model to suggest restaurants directly from user preferences. This risked hallucinating venues not present in the Zomato dataset and occasionally returned conversational markdown instead of clean JSON.
- **v2 (Candidate-Grounded JSON Prompting):** Switched to a two-stage pipeline—deterministic Python filtering first selects the top 20 real candidates, and the prompt instructs Gemini to rank only those candidates and output strict JSON.
- **v3 (Model Upgrade & Timeout Resilience):** Upgraded `GEMINI_MODEL` to `gemini-3.5-flash` with query-parameter authentication and a 90-second timeout budget, adding automatic deterministic fallback so the UI always returns reliable recommendations even during API rate limits.

---

## 4. How Scope Limits Are Enforced
- **Deterministic Catalog Pre-Filtering:** User inputs (location, cuisine, budget, minimum rating) are validated and filtered against the loaded Zomato dataset *before* calling the LLM, ensuring only real, in-catalog venues enter the prompt context.
- **Closed-World Prompt Guardrail:** The system prompt explicitly restricts Gemini to ranking and explaining only the supplied candidate IDs/records and forbids external venue generation.
- **Schema Validation & Safe Fallback:** Pydantic validates every model response; if output is malformed or out of scope, the backend discards it and safely falls back to deterministic ranking.

---

## 5. Tech Stack
- **Backend:** Python, FastAPI, Uvicorn, Pydantic Settings, HTTPX
- **AI / LLM:** Google Gemini (`gemini-3.5-flash`)
- **Frontend:** HTML5, CSS3, Vanilla JavaScript
- **Deployment & DevOps:** Railway (Backend API), Vercel (Frontend CDN), GitHub & GitHub Codespaces
