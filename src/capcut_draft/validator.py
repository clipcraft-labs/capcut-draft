"""Validation for generated draft artifacts."""

import hashlib
import json
from pathlib import Path
import re

from .project import ProjectError


_DRAFT_PATH = re.compile(r"^##_draftpath_placeholder_[^#]+_##/(.+)$")


def _media_path(value: str, root: Path) -> Path:
    placeholder = _DRAFT_PATH.match(value)
    if placeholder:
        return root / placeholder.group(1)
    return Path(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_draft(path: str | Path) -> dict[str, int]:
    root = Path(path)
    target = root / "draft_content.json" if root.is_dir() else root
    draft_root = root.resolve() if root.is_dir() else target.parent.resolve()
    try:
        draft = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError(f"Unable to read draft: {exc}") from exc
    materials = draft.get("materials")
    tracks = draft.get("tracks")
    if not isinstance(materials, dict) or not isinstance(tracks, list):
        raise ProjectError("Draft must contain materials and tracks")
    material_ids = {item.get("id") for values in materials.values() if isinstance(values, list) for item in values if isinstance(item, dict)}
    segments = [segment for track in tracks if isinstance(track, dict) for segment in track.get("segments", []) if isinstance(segment, dict)]
    missing = [segment.get("material_id") for segment in segments if segment.get("material_id") not in material_ids]
    if missing:
        raise ProjectError(f"Draft contains {len(missing)} missing material references")
    media_files = 0
    external_media_files = 0
    for values in materials.values():
        if not isinstance(values, list):
            continue
        for material in values:
            if not isinstance(material, dict) or not isinstance(material.get("path"), str) or not material["path"]:
                continue
            media = _media_path(material["path"], draft_root)
            if not media.is_file():
                raise ProjectError(f"Draft media file is missing: {media}")
            media_files += 1
            try:
                media.resolve().relative_to(draft_root)
            except ValueError:
                external_media_files += 1
            content_hash = material.get("content_hash")
            if isinstance(content_hash, str) and content_hash.startswith("sha256:"):
                expected = content_hash.removeprefix("sha256:")
                if _sha256(media) != expected:
                    raise ProjectError(f"Draft media hash does not match: {media}")
    return {
        "tracks": len(tracks),
        "segments": len(segments),
        "materials": len(material_ids),
        "media_files": media_files,
        "external_media_files": external_media_files,
    }
