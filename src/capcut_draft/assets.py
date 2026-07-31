"""Content-addressed local asset storage."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil

from .project import ProjectError


@dataclass(frozen=True, slots=True)
class StoredAsset:
    digest: str
    path: Path
    size: int


def default_asset_root() -> Path:
    configured = os.getenv("CLIPCRAFT_CACHE_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".cache" / "clipcraft"
    return base / "assets"


class AssetStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).expanduser() if root is not None else default_asset_root()

    def ingest(self, source: str | Path) -> StoredAsset:
        path = Path(source)
        content = path.read_bytes()
        return self.put(content, suffix=path.suffix)

    def put(self, content: bytes, *, suffix: str = "") -> StoredAsset:
        digest = hashlib.sha256(content).hexdigest()
        extension = suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}" if suffix else ""
        directory = self.root / digest[:2]
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{digest}{extension}"
        if not destination.exists():
            destination.write_bytes(content)
        return StoredAsset(digest, destination, len(content))

    def resolve(self, digest: str) -> Path:
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest.lower()):
            raise ProjectError("asset_hash must be a SHA-256 hex digest")
        directory = self.root / digest[:2]
        matches = list(directory.glob(f"{digest}.*")) + list(directory.glob(digest))
        if len(matches) != 1:
            raise ProjectError(f"Asset {digest} is not available in {self.root}")
        return matches[0]

    def copy_into(self, digest: str, destination_dir: Path) -> Path:
        source = self.resolve(digest)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / source.name
        if not destination.exists():
            shutil.copy2(source, destination)
        return destination

