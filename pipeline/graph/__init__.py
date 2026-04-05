"""
pipeline.graph
~~~~~~~~~~~~~~
LangGraph orchestration layer for the Research Pilot pipeline.

Public surface
--------------
    from pipeline.graph import research_pipeline, PipelineState, make_initial_state

    initial = make_initial_state(run_id="abc-123")
    result  = research_pipeline.invoke(initial)
"""

from pipeline.graph.pipeline import research_pipeline
from pipeline.graph.state import PipelineState, make_initial_state

__all__ = [
    "PipelineState",
    "make_initial_state",
    "research_pipeline",
]
