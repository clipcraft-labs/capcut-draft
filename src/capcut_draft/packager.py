"""Create self-contained CapCut draft packages from installed resources."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


MATERIAL_PLACEHOLDER = re.compile(r"^##_material_placeholder_[^#]+_##$")
DRAFT_PLACEHOLDER = re.compile(r"^##_draftpath_placeholder_[^#]+_##(?P<suffix>/.*)?$")
RESOURCE_ID = re.compile(r"^[0-9]{8,}$")
JSON_NAMES = ("draft_info.json", "draft_content.json", "template-2.tmp", "template.tmp")
PATH_KEYS = {
    "image", "album_image", "font_url", "resource_url", "video_path",
    "production_path", "algorithm_artifact_path", "aigc_current_artifact_path",
}


def _is_path_key(key: str) -> bool:
    return key == "path" or key.endswith("_path") or key in PATH_KEYS


class PackageError(RuntimeError):
    """Raised when a draft cannot be made self-contained."""


class UnresolvedResourceError(PackageError):
    """Structured failure used by orchestrators to fetch missing dependencies."""

    def __init__(self, unresolved: Iterable[str]):
        self.unresolved = tuple(sorted(set(unresolved)))
        self.dependency_ids = tuple(sorted({
            match.group(1)
            for item in self.unresolved
            if (match := re.match(r"dependency ([0-9]+) required by", item))
        }))
        super().__init__("unresolved CapCut resources:\n- " + "\n- ".join(self.unresolved))


@dataclass(frozen=True)
class PackagedResource:
    resource_id: str
    source: str
    packaged_path: str
    sha256: str
    references: int


@dataclass(frozen=True)
class PackageResult:
    output: Path
    source_json: Path
    resources: tuple[PackagedResource, ...]
    rewritten_paths: int


def default_resource_roots() -> list[Path]:
    home = Path.home()
    cache_bases = (
        home / "Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache",
        home / "Movies/CapCut/User Data/Cache",
        home / "AppData/Local/CapCut/User Data/Cache",
        home / "AppData/Roaming/CapCut/User Data/Cache",
    )
    roots: list[Path] = []
    for base in cache_bases:
        if base.is_dir():
            roots.extend(item for item in base.iterdir() if item.is_dir())
        else:
            roots.extend((base / "effect", base / "artistEffect"))
    return roots


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode())
        with item.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise PackageError(f"unsafe archive member: {member.filename}")
        bundle.extractall(destination)


def _lock_overrides(lock_path: Path | None, download_root: Path, roots: Iterable[Path] = ()) -> dict[str, Path]:
    if lock_path is None:
        return {}
    lock = _load_json(lock_path.expanduser().resolve())
    if lock.get("version") != 1 or not isinstance(lock.get("resources"), dict):
        raise PackageError("resource lock must contain version 1 and a resources object")
    resolved: dict[str, Path] = {}
    installed = ResourceResolver(roots=roots)
    for name, record in lock["resources"].items():
        if not isinstance(record, dict):
            raise PackageError(f"invalid lock resource: {name}")
        rid = str(record.get("resource_id") or record.get("id") or "")
        if not rid:
            continue
        local = record.get("local_path") or record.get("path")
        if local and Path(str(local)).expanduser().exists():
            resolved[rid] = Path(str(local)).expanduser().resolve()
            continue
        installed_path = installed.resolve(rid)
        if installed_path is not None:
            resolved[rid] = installed_path
            continue
        url = record.get("download_url")
        if not url:
            continue
        # Keep provider bundles beside the lock rather than in package_draft's
        # temporary directory. Signed CapCut URLs expire; a verified archive
        # must therefore remain usable for later offline/reproducible builds.
        expected_md5 = str(record.get("file_md5") or record.get("md5") or "").lower()
        cache_key = expected_md5 or "unversioned"
        resource_root = download_root / rid / cache_key
        resource_root.mkdir(parents=True, exist_ok=True)
        archive = resource_root / "resource.download"
        cached = archive.is_file()
        if cached and expected_md5:
            cached = hashlib.md5(archive.read_bytes()).hexdigest() == expected_md5
        if not cached:
            temporary_archive = resource_root / "resource.download.part"
            try:
                with urllib.request.urlopen(str(url), timeout=60) as response, temporary_archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
            except OSError as exc:
                temporary_archive.unlink(missing_ok=True)
                raise PackageError(f"unable to download locked resource {rid}: {exc}") from exc
            if expected_md5:
                actual_md5 = hashlib.md5(temporary_archive.read_bytes()).hexdigest()
                if actual_md5 != expected_md5:
                    temporary_archive.unlink(missing_ok=True)
                    raise PackageError(f"MD5 mismatch for locked resource {rid}: {actual_md5} != {expected_md5}")
            temporary_archive.replace(archive)
        if zipfile.is_zipfile(archive):
            extracted = resource_root / "extracted"
            if not extracted.is_dir():
                temporary_extracted = resource_root / "extracted.part"
                if temporary_extracted.exists():
                    shutil.rmtree(temporary_extracted)
                _safe_extract(archive, temporary_extracted)
                temporary_extracted.replace(extracted)
            resolved[rid] = extracted
        else:
            resolved[rid] = archive
    return resolved


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read CapCut JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PackageError(f"CapCut JSON root must be an object: {path}")
    return value


def _authoritative_json(draft: Path, requested: Path | None) -> Path:
    if requested:
        selected = requested if requested.is_absolute() else draft / requested
        if not selected.is_file():
            raise PackageError(f"source JSON does not exist: {selected}")
        return selected
    candidates = [draft / name for name in JSON_NAMES if (draft / name).is_file()]
    if not candidates:
        raise PackageError(f"no CapCut draft JSON found in {draft}")
    # Desktop writes draft_info.json first; mtime and size disambiguate stale copies.
    return max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.stat().st_size))


def _resource_id(record: dict[str, Any], path_key: str = "path") -> str | None:
    preferred = {
        "font_path": ("font_resource_id", "font_id"),
        "resource_url": ("resource_id",),
        "video_path": ("resource_id", "effect_id"),
    }.get(path_key, ())
    for key in (*preferred, "resource_id", "effect_id", "template_id", "font_resource_id", "text_preset_resource_id", "third_resource_id"):
        value = record.get(key)
        if isinstance(value, (str, int)) and RESOURCE_ID.fullmatch(str(value)):
            return str(value)
    return None


def _resource_kind(group: str, source: Path) -> str:
    if group == "files":
        return "files"
    if "artistEffect" in source.parts or group in {"stickers", "text_templates", "flowers"}:
        return "artistEffect"
    return "effect"


class ResourceResolver:
    def __init__(self, overrides: dict[str, Path] | None = None, roots: Iterable[Path] = ()) -> None:
        self.overrides = {str(key): Path(value).expanduser().resolve() for key, value in (overrides or {}).items()}
        self.roots = [Path(root).expanduser().resolve() for root in (*default_resource_roots(), *roots)]

    def resolve(self, resource_id: str, current_path: str | None = None) -> Path | None:
        explicit = self.overrides.get(resource_id)
        if explicit and explicit.exists():
            return explicit
        if current_path and not MATERIAL_PLACEHOLDER.fullmatch(current_path):
            candidate = Path(os.path.expanduser(current_path))
            if candidate.exists():
                return candidate.resolve()
        matches: list[Path] = []
        for root in self.roots:
            candidates = [root / resource_id]
            if root.is_dir():
                candidates.extend(root.glob(f"*/{resource_id}"))
                candidates.extend(root.glob(f"*/*/{resource_id}"))
            if root.name == resource_id:
                candidates.append(root)
            for resource_dir in candidates:
                if resource_dir.is_dir():
                    children = [item for item in resource_dir.iterdir() if not item.name.startswith(".")]
                    matches.extend(children or [resource_dir])
        return max(matches, key=lambda item: item.stat().st_mtime_ns) if matches else None


def _dependency_ids(path: Path) -> set[str]:
    """Read declared package dependencies without guessing from arbitrary numbers."""
    result: set[str] = set()
    files = [path] if path.is_file() and path.suffix == ".json" else list(path.rglob("*.json")) if path.is_dir() else []
    dependency_keys = {"depend_resource_list", "dependency_list", "dependencies", "resource_list"}

    def collect(value: Any, active: bool = False) -> None:
        if isinstance(value, dict):
            rid = _resource_id(value)
            if active and rid:
                result.add(rid)
            for key, child in value.items():
                collect(child, active or key in dependency_keys)
        elif isinstance(value, list):
            for child in value:
                collect(child, active)
        elif active and isinstance(value, (str, int)) and RESOURCE_ID.fullmatch(str(value)):
            result.add(str(value))

    for file in files:
        try:
            collect(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return result


def package_draft(
    draft: Path,
    output: Path,
    *,
    overrides: dict[str, Path] | None = None,
    roots: Iterable[Path] = (),
    source_json: Path | None = None,
    lock_path: Path | None = None,
) -> PackageResult:
    draft = draft.expanduser().resolve()
    output = output.expanduser().resolve()
    if not draft.is_dir():
        raise PackageError(f"draft directory does not exist: {draft}")
    if output.exists():
        raise PackageError(f"output already exists: {output}")
    selected = _authoritative_json(draft, source_json)
    data = _load_json(selected)
    materials = data.get("materials", {})
    if not isinstance(materials, dict):
        raise PackageError("draft materials must be an object")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        shutil.copytree(draft, staged)
        download_root = (
            lock_path.expanduser().resolve().parent / ".clipcraft" / "resource-cache"
            if lock_path is not None
            else Path(temporary) / "downloads"
        )
        downloaded = _lock_overrides(lock_path, download_root, roots)
        resolver = ResourceResolver({**downloaded, **(overrides or {})}, roots)
        packaged: dict[str, tuple[Path, Path, str, int]] = {}
        unresolved: list[str] = []
        rewritten = 0

        def ensure_resource(rid: str, source: Path, group: str, references: int = 1) -> Path:
            nonlocal rewritten
            existing = packaged.get(rid)
            if existing:
                packaged[rid] = (*existing[:3], existing[3] + references)
                return existing[1]
            kind = _resource_kind(group, source)
            destination = staged / "resources" / kind / rid / source.name
            _copy(source, destination)
            packaged[rid] = (source, destination, _tree_hash(destination), references)
            rewritten += references
            for dependency in sorted(_dependency_ids(destination)):
                if dependency == rid or dependency in packaged:
                    continue
                dependency_source = resolver.resolve(dependency)
                if dependency_source:
                    ensure_resource(dependency, dependency_source, group, 0)
                else:
                    unresolved.append(f"dependency {dependency} required by {rid}")
            return destination

        for group, records in materials.items():
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                rid = _resource_id(record)
                value = record.get("path")
                # The independent compiler intentionally emits catalogue
                # effects/transitions with stable IDs but no machine-local
                # path.  Hydrate those records here, before VEHelper sees the
                # draft, just like Desktop would after downloading a resource.
                if not isinstance(value, str):
                    if rid:
                        source = resolver.resolve(rid)
                        if source:
                            record["path"] = str(ensure_resource(rid, source, group))
                        else:
                            unresolved.append(f"{group}: resource {rid} ({record.get('name', '')})")
                    continue
                draft_match = DRAFT_PLACEHOLDER.fullmatch(value)
                if draft_match:
                    suffix = (draft_match.group("suffix") or "").lstrip("/")
                    target = staged / suffix if suffix else staged
                    if not target.exists():
                        unresolved.append(f"{group}: missing draft asset {suffix or '.'}")
                        continue
                    record["path"] = str(target)
                    rewritten += 1
                    continue
                source_path = Path(os.path.expanduser(value))
                if source_path.is_absolute() and draft in source_path.parents:
                    relative = source_path.relative_to(draft)
                    record["path"] = str(staged / relative)
                    rewritten += 1
                    continue
                if not rid:
                    if MATERIAL_PLACEHOLDER.fullmatch(value):
                        unresolved.append(f"{group}: placeholder has no resource_id")
                    continue
                source = resolver.resolve(rid, value)
                if not source:
                    unresolved.append(f"{group}: resource {rid} ({record.get('name', '')})")
                    continue
                record["path"] = str(ensure_resource(rid, source, group))

        serialized_json_keys = {"content", "sdk_extra", "extra", "extra_info", "template_extra"}

        def hydrate_nested_records(value: Any, group: str = "embedded", key: str = "") -> Any:
            """Hydrate resource records at any depth, including JSON stored as strings."""
            if isinstance(value, dict):
                nested_rid = _resource_id(value)
                if nested_rid and "path" not in value:
                    source = resolver.resolve(nested_rid)
                    if source:
                        value["path"] = str(ensure_resource(nested_rid, source, group))
                for path_key, path_value in list(value.items()):
                    if not _is_path_key(path_key) or not isinstance(path_value, str) or not path_value:
                        continue
                    rid = _resource_id(value, path_key)
                    is_placeholder = bool(MATERIAL_PLACEHOLDER.fullmatch(path_value))
                    candidate = Path(os.path.expanduser(path_value))
                    is_external = candidate.is_absolute() and candidate.exists() and staged not in candidate.parents
                    if not rid and is_placeholder:
                        unresolved.append(f"{group}: {path_key} placeholder has no resource ID")
                    elif rid and (is_placeholder or is_external):
                        source = resolver.resolve(rid, path_value)
                        if source:
                            value[path_key] = str(ensure_resource(rid, source, group))
                        elif is_placeholder:
                            unresolved.append(f"{group}: nested resource {rid} ({value.get('name', '')})")
                hydrated: dict[str, Any] = {}
                for child_key, child in value.items():
                    child_group = child_key if group == "embedded" or key == "materials" else group
                    hydrated[child_key] = hydrate_nested_records(child, child_group, child_key)
                return hydrated
            if isinstance(value, list):
                return [hydrate_nested_records(child, group, key) for child in value]
            if key in serialized_json_keys and isinstance(value, str) and value.strip().startswith(("{", "[")):
                try:
                    decoded = json.loads(value)
                except json.JSONDecodeError:
                    return value
                hydrated = hydrate_nested_records(decoded, group, key)
                return json.dumps(hydrated, ensure_ascii=False, separators=(",", ":"))
            return value

        data = hydrate_nested_records(data)

        def rewrite_embedded_paths(value: Any, key: str = "") -> Any:
            nonlocal rewritten
            if isinstance(value, dict):
                return {child_key: rewrite_embedded_paths(child, child_key) for child_key, child in value.items()}
            if isinstance(value, list):
                return [rewrite_embedded_paths(child, key) for child in value]
            if not isinstance(value, str):
                return value
            if key in serialized_json_keys and value.strip().startswith(("{", "[")):
                try:
                    decoded = json.loads(value)
                except json.JSONDecodeError:
                    pass
                else:
                    rewritten_json = rewrite_embedded_paths(decoded, key)
                    return json.dumps(rewritten_json, ensure_ascii=False, separators=(",", ":"))
            draft_match = DRAFT_PLACEHOLDER.fullmatch(value)
            if draft_match:
                suffix = (draft_match.group("suffix") or "").lstrip("/")
                target = staged / suffix if suffix else staged
                if not target.exists():
                    unresolved.append(f"missing embedded draft asset {suffix or '.'}")
                    return value
                rewritten += 1
                return str(target)
            expanded = Path(os.path.expanduser(value))
            resolved_expanded = expanded.resolve() if expanded.is_absolute() else expanded
            if expanded.is_absolute() and resolved_expanded == draft:
                rewritten += 1
                return str(staged)
            if expanded.is_absolute() and draft in resolved_expanded.parents:
                rewritten += 1
                return str(staged / resolved_expanded.relative_to(draft))
            if expanded.is_absolute() and (expanded == staged or staged in expanded.parents):
                return value
            if expanded.is_absolute() and expanded.exists():
                file_id = "local_" + _tree_hash(expanded)[:20]
                destination = ensure_resource(file_id, expanded.resolve(), "files")
                return str(destination)
            if MATERIAL_PLACEHOLDER.fullmatch(value):
                unresolved.append(f"unresolved embedded material placeholder {value}")
            return value

        data = rewrite_embedded_paths(data)

        if unresolved:
            raise UnresolvedResourceError(unresolved)

        # Keep every Desktop mirror synchronized with the authoritative timeline.
        # CapCut may load a copy below Timelines/<timeline-id>/ instead of the
        # root file, so a package is not self-contained unless those copies are
        # updated as well.
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        mirrors = {staged / "draft_info.json", staged / "draft_content.json"}
        for name in JSON_NAMES:
            mirrors.update(staged.glob(f"Timelines/*/{name}"))
            candidate = staged / name
            if candidate.exists():
                mirrors.add(candidate)
        for candidate in sorted(mirrors):
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(encoded, encoding="utf-8")

        resources = tuple(
            PackagedResource(rid, str(source), str(destination), digest, references)
            for rid, (source, destination, digest, references) in sorted(packaged.items())
        )
        manifest = {
            "format": "clipcraft.capcut-resource-package/v1",
            "source_draft": str(draft),
            "source_json": str(selected),
            "resources": [asdict(resource) for resource in resources],
            "rewritten_paths": rewritten,
        }
        (staged / "clipcraft_resources.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        staged.rename(output)

    # Paths in the staged JSON/manifest must point at the final package location.
    finalized = {output / "clipcraft_resources.json"}
    for name in JSON_NAMES:
        finalized.update(output.glob(f"Timelines/*/{name}"))
        finalized.add(output / name)
    for candidate in sorted(finalized):
        if candidate.is_file():
            candidate.write_text(candidate.read_text(encoding="utf-8").replace(str(staged), str(output)), encoding="utf-8")
    final_resources = tuple(
        PackagedResource(item.resource_id, item.source, item.packaged_path.replace(str(staged), str(output)), item.sha256, item.references)
        for item in resources
    )
    return PackageResult(output, selected, final_resources, rewritten)


def render_preflight(draft: Path) -> dict[str, Any]:
    """Fail unless a packaged draft is complete and its resource hashes match."""
    draft = draft.expanduser().resolve()
    manifest_path = draft / "clipcraft_resources.json"
    if not manifest_path.is_file():
        raise PackageError(f"resource manifest is missing: {manifest_path}")
    manifest = _load_json(manifest_path)
    timeline_path = draft / "draft_info.json"
    timeline = _load_json(timeline_path)
    errors: list[str] = []
    checked_paths = 0

    def inspect(value: Any, key: str = "") -> None:
        nonlocal checked_paths
        if isinstance(value, dict):
            for child_key, child in value.items():
                inspect(child, child_key)
        elif isinstance(value, list):
            for child in value:
                inspect(child, key)
        elif isinstance(value, str):
            if key in {"sdk_extra", "extra", "extra_info", "template_extra"} and value.strip().startswith(("{", "[")):
                try:
                    inspect(json.loads(value), key)
                except json.JSONDecodeError:
                    pass
            if "##_material_placeholder_" in value or "##_draftpath_placeholder_" in value:
                errors.append(f"unresolved placeholder in {key}: {value}")
            if _is_path_key(key) and value.startswith("/"):
                checked_paths += 1
                path = Path(value)
                if not path.exists():
                    errors.append(f"missing path: {path}")
                elif path != draft and draft not in path.parents:
                    errors.append(f"external path: {path}")

    timeline_files = {timeline_path}
    for name in JSON_NAMES:
        candidate = draft / name
        if candidate.is_file():
            timeline_files.add(candidate)
        timeline_files.update(draft.glob(f"Timelines/*/{name}"))
    for candidate in sorted(timeline_files):
        try:
            inspect(_load_json(candidate))
        except PackageError as exc:
            errors.append(str(exc))
    resources = manifest.get("resources", [])
    if not isinstance(resources, list):
        errors.append("manifest resources must be a list")
        resources = []
    for item in resources:
        if not isinstance(item, dict):
            errors.append("invalid manifest resource record")
            continue
        path = Path(str(item.get("packaged_path", "")))
        expected = item.get("sha256")
        if not path.exists():
            errors.append(f"missing packaged resource {item.get('resource_id')}: {path}")
        elif expected != _tree_hash(path):
            errors.append(f"resource hash mismatch {item.get('resource_id')}: {path}")
    if errors:
        raise PackageError("render preflight failed:\n- " + "\n- ".join(errors))
    return {
        "draft": str(draft),
        "resources": len(resources),
        "checked_paths": checked_paths,
        "duration_us": timeline.get("duration"),
        "canvas": timeline.get("canvas_config"),
    }
