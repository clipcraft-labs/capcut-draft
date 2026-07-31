# Clipcraft CapCut Draft

Independent compiler from vendor-neutral Clipcraft Project JSON to CapCut
Desktop draft files. This project is unofficial and is not affiliated with or
endorsed by CapCut or ByteDance.

## Quick start

```bash
python -m pip install -e .
clipcraft-draft validate examples/project.json
clipcraft-draft build examples/project.json --out examples/build/demo
clipcraft-draft register examples/build/demo --drafts-dir /path/to/Desktop/drafts
clipcraft-draft register examples/build/demo --drafts-dir /path/to/Desktop/drafts --apply
clipcraft-draft open examples/build/demo
```

The source project remains the source of truth. Generated `draft_content.json`
and `draft_info.json` files are disposable build artifacts.

## Project model

```json
{
  "$schema": "https://raw.githubusercontent.com/clipcraft-labs/capcut-draft/main/schemas/project.v1.schema.json",
  "version": 1,
  "name": "Demo",
  "target": { "app": "capcut", "version": "9.1.0", "os": "mac" },
  "canvas": { "width": 1080, "height": 1920, "fps": 30 },
  "tracks": [
    {
      "type": "video",
      "items": [
        { "src": "./sample.mp4", "at": 0, "duration": 5, "ref": "hero" }
      ]
    }
  ],
  "operations": [
    { "type": "effect", "target": "hero", "resource": "blur-popular" }
  ]
}
```

Dynamic resources are stored in `clipcraft.lock`, not hard-coded into the
project. The lock file is safe to commit only after reviewing its URLs and
metadata; the compiler rejects secret-bearing URL query strings.

Current operations include locked scene effects, filters, transitions, and
caption templates. Local media is copied under a SHA-256 content-addressed
filename so basename collisions cannot change a build.

Desktop registration is plan-first. Without `--apply`, the command only prints
the files it would change. Applying registration preserves existing metadata
with `.bak` files and refuses drafts outside the selected drafts directory.

Generated CapCut 9.1 builds include the full empty material containers,
timeline project index, timeline backup, project metadata, and auxiliary JSON
files expected by the current macOS Desktop layout. Platform device, disk, and
network identifiers are deliberately omitted and are never copied from a real
Desktop project.

The verified target is CapCut Desktop 9.1.0 on macOS. Other target versions or
operating systems are rejected by default because draft layouts are
version-specific. Use `--allow-unsupported-version` only after manually
reviewing the generated files against that Desktop release.
