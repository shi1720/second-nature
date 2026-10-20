# Cloud deployment

SECOND NATURE uses Firebase Hosting and Firebase Authentication for the public site, a Firebase-token-protected Cloud Run API, private Cloud Storage for metadata and artifacts, and a Cloud Run CPU rendering job. Metadata updates use GCS object-generation checks rather than Firestore. No Firestore access or shared Auth administration permissions are granted.

## Current deployment layout

| Component | Project / resource |
| --- | --- |
| Public website and Auth | `second-nature-studio` |
| Website | `https://second-nature-studio.web.app` |
| Cloud runtime | `gen-lang-client-0444960702`, an already billed project |
| API / rendering job | `second-nature-api` / `second-nature-render`, `us-central1` |
| Private artifacts and state | `gs://second-nature-studio-render-assets` |
| Private build source and logs | `gs://second-nature-studio-build-source` |
| Container repository | `us-central1-docker.pkg.dev/gen-lang-client-0444960702/second-nature` |

The split avoids a Google Cloud billing-account project-link quota. Runtime resources have their own service accounts and names. Existing applications, Auth settings, databases, and billing links in the runtime project are not replaced. The browser calls the actual Cloud Run URL using CORS limited to the new Hosting origins. Firebase JWT audience remains `second-nature-studio`, independent of the runtime project.

## Reproduce provisioning

Install Google Cloud CLI and sign in as an authorized project owner. Tokens are held in process memory, never logged or saved. No service-account keys are required.

Create the isolated Firebase project in an organization with remaining project quota if necessary, then initialize Firebase Authentication using **Get started** in its Firebase console. This free Firebase Auth step is different from paid Identity Platform initialization.

From the `second-nature` folder:

```sh
python3 cloud/infra/provision.py --project YOUR_FIREBASE_PROJECT --site YOUR_CLEAN_SITE_ID --hosting-only --configure-auth
python3 cloud/infra/provision.py --project YOUR_ALREADY_BILLED_RUNTIME_PROJECT --site YOUR_CLEAN_SITE_ID --auth-project YOUR_FIREBASE_PROJECT --runtime-only --bucket YOUR_PRIVATE_ARTIFACT_BUCKET --source-bucket YOUR_PRIVATE_BUILD_BUCKET
```

The first command enables email/password and anonymous sign-in and enforces a 12-character minimum password. It refuses Auth changes when it sees another registered app. Use a new isolated Auth project, never an unrelated application's Auth pool. The second command reads the first command's public SDK configuration and adds only namespaced runtime resources. `cloud/deployment.json` contains public deployment identifiers; Firebase web API keys identify the app and are not server credentials.

If a new fully isolated billed project is available, the script also supports `--create-project`, `--organization`, and an explicit `--billing-account`. It never infers or switches billing accounts. Do not run Auth configuration against an unrelated application.

## Build and publish

```sh
python3 cloud/infra/deploy.py build
python3 cloud/infra/deploy.py services
python3 cloud/infra/deploy.py hosting
```

Cloud Build creates the API and worker images from the shipped Dockerfiles. For a focused worker change, run `python3 cloud/infra/deploy.py build-worker` and then `python3 cloud/infra/deploy.py job`; the worker rebuild uses a source hash tag and cached Blender layers, and runs a real headless Blender and FFmpeg startup check before deployment. `build-api` followed by `api` performs the corresponding API-only update. Upload rules omit local Python environments, account state, rendered assets, and common credential files. The builder can access only its new source/log bucket and container repository. The API and worker can read and write only their new artifact bucket. The API additionally invokes/cancels its own rendering job and reads its own rate-limit salt from Secret Manager.

Before Hosting publication, stage the verified film and public images in `web/dist/assets/`. The release writes `config.js`, applies security headers, and uses Google's Hosting REST version/upload/finalize/release flow. Same-project deployments can use an `/api/**` rewrite; this split deployment uses the actual API URL. Publishing static assets alone does not prove that login or rendering works.

## Cost and retention

The rendering job uses 8 vCPU and 16 GiB, one task, zero automatic retries, and a two-hour timeout. Application admission limits allow one globally active render, three per day globally, two per account, and two per hashed IP. These reduce routine usage; they are not a billing cap. Operators can bypass application limits with direct cloud access, and other services still incur charges.

At the published us-central1 on-demand rates of $0.000018 per vCPU-second and $0.000002 per GiB-second, a full two-hour execution costs approximately **$1.27 in job compute**, or **$3.80 for three maximum-duration jobs**, before any free allowance. API compute, requests, storage, egress, image storage, taxes, and builds are additional. The free allowance is shared across a billing account and must not be assumed unused. Cloud Build's configured e2-highcpu-8 is listed at $0.0156 per minute. Rates checked 21 October 2026. [Cloud Run pricing](https://cloud.google.com/run/pricing) · [Cloud Build pricing](https://cloud.google.com/build/pricing)

Generated files under `users/` expire after seven days. `metadata/state.json` is retained so workspace records do not silently disappear. Source archives and build logs expire after seven days. Deletion timing is controlled by GCS lifecycle processing; it is not an exact seven-day timer.

## Verify and operate

Test guest sign-in, email/password account creation and login, project creation, actual worker execution, complete playback/download, sign-out isolation, and rejection of unauthenticated/cross-account API requests. Record nonsecret receipts and observed progress. Do not invent percentages, render completion, or measured savings.

Inspect or cancel only this application's Cloud Run executions. Review billing reports and consider a project budget notification where appropriate; budget alerts do not stop spending. Server credentials, browser session tokens, local account state, and private metadata must stay out of Git, source archives, and Hosting assets.

Sources: [Hosting REST deployments](https://firebase.google.com/docs/hosting/api-deploy), [Cloud Run job execution](https://docs.cloud.google.com/run/docs/execute/jobs), [Cloud Run roles](https://docs.cloud.google.com/iam/docs/roles-permissions/run), [Firebase password policy](https://docs.cloud.google.com/identity-platform/docs/password-policy).
