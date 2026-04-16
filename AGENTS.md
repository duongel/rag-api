# Agents

<!-- Keep in sync with .github/copilot-instructions.md -->

## Workflow

Always start new work by pulling the latest `master` and creating a new branch for your changes.

- **GitHub Flow**: `master` is always deployable.
- New features and fixes go into a **separate branch** off current `master`.
- Branch naming: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`.
- When done, create a **pull request** — never push directly to `master`.

## Commits

Follow **Conventional Commits**:

```
<type>(<optional scope>): <description>
```

Types: `feat`, `fix`, `perf`, `refactor`, `test`, `chore`, `docs`, `ci`, `build`.

- Keep the subject line under 72 characters.
- Use the body for context when the diff isn't self-explanatory.
- One logical change per commit.

## Code

- Python ≥ 3.9 — use `Optional[X]` / `Union[X, Y]` instead of `X | Y`.
- Run `python3 -m pytest tests/` before pushing. All tests must pass.
- No code changes without reading the affected files first.

## Notes And Knowledge Base

- When the user asks about personal notes, documents, Obsidian content, or Paperless knowledge-base content, read `./SKILL.md` first.
- Treat `./SKILL.md` as the canonical guide for how to search and retrieve notes in this repo.
- For note-related questions, use the host's rag-api over HTTP as the primary access path instead of reading the vault directly.
- In this Codex environment, use `http://127.0.0.1:8484` for note requests with host-network access when needed.
- Do not rely on `http://host.docker.internal:8484` here because that hostname does not resolve in this environment.
- Only fall back to direct filesystem reads of the vault if the host rag-api is unavailable.
- Prefer the HTTP API and tool patterns documented in `./SKILL.md` to answer note-related questions.
- Use the search mode described in `./SKILL.md`:
  - semantic search for broad or fuzzy questions
  - hybrid search as the default when the query includes both natural language and specific identifiers
  - keyword search for exact terms, filenames, IDs, URLs, or abbreviations
- Only apply `paperless_*` filters when the user explicitly asks for Paperless documents such as invoices, receipts, contracts, or scanned mail, because those filters exclude Obsidian notes.
