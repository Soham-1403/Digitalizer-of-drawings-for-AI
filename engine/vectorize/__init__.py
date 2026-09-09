"""Deterministic vectorization: raster binary mask -> vector primitives.

Each submodule handles one primitive family and returns plain geometry
(tuples/lists), not `engine.model.Entity` objects — the pipeline module
wraps the results into `Entity` instances once classification/confidence
have both run, since an entity isn't "complete" until it has a layer and
a confidence score.
"""
