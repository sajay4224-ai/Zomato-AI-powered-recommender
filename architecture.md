# Project Architecture

## 1. Purpose and Scope

This document describes a proposed logical architecture for the Zomato
AI-Powered Restaurant Recommender described in [problemStatement.md](./problemStatement.md).
It covers dataset ingestion, preference handling, deterministic filtering,
LLM-assisted ranking and explanations, and presentation of results.

The repository has not specified a web framework, hosting platform, database,
or LLM provider. The architecture therefore defines responsibilities and
interfaces without assuming a particular implementation technology.

## 2. Design Principles

- **Dataset-grounded results:** Restaurant facts come from ingested dataset
  records, not from LLM output.
- **Deterministic eligibility:** Location, cuisine, budget, and minimum-rating
  filters are applied by application code before LLM ranking.
- **Bounded LLM context:** Send only relevant candidate records and the
  preferences needed to rank them.
- **Validated output:** Treat LLM output as untrusted structured data; accept
  only recommendations that refer to supplied candidates.
- **Explicit data quality:** Preserve missing values and surface them as
  unavailable instead of inventing or silently substituting values.
- **Separation of concerns:** Keep data ingestion, filtering, LLM integration,
  and presentation independently testable.

## 3. Logical Architecture

```text
                         ┌──────────────────────────┐
                         │       User / UI          │
                         │ preferences + results    │
                         └────────────┬─────────────┘
                                      │ Preferences
                                      ▼
                         ┌──────────────────────────┐
                         │ Input validation and     │
                         │ request orchestration    │
                         └────────────┬─────────────┘
                                      │ Valid preferences
                                      ▼
┌─────────────────────┐    ┌──────────────────────────┐
│ Hugging Face        │───▶│ Dataset ingestion and    │
│ Zomato dataset      │    │ normalization            │
└─────────────────────┘    └────────────┬─────────────┘
                                         │ Normalized records
                                         ▼
                              ┌──────────────────────────┐
                              │ Restaurant catalog       │
                              │ (in-memory or persisted)  │
                              └────────────┬─────────────┘
                                           │
                                           ▼
                              ┌──────────────────────────┐
                              │ Deterministic filtering  │
                              │ and candidate selection │
                              └────────────┬─────────────┘
                                           │ Candidates + preferences
                                           ▼
                              ┌──────────────────────────┐
                              │ LLM adapter              │
                              │ rank + explain           │
                              └────────────┬─────────────┘
                                           │ Structured ranking
                                           ▼
                              ┌──────────────────────────┐
                              │ Output validation and   │
                              │ result assembly          │
                              └────────────┬─────────────┘
                                           │ Recommendations
                                           └──────────────▶ User / UI
```

The LLM is not a data source or a replacement for filtering. It ranks
eligible candidates and produces explanations using the information supplied
to it.

## 4. Component Responsibilities

### 4.1 User Interface

Collect the following inputs:

| Input | Suggested representation |
|---|---|
| Location | User-entered text or a supported location selection |
| Budget | Low, medium, or high |
| Cuisine | Optional text or one or more cuisine selections |
| Minimum rating | Optional numeric threshold within the dataset's rating scale |
| Additional preferences | Optional free-form text, such as family-friendly or quick service |

Display a loading state during recommendation generation, validation errors
next to the relevant inputs, a clear no-results state, and an actionable error
if recommendations cannot be generated.

### 4.2 Input Validation and Orchestration

Validate and normalize the request before running a search:

- Trim and normalize text for matching while retaining display-ready input.
- Validate the rating threshold against the rating scale discovered for the
  dataset.
- Validate budget against the supported values.
- Enforce reasonable length limits on free-form preferences.
- Reject malformed requests with clear validation errors.

Orchestrate the request in sequence: obtain the catalog, filter candidates,
invoke ranking when there are candidates, validate the ranking, and assemble
the response. Apply a request timeout to external LLM calls.

### 4.3 Dataset Ingestion and Normalization

Load the
[ManikaSaini Zomato restaurant recommendation dataset](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation)
from Hugging Face. The ingestion component should:

1. Load the selected dataset configuration and split.
2. Inspect the available columns and map source fields to a stable internal
   schema.
3. Normalize text, numeric values, and missing-value markers.
4. Parse cost and rating only when their source values can be interpreted
   reliably.
5. Deduplicate records where a stable identity or sufficiently reliable
   combination of fields is available.
