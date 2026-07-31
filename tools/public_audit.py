#!/usr/bin/env python3
"""Reject likely secrets, local paths, and private artifacts in public files."""

import re
from pathlib import Path

SKIP = {".git", ".venv", "build", "dist", "__pycache__"}
SUFFIXES = {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".txt"}
PATTERNS = (
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"\b(?:Authorization|Cookie)\s*:\s*\S+"),
    re.compile(r"(?i)\b(?:access_token|api[_-]?key)\s*[=:]\s*[^\s<]"),
)


def main() -> int:
    findings: list[str] = []
    for path in Path(".").rglob("*"):
        if not path.is_file() or set(path.parts) & SKIP or path.suffix.lower() not in SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if path.name == "public_audit.py" and "re.compile" in line:
                continue
            if any(pattern.search(line) for pattern in PATTERNS):
                findings.append(f"{path}:{number}")
    if findings:
        print("Public audit failed:\n" + "\n".join(findings))
        return 1
    print("Public audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
