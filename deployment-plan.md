# Railway API and Vercel frontend deployment plan

This plan deploys the FastAPI service on Railway and publishes the existing
static UI on Vercel. The UI can continue to run locally through FastAPI; when
served separately, it uses a configured API origin to reach Railway.

## 1. Deployment layout

- **Railway:** runs `app.main:app`, loads the restaurant catalog, and exposes
  `/health`, `/ready`, `/api/options`, and `/api/recommend`.
- **Vercel:** publishes `templates/index.html` and the files in `static/` as a
  static site. It does not host or proxy the FastAPI application.
- **Local:** `uvicorn app.main:app --reload` continues to serve both the UI and
  API from one origin. An empty API base URL makes the UI use relative URLs.

The current UI calls `/api/...` relative to its own origin. Before deploying
the UI separately, make the API base configurable and enable CORS on the API
(see sections 3 and 4).

## 2. Railway backend

### Procfile

Add a root-level file named `Procfile` with this process declaration:

```procfile
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Railway provides `PORT` at runtime. Do not rely on the current local default
`SERVER_PORT=8000` for the deployed listener; the Procfile must bind to
Railway's assigned port. The existing `uvicorn[standard]` dependency provides
the server executable.

### Create the Railway service

1. Create a Railway project and deploy this repository as a service.
2. Set the service root directory to the repository root.
3. Use the Procfile start command above. If Railway asks for a build command,
   use `pip install .` (or its equivalent install step).
4. Configure the health check path as `/ready`, with a timeout/grace period
   long enough for the initial dataset download and parse.
5. Deploy and wait for `/ready` to return `200` with `"status":"ready"` before
   testing recommendation requests. `/health` only confirms that the process is
   responding; it does not confirm that the catalog loaded.

### Memory-safe dataset loading

The current `RestaurantCatalog.from_csv_url` reads the response fully into
bytes, decodes a second full copy into text, then parses it via `StringIO`
while building the in-memory restaurant list. Peak memory can therefore be
several times the CSV size, in addition to the final catalog.

Before deploying on a memory-limited Railway plan:

1. Change URL ingestion to copy the response to a temporary file in bounded
   chunks instead of calling `response.read()` with no size.
2. Parse that file incrementally with `csv.DictReader` and construct one
   normalized `RestaurantCandidate` per row. Preserve UTF-8 BOM handling and
   the existing Latin-1 fallback.
3. Do not retain both a complete decoded CSV string and the candidate list.
   Keep only fields needed by filtering, ranking, and API responses; remove or
   avoid storing `source_fields` if it is not required by application
   behavior.
4. Close and remove the temporary file on both success and failure. Set a
   reasonable download-size limit and surface a clear ingestion error if it is
   exceeded.
5. Measure peak memory against the actual dataset and Railway service limit.
   Streaming removes the large duplicate input buffers, but the current
   catalog and ID index still keep all normalized restaurants in memory. If
   that alone is too large, use a disk-backed store such as SQLite or a smaller
   pre-filtered dataset; chunked download by itself cannot make the final
   in-memory catalog bounded.

Keep the existing explicit failure behavior: a failed or empty catalog should
leave `/ready` not ready and recommendation endpoints should report a service
error, not silently return an empty successful result.

## 3. CORS configuration

Add a configurable `FRONTEND_ORIGINS` setting to the backend. Parse it as a
comma-separated list of exact origins, trimming whitespace and trailing
slashes. Register FastAPI's `CORSMiddleware` with that allowlist, allow the
methods and headers required by the UI (`GET`, `POST`, `OPTIONS`, and
`Content-Type`), and leave `allow_credentials=False` unless cookie-based
authentication is deliberately added later.

Example backend setting:

```text
FRONTEND_ORIGINS=https://your-vercel-project.vercel.app,https://your-custom-domain.example
```

For a separately served local frontend, include only its exact development
origin, for example `http://localhost:3000`. If local UI testing uses the
FastAPI-served page at `http://localhost:8000`, it is same-origin and does not
need a CORS entry. Do not use `*` in production; update the allowlist when the
Vercel deployment URL or custom domain changes.

## 4. Configurable frontend API base URL

