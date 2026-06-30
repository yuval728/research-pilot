# Security Policy

## Reporting A Vulnerability

Please do not open public issues for security vulnerabilities.

Before the project has a dedicated security contact, email the maintainer directly or use a private GitHub security advisory if available. Include:

- Affected commit or release.
- Reproduction steps.
- Impact and affected data.
- Any suggested fix.

## Supported Versions

The project is pre-1.0. Security fixes target the `main` branch unless release branches are introduced later.

## Sensitive Data

Never commit:

- `.env` files.
- Supabase service-role keys.
- Gemini or Langfuse keys.
- Private papers or generated outputs from private papers.
- Database dumps.

Run a history-aware secret scan before making the repository public.
