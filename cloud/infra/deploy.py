#!/usr/bin/env python3
"""Build images, deploy bounded Cloud Run resources, and publish Firebase Hosting."""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import subprocess
import uuid
from urllib.parse import urlsplit
from pathlib import Path

try:
    from .google_rest import GoogleRest, query
except ImportError:
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
    settings.pop("workerImageTag", None)


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


def build_worker(settings):
    project, region = settings["project"], settings["region"]
    paths = [ROOT / "pipeline.py", ROOT / "cloud" / "Dockerfile.worker", ROOT / "cloud" / "requirements.txt"]
    paths += list((ROOT / "source").glob("*.py"))
    paths += list((ROOT / "cloud").glob("*.py"))
    paths += [path for path in (ROOT / "assets" / "fonts").rglob("*") if path.is_file()]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    tag = "src-" + digest.hexdigest()[:16]
    cloud("builds", "submit", str(ROOT), "--project", project, "--region", region,
          "--config", str(ROOT / "cloud" / "infra" / "cloudbuild.worker.yaml"),
          "--substitutions", f"_REGION={region},_WORKER_TAG={tag}",
          "--service-account", f"projects/{project}/serviceAccounts/second-nature-builder@{project}.iam.gserviceaccount.com",
          "--gcs-source-staging-dir", f"gs://{settings['sourceBucket']}/source",
          "--gcs-log-dir", f"gs://{settings['sourceBucket']}/logs")
    settings["workerImageTag"] = tag


def deploy_job(settings):
    project, region, bucket = settings["project"], settings["region"], settings["bucket"]
    api, job = settings["apiService"], settings["renderJob"]
    image_prefix = f"{region}-docker.pkg.dev/{project}/second-nature"
    shared = f"GOOGLE_CLOUD_PROJECT={project},FIREBASE_PROJECT_ID={settings.get('firebaseProject', project)},AUTH_PROJECT_ID={settings.get('firebaseProject', project)},RENDER_BUCKET={bucket},RUN_REGION={region},RENDER_JOB={job}"
    cloud("run", "jobs", "deploy", job, "--project", project, "--region", region,
          "--image", image_prefix + "/worker:" + settings.get("workerImageTag", "latest"), "--service-account", f"second-nature-worker@{project}.iam.gserviceaccount.com",
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

SHOWCASE_SOURCES = {
    'original.mp4': '/assets/second-nature.mp4',
    'blue-hour.mp4': '/assets/blue-hour-preview.mp4',
    'studio-demo.mp4': '/assets/studio-demo.mp4',
}

def upload_showcase(settings, paths):
    """Operator-only upload of exactly three curated movies, never user objects."""
    if set(paths)!=set(SHOWCASE_SOURCES):
        raise ValueError('Provide exactly original.mp4, blue-hour.mp4 and studio-demo.mp4.')
    prepared={}
    for name,value in paths.items():
        path=Path(value)
        if path.is_symlink() or not path.is_file() or path.suffix.lower()!='.mp4':
            raise ValueError('Showcase inputs must be regular MP4 files.')
        body=path.read_bytes()
        if len(body)<12 or body[4:8]!=b'ftyp':raise ValueError('Showcase input is not an MP4 container.')
        prepared[name]=(body,hashlib.sha256(body).hexdigest(),base64.b64encode(hashlib.md5(body,usedforsecurity=False).digest()).decode())
    api=GoogleRest(settings['project']);receipt={}
    for name,(body,sha256,md5) in prepared.items():
        key='showcase/'+name
        metadata={'name':key,'contentType':'video/mp4','cacheControl':'public, max-age=3600','metadata':{'sha256':sha256}}
        boundary='showcase-'+uuid.uuid4().hex
        payload=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+json.dumps(metadata).encode()+
                 f'\r\n--{boundary}\r\nContent-Type: video/mp4\r\n\r\n'.encode()+body+f'\r\n--{boundary}--\r\n'.encode())
        result=api.request('POST',f"https://storage.googleapis.com/upload/storage/v1/b/{settings['bucket']}/o?"+query(uploadType='multipart',name=key),
                           raw=payload,content_type='multipart/related; boundary='+boundary)
        if result.get('name')!=key or int(result.get('size',-1))!=len(body) or result.get('md5Hash')!=md5:
            raise RuntimeError('Uploaded showcase checksum verification failed.')
        receipt[name]={'object':key,'size':len(body),'sha256':sha256,'md5':md5,'generation':result.get('generation'),'verified':True}
    settings['showcaseUploaded']=receipt
    (ROOT/'cloud'/'showcase-upload.json').write_text(json.dumps({'bucket':settings['bucket'],'publicBucket':False,'files':receipt},indent=2)+'\n')
    print('Three curated showcase movies uploaded and verified; private user objects were not accessed.')


