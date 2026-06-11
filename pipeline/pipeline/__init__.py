"""Compatibility package for tests that import pipeline.* modules.

This mirrors the src.* package structure for unit tests that patch
pipeline.core/services/etc.
"""

from __future__ import annotations

import importlib
import sys


def _alias_package(name: str) -> None:
    module = importlib.import_module(f"src.{name}")
    sys.modules[f"pipeline.{name}"] = module


for _pkg in (
    "api",
    "core",
    "db",
    "domains",
    "graph",
    "models",
    "services",
):
    _alias_package(_pkg)
