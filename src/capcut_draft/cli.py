"""Command-line interface for the independent draft compiler."""

import argparse
import json
from pathlib import Path

from .compiler import compile_project
from .desktop import apply_registration, plan_registration
from .project import load_project
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
    register = commands.add_parser("register", help="Plan or apply Desktop project registration")
    register.add_argument("draft", type=Path)
    register.add_argument("--drafts-dir", type=Path, required=True)
    register.add_argument("--apply", action="store_true")
    return root


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
    project = load_project(args.project)
    result = compile_project(project, args.out, lock_path=args.lock)
    print(json.dumps({"ok": True, "output": str(result.output), "tracks": result.tracks, "segments": result.segments, "duration_us": result.duration_us}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
