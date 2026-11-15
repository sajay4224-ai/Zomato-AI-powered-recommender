# Edge Cases and Corner Scenarios

This document catalogs edge cases for the Zomato AI-Powered Restaurant
Recommender. Expected behavior should be implemented and tested at the
component boundary that owns it. Where behavior depends on an unresolved
product choice, the scenario is marked **Decision required** and should be
settled before release, as described in
[implementation-plan.md](./implementation-plan.md) and
[architecture.md](./architecture.md).

## 1. Dataset Availability and Ingestion

| Scenario | Expected handling |
|---|---|
| Hugging Face is unreachable, rate-limited, or returns an error | Report an ingestion/service failure. Do not treat it as an empty dataset or claim there are no matches. |
| Selected dataset, configuration, or split no longer exists | Fail with a clear configuration/schema error and retain the prior valid catalog if one exists. |
| Dataset download is interrupted or partially completed | Do not publish partial records; retry only under an explicit bounded retry policy. |
| Dataset is empty | Report a valid-but-empty catalog distinctly from a load failure; return no matches only after the application has confirmed the catalog is valid and empty. |
| Dataset schema changes, a required source column is renamed, or an unexpected type appears | Detect and report schema drift. Do not silently map unrelated fields or publish an invalid catalog. |
| Optional columns are missing | Continue if safe, marking affected attributes unavailable. |
| A row has nulls, empty strings, whitespace, `N/A`, `-`, `null`, or another placeholder | Normalize recognized missing markers to unavailable; preserve original values where needed for diagnostics. |
| A row has an invalid encoding or unexpected Unicode | Decode safely where possible; reject or quarantine the affected row with a diagnostic rather than corrupting the catalog. |
| A dataset field contains a list, delimited string, or mixed format | Parse using the observed source format; do not assume one representation without validation. |
| A row is missing its restaurant name or cannot form a stable ID | Apply the documented row eligibility rule; never create an ID that collides with another record. |
| Duplicate rows occur | Deduplicate only according to a documented stable key. Do not merge distinct branches merely because their names match. |
| Dataset contains duplicate names at different locations | Preserve distinct records and display enough location context to distinguish them. |
| Numeric values include commas, currency symbols, units, decimal separators, or ranges | Parse only formats covered by explicit normalization rules; retain the display/source value when a numeric interpretation is uncertain. |
| Numeric values are negative, implausibly large, `NaN`, or infinite | Reject or mark unavailable according to field validation; never let invalid numbers pass filters. |
| Rating uses textual labels such as `NEW`, `Not rated`, or `Excellent` | Map only known source labels according to the confirmed rating policy; otherwise mark unavailable. |
| Rating scale differs from assumptions (for example, values are percentages or use a different maximum) | Derive validation bounds from inspected data/configuration; do not hard-code an unsupported scale. |
| Cost is not comparable across records or its convention is unclear | Keep it unavailable or display the source value with an explicit convention; do not imply a comparable numeric price. |
| Dataset refresh fails while an older catalog is active | Keep the prior catalog only if the stale-catalog policy permits it; report its age/status and do not claim a fresh load. **Decision required:** stale-data availability policy. |
| Two refreshes overlap or requests occur during refresh | Publish catalogs atomically; each request should use one consistent catalog version. |
| A refresh produces a catalog with invalid IDs or fails validation | Do not replace the active catalog. |

## 2. Restaurant Normalization and Identity

- **Case and whitespace differences:** Normalize for comparisons while
  preserving a display-friendly source name.
- **Punctuation, accents, and Unicode variants:** Avoid overly aggressive
  normalization that merges distinct restaurant or location names.
- **Multiple cuisines:** Treat cuisine as a collection when the source
  supports it; match according to the defined any-match/all-match rule.
  **Decision required:** whether multiple requested cuisines use OR or AND
  semantics.
- **Cuisine aliases or spelling variants:** Apply only an explicit alias
  mapping; do not infer unrelated cuisines from approximate text matches.
- **Location hierarchy:** A city, neighborhood, and locality may share text.
  Define whether a city-level query includes its neighborhoods and how
  ambiguous names are handled. **Decision required:** location hierarchy and
  match semantics.
