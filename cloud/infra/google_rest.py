"""Small Google REST client. Credentials stay in memory and never enter logs."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"Google API returned {status}: {message}")


class GoogleRest:
    def __init__(self, quota_project=None):
        self._token = ""
        self._issued = 0.0
        self.quota_project = quota_project

    def _authorization(self) -> str:
        if time.monotonic() - self._issued > 2400 or not self._token:
            result = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                check=True, text=True, capture_output=True,
            )
            self._token = result.stdout.strip()
            self._issued = time.monotonic()
        return "Bearer " + self._token

    def request(self, method, url, data=None, *, raw=None, content_type=None):
        payload = raw if raw is not None else (
            json.dumps(data).encode() if data is not None else None
        )
        for attempt in range(7):
            headers = {"Authorization": self._authorization()}
            if self.quota_project:
                headers["X-Goog-User-Project"] = self.quota_project
            if payload is not None:
                headers["Content-Type"] = content_type or "application/json"
            request = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    body = response.read()
                    return json.loads(body) if body and "json" in response.headers.get("Content-Type", "") else {}
            except urllib.error.HTTPError as error:
                body = error.read()
                if error.code == 401 and attempt == 0:
                    self._token = ""
                    continue
                if error.code in (429, 500, 502, 503, 504) and attempt < 6:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                if error.code == 403 and b"SERVICE_DISABLED" in body and attempt < 6:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                try:
                    message = json.loads(body).get("error", {}).get("message", "Request failed")
                except (ValueError, AttributeError):
                    message = "Request failed; response suppressed"
                # Never include request headers, raw token responses, or secret payloads.
                raise ApiError(error.code, message) from None
        raise RuntimeError("Google API retry limit reached")

    def wait(self, operation, base, *, timeout=600):
        deadline = time.monotonic() + timeout
        while not operation.get("done"):
            if time.monotonic() >= deadline:
                raise TimeoutError("Google API operation is still pending")
            time.sleep(3)
            operation = self.request("GET", base.rstrip("/") + "/" + operation["name"])
        if operation.get("error"):
            raise RuntimeError(operation["error"].get("message", "Google API operation failed"))
        return operation.get("response", {})


def query(**values):
    return urllib.parse.urlencode(values)
