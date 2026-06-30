# Open Source Launch Plan

Use this as the public-release checklist before switching the repository visibility to public.

## Must Do Before Public

- Run a secrets scan across the full Git history, not only the current tree.
- Remove or rewrite any commit that ever contained credentials, private URLs, or personal data.
- Verify a fresh clone can run the API and frontend from the README in under 10 minutes.
- Add launch screenshots and demo GIFs under `assets/`.
- Replace placeholder GitHub URLs in README and CONTRIBUTING with the real repository URL.
- Confirm the deployed demo has test data that does not expose private papers or keys.

## GitHub Repository Setup

Recommended description:

```text
Open source AI pipeline that turns ML papers into architecture diagrams, summaries, and implementation code.
```

Recommended topics:

```text
machine-learning, llm, langgraph, gemini, research, nlp, open-source, python, react, vite, fastapi, supabase
```

Recommended links:

- Website: hosted demo URL.
- Social preview: `assets/social/github-social-preview.png` at 1280x640.
- Pinned repo on your GitHub profile.

## Seed Issues

Create these as GitHub issues after publishing:

- Add System Design domain plugin. Labels: `roadmap`, `help wanted`.
- Add Cybersecurity domain plugin. Labels: `roadmap`, `help wanted`.
- Add paper comparison view. Labels: `roadmap`.
- Support DOI resolution for more publishers. Labels: `help wanted`.
- Add citation graph extraction. Labels: `roadmap`.
- Improve Mermaid diagram quality for computer vision papers. Labels: `good first issue`.
- Add Obsidian export. Labels: `good first issue`.
- Add Notion export. Labels: `help wanted`.
- Support batch processing multiple papers. Labels: `roadmap`.
- Build extraction quality evaluation framework. Labels: `help wanted`.

## Launch Assets

Minimum assets before launch:

- Demo GIF: paste arXiv URL, run pipeline, open paper viewer, show diagram, show code.
- Screenshot: extraction sidebar.
- Screenshot: multi-level summary.
- Screenshot: architecture diagram from Attention Is All You Need.
- Screenshot: generated PyTorch code.
- Social preview image.

## Distribution Plan

Launch in this order:

1. Publish the GitHub repo with polished README, screenshots, and issues.
2. Post a concise technical demo on X, LinkedIn, and relevant Discord/Slack communities.
3. Share a deeper engineering write-up explaining the LangGraph + Gemini + Supabase architecture.
4. Submit to Hacker News only after the hosted demo and cold-start docs are stable.
5. Follow up one week later with a concrete improvement, not just a reminder post.

## Positioning

Lead with the concrete output, not the model stack:

```text
Research Pilot turns ML papers into structured extraction, diagrams, summaries, and implementation code.
```

Avoid vague claims like "AI research assistant". The differentiator is artifact generation from papers.
