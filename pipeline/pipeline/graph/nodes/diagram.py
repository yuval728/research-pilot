"""
pipeline.graph.nodes.diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``diagram_node`` — generates architecture and flow diagrams as Mermaid DSL.

Responsibilities
----------------
1. Works from ``state["extraction"]``.
2. Renders ``diagram_v1.j2`` with architecture components and flow descriptions.
3. Makes three LiteLLM calls — ARCHITECTURE, TRAINING_FLOW, INFERENCE_FLOW.
4. Validates Mermaid syntax; on failure, retries with error feedback.
5. Uploads SVG files to Supabase Storage ``outputs`` bucket.
6. Stores ``DiagramOutput`` records in DB.
7. Updates state with ``diagrams``.
8. Emits ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import litellm  # type: ignore[import-untyped]
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from supabase import create_client  # type: ignore[import-untyped]

from pipeline.core.config import get_settings
from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, track_llm_call
from pipeline.core.utils import extract_json
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


def _validate_mermaid(dsl: str) -> tuple[bool, str]:
    """Validate Mermaid DSL syntax."""
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

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mmd", delete=False, encoding="utf-8"
        ) as f:
            f.write(stripped)
            tmp_path = f.name

        result = subprocess.run(
            ["mmdc", "-i", tmp_path, "-o", "/dev/null"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return False, result.stderr.strip() or "mmdc validation failed."
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return True, ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_prompt(
    extraction: AiMlExtraction,
    diagram_type: DiagramType,
) -> str:
    """Render diagram_v1.j2 for the given diagram type."""
    env = Environment(
        loader=FileSystemLoader(str(_PROMPT_PATH.parent)),
        autoescape=False,
    )
    template = env.get_template(_PROMPT_PATH.name)
    return template.render(
        architecture_components=[
            c.model_dump() for c in extraction.architecture_components
        ],
        training_procedure=extraction.training_procedure,
        proposed_method_summary=extraction.proposed_method_summary,
        diagram_type=diagram_type.value,
    )


def _call_gemini_diagram(
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

    for attempt in range(1, max_retries + 1):
        with track_llm_call(
            collector, stage_name=f"{_STAGE}.{diagram_type.value}", model=model
        ) as ctx:
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=settings.gemini.temperature,
                max_tokens=1024,
                num_retries=3,
                response_format=DiagramResponse,  # Force JSON mode
                api_key=settings.gemini.api_key.get_secret_value(),
            )
            ctx.set_response(response)

        raw = (response.choices[0].message.content or "").strip()

        try:
            cleaned = extract_json(raw)
            data = json.loads(cleaned)
            validated = DiagramResponse.model_validate(data)
            dsl = validated.dsl.strip()
        except Exception as exc:
            log.warning("diagram_node.parse_failed", error=str(exc), raw=raw)
            dsl = raw

        if dsl.startswith("```"):
            dsl = re.sub(r"^```[a-z]*\n?", "", dsl)
            dsl = re.sub(r"\n?```$", "", dsl)
            dsl = dsl.strip()

        is_valid, error_msg = _validate_mermaid(dsl)

        if is_valid:
            log.info(
                "diagram_node.dsl_valid",
                run_id=run_id,
                diagram_type=diagram_type.value,
                attempt=attempt,
            )
            return raw

        log.warning(
            "diagram_node.dsl_invalid",
            run_id=run_id,
            diagram_type=diagram_type.value,
            attempt=attempt,
            error=error_msg,
        )

        if attempt < max_retries:
            # Append error feedback to messages for next attempt
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The Mermaid DSL you produced has a syntax error: {error_msg}\n"
                        "Please fix the syntax and return ONLY valid Mermaid DSL, "
                        "starting with 'graph TD'. No markdown fences."
                    ),
                }
            )

    # Return best-effort DSL even if still invalid after all retries
    log.error(
        "diagram_node.dsl_invalid_after_retries",
        run_id=run_id,
        diagram_type=diagram_type.value,
    )
    return raw


def _upload_svg(paper_id: str, diagram_type: DiagramType, dsl: str) -> str | None:
    """Render Mermaid DSL to SVG via mmdc and upload to Supabase Storage."""
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
            ["mmdc", "-i", in_path, "-o", out_path],
            capture_output=True,
            timeout=30,
        )

        Path(in_path).unlink(missing_ok=True)

        if result.returncode != 0:
            Path(out_path).unlink(missing_ok=True)
            return None

        svg_bytes = Path(out_path).read_bytes()
        Path(out_path).unlink(missing_ok=True)

        settings = get_settings()
        client = create_client(
            settings.supabase.url,
            settings.supabase.service_role_key.get_secret_value(),
        )

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


def _store_diagram(paper_id: str, diagram: DiagramOutput) -> None:
    """Persist DiagramOutput record to the ``outputs`` table."""
    try:
        settings = get_settings()
        engine = create_engine(
            settings.supabase.db_url.get_secret_value(), pool_pre_ping=True
        )
        with Session(engine) as session:
            row = OutputORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                output_type=f"diagram_{diagram.diagram_type.value}",
                storage_path=diagram.svg_path or f"inline:{diagram.diagram_type.value}",
            )
            session.add(row)
            session.commit()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        log.warning("diagram_store_failed", reason=str(exc))


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def diagram_node(state: PipelineState) -> dict[str, Any]:
    """Generate architecture and flow diagrams from the paper extraction.

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

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("diagram_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors, "diagrams": []}

    try:
        from pipeline.core.config import get_settings

        settings = get_settings()
        collector = TelemetryCollector(run_id=run_id)
        diagrams: list[DiagramOutput] = []

        for diagram_type in DiagramType:
            prompt = _render_prompt(extraction, diagram_type)
            dsl = _call_gemini_diagram(
                prompt,
                diagram_type,
                run_id,
                collector,
                max_retries=settings.gemini.max_retries,
            )

            svg_path: str | None = None
            if paper_id:
                svg_path = _upload_svg(paper_id, diagram_type, dsl)

            diagram = DiagramOutput(
                paper_id=uuid.UUID(paper_id) if paper_id else uuid.uuid4(),
                diagram_type=diagram_type,
                dsl_code=dsl,
                svg_path=svg_path,
                dsl_language="mermaid",
            )
            diagrams.append(diagram)

            if paper_id:
                _store_diagram(paper_id, diagram)

            log.info(
                "diagram_node.diagram_done",
                run_id=run_id,
                diagram_type=diagram_type.value,
                has_svg=svg_path is not None,
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

        log.info(
            "diagram_node.completed",
            run_id=run_id,
            count=len(diagrams),
        )

        return {
            "diagrams": diagrams,
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("diagram_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors, "diagrams": []}
