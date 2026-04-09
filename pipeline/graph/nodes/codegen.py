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
import uuid
from pathlib import Path
from typing import Any

from pipeline.core.events import Event, EventType, default_bus
from pipeline.core.logger import get_logger
from pipeline.core.telemetry import TelemetryCollector, track_llm_call
from pipeline.graph.state import PipelineState
from pipeline.domains.ai_ml.schema import AiMlExtraction
from pipeline.models.output import CodeOutput
from pipeline.models.run import StageStatus

_STAGE = "codegen"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "codegen_v1.j2"
_OUTPUTS_BUCKET = "outputs"

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_prompt(extraction: AiMlExtraction) -> str:
    """Render codegen_v1.j2 with extraction data."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(_PROMPT_PATH.parent)),
        autoescape=False,
    )
    template = env.get_template(_PROMPT_PATH.name)
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


def _validate_python(code: str) -> tuple[bool, str]:
    """Validate Python source using the built-in AST parser.

    Returns
    -------
    (is_valid, error_message)
    """
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"SyntaxError at line {exc.lineno}: {exc.msg}"


def _call_gemini_codegen(
    prompt: str,
    run_id: str,
    collector: TelemetryCollector,
    max_retries: int = 3,
) -> str:
    """Call Gemini to generate Python code, retrying on syntax errors."""
    import litellm  # type: ignore[import-untyped]

    from pipeline.core.config import get_settings

    settings = get_settings()
    model = settings.gemini.default_model

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    for attempt in range(1, max_retries + 1):
        with track_llm_call(collector, stage_name=_STAGE, model=model) as ctx:
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=settings.gemini.max_output_tokens,
                api_key=settings.gemini.api_key.get_secret_value(),
            )
            ctx.set_response(response)

        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown fences
        if raw.startswith("```"):
            import re

            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            raw = raw.strip()

        is_valid, error_msg = _validate_python(raw)

        if is_valid:
            log.info("codegen_node.code_valid", run_id=run_id, attempt=attempt)
            return raw

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


def _build_notebook(python_code: str, title: str) -> bytes:
    """Convert Python source to a Jupyter notebook (.ipynb) as bytes."""
    import nbformat  # type: ignore[import-untyped]

    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb.metadata["language_info"] = {"name": "python", "version": "3.12.0"}

    # Title cell
    nb.cells.append(
        nbformat.v4.new_markdown_cell(f"# {title}\n\nAuto-generated by Research Pilot.")
    )

    # Split code into logical sections at class/function boundaries
    lines = python_code.splitlines(keepends=True)
    current_block: list[str] = []

    for line in lines:
        if (
            line.startswith(("class ", "def ", "# ----", "if __name__"))
            and current_block
        ):
            nb.cells.append(nbformat.v4.new_code_cell("".join(current_block).strip()))
            current_block = []
        current_block.append(line)

    if current_block:
        nb.cells.append(nbformat.v4.new_code_cell("".join(current_block).strip()))

    return nbformat.writes(nb).encode("utf-8")


def _upload_artefacts(
    paper_id: str,
    python_code: str,
    notebook_bytes: bytes,
) -> tuple[str | None, str | None]:
    """Upload .py and .ipynb to Supabase Storage, return (py_path, nb_path)."""
    try:
        from pipeline.core.config import get_settings
        from supabase import create_client  # type: ignore[import-untyped]

        settings = get_settings()
        client = create_client(
            settings.supabase.url,
            settings.supabase.service_role_key.get_secret_value(),
        )

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


def _store_code_output(paper_id: str, code_output: CodeOutput) -> None:
    """Persist CodeOutput record to the ``outputs`` table."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from pipeline.core.config import get_settings
        from pipeline.db.models import OutputORM

        settings = get_settings()
        engine = create_engine(
            settings.supabase.db_url.get_secret_value(), pool_pre_ping=True
        )
        with Session(engine) as session:
            row = OutputORM(
                id=uuid.uuid4(),
                paper_id=uuid.UUID(paper_id),
                output_type="codegen",
                storage_path=code_output.python_path or "inline:model.py",
            )
            session.add(row)
            session.commit()
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        log.warning("codegen_store_failed", reason=str(exc))


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------


def codegen_node(state: PipelineState) -> dict[str, Any]:
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

    if extraction is None:
        msg = f"[{_STAGE}] extraction is None — skipping."
        errors.append(msg)
        stage_statuses[_STAGE] = StageStatus.SKIPPED
        log.warning("codegen_node.skipped", run_id=run_id, reason="no extraction")
        return {"stage_statuses": stage_statuses, "errors": errors, "code_output": None}

    try:
        from pipeline.core.config import get_settings

        settings = get_settings()
        collector = TelemetryCollector(run_id=run_id)

        # ── 1. Render prompt and generate code ───────────────────────────
        prompt = _render_prompt(extraction)
        python_code = _call_gemini_codegen(
            prompt, run_id, collector, max_retries=settings.gemini.max_retries
        )

        token_usage[_STAGE] = collector.total_tokens

        # ── 2. Build notebook ────────────────────────────────────────────
        title = (
            paper_metadata.title if paper_metadata else "Research Pilot Generated Model"
        )
        notebook_bytes = _build_notebook(python_code, title)

        # ── 3. Upload artefacts ──────────────────────────────────────────
        py_path, nb_path = None, None
        if paper_id:
            py_path, nb_path = _upload_artefacts(paper_id, python_code, notebook_bytes)

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
            _store_code_output(paper_id, code_output)

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
