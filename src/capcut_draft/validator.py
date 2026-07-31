"""Validation for generated draft artifacts."""

import json
from pathlib import Path

from .project import ProjectError


def validate_draft(path: str | Path) -> dict[str, int]:
    root = Path(path)
    target = root / "draft_content.json" if root.is_dir() else root
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
    return {"tracks": len(tracks), "segments": len(segments), "materials": len(material_ids)}

