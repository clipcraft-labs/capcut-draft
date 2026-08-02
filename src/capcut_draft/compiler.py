"""Compile Clipcraft Project data into a minimal CapCut Desktop draft."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
from typing import Any
from uuid import uuid4

from .lockfile import load_lock
from .project import Project, ProjectError
from .assets import AssetStore
from .compatibility import require_verified_target

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
    names = (
        "flowers", "videos", "tail_leaders", "audios", "images", "texts",
        "effects", "stickers", "canvases", "transitions", "audio_effects",
        "audio_fades", "beats", "material_animations", "placeholders",
        "placeholder_infos", "speeds", "common_mask", "chromas",
        "text_templates", "realtime_denoises", "audio_pannings",
        "audio_pitch_shifts", "video_trackings", "hsl", "drafts",
        "color_curves", "hsl_curves", "primary_color_wheels",
        "log_color_wheels", "video_effects", "ai_text_effects",
        "audio_balances", "handwrites", "manual_deformations",
        "manual_beautys", "plugin_effects", "sound_channel_mappings",
        "green_screens", "shapes", "material_colors", "digital_humans",
        "digital_human_model_dressing", "smart_crops", "ai_translates",
        "audio_track_indexes", "loudnesses", "vocal_beautifys",
        "vocal_separations", "smart_relights", "time_marks",
        "multi_language_refs", "video_shadows", "video_strokes", "video_radius",
    )
    return {name: [] for name in names}


def _clip(*, alpha: float = 1.0, scale: float = 1.0, x: float = 0.0, y: float = 0.0) -> dict[str, Any]:
    return {
        "alpha": alpha,
        "flip": {"horizontal": False, "vertical": False},
        "rotation": 0.0,
        "scale": {"x": scale, "y": scale},
        "transform": {"x": x, "y": y},
    }


def _config() -> dict[str, Any]:
    return {
        "video_mute": False, "record_audio_last_index": 1,
        "extract_audio_last_index": 1, "original_sound_last_index": 1,
        "subtitle_recognition_id": "", "subtitle_taskinfo": [],
        "lyrics_recognition_id": "", "lyrics_taskinfo": [],
        "subtitle_sync": True, "lyrics_sync": True, "voice_change_sync": False,
        "sticker_max_index": 1, "adjust_max_index": 1,
        "material_save_mode": 0, "export_range": None,
        "maintrack_adsorb": True, "combination_max_index": 1,
        "attachment_info": [], "zoom_info_params": None,
        "system_font_list": [], "multi_language_mode": "none",
        "multi_language_main": "none", "multi_language_current": "none",
        "multi_language_list": [], "subtitle_keywords_config": None,
        "use_float_render": False,
    }


def _keyframes() -> dict[str, list[Any]]:
    return {name: [] for name in ("videos", "audios", "texts", "stickers", "filters", "adjusts", "handwrites", "effects")}


def _catalog_identity(resource: dict[str, Any]) -> dict[str, Any]:
    """Return stable catalogue provenance safe to copy into build metadata."""
    identifier = str(resource.get("id") or resource.get("resource_id") or resource.get("effect_id") or "")
    resource_id = resource.get("resource_id")
    effect_id = resource.get("effect_id")
    category = resource.get("category") if isinstance(resource.get("category"), dict) else {}
    return {
        "provider": resource.get("provider"),
        "kind": resource.get("kind"),
        "id": identifier,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "effect_id": str(effect_id) if effect_id is not None else None,
        "name": resource.get("name"),
        "category": dict(category),
        "vip": resource.get("vip"),
        "commercial": resource.get("commercial"),
        "duration": resource.get("duration"),
        "asset_hash": resource.get("asset_hash"),
        "size": resource.get("size"),
    }


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        length = struct.unpack(">H", data[offset:offset + 2])[0]
        if length < 2 or offset + length > len(data):
            break
        if marker in sof_markers and length >= 7:
            height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
            return width, height
        offset += length
    return None


def _cover_scale(media_width: int, media_height: int, canvas_width: int, canvas_height: int) -> float:
    contain = min(canvas_width / media_width, canvas_height / media_height)
    cover = max(canvas_width / media_width, canvas_height / media_height)
    return cover / contain


def compile_project(
    project: Project,
    output: str | Path,
    *,
    lock_path: str | Path | None = None,
    asset_store: str | Path | None = None,
    allow_unsupported_version: bool = False,
) -> BuildResult:
    out = Path(output).resolve()
    if out.exists():
        raise ProjectError(f"Output already exists: {out}")
    target = project.data.get("target", {})
    target_os, target_version = require_verified_target(
        target, allow_unsupported=allow_unsupported_version
    )
    resources = load_lock(lock_path)
    store = AssetStore(asset_store)
    materials = _materials()
    tracks: list[dict[str, Any]] = []
    refs: dict[str, tuple[dict[str, Any], dict[str, Any], int, int]] = {}
    resource_uses: list[dict[str, Any]] = []
    duration_us = 0

    for source_track in project.data["tracks"]:
        source_type = source_track["type"]
        track_type = "video" if source_type == "image" else source_type
        track = {"id": _id(), "type": track_type, "name": source_track.get("name", ""), "is_default_name": True, "attribute": 0, "flag": 0, "segments": []}
        for item in source_track["items"]:
            material_id = _id()
            start = round(float(item["at"]) * US)
            duration = round(float(item["duration"]) * US)
            segment_id = _id()
            if source_type == "text":
                content = json.dumps({"text": item["text"], "styles": []}, ensure_ascii=False, separators=(",", ":"))
                materials["texts"].append({"id": material_id, "type": "text", "content": content, "font_size": item.get("fontSize", 15), "text_color": item.get("color", "#FFFFFF"), "alignment": item.get("alignment", 1), "background_alpha": item.get("backgroundAlpha", 0.0), "background_color": item.get("backgroundColor", ""), "bold_width": item.get("boldWidth", 0.0), "border_color": item.get("borderColor", "#000000"), "border_width": item.get("borderWidth", 0.0), "check_flag": 15, "font_id": "", "font_name": item.get("fontFamily", ""), "has_shadow": item.get("shadowAlpha", 0.0) > 0, "italic_degree": 0, "letter_spacing": item.get("letterSpacing", 0), "line_spacing": item.get("lineSpacing", 0.02), "name": "", "recognize_type": 0, "shadow_alpha": item.get("shadowAlpha", 0.0), "text_alpha": item.get("alpha", 1.0), "text_size": item.get("fontSize", 15), "underline": False})
            else:
                asset_dir = out / "assets" / source_type
                if item.get("resource"):
                    locked = resources.get(item["resource"])
                    if locked is None or not locked.get("asset_hash"):
                        raise ProjectError(f"Resource {item['resource']!r} has no locked asset_hash")
                    digest = str(locked["asset_hash"])
                    destination = store.copy_into(digest, asset_dir)
                    display_name = str(locked.get("name") or destination.name)
                    identity = _catalog_identity(locked)
                    resource_uses.append({
                        "resource": item["resource"],
                        "usage": source_type,
                        "target": item.get("ref"),
                    })
                else:
                    source = (project.path.parent / item["src"]).resolve()
                    if not source.is_file():
                        raise ProjectError(f"Local asset does not exist: {source}")
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    destination = asset_dir / f"{digest}{source.suffix.lower()}"
                    shutil.copy2(source, destination)
                    display_name = source.name
                    identity = None
                canvas_width = int(project.data["canvas"]["width"])
                canvas_height = int(project.data["canvas"]["height"])
                media_width, media_height = (
                    _image_dimensions(destination) or (canvas_width, canvas_height)
                    if source_type == "image"
                    else (canvas_width, canvas_height)
                )
                entry = {
                    "id": material_id,
                    "type": "photo" if source_type == "image" else source_type,
                    "name": display_name,
                    "material_id": material_id,
                    "local_material_id": "",
                    "material_name": display_name,
                    "path": str(destination),
                    "media_path": "",
                    "content_hash": f"sha256:{digest}",
                    "duration": duration,
                    "width": media_width,
                    "height": media_height,
                    "category_id": "",
                    "category_name": "local",
                    "check_flag": 63487,
                    "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
                    "crop_ratio": "free", "crop_scale": 1.0,
                    "audio_fade": None, "remote_url": None,
                    "has_audio": source_type == "video",
                }
                if identity is not None:
                    entry.update({
                        "provider": identity["provider"],
                        "resource_id": identity["resource_id"] or identity["id"],
                        "category_id": str(identity["category"].get("id") or ""),
                        "category_name": str(identity["category"].get("name") or ""),
                    })
                    if identity["kind"] == "music":
                        entry["music_id"] = identity["id"]
                materials["videos" if source_type in {"video", "image"} else "audios"].append(entry)
            position = item.get("position") if isinstance(item.get("position"), dict) else {}
            clip_scale = float(item.get("scale", 1.0))
            if source_type == "image" and item.get("fit") == "cover":
                clip_scale *= _cover_scale(entry["width"], entry["height"], int(project.data["canvas"]["width"]), int(project.data["canvas"]["height"]))
            segment = {"id": segment_id, "material_id": material_id, "raw_segment_id": track["id"], "target_timerange": {"start": start, "duration": duration}, "source_timerange": {"start": 0, "duration": duration}, "speed": 1.0, "volume": item.get("volume", 1.0), "visible": True, "reverse": False, "clip": _clip(alpha=float(item.get("alpha", 1.0)), scale=clip_scale, x=float(position.get("x", 0.0)), y=float(position.get("y", 0.0))), "uniform_scale": {"on": True, "value": clip_scale}, "extra_material_refs": [], "common_keyframes": [], "keyframe_refs": [], "render_index": int(item.get("renderIndex", 0)), "track_render_index": int(item.get("renderIndex", 0)), "track_attribute": 0}
            track["segments"].append(segment)
            if item.get("ref"):
                refs[item["ref"]] = (segment, materials["texts"][-1] if source_type == "text" else entry, start, duration)
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
        resource_uses.append({
            "resource": operation["resource"],
            "usage": kind,
            "target": operation["target"],
        })
        category = resource.get("category") if isinstance(resource.get("category"), dict) else {}
        metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
        if kind in {"effect", "filter", "body-effect"}:
            materials["video_effects"].append({
                "id": material_id,
                "type": "filter" if kind == "filter" else "video_effect",
                "name": resource.get("name", operation["resource"]),
                "resource_id": resource_id,
                "effect_id": effect_id,
                "apply_target_type": 2 if kind == "body-effect" else 0,
                "bind_segment_id": "" if kind == "body-effect" else target_segment["id"],
                "source_platform": 1,
                "value": operation.get("intensity", 1.0),
                "adjust_params": [], "apply_time_range": None,
                "category_id": str(category.get("id") or ""),
                "category_name": str(category.get("name") or ""),
                "common_keyframes": [],
                "disable_effect_faces": [], "formula_id": "", "platform": "all",
                "render_index": 11000, "time_range": None,
                "track_render_index": 0, "version": "",
            })
            effect_track_id = _id()
            tracks.append({"id": effect_track_id, "type": "effect" if kind == "body-effect" else kind, "name": "Filters" if kind == "filter" else "Effects", "is_default_name": True, "attribute": 0, "flag": 0, "segments": [{"id": effect_segment_id, "material_id": material_id, "raw_segment_id": effect_track_id, "target_timerange": {"start": start, "duration": duration}, "source_timerange": {"start": 0, "duration": duration}, "speed": 1.0, "volume": 1.0, "visible": True, "reverse": False, "extra_material_refs": [], "common_keyframes": [], "keyframe_refs": [], "render_index": 0, "track_render_index": 0, "track_attribute": 0}]})
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
                "category_id": str(category.get("id") or ""),
                "category_name": str(category.get("name") or ""),
            })
            target_segment["extra_material_refs"].append(material_id)
        elif kind == "caption-template":
            if target_material.get("type") != "text":
                raise ProjectError("caption-template operations require a text target")
            target_material["effect_id"] = effect_id
            target_material["effect_resource_id"] = resource_id
            target_material["effect_category_id"] = str(category.get("id") or "")
        elif kind in {"animation", "text-animation"}:
            is_text = target_material.get("type") == "text"
            if kind == "text-animation" and not is_text:
                raise ProjectError("text-animation operations require a text target")
            if kind == "animation" and target_material.get("type") not in {"photo", "video"}:
                raise ProjectError("animation operations require an image or video target")
            animation_type = operation.get("animationType") or metadata.get("animation_type") or ("loop" if is_text else "group")
            allowed = {"in", "out", "loop"} if is_text else {"in", "out", "group"}
            if animation_type not in allowed:
                raise ProjectError(f"{kind} does not support animationType {animation_type!r}")
            animation_duration = min(duration, round(float(operation.get("duration", duration / US)) * US))
            animation_start = round(float(operation.get("start", 0)) * US)
            if animation_type == "out" and "start" not in operation:
                animation_start = duration - animation_duration
            if animation_start + animation_duration > duration:
                raise ProjectError("animation range exceeds its target segment")
            materials["material_animations"].append({
                "id": material_id,
                "type": "sticker_animation",
                "multi_language_current": "none",
                "animations": [{
                    "anim_adjust_params": None,
                    "platform": "all",
                    "panel": "" if is_text else "video",
                    "material_type": "sticker" if is_text else "video",
                    "name": resource.get("name", operation["resource"]),
                    "id": effect_id,
                    "type": animation_type,
                    "resource_id": resource_id,
                    "start": animation_start,
                    "duration": animation_duration,
                }],
            })
            target_segment["extra_material_refs"].append(material_id)
        elif kind == "audio-effect":
            if target_material.get("type") != "audio":
                raise ProjectError("audio-effect operations require an audio target")
            materials["audio_effects"].append({
                "audio_adjust_params": resource.get("audio_adjust_params", []),
                "category_id": str(resource.get("audio_category_id") or "sound_effect"),
                "category_name": str(resource.get("audio_category_name") or "Scene effect"),
                "id": material_id,
                "is_ugc": False,
                "name": resource.get("name", operation["resource"]),
                "production_path": "",
                "resource_id": resource_id,
                "speaker_id": "",
                "sub_type": int(resource.get("audio_sub_type", 1)),
                "time_range": {"duration": 0, "start": 0},
                "type": "audio_effect",
            })
            target_segment["extra_material_refs"].append(material_id)
        elif kind == "font":
            if target_material.get("type") != "text":
                raise ProjectError("font operations require a text target")
            content = json.loads(target_material["content"])
            if not content.get("styles"):
                content["styles"] = [{"range": [0, len(content.get("text", ""))]}]
            content["styles"][0]["font"] = {
                "id": resource_id,
                "resource_id": resource_id,
                "path": f"##_material_placeholder_{resource_id}_##",
            }
            target_material["content"] = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            target_material["font_id"] = resource_id
            target_material["font_name"] = resource.get("name", operation["resource"])
        elif kind == "text-effect":
            if target_material.get("type") != "text":
                raise ProjectError("text-effect operations require a text target")
            materials["effects"].append({
                "apply_target_type": 0,
                "effect_id": effect_id,
                "id": material_id,
                "resource_id": resource_id,
                "source_platform": 1,
                "type": "text_effect",
                "value": float(operation.get("intensity", 1.0)),
            })
            content = json.loads(target_material["content"])
            if not content.get("styles"):
                content["styles"] = [{"range": [0, len(content.get("text", ""))]}]
            content["styles"][0]["effectStyle"] = {
                "id": effect_id,
                "resource_id": resource_id,
                "path": f"##_material_placeholder_{resource_id}_##",
            }
            target_material["content"] = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            target_segment["extra_material_refs"].append(material_id)
        elif kind == "mask":
            if target_material.get("type") not in {"photo", "video"}:
                raise ProjectError("mask operations require an image or video target")
            width = float(operation.get("width", 1.0))
            height = float(operation.get("height", 1.0))
            materials["common_mask"].append({
                "config": {
                    "aspectRatio": float(operation.get("aspectRatio", width / height)),
                    "centerX": float(operation.get("centerX", 0.0)),
                    "centerY": float(operation.get("centerY", 0.0)),
                    "feather": float(operation.get("feather", 0.0)),
                    "height": height,
                    "invert": bool(operation.get("invert", False)),
                    "rotation": float(operation.get("rotation", 0.0)),
                    "roundCorner": float(operation.get("roundCorner", 0.0)),
                    "width": width,
                },
                "id": material_id,
                "name": resource.get("name", operation["resource"]),
                "platform": "all",
                "position_info": "",
                "resource_type": str(operation.get("resourceType") or metadata.get("resource_type") or resource.get("resource_type") or "mask"),
                "resource_id": resource_id,
                "type": "mask",
            })
            target_segment["extra_material_refs"].append(material_id)
        elif kind == "sticker":
            position = operation.get("position") if isinstance(operation.get("position"), dict) else {}
            scale = float(operation.get("scale", 1.0))
            sticker_track_id = _id()
            materials["stickers"].append({
                "id": material_id,
                "unique_id": "",
                "type": "sticker",
                "sticker_id": resource_id,
                "resource_id": resource_id,
                "name": resource.get("name", operation["resource"]),
                "category_id": str(category.get("id") or ""),
                "category_name": str(category.get("name") or ""),
                "platform": "all",
                "unicode": "",
                "source_platform": 1,
                "formula_id": "",
                "check_flag": 1,
                "team_id": "",
                "request_id": "",
                "combo_info": {"text_templates": []},
                "sub_type": 0,
                "radius": {"top_left": 0.0, "top_right": 0.0, "bottom_left": 0.0, "bottom_right": 0.0},
                "global_alpha": float(operation.get("alpha", 1.0)),
                "background_color": "",
                "background_alpha": 1.0,
                "border_line_style": 0,
                "border_width": 0.0,
                "border_color": "",
                "has_shadow": False,
                "shadow_color": "",
                "shadow_alpha": 0.8,
                "shadow_smoothing": 0.0,
                "shadow_distance": 0.0,
                "shadow_point": {"x": 0.0, "y": 0.0},
                "shadow_angle": 0.0,
                "shape_param": {"shape_type": 0, "roundness": [], "custom_points": [], "shape_size": []},
                "original_size": [],
                "update_params": "",
                "aigc_type": "none",
                "sequence_type": False,
                "cycle_setting": True,
                "multi_language_current": "none",
                "corner_pin": None,
            })
            tracks.append({
                "id": sticker_track_id,
                "type": "sticker",
                "name": "Stickers",
                "is_default_name": True,
                "attribute": 0,
                "flag": 0,
                "segments": [{
                    "id": effect_segment_id,
                    "material_id": material_id,
                    "raw_segment_id": sticker_track_id,
                    "target_timerange": {"start": start, "duration": duration},
                    "source_timerange": None,
                    "speed": 1.0,
                    "volume": 1.0,
                    "visible": True,
                    "reverse": False,
                    "clip": _clip(alpha=float(operation.get("alpha", 1.0)), scale=scale, x=float(position.get("x", 0.0)), y=float(position.get("y", 0.0))),
                    "uniform_scale": {"on": True, "value": scale},
                    "extra_material_refs": [],
                    "common_keyframes": [],
                    "keyframe_refs": [],
                    "render_index": int(operation.get("renderIndex", 14000)),
                    "track_render_index": 0,
                    "track_attribute": 0,
                }],
            })
        else:
            raise ProjectError(f"Unsupported operation type: {kind}")

    canvas = project.data["canvas"]
    draft_id = _id()
    now_us = int(time.time() * US)
    platform = {"app_source": "cc", "os": target_os, "os_version": "", "app_id": 359289, "app_version": target_version}
    draft = {
        "id": draft_id, "version": 360000, "new_version": "179.0.0",
        "name": project.name, "duration": duration_us,
        "create_time": now_us, "update_time": now_us, "fps": canvas["fps"],
        "is_drop_frame_timecode": False, "color_space": -1, "config": _config(),
        "canvas_config": {"width": canvas["width"], "height": canvas["height"], "ratio": canvas.get("ratio", ""), "background": None},
        "tracks": tracks, "group_container": None, "materials": materials,
        "keyframes": _keyframes(), "keyframe_graph_list": [], "platform": platform,
        "last_modified_platform": platform, "mutable_config": None, "cover": None,
        "retouch_cover": None, "extra_info": None, "relationships": [],
        "mixed_track_mode_on": False, "render_index_track_mode_on": False,
        "free_render_index_mode_on": False, "static_cover_image_path": "",
        "source": "", "time_marks": None, "path": str(out),
        "lyrics_effects": [], "uneven_animation_template_info": {},
        "draft_type": "video", "smart_ads_info": {}, "function_assistant_info": {},
    }
    out.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(draft, ensure_ascii=False, separators=(",", ":"))
    (out / "draft_content.json").write_text(encoded, encoding="utf-8")
    (out / "draft_info.json").write_text(encoded, encoding="utf-8")
    timeline_id = _id()
    timeline_dir = out / "Timelines" / timeline_id
    timeline_dir.mkdir(parents=True)
    timeline_draft = dict(draft)
    timeline_draft["id"] = timeline_id
    timeline_encoded = json.dumps(timeline_draft, ensure_ascii=False, separators=(",", ":"))
    (timeline_dir / "draft_info.json").write_text(timeline_encoded, encoding="utf-8")
    (timeline_dir / "draft_info.json.bak").write_text(timeline_encoded, encoding="utf-8")
    project_index = {"config": {}, "create_time": now_us, "id": draft_id, "main_timeline_id": timeline_id, "timelines": [{"create_time": now_us, "id": timeline_id, "is_marked_delete": False, "name": project.name, "update_time": now_us}], "update_time": now_us, "version": 0}
    project_encoded = json.dumps(project_index, ensure_ascii=False, separators=(",", ":"))
    (out / "Timelines" / "project.json").write_text(project_encoded, encoding="utf-8")
    (out / "Timelines" / "project.json.bak").write_text(project_encoded, encoding="utf-8")
    metadata = {"draft_fold_path": str(out), "draft_id": draft_id, "draft_name": project.name, "draft_new_version": "179.0.0", "draft_root_path": str(out.parent), "tm_draft_create": now_us, "tm_draft_modified": now_us, "tm_draft_removed": 0, "tm_duration": duration_us, "draft_materials": [], "draft_materials_copied_info": [], "draft_segment_extra_info": [], "draft_is_invisible": False, "draft_need_rename_folder": False, "draft_cover": "draft_cover.jpg"}
    (out / "draft_meta_info.json").write_text(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "attachment_pc_common.json").write_text('{"ai_packaging_infos":[],"ai_packaging_report_info":{},"broll":[],"commercial_music_category_ids":[],"pc_feature_flag":{},"recognize_tasks":[],"reference_lines_config":{},"safe_area_type":0,"template_item_infos":[],"unlock_template_ids":[]}', encoding="utf-8")
    (out / "performance_opt_info.json").write_text('{"manual_cancle_precombine_segs":[],"need_auto_precombine_segs":[]}', encoding="utf-8")
    used_keys = list(dict.fromkeys(use["resource"] for use in resource_uses))
    build_manifest = {
        "version": 1,
        "project": project.name,
        "draft_id": draft_id,
        "resources": {key: _catalog_identity(resources[key]) for key in used_keys},
        "uses": resource_uses,
    }
    (out / "clipcraft_build.json").write_text(
        json.dumps(build_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return BuildResult(out, len(tracks), sum(len(track["segments"]) for track in tracks), duration_us)
