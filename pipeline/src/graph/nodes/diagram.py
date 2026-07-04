"""
pipeline.graph.nodes.diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
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

Why Parallel Generation?
------------------------
All three diagram types (architecture, training flow, inference flow) read from
the same ``extraction`` and write to disjoint state fields. Running them
sequentially would add ~6-9s latency (3 x 2-3s per LLM call). Using
``asyncio.gather`` fans out all three calls concurrently, reducing wall-clock
time to ~2-3s total. The ``_merge_parallel_results`` helper combines the
partial state dicts returned by each sub-task.

Mermaid Validation Strategy:
----------------------------
Two-layer validation:
1. **Structural check** (fast, no external deps): Verifies DSL starts with a
   recognised Mermaid keyword (graph, flowchart, sequenceDiagram, etc.) and
   has balanced square brackets. Catches ~80% of syntax errors instantly.
2. **mmdc render test** (if available): Actually runs the Mermaid CLI to render
   SVG. Catches subtle syntax errors the structural check misses. Requires
   ``@mermaid-js/mermaid-cli`` installed globally (``npm i -g @mermaid-js/mermaid-cli``).
   If mmdc not found, falls back to structural check only.

Cache Key Design:
-----------------
Cache key = (paper_id, diagram_type) from the ``outputs`` table where
output_type starts with "diagram_". Each diagram type is cached independently
so a failed architecture diagram doesn't block cached training/inference flows.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]
from pydantic import BaseModel, Field


from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, track_llm_call
from src.core.utils import extract_json
from src.db.engine import get_supabase_client
from src.db.models import OutputORM
from src.db.session import get_db_context
from sqlalchemy import select
from src.domains.ai_ml.schema import AiMlExtraction
from src.graph.nodes._base import NodeContext, render_prompt
from src.graph.state import PipelineState
from src.models.output import DiagramOutput, DiagramType
from src.services.converters import OutputDeserializer

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

# Why mmdc for validation?
# We could just check syntax with regex, but that misses semantic errors
# (undefined nodes, wrong arrow types). The Mermaid CLI (mmdc) does a full
# parse + render, catching real syntax errors. We run it in a temp file
# subprocess — fast enough (<500ms) and isolates the validation from the
# main process. If mmdc isn't installed, we fall back to structural checks
# (valid start keyword, balanced brackets) which catch ~80% of errors.


def _find_mmdc() -> str | None:
    """Find the mmdc executable, checking common locations including npm global."""
    # Standard PATH lookup
    mmdc = shutil.which("mmdc")
    if mmdc:
        return mmdc

    # Windows npm global installs go to AppData/Roaming/npm
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidate = Path(appdata) / "npm" / "mmdc.cmd"
        if candidate.exists():
            return str(candidate)

    return None


_MMDC_PATH: str | None = _find_mmdc()


async def _validate_mermaid(dsl: str) -> tuple[bool, str]:
    """Validate Mermaid DSL syntax using a quick structural check + optional mmdc.

    Two-layer validation:
    1. **Structural check** (always runs, no deps): Verifies DSL starts with a
       recognised Mermaid keyword (graph, flowchart, sequenceDiagram, etc.) and
       has balanced square brackets. Catches ~80% of syntax errors instantly.
    2. **mmdc render test** (if available): Actually runs the Mermaid CLI to
       render SVG. Catches subtle syntax errors the structural check misses.
       Requires ``@mermaid-js/mermaid-cli`` installed globally
       (``npm i -g @mermaid-js/mermaid-cli``). If mmdc not found, falls back
       to structural check only.

    Returns (is_valid, error_message).
    """
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


async def _call_llm_diagram_async(
    prompt: str,
    diagram_type: DiagramType,
    run_id: str,
    collector: TelemetryCollector,
    max_retries: int = 3,
) -> str:
    """Call LLM to generate Mermaid DSL, with retry on syntax failure."""
    settings = get_settings()
    model = settings.llm.model

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    dsl = ""
    for attempt in range(1, max_retries + 1):
        with track_llm_call(
            collector, stage_name=f"{_STAGE}.{diagram_type.value}", model=model
        ) as ctx:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=settings.llm.temperature,
                max_tokens=8192,
                num_retries=3,
                api_key=settings.llm.api_key.get_secret_value(),
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
    """Render Mermaid DSL to SVG via mmdc and upload to Supabase Storage.

    Why render to SVG instead of storing just the DSL?
    - Frontend can display SVG immediately without client-side Mermaid rendering
    - SVG is resolution-independent and works in all browsers
    - No JavaScript bundle size increase for mermaid.js on the client
    - Supabase Storage serves SVG with correct content-type for <img> tags

    If mmdc is not installed (common in minimal containers), we skip SVG
    generation and store only the DSL. The frontend falls back to client-side
    Mermaid rendering via mermaid.js in that case.
    """
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
        async with get_db_context() as session:
            data = {"dsl_code": diagram.dsl_code, "svg_path": diagram.svg_path}
            row = OutputORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                output_type=f"diagram_{diagram.diagram_type.value}",
                storage_path=f"json:{json.dumps(data)}",
            )
            session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("diagram_store_failed", reason=str(exc))


async def _load_cached_diagrams(paper_id: str) -> list[DiagramOutput]:
    """Return cached ``DiagramOutput`` records if they exist in the DB."""
    try:
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
                diagrams.append(OutputDeserializer.parse_diagram(orm))
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
    ctx = NodeContext(state, _STAGE)
    ctx.mark_running()

    raw_extraction = state.get("extraction")
    extraction = (
        AiMlExtraction.model_validate(raw_extraction) if raw_extraction else None
    )

    # ── 1. Cache check ───────────────────────────────────────────────────────
    if ctx.settings.pipeline.cache_enabled and ctx.paper_id:
        cached_diagrams = await _load_cached_diagrams(ctx.paper_id)
        if cached_diagrams:
            return {
                "diagrams": cached_diagrams,
                **ctx.mark_cached(),
            }

    if extraction is None:
        return {
            "diagrams": [],
            **ctx.mark_skipped("extraction is None — skipping."),
        }

    try:
        collector = TelemetryCollector(run_id=ctx.run_id, paper_id=ctx.paper_id)
        diagram_types = list(DiagramType)

        # Pre-render prompts sequentially
        prompts = [
            render_prompt(
                _PROMPT_PATH,
                architecture_components=[
                    c.model_dump() for c in extraction.architecture_components
                ],
                training_procedure=extraction.training_procedure,
                proposed_method_summary=extraction.proposed_method_summary,
                diagram_type=dt.value,
            )
            for dt in diagram_types
        ]

        # ── Parallel LLM calls: all 3 diagram types at once ───────────────
        tasks = [
            _call_llm_diagram_async(
                prompt,
                dt,
                run_id=ctx.run_id,
                collector=collector,
                max_retries=ctx.settings.llm.max_retries,
            )
            for prompt, dt in zip(prompts, diagram_types)
        ]
        dsls = await asyncio.gather(*tasks)

        diagrams: list[DiagramOutput] = []
        for diagram_type, dsl in zip(diagram_types, dsls):
            svg_path: str | None = None
            if ctx.paper_id:
                log.info("diagram_node.rendering_svg", type=diagram_type.value)
                svg_path = await _upload_svg(ctx.paper_id, diagram_type, dsl)

            diagram = DiagramOutput(
                paper_id=uuid.UUID(ctx.paper_id) if ctx.paper_id else uuid.uuid4(),
                diagram_type=diagram_type,
                dsl_code=dsl,
                svg_path=svg_path,
                dsl_language="mermaid",
            )
            diagrams.append(diagram)

            if ctx.paper_id:
                await _store_diagram(ctx.paper_id, diagram)

            log.info(
                "diagram_node.diagram_done",
                run_id=ctx.run_id,
                diagram_type=diagram_type.value,
                has_svg=svg_path is not None,
                dsl_lines=len(dsl.splitlines()),
            )

        ctx.token_usage[_STAGE] = collector.total_tokens

        log.info("diagram_node.completed", run_id=ctx.run_id, count=len(diagrams))

        return {
            "diagrams": diagrams,
            **ctx.mark_completed(
                {"diagram_count": len(diagrams), "tokens": ctx.token_usage[_STAGE]}
            ),
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "diagrams": [],
            **ctx.mark_failed(exc),
        }
