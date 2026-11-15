# Phase-Wise Implementation Plan

## 1. Purpose

This plan turns the requirements in [problemStatement.md](./problemStatement.md)
and the component design in [architecture.md](./architecture.md) into an
ordered implementation roadmap. Each phase has concrete work items,
deliverables, dependencies, and exit criteria. No framework, hosting platform,
data store, or LLM provider is assumed in advance.

## 2. Phase Overview

| Phase | Name | Main outcome |
|---|---|---|
| 0 | Resolve implementation decisions | Confirm the choices needed to build a runnable application |
| 1 | Establish application foundation | Create the project structure, configuration, and quality checks |
| 2 | Ingest and normalize restaurant data | Produce a validated, reusable restaurant catalog |
| 3 | Implement preference validation and filtering | Return deterministic candidates for valid user preferences |
| 4 | Build the application interface | Collect preferences and present loading, empty, error, and result states |
| 5 | Integrate LLM ranking and explanations | Rank bounded candidates and validate grounded explanations |
| 6 | End-to-end verification and release readiness | Validate complete workflows, reliability, and deployment configuration |

Phases 2 and 3 depend on Phase 1. Phase 4 can begin after the request and
response contracts are agreed in Phase 0, and can proceed alongside Phases 2
and 3 if interfaces are stable. Phase 5 depends on the candidate and
recommendation contracts from Phases 2 and 3. Phase 6 depends on all
user-facing and recommendation components being integrated.

## 3. Detailed Phases

### Phase 0 — Resolve Implementation Decisions

**Goal:** Resolve the minimum open decisions in the architecture before
committing to application-specific dependencies or behavior.

**Work items**

- Inspect the Hugging Face dataset's available configurations, splits, fields,
  value formats, rating scale, missing-value patterns, and cost convention.
- Select the application interface pattern (for example, a web UI, API, or
  both) and the language/framework that fits the repository and deployment
  needs.
- Select an LLM provider/model and determine how credentials will be supplied
  at runtime.
- Define the initial budget bands and how they map to normalized dataset cost.
- Decide location and cuisine matching semantics, rating behavior for missing
  values, result count, and candidate limit.
- Decide whether an explicit deterministic-only fallback is in scope when the
  LLM is unavailable.
- Confirm initial hosting and dataset refresh expectations, if known.
- Record decisions and assumptions in the relevant project documentation.

**Deliverables**

- Dataset field and quality profile.
- Agreed request/response contract and matching rules.
- Chosen application and LLM integration approach.
- Documented budget mapping and fallback policy.

**Exit criteria**

- Every behavior that affects filtering or displayed facts has a defined rule.
- The source dataset can be loaded and its required fields have been mapped or
  marked unavailable.
- Required external credentials and runtime configuration are identified;
  no secrets are committed.

### Phase 1 — Establish Application Foundation

**Goal:** Create a maintainable application skeleton with repeatable local
development and validation.

**Work items**

- Create the project structure for UI/API, configuration, data ingestion,
  domain models, filtering, LLM adapter, and tests, following the selected
  framework's conventions.
- Define typed request, normalized restaurant, candidate, and response models.
- Add configuration loading and validation for dataset and LLM settings.
- Add environment-variable or secret-manager integration for credentials.
- Add the repository's formatter, linter, and test commands, or use existing
  tooling if already configured.
- Add a minimal health/readiness check if the chosen application architecture
  requires one.

**Deliverables**

- Runnable application skeleton.
- Typed domain and API/UI boundary contracts.
- Documented local setup and test commands.

**Exit criteria**

- The application starts using documented local configuration.
- Missing required configuration fails clearly rather than producing a
  success-shaped response.
- Formatting, linting, and a minimal test suite run successfully.

### Phase 2 — Ingest and Normalize Restaurant Data

**Goal:** Load the real-world dataset and expose validated restaurant records
through a stable catalog interface.

**Work items**

- Implement dataset loading from the selected Hugging Face configuration and
  split.
- Map source columns to the normalized restaurant schema.
- Normalize location and cuisine text, parse numeric rating and cost values
  where reliable, and retain display/provenance values as needed.
- Handle nulls, placeholders, malformed numeric values, duplicate records,
  and records missing required identity/display fields.
- Implement stable record IDs and ensure they are unique within a catalog
  version.
- Cache the normalized catalog for reuse across requests.
- Make initial load or refresh atomic: only publish a catalog after validation
  succeeds.
- Emit useful ingestion diagnostics and counts without exposing secrets.

**Deliverables**

- Dataset loader and normalization pipeline.
- Catalog interface with normalized restaurant records.
- Ingestion tests using representative fixtures, including malformed and
  incomplete rows.

**Exit criteria**

- The application can load the selected real dataset and report the active
  catalog size/version.
- Required fields are mapped correctly; unavailable optional values remain
  unavailable.
- Invalid rows and data-quality issues are handled according to documented
  rules.
- A failed load is reported as an error and does not replace a valid catalog
  with an empty one.

### Phase 3 — Implement Preference Validation and Filtering

**Goal:** Find eligible restaurants deterministically before any LLM call.

**Work items**

- Validate required and optional user preferences and provide actionable
  field-level validation errors.
- Normalize user inputs using the same text rules as the catalog.
- Implement location, cuisine, rating, and budget filters using Phase 0
  decisions.
- Ensure a missing rating never satisfies a requested minimum rating.
- Apply documented semantics for missing cost and optional filters.
- Implement deterministic candidate ordering, stable tie-breaking, and a
  configurable candidate limit.
