"""
pipeline.graph.nodes.codegen
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``codegen_node`` — generates a PyTorch implementation skeleton from the paper.

Responsibilities
----------------
1. Works from ``state["extraction"]``.
2. Renders ``codegen_v1.j2`` with architecture, training, and dataset info.
3. Sends to Gemini via LiteLLM — returns Python source code.
4. Validates with ``ast.parse()``; retries with syntax error feedback.
5. Exports ``.py`` file and Jupyter notebook via ``nbformat``.
6. Uploads both to Supabase Storage ``outputs`` bucket.
7. Stores ``CodeOutput`` record in DB.
8. Updates state with ``code_output``.
9. Emits ``STAGE_COMPLETED`` event.
"""

from __future__ import annotations

import ast
import json
import re
import uuid
from pathlib import Path
from typing import Any

import nbformat  # type: ignore[import-untyped]
import litellm  # type: ignore[import-untyped]
from pydantic import BaseModel, Field


from jinja2 import Environment
from src.db.engine import get_supabase_client

from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.telemetry import TelemetryCollector, track_llm_call
from src.core.utils import extract_json
from src.db.models import OutputORM
from src.graph.state import PipelineState
from src.domains.ai_ml.schema import AiMlExtraction
from src.models.output import CodeOutput
from src.models.run import StageStatus
from src.core.events import Event, EventType, default_bus

_STAGE = "codegen"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "codegen_v1.j2"
_OUTPUTS_BUCKET = "outputs"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class CodegenResponse(BaseModel):
    """Structured response for generated Python code."""

    python_code: str = Field(
        ..., description="The complete Python code for implementing the model."
    )


# ---------------------------------------------------------------------------
# Python validation
# ---------------------------------------------------------------------------


def _validate_python(code: str) -> tuple[bool, str]:
    """Basic structural validation of generated Python code."""
    if not code.strip():
        return False, "Empty code generated."

    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"SyntaxError at line {exc.lineno}: {exc.msg}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _render_prompt(extraction: AiMlExtraction) -> str:
    """Render codegen_v1.j2 with extraction data."""
    import aiofiles  # type: ignore[import-untyped]

    async with aiofiles.open(_PROMPT_PATH, mode="r", encoding="utf-8") as f:
        template_str = await f.read()

    env = Environment(autoescape=False)
    template = env.from_string(template_str)
    return template.render(
        task=extraction.task,
        proposed_method_summary=extraction.proposed_method_summary,
        architecture_components=[
            c.model_dump() for c in extraction.architecture_components
        ],
        training_procedure=extraction.training_procedure,
        loss_functions=extraction.loss_functions,
        datasets=[d.model_dump() for d in extraction.datasets],
    )


async def _call_gemini_codegen(
    prompt: str,
    run_id: str,
    collector: TelemetryCollector,
    max_retries: int = 3,
) -> str:
    """Call Gemini to generate implementation code, with retry on syntax failure."""
    settings = get_settings()
    model = settings.gemini.default_model

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    for attempt in range(1, max_retries + 1):
        with track_llm_call(collector, stage_name=_STAGE, model=model) as ctx:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=settings.gemini.temperature,
                max_tokens=settings.gemini.max_output_tokens,
                num_retries=3,
                api_key=settings.gemini.api_key.get_secret_value(),
                # NOTE: No response_format — the prompt asks for raw Python code.
                # JSON mode wraps the code in a JSON string, breaking ast.parse.
            )
            ctx.set_response(response)

        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown fences if present
        code = raw
        if code.startswith("```"):
            code = re.sub(r"^```[a-z]*\n?", "", code)
            code = re.sub(r"\n?```$", "", code)
            code = code.strip()

        # Fallback: if model wrapped in JSON despite instructions, extract it
        if not code.strip().startswith(("import ", "from ", "#", "class ", "def ")):
            try:
                cleaned = extract_json(raw)
                data = json.loads(cleaned)
                validated = CodegenResponse.model_validate(data)
                extracted = validated.python_code.strip()
                if extracted.startswith("```"):
                    extracted = re.sub(r"^```[a-z]*\n?", "", extracted)
                    extracted = re.sub(r"\n?```$", "", extracted)
                code = extracted.strip()
            except Exception:
                pass  # Keep raw code

        is_valid, error_msg = _validate_python(code)

        if is_valid:
            log.info("codegen_node.code_valid", run_id=run_id, attempt=attempt)
            return code

        log.warning(
            "codegen_node.code_invalid",
            run_id=run_id,
            attempt=attempt,
            error=error_msg,
        )

        if attempt < max_retries:
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The Python code you produced has a syntax error: {error_msg}\n"
                        "Please fix the syntax error and return ONLY valid Python code. "
                        "No markdown fences, no explanations."
                    ),
                }
            )

    log.error("codegen_node.code_invalid_after_retries", run_id=run_id)
    return raw  # Return best-effort code


