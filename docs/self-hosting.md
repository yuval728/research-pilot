# Self-Hosting

This guide gets Research Pilot running with a local frontend, local API, and hosted Supabase project.

## Prerequisites

- Node.js LTS.
- Python 3.11.
- uv.
- A Supabase project.
- A Gemini API key.

## Supabase

1. Create a Supabase project.
2. Copy the project URL, anon key, service-role key, and database connection string.
3. Create two private Storage buckets:
   - `papers`
   - `outputs`
4. Enable Auth providers you want to support.

## Environment

From the repo root:

```powershell
Copy-Item .env.example .env
```

Fill in:

- `LLM_API_KEY`
- `EMBEDDING_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_DB_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_URL`

For the frontend:

```powershell
Copy-Item app/.env.example app/.env
```

## Database

```powershell
cd pipeline
uv sync --all-extras --dev
uv run alembic upgrade head
```

## Run The API

```powershell
cd pipeline
uv run uvicorn src.api.main:app --reload
```

The API should be available at `http://localhost:8000`.

## Run The App

```powershell
cd app
npm install
npm run dev
```

Open `http://localhost:3000`.

## Production Notes

- Keep `SUPABASE_SERVICE_ROLE_KEY` server-side only.
- Set `ENVIRONMENT=production`.
- Set `FRONTEND_ORIGIN` to the deployed frontend URL.
- Use a managed secret store instead of checking `.env` files into source control.
- Run migrations before deploying a backend build.
- Keep `LANGFUSE_ENABLED=false` unless Langfuse keys are configured.
