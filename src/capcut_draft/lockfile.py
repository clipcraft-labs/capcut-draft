"""Reproducible catalogue resolution lock file."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .project import ProjectError


SENSITIVE_QUERY_KEYS = {"token", "signature", "sig", "auth", "authorization", "cookie"}


def load_lock(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    lock_path = Path(path)
    try:
        value = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError(f"Unable to read lock file: {exc}") from exc
    if value.get("version") != 1 or not isinstance(value.get("resources"), dict):
        raise ProjectError("Lock file must contain version 1 and a resources object")
    for name, resource in value["resources"].items():
        if not isinstance(resource, dict):
            raise ProjectError(f"Lock resource {name!r} must be an object")
        for field in ("preview_url", "download_url"):
            url = resource.get(field)
            if not url:
                continue
            keys = {key.lower() for key in parse_qs(urlparse(str(url)).query)}
            if keys & SENSITIVE_QUERY_KEYS:
                raise ProjectError(f"Lock resource {name!r} contains a sensitive URL query")
    return value["resources"]

