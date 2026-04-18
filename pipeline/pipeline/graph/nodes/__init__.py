"""
pipeline.graph.nodes
~~~~~~~~~~~~~~~~~~~~~
Exports all eight pipeline node functions in a flat namespace so
``pipeline.py`` can import them without knowing the module layout.
"""

from pipeline.graph.nodes.classify import classify_node
from pipeline.graph.nodes.codegen import codegen_node
from pipeline.graph.nodes.diagram import diagram_node
from pipeline.graph.nodes.embed import embed_node
from pipeline.graph.nodes.extract import extract_node
from pipeline.graph.nodes.ingest import ingest_node
from pipeline.graph.nodes.report import report_node
from pipeline.graph.nodes.summarise import summarise_node

__all__ = [
    "ingest_node",
    "classify_node",
    "extract_node",
    "summarise_node",
    "embed_node",
    "diagram_node",
    "codegen_node",
    "report_node",
]
