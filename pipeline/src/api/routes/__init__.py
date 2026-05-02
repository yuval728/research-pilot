"""
pipeline.api.routes
~~~~~~~~~~~~~~~~~~~
Router package — exposes all sub-routers for mounting in main.py.
"""

from .health import router as health_router
from .papers import router as papers_router
from .pipeline import router as pipeline_router
from .search import router as search_router

__all__ = [
    "health_router",
    "papers_router",
    "pipeline_router",
    "search_router",
]
