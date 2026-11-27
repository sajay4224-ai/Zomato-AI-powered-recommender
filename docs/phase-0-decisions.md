# Phase 0: Implementation Decisions

This document records the implementation decisions required before the project moves into application scaffolding and feature work. The decisions below are intentionally explicit and are used as the contract for Phases 1-5.

## 1. Dataset profile

### Selected source
- Dataset: `ManikaSaini/zomato-restaurant-recommendation`
- Data file: `zomato.csv`
- Source URL: `https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation`
- Access pattern: direct CSV download from the dataset repository at startup or refresh time; no custom dataset configuration is needed because the repository exposes a single CSV asset.

### Observed schema
The dataset contains 51,717 rows and the following fields:

- `url`
- `address`
- `name`
- `online_order`
- `book_table`
- `rate`
- `votes`
- `phone`
- `location`
- `rest_type`
- `dish_liked`
- `cuisines`
- `approx_cost(for two people)`
- `reviews_list`
- `menu_item`
- `listed_in(type)`
- `listed_in(city)`

### Quality profile
- `name`: always present; no missing values.
- `listed_in(city)`: always present; stable city dimension for search.
- `location`: 21 missing values; neighborhood-level field that is useful when a user requests a local area.
- `cuisines`: 45 missing values; treat as optional but not as a successful cuisine match.
- `rate`: 7,775 missing values, and textual values such as `4.1/5`, `3.8/5`, and `NEW` appear in the source.
- `approx_cost(for two people)`: 346 missing values; values are integer-style cost strings such as `800`, `1,000`, and `1,500`.
- `rest_type`: 227 missing values.

### Cost and rating conventions
- Rating values are represented as strings in a 0-5 style scale, commonly `X/5` with decimal values like `3.8/5` and `4.9/5`.
- Missing or non-numeric ratings are not treated as passing a minimum rating threshold.
- The cost column is the dataset's approximate cost for two people, represented in INR as a plain integer-like value without a currency symbol. Example values: `800`, `1000`, `1500`.
- The dataset may also contain placeholder values such as `-` for ratings; those are normalized to `null`/unavailable.

### Data-quality rules adopted
- Preserve original values in source metadata for diagnostics.
- Normalize recognized missing markers (`''`, whitespace, `-`, `NEW`, `N/A`, `null`) to `null` before filtering.
- Reject or quarantine rows that cannot produce a stable record ID.
- Keep location and cuisine normalization case-insensitive but do not merge unrelated names via fuzzy matching.

## 2. Application and interface pattern

### Chosen stack
- Backend: Python + FastAPI
- UI: light server-rendered HTML via Jinja2 templates + minimal JavaScript for interaction
- API: JSON endpoints for recommendation requests and health checks
- Runtime config: environment variables and `.env` files (never committed)

### Why this stack
- The repository is still at a prototype stage and the project needs a simple, fast, testable path.
- A single-process FastAPI service keeps the app easy to run locally while still supporting a JSON API boundary for future extensions.
- The UI can be simple enough to satisfy the requirement without adding a heavier frontend framework prematurely.

### Runtime configuration contract
The app reads the following environment variables at runtime:

- `DATASET_URL` — HF CSV URL for the restaurant catalog
- `GEMINI_API_KEY` — Gemini credential, never committed to the repo
- `GEMINI_MODEL` — default Gemini model name, e.g. `gemini-3.5-flash-lite`
- `REQUEST_TIMEOUT_SECONDS` — model timeout window
- `DEFAULT_CANDIDATE_LIMIT` — candidate count sent to the LLM
- `DEFAULT_RESULT_LIMIT` — number of recommendations to show to the user
- `SERVER_HOST` / `SERVER_PORT` — local runtime binding

A repo-local `.env.example` establishes the expected names without exposing secrets.

## 3. LLM provider and orchestration approach

### Selected provider
- Provider: Google Gemini via the official Google Generative AI SDK
- Model: `gemini-3.5-flash-lite` for the initial implementation
- Rationale: strong multimodal/structured-output capabilities, low latency, and a straightforward Python integration for ranking and explanation tasks

