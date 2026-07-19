"""Small, dependency-free client for Fabric public REST APIs."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FABRIC_API = "https://api.fabric.microsoft.com/v1"


class FabricApiError(RuntimeError):
    """A Fabric API error that retains the HTTP status for safe handling."""

    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"Fabric API {method} {path} failed: {status} {body}")
        self.status = status
        self.body = body


@dataclass
class FabricResponse:
    """A successful Fabric API response."""

    status: int
    headers: dict[str, str]
    body: dict[str, Any]


def access_token() -> str:
    """Return a Fabric token from the active Azure CLI identity."""

    result = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://api.fabric.microsoft.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


class FabricClient:
    """Issue authenticated requests and follow Fabric long-running operations."""

    def __init__(self, token: str) -> None:
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 60,
    ) -> FabricResponse:
        url = path if path.startswith("https://") else f"{FABRIC_API}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
                body = json.loads(raw_body) if raw_body else {}
                return FabricResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=body,
                )
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise FabricApiError(method, path, exc.code, body) from exc

    def list_values(self, path: str) -> list[dict[str, Any]]:
        """Return every item from a Fabric list endpoint."""

        values: list[dict[str, Any]] = []
        continuation_token: str | None = None
        while True:
            page_path = path
            if continuation_token:
                separator = "&" if "?" in page_path else "?"
                page_path = f"{page_path}{separator}{urlencode({'continuationToken': continuation_token})}"
            response = self.request("GET", page_path)
            values.extend(response.body.get("value", []))
            continuation_token = response.body.get("continuationToken")
            if not continuation_token:
                return values

    def wait_for_lro(self, response: FabricResponse, timeout_seconds: int) -> FabricResponse:
        """Wait for a Fabric long-running operation when the API returned 202."""

        if response.status != 202:
            return response

        location = response.headers.get("Location") or response.headers.get("location")
        if not location:
            raise RuntimeError("Fabric returned 202 Accepted without an operation Location header.")

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after") or "5"
            try:
                delay = max(1, int(retry_after))
            except ValueError:
                delay = 5
            time.sleep(delay)
            response = self.request("GET", location)
            if response.status != 202:
                return response

        raise TimeoutError(f"Timed out after {timeout_seconds} seconds waiting for Fabric operation {location}.")
