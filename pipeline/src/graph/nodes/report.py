"""
pipeline.graph.nodes.report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``report_node`` — final stage; assembles the full structured Markdown report.

Responsibilities
----------------
1. Works from the full state: summaries, diagrams, code_output, extraction,
   paper_metadata.
2. Assembles a structured Markdown report with all sections.
3. Uploads Markdown to Supabase Storage ``outputs`` bucket.
4. Stores a ``ReportOutput`` record in DB.
5. Updates state with ``report_path``.
6. Emits ``RUN_COMPLETED`` event on the default bus.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from src.core.logger import get_logger
from src.graph.state import PipelineState
from src.domains.ai_ml.schema import AiMlExtraction
from src.models.output import (
    CodeOutput,
    DiagramOutput,
    DiagramType,
    ReportOutput,
    SummaryLevel,
    SummaryOutput,
)
from src.models.paper import PaperMetadata
from src.models.run import StageStatus

_STAGE = "report"
_OUTPUTS_BUCKET = "outputs"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _get_summary(summaries: list[SummaryOutput], level: SummaryLevel) -> str:
    """Return summary content for the requested level, or a placeholder."""
    for s in summaries:
        if s.level == level:
            return s.content
    return "_Summary not available._"


def _get_diagram_svg_ref(
    diagrams: list[DiagramOutput], diagram_type: DiagramType
) -> str:
    """Return an embedded SVG reference or a Mermaid DSL code block."""
    for d in diagrams:
        if d.diagram_type == diagram_type:
            if d.svg_path:
                return f"![{diagram_type.value} diagram]({d.svg_path})"
            # Fall back to fenced Mermaid block
            return f"```mermaid\n{d.dsl_code}\n```"
    return "_Diagram not generated._"


def _build_markdown(
    paper_metadata: PaperMetadata | None,
    extraction: AiMlExtraction | None,
    summaries: list[SummaryOutput],
    diagrams: list[DiagramOutput],
    code_output: CodeOutput | None,
    run_id: str,
) -> str:
    """Assemble the full structured Markdown report."""

    title = paper_metadata.title if paper_metadata else "Untitled Paper"
    authors = (
        ", ".join(paper_metadata.authors)
        if paper_metadata and paper_metadata.authors
        else "Unknown Authors"
    )
    abstract = (
        paper_metadata.abstract
        if paper_metadata and paper_metadata.abstract
        else "_No abstract available._"
    )
    year = (
        str(paper_metadata.year)
        if paper_metadata and paper_metadata.year
        else "Unknown"
    )
    venue = (
        paper_metadata.venue
        if paper_metadata and paper_metadata.venue
        else "Unknown Venue"
    )
    arxiv_id = (
        paper_metadata.arxiv_id if paper_metadata and paper_metadata.arxiv_id else None
    )
    doi = paper_metadata.doi if paper_metadata and paper_metadata.doi else None

    # ── Key contributions ────────────────────────────────────────────────────
    contributions_md = "_Not extracted._"
    if extraction and extraction.key_contributions:
        contributions_md = "\n".join(f"- {c}" for c in extraction.key_contributions)

    # ── Metrics table ────────────────────────────────────────────────────────
    metrics_md = "_No quantitative results extracted._"
    if extraction and extraction.evaluation_metrics:
        rows = "\n".join(
            f"| {m.metric_name} | {m.value} | {m.baseline_comparison or '—'} |"
            for m in extraction.evaluation_metrics
        )
        metrics_md = (
            "| Metric | Value | vs. Baseline |\n"
            "|--------|-------|-------------|\n" + rows
        )

    # ── Architecture components ──────────────────────────────────────────────
    arch_md = "_No architecture components extracted._"
    if extraction and extraction.architecture_components:
        arch_md = "\n".join(
            f"- **{c.name}** (`{c.type}`): {c.description}"
            for c in extraction.architecture_components
        )

    # ── Code snippet preview ─────────────────────────────────────────────────
    code_preview = "_Code generation was skipped for this paper._"
    if code_output:
        paths: list[str] = []
        if code_output.python_path:
            paths.append(f"- **Python script**: `{code_output.python_path}`")
        if code_output.notebook_path:
            paths.append(f"- **Jupyter notebook**: `{code_output.notebook_path}`")
        if paths:
            code_preview = "\n".join(paths)
        if code_output.synthetic_data_description:
            code_preview += f"\n\n> {code_output.synthetic_data_description}"

    # ── Extraction JSON (collapsible) ────────────────────────────────────────
    extraction_json = (
        json.dumps(extraction.model_dump(mode="json"), indent=2) if extraction else "{}"
    )

    # ── Metadata links ───────────────────────────────────────────────────────
    links: list[str] = []
    if arxiv_id:
        links.append(f"[arXiv:{arxiv_id}](https://arxiv.org/abs/{arxiv_id})")
    if doi:
        links.append(f"[DOI:{doi}](https://doi.org/{doi})")
    links_md = " · ".join(links) if links else "_No external links._"

    report = f"""# Research Report: {title}

> Generated by **Research Pilot** · Run ID: `{run_id}`

---

## 📄 Paper Metadata

| Field | Value |
|-------|-------|
| **Title** | {title} |
| **Authors** | {authors} |
| **Year** | {year} |
| **Venue** | {venue} |
| **Links** | {links_md} |

### Abstract

{abstract}

---

## 🔍 One-Paragraph Summary

{_get_summary(summaries, SummaryLevel.PARAGRAPH)}

---

## ✨ Key Contributions

{contributions_md}

---

## 🏗️ Architecture Diagram

{_get_diagram_svg_ref(diagrams, DiagramType.ARCHITECTURE)}

---

## 🔄 Training Flow

{_get_diagram_svg_ref(diagrams, DiagramType.TRAINING_FLOW)}