def stage_showcase(index,settings):
    if not settings.get('showcaseUploaded'):return index,[],None
    if set(settings['showcaseUploaded'])!=set(SHOWCASE_SOURCES):raise ValueError('All three verified showcase uploads are required.')
    parsed=urlsplit(settings.get('apiUrl',''))
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('Showcase requires a configured HTTPS API origin.')
    origin=parsed.scheme+'://'+parsed.netloc
    redirects=[]
    for filename,asset in SHOWCASE_SOURCES.items():
        record=settings['showcaseUploaded'][filename]
        if record.get('object')!='showcase/'+filename or record.get('verified') is not True:raise ValueError('Showcase upload receipt is invalid.')
        public_url=origin+'/api/v1/showcase/'+filename
        index=index.replace('"'+asset+'"','"'+public_url+'"')
        redirects.append({'glob':asset,'location':public_url,'statusCode':302})
    return index,redirects,origin

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
    # New HTML must not reuse an older release's still-fresh module or stylesheet.
    # Fingerprint dependencies from the leaves upward without changing dev sources.
    staged = {}
    state_hash = hashlib.sha256((public_dir / "state.mjs").read_bytes()).hexdigest()[:16]
    app = (public_dir / "app.js").read_text().replace(
        '"./state.mjs"', f'"./state.mjs?v={state_hash}"')
    staged["app.js"] = app.encode()
    app_hash = hashlib.sha256(staged["app.js"]).hexdigest()[:16]
    css_hash = hashlib.sha256((public_dir / "style.css").read_bytes()).hexdigest()[:16]
    index = (public_dir / "index.html").read_text().replace(
        'src="/app.js"', f'src="/app.js?v={app_hash}"').replace(
        'href="/style.css"', f'href="/style.css?v={css_hash}"')
    index, media_redirects, media_origin = stage_showcase(index, settings)
    staged["index.html"] = index.encode()
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(public_dir)
        if media_origin and path.suffix.lower() == ".mp4":
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(public_dir):
            raise ValueError("Hosting assets must be regular files inside the public directory")
        if path.suffix.lower() in (".pem", ".p12", ".key", ".sqlite3", ".env"):
            raise ValueError("Credential or state file rejected from Hosting assets")
        body = gzip.compress(staged.get(relative.as_posix(), path.read_bytes()), mtime=0)
        digest = hashlib.sha256(body).hexdigest()
        files["/" + relative.as_posix()] = digest
        bodies[digest] = body
    hosting_config = {
        "redirects": media_redirects,
        "rewrites": [
            *([{ "glob": "/api/**", "run": {"serviceId": settings["apiService"], "region": region}}] if firebase_project == project else []),
            {"glob": "**", "path": "/index.html"},
        ],
        "headers": [
            {"glob": "**", "headers": {
                "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' https://www.gstatic.com; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: " + (media_origin or "") + "; connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com " + settings.get("apiUrl", "") + "; frame-src https://" + settings["firebaseConfig"]["authDomain"] + "; base-uri 'self'; form-action 'self'; object-src 'none'; frame-ancestors 'none'",
            }},
            {"glob": "/config.js", "headers": {"Cache-Control": "no-store"}},
            *[{"glob": filename, "headers": {"Cache-Control": "no-cache"}}
              for filename in ("/", "/index.html", "/app.js", "/state.mjs", "/style.css")],
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
    parser.add_argument("stage", choices=("build", "build-api", "build-worker", "job", "api", "services", "showcase", "hosting", "all"))
    parser.add_argument("--settings", default=str(ROOT / "cloud" / "deployment.json"))
    parser.add_argument("--public-dir", default=str(ROOT / "web" / "dist"))
    parser.add_argument("--original", help="Verified original MP4 for the curated showcase")
    parser.add_argument("--blue-hour", help="Accepted cloud palette MP4 for the curated showcase")
    parser.add_argument("--studio-demo", help="Completed narrated demonstration MP4 for the curated showcase")
    args = parser.parse_args()
    settings_path = Path(args.settings)
    settings = json.loads(settings_path.read_text())
    if args.stage == "showcase":
        if not all((args.original,args.blue_hour,args.studio_demo)):
            parser.error("showcase requires --original, --blue-hour and --studio-demo")
        upload_showcase(settings,{'original.mp4':args.original,'blue-hour.mp4':args.blue_hour,'studio-demo.mp4':args.studio_demo})
        settings_path.write_text(json.dumps(settings,indent=2)+"\n")
    if args.stage in ("build", "all"):
        build(settings)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    if args.stage == "build-api":
        build_api(settings)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    if args.stage == "build-worker":
        build_worker(settings)
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
