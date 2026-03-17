# Copilot Instructions

## Workflow

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