def _build_notebook(python_code: str, paper_metadata: Any | None) -> bytes:
    """Wrap Python source into a basic Jupyter Notebook structure (.ipynb)."""
    nb = nbformat.v4.new_notebook()

    # Title & Metadata
    title = "Research Implementation"
    if paper_metadata:
        if hasattr(paper_metadata, "title"):
            title = getattr(paper_metadata, "title")
        elif isinstance(paper_metadata, dict):
            title = paper_metadata.get("title", title)

    nb.cells.append(
        nbformat.v4.new_markdown_cell(
            f"# {title}\nGenerated by Research Pilot pipeline"
        )
    )

    # Parse and split code by top-level blocks for readability
    lines = python_code.splitlines(keepends=True)
    current_block: list[str] = []
    for line in lines:
        if line.startswith(("class ", "def ", "import ", "from ")):
            if current_block:
                nb.cells.append(
                    nbformat.v4.new_code_cell("".join(current_block).strip())
                )
            current_block = []
        current_block.append(line)

    if current_block:
        nb.cells.append(nbformat.v4.new_code_cell("".join(current_block).strip()))

    return nbformat.writes(nb).encode("utf-8")


async def _upload_artefacts(
    paper_id: str,
    python_code: str,
    notebook_bytes: bytes,
) -> tuple[str | None, str | None]:
    """Upload .py and .ipynb to Supabase Storage, return (py_path, nb_path)."""
    import asyncio

    def _do_upload() -> tuple[str | None, str | None]:
        try:
            client = get_supabase_client()

            py_path = f"{paper_id}/code/model.py"
            nb_path = f"{paper_id}/code/model.ipynb"

            client.storage.from_(_OUTPUTS_BUCKET).upload(
                path=py_path,
                file=python_code.encode("utf-8"),
                file_options={"content-type": "text/x-python"},
            )
            client.storage.from_(_OUTPUTS_BUCKET).upload(
                path=nb_path,
                file=notebook_bytes,
                file_options={"content-type": "application/json"},
            )

            return py_path, nb_path

        except Exception as exc:  # noqa: BLE001
            log.warning("codegen_upload_skipped", reason=str(exc))
            return None, None

    return await asyncio.to_thread(_do_upload)


async def _store_code_output(paper_id: str, code_output: CodeOutput) -> None:
    """Persist CodeOutput record to the ``outputs`` table."""
    try:
        from src.db.session import get_db_context

        async with get_db_context() as session:
            row = OutputORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                output_type="codegen",
                storage_path=code_output.python_path or "inline:model.py",
            )
            session.add(row)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("codegen_store_failed", reason=str(exc))


async def _load_cached_code(paper_id: str) -> CodeOutput | None:
    """Return a cached ``CodeOutput`` if one exists in the DB."""
    try:
        from src.db.session import get_db_context
        from src.db.models import OutputORM
        from sqlalchemy import select
        import uuid

        async with get_db_context() as session:
            stmt = (
                select(OutputORM.storage_path)
                .where(OutputORM.paper_id == uuid.UUID(paper_id))
                .where(OutputORM.output_type == "codegen")
                .limit(1)
            )
            res = await session.execute(stmt)
            path = res.scalar_one_or_none()
            if path:
                return CodeOutput(
                    paper_id=uuid.UUID(paper_id),
                    python_path=path if not path.startswith("inline:") else None,
                    notebook_path=None,
                    synthetic_data_description=None,
                )
    except Exception as exc:  # noqa: BLE001
        log.debug("codegen_cache_miss", reason=str(exc))
    return None


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


