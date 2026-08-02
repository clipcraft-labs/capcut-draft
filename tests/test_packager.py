import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from capcut_draft.packager import PackageError, package_draft, render_preflight


class PackageDraftTests(unittest.TestCase):
    def test_packages_resources_and_rewrites_draft_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            (draft / "assets").mkdir()
            (draft / "assets" / "clip.mp4").write_bytes(b"video")
            resource = root / "download" / "effect-package"
            resource.mkdir(parents=True)
            (resource / "config.json").write_text("{}", encoding="utf-8")
            timeline = {
                "materials": {
                    "videos": [{"id": "v", "path": "##_draftpath_placeholder_media_##/assets/clip.mp4"}],
                    "effects": [{
                        "id": "fx",
                        "name": "effect",
                        "resource_id": "123456789",
                        "path": "##_material_placeholder_x_##",
                    }],
                    "drafts": [{"id": "d", "path": "##_draftpath_placeholder_x_##"}],
                }
            }
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")
            output = root / "package"

            result = package_draft(draft, output, overrides={"123456789": resource})
            packaged = json.loads((output / "draft_content.json").read_text(encoding="utf-8"))
            effect_path = Path(packaged["materials"]["effects"][0]["path"])

            self.assertEqual(result.output, output.resolve())
            self.assertTrue(effect_path.is_dir())
            self.assertTrue(str(effect_path).startswith(str(output.resolve())))
            self.assertEqual(packaged["materials"]["videos"][0]["path"], str(output.resolve() / "assets" / "clip.mp4"))
            self.assertEqual(packaged["materials"]["drafts"][0]["path"], str(output.resolve()))
            self.assertTrue((output / "clipcraft_resources.json").is_file())

    def test_synchronizes_and_preflights_timeline_mirrors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            timeline_dir = draft / "Timelines" / "timeline-1"
            timeline_dir.mkdir(parents=True)
            (draft / "assets").mkdir()
            (draft / "assets" / "clip.mp4").write_bytes(b"video")
            authoritative = {
                "duration": 1000000,
                "path": str(draft),
                "materials": {"videos": [{
                    "id": "video",
                    "path": str(draft / "assets" / "clip.mp4"),
                }]},
            }
            stale = {"materials": {"effects": [{
                "resource_id": "999999999",
                "path": "##_material_placeholder_stale_##",
            }]}}
            (draft / "draft_info.json").write_text(json.dumps(authoritative), encoding="utf-8")
            (timeline_dir / "draft_info.json").write_text(json.dumps(stale), encoding="utf-8")
            (timeline_dir / "template-2.tmp").write_text(json.dumps(stale), encoding="utf-8")

            output = root / "package"
            package_draft(draft, output, source_json=Path("draft_info.json"))

            root_bytes = (output / "draft_info.json").read_bytes()
            self.assertEqual((output / "Timelines" / "timeline-1" / "draft_info.json").read_bytes(), root_bytes)
            self.assertEqual((output / "Timelines" / "timeline-1" / "template-2.tmp").read_bytes(), root_bytes)
            result = render_preflight(output)
            self.assertGreaterEqual(result["checked_paths"], 3)
            packaged = json.loads((output / "draft_info.json").read_text(encoding="utf-8"))
            self.assertEqual(packaged["path"], str(output.resolve()))

    def test_refuses_unresolved_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            timeline = {"materials": {"effects": [{
                "resource_id": "987654321",
                "path": "##_material_placeholder_x_##",
            }]}}
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")
            with self.assertRaises(PackageError):
                package_draft(draft, root / "package", roots=[])

    def test_hydrates_sdk_extra_and_recursive_dependency_from_any_cache_category(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            cache = root / "Cache" / "AITextTemplate"
            main = cache / "111111111" / "main-hash"
            dependency = cache / "222222222" / "dependency-hash"
            main.mkdir(parents=True)
            dependency.mkdir(parents=True)
            (main / "config.json").write_text(json.dumps({
                "depend_resource_list": [{"resource_id": "222222222"}]
            }), encoding="utf-8")
            (dependency / "content.json").write_text("{}", encoding="utf-8")
            sdk_extra = json.dumps({
                "caption": {
                    "resource_id": "111111111",
                    "path": "##_material_placeholder_caption_##",
                }
            })
            timeline = {"materials": {"text_templates": [{
                "id": "caption",
                "path": "",
                "sdk_extra": sdk_extra,
            }]}}
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")

            output = root / "package"
            result = package_draft(draft, output, roots=[cache])
            packaged = json.loads((output / "draft_info.json").read_text(encoding="utf-8"))
            embedded = json.loads(packaged["materials"]["text_templates"][0]["sdk_extra"])

            self.assertTrue(Path(embedded["caption"]["path"]).exists())
            self.assertEqual({item.resource_id for item in result.resources}, {"111111111", "222222222"})
            self.assertTrue((output / "resources" / "artistEffect" / "111111111").is_dir())

    def test_downloads_and_verifies_resource_from_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            timeline = {"materials": {"effects": [{
                "resource_id": "333333333",
                "path": "##_material_placeholder_download_##",
            }]}}
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")
            archive = root / "effect.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("AmazingFeature/content.json", "{}")
            digest = hashlib.md5(archive.read_bytes()).hexdigest()
            lock = root / "clipcraft.lock"
            lock.write_text(json.dumps({
                "version": 1,
                "resources": {"effect": {
                    "resource_id": "333333333",
                    "download_url": archive.as_uri(),
                    "file_md5": digest,
                }},
            }), encoding="utf-8")

            output = root / "package"
            result = package_draft(draft, output, lock_path=lock)

            self.assertEqual(len(result.resources), 1)
            self.assertTrue(Path(result.resources[0].packaged_path, "AmazingFeature", "content.json").is_file())

    def test_hydrates_id_only_compiler_resource_from_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            timeline = {"materials": {"video_effects": [{
                "resource_id": "555555555",
                "effect_id": "555555555",
                "name": "ID-only effect",
            }]}}
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")
            archive = root / "effect.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("AmazingFeature/content.json", "{}")
            lock = root / "clipcraft.lock"
            lock.write_text(json.dumps({
                "version": 1,
                "resources": {"effect": {
                    "resource_id": "555555555",
                    "download_url": archive.as_uri(),
                    "file_md5": hashlib.md5(archive.read_bytes()).hexdigest(),
                }},
            }), encoding="utf-8")

            output = root / "package"
            package_draft(draft, output, lock_path=lock)
            packaged = json.loads((output / "draft_info.json").read_text(encoding="utf-8"))

            path = Path(packaged["materials"]["video_effects"][0]["path"])
            self.assertTrue(path.is_dir())
            self.assertTrue(str(path).startswith(str(output.resolve())))

    def test_resolves_font_resource_id_with_font_path_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            font = root / "font-package"
            font.mkdir()
            (font / "font.ttf").write_bytes(b"font")
            timeline = {"materials": {"texts": [{
                "id": "text",
                "font_resource_id": "444444444",
                "font_path": "##_material_placeholder_font_##",
            }]}}
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")

            output = root / "package"
            package_draft(draft, output, overrides={"444444444": font})
            packaged = json.loads((output / "draft_info.json").read_text(encoding="utf-8"))

            self.assertTrue(Path(packaged["materials"]["texts"][0]["font_path"]).is_dir())

    def test_hydrates_resources_inside_serialized_text_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            draft = root / "source"
            draft.mkdir()
            font = root / "font-package"
            font.mkdir()
            (font / "font.ttf").write_bytes(b"font")
            content = json.dumps({"text": "hello", "styles": [{"font": {
                "id": "666666666", "resource_id": "666666666",
                "path": "##_material_placeholder_666666666_##",
            }}]})
            timeline = {"materials": {"texts": [{"id": "text", "content": content}]}}
            (draft / "draft_info.json").write_text(json.dumps(timeline), encoding="utf-8")

            output = root / "package"
            result = package_draft(draft, output, overrides={"666666666": font})
            packaged = json.loads((output / "draft_info.json").read_text(encoding="utf-8"))
            hydrated = json.loads(packaged["materials"]["texts"][0]["content"])

            self.assertTrue(Path(hydrated["styles"][0]["font"]["path"]).is_dir())
            self.assertEqual({item.resource_id for item in result.resources}, {"666666666"})


if __name__ == "__main__":
    unittest.main()
