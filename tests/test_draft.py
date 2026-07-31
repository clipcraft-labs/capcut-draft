import json
from pathlib import Path
import tempfile
import unittest

from capcut_draft import ProjectError, compile_project, load_project
from capcut_draft.validator import validate_draft


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

    def test_rejects_missing_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps({"version": 1, "canvas": {"width": 1, "height": 1, "fps": 1}, "tracks": [{"type": "video", "items": [{"src": "missing.mp4", "at": 0, "duration": 1}]}]}), encoding="utf-8")
            with self.assertRaises(ProjectError):
                compile_project(load_project(project_path), root / "build")

