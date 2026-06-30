# Changelog

All notable changes to Research Pilot will be documented in this file.

## 0.1.0 - Initial Open Source Release

- Added FastAPI backend for authenticated paper ingestion, pipeline runs, outputs, and search.
- Added LangGraph processing pipeline with ingestion, metadata, classification, extraction, summaries, embeddings, diagrams, code generation, and reports.
- Added Supabase-backed persistence for papers, runs, outputs, auth, storage, and pgvector search.
- Added Vite React frontend for paper ingestion, library browsing, pipeline progress, and paper viewing.
- Added Alembic migrations under `pipeline/src/db/migrations`.
- Added GitHub Actions CI for backend linting, formatting, typing, and tests.
- Added open-source launch docs, contribution guide, API docs, configuration docs, and issue templates.
