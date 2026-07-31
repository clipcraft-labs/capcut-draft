# Clipcraft CapCut Draft

Independent compiler from vendor-neutral Clipcraft Project JSON to CapCut
Desktop draft files. This project is unofficial and is not affiliated with or
endorsed by CapCut or ByteDance.

## Quick start

```bash
python -m pip install -e .
clipcraft-draft validate examples/project.json
clipcraft-draft build examples/project.json --out examples/build/demo
```

The source project remains the source of truth. Generated `draft_content.json`
and `draft_info.json` files are disposable build artifacts.

## Project model

```json
{
  "$schema": "https://clipcraft-labs.github.io/schemas/project.v1.json",
  "version": 1,
  "name": "Demo",
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

Current scope is an alpha foundation: local video, audio, text, and locked
scene effects. Desktop registration and version adapters will be added after
fixture validation.