- **Same restaurant brand with multiple branches:** Keep branches distinct
  when the dataset provides distinct locations or records.
- **Missing location/cuisine/rating/cost:** Preserve missingness. Do not fill
  values from another branch, search result, or LLM response.
- **Catalog ID stability:** IDs must be unique within a catalog version.
  If IDs can change after refresh, do not use them as long-lived external
  identifiers without a versioning strategy.
- **Display collisions:** If two results have the same name, include location
  or another dataset-provided distinguishing field when available.

## 3. User Input and Validation

| Scenario | Expected handling |
|---|---|
| All inputs are blank or contain only whitespace | Validate according to the product's minimum search requirements; return actionable feedback rather than launching a broad accidental search. **Decision required:** required fields and default search behavior. |
| Optional fields are omitted, null, empty, or whitespace-only | Normalize consistently to “not provided.” |
| Location or cuisine contains leading/trailing whitespace or different casing | Normalize for matching, retain the original value for display where appropriate. |
| User enters an unsupported or ambiguous location | Do not silently broaden to a different city. Return no matches or ask for clarification according to the UI design. |
| User enters a cuisine not represented in the dataset | Return no matches or an explanatory empty state; do not substitute a different cuisine. |
| Multiple cuisine values are submitted with duplicates or mixed casing | Normalize and deduplicate before applying the documented matching semantics. |
| Budget has an unsupported value or unexpected capitalization | Validate against the supported low/medium/high values; return a clear error or normalize capitalization consistently. |
| Cost is missing for a restaurant and a budget is specified | Do not claim the restaurant fits the budget. **Decision required:** exclude unknown-cost records or show them separately. |
| Cost lies exactly on a budget-band boundary | Apply documented inclusive/exclusive boundaries consistently and cover them with tests. |
| Budget bands overlap or leave gaps | Configuration validation should reject invalid bands; each valid cost should map to at most one tier. |
| Minimum rating is below/above the supported scale | Reject or clamp only if that behavior is explicitly selected; prefer a clear validation message. **Decision required:** accepted range and out-of-range behavior. |
| Minimum rating equals a restaurant's rating exactly | Follow the documented inclusive threshold rule and test the boundary. |
| Restaurant rating is missing while a minimum is specified | Never treat missing as passing. **Decision required:** exclude it or include it as “rating unavailable” only if the product explicitly allows that distinction. |
| Additional preferences are exceptionally long | Enforce a documented length limit before the LLM call and provide clear feedback. |
| Additional preferences contain prompt-like instructions or attempts to override system behavior | Treat them as untrusted preference text; keep the ranking instructions and candidate boundaries authoritative. |
| Additional preferences ask for facts absent from the dataset (for example, parking, allergy safety, family-friendly facilities, or opening hours) | Do not assert those properties. Explain that available data cannot verify them, or leave them out according to the response policy. |
| Input includes control characters, markup, or HTML | Escape for display and serialize safely for the LLM/API; do not render as executable markup. |
| Input has a very large number of cuisine selections or malformed numeric values | Enforce request size and type limits; return validation errors before filtering or model invocation. |
| Repeated form submission sends the same request more than once | Prevent accidental duplicate work in the UI where practical; ensure repeated requests do not corrupt shared state. |

## 4. Filtering and Candidate Selection

- **No records match all hard filters:** Return a `no_results` outcome and do
  not call the LLM.
- **One candidate matches:** Return it without requiring a minimum result
  count.
- **More candidates match than the LLM limit:** Select a bounded candidate
  subset using deterministic criteria and stable tie-breaking. Do not
  arbitrarily send an unbounded catalog.
- **Many near-identical records or branches:** Avoid accidentally returning
  only duplicates when the selection strategy can distinguish them. Any
  diversity rule must be explicit and deterministic.
- **Tie on every selection criterion:** Use a stable final tie-breaker, such
  as the normalized record ID.
- **Missing optional fields:** A missing cuisine/location/cost must not be
  treated as an affirmative match to the corresponding requested filter.
- **Filter normalization differs from ingestion normalization:** Use shared
  normalization rules so results do not depend on which component processed
  the value.
