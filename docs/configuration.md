# Configuration

Backend settings are defined in `pipeline/src/core/config.py`. Values load from defaults, optional YAML, environment variables, and `.env` files.

## Backend

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ENVIRONMENT` | No | `development` | Runtime environment: `development`, `staging`, or `production`. |
| `DEBUG` | No | `false` | Enables debug behavior where supported. |
| `LOG_LEVEL` | No | `INFO` | Logging threshold. |
| `FRONTEND_ORIGIN` | No | `http://localhost:3000` | CORS origin for the frontend. |
| `SENTRY_DSN` | No | empty | Optional Sentry DSN. |
| `LLM_API_KEY` | Yes | none | API key used by LiteLLM for generation calls. |
| `LLM_MODEL` | No | `gemini/gemini-2.0-flash` | Main generation model. |
| `LLM_TEMPERATURE` | No | `0.2` | Generation temperature. |
| `LLM_MAX_OUTPUT_TOKENS` | No | `8192` | Maximum output tokens per generation call. |
| `LLM_MAX_RETRIES` | No | `3` | Retry count for LLM calls. |
| `LLM_TIMEOUT_SECONDS` | No | `120.0` | LLM request timeout. |
| `EMBEDDING_API_KEY` | Yes | none | API key used for embeddings. |
| `EMBEDDING_MODEL` | No | `gemini/text-embedding-004` | Embedding model. |
| `SUPABASE_URL` | Yes | none | Supabase project URL. |
| `SUPABASE_DB_URL` | Yes | none | SQLAlchemy async database URL. |
| `SUPABASE_ANON_KEY` | Yes | none | Supabase anon key for auth validation. |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | none | Backend-only service role key for privileged storage/database work. |
| `SUPABASE_PAPERS_BUCKET` | No | `papers` | Bucket for input PDFs. |
| `SUPABASE_OUTPUTS_BUCKET` | No | `outputs` | Bucket for generated outputs. |
| `LANGFUSE_ENABLED` | No | `true` | Enables Langfuse tracing when keys are configured. |
| `LANGFUSE_PUBLIC_KEY` | Required by settings | none | Langfuse public key. |
| `LANGFUSE_SECRET_KEY` | Required by settings | none | Langfuse secret key. |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | Langfuse host. |
| `PIPELINE_ENABLED_STAGES` | No | empty | Optional comma-separated stage allowlist. Empty means all stages. |
| `PIPELINE_CACHE_ENABLED` | No | `true` | Enables stage reuse on reruns. |
| `PIPELINE_MAX_PAGES` | No | `60` | Maximum pages processed per paper. |
| `PIPELINE_TOKEN_BUDGET_PER_PAPER` | No | `500000` | Token budget across a full paper run. |

## Frontend

Frontend values are documented in `app/.env.example`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL exposed to the browser. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anon key exposed to the browser. |
| `NEXT_PUBLIC_API_URL` | Yes | Backend API base URL. |

## YAML Overrides

Set `RESEARCH_PILOT_CONFIG_PATH` to point at a YAML file if you prefer structured local config. Environment variables still take priority.
