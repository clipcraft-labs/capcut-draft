"""Clipcraft project and CapCut draft compiler."""

from .compiler import BuildResult, compile_project
from .project import Project, ProjectError, load_project
from .desktop import RegistrationPlan, apply_registration, open_desktop, plan_registration
from .assets import AssetStore, StoredAsset, default_asset_root
from .packager import PackageError, PackageResult, PackagedResource, ResourceResolver, UnresolvedResourceError, package_draft, render_preflight

__all__ = ["AssetStore", "BuildResult", "PackageError", "PackageResult", "PackagedResource", "Project", "ProjectError", "RegistrationPlan", "ResourceResolver", "StoredAsset", "UnresolvedResourceError", "apply_registration", "compile_project", "default_asset_root", "load_project", "open_desktop", "package_draft", "plan_registration", "render_preflight"]
__version__ = "0.2.0"
