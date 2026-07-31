import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capcut_draft import ProjectError, compile_project, load_project
from capcut_draft.validator import validate_draft
from capcut_draft.desktop import apply_registration, open_desktop, plan_registration
from capcut_draft.assets import AssetStore


class DraftTests(unittest.TestCase):
    def test_text_project_compiles_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "name": "Synthetic", "canvas": {"width": 1080, "height": 1920, "fps": 30}, "tracks": [{"type": "text", "items": [{"text": "hello", "at": 0, "duration": 2, "ref": "title"}]}], "operations": []}), encoding="utf-8")
            result = compile_project(load_project(project_path), root / "build")
            self.assertEqual((result.tracks, result.segments, result.duration_us), (1, 1, 2_000_000))
            self.assertEqual(validate_draft(result.output)["materials"], 1)
            draft = json.loads((result.output / "draft_info.json").read_text(encoding="utf-8"))
            self.assertEqual((draft["version"], draft["new_version"]), (360000, "179.0.0"))
            self.assertEqual(draft["platform"]["app_version"], "9.1.0")
            project = json.loads((result.output / "Timelines" / "project.json").read_text(encoding="utf-8"))
            timeline = result.output / "Timelines" / project["main_timeline_id"] / "draft_info.json"
            self.assertTrue(timeline.is_file())
            self.assertEqual(json.loads(timeline.read_text(encoding="utf-8"))["tracks"][0]["type"], "text")

    def test_locked_effect_compiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "name": "Synthetic", "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "text", "items": [{"text": "hello", "at": 0, "duration": 1, "ref": "title"}]}], "operations": [{"type": "effect", "target": "title", "resource": "effect"}]}), encoding="utf-8")
            lock = root / "clipcraft.lock"
            lock.write_text(json.dumps({"version": 1, "resources": {"effect": {"provider": "capcut", "kind": "effect", "name": "Synthetic", "resource_id": "resource", "effect_id": "effect"}}}), encoding="utf-8")
            result = compile_project(load_project(project_path), root / "build", lock_path=lock)
            self.assertEqual(result.tracks, 2)
            self.assertEqual(validate_draft(result.output)["materials"], 2)

    def test_locked_decorators_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "name": "Synthetic", "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "text", "items": [{"text": "hello", "at": 0, "duration": 1, "ref": "title"}]}], "operations": [{"type": "filter", "target": "title", "resource": "filter"}, {"type": "transition", "target": "title", "resource": "transition", "duration": 0.25}, {"type": "caption-template", "target": "title", "resource": "caption"}]}), encoding="utf-8")
            lock = root / "clipcraft.lock"
            lock.write_text(json.dumps({"version": 1, "resources": {name: {"provider": "capcut", "kind": name, "name": name, "resource_id": name, "effect_id": name, "category": {"panel": f"{name}-panel", "id": f"{name}-category", "key": "hot"}} for name in ("filter", "transition", "caption")}}), encoding="utf-8")
            result = compile_project(load_project(project_path), root / "build", lock_path=lock)
            draft = json.loads((result.output / "draft_content.json").read_text(encoding="utf-8"))
            self.assertEqual(draft["materials"]["video_effects"][0]["type"], "filter")
            self.assertEqual(draft["materials"]["video_effects"][0]["category_id"], "filter-category")
            self.assertEqual(draft["materials"]["transitions"][0]["duration"], 250_000)
            self.assertEqual(draft["materials"]["transitions"][0]["category_id"], "transition-category")
            self.assertEqual(draft["materials"]["texts"][0]["effect_resource_id"], "caption")
            self.assertEqual(draft["materials"]["texts"][0]["effect_category_id"], "caption-category")
            manifest = json.loads((result.output / "clipcraft_build.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["resources"]["caption"]["category"]["panel"], "caption-panel")
            self.assertEqual([use["resource"] for use in manifest["uses"]], ["filter", "transition", "caption"])
            self.assertEqual(validate_draft(result.output)["materials"], 3)

    def test_registration_is_plan_first_and_backed_up(self):
        with tempfile.TemporaryDirectory() as directory:
            drafts = Path(directory)
            draft_dir = drafts / "Synthetic"
            draft_dir.mkdir()
            value = {"id": "draft-id", "name": "Synthetic", "duration": 1, "materials": {}, "tracks": []}
            (draft_dir / "draft_content.json").write_text(json.dumps(value), encoding="utf-8")
            plan = plan_registration(draft_dir, drafts)
            self.assertEqual(plan.action, "create")
            result = apply_registration(plan)
            self.assertTrue(result["registered"])
            second = plan_registration(draft_dir, drafts)
            self.assertEqual(second.action, "update")
            apply_registration(second)
            self.assertTrue((drafts / "root_meta_info.json.bak").is_file())

    def test_registration_rebases_copied_draft_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            drafts = Path(directory)
            draft_dir = drafts / "Registered"
            asset = draft_dir / "assets" / "image" / "screen.png"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"synthetic image")
            old_root = Path("/tmp/clipcraft-build")
            value = {
                "id": "draft-id",
                "name": "Registered",
                "duration": 1,
                "path": str(old_root),
                "materials": {
                    "videos": [{"id": "material-id", "path": str(old_root / "assets" / "image" / "screen.png")}]
                },
                "tracks": [],
            }
            content = draft_dir / "draft_content.json"
            content.write_text(json.dumps(value), encoding="utf-8")
            result = apply_registration(plan_registration(draft_dir, drafts))
            registered = json.loads(content.read_text(encoding="utf-8"))
            self.assertEqual(result["rebased_files"], 1)
            self.assertEqual(registered["path"], str(draft_dir.resolve()))
            self.assertEqual(registered["materials"]["videos"][0]["path"], str(asset.resolve()))
            self.assertTrue((draft_dir / "draft_content.json.clipcraft.bak").is_file())

    def test_open_desktop_launches_capcut(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = Path(directory)
            (draft / "draft_content.json").write_text("{}", encoding="utf-8")
            with patch("capcut_draft.desktop.sys.platform", "darwin"), patch(
                "capcut_draft.desktop.subprocess.Popen"
            ) as launch:
                result = open_desktop(draft)
            self.assertEqual(result["status"], "launched")
            launch.assert_called_once()

    def test_rejects_missing_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "video", "items": [{"src": "missing.mp4", "at": 0, "duration": 1}]}]}), encoding="utf-8")
            with self.assertRaises(ProjectError):
                compile_project(load_project(project_path), root / "build")

    def test_locked_content_addressed_audio_compiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = AssetStore(root / "store")
            stored = store.put(b"synthetic audio", suffix="m4a")
            lock = root / "clipcraft.lock"
            lock.write_text(json.dumps({"version": 1, "resources": {"music": {"provider": "capcut", "kind": "music", "id": "catalog-song-id", "name": "Synthetic", "commercial": True, "asset_hash": stored.digest}}}), encoding="utf-8")
            project = root / "project.json"
            project.write_text(json.dumps({"version": 1, "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "audio", "items": [{"resource": "music", "at": 0, "duration": 1}]}]}), encoding="utf-8")
            result = compile_project(load_project(project), root / "build", lock_path=lock, asset_store=store.root)
            draft = json.loads((result.output / "draft_content.json").read_text(encoding="utf-8"))
            material = draft["materials"]["audios"][0]
            self.assertEqual(material["content_hash"], f"sha256:{stored.digest}")
            self.assertEqual(material["music_id"], "catalog-song-id")
            self.assertEqual(material["resource_id"], "catalog-song-id")
            self.assertTrue(Path(material["path"]).is_file())
            manifest = json.loads((result.output / "clipcraft_build.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["resources"]["music"]["id"], "catalog-song-id")
            self.assertTrue(manifest["resources"]["music"]["commercial"])

    def test_rejects_unverified_target_without_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "target": {"app": "capcut", "version": "10.0.0", "os": "mac"}, "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "text", "items": [{"text": "hello", "at": 0, "duration": 1}]}]}), encoding="utf-8")
            project = load_project(project_path)
            with self.assertRaises(ProjectError):
                compile_project(project, root / "rejected")
            result = compile_project(project, root / "allowed", allow_unsupported_version=True)
            draft = json.loads((result.output / "draft_content.json").read_text(encoding="utf-8"))
            self.assertEqual(draft["platform"]["app_version"], "10.0.0")

    def test_still_image_compiles_as_photo_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "screen.png"
            image.write_bytes(b"synthetic png bytes")
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "canvas": {"width": 1080, "height": 1920, "fps": 30}, "tracks": [{"type": "image", "items": [{"src": "screen.png", "at": 0, "duration": 2, "ref": "screen"}]}]}), encoding="utf-8")
            result = compile_project(load_project(project_path), root / "build")
            draft = json.loads((result.output / "draft_content.json").read_text(encoding="utf-8"))
            self.assertEqual(draft["tracks"][0]["type"], "video")
            self.assertEqual(draft["materials"]["videos"][0]["type"], "photo")
            self.assertFalse(draft["materials"]["videos"][0]["has_audio"])
            validation = validate_draft(result.output)
            self.assertEqual(validation["media_files"], 1)
            self.assertEqual(validation["external_media_files"], 0)

    def test_validation_rejects_missing_and_modified_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "screen.png"
            image.write_bytes(b"synthetic png bytes")
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "image", "items": [{"src": "screen.png", "at": 0, "duration": 1}]}]}), encoding="utf-8")
            first = compile_project(load_project(project_path), root / "first")
            first_draft = json.loads((first.output / "draft_content.json").read_text(encoding="utf-8"))
            first_media = Path(first_draft["materials"]["videos"][0]["path"])
            first_media.unlink()
            with self.assertRaisesRegex(ProjectError, "media file is missing"):
                validate_draft(first.output)

            second = compile_project(load_project(project_path), root / "second")
            second_draft = json.loads((second.output / "draft_content.json").read_text(encoding="utf-8"))
            second_media = Path(second_draft["materials"]["videos"][0]["path"])
            second_media.write_bytes(b"modified")
            with self.assertRaisesRegex(ProjectError, "media hash does not match"):
                validate_draft(second.output)