### Provider-independent adapter contract
The LLM layer is implemented behind an adapter interface with the following responsibilities:
- read credentials from environment variables only
- accept a list of normalized restaurant candidates and the validated user request
- rank only the IDs in the supplied candidate set
- return a typed structured ranking payload
- surface provider and timeout errors explicitly

The recommendation workflow remains provider-agnostic at the application layer. The adapter handles request/response translation.

## 4. Request and response contract

### Request contract
```json
{
  "location": "Bangalore",
  "budget": "medium",
  "cuisine": ["Italian", "Chinese"],
  "min_rating": 4.0,
  "additional_preferences": "family friendly"
}
```

### Response contract
```json
{
  "status": "success",
  "recommendations": [
    {
      "restaurant_id": "stable-catalog-id",
      "rank": 1,
      "explanation": "Grounded explanation using dataset facts and user preferences."
    }
  ],
  "summary": "Optional concise overview of the returned options.",
  "catalog_version": "2026-11-15T00:00:00Z"
}
```

### Validation/error outcomes
- `invalid_request` — malformed or unsupported user input
- `no_results` — filtering found no candidate restaurants
- `service_error` — dataset failure, provider failure, or unexpected runtime error
- `success` — valid recommendations returned and validated

The application never displays model-generated restaurant facts as authoritative. The final UI always joins model-selected IDs back to the trusted catalog before rendering name, cuisine, rating, cost, and location.

## 5. Matching rules and filters

### Budget mapping
Budget bands map to the dataset cost convention (`approx_cost(for two people)`, INR for two people):
- `low`: `<= 500`
- `medium`: `> 500` and `<= 1000`
- `high`: `> 1000`

Records with missing cost are not treated as budget matches. They may appear in a diagnostic state if a user requests an incomplete dataset, but they do not satisfy a budget filter.

### Location matching
- Primary match is the normalized `listed_in(city)` value, because city-level requests are the product contract.
- A neighborhood-level `location` may be used only as a secondary, user-friendly hint when present.
- Exact, case-insensitive string equality is used for the initial implementation. No broad prefix or fuzzy city expansion is allowed.

### Cuisine matching
- Matching is case-insensitive and uses normalized cuisine tokens from the `cuisines` field.
- If the user supplies multiple cuisines, the application applies OR semantics (`restaurant matches if any requested cuisine is present`).
- If a restaurant has no cuisine data, it is not treated as a cuisine match.

### Rating behavior
- Minimum rating is a required numeric threshold when supplied.
- A record with a missing rating never satisfies `min_rating`.
- `min_rating` uses an inclusive comparison: `rating >= min_rating`.

### Candidate selection and result counts
- Candidate limit before LLM ranking: 20
- Final display limit: 5
- Selection order is deterministic: sort by rating descending, cost fit descending, then by a stable catalog ID as a final tie-breaker

This ensures repeated equivalent calls produce stable candidate lists when the catalog is unchanged.

## 6. Deterministic fallback policy

The application includes an explicit fallback path when the LLM is unavailable or fails:
- If there are valid filtered candidates but the model is unavailable, return the top deterministic candidates with an `ai_unavailable` or `fallback` marker.
- If the LLM is disabled by configuration, the service should still return the best-ranked candidates without claiming they were AI-ranked.
- The fallback is not a silent success mask; it is an explicit, testable behavior.

The fallback policy is on by default to keep the app usable during provider outages while preserving the requirement that factual card data remains catalog-grounded.

## 7. Hosting and refresh expectations

### Initial hosting decision
- Host the application as a single Python service in a standard managed runtime such as Render or Railway.
- Keep the catalog in memory at runtime; no database is required in this phase.
- Dataset refresh occurs at app startup and on an explicit refresh action or scheduled maintenance window.

### Refresh policy
- A failed refresh must not replace a valid active catalog with an empty or partial catalog.
- Requests use a consistent catalog snapshot for filtering and display.
- Catalog version can be tracked by the last successful load timestamp.

## 8. Exit criteria status for Phase 0

The following are resolved and documented:
- dataset source, configuration, schema, and quality profile are known
- the request/response contract and matching rules are agreed
- the application pattern and LLM integration approach are selected
- the budget mapping and fallback policy are defined
- external credentials and runtime env names are identified without committing secrets

These decisions are the contract for Phase 1 and beyond.
