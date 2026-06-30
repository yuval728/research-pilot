# Adding A Domain

Domain plugins let Research Pilot support new paper families without changing the core graph.

## Folder Layout

Create a folder under `pipeline/src/domains/`:

```text
pipeline/src/domains/system_design/
  __init__.py
  plugin.py
  schema.py
  prompts/
    classify_v1.j2
    extract_v1.j2
    summarise_v1.j2
    diagram_v1.j2
    codegen_v1.j2
```

## Plugin

`plugin.py` should create a `DomainPlugin` and register it with `pipeline/src/domains/registry.py`. Use `pipeline/src/domains/ai_ml/plugin.py` as the reference implementation.

## Schemas

Keep schemas narrow and reviewable. A good domain schema should capture:

- The core problem.
- The method or system design.
- Inputs and outputs.
- Evaluation setup.
- Claims and limitations.
- Implementation notes when applicable.

## Prompts

Prompts should ask for structured evidence, not just conclusions. Include instructions for:

- Where the evidence came from in the paper.
- How to handle missing information.
- What should be omitted instead of hallucinated.
- Domain-specific diagram conventions.

## Tests

Add tests for:

- Plugin discovery.
- Schema validation.
- Prompt rendering.
- One representative extraction fixture when feasible.

## Acceptance Checklist

- The domain auto-discovers at API startup.
- Classification can route a matching paper to the new domain.
- Extraction returns typed data.
- Downstream summary, diagram, and report stages can consume the domain output.
- Documentation includes any domain-specific setup.
