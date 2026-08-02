"""Command-line interface for the independent draft compiler."""

import argparse
import json
from pathlib import Path

from .compiler import compile_project
from .desktop import apply_registration, open_desktop, plan_registration
from .project import load_project
from .packager import PackageError, package_draft, render_preflight
from .validator import validate_draft


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="clipcraft-draft", description="Compile Clipcraft Project JSON into CapCut drafts")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate a project or generated draft")
    validate.add_argument("path", type=Path)
    build = commands.add_parser("build", help="Compile a project")
    build.add_argument("project", type=Path)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--lock", type=Path)
    build.add_argument("--asset-store", type=Path)
    build.add_argument(
        "--allow-unsupported-version",
        action="store_true",
        help="Build for an unverified Desktop target after manual review",
    )
    register = commands.add_parser("register", help="Plan or apply Desktop project registration")
    register.add_argument("draft", type=Path)
    register.add_argument("--drafts-dir", type=Path, required=True)
    register.add_argument("--apply", action="store_true")
    open_command = commands.add_parser("open", help="Launch CapCut Desktop for a registered draft")
    open_command.add_argument("draft", type=Path)
    open_command.add_argument("--app", default="CapCut")
    package = commands.add_parser("package", help="Create a self-contained draft with all CapCut resources")
    package.add_argument("draft", type=Path)
    package.add_argument("--out", type=Path, required=True)
    package.add_argument("--source-json", type=Path)
    package.add_argument("--lock", type=Path, help="Download resources missing from the local CapCut cache")
    package.add_argument("--resource-root", action="append", default=[], type=Path)
    package.add_argument("--resource", action="append", default=[], metavar="ID=PATH")
    preflight = commands.add_parser("render-preflight", help="Verify a resource package before headless rendering")
    preflight.add_argument("draft", type=Path)
    return root


def _resource_overrides(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        resource_id, separator, path = value.partition("=")
        if not separator or not resource_id or not path:
            raise PackageError(f"invalid --resource value {value!r}; expected ID=PATH")
        result[resource_id] = Path(path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "validate":
        if args.path.is_dir() or args.path.name.startswith("draft_"):
            result = validate_draft(args.path)
        else:
            project = load_project(args.path)
            result = {"name": project.name, "version": project.data["version"], "tracks": len(project.data["tracks"])}
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    if args.command == "register":
        plan = plan_registration(args.draft, args.drafts_dir)
        result = apply_registration(plan) if args.apply else {"apply": False, "plan": plan.to_dict()}
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    if args.command == "open":
        print(json.dumps({"ok": True, **open_desktop(args.draft, app=args.app)}, ensure_ascii=False))
        return 0
    if args.command == "package":
        result = package_draft(
            args.draft,
            args.out,
            source_json=args.source_json,
            lock_path=args.lock,
            roots=args.resource_root,
            overrides=_resource_overrides(args.resource),
        )
        print(json.dumps({
            "ok": True,
            "output": str(result.output),
            "source_json": str(result.source_json),
            "resources": len(result.resources),
            "rewritten_paths": result.rewritten_paths,
        }, ensure_ascii=False))
        return 0
    if args.command == "render-preflight":
        print(json.dumps({"ok": True, **render_preflight(args.draft)}, ensure_ascii=False))
        return 0
    project = load_project(args.project)
    result = compile_project(
        project,
        args.out,
        lock_path=args.lock,
        asset_store=args.asset_store,
        allow_unsupported_version=args.allow_unsupported_version,
    )
    print(json.dumps({"ok": True, "output": str(result.output), "tracks": result.tracks, "segments": result.segments, "duration_us": result.duration_us}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