---

## ⚡ Inference Flow

{_get_diagram_svg_ref(diagrams, DiagramType.INFERENCE_FLOW)}

---

## 📑 Section-by-Section Summary

{_get_summary(summaries, SummaryLevel.SECTION_BY_SECTION)}

---

## 🧱 Architecture Components

{arch_md}

---

## 📊 Evaluation Results

{metrics_md}

---

## 💻 Implementation Notes

### Generated Code Artefacts

{code_preview}

---

## 🧒 ELI5 Summary

{_get_summary(summaries, SummaryLevel.ELI5)}

---

## 📋 Bullet Summary

{_get_summary(summaries, SummaryLevel.BULLETS)}

---

## 🗂️ Full Extraction Data

<details>
<summary>Click to expand JSON extraction payload</summary>

```json
{extraction_json}
```

</details>
"""

    return report.strip()


# ---------------------------------------------------------------------------
# Storage + DB helpers
# ---------------------------------------------------------------------------


async def _upload_report(paper_id: str, markdown: str) -> str:
    """Upload the Markdown report to Supabase Storage, return storage path."""
    import asyncio

    storage_path = f"{paper_id}/report.md"

    def _do_upload() -> str:
        try:
            from src.db.engine import get_supabase_client

            client = get_supabase_client()
            client.storage.from_(_OUTPUTS_BUCKET).upload(
                path=storage_path,
                file=markdown.encode("utf-8"),
                file_options={"content-type": "text/markdown"},
            )
            return storage_path
        except Exception as exc:  # noqa: BLE001
            log.warning("report_upload_skipped", reason=str(exc))
            return f"local://{paper_id}/report.md"

    return await asyncio.to_thread(_do_upload)


async def _store_report_output(paper_id: str, report: ReportOutput) -> None:
    """Persist ReportOutput to the ``outputs`` table."""
    try:
        from src.db.session import get_db_context
        from src.db.models import OutputORM

        async with get_db_context() as session:
            row = OutputORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                output_type="report",
                storage_path=report.markdown_path,
            )
            session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("report_store_failed", reason=str(exc))


async def _load_cached_report(paper_id: str) -> str | None:
    """Return a cached report path if one exists in the DB."""
    try:
        from src.db.session import get_db_context
        from src.db.models import OutputORM
        from sqlalchemy import select
        import uuid

        async with get_db_context() as session:
            stmt = (
                select(OutputORM.storage_path)
                .where(OutputORM.paper_id == uuid.UUID(paper_id))
                .where(OutputORM.output_type == "report")
                .limit(1)
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        log.debug("report_cache_miss", reason=str(exc))
    return None


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def report_node(state: PipelineState) -> dict[str, Any]:
    """Assemble the final Markdown report and emit RUN_COMPLETED.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``paper_metadata``, ``extraction``
    - ``summaries``, ``diagrams``, ``code_output``

    Writes to state
    ---------------
    - ``report_path``
    - ``stage_statuses["report"]``
    - ``errors`` — appended on failure
    """
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    paper_metadata: PaperMetadata | None = state.get("paper_metadata")
    extraction: AiMlExtraction | None = state.get("extraction")
    summaries: list[SummaryOutput] = state.get("summaries", [])
    diagrams: list[DiagramOutput] = state.get("diagrams", [])
    code_output: CodeOutput | None = state.get("code_output")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))

    log.info("report_node.started", run_id=run_id, paper_id=paper_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    cached_stages: set[str] = set(state.get("cached_stages", set()))

    # ── 0. Cache check ───────────────────────────────────────────────────────
    from src.core.config import get_settings

    settings = get_settings()

    if settings.pipeline.cache_enabled and paper_id:
        cached_path = await _load_cached_report(paper_id)
        if cached_path:
            log.info("report_node.cache_hit", run_id=run_id)
            stage_statuses[_STAGE] = StageStatus.CACHED
            cached_stages.add(_STAGE)
            from src.core.events import Event, EventType, default_bus

            default_bus.emit(
                Event(
                    type=EventType.STAGE_COMPLETED,
                    run_id=run_id,
                    stage_name=_STAGE,
                    payload={"cached": True},
                )
            )
            # When report hits cache, we can safely skip markdown generation
            # and just return the report path.
            return {
                "report_path": cached_path,
                "stage_statuses": stage_statuses,
                "cached_stages": cached_stages,
            }

    try:
        # ── 1. Assemble Markdown ─────────────────────────────────────────
        markdown = _build_markdown(
            paper_metadata=paper_metadata,
            extraction=extraction,
            summaries=summaries,
            diagrams=diagrams,
            code_output=code_output,
            run_id=run_id,
        )

        # ── 2. Upload to Supabase Storage ────────────────────────────────
        storage_path = await _upload_report(paper_id or run_id, markdown)

        # ── 3. Persist ReportOutput to DB ────────────────────────────────
        paper_uuid = uuid.UUID(paper_id) if paper_id else uuid.uuid4()
        report_output = ReportOutput(
            paper_id=paper_uuid,
            markdown_path=storage_path,
        )

        if paper_id:
            await _store_report_output(paper_id, report_output)

        # ── 4. Emit RUN_COMPLETED ────────────────────────────────────────
        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.RUN_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={
                    "report_path": storage_path,
                    "error_count": len(errors),
                    "staged_completed": [
                        s
                        for s, v in stage_statuses.items()
                        if v in (StageStatus.COMPLETED, StageStatus.CACHED)
                    ],
                },
            )
        )

        log.info(
            "report_node.completed",
            run_id=run_id,
            report_path=storage_path,
            report_length=len(markdown),
        )

        return {
            "report_path": storage_path,
            "stage_statuses": stage_statuses,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("report_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.RUN_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors}
