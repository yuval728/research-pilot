# ResearchPilot 🚀

An AI-powered research platform that automates data gathering, analysis, and visualization.

## Architecture

ResearchPilot uses a monorepo structure to keep the frontend and data processing pipeline tightly integrated.

- **`app/`**: A Next.js (TypeScript, Tailwind, App Router) application that serves as the user interface for interacting with research results.
- **`pipeline/`**: A Python-based (uv, Pydantic, LLM tools) data pipeline responsible for gathering research data, processing it, and generating insights.

## Project Structure

```text
research-pilot/
├── app/          # Next.js Frontend
│   ├── src/      # Application Source
│   └── ...       # Next.js Config
├── pipeline/     # Python Pipeline
│   ├── pyproject.toml
│   └── ...       # Python Source
└── README.md     # Root Documentation
```

## Getting Started

### Prerequisites

- Node.js (Latest LTS)
- Python 3.10+ (and `uv`)

### Development

- **Frontend**: `cd app && npm install && npm run dev`
- **Pipeline**: `cd pipeline && uv run hello.py`
