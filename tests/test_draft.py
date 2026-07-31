import json
from pathlib import Path
import tempfile
import unittest

from capcut_draft import ProjectError, compile_project, load_project
from capcut_draft.validator import validate_draft
from capcut_draft.desktop import apply_registration, plan_registration


class DraftTests(unittest.TestCase):
    def test_text_project_compiles_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "name": "Synthetic", "canvas": {"width": 1080, "height": 1920, "fps": 30}, "tracks": [{"type": "text", "items": [{"text": "hello", "at": 0, "duration": 2, "ref": "title"}]}], "operations": []}), encoding="utf-8")
            result = compile_project(load_project(project_path), root / "build")
            self.assertEqual((result.tracks, result.segments, result.duration_us), (1, 1, 2_000_000))
            self.assertEqual(validate_draft(result.output)["materials"], 1)

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
            lock.write_text(json.dumps({"version": 1, "resources": {name: {"provider": "capcut", "kind": name, "name": name, "resource_id": name, "effect_id": name} for name in ("filter", "transition", "caption")}}), encoding="utf-8")
            result = compile_project(load_project(project_path), root / "build", lock_path=lock)
            draft = json.loads((result.output / "draft_content.json").read_text(encoding="utf-8"))
            self.assertEqual(draft["materials"]["video_effects"][0]["type"], "filter")
            self.assertEqual(draft["materials"]["transitions"][0]["duration"], 250_000)
            self.assertEqual(draft["materials"]["texts"][0]["effect_resource_id"], "caption")
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

    def test_rejects_missing_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "video", "items": [{"src": "missing.mp4", "at": 0, "duration": 1}]}]}), encoding="utf-8")
            with self.assertRaises(ProjectError):
                compile_project(load_project(project_path), root / "build")
