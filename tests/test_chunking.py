#!/usr/bin/env python3
"""Quick test: verify recursive chunking on Erfolgsjournal.md."""
import sys
sys.path.insert(0, "src")

from rag_api.parser import parse_markdown

chunks = parse_markdown("duong/Erfolgsjournal.md", "/Users/duong.tran/Obsidian")
print("Total chunks:", len(chunks))
print()
for i, c in enumerate(chunks):
    preview = c.content.replace("\n", " ")[:60]
    print("  Chunk %2d: len=%5d  sec=%-35r  [%s...]" % (i, len(c.content), c.section[:35], preview))
print()
max_len = max(len(c.content) for c in chunks)
print("Max chunk content length:", max_len)
print("All chunks <= 1700:", max_len <= 1700)
