"""Plan-first CapCut Desktop project registration."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

from .project import ProjectError


@dataclass(frozen=True, slots=True)
class RegistrationPlan:
    draft: str
    drafts_dir: str
    root_index: str
    project_metadata: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _rebase_value(value: Any, old_root: Path, new_root: Path) -> tuple[Any, bool]:
    if isinstance(value, dict):
        changed = False
        result: dict[str, Any] = {}
        for key, child in value.items():
            result[key], child_changed = _rebase_value(child, old_root, new_root)
            changed = changed or child_changed
        return result, changed
    if isinstance(value, list):
        changed = False
        result: list[Any] = []
        for child in value:
            rewritten, child_changed = _rebase_value(child, old_root, new_root)
            result.append(rewritten)
            changed = changed or child_changed
        return result, changed
    if isinstance(value, str) and value.startswith(str(old_root)):
        try:
            relative = Path(value).relative_to(old_root)
        except ValueError:
            return value, False
        candidate = new_root / relative
        if relative == Path(".") or candidate.exists():
            return str(candidate), True
    return value, False


def _rebase_draft_documents(draft_path: Path) -> int:
    documents = [draft_path / "draft_content.json", draft_path / "draft_info.json"]
    documents.extend((draft_path / "Timelines").glob("*/draft_info.json"))
    documents.extend((draft_path / "Timelines").glob("*/draft_info.json.bak"))
    changed_files = 0
    for document in documents:
        if not document.is_file():
            continue
        value = json.loads(document.read_text(encoding="utf-8"))
        recorded_root = value.get("path")
        if not isinstance(recorded_root, str) or not Path(recorded_root).is_absolute():
            continue
        old_root = Path(recorded_root)
        if old_root == draft_path:
            continue
        rewritten, changed = _rebase_value(value, old_root, draft_path)
        if not changed:
            continue
        backup = document.with_name(document.name + ".clipcraft.bak")
        if not backup.exists():
            shutil.copy2(document, backup)
        document.write_text(
            json.dumps(rewritten, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        changed_files += 1
    return changed_files


def plan_registration(draft: str | Path, drafts_dir: str | Path) -> RegistrationPlan:
    draft_path = Path(draft).resolve()
    drafts_path = Path(drafts_dir).resolve()
    if draft_path.parent != drafts_path:
        raise ProjectError("Draft must be a direct child of the Desktop drafts directory")
    timeline = draft_path / "draft_content.json"
    if not timeline.is_file():
        timeline = draft_path / "draft_info.json"
    if not timeline.is_file():
        raise ProjectError("Draft has no draft_content.json or draft_info.json")
    root_index = drafts_path / "root_meta_info.json"
    action = "update" if root_index.exists() else "create"
    return RegistrationPlan(
        str(draft_path),
        str(drafts_path),
        str(root_index),
        str(draft_path / "draft_meta_info.json"),
        action,
    )


def apply_registration(plan: RegistrationPlan) -> dict[str, Any]:
    draft_path = Path(plan.draft)
    root_index = Path(plan.root_index)
    rebased_files = _rebase_draft_documents(draft_path)
    timeline = draft_path / "draft_content.json"
    if not timeline.is_file():
        timeline = draft_path / "draft_info.json"
    draft = json.loads(timeline.read_text(encoding="utf-8"))
    identifier = str(draft.get("id") or "")
    if not identifier:
        raise ProjectError("Draft id is missing")
    now_us = int(time.time() * 1_000_000)
    entry = {
        "draft_fold_path": str(draft_path),
        "draft_id": identifier,
        "draft_json_file": str(timeline),
        "draft_name": str(draft.get("name") or draft_path.name),
        "draft_root_path": plan.drafts_dir,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": int(draft.get("duration") or 0),
    }
    root: dict[str, Any] = {"all_draft_store": []}
    if root_index.exists():
        root = json.loads(root_index.read_text(encoding="utf-8"))
        shutil.copy2(root_index, root_index.with_suffix(root_index.suffix + ".bak"))
    store_key = next(
        (key for key, value in root.items() if isinstance(value, list) and ("draft_store" in key or key == "all_draft_store")),
        "all_draft_store",
    )
    store = root.setdefault(store_key, [])
    if not isinstance(store, list):
        raise ProjectError("Desktop root project store is not an array")
    store[:] = [value for value in store if not isinstance(value, dict) or value.get("draft_id") != identifier]
    store.append(entry)
    root_index.write_text(json.dumps(root, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    metadata = Path(plan.project_metadata)
    if metadata.exists():
        shutil.copy2(metadata, metadata.with_suffix(metadata.suffix + ".bak"))
    metadata.write_text(json.dumps(entry, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {
        "registered": True,
        "draft_id": identifier,
        "backup": str(root_index) + ".bak" if plan.action == "update" else None,
        "rebased_files": rebased_files,
    }


def open_desktop(draft: str | Path, *, app: str = "CapCut") -> dict[str, str]:
    draft_path = Path(draft).resolve()
    if not (draft_path / "draft_content.json").is_file() and not (draft_path / "draft_info.json").is_file():
        raise ProjectError("Draft has no readable timeline file")
    if sys.platform == "darwin":
        command = ["open", "-a", app]
    elif sys.platform == "win32":
        command = ["cmd", "/c", "start", "", app]
    else:
        raise ProjectError("CapCut Desktop opening is supported on macOS and Windows")
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"draft": str(draft_path), "app": app, "status": "launched"}
