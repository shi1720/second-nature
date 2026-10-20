#!/usr/bin/env python3
"""Provision only the explicitly selected Second Nature Google Cloud project."""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
from pathlib import Path

from google_rest import ApiError, GoogleRest, query

ROOT = Path(__file__).resolve().parents[2]
REST = GoogleRest()
SERVICES = (
    "firebase.googleapis.com", "firebasehosting.googleapis.com",
    "identitytoolkit.googleapis.com", "run.googleapis.com",
    "artifactregistry.googleapis.com", "cloudbuild.googleapis.com",
    "storage.googleapis.com", "iam.googleapis.com",
    "iamcredentials.googleapis.com", "secretmanager.googleapis.com",
    "logging.googleapis.com",
)


def cloud(*args, capture=False, stdin=None):
    result = subprocess.run(
        ["gcloud", *args, "--quiet"], check=True, text=True,
        input=stdin, capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def exists(*args):
    return subprocess.run(
        ["gcloud", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def grant(project, member, role):
    cloud("projects", "add-iam-policy-binding", project,
          "--member", member, "--role", role, "--condition=None", capture=True)


def save_public_settings(args, source_bucket):
    project, site, region = args.project, args.site or args.project, args.region
    bucket = args.bucket or f"{project}-render-assets"
    if args.runtime_only:
        previous = json.loads(Path(args.settings).read_text())
        public_sdk = previous["firebaseConfig"]
    else:
        apps = REST.request("GET", f"https://firebase.googleapis.com/v1beta1/projects/{project}/webApps").get("apps", [])
        app = next((a for a in apps if a.get("displayName") == "Second Nature Studio"), None)
        if not app:
            operation = REST.request("POST", f"https://firebase.googleapis.com/v1beta1/projects/{project}/webApps", {"displayName": "Second Nature Studio"})
            app = REST.wait(operation, "https://firebase.googleapis.com/v1beta1")
        sdk = REST.request("GET", f"https://firebase.googleapis.com/v1beta1/projects/{project}/webApps/{app['appId']}/config")
        public_sdk = {key: sdk[key] for key in ("apiKey", "authDomain", "projectId", "storageBucket", "messagingSenderId", "appId") if key in sdk}
    settings = {"project": project, "site": site, "region": region, "bucket": bucket,
                "firebaseProject": args.auth_project or public_sdk["projectId"], "apiService": "second-nature-api", "renderJob": "second-nature-render", "sourceBucket": source_bucket, "firebaseConfig": public_sdk, "backendProvisioned": not args.hosting_only}
    target = Path(args.settings).resolve()
    if args.hosting_only and target.exists():
        previous = json.loads(target.read_text())
        if previous.get("firebaseProject") == project and previous.get("project") != project:
            settings = {**previous, "firebaseConfig": public_sdk}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Provisioned {project}. Public deployment settings: {target}")


def configure(args):
    project, region, site = args.project, args.region, args.site or args.project
    REST.quota_project = project
    if not exists("projects", "describe", project):
        if not args.create_project:
            raise SystemExit("Project does not exist. Use --create-project to create the selected project.")
        parent = ["--organization", args.organization] if args.organization else []
        cloud("projects", "create", project, "--name=Second Nature Studio", *parent)
    if args.billing_account:
        cloud("billing", "projects", "link", project, "--billing-account", args.billing_account)
    services = SERVICES if not args.hosting_only else ("firebase.googleapis.com", "firebasehosting.googleapis.com", "identitytoolkit.googleapis.com")
    if args.runtime_only:
        services = tuple(service for service in SERVICES if service not in ("firebase.googleapis.com", "firebasehosting.googleapis.com", "identitytoolkit.googleapis.com"))
    cloud("services", "enable", *services, "--project", project)
    if not args.runtime_only:
        try:
            REST.request("GET", f"https://firebase.googleapis.com/v1beta1/projects/{project}")
        except ApiError as error:
            if error.status != 404:
                raise
            operation = REST.request("POST", f"https://firebase.googleapis.com/v1beta1/projects/{project}:addFirebase", {})
            REST.wait(operation, "https://firebase.googleapis.com/v1beta1")
        print("Firebase resources enabled.")

        if args.configure_auth:
            existing_apps = REST.request("GET", f"https://firebase.googleapis.com/v1beta1/projects/{project}/webApps").get("apps", [])
            if any(app.get("displayName") != "Second Nature Studio" for app in existing_apps):
                raise SystemExit("Auth configuration refused: the project contains another application.")
            config = {"signIn": {"email": {"enabled": True, "passwordRequired": True}, "anonymous": {"enabled": True}},
                      "authorizedDomains": [f"{site}.web.app", f"{site}.firebaseapp.com", f"{project}.firebaseapp.com", "localhost"]}
            try:
                REST.request("PATCH", f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config?" + query(updateMask="signIn.email,signIn.anonymous,authorizedDomains"), config)
            except ApiError as error:
                if error.status != 404:
                    raise
                raise SystemExit("Initialize Firebase Authentication using Get started in the Firebase console, then rerun. Identity Platform initialization is a different paid operation.") from None
            policy = {"passwordPolicyConfig": {"passwordPolicyEnforcementState": "ENFORCE", "passwordPolicyVersions": [{"customStrengthOptions": {"minPasswordLength": 12, "maxPasswordLength": 4096}}]}}
            REST.request("PATCH", f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config?" + query(updateMask="passwordPolicyConfig"), policy)

        try:
            REST.request("GET", f"https://firebasehosting.googleapis.com/v1beta1/projects/{project}/sites/{site}")
        except ApiError as error:
            if error.status != 404:
                raise
            REST.request("POST", f"https://firebasehosting.googleapis.com/v1beta1/projects/{project}/sites?" + query(siteId=site), {"type": "USER_SITE"})
    # Firestore is not used. An explicitly configured, isolated project's Auth
    # is handled above. Shared-project Auth stays unchanged by default.

    if args.hosting_only:
        save_public_settings(args, args.source_bucket or f"{site}-build-source")
        return

    bucket = args.bucket or f"{project}-render-assets"
    if not exists("storage", "buckets", "describe", f"gs://{bucket}"):
        cloud("storage", "buckets", "create", f"gs://{bucket}", "--project", project,
              "--location", region, "--uniform-bucket-level-access", "--public-access-prevention")
    # Generated artifacts expire after seven days. Original scene source is shipped separately.
    REST.request("PATCH", f"https://storage.googleapis.com/storage/v1/b/{bucket}",
                 {"lifecycle": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["users/"]}}]}})
    if not exists("artifacts", "repositories", "describe", "second-nature", "--location", region, "--project", project):
        cloud("artifacts", "repositories", "create", "second-nature", "--repository-format=docker",
              "--location", region, "--project", project, "--description=Second Nature API and render worker")

    api = f"second-nature-api@{project}.iam.gserviceaccount.com"
    worker = f"second-nature-worker@{project}.iam.gserviceaccount.com"
    builder = f"second-nature-builder@{project}.iam.gserviceaccount.com"
    for name, label in (("second-nature-api", "Second Nature API"), ("second-nature-worker", "Second Nature Render Worker"), ("second-nature-builder", "Second Nature Image Builder")):
        email = f"{name}@{project}.iam.gserviceaccount.com"
        if not exists("iam", "service-accounts", "describe", email, "--project", project):
            cloud("iam", "service-accounts", "create", name, "--display-name", label, "--project", project)
    for email, role in ((worker, "roles/storage.objectAdmin"), (api, "roles/storage.objectAdmin")):
        cloud("storage", "buckets", "add-iam-policy-binding", f"gs://{bucket}",
              "--member=serviceAccount:" + email, "--role", role, capture=True)
    source_bucket = args.source_bucket or f"{site}-build-source"
    if not exists("storage", "buckets", "describe", f"gs://{source_bucket}"):
        cloud("storage", "buckets", "create", f"gs://{source_bucket}", "--project", project,
              "--location", region, "--uniform-bucket-level-access", "--public-access-prevention")
    REST.request("PATCH", f"https://storage.googleapis.com/storage/v1/b/{source_bucket}",
                 {"lifecycle": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]}})
    cloud("storage", "buckets", "add-iam-policy-binding", f"gs://{source_bucket}",
          "--member=serviceAccount:" + builder, "--role=roles/storage.objectAdmin", capture=True)
    cloud("storage", "buckets", "add-iam-policy-binding", f"gs://{source_bucket}",
          "--member=serviceAccount:" + builder, "--role=roles/storage.legacyBucketReader", capture=True)
    cloud("artifacts", "repositories", "add-iam-policy-binding", "second-nature", "--location", region,
          "--project", project, "--member=serviceAccount:" + builder, "--role=roles/artifactregistry.writer", capture=True)

    if not exists("secrets", "describe", "second-nature-rate-limit-salt", "--project", project):
        cloud("secrets", "create", "second-nature-rate-limit-salt", "--replication-policy=automatic", "--project", project)
        cloud("secrets", "versions", "add", "second-nature-rate-limit-salt", "--data-file=-", "--project", project, stdin=secrets.token_hex(32))
    cloud("secrets", "add-iam-policy-binding", "second-nature-rate-limit-salt", "--project", project,
          "--member=serviceAccount:" + api, "--role=roles/secretmanager.secretAccessor", capture=True)

    save_public_settings(args, source_bucket)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--site")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--bucket")
    parser.add_argument("--source-bucket")
    parser.add_argument("--billing-account", help="Explicit existing billing account, never inferred")
    parser.add_argument("--create-project", action="store_true")
    parser.add_argument("--organization")
    parser.add_argument("--runtime-only", action="store_true", help="Provision only namespaced runtime resources in an already billed project")
    parser.add_argument("--auth-project", help="Separate Firebase Auth project for a split deployment")
    parser.add_argument("--hosting-only", action="store_true", help="Provision free Hosting and Auth without worker resources")
    parser.add_argument("--configure-auth", action="store_true", help="Configure Auth only in an isolated project")
    parser.add_argument("--settings", default=str(ROOT / "cloud" / "deployment.json"))
    configure(parser.parse_args())
