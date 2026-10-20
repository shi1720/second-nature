#!/usr/bin/env python3
"""Build images, deploy bounded Cloud Run resources, and publish Firebase Hosting."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

from google_rest import GoogleRest, query

ROOT = Path(__file__).resolve().parents[2]


def cloud(*args, capture=False):
    result = subprocess.run(["gcloud", *args, "--quiet"], check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def build(settings):
    project, region = settings["project"], settings["region"]
    cloud("builds", "submit", str(ROOT), "--project", project, "--region", region,
          "--config", str(ROOT / "cloud" / "infra" / "cloudbuild.yaml"),
          "--substitutions", f"_REGION={region}",
          "--service-account", f"projects/{project}/serviceAccounts/second-nature-builder@{project}.iam.gserviceaccount.com",
          "--gcs-source-staging-dir", f"gs://{settings['sourceBucket']}/source",
          "--gcs-log-dir", f"gs://{settings['sourceBucket']}/logs")
    settings.pop("apiImageTag", None)


def build_api(settings):
    project, region = settings["project"], settings["region"]
    digest = hashlib.sha256()
    for path in sorted((ROOT / "cloud").glob("*.py")) + [ROOT / "cloud" / "Dockerfile.api", ROOT / "cloud" / "requirements.txt"]:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    tag = "src-" + digest.hexdigest()[:16]
    cloud("builds", "submit", str(ROOT), "--project", project, "--region", region,
          "--config", str(ROOT / "cloud" / "infra" / "cloudbuild.api.yaml"),
          "--substitutions", f"_REGION={region},_API_TAG={tag}",
          "--service-account", f"projects/{project}/serviceAccounts/second-nature-builder@{project}.iam.gserviceaccount.com",
          "--gcs-source-staging-dir", f"gs://{settings['sourceBucket']}/source",
          "--gcs-log-dir", f"gs://{settings['sourceBucket']}/logs")
    settings["apiImageTag"] = tag


def deploy_job(settings):
    project, region, bucket = settings["project"], settings["region"], settings["bucket"]
    api, job = settings["apiService"], settings["renderJob"]
    image_prefix = f"{region}-docker.pkg.dev/{project}/second-nature"
    shared = f"GOOGLE_CLOUD_PROJECT={project},FIREBASE_PROJECT_ID={settings.get('firebaseProject', project)},AUTH_PROJECT_ID={settings.get('firebaseProject', project)},RENDER_BUCKET={bucket},RUN_REGION={region},RENDER_JOB={job}"
    cloud("run", "jobs", "deploy", job, "--project", project, "--region", region,
          "--image", image_prefix + "/worker:latest", "--service-account", f"second-nature-worker@{project}.iam.gserviceaccount.com",
          "--cpu=8", "--memory=16Gi", "--task-timeout=7200s", "--max-retries=0", "--tasks=1", "--parallelism=1",
          "--command=python", "--args=-m,cloud.worker", "--set-env-vars", shared)
    for role in ("roles/run.jobsExecutorWithOverrides", "roles/run.viewer"):
        cloud("run", "jobs", "add-iam-policy-binding", job, "--project", project, "--region", region,
              "--member", f"serviceAccount:second-nature-api@{project}.iam.gserviceaccount.com", "--role", role, capture=True)


def deploy_api(settings):
    project, region, bucket = settings["project"], settings["region"], settings["bucket"]
    api, job = settings["apiService"], settings["renderJob"]
    image_prefix = f"{region}-docker.pkg.dev/{project}/second-nature"
    shared = f"GOOGLE_CLOUD_PROJECT={project},FIREBASE_PROJECT_ID={settings.get('firebaseProject', project)},AUTH_PROJECT_ID={settings.get('firebaseProject', project)},RENDER_BUCKET={bucket},RUN_REGION={region},RENDER_JOB={job}"
    origins = f"https://{settings['site']}.web.app;https://{settings['site']}.firebaseapp.com"
    # gcloud delimiter syntax allows a comma-containing CORS value without shell interpolation.
    api_environment = "^;^" + shared.replace(",", ";") + ";ALLOWED_ORIGINS=" + origins.replace(";", ",")
    api_environment += ";MAX_DAILY_RENDERS=3;MAX_USER_DAILY_RENDERS=2;MAX_IP_DAILY_RENDERS=2;JOB_TIMEOUT_SECONDS=7200"
    cloud("run", "deploy", api, "--project", project, "--region", region,
          "--image", image_prefix + "/api:" + settings.get("apiImageTag", "latest"), "--service-account", f"second-nature-api@{project}.iam.gserviceaccount.com",
          "--cpu=1", "--memory=512Mi", "--timeout=300s", "--min-instances=0", "--max-instances=2", "--concurrency=20",
          "--allow-unauthenticated", "--port=8080", "--set-env-vars", api_environment,
          "--set-secrets=RATE_LIMIT_SALT=second-nature-rate-limit-salt:latest", "--labels=app=second-nature")
    settings["apiUrl"] = cloud("run", "services", "describe", api, "--project", project, "--region", region,
                               "--format=value(status.url)", capture=True)
    print("Cloud Run API deployed; no render execution started.")


def services(settings):
    deploy_job(settings)
    deploy_api(settings)

def hosting(settings, public_dir):
    project, site, region = settings["project"], settings["site"], settings["region"]
    firebase_project = settings.get("firebaseProject", project)
    api = GoogleRest(firebase_project)
    public_dir = Path(public_dir).resolve()
    if not (public_dir / "index.html").is_file():
        raise SystemExit("Hosting requires an actual index.html in the public directory.")
    config = {"firebaseConfig": settings["firebaseConfig"], "apiBaseUrl": settings.get("apiUrl", "") if firebase_project != project else "/api",
              "projectId": firebase_project, "siteUrl": f"https://{site}.web.app"}
    (public_dir / "config.js").write_text(
        "// Firebase web identifiers are public configuration, not server credentials.\n"
        + "window.SECOND_NATURE_CONFIG = " + json.dumps(config, indent=2) + ";\n"
    )
    files = {}
    bodies = {}
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(public_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(public_dir):
            raise ValueError("Hosting assets must be regular files inside the public directory")
        if path.suffix.lower() in (".pem", ".p12", ".key", ".sqlite3", ".env"):
            raise ValueError("Credential or state file rejected from Hosting assets")
        body = gzip.compress(path.read_bytes(), mtime=0)
        digest = hashlib.sha256(body).hexdigest()
        files["/" + relative.as_posix()] = digest
        bodies[digest] = body
    hosting_config = {
        "rewrites": [
            *([{ "glob": "/api/**", "run": {"serviceId": settings["apiService"], "region": region}}] if firebase_project == project else []),
            {"glob": "**", "path": "/index.html"},
        ],
        "headers": [
            {"glob": "**", "headers": {
                "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' https://www.gstatic.com; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com " + settings.get("apiUrl", "") + "; frame-src https://" + settings["firebaseConfig"]["authDomain"] + "; base-uri 'self'; form-action 'self'; object-src 'none'; frame-ancestors 'none'",
            }},
            {"glob": "/config.js", "headers": {"Cache-Control": "no-store"}},
            {"glob": "/index.html", "headers": {"Cache-Control": "no-cache"}},
            {"glob": "/assets/**", "headers": {"Cache-Control": "public, max-age=3600"}},
        ],
    }
    base = "https://firebasehosting.googleapis.com/v1beta1"
    version = api.request("POST", f"{base}/sites/{site}/versions", {"config": hosting_config})
    for start in range(0, len(files), 1000):
        chunk = dict(list(files.items())[start:start + 1000])
        upload = api.request("POST", f"{base}/{version['name']}:populateFiles", {"files": chunk})
        for digest in upload.get("uploadRequiredHashes", []):
            api.request("POST", upload["uploadUrl"].rstrip("/") + "/" + digest,
                        raw=bodies[digest], content_type="application/octet-stream")
    api.request("PATCH", f"{base}/{version['name']}?" + query(update_mask="status"), {"status": "FINALIZED"})
    release = api.request("POST", f"{base}/sites/{site}/releases?" + query(versionName=version["name"]), {})
    settings["hostingVersion"] = version["name"]
    settings["hostingRelease"] = release.get("name")
    settings["hostingUrl"] = f"https://{site}.web.app"
    print(f"Published {len(files)} assets to {settings['hostingUrl']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build", "build-api", "job", "api", "services", "hosting", "all"))
    parser.add_argument("--settings", default=str(ROOT / "cloud" / "deployment.json"))
    parser.add_argument("--public-dir", default=str(ROOT / "web" / "dist"))
    args = parser.parse_args()
    settings_path = Path(args.settings)
    settings = json.loads(settings_path.read_text())
    if args.stage in ("build", "all"):
        build(settings)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    if args.stage == "build-api":
        build_api(settings)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    if args.stage == "job":
        deploy_job(settings)
    if args.stage == "api":
        deploy_api(settings)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    if args.stage in ("services", "all"):
        services(settings)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    if args.stage in ("hosting", "all"):
        hosting(settings, args.public_dir)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
