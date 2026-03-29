# Research Pilot 🚀

Research Pilot is an AI-powered research paper intelligence platform built for AI/ML engineers and researchers who need to go beyond just reading papers — they need to understand, implement, and build on them fast.

By dropping in a paper via PDF upload, arXiv URL, or DOI, Research Pilot processes it end to end using Gemini's native PDF understanding—reading not just the text but actual diagrams, tables, equations, and figures—and produces a complete, structured intelligence package in minutes.

## What It Produces

- **Structured Extraction**: Every meaningful component of the paper pulled into a clean, queryable format (method, architecture components, datasets, evaluation metrics, baselines, results).
- **Multi-Level Summaries**: Four levels of understanding from a single paper (paragraph overview, section-by-section breakdown, key contributions bullet list, and ELI5).
- **Architecture & Flow Diagrams**: Automatically generated clean SVGs for model architectures, training data pipelines, and inference flows.
- **Implementation Code**: A working PyTorch skeleton that translates the paper's described architecture into actual code, paired with synthetic data generation.

## What Makes It Different

Most AI research tools treat papers as documents to chat with. Research Pilot treats them as structured knowledge to extract, visualise, and implement. The output isn't a conversation — it's a **deployable intelligence package**.

- **Automatic Architecture Diagrams & Code**: No existing tool automatically generates this level of technical output.
- **Personal Semantically Searchable Library**: Every processed paper is embedded, stored, and searchable by concept, architecture type, dataset, or method—not just title.

## The Stack

- **Core Intelligence**: Gemini handles the PDF understanding, structured extraction, summarisation, diagram generation, PyTorch code generation, and embeddings.
- **Frontend**: Next.js (TypeScript, Tailwind, App Router) user interface.
- **Backend Pipeline**: Python-based (uv, Pydantic, Instructor) processing pipeline.
- **Storage**: Supabase (Database, Auth, and Storage).
- **Deployment**: Google Cloud Run.

## Project Structure

ResearchPilot uses a monorepo structure to keep the frontend and data processing pipeline tightly integrated.

```text
research-pilot/
├── app/          # Next.js Frontend
│   ├── src/      # Application Source
│   └── ...       # Next.js Config
├── pipeline/     # Python Data Pipeline
│   ├── pyproject.toml
│   └── ...       # Python Source
└── docs/         # Additional Documentation
```

## Getting Started

### Prerequisites

- Node.js (Latest LTS)
- Python 3.10+ (and `uv`)

### Development

- **Frontend**: `cd app && npm install && npm run dev`
- **Pipeline**: `cd pipeline && uv run hello.py`

## Roadmap

The detailed implementation plan has been laid out across 10 phases. You can find the entire roadmap documenting our progress in [docs/Roadmap.md](./docs/Roadmap.md).