- **Independent filters conflict:** Apply the documented AND/OR semantics;
  do not drop a user constraint silently to produce more results.
- **Broad or empty filters yield a very large result set:** Enforce a bounded
  candidate count and context budget.
- **Candidate list is empty after candidate selection:** Return no results;
  never invoke the LLM with an empty list.
- **Catalog changes between filtering and result assembly:** Keep the
  catalog version or immutable record snapshot consistent for the entire
  request so selected IDs still resolve to the same facts.
- **Candidate source data contains user-like instructions or prompt injection
  text:** Treat dataset values as data, not instructions; delimit/serialize
  fields and enforce the candidate-ID allowlist after model response.
- **Filtering error versus valid no-match:** Surface an internal filtering
  failure as an error, not as `no_results`.

## 5. LLM Request and Response

| Scenario | Expected handling |
|---|---|
| Credentials are missing or invalid | Fail clearly at configuration/integration boundary; never expose credential values. |
| Provider is unavailable, rate-limits, or returns a server error | Apply only bounded retries for retryable failures; surface an explicit error or the documented fallback. |
| Request times out or is cancelled | Stop waiting within the configured timeout; do not return incomplete recommendations as successful. |
| Candidate payload exceeds context or request-size limits | Keep candidate and field limits bounded; handle provider limit errors explicitly rather than truncating arbitrary data silently. |
| Model returns invalid JSON, extra prose, or fenced JSON | Parse only supported response formats; reject malformed output rather than guessing at structure. |
| Response is truncated or missing required fields | Reject or validate remaining entries only under a documented partial-result policy. **Decision required:** whether valid partial output may be shown. |
| Model invents a restaurant or returns an unknown ID | Reject that item; never display it. |
| Model returns a candidate that did not pass hard filters | Reject it even if the explanation sounds plausible. |
| Model returns duplicate candidate IDs | Deduplicate deterministically and validate remaining ranks. |
| Model returns negative, repeated, missing, or non-numeric ranks | Reconstruct order only if the response contract supports a safe deterministic rule; otherwise reject invalid ranking data. |
| Model returns more recommendations than requested | Enforce the application-side result limit. |
| Model returns no recommendations despite valid candidates | Handle as an LLM/output failure or apply the explicit fallback; do not mislabel it as a filter no-match. |
| Explanation claims unsupported attributes | Do not present unsupported claims as facts. Prefer grounded, evidence-limited prompt design and reject or revise explanations only through a defined validation policy. |
| Explanation contradicts candidate data (for example, wrong rating or cuisine) | Factual card fields must still come from the catalog; reject or regenerate a contradictory explanation if detectable. |
| Explanation is empty, excessively long, or contains formatting markup | Enforce schema and length limits; render safely. |
| Model echoes sensitive or irrelevant user input | Avoid sending unnecessary data and avoid displaying echoed content as restaurant facts. |
| Prompt instructions conflict with user or dataset text | Keep system-level constraints fixed; treat user preferences and candidate fields as data; validate all returned IDs. |
| Model provider returns a refusal or safety response | Surface a clear, non-misleading failure/limitation state; do not parse it as a recommendation list. |
| Retry would cause duplicate cost or long latency | Use bounded retry policy with timeout and observability. **Decision required:** retry count/backoff and retryable error classes. |
| Provider model behavior changes | Keep structured-output validation and regression tests; do not rely on prompt compliance alone. |
| LLM is unavailable but deterministic candidates exist | Follow the selected product fallback policy. If fallback is disabled, show an explicit error. **Decision required:** fallback behavior. |

## 6. Recommendation Assembly and Display

- **Model provides factual fields that conflict with the catalog:** Ignore
  model-provided facts; populate the card from the catalog.
- **Catalog fact is unavailable:** Display “Unavailable” or the chosen
  equivalent; do not invent a value.
- **Cost convention is unclear or stale:** Label it as dataset-derived or
  estimated and avoid presenting it as a current menu price.
- **Ratings are on a non-obvious scale:** Make the scale clear if needed;
  do not imply a five-star rating if the dataset uses another scale.
- **Result card name is empty or unusable:** Do not render a misleading blank
  card; apply the documented row eligibility rule or show an explicit
  unavailable label.
