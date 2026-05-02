"""
pipeline.models
~~~~~~~~~~~~~~~
Pure Pydantic data models. No business logic, no database operations, no LLM
calls. Just data shapes and validation. Everything in the pipeline passes
these models between stages.
"""

from src.models.paper import (
    Paper,
    PaperCreate,
    PaperMetadata,
    PaperSource,
)
from src.models.run import (
    PipelineRun,
    RunStatus,
    StageResult,
    StageStatus,
)
from src.models.extraction import (
    ExtractionResult,
)
from src.models.output import (
    CodeOutput,
    DiagramOutput,
    DiagramType,
    OutputBundle,
    ReportOutput,
    SummaryLevel,
    SummaryOutput,
)

__all__ = [
    # paper
    "Paper",
    "PaperCreate",
    "PaperMetadata",
    "PaperSource",
    # run
    "PipelineRun",
    "RunStatus",
    "StageResult",
    "StageStatus",
    # extraction
    "ExtractionResult",
    # output
    "CodeOutput",
    "DiagramOutput",
    "DiagramType",
    "OutputBundle",
    "ReportOutput",
    "SummaryLevel",
    "SummaryOutput",
]
