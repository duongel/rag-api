"""Root conftest: ensure ``src/`` is on sys.path so ``import rag_api`` works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

