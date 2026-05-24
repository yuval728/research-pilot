# Research Pilot Roadmap

## Phase 1 — Core Python Foundation
**Step 5 — core/ Module**
- `exceptions.py` — full exception hierarchy
- `config.py` — pydantic-settings with yaml + env support
- `logger.py` — structlog JSON logger
- `events.py` — simple event bus
- `retry.py` — tenacity decorators for LLM and HTTP calls
- `telemetry.py` — token usage and latency tracking

**Step 6 — models/ Module**
- `paper.py` — Paper, PaperMetadata, PaperSource
- `run.py` — PipelineRun, StageResult, RunStatus
- `extraction.py` — ExtractionResult base
- `output.py` — DiagramOutput, CodeOutput, ReportOutput, SummaryOutput
- Write unit tests for all models

**Step 7 — Sentry Integration**
- Add Sentry SDK to FastAPI
- Configure environment tagging dev/prod
- Verify errors surface in Sentry dashboard

## Phase 2 — Database Setup
**Step 8 — Database Schema & SQLAlchemy Models**
- Design Postgres schema
  - `papers` — id, title, authors, arxiv_id, doi, domain, sub_domain, pdf_url, page_count, created_at
  - `pipeline_runs` — id, paper_id, status, started_at, completed_at, error
  - `stage_results` — id, run_id, stage_name, status, cached, started_at, completed_at
  - `extractions` — id, paper_id, domain, schema_version, data (JSONB)
  - `embeddings` — id, paper_id, chunk_type, embedding (vector 768)
  - `outputs` — id, paper_id, type (summary/diagram/code/report), storage_path, created_at
- Write SQLAlchemy ORM models in `db/models.py`
- Write `db/session.py` — engine + session factory
- Write initial Alembic migration

**Step 9 — Supabase Configuration**
- Create Supabase project
- Apply migrations via Supabase CLI
- Enable pgvector extension
- Configure Row Level Security policies
- Set up Auth — email + GitHub OAuth
- Set up Storage buckets — papers and outputs
- Configure Realtime on pipeline_runs and stage_results tables

**Step 10 — Langfuse Setup**
- Create Langfuse project on cloud free tier
- Add Langfuse callback to LiteLLM in config
- Verify every LLM call appears with tokens, latency, cost

## Phase 3 — Pipeline Core
**Step 11 — Pipeline Skeleton**
- `pipeline/context.py` — PipelineContext dataclass
- `pipeline/base.py` — BasePipelineStage ABC with cache check, execute, skip logic
- `pipeline/runner.py` — DAG runner with dependency resolution
- Unit test runner with mock stages

**Step 12 — Domain Plugin System**
- `domains/base.py` — DomainPlugin ABC
- `domains/registry.py` — auto-discovers domain folders
- Unit test registry discovers and loads plugins correctly

## Phase 4 — AI/ML Domain
**Step 13 — AI/ML Extraction Schema**
- Design comprehensive Pydantic schema covering:
  - task, problem statement, proposed method
  - architecture components and connections
  - datasets, metrics, baselines, results
  - limitations, future work
  - visual elements — diagrams and figures described
  - mathematical contributions
- Sub-domain variants — CV, NLP, RL, generative models
- Unit tests with fixture data

**Step 14 — Prompt Templates**
- `domains/ai_ml/prompts/classify_v1.j2`
- `domains/ai_ml/prompts/extract_v1.j2`
- `domains/ai_ml/prompts/summarise_v1.j2`
- `domains/ai_ml/prompts/diagram_v1.j2`
- `domains/ai_ml/prompts/codegen_v1.j2`
- Each prompt explicitly instructs Gemini to use both visual and textual understanding

**Step 15 — AI/ML Domain Plugin**
- `domains/ai_ml/plugin.py` — wire schema + prompts
- Register in domain registry
- Unit test plugin loads correctly

## Phase 5 — Pipeline Stages
**Step 16 — Ingest Stage**
- Accept PDF upload, arXiv URL, or DOI
- arXiv URL → fetch PDF via arxiv pip package
- DOI → CrossRef API → fetch PDF
- Deduplicate by arXiv ID / DOI / content hash
- Store raw PDF in Supabase Storage papers bucket
- Store paper metadata in Postgres
- No parsing — just fetch and store

**Step 17 — Classify Stage**
- Send raw PDF directly to Gemini 2.0 Flash
- Detect domain — AI/ML vs System Design
- Detect sub-domain — CV, NLP, RL, generative
- Confidence score on classification
- Store result in stage_results
- Cache — same PDF never classified twice

**Step 18 — Extract Stage**
- Send raw PDF + `extract_v1.j2` prompt to Gemini via LiteLLM + Instructor
- Gemini reads text, diagrams, tables, equations natively
- Validate output against AI/ML Pydantic schema
- Instructor auto-retries with validation error in prompt on failure
- Store extraction JSONB in extractions table
- Store token count and latency in Langfuse
- Cache — same PDF + same prompt version never re-extracted

**Step 19 — Summarise Stage**
- Works from extraction JSON only — no PDF needed
- Generate four levels:
  - one paragraph abstract-style
  - section by section
  - key contributions bullets
  - ELI5