Update the UI so both API requests in `static/app.js` (`/api/options` and
`/api/recommend`) prepend a configurable base URL:

```js
const API_BASE_URL = (window.API_BASE_URL || "").replace(/\/+$/, "");
```

Use `${API_BASE_URL}/api/options` and `${API_BASE_URL}/api/recommend` in the
existing fetch calls. Add `static/config.js` to define
`window.API_BASE_URL = window.API_BASE_URL || ""`, and load
`/static/config.js` before `app.js`. When the value is empty, the current
same-origin local setup continues to work.

Vercel does not automatically expose project environment variables to browser
JavaScript. Generate `config.js` as part of the Vercel build from the
non-secret `API_BASE_URL` environment variable rather than trying to read
`process.env` in `app.js`. For example, add a small Node build script that:

1. Copies `templates/index.html` to `dist/index.html`.
2. Copies `static/` to `dist/static/` (the existing HTML references those
   paths).
3. Writes `dist/static/config.js` with `window.API_BASE_URL` set to the build's
   `API_BASE_URL`, replacing the local empty default.

Include `<script src="/static/config.js"></script>` before the deferred
`/static/app.js` script in the HTML. The generated config must contain only the
public API origin, never a Gemini key or other secret.

For local use:

- When the UI is served by FastAPI, leave the base URL empty; relative API
  paths go to `localhost:8000`.
- When serving the UI separately, set it to `http://localhost:8000` and allow
  that frontend's origin in `FRONTEND_ORIGINS`.

For Vercel, set `API_BASE_URL` to the Railway public origin, for example
`https://<railway-service-domain>` (no path suffix required). The Vercel
frontend then makes browser requests directly to that Railway origin.

## 5. Environment variables

### Railway

In the Railway service's **Variables** settings, configure:

| Variable | Value |
| --- | --- |
| `DATASET_URL` | Reachable CSV URL used by the application |
| `GEMINI_API_KEY` | Secret provider key; enter through Railway's secret variable UI |
| `GEMINI_MODEL` | Optional model identifier; defaults to the application's configured model |
| `REQUEST_TIMEOUT_SECONDS` | Optional provider request timeout |
| `DEFAULT_CANDIDATE_LIMIT` | Optional maximum candidate count passed to ranking |
| `DEFAULT_RESULT_LIMIT` | Optional number of returned recommendations |
| `ENVIRONMENT` | `production` |
| `FRONTEND_ORIGINS` | Comma-separated Vercel production and any required preview/custom origins |

Railway supplies `PORT`; do not add a fixed `PORT` value. Keep `.env` local and
out of Git. The repository's `.env.example` is a reference for the application
settings; it is not a source of production secrets.

### Vercel

1. Import the repository into Vercel.
2. Configure the project to publish the generated static output: use the
   repository root, an "Other" framework preset, build command
   `node scripts/build-vercel.mjs` (after adding the small build script from
   section 4), and output directory `dist`.
3. Add `API_BASE_URL` as a Vercel environment variable containing the Railway
   public origin.
4. Apply it to Production and the Preview/Development environments where the
   frontend will be tested. Redeploy after changing it because the value is
   embedded in the generated static `config.js`.
5. Add the final Vercel production origin (and any deliberately supported
   preview origins) to Railway's `FRONTEND_ORIGINS`, then redeploy/restart the
   Railway service to apply the updated allowlist.

Never put `GEMINI_API_KEY` or other backend-only secrets in Vercel variables
that are exposed to client-side code.

## 6. Deploy and smoke-test

After both services deploy:

1. Open Railway's `/health` and `/ready`; confirm `/ready` reports the catalog
   loaded.
2. Open the Vercel site and confirm the location/cuisine options load. Check
   the browser console/network panel for CORS failures and confirm requests
   target the Railway origin.
3. Submit a recommendation request and verify a valid response or the
   application's explicit no-results/service-error response.
4. Repeat locally with `uvicorn app.main:app --reload`; confirm the empty API
   base URL still routes requests to the local FastAPI origin.
5. Review Railway logs and memory usage during startup/catalog loading. Confirm
   no API keys or full dataset contents are logged.
