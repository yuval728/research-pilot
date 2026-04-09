"""
pipeline.models
~~~~~~~~~~~~~~~
Pure Pydantic data models. No business logic, no database operations, no LLM
calls. Just data shapes and validation. Everything in the pipeline passes
these models between stages.
"""

from pipeline.models.paper import (
    Paper,
    PaperCreate,
    PaperMetadata,
    PaperSource,
)
from pipeline.models.run import (
    PipelineRun,
    RunStatus,
    StageResult,
    StageStatus,
)
from pipeline.models.extraction import (
    ExtractionResult,
)
from pipeline.models.output import (
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
