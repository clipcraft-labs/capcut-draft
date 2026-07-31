"""Verified CapCut Desktop target compatibility."""

from typing import Any

from .project import ProjectError


VERIFIED_TARGETS = frozenset({("mac", "9.1.0")})


def require_verified_target(target: dict[str, Any], *, allow_unsupported: bool = False) -> tuple[str, str]:
    os_name = str(target.get("os") or "mac")
    version = str(target.get("version") or "9.1.0")
    if (os_name, version) not in VERIFIED_TARGETS and not allow_unsupported:
        raise ProjectError(
            f"CapCut Desktop {version} on {os_name} is not a verified target; "
            "pass allow_unsupported_version=True only after reviewing the generated draft"
        )
    return os_name, version
