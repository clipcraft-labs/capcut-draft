"""Compile Clipcraft Project data into a minimal CapCut Desktop draft."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import time
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


def _clip() -> dict[str, Any]:
    return {
        "alpha": 1.0,
        "flip": {"horizontal": False, "vertical": False},
        "rotation": 0.0,
        "scale": {"x": 1.0, "y": 1.0},
        "transform": {"x": 0.0, "y": 0.0},
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
        track = {"id": _id(), "type": source_track["type"], "name": source_track.get("name", ""), "is_default_name": True, "attribute": 0, "flag": 0, "segments": []}
        for item in source_track["items"]:
            material_id = _id()
            start = round(float(item["at"]) * US)
            duration = round(float(item["duration"]) * US)
            segment_id = _id()
            if source_track["type"] == "text":
                content = json.dumps({"text": item["text"], "styles": []}, ensure_ascii=False, separators=(",", ":"))
                materials["texts"].append({"id": material_id, "type": "text", "content": content, "font_size": item.get("fontSize", 15), "text_color": item.get("color", "#FFFFFF"), "alignment": 1, "background_alpha": 0.0, "background_color": "", "bold_width": 0.0, "border_width": 0.0, "check_flag": 15, "font_id": "", "font_name": "", "has_shadow": False, "italic_degree": 0, "letter_spacing": 0, "line_spacing": 0.02, "name": "", "recognize_type": 0, "shadow_alpha": 0.0, "text_alpha": 1.0, "text_size": 15, "underline": False})
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
                    "material_id": material_id,
                    "local_material_id": "",
                    "material_name": display_name,
                    "path": str(destination),
                    "media_path": "",
                    "content_hash": f"sha256:{digest}",
                    "duration": duration,
                    "width": int(project.data["canvas"]["width"]),
                    "height": int(project.data["canvas"]["height"]),
                    "category_id": "",
                    "category_name": "local",
                    "check_flag": 63487,
                    "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
                    "crop_ratio": "free", "crop_scale": 1.0,
                    "audio_fade": None, "remote_url": None,
                }
                materials["videos" if source_track["type"] == "video" else "audios"].append(entry)
            segment = {"id": segment_id, "material_id": material_id, "raw_segment_id": track["id"], "target_timerange": {"start": start, "duration": duration}, "source_timerange": {"start": 0, "duration": duration}, "speed": 1.0, "volume": 1.0, "visible": True, "reverse": False, "clip": _clip(), "uniform_scale": {"on": True, "value": 1.0}, "extra_material_refs": [], "common_keyframes": [], "keyframe_refs": [], "render_index": 0, "track_render_index": 0, "track_attribute": 0}
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
                "adjust_params": [], "apply_time_range": None,
                "category_id": "", "category_name": "", "common_keyframes": [],
                "disable_effect_faces": [], "formula_id": "", "platform": "all",
                "render_index": 11000, "time_range": None,
                "track_render_index": 0, "version": "",
            })
            effect_track_id = _id()
            tracks.append({"id": effect_track_id, "type": kind, "name": "Filters" if kind == "filter" else "Effects", "is_default_name": True, "attribute": 0, "flag": 0, "segments": [{"id": effect_segment_id, "material_id": material_id, "raw_segment_id": effect_track_id, "target_timerange": {"start": start, "duration": duration}, "source_timerange": {"start": 0, "duration": duration}, "speed": 1.0, "volume": 1.0, "visible": True, "reverse": False, "extra_material_refs": [], "common_keyframes": [], "keyframe_refs": [], "render_index": 0, "track_render_index": 0, "track_attribute": 0}]})
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
    draft_id = _id()
    now_us = int(time.time() * US)
    platform = {"app_source": "cc", "os": target.get("os", "mac"), "os_version": "", "app_id": 359289, "app_version": target.get("version", "9.1.0") or "9.1.0"}
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
    return BuildResult(out, len(tracks), sum(len(track["segments"]) for track in tracks), duration_us)
