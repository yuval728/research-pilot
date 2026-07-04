# GitHub Issues to Create After Publishing

Create these issues manually on GitHub after the repo goes public. Use the labels as specified.

---

## 1. Add System Design domain plugin
**Labels:** `roadmap`, `help wanted`

**Body:**
Implement a new domain plugin for System Design papers under `pipeline/src/domains/system_design/`.

Requirements:
- Create `plugin.py` registering a `DomainPlugin` with `domain_id="system_design"`
- Create `schema.py` with Pydantic models for system design extraction (components, interfaces, data flow, scalability, trade-offs)
- Create prompt templates in `prompts/` for classify, extract, summarise, diagram, codegen
- Register in `pipeline/src/domains/registry.py`
- Add tests for plugin discovery and schema validation
- Update docs/adding-a-domain.md if needed

---

## 2. Add paper comparison feature
**Labels:** `roadmap`

**Body:**
Add a paper comparison view that lets users select 2-3 papers and see side-by-side:
- Extraction comparison (methods, datasets, metrics, results)
- Architecture diagram diff
- Summary comparison
- Citation overlap

UI: New `/compare` route with multi-select from library.
Backend: New API endpoint `/api/v1/papers/compare` accepting list of paper IDs.

---

## 3. Support DOI resolution for more publishers
**Labels:** `help wanted`

**Body:**
Current DOI ingestion only follows CrossRef redirect. Extend to handle:
- Direct PDF URLs from CrossRef metadata (`link` array with `content-type: application/pdf`)
- Publisher-specific patterns (IEEE, ACM, Elsevier, Springer, Nature)
- Fallback to Unpaywall API for open-access versions
- Rate limiting and polite scraping

Files to modify: `pipeline/src/graph/nodes/ingest.py` (`_fetch_doi`)

---

## 4. Add citation graph extraction
**Labels:** `roadmap`

**Body:**
Extract citation networks from papers and build a graph:
- Parse reference sections (Gemini can do this from PDF)
- Resolve citations to arXiv/DOI where possible
- Store as edges in a `citations` table: `citing_paper_id`, `cited_paper_id`, `citation_context`
- API endpoint to fetch citation graph for a paper
- Frontend: Interactive citation graph view (D3.js or Cytoscape)

---

## 5. Improve Mermaid diagram quality for CV papers
**Labels:** `good first issue`

**Body:**
Computer vision papers often have complex architectures (FPN, U-Net, attention modules) that don't render well with current prompts.

Tasks:
- Add CV-specific diagram prompt variants in `pipeline/src/domains/ai_ml/prompts/diagram_v1.j2`
- Include examples of good Mermaid for: encoder-decoder, feature pyramid, attention blocks, multi-scale
- Test on 5-10 CV papers (ResNet, U-Net, YOLO, DETR, ViT, Swin, ConvNeXt, SAM)
- Document patterns that work well

---

## 6. Add Obsidian export
**Labels:** `good first issue`

**Body:**
Export processed papers as Obsidian-compatible markdown vault:
- One `.md` file per paper with frontmatter (title, authors, tags, arXiv ID, DOI)
- Embedded diagrams as Mermaid (Obsidian renders natively)
- Code blocks with syntax highlighting
- Links between papers via `[[wiki-links]]` for citations
- Folder structure: `Papers/Year/Title.md`

New endpoint: `GET /api/v1/papers/{paper_id}/export/obsidian`

---

## 7. Add Notion export
**Labels:** `help wanted`

**Body:**
Export to Notion via their API:
- Create a database with properties: Title, Authors, Domain, Sub-domain, arXiv URL, Status, Tags
- Each paper becomes a page with blocks: Summary, Diagrams (as images), Code (code blocks), Extraction (toggle)
- OAuth flow for user's Notion workspace
- Sync button in paper viewer

Files: New service `pipeline/src/services/notion_export.py`, new API route.

---

## 8. Support batch processing multiple papers
**Labels:** `roadmap`

**Body:**
Allow users to queue multiple papers for processing:
- Frontend: Multi-select in library → "Process selected" button
- Backend: New endpoint `POST /api/v1/pipeline/batch` accepting list of paper IDs
- Queue management: Redis or Supabase-backed queue with concurrency control (max 2-3 parallel)
- Progress: SSE endpoint for batch progress
- Error handling: Partial failures don't stop the batch

---

## 9. Add paper recommendation based on library
**Labels:** `roadmap`

**Body:**
Recommend new papers based on user's processed library:
- Use embeddings from processed papers as user profile
- Query arXiv API for recent papers in similar domains
- Score by cosine similarity to user's centroid embedding
- Weekly digest email / in-app notification
- "Discover" page in frontend

---

## 10. Build evaluation framework for extraction quality
**Labels:** `help wanted`

**Body:**
Create a rigorous evaluation harness:
- Golden dataset: 10-20 papers with manually verified extractions
- Metrics: Field-level precision/recall/F1, schema compliance rate, hallucination rate
- Automated eval script: `uv run python -m pipeline.eval.run --golden-data`
- CI integration: Run on PR, fail if regression detected
- Langfuse integration: Track prompt version vs quality over time

Files: New `pipeline/eval/` module, GitHub Action for nightly eval.

---

## 11. Add Cybersecurity domain plugin
**Labels:** `roadmap`, `help wanted`

**Body:**
Similar to System Design plugin but for security papers:
- Schema: Threat model, attack vector, defense mechanism, evaluation setup, CVEs addressed
- Diagram types: Attack tree, data flow with trust boundaries, mitigation flow
- Codegen: Proof-of-concept exploits (with safety guards), detection rules (Sigma/YARA)

---

## 12. Add audio/video paper ingestion
**Labels:** `roadmap`

**Body:**
Support non-PDF sources:
- YouTube links (conference talks) → Whisper transcription → same pipeline
- arXiv audio versions
- MP4/MP3 upload → transcription → extraction
- New source type in `PaperSource` enum

---

## 13. Improve code generation for training loops
**Labels:** `good first issue`

**Body:**
Current codegen produces skeleton classes. Enhance to generate:
- Complete training loop with optimizer, scheduler, logging
- Distributed training boilerplate (DDP, FSDP)
- Mixed precision (AMP)
- Checkpointing and resume
- WandB/TensorBoard logging
- Config management (Hydra/OmegaConf)

Test by running generated code on a dummy dataset.

---

## 14. Add multi-language summary support
**Labels:** `roadmap`

**Body:**
Generate summaries in languages other than English:
- Add `language` parameter to summarise stage
- Prompt templates with language instruction
- UI: Language selector in paper viewer
- Start with: Chinese, Spanish, French, Japanese, Korean

---

## 15. Add paper chat / Q&A
**Labels:** `roadmap`

**Body:**
Let users ask questions about a processed paper:
- RAG over paper chunks (already embedded)
- Context: extraction + summaries + full text chunks
- Stream responses via SSE
- Cite sources (section, figure, page) in answers
- Frontend: Chat panel in paper viewer
