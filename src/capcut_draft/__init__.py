"""Clipcraft project and CapCut draft compiler."""

from .compiler import BuildResult, compile_project
from .project import Project, ProjectError, load_project
from .desktop import RegistrationPlan, apply_registration, plan_registration
from .assets import AssetStore, StoredAsset, default_asset_root

__all__ = ["AssetStore", "BuildResult", "Project", "ProjectError", "RegistrationPlan", "StoredAsset", "apply_registration", "compile_project", "default_asset_root", "load_project", "plan_registration"]
__version__ = "0.1.0"