async def codegen_node(state: PipelineState) -> dict[str, Any]:
    """Generate a PyTorch implementation skeleton for the paper.

    Reads from state
    ----------------
    - ``run_id``, ``paper_id``, ``extraction``, ``paper_metadata``

    Writes to state
    ---------------
    - ``code_output``
    - ``stage_statuses["codegen"]``
    - ``token_usage["codegen"]``
    - ``errors`` — appended on failure
    """
    run_id = state["run_id"]
    paper_id: str | None = state.get("paper_id")
    extraction: AiMlExtraction | None = state.get("extraction")
    paper_metadata = state.get("paper_metadata")
    errors: list[str] = list(state.get("errors", []))
    stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
    token_usage: dict[str, int] = dict(state.get("token_usage", {}))

    log.info("codegen_node.started", run_id=run_id)
    stage_statuses[_STAGE] = StageStatus.RUNNING

    cached_stages: set[str] = set(state.get("cached_stages", set()))

    # ── 1. Cache check ───────────────────────────────────────────────────────
    from src.core.config import get_settings

    settings = get_settings()

    if settings.pipeline.cache_enabled and paper_id:
        cached_code = await _load_cached_code(paper_id)
        if cached_code:
            log.info("codegen_node.cache_hit", run_id=run_id)
            stage_statuses[_STAGE] = StageStatus.CACHED
            cached_stages.add(_STAGE)

            default_bus.emit(
                Event(
                    type=EventType.STAGE_COMPLETED,
                    run_id=run_id,
                    stage_name=_STAGE,
                    payload={"cached": True},
                )
            )
            return {
                "code_output": cached_code,
                "stage_statuses": stage_statuses,
                "cached_stages": cached_stages,
            }

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("codegen_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors, "code_output": None}

    try:
        settings = get_settings()
        collector = TelemetryCollector(run_id=run_id, paper_id=paper_id)

        # ── 1. Render prompt and generate code ───────────────────────────
        prompt = await _render_prompt(extraction)
        python_code = await _call_gemini_codegen(
            prompt, run_id, collector, max_retries=settings.gemini.max_retries
        )

        token_usage[_STAGE] = collector.total_tokens

        # ── 2. Build notebook ────────────────────────────────────────────
        notebook_bytes = _build_notebook(python_code, paper_metadata)

        # ── 3. Upload artefacts ──────────────────────────────────────────
        py_path, nb_path = None, None
        if paper_id:
            py_path, nb_path = await _upload_artefacts(
                paper_id, python_code, notebook_bytes
            )

        # ── 4. Build CodeOutput ──────────────────────────────────────────
        paper_uuid = uuid.UUID(paper_id) if paper_id else uuid.uuid4()
        code_output = CodeOutput(
            paper_id=paper_uuid,
            python_path=py_path,
            notebook_path=nb_path,
            synthetic_data_description=(
                "Synthetic data generation function included in the generated script. "
                "Inputs are shaped to match the paper's described input format using NumPy."
            ),
        )

        if paper_id:
            await _store_code_output(paper_id, code_output)

        # ── 5. Emit event ────────────────────────────────────────────────
        stage_statuses[_STAGE] = StageStatus.COMPLETED
        default_bus.emit(
            Event(
                type=EventType.STAGE_COMPLETED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={
                    "py_path": py_path,
                    "nb_path": nb_path,
                    "tokens": token_usage[_STAGE],
                },
            )
        )

        log.info(
            "codegen_node.completed",
            run_id=run_id,
            py_path=py_path,
            tokens=token_usage[_STAGE],
        )

        return {
            "code_output": code_output,
            "stage_statuses": stage_statuses,
            "token_usage": token_usage,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001
        msg = f"[{_STAGE}] {exc}"
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.FAILED
        log.exception("codegen_node.failed", run_id=run_id, error=str(exc))
        default_bus.emit(
            Event(
                type=EventType.STAGE_FAILED,
                run_id=run_id,
                stage_name=_STAGE,
                payload={"error": str(exc)},
            )
        )
        return {"stage_statuses": stage_statuses, "errors": errors, "code_output": None}
