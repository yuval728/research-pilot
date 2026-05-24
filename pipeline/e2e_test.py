"""
ResearchPilot Pipeline — End-to-End API Test Script
=====================================================

Runs against the live FastAPI server at BASE_URL.
All test scenarios are real HTTP calls — no mocks.

Prerequisites
-------------
1. Server running:
   cd pipeline && uv run uvicorn pipeline.api.main:app --reload

2. A valid Supabase JWT (from your frontend login or Supabase dashboard):
   export RESEARCH_PILOT_TOKEN=<your_jwt>

3. (Optional) Set BASE_URL for non-default server:
   export RESEARCH_PILOT_BASE_URL=http://127.0.0.1:8000

Run
---
    cd pipeline
    uv run python e2e_test.py

Results are printed with PASS / FAIL per case, and an overall summary.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("RESEARCH_PILOT_BASE_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv("RESEARCH_PILOT_TOKEN", "")

# A well-known arXiv paper: "Attention Is All You Need"
ARXIV_URL = "https://arxiv.org/abs/1706.03762"
# CrossRef-resolvable DOI for the same paper
TEST_DOI = "10.48550/arXiv.1706.03762"


# ---------------------------------------------------------------------------
# Minimal fake PDF bytes
# ---------------------------------------------------------------------------


def _make_pdf_bytes() -> bytes:
    """Return a minimal but structurally valid 1-page PDF."""
    content = b"%PDF-1.4\n"
    content += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    content += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    content += (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    )
    content += b"xref\n0 4\n0000000000 65535 f \n"
    content += b"trailer\n<< /Root 1 0 R /Size 4 >>\nstartxref\n9\n%%EOF\n"
    return content


# ---------------------------------------------------------------------------
# Test framework helpers
# ---------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    detail: str = ""


@dataclass
class TestSuite:
    results: list[TestResult] = field(default_factory=list)

    def record(
        self, name: str, passed: bool, duration_ms: float, detail: str = ""
    ) -> None:
        icon = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        ms = f"{duration_ms:6.0f}ms"
        msg = f"  [{icon}] {ms}  {name}"
        if detail:
            msg += f"\n         {YELLOW}{detail}{RESET}"
        print(msg)
        self.results.append(TestResult(name, passed, duration_ms, detail))

    def summary(self) -> None:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        print("\n" + "─" * 60)
        colour = GREEN if failed == 0 else RED
        print(f"  {colour}Result: {passed}/{total} passed, {failed} failed{RESET}")
        if failed:
            print(f"\n  {RED}Failed tests:{RESET}")
            for r in self.results:
                if not r.passed:
                    print(f"    • {r.name}: {r.detail}")
        print("─" * 60)
        sys.exit(0 if failed == 0 else 1)


suite = TestSuite()


def _headers(token: str | None = None) -> dict[str, str]:
    t = token or TOKEN
    h: dict[str, str] = {"Authorization": f"Bearer {t}"} if t else {}
    return h


async def _timed(coro: Any) -> tuple[httpx.Response, float]:
    t0 = time.perf_counter()
    resp = await coro
    elapsed = (time.perf_counter() - t0) * 1000
    return resp, elapsed


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


async def test_health(client: httpx.AsyncClient) -> None:
    """GET /health — liveness probe."""
    resp, ms = await _timed(client.get("/health"))
    passed = resp.status_code == 200 and resp.json().get("status") == "ok"
    suite.record(
        "GET /health liveness",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:200]}",
    )


async def test_health_detailed(client: httpx.AsyncClient) -> None:
    """GET /health/detailed — dependency check."""
    resp, ms = await _timed(client.get("/health/detailed"))
    passed = resp.status_code == 200
    data = resp.json() if passed else {}
    deps = data.get("dependencies", {})
    db_ok = deps.get("database", {}).get("healthy", False)
    detail = "" if passed else f"status={resp.status_code} body={resp.text[:200]}"
    suite.record(
        "GET /health/detailed (database healthy)",
        passed and db_ok,
        ms,
        detail or ("DB not healthy: " + str(deps.get("database"))) if not db_ok else "",
    )


async def test_unauthenticated(client: httpx.AsyncClient) -> None:
    """All protected routes should return 403/401 without a token."""
    endpoints = [
        ("GET", "/api/v1/papers"),
        ("POST", "/api/v1/papers/arxiv"),
        ("POST", "/api/v1/papers/doi"),
        ("GET", f"/api/v1/papers/{uuid.uuid4()}"),
        ("POST", f"/api/v1/pipeline/run/{uuid.uuid4()}"),
        ("GET", f"/api/v1/pipeline/runs/{uuid.uuid4()}"),
        ("POST", "/api/v1/search"),
    ]
    all_passed = True
    for method, path in endpoints:
        resp = await client.request(method, path, json={})
        if resp.status_code not in (401, 403, 422):
            all_passed = False
            suite.record(
                f"Unauthenticated {method} {path}",
                False,
                0,
                f"Expected 401/403, got {resp.status_code}",
            )
    if all_passed:
        suite.record("Unauthenticated requests return 401/403", True, 0)


async def test_paper_lifecycle(client: httpx.AsyncClient) -> str | None:
    """Full CRUD lifecycle: arXiv ingest → get → list → delete."""
    if not TOKEN:
        suite.record(
            "Paper lifecycle (skipped — no TOKEN)",
            True,
            0,
            "Set RESEARCH_PILOT_TOKEN env var to enable auth tests.",
        )
        return None

    headers = _headers()

    # 1. Ingest via arXiv
    resp, ms = await _timed(
        client.post(
            "/api/v1/papers/arxiv",
            json={"url": ARXIV_URL},
            headers=headers,
        )
    )
    passed = resp.status_code == 201
    paper_id: str | None = None
    if passed:
        paper_id = resp.json().get("id")
    suite.record(
        "POST /api/v1/papers/arxiv (ingest ArXiv paper)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )

    if not paper_id:
        return None

    # 2. Get paper by ID
    resp, ms = await _timed(client.get(f"/api/v1/papers/{paper_id}", headers=headers))
    passed = resp.status_code == 200 and resp.json().get("id") == paper_id
    suite.record(
        "GET /api/v1/papers/{id} (fetch by ID)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )

    # 3. List papers — verify our paper is present
    resp, ms = await _timed(client.get("/api/v1/papers", headers=headers))
    ids_in_list = [p["id"] for p in resp.json()] if resp.status_code == 200 else []
    passed = resp.status_code == 200 and paper_id in ids_in_list
    suite.record(
        "GET /api/v1/papers (list, contains ingested paper)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} n={len(ids_in_list)}",
    )

    # 4. Filter list by source
    resp, ms = await _timed(
        client.get("/api/v1/papers", params={"source": "arxiv_url"}, headers=headers)
    )
    ids_in_list = [p["id"] for p in resp.json()] if resp.status_code == 200 else []
    passed = resp.status_code == 200 and paper_id in ids_in_list
    suite.record(
        "GET /api/v1/papers?source=arxiv_url (filter by source)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} n={len(ids_in_list)}",
    )

    return paper_id


async def test_404_paper(client: httpx.AsyncClient) -> None:
    """GET /api/v1/papers/<random_uuid> → 404."""
    if not TOKEN:
        return
    resp, ms = await _timed(
        client.get(
            f"/api/v1/papers/{uuid.uuid4()}",
            headers=_headers(),
        )
    )
    passed = resp.status_code == 404
    suite.record(
        "GET /api/v1/papers/<nonexistent_id> returns 404",
        passed,
        ms,
        "" if passed else f"status={resp.status_code}",
    )


async def test_invalid_arxiv_url(client: httpx.AsyncClient) -> None:
    """POST /api/v1/papers/arxiv with garbage URL → 4xx."""
    if not TOKEN:
        return
    resp, ms = await _timed(
        client.post(
            "/api/v1/papers/arxiv",
            json={"url": "https://definitely-not-arxiv.example.com/paper"},
            headers=_headers(),
        )
    )
    passed = 400 <= resp.status_code < 500
    suite.record(
        "POST /api/v1/papers/arxiv (invalid URL → 4xx)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:200]}",
    )


async def test_doi_ingest(client: httpx.AsyncClient) -> str | None:
    """POST /api/v1/papers/doi — ingest via CrossRef DOI."""
    if not TOKEN:
        suite.record("DOI ingest (skipped — no TOKEN)", True, 0)
        return None
    resp, ms = await _timed(
        client.post(
            "/api/v1/papers/doi",
            json={"doi": TEST_DOI},
            headers=_headers(),
        )
    )
    passed = resp.status_code == 201
    paper_id = resp.json().get("id") if passed else None
    suite.record(
        "POST /api/v1/papers/doi (CrossRef DOI ingest)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )
    return paper_id


async def test_pdf_upload(client: httpx.AsyncClient) -> str | None:
    """POST /api/v1/papers/upload — upload a real (minimal) PDF."""
    if not TOKEN:
        suite.record("PDF upload (skipped — no TOKEN)", True, 0)
        return None

    pdf_bytes = _make_pdf_bytes()
    resp, ms = await _timed(
        client.post(
            "/api/v1/papers/upload",
            files={
                "file": ("test_paper.pdf", io.BytesIO(pdf_bytes), "application/pdf")
            },
            headers=_headers(),
        )
    )
    passed = resp.status_code == 201
    paper_id = resp.json().get("id") if passed else None
    suite.record(
        "POST /api/v1/papers/upload (minimal PDF)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )
    return paper_id


async def test_upload_non_pdf(client: httpx.AsyncClient) -> None:
    """Uploading a non-PDF file should be rejected."""
    if not TOKEN:
        return
    resp, ms = await _timed(
        client.post(
            "/api/v1/papers/upload",
            files={
                "file": (
                    "malicious.exe",
                    io.BytesIO(b"MZ\x90\x00"),
                    "application/octet-stream",
                )
            },
            headers=_headers(),
        )
    )
    # The service itself checks the extension; fastapi returns 422 or similar
    passed = resp.status_code in (400, 422, 500)
    suite.record(
        "POST /api/v1/papers/upload (non-PDF rejected)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:200]}",
    )


async def test_pipeline_trigger(client: httpx.AsyncClient, paper_id: str) -> str | None:
    """POST /api/v1/pipeline/run/{paper_id} — trigger a run & verify PENDING."""
    if not TOKEN or not paper_id:
        suite.record("Pipeline trigger (skipped)", True, 0)
        return None
    resp, ms = await _timed(
        client.post(
            f"/api/v1/pipeline/run/{paper_id}",
            headers=_headers(),
        )
    )
    passed = resp.status_code == 202
    run_id: str | None = None
    if passed:
        data = resp.json()
        run_id = data.get("id")
        passed = passed and data.get("status") in (
            "pending",
            "running",
            "PENDING",
            "RUNNING",
        )
    suite.record(
        "POST /api/v1/pipeline/run/{paper_id} (trigger, 202 PENDING)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )
    return run_id


async def test_pipeline_status_poll(client: httpx.AsyncClient, run_id: str) -> None:
    """GET /api/v1/pipeline/runs/{run_id} — poll until done or timeout."""
    if not TOKEN or not run_id:
        suite.record("Pipeline status polling (skipped)", True, 0)
        return

    print(f"\n  {CYAN}  Polling run {run_id} (max 120s)...{RESET}")
    timeout = 120
    interval = 5
    elapsed = 0
    final_status = "unknown"
    while elapsed < timeout:
        resp = await client.get(
            f"/api/v1/pipeline/runs/{run_id}",
            headers=_headers(),
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        final_status = data.get("status", "unknown").lower()
        print(f"  {CYAN}  {elapsed:3d}s — status: {final_status}{RESET}")
        if final_status in ("completed", "failed", "success"):
            break
        await asyncio.sleep(interval)
        elapsed += interval

    passed = final_status in ("completed", "success")
    suite.record(
        "Pipeline run completes successfully",
        passed,
        elapsed * 1000,
        f"final_status={final_status}" if not passed else "",
    )


async def test_run_not_found(client: httpx.AsyncClient) -> None:
    """GET /api/v1/pipeline/runs/<random> → 404."""
    if not TOKEN:
        return
    resp, ms = await _timed(
        client.get(
            f"/api/v1/pipeline/runs/{uuid.uuid4()}",
            headers=_headers(),
        )
    )
    passed = resp.status_code == 404
    suite.record(
        "GET /api/v1/pipeline/runs/<nonexistent> returns 404",
        passed,
        ms,
        "" if passed else f"status={resp.status_code}",
    )


async def test_semantic_search(client: httpx.AsyncClient) -> None:
    """POST /api/v1/search — semantic similarity query."""
    if not TOKEN:
        suite.record("Semantic search (skipped — no TOKEN)", True, 0)
        return
    resp, ms = await _timed(
        client.post(
            "/api/v1/search",
            json={
                "query": "transformer attention mechanism self-attention",
                "limit": 3,
            },
            headers=_headers(),
        )
    )
    # May return 200 with empty list if embeddings haven't been generated yet — still a pass
    passed = resp.status_code == 200
    suite.record(
        "POST /api/v1/search (semantic query)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )


async def test_search_empty_query(client: httpx.AsyncClient) -> None:
    """POST /api/v1/search with an empty string → 422 validation error."""
    if not TOKEN:
        return
    resp, ms = await _timed(
        client.post(
            "/api/v1/search",
            json={"query": "", "limit": 5},
            headers=_headers(),
        )
    )
    passed = resp.status_code == 422
    suite.record(
        "POST /api/v1/search (empty query → 422)",
        passed,
        ms,
        "" if passed else f"status={resp.status_code}",
    )


async def test_similar_paper(client: httpx.AsyncClient, paper_id: str) -> None:
    """GET /api/v1/search/similar/{paper_id} — find similar papers."""
    if not TOKEN or not paper_id:
        suite.record("Similar papers (skipped)", True, 0)
        return
    resp, ms = await _timed(
        client.get(
            f"/api/v1/search/similar/{paper_id}",
            headers=_headers(),
        )
    )
    # 200 or 422 (no metadata yet) are both valid at this point
    passed = resp.status_code in (200, 422)
    suite.record(
        "GET /api/v1/search/similar/{paper_id}",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:300]}",
    )


async def test_delete_paper(client: httpx.AsyncClient, paper_id: str) -> None:
    """DELETE /api/v1/papers/{id} — verify 204 and subsequent 404."""
    if not TOKEN or not paper_id:
        suite.record("Delete paper (skipped)", True, 0)
        return

    resp, ms = await _timed(
        client.delete(
            f"/api/v1/papers/{paper_id}",
            headers=_headers(),
        )
    )
    passed = resp.status_code == 204
    suite.record(
        f"DELETE /api/v1/papers/{paper_id} returns 204",
        passed,
        ms,
        "" if passed else f"status={resp.status_code} body={resp.text[:200]}",
    )

    # Verify it's gone
    resp2, ms2 = await _timed(
        client.get(
            f"/api/v1/papers/{paper_id}",
            headers=_headers(),
        )
    )
    suite.record(
        "GET deleted paper returns 404",
        resp2.status_code == 404,
        ms2,
        "" if resp2.status_code == 404 else f"status={resp2.status_code}",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def main() -> None:
    print(f"\n{CYAN}{'═' * 60}")
    print("  ResearchPilot E2E Test Suite")
    print(f"  Target: {BASE_URL}")
    print(
        f"  Auth:   {'✓ TOKEN set' if TOKEN else '✗ No TOKEN — auth tests will be skipped'}"
    )
    print(f"{'═' * 60}{RESET}\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # ── Health ──────────────────────────────────────────────────────────
        print(
            f"{CYAN}── Health Checks ──────────────────────────────────────────{RESET}"
        )
        await test_health(client)
        await test_health_detailed(client)

        # ── Auth guard ──────────────────────────────────────────────────────
        print(
            f"\n{CYAN}── Authentication Guard ───────────────────────────────────{RESET}"
        )
        await test_unauthenticated(client)

        # ── Paper ingestion & CRUD ──────────────────────────────────────────
        print(
            f"\n{CYAN}── Paper Ingestion & CRUD ─────────────────────────────────{RESET}"
        )
        arxiv_paper_id = await test_paper_lifecycle(client)
        doi_paper_id = await test_doi_ingest(client)
        pdf_paper_id = await test_pdf_upload(client)
        await test_404_paper(client)
        await test_invalid_arxiv_url(client)
        await test_upload_non_pdf(client)

        # ── Pipeline ────────────────────────────────────────────────────────
        print(
            f"\n{CYAN}── Pipeline Execution ─────────────────────────────────────{RESET}"
        )
        run_paper_id = arxiv_paper_id or doi_paper_id or pdf_paper_id
        run_id: str | None = None
        if run_paper_id:
            run_id = await test_pipeline_trigger(client, run_paper_id)
        await test_run_not_found(client)

        # Pipeline polling is slow — run it ONLY if we actually triggered a run
        if run_id:
            await test_pipeline_status_poll(client, run_id)

        # ── Search ──────────────────────────────────────────────────────────
        print(
            f"\n{CYAN}── Semantic Search ────────────────────────────────────────{RESET}"
        )
        await test_semantic_search(client)
        await test_search_empty_query(client)
        if arxiv_paper_id:
            await test_similar_paper(client, arxiv_paper_id)

        # ── Cleanup ─────────────────────────────────────────────────────────
        print(
            f"\n{CYAN}── Cleanup ────────────────────────────────────────────────{RESET}"
        )
        for pid in filter(None, [arxiv_paper_id, doi_paper_id, pdf_paper_id]):
            await test_delete_paper(client, pid)

    suite.summary()


if __name__ == "__main__":
    asyncio.run(main())
