# Clipcraft CapCut Draft

Independent compiler from vendor-neutral Clipcraft Project JSON to CapCut
Desktop draft files. This project is unofficial and is not affiliated with or
endorsed by CapCut or ByteDance.

The public package contains only the independent JSON compiler, packager,
validator, and Desktop registration adapter. It does not contain CapCut,
VEHelper, provider frameworks, downloaded bundles, models, fonts, or catalogue
media.

## Quick start

```bash
python -m pip install -e .
clipcraft-draft validate examples/project.json
clipcraft-draft build examples/project.json --out examples/build/demo
clipcraft-draft register examples/build/demo --drafts-dir /path/to/Desktop/drafts
clipcraft-draft register examples/build/demo --drafts-dir /path/to/Desktop/drafts --apply
clipcraft-draft open examples/build/demo
clipcraft-draft package /path/to/CapCut/Draft --out build/render-package \
  --lock clipcraft.lock --resource RESOURCE_ID=/path/to/unpacked/resource
clipcraft-draft render-preflight build/render-package
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

Project JSON may declare dynamic resources as readable keys plus exact CapCut
IDs. `clipcraft project render` turns those declarations into a managed
`clipcraft.lock`; callers do not need a separate resolve step. The generated
lock file is safe to commit only after reviewing its URLs and
metadata; the compiler rejects secret-bearing URL query strings.

Each build also writes `clipcraft_build.json`. This provenance manifest keeps
the complete normalized identity of every locked resource actually used by the
project—including catalogue, resource, effect, panel, and category identifiers—and
records every target where it was applied. CapCut-native material fields retain
the identifiers needed by Desktop; the manifest retains provider metadata that
does not have a stable native field. Content-addressed music additionally keeps
its catalogue ID alongside the local audio material.

Local or catalogue-resolved images, video, and audio are embedded under the
build's `assets/` directory. Catalogue effects, filters, transitions, caption
templates, body/face effects, stickers, video/text animations, audio effects,
fonts, text effects, and masks are emitted as ID-only reproducible references
during compilation. The `package` or integrated `project render` stage resolves
those IDs and embeds their vendor bundles for offline export.

The `package` command converts an existing Desktop draft into a self-contained
render package. It searches every installed CapCut cache category (not only
effects), resolves nested records and JSON-encoded `sdk_extra`, recursively
copies declared dependencies, embeds application fonts and other absolute-path
assets, and synchronizes the Desktop timeline mirrors. Missing resources may be
supplied as `ID=PATH` or downloaded from a version-1 lock record containing
`download_url` and optional `file_md5`. Downloads are hash-checked and archives
are extracted with path traversal protection.

`render-preflight` rejects unresolved placeholders, missing or external paths,
and modified resource trees. A successful preflight means the draft directory
is resource-complete; it does not itself invoke CapCut's private VEHelper export
service.

The unified `clipcraft project render` command can invoke a separately supplied
native runner after preflight. The runner is not distributed by this package;
see the public
[headless rendering guide](https://clipcraft-labs.docs.buildwithfern.com/guides/build-projects/headless-rendering).

Current tracks include video, still images, audio, and text. Operations include
locked scene effects, filters, transitions, caption templates, body effects,
stickers, animations, text animations, audio effects, fonts, text effects, and
masks. Sticker operations accept `scale`, `alpha`, `position`, and
`renderIndex`; animation and mask operations accept their native timing and
geometry controls. Their base time range is inherited from the target. Local
media is copied under a SHA-256 content-addressed filename so basename
collisions cannot change a build.

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

## Public repository safety

Generated drafts and packages can contain absolute paths, copied source media,
and downloaded proprietary resources. Do not commit them. Publish only Project
JSON, sanitized lock metadata, and source media you are licensed to distribute.
Never publish provider binaries, Desktop indexes, raw responses, signed URLs,
profiles, cookies, request signatures, or device/account identifiers.
