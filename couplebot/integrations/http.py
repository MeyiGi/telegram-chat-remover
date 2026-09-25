"""Small JSON HTTP helper shared by external service adapters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class ExternalServiceError(RuntimeError):
    pass


def request_json(
    url: str,
    headers: dict[str, str],
    payload: dict | None = None,
    timeout: int = 90,
    method: str = "POST",
) -> dict:
    request = urllib.request.Request(
        url,
        data=(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        ),
        headers={**headers, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ExternalServiceError(f"API request failed with HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise ExternalServiceError(f"API request failed: {url}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ExternalServiceError(f"API returned invalid JSON: {url}") from exc