6. Report ingestion errors and basic data-quality counts.
7. Publish the normalized catalog only after a successful load and validation.

Do not assume source column names or a particular cost convention until the
dataset has been inspected. Keep source values or provenance where useful so
normalization can be audited. A failed refresh should not be represented as a
successful empty dataset.

### 4.4 Restaurant Catalog

Provide a read interface to the normalized records. The initial implementation
may keep the catalog in memory if dataset size and deployment constraints
allow. A database or search index can be introduced later if refresh, scale, or
concurrent access requires it.

Suggested internal record:

```text
Restaurant:
  id: stable application identifier
  name: string
  location: optional string
  cuisines: list of strings
  cost: optional numeric value
  cost_display: optional string
  rating: optional numeric value
  source_fields: optional map of relevant original values
```

The stable `id` must uniquely identify a record within a catalog version. It
may be generated from source identifiers when available or from a documented
stable key. Do not rely on LLM-generated names as identifiers.

### 4.5 Deterministic Filtering and Candidate Selection

Apply user constraints in application code:

- **Location:** Match normalized location values. Define and test whether
  matching uses exact, prefix, or token-based comparison.
- **Cuisine:** Match normalized cuisine values using a documented
  case-insensitive strategy.
- **Rating:** Exclude records with a known rating below the threshold. Decide
  explicitly whether records without a rating are excluded when a minimum is
  requested; they must not be treated as meeting the threshold.
- **Budget:** Compare a normalized source cost value against explicit budget
  bands. Define those bands from a documented product configuration or a
  deliberate dataset-based rule; do not infer them inconsistently per request.
- **Additional preferences:** Pass this text to ranking only as a soft
  preference. Do not claim a restaurant is family-friendly, offers quick
  service, or has another attribute unless the dataset provides evidence.

If filters produce no candidates, return a no-results response without
calling the LLM. If more candidates match than should be sent to the model,
select a bounded candidate set using deterministic relevance criteria and
stable tie-breaking. Keep the candidate limit configurable at the application
level and within the model's context constraints.

### 4.6 LLM Adapter

Encapsulate provider-specific SDK or API behavior behind an adapter. The
adapter is responsible for:

- Reading credentials from runtime configuration or a secret manager, never
  from source-controlled files.
- Sending only the user's relevant preferences and the bounded candidate
  records.
- Requesting a structured response, preferably using the provider's
  structured-output facility where available.
- Applying timeouts and handling provider errors explicitly.
- Returning a typed ranking result to the orchestration layer.

Keep the provider, model, timeout, and candidate limit configurable without
changing filtering or presentation logic.

#### Prompt contract

The system/developer instructions to the model should specify:

1. Rank only the supplied candidate IDs.
2. Use the user's preferences to order eligible options.
3. Explain each recommendation using only supplied candidate fields and user
   preferences.
4. Do not invent restaurant details or assert unsupported attributes.
5. Treat additional free-form preferences as desired criteria, not as facts
   about any restaurant.
6. Return the requested schema and a short summary if requested.

Suggested model response:

```json
{
  "recommendations": [
    {
      "restaurant_id": "catalog-record-id",
      "rank": 1,
      "explanation": "A concise explanation grounded in the supplied data."
    }
  ],
  "summary": "Optional concise overview of the returned choices."
}
```

The model must not supply authoritative restaurant name, rating, cuisine,
location, or cost fields. The application joins the returned IDs to the
catalog and fills all displayed facts from trusted normalized records.

### 4.7 Output Validation and Result Assembly

Validate the LLM response before displaying it:

- Parse the expected schema; reject malformed output.
- Verify each ID belongs to the submitted candidate set.
- Remove duplicate IDs and invalid ranks.
- Enforce the requested result limit.
- Ensure explanations are present and within reasonable length limits.
- Populate factual fields from the catalog, not the model response.

If the LLM fails or returns unusable output, report the failure clearly.
Returning deterministic matches without AI explanations is a possible product
fallback, but should be an explicit, documented behavior rather than a silent
success-shaped response.

### 4.8 Presentation

For each recommendation, display:

- Restaurant name
- Cuisine
- Rating
- Estimated cost, with units or source convention when known
- AI-generated explanation

Mark unknown values as unavailable and distinguish estimated or
dataset-derived cost from a guaranteed current menu price. Optionally show a
short summary and the applied preference criteria.

## 5. Data and API Contracts

### Recommendation request

