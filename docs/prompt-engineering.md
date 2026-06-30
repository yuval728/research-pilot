# Prompt Engineering

Research Pilot prompts are versioned Jinja templates. Shared prompts live in `pipeline/src/prompts/`; domain-specific prompts live under `pipeline/src/domains/<domain>/prompts/`.

## Principles

- Ask for evidence-backed structure, not prose.
- Make missing data explicit instead of encouraging guesses.
- Keep schema field names aligned with Pydantic models.
- Separate extraction, summarization, diagramming, and code generation prompts.
- Prefer small prompt changes with focused tests over broad rewrites.

## Extraction Prompts

Extraction prompts should identify:

- Paper objective.
- Method and architecture components.
- Datasets, baselines, metrics, and results.
- Training, inference, and evaluation details.
- Limitations and assumptions.

## Diagram Prompts

Diagram prompts should produce implementation-friendly structure:

- Nodes should be named after real components in the paper.
- Edges should describe data flow or dependency.
- Avoid visual decoration in the generated diagram source.
- Prefer concise labels that fit in the UI.

## Code Generation Prompts

Code generation should run only when a paper has an implementable architecture. Prompts should ask for:

- Minimal runnable skeletons.
- Clearly named modules.
- Synthetic data placeholders when real data is unavailable.
- Comments only where the generated code needs orientation.

## Evaluation

When changing prompts, test against a fixed paper set and compare:

- Schema validity.
- Missing-field rate.
- Diagram readability.
- Whether generated code imports and type-checks.
- Token use and latency.
