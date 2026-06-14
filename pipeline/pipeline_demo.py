"""
ResearchPilot — Interactive Pipeline Demo
==========================================

Runs the FULL LangGraph pipeline end-to-end, bypassing the HTTP API layer
and calling services + the compiled graph directly. Every branch of the
graph is exercised:

  Branch A — Full run (high-confidence domain paper)
      arXiv "Attention Is All You Need"
      ingest → classify → extract → summarise → embed → diagram → codegen → report

  Branch B — Theory-domain paper (codegen skipped)
      arXiv "PAC Learning" (statistical learning theory)
      ingest → classify → extract → summarise → embed → diagram → report

  Branch C — Low-confidence early exit
      A manually crafted paper whose domain is deliberately vague so
      classify confidence drops below 0.5, routing straight to END.

Results from every stage are printed to the console so you can inspect
real LLM output, token counts, generated code, diagram specs, and more.

Prerequisites
-------------
1. `.env` configured with real GEMINI_API_KEY and SUPABASE_* keys.
2. Alembic migrations applied:
       uv run alembic upgrade head
3. Run from inside the pipeline/ directory:
       uv run python pipeline_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# ── rich console helpers ────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RED = "\033[91m"
RESET = "\033[0m"
LINE = "─" * 68


def _h1(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'═' * 68}")
    print(f"  {title}")
    print(f"{'═' * 68}{RESET}")


def _h2(title: str) -> None:
    print(f"\n{BOLD}{YELLOW}{LINE}")
    print(f"  {title}")
    print(f"{LINE}{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def _err(msg: str) -> None:
    print(f"  {RED}✗{RESET}  {msg}")


def _field(label: str, value: Any, indent: int = 4) -> None:
    pad = " " * indent
    val_str = str(value) if not isinstance(value, str) else value
    wrapped = textwrap.fill(val_str, width=90, subsequent_indent=pad + "  ")
    print(f"{pad}{BOLD}{label}:{RESET} {wrapped}")


def _section(title: str) -> None:
    print(f"\n  {MAGENTA}{BOLD}▸ {title}{RESET}")


# ── import pipeline internals ───────────────────────────────────────────────
try:
    from src.core.config import get_settings
    from src.db.session import get_db_context
    from src.graph.pipeline import research_pipeline
    from src.graph.state import PipelineState, make_initial_state
    from src.models.paper import PaperMetadata, PaperSource
    from src.models.run import StageStatus
    from src.services.paper_service import PaperService
except ImportError as exc:
    print(f"\n{RED}Import error: {exc}")
    print(
        "Make sure you are running from the pipeline/ directory with: uv run python pipeline_demo.py{RESET}\n"
    )
    sys.exit(1)


# ───────────────────────────────────────────────────────────────────────────
# State printer
# ───────────────────────────────────────────────────────────────────────────


def print_state_summary(
    state: PipelineState, title: str = "Final Pipeline State"
) -> None:
    _h2(title)

    # Stage statuses
    _section("Stage Statuses")
    statuses: dict[str, StageStatus] = state.get("stage_statuses", {})
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
    for stage_name in ordered:
        st_status = statuses.get(stage_name)
        if st_status is None:
            continue
        cached = stage_name in state.get("cached_stages", set())
        colour = (
            GREEN
            if st_status == StageStatus.COMPLETED
            else (RED if st_status == StageStatus.FAILED else YELLOW)
        )
        cached_tag = f"{DIM} [cached]{RESET}" if cached else ""
        tokens = state.get("token_usage", {}).get(stage_name, 0)
        tok_tag = f"  {DIM}{tokens:,} tokens{RESET}" if tokens else ""
        print(
            f"    {colour}{st_status.value:12s}{RESET}  {stage_name}{cached_tag}{tok_tag}"
        )

    # Errors
    errors: list[str] = state.get("errors", [])
    if errors:
        _section("Errors")
        for e in errors:
            _err(e)

    # Classification
    if state.get("domain"):
        _section("Classification")
        _field("domain", state.get("domain", "—"))
        _field("sub_domain", state.get("sub_domain", "—"))
        _field("confidence", f"{state.get('classification_confidence', 0):.2%}")

    # Extraction highlights
    extraction = state.get("extraction")
    if extraction:
        _section("Extraction Highlights")
        if hasattr(extraction, "contributions"):
            for i, c in enumerate(extraction.contributions[:3], 1):
                _field(f"contribution {i}", c)
        if hasattr(extraction, "novelties"):
            for i, n in enumerate(extraction.novelties[:2], 1):
                _field(f"novelty {i}", n)

    # Summaries
    summaries = state.get("summaries", [])
    if summaries:
        _section("Summaries")
        for summary in summaries:
            level = getattr(summary, "level", "?")
            text = getattr(summary, "text", "") or ""
            print(f"    {BOLD}[{level}]{RESET}")
            print(
                textwrap.fill(
                    text[:600] + ("…" if len(text) > 600 else ""),
                    width=88,
                    initial_indent="      ",
                    subsequent_indent="      ",
                )
            )

    # Diagrams
    diagrams = state.get("diagrams", [])
    if diagrams:
        _section(f"Diagrams ({len(diagrams)} generated)")
        for d in diagrams:
            dtype = getattr(d, "diagram_type", "?")
            path = getattr(d, "storage_path", "")
            print(f"    {BOLD}{dtype}{RESET}  →  {DIM}{path}{RESET}")

    # Code output
    code_output = state.get("code_output")
    if code_output:
        _section("Code Output")
        py_path = getattr(code_output, "py_storage_path", None)
        nb_path = getattr(code_output, "notebook_storage_path", None)
        if py_path:
            _field(".py file", py_path)
        if nb_path:
            _field(".ipynb notebook", nb_path)
        snippet = getattr(code_output, "snippet", None) or ""
        if snippet:
            print(f"    {BOLD}Code preview:{RESET}")
            for line in snippet.splitlines()[:12]:
                print(f"      {DIM}{line}{RESET}")

    # Report
    report_path = state.get("report_path")
    if report_path:
        _section("Report")
        _field("storage path", report_path)

    # Token totals
    total_tokens = sum(state.get("token_usage", {}).values())
    if total_tokens:
        print(f"\n  {DIM}Total tokens consumed: {total_tokens:,}{RESET}")


# ───────────────────────────────────────────────────────────────────────────
# Demo scenario runner
# ───────────────────────────────────────────────────────────────────────────


@dataclass
class Scenario:
    label: str
    description: str
    arxiv_url: str | None = None
    paper_metadata: PaperMetadata | None = None  # used when no arxiv_url
    pdf_bytes: bytes | None = None  # pre-supplied PDF (e.g. stub for Branch C)
    expected_branch: str = "full"  # full | theory | early_exit


async def run_scenario(scenario: Scenario) -> PipelineState:
    """Ingest a paper via PaperService then run the graph directly."""
    print(f"\n  Source: {DIM}{scenario.arxiv_url or 'manual metadata'}{RESET}")
    print(f"  Expected branch: {BOLD}{scenario.expected_branch}{RESET}")

    # ── 1. Ingest the paper ─────────────────────────────────────────────────
    async with get_db_context() as db:
        paper_svc = PaperService(db)

        if scenario.arxiv_url:
            _ok("Fetching metadata from arXiv …")
            t0 = time.perf_counter()
            paper = await paper_svc.create_from_arxiv(scenario.arxiv_url)
            elapsed = (time.perf_counter() - t0) * 1000
            _ok(f"Paper ingested in {elapsed:.0f}ms  │  id={paper.id}")
            if paper.metadata:
                _field("title", paper.metadata.title)
                _field("authors", ", ".join(paper.metadata.authors[:3]))
                _field("year", paper.metadata.year or "—")
        else:
            # Synthetic paper with user-supplied metadata
            _ok("Creating synthetic paper record …")
            from src.db.models import PaperORM
            from datetime import datetime, timezone
            import uuid as _uuid

            paper_id = _uuid.uuid4()
            orm = PaperORM(
                id=paper_id,
                source=PaperSource.PDF_UPLOAD.value,
                source_url=None,
                pdf_storage_path=None,
                metadata_=scenario.paper_metadata.model_dump()
                if scenario.paper_metadata
                else None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(orm)
            await db.commit()
            await db.refresh(orm)
            from src.models.paper import Paper

            paper = Paper(
                id=orm.id,
                source=PaperSource.PDF_UPLOAD,
                source_url=None,
                pdf_storage_path=None,
                metadata=scenario.paper_metadata,
                created_at=orm.created_at.replace(tzinfo=timezone.utc),
                updated_at=orm.updated_at.replace(tzinfo=timezone.utc),
                user_id=None,
                is_public=False,
                published_at=None,
                imported_from_paper_id=None,
            )
            _ok(f"Synthetic paper created  │  id={paper.id}")
            if paper.metadata:
                _field("title", paper.metadata.title)

        # ── 2. Build initial state ───────────────────────────────────────────
        run_id = str(uuid.uuid4())
        initial_state = make_initial_state(
            run_id=run_id,
            paper_metadata=paper.metadata,
            pdf_bytes=scenario.pdf_bytes,  # None for arXiv scenarios; stub for Branch C
            extra={
                "paper_id": str(paper.id),
                "pdf_storage_path": paper.pdf_storage_path,
            },
        )

    # ── 3. Run the graph (outside the DB context — nodes open own sessions) ──
    _ok(f"Starting LangGraph pipeline  │  run_id={run_id}")
    print(f"\n  {'─' * 60}")

    t0 = time.perf_counter()
    final_state: PipelineState = await research_pipeline.ainvoke(initial_state)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - t0
    print(f"\n  {'─' * 60}")
    _ok(f"Pipeline finished in {elapsed:.1f}s")

    return final_state


# ───────────────────────────────────────────────────────────────────────────
# Scenarios
# ───────────────────────────────────────────────────────────────────────────

SCENARIOS: list[Scenario] = [
    # ── Branch A: Full pipeline (deep-learning architecture paper) ──────────
    Scenario(
        label="Branch A — Full Pipeline",
        description=(
            "Transformer architecture paper. High classification confidence is "
            "expected → all 8 stages run including codegen."
        ),
        arxiv_url="https://arxiv.org/abs/1706.03762",  # Attention Is All You Need
        expected_branch="full",
    ),
    # # ── Branch B: Theory domain → codegen skipped ──────────────────────────
    # Scenario(
    #     label="Branch B — Theory Domain (codegen skipped)",
    #     description=(
    #         "Statistical learning theory paper. should_run_codegen() detects "
    #         "a theory sub-domain and routes diagram → report, skipping codegen."
    #     ),
    #     arxiv_url="https://arxiv.org/abs/1301.3666",  # A Few Useful Things to Know About ML
    #     expected_branch="theory",
    # ),
    # # ── Branch C: Low-confidence early exit ─────────────────────────────────
    # Scenario(
    #     label="Branch C — Low-Confidence Early Exit",
    #     description=(
    #         "A vague, interdisciplinary abstract that intentionally resists "
    #         "classification. should_continue_after_classify() fires __end__ "
    #         "when confidence < 0.5."
    #     ),
    #     paper_metadata=PaperMetadata(
    #         title="On the Nature of Information in Complex Adaptive Systems: "
    #         "A Philosophical and Interdisciplinary Overview",
    #         authors=["J. Doe", "A. Smith"],
    #         abstract=(
    #             "This speculative position paper explores loose connections between "
    #             "thermodynamic entropy, consciousness studies, economic market dynamics, "
    #             "literary criticism, and music theory. No formal model is presented. "
    #             "The work is intentionally broad and non-committal. "
    #             "No specific algorithm, dataset, or benchmark is discussed."
    #         ),
    #         year=2024,
    #         arxiv_id=None,
    #         doi=None,
    #         venue=None,
    #         page_count=6,
    #         domain=None,
    #         sub_domain=None,
    #     ),
    #     # Minimal valid PDF stub so ingest_node can proceed to classify.
    #     # The early-exit fires at classify (low confidence), not at ingest.
    #     pdf_bytes=b"%PDF-1.0\n1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj "
    #     b"2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj "
    #     b"3 0 obj<</Type /Page /MediaBox [0 0 3 3]>>endobj\n"
    #     b"xref\n0 4\n0000000000 65535 f\n"
    #     b"trailer<</Size 4 /Root 1 0 R>>\nstartxref\n0\n%%EOF",
    #     expected_branch="early_exit",
    # ),
]


# ───────────────────────────────────────────────────────────────────────────
# Main entrypoint
# ───────────────────────────────────────────────────────────────────────────


async def main() -> None:
    _h1("ResearchPilot — Pipeline Demo  (direct service calls)")
    settings = get_settings()
    print(f"  environment : {settings.environment}")
    print(f"  gemini model: {settings.llm.model}")
    print(f"  langfuse    : {'enabled' if settings.langfuse.enabled else 'disabled'}")
    print(f"  scenarios   : {len(SCENARIOS)}")
    print(f"  started at  : {datetime.now().strftime('%H:%M:%S')}")

    results: list[tuple[Scenario, PipelineState | None, str]] = []

    for i, scenario in enumerate(SCENARIOS, 1):
        _h1(f"Scenario {i}/{len(SCENARIOS)} — {scenario.label}")
        print(f"  {DIM}{scenario.description}{RESET}")

        try:
            final_state = await run_scenario(scenario)
            print_state_summary(final_state, title=f"Results — {scenario.label}")
            results.append((scenario, final_state, "ok"))
        except Exception as exc:
            _err(f"Scenario failed with unhandled exception: {exc}")
            import traceback

            traceback.print_exc()
            results.append((scenario, None, str(exc)))

        print()  # spacer

    # ── Overall summary ──────────────────────────────────────────────────────
    _h1("Demo Complete — Summary")
    for scenario, state_opt, status in results:
        # Avoid TypedDict assignment issues by using simple conditional access
        if state_opt is not None:
            st_map = state_opt.get("stage_statuses", {})
            stages_run = [k for k, v in st_map.items() if v != StageStatus.FAILED]
            token_map = state_opt.get("token_usage", {})
            total_tok = sum(token_map.values())
        else:
            stages_run = []
            total_tok = 0

        colour = GREEN if status == "ok" else RED
        print(f"\n  {colour}{BOLD}{scenario.label}{RESET}")
        print(f"    status      : {colour}{status}{RESET}")
        print(f"    stages run  : {', '.join(stages_run) or '—'}")
        print(f"    total tokens: {total_tok:,}")

    print(f"\n  {DIM}Finished at {datetime.now().strftime('%H:%M:%S')}{RESET}\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        # Psycopg 3 + SQLAlchemy async requires SelectorEventLoop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
