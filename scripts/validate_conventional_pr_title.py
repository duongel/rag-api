#!/usr/bin/env python3
"""Validate that a PR title follows Conventional Commits."""

from __future__ import annotations

import re
import sys

ALLOWED_TYPES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)

CONVENTIONAL_TITLE_PATTERN = re.compile(
    rf"^(?:{'|'.join(ALLOWED_TYPES)})(?:\([a-z0-9._/-]+\))?(?:!)?:\s.+$"
)


def is_valid_conventional_title(title: str) -> bool:
    return bool(CONVENTIONAL_TITLE_PATTERN.match(title.strip()))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_conventional_pr_title.py '<pr-title>'", file=sys.stderr)
        return 2

    title = argv[1]
    if is_valid_conventional_title(title):
        print(f"\u2705 Conventional PR title valid: {title}")
        return 0

    print("\u274c PR title must follow Conventional Commits:", file=sys.stderr)
    print("   <type>(optional-scope): short description", file=sys.stderr)
    print(
        "   Allowed types: " + ", ".join(ALLOWED_TYPES),
        file=sys.stderr,
    )
    print("   Example: feat(api): add search endpoint", file=sys.stderr)
    print(f"   Got: {title}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
