# Second Nature cloud production

A real Blender render backend for the hosted Second Nature studio. Firebase Authentication establishes the caller's identity; an authenticated Cloud Run API validates project ownership and reserves a production slot; a Cloud Run Job runs the shipped Blender Python pipeline; a private Cloud Storage bucket holds records, progress, completed frames, and downloads.

The worker never returns an invented animation or substitutes the featured film for a user's production. A complete job runs scene generation (or validates an exact cached build), renders all 576 frames, assembles the original soundtrack and titles with FFmpeg, verifies the sequence and encoded delivery, then publishes the actual artifacts.

## Architecture and isolation

- **Authentication:** Firebase ID tokens are verified with the Admin SDK against `AUTH_PROJECT_ID`. Signature, issuer, audience, and expiry are checked. Tokens are sent in the Authorization header. No server cookies are used.
- **Metadata:** `metadata/state.json` in the app's private bucket contains project/job records, quota counters, and the global worker lease. Generation-match preconditions implement compare-and-swap transactions. Concurrent writes retry from a fresh snapshot. There is no Firestore dependency or permission grant.
- **Artifacts:** `users/<hashed-uid>/projects/<project-id>/` contains Blender projects, manifests, audio, encoded movies, and fingerprinted frame caches. The public API never accepts an arbitrary bucket object name or output directory.
- **Execution:** the API overrides only `JOB_ID` when executing the app's dedicated Cloud Run Job. The nonroot worker image contains the existing pipeline, scene/render/finish scripts, required fonts, official Blender 4.5.9 Linux (verified against its official SHA256 list), FFmpeg, NumPy, and Pillow.
- **Downloads:** every artifact request checks Firebase authentication and project ownership. Video responses support byte ranges. The frontend fetches with its Bearer token and uses a local blob URL for playback. Buckets and artifact URLs are not public; no service-account signing key is exposed.

The Firebase/Auth project and the paid Cloud Run/storage runtime project can differ. `AUTH_PROJECT_ID` selects token audience; `GOOGLE_CLOUD_PROJECT` selects runtime services. Service accounts receive access only to this app's new bucket and Cloud Run resources. The API uses public signing certificates and does not need permission to read another project's Firebase users.

Token revocation is not queried through privileged Firebase Admin user APIs in the split-project deployment. A previously issued token can remain valid until its normal expiry (typically one hour). Client sign-out clears local credentials. Deployments needing immediate server-side revocation must explicitly add an app-specific revocation mechanism or grant appropriate access to their own isolated Auth project.

## API contract

Use `/api/healthz` for the deployed Cloud Run health check. `/healthz` is also an application alias, but Google Front End can intercept that root path.

All `/v1` routes require `Authorization: Bearer <Firebase ID token>`. Hosting rewrites may also reach identical routes under `/api/v1`. Direct Cloud Run URLs work with the configured Hosting CORS origins. Errors return `{"error":"human-readable explanation"}` with an appropriate HTTP status. Timestamps use UTC ISO 8601 strings.

| Method and path | Behavior |
| --- | --- |
| `GET /api/healthz` or `HEAD /api/healthz` | Public deployed process health |
| `GET /v1/me` | Identity type and current render budget |
| `GET /v1/projects` | `{projects: [...]}` for the caller only |
| `POST /v1/projects` | Create immutable configuration; returns the project |
| `GET /v1/projects/{id}` | `{project, jobs}` with recent actual job state |
| `POST /v1/projects/{id}/jobs` | `{action, profile}`; action defaults to `all`; returns a queued job |
| `GET /v1/jobs/{id}` | Current job, progress, actual log, and failure if present |
| `POST /v1/jobs/{id}/cancel` | Request cancellation; a running worker checkpoints completed frames |
| `POST /v1/jobs/{id}/resume` | Start a new execution from a failed/cancelled/interrupted job's saved artifacts |
| `GET /v1/projects/{id}/artifacts/{kind}` | Authenticated content URL, content type, filename, and size |
| `GET /v1/projects/{id}/artifacts/{kind}/content` | Stream actual artifact bytes; movie seeking supports `Range` |

Artifact kinds are `movie`, `blend`, `config`, and `poster`. URLs returned by the metadata endpoint are relative to the API origin, not the Hosting origin. Fetch content with the same Bearer token. `config` is a portable JSON configuration with a relative output directory.

Project input:

```json
{
  "name": "Second Nature - Blue cut",
  "seed": 42,
  "hero_color": "#5AB8FF",
  "accent_color": "#203C5A",
  "profile": "preview"
}
```

