"""Validated, vendor-neutral Clipcraft Project representation."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class ProjectError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Project:
    path: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("name") or self.path.stem)


def load_project(path: str | Path) -> Project:
    project_path = Path(path).resolve()
    try:
        data = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError(f"Unable to read project JSON: {exc}") from exc
    validate_project(data)
    return Project(project_path, data)


def validate_project(data: Any) -> None:
    if not isinstance(data, dict):
        raise ProjectError("Project must be a JSON object")
    if data.get("version") != 1:
        raise ProjectError("Project version must be 1")
    canvas = data.get("canvas")
    if not isinstance(canvas, dict):
        raise ProjectError("canvas is required")
    for key in ("width", "height", "fps"):
        if not isinstance(canvas.get(key), int) or canvas[key] <= 0:
            raise ProjectError(f"canvas.{key} must be a positive integer")
    target = data.get("target", {})
    if not isinstance(target, dict):
        raise ProjectError("target must be an object")
    if target.get("app", "capcut") != "capcut":
        raise ProjectError("target.app must be capcut")
    if target.get("os", "mac") not in {"mac", "windows"}:
        raise ProjectError("target.os must be mac or windows")
    tracks = data.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ProjectError("tracks must be a non-empty array")
    refs: set[str] = set()
    for track_index, track in enumerate(tracks):
        if not isinstance(track, dict) or track.get("type") not in {"video", "audio", "text"}:
            raise ProjectError(f"tracks[{track_index}].type must be video, audio, or text")
        items = track.get("items")
        if not isinstance(items, list) or not items:
            raise ProjectError(f"tracks[{track_index}].items must be a non-empty array")
        for item_index, item in enumerate(items):
            where = f"tracks[{track_index}].items[{item_index}]"
            if not isinstance(item, dict):
                raise ProjectError(f"{where} must be an object")
            if not isinstance(item.get("at"), (int, float)) or item["at"] < 0:
                raise ProjectError(f"{where}.at must be non-negative seconds")
            if not isinstance(item.get("duration"), (int, float)) or item["duration"] <= 0:
                raise ProjectError(f"{where}.duration must be positive seconds")
            if track["type"] == "text":
                if not isinstance(item.get("text"), str) or not item["text"]:
                    raise ProjectError(f"{where}.text is required")
            elif not any(isinstance(item.get(key), str) and item[key] for key in ("src", "resource")):
                raise ProjectError(f"{where}.src or {where}.resource is required")
            ref = item.get("ref")
            if ref:
                if not isinstance(ref, str) or ref in refs:
                    raise ProjectError(f"{where}.ref must be a unique string")
                refs.add(ref)
    operations = data.get("operations", [])
    if not isinstance(operations, list):
        raise ProjectError("operations must be an array")
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict) or operation.get("type") not in {
            "effect",
            "filter",
            "transition",
            "caption-template",
        }:
            raise ProjectError(f"operations[{index}].type is not supported")
        if operation.get("target") not in refs:
            raise ProjectError(f"operations[{index}].target does not match an item ref")
        if not isinstance(operation.get("resource"), str):
            raise ProjectError(f"operations[{index}].resource is required")