```json
{
  "location": "Bangalore",
  "budget": "medium",
  "cuisines": ["Italian"],
  "minimum_rating": 4.0,
  "additional_preferences": "Family-friendly"
}
```

Optional inputs may be omitted or empty. The numeric example is illustrative;
accepted rating bounds must be derived from the dataset's actual rating scale.

### Recommendation response

```json
{
  "recommendations": [
    {
      "restaurant_id": "catalog-record-id",
      "name": "Restaurant name from the dataset",
      "location": "Location from the dataset",
      "cuisines": ["Cuisine from the dataset"],
      "rating": 4.2,
      "estimated_cost": "Cost from the dataset, with its convention if known",
      "explanation": "AI-generated explanation grounded in the supplied data."
    }
  ],
  "summary": "Optional overview.",
  "status": "ok"
}
```

The response's restaurant facts are resolved from the catalog. For no matches,
return an empty recommendations list with a `no_results` status and a useful
message. For failures, surface an explicit error status/message through the
application's standard error mechanism; do not confuse a failed search with no
matches.

## 6. End-to-End Request Sequence

1. The user submits preferences through the UI.
2. The application validates and normalizes the request.
3. The orchestrator obtains the current normalized catalog.
4. The filter applies supported hard constraints and selects a bounded set of
   candidates.
5. If there are no candidates, the application returns a no-results response.
6. Otherwise, the orchestrator sends candidate IDs, relevant candidate
   fields, and preferences to the LLM adapter.
7. The adapter returns a structured ranking and explanations or an explicit
   error.
8. The application validates IDs and response shape, joins IDs back to catalog
   records, and assembles the final response.
9. The UI presents the recommendations, explanations, or the appropriate
   empty/error state.

## 7. Data Lifecycle and Operations

- Load the dataset at startup or through a controlled refresh operation.
- Cache the normalized catalog so each user request does not re-download the
  dataset.
- Associate a catalog version or load timestamp with records used for a
  request where practical.
- Refresh atomically: validate a new catalog before making it active.
- Log operational events such as dataset load failures, candidate counts,
  LLM latency, and validation failures. Avoid logging API credentials or
  unnecessary free-form user text.
- Keep provider credentials and environment-specific configuration outside
  the repository.

## 8. Failure Handling

| Failure | Expected behavior |
|---|---|
| Dataset unavailable or invalid | Report an ingestion/service error; do not claim there are no matches |
| Optional restaurant field missing | Keep the value unavailable and continue where safe |
| Invalid user input | Return a specific validation error |
| No matching restaurants | Return `no_results` without an LLM request |
| LLM timeout/provider error | Surface an explicit recommendation error or a documented deterministic fallback |
| Malformed LLM response | Reject invalid output; do not display fabricated or unvalidated recommendations |
| LLM returns unknown/duplicate IDs | Discard invalid entries and validate the remaining results; report if none remain |

## 9. Security, Privacy, and Reliability

- Keep LLM credentials server-side and out of client code, logs, and version
  control.
- Send only the minimum restaurant fields and preference data needed for
  ranking.
- Treat user-entered additional preferences and model responses as untrusted
  input.
- Set request size, candidate count, and external-call time limits.
- Avoid exposing stack traces or provider secrets in user-facing errors.
- Make external dataset and LLM failures observable through logs and metrics
  without recording sensitive data.

## 10. Verification Strategy

Test each boundary independently:

- **Ingestion:** source-field mapping, numeric parsing, missing values,
  malformed records, and deduplication behavior.
- **Filtering:** location/cuisine normalization, budget boundaries, rating
  thresholds, missing ratings, and empty results.
- **LLM adapter:** prompt inputs, valid structured output, timeout, provider
  error, and malformed output handling.
- **Output assembly:** candidate-ID validation, duplicate IDs, and factual
  fields always resolved from the catalog.
- **UI or API:** valid request, validation error, no results, and service
  failure states.
- **End-to-end:** preferences produce recommendations whose factual fields
  correspond to actual dataset records and whose explanations are grounded in
  the provided candidate data.

## 11. Implementation Decisions to Confirm

The following are intentionally left open until implementation requirements
or deployment constraints are known:

- UI framework and whether the application exposes an API
- Dataset configuration, split, and refresh schedule
- In-memory catalog versus persistent storage or search index
- Exact location and cuisine matching behavior
- Budget band definitions and source cost interpretation
- LLM provider, model, structured-output support, and result count
- Whether to provide deterministic recommendations when the LLM is unavailable
- Hosting, monitoring, and deployment environment
