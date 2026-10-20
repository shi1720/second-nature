import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import package_delivery


class PackagingTests(unittest.TestCase):
    def test_credentials_caches_databases_and_symlinks_are_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in [
                ".env",
                "service-account.json",
                "local.sqlite3",
                ".voice-venv/bin/tool",
                "film/frames/frame.png",
                "README.md",
            ]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            (root / "linked.txt").symlink_to(root / "README.md")
            self.assertEqual(
                [
                    p.relative_to(root).as_posix()
                    for p in package_delivery.collect(root)
                ],
                ["README.md"],
            )

    def test_credential_like_json_is_rejected_without_echoing_value(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            value = "disposable-fixture-value-only"
            (root / "settings.json").write_text(json.dumps({"refresh_token": value}))
            with self.assertRaises(ValueError) as caught:
                package_delivery.collect(root)
            self.assertNotIn(value, str(caught.exception))

    def test_archive_detects_changed_content_even_with_valid_zip_crc(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "delivery.zip"
            manifest = {
                "files": [
                    {
                        "path": "hello.txt",
                        "bytes": 5,
                        "sha256": hashlib.sha256(b"alpha").hexdigest(),
                    }
                ]
            }
            for payload, valid in [(b"alpha", True), (b"omega", False)]:
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(
                        "entry/PACKAGE-MANIFEST.json", json.dumps(manifest)
                    )
                    archive.writestr("entry/hello.txt", payload)
                if valid:
                    self.assertEqual(package_delivery.verify_archive(path), 2)
                else:
                    with self.assertRaisesRegex(ValueError, "checksum"):
                        package_delivery.verify_archive(path)

    def test_incomplete_media_cannot_produce_a_submission_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "submission.zip"
            with self.assertRaises((FileNotFoundError, ValueError)):
                package_delivery.package(root, target)
            self.assertFalse(target.exists())
            self.assertFalse((root / "PACKAGE-MANIFEST.json").exists())


if __name__ == "__main__":
    unittest.main()
