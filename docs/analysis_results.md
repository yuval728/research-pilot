# ResearchPilot `pipeline/src` — Full Code Review

> Reviewed all **~40 source files** across 8 modules. Findings are grouped by severity.

---

## 🔴 Critical Bugs

### 1. `datetime.utcnow()` is deprecated and produces naive datetimes
**Files:** [models.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/db/models.py) (lines 43, 47, 48, 87, 141, 163, 183)

All ORM models use `datetime.utcnow` which:
- Is deprecated in Python 3.12+ (will be removed in 3.14)
- Returns **timezone-naive** datetimes, which clash with your `DateTime(timezone=True)` columns
- Your Pydantic models correctly use `datetime.now(timezone.utc)`, creating an inconsistency

```diff
-    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
+    created_at: Mapped[datetime] = mapped_column(
+        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
+    )
```

> [!CAUTION]
> This is a ticking bomb. When Python removes `utcnow()`, your entire DB layer breaks. Fix all 7 occurrences.

---

### 2. `should_continue_after_classify` mutates `errors` but **discards the mutation**
**File:** [edges.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/edges.py#L96-L106)

```python
errors: list[str] = list(state.get("errors", []))
errors.append(f"[routing] Classification confidence ...")
# ← `errors` is a local copy. The append is never returned to the state.
return "__end__"
```

The user-facing error message about low confidence is silently lost. The edge function returns a string, not state — so there's no way to propagate this. The error needs to be emitted via the event bus or logged explicitly instead.

---

### 3. `_persist_stage_deltas` silently drops dirty objects without flushing
**File:** [pipeline_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/pipeline_service.py#L139-L164)

```python
if changed:
    continue  # ← this does nothing useful; it just moves to the next iteration
              #   BUT existing ORM objects are mutated in-place — they'll be flushed
              #   by the `await session.commit()` caller. However if `changed` is False,
              #   the `continue` at L164 is a no-op since it's the last statement anyway.
```

The real bug: the `if changed: continue` at the end of the loop body does nothing. It should probably be `if not changed: continue` at the TOP of the attribute-check block (to skip the loop body entirely for unchanged stages). As-is, it's misleading but harmless.

---

### 4. Duplicate Supabase client creation — bypasses the singleton
**Files:** [paper_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/paper_service.py#L31-L34), [export_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/export_service.py#L31-L34), [dependencies.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/api/dependencies.py#L76-L82)

Three separate `_get_supabase()` / `get_auth_client()` functions each call `create_client()`, creating **independent Supabase client instances**. Meanwhile, [engine.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/db/engine.py) already has a proper `@lru_cache` singleton (`get_supabase_client()`).

```diff
# paper_service.py & export_service.py — replace _get_supabase() with:
-def _get_supabase() -> Client:
-    return create_client(settings.supabase.url, settings.supabase.service_role_key.get_secret_value())
+from src.db.engine import get_supabase_client as _get_supabase
```

---

### 5. SSE stream swallows ALL exceptions silently
**File:** [pipeline.py (route)](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/api/routes/pipeline.py#L158-L160)

```python
except Exception:
    # On errors, continue polling; don't break the stream immediately
    pass
```

If `get_run_status` raises because the DB connection died, this loop will spin at 1 req/sec forever, burning a database connection per iteration. At minimum, add a retry counter or exponential backoff:

```python
except Exception:
    error_count += 1
    if error_count > 10:
        yield f"data: {json.dumps({'error': 'Stream failed'})}\n\n"
        break
```

---

### 6. Background task is fire-and-forget with no exception capture
**File:** [pipeline_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/pipeline_service.py#L272-L273)

```python
loop.create_task(self._execute_pipeline_run(run_id, initial_state))
```

The task handle is immediately discarded. If the task raises, the exception goes to `asyncio`'s default handler (logged to stderr but easily missed). Store the task or add `task.add_done_callback(...)`.

---

## 🟠 Security Issues

### 7. API key leaked in health check response on 4xx
**File:** [health.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/api/routes/health.py#L99-L110)

The Gemini API key is sent as a **query parameter** to the Google API on every health check. While this is how the Google API works, the full URL including the key could end up in:
- Access logs (reverse proxy, CDN)
- Error tracking (Sentry breadcrumbs)
- Browser history if `/health/detailed` is hit from a browser

Consider using an `x-goog-api-key` header instead, or just check that `settings.gemini.api_key` is non-empty without making an actual API call.

### 8. Search route leaks internal exception details to the client
**File:** [search.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/api/routes/search.py#L66-L70)

```python
detail=f"Search failed: {exc}"  # ← could expose DB connection strings, stack info
```

Use a generic message and log the real error server-side.

### 9. `FileNotFoundError` shadows the Python builtin
**File:** [exceptions.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/core/exceptions.py#L334)

The `# noqa: A001` acknowledges this, but any module that imports this alongside Python's builtin `FileNotFoundError` will get confusing behavior. Consider renaming to `StorageFileNotFoundError`.

---

## 🟡 Performance Optimizations

### 10. `list_papers` does an N+1-style query pattern
**File:** [paper_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/paper_service.py#L247-L282)

First fetches all papers, then runs a second query for all runs. Use a single query with a lateral join or `selectinload` on `PaperORM.runs` with `limit(1)`:

```python
stmt = (
    select(PaperORM)
    .options(selectinload(PaperORM.runs).selectinload(PipelineRunORM.stages))
)
```
Then pick the latest run in Python. This eliminates the second round-trip.

### 11. Prompt templates are read from disk on every single LLM call
**Files:** All node files (`classify.py`, `extract.py`, `summarise.py`, `diagram.py`, `codegen.py`)

Every node calls `aiofiles.open()` to read Jinja2 templates from disk on every invocation. These templates are static — cache them at module level:

```python
@functools.lru_cache(maxsize=1)
def _load_prompt_sync() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")
```

### 12. `_build_chunks` for embedding doesn't deduplicate content
**File:** [embed.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/embed.py#L43-L72)

If `problem_statement` and `proposed_method_summary` overlap significantly (common in papers), you're paying for embedding redundant content. Consider hashing chunks and deduplicating.

### 13. Jinja2 `Environment` recreated on every call
**Files:** [extract.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/extract.py#L61), [summarise.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/summarise.py#L61), [diagram.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/diagram.py#L167), [codegen.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/codegen.py#L96), [base.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/domains/base.py#L36)

`jinja2.Environment()` is instantiated fresh on every prompt render. Create a module-level singleton:
```python
_JINJA_ENV = Environment(autoescape=False)
```

### 14. Summaries are stored as `inline:{full_text}` in the `storage_path` column
**File:** [summarise.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/summarise.py#L110)

```python
storage_path=f"inline:{summary.content}",
```

Summaries can be 2000+ characters. You're stuffing full-text content into a column designed for file paths. This will:
- Blow up index sizes if the column is indexed
- Make `OutputORM` queries heavy (always fetches full text even when you only need paths)
- Approach VARCHAR limits on some configurations

**Recommendation:** Either upload summary text to Supabase Storage like reports, or add a dedicated `content` TEXT column to `OutputORM`.

---

## 🔵 Architectural Improvements

### 15. Massive code duplication across all 8 node files
**Pattern in:** Every node (`ingest.py`, `classify.py`, `extract.py`, `summarise.py`, `embed.py`, `diagram.py`, `codegen.py`, `report.py`)

Every node has this identical boilerplate (~25 lines):
```python
errors: list[str] = list(state.get("errors", []))
stage_statuses: dict[str, StageStatus] = dict(state.get("stage_statuses", {}))
token_usage: dict[str, int] = dict(state.get("token_usage", {}))
cached_stages: set[str] = set(state.get("cached_stages", set()))
# ... try/except with event emission ...
stage_statuses[_STAGE] = StageStatus.FAILED
log.exception(...)
default_bus.emit(Event(type=EventType.STAGE_FAILED, ...))
return {"stage_statuses": stage_statuses, "errors": errors}
```

**Recommendation:** Create a `@node_wrapper` decorator or context manager:

```python
@node_wrapper("extract")
async def extract_node(ctx: NodeContext) -> dict[str, Any]:
    # Just the happy path — errors, events, and state unpacking handled by wrapper
    ...
```

This would eliminate ~200 lines of duplicated code across the codebase.

### 16. Cache-check logic is duplicated with slight variations in every node
Each node independently implements:
1. Import `get_db_context` locally
2. Write a `_load_cached_*` function with raw SQL or ORM queries
3. Check `settings.pipeline.cache_enabled`
4. Set `StageStatus.CACHED` + add to `cached_stages` + emit event

This should be a shared `check_cache(paper_id, stage_name, loader_fn)` utility.

### 17. Diagram/summary/codegen deserialization logic is duplicated between nodes and `ExportService`
**Files:** [export_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/export_service.py#L125-L168) duplicates the `json:`/`inline:` parsing logic from [diagram.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/diagram.py#L350-L398) and [summarise.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/summarise.py#L118-L155).

Any change to the storage format requires updating both files. Extract a shared `OutputDeserializer` class.

### 18. `_to_stage_pydantic` and `_to_run_pydantic` are duplicated
**Files:** [paper_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/paper_service.py#L63-L97) and [pipeline_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/pipeline_service.py#L31-L67) contain identical ORM→Pydantic converters.

Extract to a shared `converters.py` module in `services/` or add `to_pydantic()` methods to the ORM models.

### 19. `PipelineState` is hardcoded to `AiMlExtraction`
**File:** [state.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/state.py#L78)

```python
extraction: NotRequired[AiMlExtraction | None]
```

The domain plugin system exists precisely to support multiple domains, but the state is hardcoded to `AiMlExtraction`. This should be `BaseModel | None` or `dict[str, Any]` to support future domain plugins.

Similarly, [output.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/models/output.py#L15) imports `AiMlExtraction` directly into the generic output model.

### 20. `retry.py` decorators don't work with async functions
**File:** [retry.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/core/retry.py#L104-L124)

The `llm_retry` decorator wraps with a **sync** `wrapper` function:
```python
@functools.wraps(fn)
def wrapper(*args, **kwargs):  # ← sync!
    return decorated(*args, **kwargs)
```

If `fn` is an `async` function (which all LLM calls are), this wrapper returns a coroutine without `await`ing it. Tenacity's `retry` handles async correctly since v8, but the extra sync wrapper layer breaks the chain. Remove the wrapper entirely or make it `async`:

```python
return decorated  # Just return tenacity's decorated function directly
```

---

## ⚪ Code Quality & Minor Fixes

### 21. `import uuid` duplicated in same file
**File:** [paper_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/paper_service.py#L8-L9)
```python
import uuid
import uuid as uuid_pkg  # ← redundant; use uuid.uuid4() everywhere
```

Same issue in [pipeline_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/pipeline_service.py#L8-L9).

### 22. `get_settings()` called redundantly inside functions that already have it
**Files:** [embed.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/embed.py#L179-L213) calls `get_settings()` twice, [diagram.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/diagram.py#L435-L468) calls it twice, [codegen.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/codegen.py#L357-L390) calls it twice.

### 23. `get_db` is defined in both `session.py` AND `dependencies.py`
**Files:** [session.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/db/session.py#L32-L38) and [dependencies.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/api/dependencies.py#L35-L41) both define `get_db()` with identical bodies. The routes use the one from `dependencies.py`; delete the duplicate.

### 24. `embed.py` docstring says 768-d but code uses 1536-d
**File:** [embed.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/graph/nodes/embed.py#L14-L16)
```
3. Calls ``litellm.embedding()`` with ``gemini/text-embedding-004`` per chunk.
4. Stores 768-d vectors in the ``embeddings`` table via pgvector.
```
But line 89 passes `dimensions=1536`, and `models.py` declares `Vector(1536)`. Fix the docstring.

### 25. `search_papers` accesses embedding response inconsistently
**File:** [paper_service.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/services/paper_service.py#L290-L292)
```python
query_vec = res.data[0]["embedding"]       # dict access
if hasattr(res.data[0], "embedding"):
    query_vec = res.data[0].embedding      # attribute access
```
This first line will always succeed (dict-style) OR raise. The `hasattr` check then pointlessly overwrites. Just use one consistent access pattern.

### 26. `config.py` has an unused `TypeVar` inside a function
**File:** [config.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/core/config.py#L206)
```python
TBaseSettings = TypeVar("TBaseSettings", bound=BaseSettings)
```
Defined inside `_build_settings()`, which is fine but the generic isn't actually leveraged for type safety. The `_section` function could just use `cls: type[BaseSettings]`.

### 27. `__import__` used inline in health check
**File:** [health.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/api/routes/health.py#L75)
```python
await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
```
`sqlalchemy` is already imported transitively. Just use a normal import at the top of the file.

### 28. `Paper.require_url_for_non_upload` validator does nothing
**File:** [paper.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/models/paper.py#L101-L105)
```python
@field_validator("source_url", mode="before")
@classmethod
def require_url_for_non_upload(cls, v: object) -> object:
    """Passthrough — cross-field logic lives in PaperCreate."""
    return v
```
This is dead code. Remove it.

### 29. `_log_final_failure` callback is defined but never used
**File:** [retry.py](file:///C:/Users/Yuval/Desktop/SEM%20XII/ResearchPilot/pipeline/src/core/retry.py#L84-L96)

The function exists but is never registered with any `retry()` call via `retry_error_callback`. Either wire it up or delete it.

---

## 📊 Summary Table

| Severity | Count | Key Theme |
|----------|-------|-----------|
| 🔴 Critical Bugs | 6 | Deprecated APIs, silent data loss, resource leaks |
| 🟠 Security | 3 | Key leakage, error detail exposure, name shadowing |
| 🟡 Performance | 5 | Disk I/O per call, N+1 queries, column bloat |
| 🔵 Architecture | 6 | ~200 lines of duplicated boilerplate, hardcoded domain |
| ⚪ Code Quality | 9 | Dead code, stale docs, duplicate imports |
| **Total** | **29** | |

---

## 🎯 Recommended Priority Order

1. **Fix `datetime.utcnow`** → prevents future Python breakage (30 min)
2. **Consolidate Supabase clients** → use `get_supabase_client()` everywhere (15 min)
3. **Fix SSE error handling** → add retry limit and backoff (15 min)
4. **Cache prompt templates** → free perf win across all LLM calls (20 min)
5. **Extract node boilerplate** → biggest DRY win, ~200 LOC reduction (2-3 hrs)
6. **Fix inline storage for summaries** → data model improvement (1 hr)
7. **Fix async retry wrappers** → correctness for retry decorators (15 min)
