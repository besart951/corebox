"""Composable application capabilities. Import features explicitly."""

from importlib.metadata import version

__version__ = version("app-foundation")
__all__ = ("__version__",)
