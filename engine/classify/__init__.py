"""Assigns a `LayerCategory` to each raw detection from `engine.vectorize`.

Deliberately conservative: only patterns with a clear, checkable geometric
signature (structural grid lines, parallel wall pairs, dimension lines
tied to dimension-shaped text) are auto-classified with confidence. Any
detection that doesn't match a known pattern is tagged
`LayerCategory.UNCLASSIFIED` rather than guessed — see
`ARCHITECTURE.md` §1.2. Unclassified entities are exactly what the
low-confidence threshold in `engine.confidence` routes to LLM-vision
fallback or human review.
"""
