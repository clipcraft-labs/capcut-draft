"""Clipcraft project and CapCut draft compiler."""

from .compiler import BuildResult, compile_project
from .project import Project, ProjectError, load_project
from .desktop import RegistrationPlan, apply_registration, plan_registration

__all__ = ["BuildResult", "Project", "ProjectError", "RegistrationPlan", "apply_registration", "compile_project", "load_project", "plan_registration"]
__version__ = "0.1.0"