Jobs accept `build`, `render`, `assemble`, or `all`. Cloud rendering uses Preview only: **960x540, 16 Cycles samples, 576 frames, 24 fps, 24 seconds**. Download the source and Blender file for the local Final workflow. Render duration depends on CPU workload; the UI shows measured frame completions rather than a fabricated estimate.

## Quotas, cancellation, and resuming

Default limits are one active job globally; three render/all starts per UTC day globally; two per account; two per hashed client network; ten total jobs per account per day; and thirty total jobs globally per day. Resume starts consume another slot because they launch a real paid execution. Failed or cancelled starts also count. Accounts may own twenty projects; project creation has additional global/network limits. These conservative limits are configurable by the operator.

The Cloud Run worker uses eight CPUs, 16 GiB memory, one task, no automatic retries, and a 7,200-second timeout. A lease includes ten minutes of startup margin. GCS generation transactions reserve quota and the active lease together. The API never starts a second job while that reservation is valid.

The worker checkpoints real, atomically completed PNGs every five frames and at stage boundaries, failure, or cancellation. Frame-cache namespaces use the pipeline's source/build/profile fingerprint, so a new build cannot reuse an unrelated render. Resume restores matching files and lets the existing pipeline validate and skip intact frames. It does not claim missing frames are finished. The exact last few frames may need rendering again after abrupt termination.

Cancellation marks state first and cancels the actual Cloud Run execution. Workers poll state and handle termination signals. If a worker cannot persist final status, API reads reconcile it against the real execution and release the reservation only after that execution has stopped; expired leases become interrupted. An execution succeeding at the platform level is never sufficient by itself to declare the film complete.

The deployment expires the artifact `users/` prefix after seven days to control storage costs. Metadata is retained. Expired files return an honest unavailable response; a subsequent permitted production can rebuild them. Recent job history is bounded to 200 terminal records, while active work is retained.

## Runtime configuration

| Variable | Purpose |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Runtime Cloud Run/GCS project |
| `AUTH_PROJECT_ID` | Firebase token audience (supports a separate Auth project) |
| `FIREBASE_PROJECT_ID` | Compatibility fallback for Auth audience |
| `RENDER_BUCKET` | Dedicated private artifact and metadata bucket |
| `RUN_REGION` | Dedicated job region, normally `us-central1` |
| `RENDER_JOB` | Dedicated Cloud Run Job short name or full resource name |
| `RATE_LIMIT_SALT` | Secret used to HMAC client network identifiers; required by API |
| `ALLOWED_ORIGINS` | Comma-separated exact Hosting origins |
| `JOB_TIMEOUT_SECONDS` | Maximum execution timeout, default `7200` |
| `MAX_DAILY_RENDERS` | Global render/all starts per UTC day, default `3` |
| `MAX_USER_DAILY_RENDERS` | Per-account render starts, default `2` |
| `MAX_IP_DAILY_RENDERS` | Per-network render starts, default `2` |

Keep `RATE_LIMIT_SALT` in Secret Manager. No Firebase service-account JSON or cloud private key belongs in source or browser configuration. Firebase web configuration is public client metadata, not a privileged server credential.

Build contexts are the parent `second-nature` directory:

```sh
docker build -f cloud/Dockerfile.api -t second-nature-api .
docker build -f cloud/Dockerfile.worker -t second-nature-worker .
```

API command: `uvicorn cloud.api:app --host 0.0.0.0 --port 8080`.
Worker command: `python -m cloud.worker`, with `JOB_ID` supplied only by the API's execution override.

Deployment automation and IAM/resource details are under `cloud/infra/`. Use the dedicated resources, not an unrelated application's buckets or databases.

## Tests

```sh
python3 -m venv cloud/.venv
cloud/.venv/bin/pip install -r cloud/requirements.txt httpx
cloud/.venv/bin/python -m unittest discover -s cloud/tests -v
```

Tests use injected in-memory CAS storage, fake Cloud Run clients, and isolated subprocess fixtures. They cover authentication/ownership, URL aliases, input/path validation, quota races, failed-CAS retries without double spending, identity-reset network limits, cancellation/resume, platform-stop reconciliation, byte ranges, portable configuration, actual Cloud Run SDK request shapes, fingerprinted checkpoint restoration, genuine subprocess progress, and failed exit codes. These tests do not render with the local GPU and do not substitute for the separately recorded live cloud production check.
