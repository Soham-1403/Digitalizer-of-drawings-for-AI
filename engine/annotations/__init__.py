"""On-canvas markup/annotation helpers.

The `Annotation` data type itself lives in `engine.model` (it's part of
`Page`, alongside `Entity`); this package holds constructor helpers and
validation so callers (the desktop app, tests) don't need to poke at the
dataclass fields directly.
"""
