"""
pipeline.graph.nodes.diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``diagram_node`` — generates architecture and flow diagrams as Mermaid DSL.

Responsibilities
----------------
1. Works from ``state["extraction"]``.
2. Renders ``diagram_v1.j2`` with architecture components and flow descriptions.
3. Makes three **parallel** LiteLLM calls — ARCHITECTURE, TRAINING_FLOW, INFERENCE_FLOW.
4. Validates Mermaid syntax; on failure, retries with error feedback.
5. Uploads SVG files to Supabase Storage ``outputs`` bucket (requires mmdc).
6. Stores ``DiagramOutput`` records in DB.
7. Updates state with ``diagrams``.
8. Emits ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]
from jinja2 import Environment
from pydantic import BaseModel, Field


from pipeline.core.config import get_settings
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, track_llm_call
from pipeline.core.utils import extract_json
from pipeline.db.engine import get_supabase_client
from pipeline.db.models import OutputORM
from pipeline.domains.ai_ml.schema import AiMlExtraction
from pipeline.graph.state import PipelineState
from pipeline.models.output import DiagramOutput, DiagramType
from pipeline.models.run import StageStatus

_STAGE = "diagram"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "diagram_v1.j2"
_OUTPUTS_BUCKET = "outputs"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class DiagramResponse(BaseModel):
    """Structured response for a Mermaid diagram."""

    dsl: str = Field(..., description="The Mermaid DSL code for the diagram.")


# ---------------------------------------------------------------------------
# Mermaid validation
# ---------------------------------------------------------------------------


def _find_mmdc() -> str | None:
    """Find the mmdc executable, checking common locations including npm global."""
    # Standard PATH lookup
    mmdc = shutil.which("mmdc")
    if mmdc:
        return mmdc

    # Windows npm global installs go to AppData/Roaming/npm
    import os

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidate = Path(appdata) / "npm" / "mmdc.cmd"
        if candidate.exists():
            return str(candidate)

    return None


_MMDC_PATH: str | None = _find_mmdc()


async def _validate_mermaid(dsl: str) -> tuple[bool, str]:
    """Validate Mermaid DSL syntax using a quick structural check."""
    import asyncio

    stripped = dsl.strip()
    valid_starts = (
        "graph ",
        "graph\n",
        "flowchart ",
        "flowchart\n",
        "sequenceDiagram",
        "classDiagram",
        "stateDiagram",
        "erDiagram",
        "gantt",
        "pie",
        "gitGraph",
    )
    if not any(stripped.startswith(s) for s in valid_starts):
        return (
            False,
            f"DSL does not start with a recognised Mermaid keyword. Got: {stripped[:60]!r}",
        )

    open_count = stripped.count("[") - stripped.count("]")
    if open_count != 0:
        return False, f"Mismatched square brackets (delta={open_count})."

    if _MMDC_PATH:

        def _run_mmdc():
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".mmd", delete=False, encoding="utf-8"
                ) as in_f:
                    in_f.write(stripped)
                    tmp_in = in_f.name

                tmp_out = tmp_in.replace(".mmd", "_validate.svg")

                result = subprocess.run(
                    [_MMDC_PATH, "-i", tmp_in, "-o", tmp_out],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                Path(tmp_in).unlink(missing_ok=True)
                Path(tmp_out).unlink(missing_ok=True)

                if result.returncode != 0:
                    return False, result.stderr.strip() or "mmdc validation failed."
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            return True, ""

        return await asyncio.to_thread(_run_mmdc)

    return True, ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _render_prompt(
    extraction: AiMlExtraction,
    diagram_type: DiagramType,
) -> str:
    """Render diagram_v1.j2 for the given diagram type."""
    import aiofiles  # type: ignore[import-untyped]

    async with aiofiles.open(_PROMPT_PATH, mode="r", encoding="utf-8") as f:
        template_str = await f.read()

    env = Environment(autoescape=False)
    template = env.from_string(template_str)
    return template.render(
        architecture_components=[
            c.model_dump() for c in extraction.architecture_components
        ],
        training_procedure=extraction.training_procedure,
        proposed_method_summary=extraction.proposed_method_summary,
        diagram_type=diagram_type.value,
    )


async def _call_gemini_diagram_async(
    prompt: str,
    diagram_type: DiagramType,
    run_id: str,
    collector: TelemetryCollector,
    max_retries: int = 3,
) -> str:
    """Call Gemini to generate Mermaid DSL, with retry on syntax failure."""
    settings = get_settings()
    model = settings.gemini.default_model

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    dsl = ""
    for attempt in range(1, max_retries + 1):
        with track_llm_call(
            collector, stage_name=f"{_STAGE}.{diagram_type.value}", model=model
        ) as ctx:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=settings.gemini.temperature,
                max_tokens=8192,
                num_retries=3,
                api_key=settings.gemini.api_key.get_secret_value(),
            )
            ctx.set_response(response)

        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown fences if the model wraps despite instructions
        dsl = raw
        if dsl.startswith("```"):
            dsl = re.sub(r"^```[a-z]*\n?", "", dsl)
            dsl = re.sub(r"\n?```$", "", dsl)
            dsl = dsl.strip()

        # Try JSON extraction as a fallback
        if not any(
            dsl.startswith(s)
            for s in ("graph ", "flowchart ", "sequenceDiagram", "classDiagram")
        ):
            try:
                cleaned = extract_json(raw)
                data = json.loads(cleaned)
                validated = DiagramResponse.model_validate(data)
                extracted = validated.dsl.strip()
                if extracted.startswith("```"):
                    extracted = re.sub(r"^```[a-z]*\n?", "", extracted)
                    extracted = re.sub(r"\n?```$", "", extracted)
                dsl = extracted.strip()
            except Exception:
                pass  # Keep raw dsl

        is_valid, error_msg = await _validate_mermaid(dsl)

        if is_valid:
            log.info(
                "diagram_node.dsl_valid",
                run_id=run_id,
                diagram_type=diagram_type.value,
                attempt=attempt,
            )
            return dsl

        log.warning(
            "diagram_node.dsl_invalid",
            run_id=run_id,
            diagram_type=diagram_type.value,
            attempt=attempt,
            error=error_msg,
        )

        if attempt < max_retries:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The Mermaid DSL you produced has a syntax error: {error_msg}\n"
                        "Please fix the syntax and return ONLY valid Mermaid DSL, "
                        "starting with 'graph TD'. No markdown fences, no JSON wrapping."
                    ),
                }
            )

    log.error(
        "diagram_node.dsl_invalid_after_retries",
        run_id=run_id,
        diagram_type=diagram_type.value,
    )
    return dsl


async def _upload_svg(paper_id: str, diagram_type: DiagramType, dsl: str) -> str | None:
    """Render Mermaid DSL to SVG via mmdc and upload to Supabase Storage."""
    if not _MMDC_PATH:
        log.warning("diagram_node.mmdc_not_found", diagram_type=diagram_type.value)
        return None

    def _do_upload() -> str | None:
        try:
            with (
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".mmd", delete=False, encoding="utf-8"
                ) as in_f,
                tempfile.NamedTemporaryFile(
                    mode="rb", suffix=".svg", delete=False
                ) as out_f,
            ):
                in_f.write(dsl)
                in_path = in_f.name
                out_path = out_f.name

            result = subprocess.run(
                [_MMDC_PATH, "-i", in_path, "-o", out_path],
                capture_output=True,
                timeout=30,
            )

            Path(in_path).unlink(missing_ok=True)

            if result.returncode != 0:
                Path(out_path).unlink(missing_ok=True)
                return None

            svg_bytes = Path(out_path).read_bytes()
            Path(out_path).unlink(missing_ok=True)

            client = get_supabase_client()
            storage_path = f"{paper_id}/diagrams/{diagram_type.value}.svg"
            client.storage.from_(_OUTPUTS_BUCKET).upload(
                path=storage_path,
                file=svg_bytes,
                file_options={"content-type": "image/svg+xml"},
            )

            return storage_path

        except Exception as exc:  # noqa: BLE001
            log.warning(
                "diagram_node.svg_upload_skipped",
                diagram_type=diagram_type.value,
                reason=str(exc),
            )
            return None

    return await asyncio.to_thread(_do_upload)


async def _store_diagram(paper_id: str, diagram: DiagramOutput) -> None:
    """Persist DiagramOutput record to the ``outputs`` table."""
    try:
        from pipeline.db.session import get_db_context

        async with get_db_context() as session:
            row = OutputORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                output_type=f"diagram_{diagram.diagram_type.value}",
                storage_path=diagram.svg_path or f"inline:{diagram.diagram_type.value}",
            )
            session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("diagram_store_failed", reason=str(exc))


async def _load_cached_diagrams(paper_id: str) -> list[DiagramOutput]:
    """Return cached ``DiagramOutput`` records if they exist in the DB."""
    try:
        from pipeline.db.session import get_db_context
        from pipeline.db.models import OutputORM
        from sqlalchemy import select
        import uuid

        async with get_db_context() as session:
            stmt = (
                select(OutputORM)
                .where(OutputORM.paper_id == uuid.UUID(paper_id))
                .where(OutputORM.output_type.startswith("diagram_"))
            )
            res = await session.execute(stmt)
            orms = res.scalars().all()

            diagrams: list[DiagramOutput] = []
            for orm in orms:
                level_str = orm.output_type.replace("diagram_", "")
                diagrams.append(
                    DiagramOutput(
                        paper_id=uuid.UUID(paper_id),
                        diagram_type=DiagramType(level_str),
                        dsl_code="DSL Code Omitted",  # Raw text not in DB schema currently
                        svg_path=orm.storage_path
                        if not orm.storage_path.startswith("inline:")
                        else None,
                    )
                )
            return diagrams
    except Exception as exc:  # noqa: BLE001
        log.debug("diagram_cache_miss", reason=str(exc))
    return []


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def diagram_node(state: PipelineState) -> dict[str, Any]:
    """Generate architecture and flow diagrams from the paper extraction.

    All three diagram types are generated in **parallel** via asyncio.gather.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``extraction``

    Writes to state
    ---------------
    - ``diagrams``
    - ``stage_statuses["diagram"]``
    - ``token_usage["diagram"]``
    - ``errors`` — appended on failure
    """
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    extraction: AiMlExtraction | None = state.get("extraction")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
    token_usage: dict[str, int] = dict(state.get("token_usage", {}))

    log.info("diagram_node.started", run_id=run_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    cached_stages: set[str] = set(state.get("cached_stages", set()))

    # ── 1. Cache check ───────────────────────────────────────────────────────
    from pipeline.core.config import get_settings

    settings = get_settings()

    if settings.pipeline.cache_enabled and paper_id:
        cached_diagrams = await _load_cached_diagrams(paper_id)
        if cached_diagrams:
            log.info("diagram_node.cache_hit", run_id=run_id)
            stage_statuses[_STAGE] = StageStatus.CACHED
            cached_stages.add(_STAGE)
            from pipeline.core.events import Event, EventType, default_bus

            default_bus.emit(
                Event(
                    type=EventType.STAGE_COMPLETED,
                    run_id=run_id,
                    stage_name=_STAGE,
                    payload={"cached": True},
                )
            )
            return {
                "diagrams": cached_diagrams,
                "stage_statuses": stage_statuses,
                "cached_stages": cached_stages,
            }

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("diagram_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors, "diagrams": []}

    try:
        settings = get_settings()
        collector = TelemetryCollector(run_id=run_id, paper_id=paper_id)
        diagram_types = list(DiagramType)

        # Pre-render prompts sequentially
        prompts = [await _render_prompt(extraction, dt) for dt in diagram_types]

        # ── Parallel LLM calls: all 3 diagram types at once ───────────────
        tasks = [
            _call_gemini_diagram_async(
                prompt,
                dt,
                run_id,
                collector,
                settings.gemini.max_retries,
            )
            for prompt, dt in zip(prompts, diagram_types)
        ]
        dsls = await asyncio.gather(*tasks)

        diagrams: list[DiagramOutput] = []
        for diagram_type, dsl in zip(diagram_types, dsls):
            svg_path: str | None = None
            if paper_id:
                log.info("diagram_node.rendering_svg", type=diagram_type.value)
                svg_path = await _upload_svg(paper_id, diagram_type, dsl)

            diagram = DiagramOutput(
                paper_id=uuid.UUID(paper_id) if paper_id else uuid.uuid4(),
                diagram_type=diagram_type,
                dsl_code=dsl,
                svg_path=svg_path,
                dsl_language="mermaid",
            )
            diagrams.append(diagram)

            if paper_id:
                await _store_diagram(paper_id, diagram)

            log.info(
                "diagram_node.diagram_done",
                run_id=run_id,
                diagram_type=diagram_type.value,
                has_svg=svg_path is not None,
                dsl_lines=len(dsl.splitlines()),
            )

        token_usage[_STAGE] = collector.total_tokens
        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"diagram_count": len(diagrams), "tokens": token_usage[_STAGE]},
            )
        )

        log.info("diagram_node.completed", run_id=run_id, count=len(diagrams))

        return {
            "diagrams": diagrams,
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("diagram_node.failed", run_id=run_id, error=str(exc))
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors, "diagrams": []}
