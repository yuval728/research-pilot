"""
ResearchPilot — Output Quality Inspector
=========================================

Runs the full pipeline on a single arXiv paper and then prints EVERY piece
of output in its entirety — full summary text per level, full Mermaid DSL
per diagram type, full generated Python code, and the full Markdown report —
so you can judge the quality of each LLM output directly.

Run
---
    cd pipeline
    uv run python pipeline_demo.py

Optionally set the paper to inspect:
    $env:DEMO_ARXIV_URL="https://arxiv.org/abs/xxxx.xxxxx"
    uv run python pipeline_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap
import uuid
from datetime import datetime

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError with box-drawing chars)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# ── ANSI colours ────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def _banner(text: str, char: str = "═") -> None:
    w = 72
    print(f"\n{BOLD}{CYAN}{char * w}\n  {text}\n{char * w}{RESET}")


def _section(title: str, colour: str = MAGENTA) -> None:
    print(f"\n{colour}{BOLD}{'─' * 68}")
    print(f"  {title}")
    print(f"{'─' * 68}{RESET}")


def _tag(label: str, colour: str = YELLOW) -> None:
    print(f"\n{colour}{BOLD}┌─ {label} {'─' * (60 - len(label))}┐{RESET}")


def _end_tag(colour: str = YELLOW) -> None:
    print(f"{colour}{BOLD}└{'─' * 67}┘{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def _info(msg: str) -> None:
    print(f"  {CYAN}·{RESET}  {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def _err(msg: str) -> None:
    print(f"  {RED}✗{RESET}  {msg}")


def _kv(key: str, val: str, indent: int = 4) -> None:
    pad = " " * indent
    wrapped = textwrap.fill(
        str(val), width=90, initial_indent="", subsequent_indent=pad + "  "
    )
    print(f"{pad}{BOLD}{key}:{RESET} {wrapped}")


def _block(text: str, label: str | None = None, max_lines: int | None = None) -> None:
    lines = text.splitlines()
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines] + [
            f"{DIM}  … ({len(lines) - max_lines} more lines){RESET}"
        ]
    if label:
        print(f"  {BOLD}{label}{RESET}")
    for line in lines:
        print(f"  {DIM}│{RESET} {line}")


# ── imports ──────────────────────────────────────────────────────────────────
try:
    from src.core.config import get_settings
    from src.db.session import get_db_context
    from src.graph.pipeline import research_pipeline
    from src.graph.state import PipelineState, make_initial_state
    from src.domains.ai_ml.schema import AiMlExtraction
    from src.models.output import DiagramType, SummaryLevel
    from src.models.run import StageStatus
    from src.services.paper_service import PaperService
except ImportError as exc:
    print(f"\n{RED}Import error: {exc}")
    print("Run from pipeline/ directory:  uv run python pipeline_demo.py{RESET}\n")
    sys.exit(1)

ARXIV_URL = os.getenv(
    "DEMO_ARXIV_URL",
    "https://arxiv.org/abs/1706.03762",  # Attention Is All You Need
)


# ────────────────────────────────────────────────────────────────────────────
# 1. Ingest paper
# ────────────────────────────────────────────────────────────────────────────


async def ingest_paper() -> tuple[str, PipelineState]:
    """Create DB paper record, build initial state, run the pipeline."""
    async with get_db_context() as db:
        svc = PaperService(db)
        _info(f"Fetching arXiv metadata for: {ARXIV_URL}")
        paper = await svc.create_from_arxiv(ARXIV_URL)
        _ok(f"Paper ingested  │  id = {paper.id}")
        if paper.metadata:
            _kv("title", paper.metadata.title)
            _kv("authors", ", ".join(paper.metadata.authors[:5]))
            _kv("year", str(paper.metadata.year or "—"))

        run_id = str(uuid.uuid4())
        state = make_initial_state(
            run_id=run_id,
            paper_metadata=paper.metadata,
            extra={
                "paper_id": str(paper.id),
                "pdf_storage_path": paper.pdf_storage_path,
            },
        )
        return run_id, state


# ────────────────────────────────────────────────────────────────────────────
# 2. Run pipeline
# ────────────────────────────────────────────────────────────────────────────


async def run_pipeline(state: PipelineState) -> PipelineState:
    import time

    _info("Invoking LangGraph pipeline …")
    print()
    t0 = time.perf_counter()
    final: PipelineState = await research_pipeline.ainvoke(state)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - t0
    print()
    _ok(f"Pipeline finished in {elapsed:.1f}s")
    return final


# ────────────────────────────────────────────────────────────────────────────
# 3. Quality inspection — each output in full detail
# ────────────────────────────────────────────────────────────────────────────


def inspect_stages(state: PipelineState) -> None:
    _banner("Stage Results", "─")
    statuses = state.get("stage_statuses", {})
    token_usage = state.get("token_usage", {})
    cached_stages = state.get("cached_stages", set())

    ordered = [
        "ingest",
        "classify",
        "extract",
        "summarise",
        "embed",
        "diagram",
        "codegen",
        "report",
    ]
    for stage in ordered:
        s = statuses.get(stage)
        if s is None:
            continue
        col = (
            GREEN
            if s == StageStatus.COMPLETED
            else (RED if s == StageStatus.FAILED else YELLOW)
        )
        cached = "  [cached]" if stage in cached_stages else ""
        tok = f"  {token_usage.get(stage, 0):,} tokens" if stage in token_usage else ""
        print(
            f"  {col}{s.value:12s}{RESET}  {BOLD}{stage}{RESET}{DIM}{cached}{tok}{RESET}"
        )

    errors = state.get("errors", [])
    if errors:
        print(f"\n  {RED}Errors:{RESET}")
        for e in errors:
            _err(e)


def inspect_classification(state: PipelineState) -> None:
    _banner("Classification", "─")
    _kv("domain", state.get("domain") or "—")
    _kv("sub_domain", state.get("sub_domain") or "—")
    _kv("confidence", f"{state.get('classification_confidence', 0):.2%}")


def inspect_extraction(state: PipelineState) -> None:
    _banner("Extraction", "─")
    ext = state.get("extraction")
    if ext is None:
        _warn("extraction is None")
        return

    if not isinstance(ext, AiMlExtraction):
        _warn(f"unexpected extraction type: {type(ext).__name__}")
        return

    _kv("task", ext.task or "—")
    _kv("proposed_method", ext.proposed_method_summary or "—")

    print(f"\n  {BOLD}Contributions ({len(ext.key_contributions)}){RESET}")
    for i, c in enumerate(ext.key_contributions, 1):
        print(f"    {i}. {c}")

    print(
        f"\n  {BOLD}Architecture Components ({len(ext.architecture_components)}){RESET}"
    )
    for comp in ext.architecture_components:
        print(f"    {CYAN}{BOLD}{comp.name}{RESET}")
        _kv("type", comp.type, indent=6)
        _kv("description", comp.description, indent=6)

    print(f"\n  {BOLD}Training Procedure{RESET}")
    tp = ext.training_procedure
    if tp:
        _kv("overview", tp)

    print(f"\n  {BOLD}Loss Functions ({len(ext.loss_functions)}){RESET}")
    for lf in ext.loss_functions:
        print(f"    • {lf}")

    print(f"\n  {BOLD}Datasets ({len(ext.datasets)}){RESET}")
    for d in ext.datasets:
        print(f"    {CYAN}{BOLD}{d.name}{RESET}")
        _kv("split", d.split_info or "—", indent=6)
        _kv("modality", d.modality or "—", indent=6)

    print(f"\n  {BOLD}Metrics{RESET}")
    for m in ext.evaluation_metrics:
        val_str = f" = {m.value}" if m.value is not None else ""
        print(f"    • {m.metric_name}{val_str}")

    if ext.limitations:
        print(f"\n  {BOLD}Limitations{RESET}")
        _kv("statement", ext.limitations)

    if ext.future_work:
        print(f"\n  {BOLD}Future Work{RESET}")
        _kv("statement", ext.future_work)


def inspect_summaries(state: PipelineState) -> None:
    _banner("Summaries — Full Text per Level", "─")
    summaries = state.get("summaries", [])
    if not summaries:
        _warn("No summaries generated")
        return

    label_map = {
        SummaryLevel.PARAGRAPH: ("Paragraph Summary", "A single cohesive paragraph."),
        SummaryLevel.SECTION_BY_SECTION: (
            "Section-by-Section",
            "Mirrors paper structure.",
        ),
        SummaryLevel.BULLETS: ("Bullet Points", "Concise bullet list."),
        SummaryLevel.ELI5: ("ELI5  (Explain Like I'm 5)", "Plain language for anyone."),
    }

    for s in summaries:
        title, subtitle = label_map.get(s.level, (s.level.value, ""))
        _tag(f"  {title}  —  {subtitle}")
        print()
        # Print FULL text — no truncation
        for line in s.content.splitlines():
            print(f"  {line}")
        print()
        _kv(
            "length",
            f"{len(s.content)} chars  /  {len(s.content.split())} words",
            indent=2,
        )
        _end_tag()


def inspect_diagrams(state: PipelineState) -> None:
    _banner("Diagrams — Full Mermaid DSL", "─")
    diagrams = state.get("diagrams", [])
    if not diagrams:
        _warn("No diagrams generated")
        return

    label_map = {
        DiagramType.ARCHITECTURE: "Architecture Diagram  (static model/system layout)",
        DiagramType.TRAINING_FLOW: "Training Flow  (training loop & data-flow graph)",
        DiagramType.INFERENCE_FLOW: "Inference Flow  (serving/prediction graph)",
    }

    for d in diagrams:
        label = label_map.get(d.diagram_type, d.diagram_type.value)
        _tag(label)
        print()
        # Print full Mermaid DSL
        for line in d.dsl_code.splitlines():
            print(f"  {CYAN}{line}{RESET}")
        print()
        _kv("svg uploaded", d.svg_path or "no  (mmdc not installed)", indent=2)
        _kv("dsl language", d.dsl_language, indent=2)
        _kv("dsl lines", str(len(d.dsl_code.splitlines())), indent=2)
        _end_tag()


def inspect_code(state: PipelineState) -> None:
    _banner("Generated Code — Full Python Source", "─")
    code_output = state.get("code_output")
    if code_output is None:
        _warn(
            "No code output (either codegen was skipped for a theory paper, or it failed)"
        )
        return

    _kv(".py path", code_output.python_path or "not uploaded")
    _kv(".ipynb path", code_output.notebook_path or "not uploaded")
    if code_output.synthetic_data_description:
        _kv("synthetic data", code_output.synthetic_data_description)

    # Try to retrieve the actual code from state extras (direct reference in memory)
    # The code lives in code_output but is not a field; it was uploaded to Supabase.
    # Instead, note the storage path clearly.
    print(
        f"\n  {YELLOW}To view the full Python code, download from Supabase Storage:{RESET}"
    )
    if code_output.python_path:
        settings = get_settings()
        print(f"  bucket  : {settings.supabase.outputs_bucket}")
        print(f"  path    : {code_output.python_path}")
        print(
            f"\n  Or visit: {settings.supabase.url}/storage/v1/object/public/"
            f"{settings.supabase.outputs_bucket}/{code_output.python_path}"
        )


def inspect_report(state: PipelineState) -> None:
    _banner("Report", "─")
    report_path = state.get("report_path")
    if not report_path:
        _warn("No report path in state")
        return
    _kv("storage path", report_path)
    settings = get_settings()
    print(
        f"\n  {YELLOW}Download the full Markdown report from Supabase Storage:{RESET}"
    )
    print(f"  bucket: {settings.supabase.outputs_bucket}")
    print(f"  path  : {report_path}")


def inspect_token_budget(state: PipelineState) -> None:
    _banner("Token Budget Breakdown", "─")
    usage = state.get("token_usage", {})
    if not usage:
        _warn("No token usage recorded")
        return

    total = sum(usage.values())
    print(f"\n  {'Stage':<20} {'Tokens':>10}  {'Share':>8}")
    print(f"  {'─' * 20} {'─' * 10}  {'─' * 8}")
    for stage, tokens in sorted(usage.items(), key=lambda x: -x[1]):
        share = tokens / total * 100 if total else 0
        bar = "█" * int(share / 2)
        print(f"  {stage:<20} {tokens:>10,}  {share:>7.1f}%  {CYAN}{bar}{RESET}")
    print(f"\n  {'TOTAL':<20} {total:>10,}")


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    _banner("ResearchPilot — Output Quality Inspector")
    settings = get_settings()
    print(f"  paper       : {ARXIV_URL}")
    print(f"  gemini model: {settings.llm.model}")
    print(f"  started     : {datetime.now().strftime('%H:%M:%S')}")

    # Step 1 — ingest
    _section("Step 1 — Paper Ingestion")
    run_id, initial_state = await ingest_paper()

    # Step 2 — run pipeline
    _section("Step 2 — Pipeline Execution")
    final_state = await run_pipeline(initial_state)

    # Step 3 — inspect every output
    _banner("OUTPUT QUALITY INSPECTION")

    inspect_stages(final_state)
    inspect_classification(final_state)
    inspect_extraction(final_state)
    inspect_summaries(final_state)
    inspect_diagrams(final_state)
    inspect_code(final_state)
    inspect_report(final_state)
    inspect_token_budget(final_state)

    _banner("Done", "═")
    print(f"  finished: {datetime.now().strftime('%H:%M:%S')}\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        # Psycopg 3 + SQLAlchemy async requires SelectorEventLoop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
