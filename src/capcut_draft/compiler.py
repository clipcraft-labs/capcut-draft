"""Compile Clipcraft Project data into a minimal CapCut Desktop draft."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from .lockfile import load_lock
from .project import Project, ProjectError
from .assets import AssetStore

US = 1_000_000


@dataclass(frozen=True, slots=True)
class BuildResult:
    output: Path
    tracks: int
    segments: int
    duration_us: int


def _id() -> str:
    return str(uuid4())


def _materials() -> dict[str, list[dict[str, Any]]]:
    names = ("videos", "audios", "texts", "video_effects", "transitions", "material_animations", "masks", "canvases", "speeds", "placeholder_infos", "sound_channel_mappings", "vocal_separations")
    return {name: [] for name in names}


def compile_project(project: Project, output: str | Path, *, lock_path: str | Path | None = None, asset_store: str | Path | None = None) -> BuildResult:
    out = Path(output).resolve()
    if out.exists():
        raise ProjectError(f"Output already exists: {out}")
    resources = load_lock(lock_path)
    store = AssetStore(asset_store)
    materials = _materials()
    tracks: list[dict[str, Any]] = []
    refs: dict[str, tuple[dict[str, Any], dict[str, Any], int, int]] = {}
    duration_us = 0

    for source_track in project.data["tracks"]:
        track = {"id": _id(), "type": source_track["type"], "name": source_track.get("name", ""), "segments": []}
        for item in source_track["items"]:
            material_id = _id()
            start = round(float(item["at"]) * US)
            duration = round(float(item["duration"]) * US)
            segment_id = _id()
            if source_track["type"] == "text":
                content = json.dumps({"text": item["text"], "styles": []}, ensure_ascii=False, separators=(",", ":"))
                materials["texts"].append({"id": material_id, "type": "text", "content": content, "font_size": item.get("fontSize", 15), "text_color": item.get("color", "#FFFFFF")})
            else:
                asset_dir = out / "assets" / source_track["type"]
                if item.get("resource"):
                    locked = resources.get(item["resource"])
                    if locked is None or not locked.get("asset_hash"):
                        raise ProjectError(f"Resource {item['resource']!r} has no locked asset_hash")
                    digest = str(locked["asset_hash"])
                    destination = store.copy_into(digest, asset_dir)
                    display_name = str(locked.get("name") or destination.name)
                else:
                    source = (project.path.parent / item["src"]).resolve()
                    if not source.is_file():
                        raise ProjectError(f"Local asset does not exist: {source}")
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    destination = asset_dir / f"{digest}{source.suffix.lower()}"
                    shutil.copy2(source, destination)
                    display_name = source.name
                entry = {
                    "id": material_id,
                    "type": source_track["type"],
                    "name": display_name,
                    "path": str(destination),
                    "content_hash": f"sha256:{digest}",
                }
                materials["videos" if source_track["type"] == "video" else "audios"].append(entry)
            segment = {"id": segment_id, "material_id": material_id, "target_timerange": {"start": start, "duration": duration}, "source_timerange": {"start": 0, "duration": duration}, "extra_material_refs": [], "render_index": 0}
            track["segments"].append(segment)
            if item.get("ref"):
                refs[item["ref"]] = (segment, materials["texts"][-1] if source_track["type"] == "text" else entry, start, duration)
            duration_us = max(duration_us, start + duration)
        tracks.append(track)

    for operation in project.data.get("operations", []):
        resource = resources.get(operation["resource"])
        if resource is None:
            raise ProjectError(f"Resource {operation['resource']!r} is not locked")
        target_segment, target_material, start, duration = refs[operation["target"]]
        material_id = _id()
        effect_segment_id = _id()
        resource_id = str(resource.get("resource_id") or resource.get("id") or "")
        effect_id = str(resource.get("effect_id") or resource_id)
        if not resource_id:
            raise ProjectError(f"Resource {operation['resource']!r} has no resource_id")
        kind = operation["type"]
        if kind in {"effect", "filter"}:
            materials["video_effects"].append({
                "id": material_id,
                "type": "filter" if kind == "filter" else "video_effect",
                "name": resource.get("name", operation["resource"]),
                "resource_id": resource_id,
                "effect_id": effect_id,
                "apply_target_type": 0,
                "bind_segment_id": target_segment["id"],
                "source_platform": 1,
                "value": operation.get("intensity", 1.0),
            })
            tracks.append({"id": _id(), "type": kind, "name": "Filters" if kind == "filter" else "Effects", "segments": [{"id": effect_segment_id, "material_id": material_id, "target_timerange": {"start": start, "duration": duration}, "source_timerange": {"start": 0, "duration": duration}, "extra_material_refs": [], "render_index": 0}]})
        elif kind == "transition":
            transition_duration = round(float(operation.get("duration", min(duration / US, 0.5))) * US)
            materials["transitions"].append({
                "id": material_id,
                "type": "transition",
                "name": resource.get("name", operation["resource"]),
                "resource_id": resource_id,
                "effect_id": effect_id,
                "duration": transition_duration,
                "is_overlap": bool(resource.get("is_overlap", True)),
            })
            target_segment["extra_material_refs"].append(material_id)
        else:
            if target_material.get("type") != "text":
                raise ProjectError("caption-template operations require a text target")
            target_material["effect_id"] = effect_id
            target_material["effect_resource_id"] = resource_id

    canvas = project.data["canvas"]
    target = project.data.get("target", {})
    draft = {"id": _id(), "name": project.name, "duration": duration_us, "fps": canvas["fps"], "canvas_config": {"width": canvas["width"], "height": canvas["height"], "ratio": canvas.get("ratio", "")}, "tracks": tracks, "materials": materials, "platform": {"app_source": "cc", "os": target.get("os", "mac"), "app_version": target.get("version", "")}, "free_render_index_mode_on": False}
    out.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(draft, ensure_ascii=False, separators=(",", ":"))
    (out / "draft_content.json").write_text(encoded, encoding="utf-8")
    (out / "draft_info.json").write_text(encoded, encoding="utf-8")
    return BuildResult(out, len(tracks), sum(len(track["segments"]) for track in tracks), duration_us)