- Store all four in outputs table

**Step 20 — Embed Stage**
- Generate embeddings for key chunks — title + abstract, contributions, method, results
- Call `litellm.embedding()` with Gemini Embedding 2
- Store 768d vectors in embeddings table via pgvector
- Enables semantic search across paper library

**Step 21 — Diagram Generation Stage**
- Works from extraction JSON
- Generate Mermaid/D2 code for:
  - architecture diagram — model components and connections
  - training flow — data → model → loss → update
  - inference flow
- Validate Mermaid syntax before storing
- Render to SVG
- Store DSL code + SVG in Supabase Storage outputs bucket
- Store path reference in outputs table

**Step 22 — Code Generation Stage**
- Works from extraction JSON
- Generate PyTorch implementation skeleton
- Generate synthetic data matching paper's described input format using Faker + NumPy
- Validate with `ast.parse()` before storing
- Export as `.py` file and Jupyter notebook via nbformat
- Store in Supabase Storage
- Store path reference in outputs table

**Step 23 — Report Builder Stage**
- Assemble all stage outputs into structured markdown report
- Sections — metadata, summaries, diagrams (embedded SVG), code snippet, full extraction JSON
- Store final report in Supabase Storage
- Store path in outputs table

## Phase 6 — FastAPI Layer
**Step 24 — FastAPI App**
- `api/main.py` — app setup, Sentry middleware, CORS
- `api/routes/papers.py` — upload, fetch by ID, list library
- `api/routes/pipeline.py` — trigger run, get run status, get stage results
- `api/routes/search.py` — semantic search via pgvector
- `api/routes/health.py` — health check for uptime monitoring

**Step 25 — Realtime Progress**
- Pipeline stages write progress events to Supabase Realtime on pipeline_runs and stage_results
- FastAPI triggers run then returns run_id immediately
- Frontend subscribes to Realtime channel for live stage updates
- Test full progress flow end to end

**Step 26 — API Testing**
- Integration tests for all routes
- Test with real Gemini API calls against 3-5 fixture papers
- Verify caching works — second run of same paper hits no LLM calls

## Phase 7 — Frontend
**Step 27 — Next.js Foundation**
- Configure Supabase client
- Set up Auth — email + GitHub OAuth login page
- Protected routes middleware
- PostHog analytics setup
- Sentry frontend setup

**Step 28 — Paper Library Page**
- List all processed papers
- Semantic search bar — queries pgvector
- Filter by domain, sub-domain, date
- Paper card — title, authors, domain, status

**Step 29 — Paper Ingest Page**
- PDF upload dropzone
- arXiv URL input
- DOI input
- Submit triggers pipeline run
- Realtime progress bar — each stage lights up as it completes

**Step 30 — Paper Viewer Page**
- Summary tabs — paragraph, section-by-section, bullets, ELI5
- Diagram viewer — render SVG diagrams
- Code viewer — syntax highlighted, download as `.py` or `.ipynb`
- Extraction JSON viewer — collapsible tree
- Regenerate individual stage button

**Step 31 — Polish**
- Error states for failed stages
- Empty states for new users
- Loading skeletons
- Mobile responsive layout

## Phase 8 — Deployment
**Step 32 — Pipeline Deployment (Google Cloud Run)**
- Write Dockerfile for Python pipeline
- Configure Cloud Run — 2GB RAM, 60min timeout, scale to zero
- Set all environment variables — Gemini API key, Supabase keys, Langfuse keys, Sentry DSN
- Add Cloud Run deploy job to GitHub Actions
- Verify end to end from Cloud Run

**Step 33 — Frontend Deployment (Vercel)**
- Connect GitHub repo to Vercel
- Set environment variables
- Configure production Supabase URL
- Verify Auth, Storage, Realtime all work in production

**Step 34 — Monitoring Setup**
- Better Uptime — monitors for Cloud Run health endpoint and Supabase
- Sentry — verify production errors surface
- Langfuse — verify production LLM calls tracked
- PostHog — verify analytics flowing

## Phase 9 — Validation & Hardening
**Step 35 — Test on Real Papers**
- Process 20 AI/ML papers across sub-domains — CV, NLP, RL, generative
- Score each — extraction accuracy, diagram correctness, code runnability
- Build golden dataset — 10 papers with manually verified extractions

**Step 36 — Prompt Iteration**
- Use Langfuse to identify worst performing prompts
- Run evals against golden dataset
- Version bumped prompts — `extract_v2.j2`
- Document changes in Notion

**Step 37 — Hardening**
- Test with long papers (30,000+ tokens) — verify token budget handling
- Test Gemini free tier rate limits — add queuing if needed
- Verify all error paths surface in Sentry
- Verify cache invalidation on prompt version change

## Phase 10 — Personal Use & Decision Point
**Step 38 — Daily Use**
- Process every paper you read through the pipeline
- Log every friction point and wrong output
- Do not add features until 50 papers processed

**Step 39 — Phase 2 Decision**
- After 50-100 papers review everything
- Is core value validated?
- What's missing?
- Worth productising?
- Plan Phase 2 only then
