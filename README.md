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

Each build also writes `clipcraft_build.json`. This provenance manifest keeps
the complete normalized identity of every locked resource actually used by the
project—including catalogue, resource, effect, panel, and category identifiers—and
records every target where it was applied. CapCut-native material fields retain
the identifiers needed by Desktop; the manifest retains provider metadata that
does not have a stable native field. Content-addressed music additionally keeps
its catalogue ID alongside the local audio material.

Local images, video, and resolved audio are embedded under the build's
`assets/` directory. Catalogue effects, filters, transitions, and caption
templates are reproducible references, not archived vendor bundles: their
exact IDs and category provenance are preserved, and CapCut Desktop resolves
the corresponding package when the draft is opened. Those resource types are
therefore not guaranteed to work fully offline.

Current tracks include video, still images, audio, and text. Operations include
locked scene effects, filters, transitions, and caption templates. Local media
is copied under a SHA-256 content-addressed filename so basename collisions
cannot change a build.

Desktop registration is plan-first. Without `--apply`, the command only prints
the files it would change. Applying registration preserves existing metadata
with `.bak` files and refuses drafts outside the selected drafts directory. If
a build was copied into that directory, registration rebases its draft root and
all project-owned media paths to the copied location. This keeps the registered
draft self-contained instead of depending on the original build directory.
Validation checks every referenced local media file, verifies any recorded
SHA-256 content hash, and reports whether a draft still depends on media outside
its own project directory.

Generated CapCut 9.1 builds include the full empty material containers,
timeline project index, timeline backup, project metadata, and auxiliary JSON
files expected by the current macOS Desktop layout. Platform device, disk, and
network identifiers are deliberately omitted and are never copied from a real
Desktop project.

The verified target is CapCut Desktop 9.1.0 on macOS. Other target versions or
operating systems are rejected by default because draft layouts are
version-specific. Use `--allow-unsupported-version` only after manually
reviewing the generated files against that Desktop release.
