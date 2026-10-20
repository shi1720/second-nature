#!/usr/bin/env python3
"""Package verified deliverables, excluding credentials and generated caches."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".voice-venv",
    ".demo-build",
    "__pycache__",
    "node_modules",
    "projects",
    ".data",
    "work",
    "credentials",
    "secrets",
    ".firebase",
}
EXCLUDED_NAMES = {
    "PACKAGE-MANIFEST.json",
    ".DS_Store",
    "opening.png",
    "closing.png",
    "render-job.json",
    "resolved-config.json",
}
CREDENTIAL_PATTERNS = (
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    rb'"(?:refresh_token|access_token|client_secret)"\s*:\s*"[^"\r\n]{16,}"',
    rb"\bya29\.[A-Za-z0-9_-]{20,}",
)


def digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return digest(stream)


def sensitive_name(name):
    lower = name.lower()
    return (
        lower.startswith(".env")
        or lower
        in {"credentials.json", "token.json", "application_default_credentials.json"}
        or Path(lower).suffix in {".pem", ".key", ".p12", ".pfx"}
        or bool(
            re.search(
                r"(?:service[-_]account|firebase-adminsdk|client[-_]secret).*\.json$",
                lower,
            )
        )
    )


def collect(root):
    files = []

    def excluded_directory(name):
        return (
            name in EXCLUDED_DIRS
            or name.endswith("-venv")
            or name == "frames"
            or name.startswith("frames-")
        )

    candidates = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = [
            name
            for name in names
            if not excluded_directory(name)
            and not (Path(directory) / name).is_symlink()
        ]
        candidates.extend(Path(directory) / name for name in filenames)
    for path in sorted(candidates):
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink():
            continue
        if (
            path.name in EXCLUDED_NAMES
            or sensitive_name(path.name)
            or path.name.startswith(".pipeline")
            or ".partial." in path.name
            or path.suffix.lower()
            in {
                ".log",
                ".pyc",
                ".blend1",
                ".blend2",
                ".zip",
                ".db",
                ".sqlite",
                ".sqlite3",
            }
        ):
            continue
        if path.suffix.lower() in {
            ".json",
            ".txt",
            ".md",
            ".py",
            ".js",
            ".mjs",
            ".yml",
            ".yaml",
            ".toml",
        }:
            body = path.read_bytes()
            if any(re.search(pattern, body) for pattern in CREDENTIAL_PATTERNS):
                raise ValueError(
                    f"Credential-like content rejected in {relative}; values are not printed."
                )
        files.append(path)
    return files


def require_finished_media(root):
    for name in (
        "verification.json",
        "studio-demo.verification.json",
        "blue-hour-verification.json",
    ):
        report = json.loads((root / "film" / name).read_text())
        if report.get("passed") is not True:
            raise ValueError(f"Media acceptance has not passed: {name}")
    if (
        json.loads((root / "cloud/qa-report.json").read_text()).get("full_verified")
        is not True
    ):
        raise ValueError("The full cloud acceptance render must pass before packaging.")
    master = json.loads((root / "film/delivery.json").read_text())
    demo = json.loads((root / "film/studio-demo.verification.json").read_text())
    blue = json.loads((root / "film/blue-hour-delivery.json").read_text())
    for filename, expected in (
        ("second-nature.mp4", master.get("sha256")),
        ("studio-demo.mp4", demo.get("sha256")),
        ("blue-hour-preview.mp4", blue.get("sha256")),
    ):
        if not expected or file_digest(root / "film" / filename) != expected:
            raise ValueError(f"Verified media changed: {filename}")


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        manifests = [
            name
            for name in archive.namelist()
            if name.endswith("/PACKAGE-MANIFEST.json")
        ]
        if len(manifests) != 1:
            raise ValueError("The archive requires exactly one package manifest.")
        manifest_name = manifests[0]
        prefix = manifest_name.removesuffix("PACKAGE-MANIFEST.json")
        if Path(prefix).is_absolute() or ".." in Path(prefix).parts or "\\" in prefix:
            raise ValueError("The archive root is not a safe relative path.")
        manifest = json.loads(archive.read(manifest_name))
        expected = {manifest_name}
        for record in manifest["files"]:
            relative = Path(record["path"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in record["path"]
            ):
                raise ValueError("An archive entry contains an unsafe relative path.")
            name = prefix + relative.as_posix()
            if name in expected:
                raise ValueError("The manifest contains a duplicate entry.")
            expected.add(name)
            if archive.getinfo(name).file_size != record["bytes"]:
                raise ValueError(f"Archive size mismatch: {relative}")
            with archive.open(name) as stream:
                if digest(stream) != record["sha256"]:
                    raise ValueError(f"Archive checksum mismatch: {relative}")
        if (
            len(archive.namelist()) != len(expected)
            or set(archive.namelist()) != expected
        ):
            raise ValueError("The archive inventory differs from its manifest.")
    return len(expected)


def package(root, target):
    require_finished_media(root)
    files = collect(root)
    manifest = {
        "title": "SECOND NATURE",
        "entrant": "Shivam Gupta",
        "scope": "Every shipped file except this manifest is inventoried and hashed.",
        "files": [
            {
                "path": p.relative_to(root).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": file_digest(p),
            }
            for p in files
        ],
    }
    manifest_path = root / "PACKAGE-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    files.append(manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=target.stem + ".", suffix=".partial.zip", dir=target.parent, delete=False
    ) as stream:
        partial = Path(stream.name)
    try:
        with zipfile.ZipFile(
            partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for path in files:
                archive.write(path, root.name + "/" + path.relative_to(root).as_posix())
        count = verify_archive(partial)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return {
        "zip": str(target),
        "files": count,
        "bytes": target.stat().st_size,
        "sha256": file_digest(target),
        "verified": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT.parent / "second-nature-submission.zip"
    )
    parser.add_argument(
        "--verify", type=Path, help="Verify an existing ZIP without rebuilding it"
    )
    args = parser.parse_args()
    if args.verify:
        print(json.dumps({"verified": True, "files": verify_archive(args.verify)}))
    else:
        print(json.dumps(package(ROOT, args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