- **Several restaurants have identical names:** Display location or another
  available distinguishing attribute.
- **LLM ranking omits some candidates:** Show only ranked candidates unless
  deterministic fallback is explicitly selected; do not imply omitted
  candidates were evaluated successfully.
- **No results:** Provide a useful empty state and let the user adjust
  filters; do not phrase it as an LLM failure.
- **Service failure:** Provide a retry/actionable error state that is clearly
  different from no results.
- **Slow request:** Show a loading state; prevent stale results from replacing
  results for a newer preference submission.
- **User navigates away or cancels:** Cancel downstream work where supported;
  never update a different request's screen with a late response.
- **Unsafe text in dataset or explanation:** Escape text for the rendering
  context; never interpret model output as executable HTML/script.
- **Small screens, long cuisines, or long explanations:** Ensure cards remain
  readable and content does not obscure rating, cost, or controls.
- **Results do not match the user's requested location after a data refresh:**
  Ensure result assembly uses the same catalog snapshot used for filtering.

## 7. Runtime, Operations, and Security

- **Application starts without network access:** Clearly report whether a
  valid cached catalog is available; follow the stale-data policy.
- **Dataset and LLM are both unavailable:** Surface the relevant service
  error; do not show a fabricated or empty-success response.
- **Concurrent requests share a catalog refresh:** Keep refresh state
  isolated and ensure requests use a consistent snapshot.
- **High request volume or slow model responses:** Enforce concurrency,
  request, and provider limits appropriate to deployment; return explicit
  overload errors where needed.
- **Logs contain credentials or full free-form preferences:** Redact secrets
  and minimize user text in logs; log operational metadata instead.
- **Environment variable is malformed or missing:** Validate configuration
  at startup or before use and identify the variable without printing secret
  values.
- **Client attempts to access provider credentials:** Keep LLM calls and
  credentials server-side.
- **External provider returns an error containing sensitive details:** Map it
  to a safe user-facing message and retain only appropriately sanitized
  diagnostics.
- **Stale catalog is served:** Expose catalog load time/status where
  appropriate and apply the documented maximum staleness policy.
- **Monitoring records user text or dataset contents:** Prefer counts,
  latency, error categories, and catalog version; avoid unnecessary content
  capture.

## 8. Test Matrix

At minimum, automated tests should cover the following representative
scenarios:

| Area | Required cases |
|---|---|
| Ingestion | Valid dataset; empty dataset; missing optional field; schema drift; malformed rating/cost; duplicate branches; failed refresh preserving prior catalog |
| Validation | Whitespace-only input; unsupported budget; rating boundaries; invalid numeric values; oversized free text; duplicate cuisines |
| Filtering | Exact threshold; missing rating; missing cost; budget boundary; case/whitespace normalization; combined filters; no matches; stable ties; candidate limit |
| LLM boundary | Valid response; malformed/truncated response; unknown ID; ineligible ID; duplicate ID; over-limit output; timeout; provider failure; refusal |
| Assembly | Dataset remains source of factual fields; unavailable values stay unavailable; catalog snapshot consistency |
| Interface | Loading; successful results; no results; validation error; service error; late/stale response; safe rendering of untrusted text |
| Operations | Missing credentials; bounded retries; safe error messages; no secrets or unnecessary user text in logs |

## 9. Product Decisions to Resolve

The following edge-case behavior depends on decisions called out in the
architecture and implementation plan:

1. Which fields are required for a search, and what happens when all filters
   are omitted?
2. Are multiple cuisine selections ORed or ANDed?
3. Does a city-level location match include neighborhoods or localities?
4. What are the budget-band boundaries, and how is cost convention defined?
5. Are unknown-cost restaurants excluded or shown separately for budget
   searches?
6. What rating scale/range is supported, and how are unrated records handled?
7. Is partial valid LLM output acceptable when the response is truncated or
   contains invalid items?
8. Should deterministic results be shown when LLM ranking is unavailable?
9. How many retries are allowed, and which errors are retryable?
10. How old may a cached catalog be before it must be considered unavailable?
11. What is the maximum candidate count, result count, and preference-text
    length?
