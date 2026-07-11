# Contributing

Thanks for helping improve Research Pilot. The project is early, so the best contributions are focused, tested, and tied to a clear user-visible improvement.

## Development Setup

```powershell
git clone https://github.com/yuval728/research-pilot
cd research-pilot
Copy-Item .env.example .env
```

Backend:

```powershell
cd pipeline
uv sync --all-extras --dev
uv run alembic upgrade head
uv run uvicorn src.api.main:app --reload
```

Frontend:

```powershell
cd app
npm install
npm run dev
```

## Checks

Run backend checks from `pipeline/`:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest tests/unit
```

Run frontend checks from `app/`:

```powershell
npm run lint
npm test
npm run build
```

## Pull Requests

- Keep PRs small enough to review in one sitting.
- Include tests for behavior changes.
- Update docs when setup, configuration, API shape, or outputs change.
- Explain the problem, the approach, and any tradeoffs in the PR description.
- Do not commit secrets, local `.env` files, generated caches, or private data.

## Code Style

- Python uses Ruff, mypy, Pydantic models, and explicit public function signatures.
- Frontend code uses TypeScript, React hooks, and the existing component patterns in `app/src`.
- Prefer typed models and structured parsing over ad hoc string manipulation.
- Keep domain-specific prompt changes in the relevant `domains/<domain>/prompts` folder.

## Adding A Domain Plugin

Domain plugins live under `pipeline/src/domains/<domain_id>/`. See [docs/adding-a-domain.md](docs/adding-a-domain.md) for the expected files, registration flow, schemas, prompts, and tests.

## Good First Issues

Good first issues should be self-contained and include:

- The expected behavior.
- The relevant files.
- A small reproduction or acceptance checklist.
- Any setup requirements.

Useful starter areas include docs improvements, prompt examples, issue template polish, small UI states, and tests around existing services.
