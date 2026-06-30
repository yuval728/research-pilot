# API Reference

The FastAPI OpenAPI UI is available at `/docs` when the backend is running.

Base path for application routes: `/api/v1`.

Most routes require a Supabase access token:

```http
Authorization: Bearer <supabase-access-token>
```

SSE endpoints also accept `?token=<supabase-access-token>` for browser event streams.

## Health

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness check. |
| `GET` | `/health/detailed` | Dependency readiness check for database, Supabase Storage, and LLM API. |

## Papers

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/v1/papers/upload` | Upload and ingest a PDF. |
| `POST` | `/api/v1/papers/arxiv` | Ingest a paper from an arXiv URL. |
| `POST` | `/api/v1/papers/doi` | Ingest a paper from a DOI. |
| `GET` | `/api/v1/papers` | List the current user's papers. |
| `GET` | `/api/v1/papers/public` | List publicly published papers. |
| `GET` | `/api/v1/papers/{paper_id}` | Get one paper. |
| `DELETE` | `/api/v1/papers/{paper_id}` | Delete a paper and related outputs. |
| `POST` | `/api/v1/papers/{paper_id}/publish` | Publish a paper to the public library. |
| `POST` | `/api/v1/papers/{paper_id}/import` | Import a public paper into the current user's library. |
| `GET` | `/api/v1/papers/{paper_id}/outputs` | Fetch the complete output bundle. |
| `GET` | `/api/v1/papers/{paper_id}/outputs/report.md` | Download generated markdown report. |
| `GET` | `/api/v1/papers/{paper_id}/outputs/code.py` | Download generated Python code. |
| `GET` | `/api/v1/papers/{paper_id}/outputs/notebook.ipynb` | Download generated notebook. |

## Pipeline

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/v1/pipeline/run/{paper_id}` | Trigger a pipeline run. |
| `GET` | `/api/v1/pipeline/runs/{run_id}` | Get run status and stage results. |
| `GET` | `/api/v1/pipeline/papers/{paper_id}/latest-run` | Get the newest run for a paper. |
| `POST` | `/api/v1/pipeline/runs/{run_id}/stages/{stage_name}/retry` | Retry one stage. |
| `GET` | `/api/v1/pipeline/runs/{run_id}/stages/{stage_name}` | Get one stage result. |
| `GET` | `/api/v1/pipeline/runs/{run_id}/stream` | Stream run updates over server-sent events. |

## Search

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/v1/search` | Semantic paper search. |
| `GET` | `/api/v1/search/similar/{paper_id}` | Find similar papers. |

## Example

```bash
curl -X POST http://localhost:8000/api/v1/papers/arxiv \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://arxiv.org/abs/1706.03762"}'
```