- Return a no-results outcome without invoking the LLM.
- Add unit tests for boundary values, normalization, missing fields, and
  combined filters.

**Deliverables**

- Preference validation and filtering services.
- Candidate-selection rules and tests.
- Typed no-results and invalid-input outcomes.

**Exit criteria**

- Matching behavior conforms to the documented rules and is independent of
  LLM output.
- No-results and invalid-input outcomes are distinguishable from service
  failures.
- Candidate count is bounded and repeated equivalent requests produce stable
  candidate selection for an unchanged catalog.

### Phase 4 — Build the Application Interface

**Goal:** Let users submit preferences and understand the application's
response.

**Work items**

- Implement controls for location, budget, cuisine, minimum rating, and
  additional free-form preferences.
- Connect the UI or API boundary to preference validation and candidate
  selection.
- Present loading, validation, no-results, and service-error states.
- Define and render recommendation cards with name, cuisine, rating, estimated
  cost, and explanation fields, allowing unavailable dataset values.
- Clearly label cost as dataset-derived or estimated and avoid presenting it
  as a guaranteed current menu price.
- Keep the UI responsive to slow dataset or LLM operations and prevent
  accidental duplicate submissions where appropriate.

**Deliverables**

- Usable preference-entry and result experience.
- API routes/contracts if the selected design exposes an API.
- UI or API tests for valid submissions and non-success states.

**Exit criteria**

- A user can submit preferences and see the matching candidate data through the
  selected interface.
- Validation feedback, empty results, and operational errors are distinguishable.
- Missing restaurant fields are displayed as unavailable rather than omitted
  in a misleading way or fabricated.

### Phase 5 — Integrate LLM Ranking and Explanations

**Goal:** Rank filtered restaurants and explain their fit without allowing the
model to invent restaurant facts.

**Work items**

- Implement a provider-independent LLM adapter using the provider selected in
  Phase 0.
- Build the prompt from validated preferences and a bounded set of structured
  candidate fields.
- Instruct the model to rank only supplied candidate IDs, ground explanations
  in supplied evidence, and treat free-form preferences as desired criteria
  rather than restaurant facts.
- Request structured output using provider-supported schema constraints where
  available.
- Apply request timeouts and explicit provider error handling.
- Validate the response schema, candidate IDs, duplicate IDs, ranks, result
  count, and explanation length.
- Join valid IDs back to catalog records so displayed factual fields always
  come from the dataset.
- Implement the Phase 0 fallback policy, if selected; otherwise surface LLM
  failure clearly.
- Test valid, malformed, unknown-ID, duplicate-ID, timeout, and provider-error
  cases using a mocked adapter. Keep live-provider tests opt-in.

**Deliverables**

- LLM adapter and prompt contract.
- Output validation and recommendation assembly.
- Focused adapter and orchestration tests.

**Exit criteria**

- Only eligible, submitted candidates can appear in the final response.
- Restaurant name, location, cuisine, rating, and cost are sourced from the
  catalog, never trusted from model text.
- Unsupported preferences do not become asserted restaurant attributes.
- Provider failures and malformed output produce explicit, tested outcomes.

### Phase 6 — End-to-End Verification and Release Readiness

**Goal:** Verify the complete user journey and prepare a safe, repeatable
deployment.

**Work items**

- Add end-to-end coverage from preference submission through filtered results
  and validated LLM ranking.
- Verify dataset facts shown in results map back to source records.
- Verify no-match, missing-data, invalid-input, dataset-failure, LLM-failure,
  and malformed-output workflows.
- Review logs for secrets and unnecessary user-preference data; add useful
  operational signals such as catalog load status, candidate counts, and LLM
  latency.
- Review timeouts, input length limits, candidate limits, and error messages.
- Document installation, runtime configuration, dataset refresh, LLM setup,
  testing, and deployment.
- Run the repository's full relevant test, lint, and build checks.
- Deploy to the selected environment and perform a smoke test with a
  representative request.

**Deliverables**

- End-to-end test coverage and release checklist.
- Deployment/runtime documentation.
- Verified deployable application.

**Exit criteria**

- The full workflow succeeds with real dataset records and the configured LLM.
- All defined failure states are handled without fabricating recommendations.
- Tests, lint, and build pass in the target environment.
- Runtime secrets are configured outside source control, and the deployed
  application passes a smoke test.

## 4. Cross-Phase Quality Gates

Apply these checks throughout implementation:

- Keep ingestion, filtering, LLM integration, and presentation independently
  testable.
- Use typed contracts at component boundaries.
- Do not silently convert ingestion/provider failures into empty success
  results.
- Keep LLM candidate context bounded and user input length-limited.
- Preserve factual provenance for displayed restaurant attributes.
- Update setup and operational documentation when implementation decisions
  change.

## 5. MVP Completion Checklist

- [ ] Dataset is loaded from the specified Hugging Face source and normalized.
- [ ] User can submit location, budget, cuisine, minimum rating, and optional
      additional preferences.
- [ ] Deterministic filters return a bounded set of eligible candidates.
- [ ] LLM ranks candidates and generates evidence-based explanations.
- [ ] Output validation prevents unknown or ineligible restaurants from being
      displayed.
- [ ] Results show restaurant name, cuisine, rating, estimated cost, and
      explanation where available.
- [ ] Empty results and dataset, validation, and LLM errors are clearly
      distinguishable.
- [ ] Automated tests, lint, and build pass; runtime setup is documented.
