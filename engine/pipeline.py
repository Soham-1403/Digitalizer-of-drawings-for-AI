"""End-to-end orchestration: source file -> VectorDocument.

This is the one place that wires io -> preprocess -> vectorize ->
classify -> confidence -> (optional) llm_assist together. Every stage is
independently testable/importable; this module just sequences them with
sensible, tunable defaults via `PipelineConfig`.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import cv2

from engine.classify.layer_rules import (
    classify_dimension_lines,
    classify_grid_lines,
    classify_quad_as_column_or_footing,
    classify_wall_pairs,
)
from engine.classify.symbols import find_grid_bubbles
from engine.confidence.scoring import (
    estimate_local_image_quality,
    rollup_page_confidence,
    score_entity_confidence,
)
from engine.io.pdf_loader import RasterPage
from engine.io.image_loader import load_pages
from engine.llm_assist.fusion import fuse_llm_suggestions
from engine.llm_assist.provider import VisionAssistProvider
from engine.model import Entity, EntitySource, EntityType, LayerCategory, Page, VectorDocument
from engine.preprocess import preprocess_page
from engine.vectorize.contours import detect_hatch_regions
from engine.vectorize.curves import detect_arcs, detect_circles
from engine.vectorize.lines import detect_lines
from engine.vectorize.text_regions import find_text_component_boxes, ocr_text_boxes


@dataclass
class PipelineConfig:
    units: str = "mm"
    assumed_dpi: float = 300.0
    min_line_length_px: float = 20.0
    max_line_gap_px: float = 6.0
    grid_span_ratio_threshold: float = 0.55
    wall_thickness_multiplier_range: tuple[float, float] = (2.5, 20.0)
    column_max_side_ratio: float = 0.08  # relative to min(page_width, page_height)
    dimension_text_max_dist_px: float = 60.0
    grid_bubble_max_dist_px: float = 60.0
    ai_assist_enabled: bool = False
    confidence_threshold: float = 0.55
    ai_provider: VisionAssistProvider | None = None


def digitize_page(raster_page: RasterPage, config: PipelineConfig) -> Page:
    image_bgr = cv2.imread(raster_page.image_path)
    if image_bgr is None:
        raise ValueError(f"Could not read image: {raster_page.image_path}")

    pre = preprocess_page(image_bgr)
    height_px, width_px = pre.binary.shape[:2]

    page = Page(
        index=raster_page.index,
        width_px=width_px,
        height_px=height_px,
        dpi=raster_page.dpi,
        source_image_path=raster_page.image_path,
        skew_angle_deg=pre.skew_angle_deg,
    )

    raw_lines = detect_lines(
        pre.binary, min_length_px=config.min_line_length_px, max_gap_px=config.max_line_gap_px
    )
    circles = detect_circles(pre.binary)
    arcs = detect_arcs(pre.binary)
    hatch_regions = detect_hatch_regions(pre.binary)
    text_boxes_raw = find_text_component_boxes(pre.binary, pre.estimated_line_thickness_px)
    text_results = ocr_text_boxes(pre.gray, text_boxes_raw)

    _classify_and_add_lines(page, raw_lines, text_results, width_px, height_px, pre.estimated_line_thickness_px, config)
    _add_circle_entities(page, circles, text_results, raw_lines, config)
    _add_arc_entities(page, arcs)
    _add_hatch_entities(page, hatch_regions, pre.estimated_line_thickness_px, width_px, height_px)
    _add_text_entities(page, text_results)

    for entity in page.entities:
        quality = estimate_local_image_quality(pre.gray, entity.bounds())
        entity.confidence = score_entity_confidence(
            geometric_confidence=entity.confidence, source_agreement=0.5, local_image_quality=quality
        )

    page.overall_confidence = rollup_page_confidence([e.confidence for e in page.entities])

    if config.ai_assist_enabled and config.ai_provider and config.ai_provider.is_available():
        _run_ai_fallback(page, image_bgr, pre.gray, config)

    return page


def _classify_and_add_lines(page, raw_lines, text_results, width_px, height_px, line_thickness, config):
    grid = classify_grid_lines(raw_lines, width_px, height_px, span_ratio_threshold=config.grid_span_ratio_threshold)
    classified_ids = {id(cl.line) for cl in grid}

    remaining = [l for l in raw_lines if id(l) not in classified_ids]
    min_wall, max_wall = config.wall_thickness_multiplier_range
    walls = classify_wall_pairs(remaining, min_wall_px=line_thickness * min_wall, max_wall_px=line_thickness * max_wall)
    classified_ids |= {id(cl.line) for cl in walls}

    remaining = [l for l in remaining if id(l) not in classified_ids]
    dim_text_boxes = [t for t in text_results if t["is_dimension"]]
    dims = classify_dimension_lines(remaining, dim_text_boxes, max_dist_px=config.dimension_text_max_dist_px)
    classified_ids |= {id(cl.line) for cl in dims}

    remaining = [l for l in remaining if id(l) not in classified_ids]

    for cl in (*grid, *walls, *dims):
        line = cl.line
        page.entities.append(
            Entity(
                type=EntityType.LINE,
                points=line["points"],
                layer=cl.layer,
                confidence=0.5 * line["confidence"] + 0.5 * cl.classification_confidence,
                source=EntitySource.DETERMINISTIC,
                page_index=page.index,
                metadata={"group_id": cl.group_id} if cl.group_id else {},
            )
        )

    for line in remaining:
        page.entities.append(
            Entity(
                type=EntityType.LINE,
                points=line["points"],
                layer=LayerCategory.UNCLASSIFIED,
                confidence=0.5 * line["confidence"] + 0.5 * 0.4,
                source=EntitySource.DETERMINISTIC,
                page_index=page.index,
            )
        )


def _grid_line_endpoints(page: Page) -> list[tuple[float, float]]:
    endpoints = []
    for e in page.entities:
        if e.layer == LayerCategory.GRID and e.type == EntityType.LINE:
            endpoints.extend(e.points)
    return endpoints


def _add_circle_entities(page, circles, text_results, raw_lines, config):
    grid_endpoints = _grid_line_endpoints(page)
    bubbles = find_grid_bubbles(circles, text_results, grid_endpoints, config.grid_bubble_max_dist_px)
    bubble_centers = {b["center"] for b in bubbles}

    for circle in circles:
        is_bubble = circle["center"] in bubble_centers
        layer = LayerCategory.GRID if is_bubble else LayerCategory.UNCLASSIFIED
        confidence = circle["confidence"] if is_bubble else 0.5 * circle["confidence"] + 0.5 * 0.4
        matching_bubble = next((b for b in bubbles if b["center"] == circle["center"]), None)
        text_label = matching_bubble["label"] if matching_bubble else None
        page.entities.append(
            Entity(
                type=EntityType.CIRCLE,
                points=[circle["center"]],
                layer=layer,
                confidence=confidence,
                source=EntitySource.DETERMINISTIC,
                page_index=page.index,
                text=text_label,
                params={"radius": circle["radius"]},
            )
        )


def _add_arc_entities(page, arcs):
    for arc in arcs:
        page.entities.append(
            Entity(
                type=EntityType.ARC,
                points=[arc["center"]],
                layer=LayerCategory.UNCLASSIFIED,
                confidence=0.5 * arc["confidence"] + 0.5 * 0.4,
                source=EntitySource.DETERMINISTIC,
                page_index=page.index,
                params={
                    "radius": arc["radius"],
                    "start_angle_deg": arc["start_angle_deg"],
                    "end_angle_deg": arc["end_angle_deg"],
                },
            )
        )


def _add_hatch_entities(page, hatch_regions, line_thickness_px, width_px, height_px):
    column_max_side_px = min(width_px, height_px) * 0.08
    for region in hatch_regions:
        if region["is_hatch_pattern"]:
            layer, confidence = LayerCategory.HATCH, region["confidence"]
        else:
            quad_result = classify_quad_as_column_or_footing(
                region["boundary"], line_thickness_px, column_max_side_px
            )
            if quad_result:
                layer, confidence = quad_result
            else:
                layer, confidence = LayerCategory.UNCLASSIFIED, 0.5 * region["confidence"] + 0.5 * 0.4

        page.entities.append(
            Entity(
                type=EntityType.HATCH,
                points=region["boundary"],
                layer=layer,
                confidence=confidence,
                source=EntitySource.DETERMINISTIC,
                page_index=page.index,
                params={"is_hatch_pattern": region["is_hatch_pattern"], "fill_ratio": region["fill_ratio"]},
            )
        )


def _add_text_entities(page, text_results):
    for t in text_results:
        if not t["text"]:
            continue
        x0, y0, x1, y1 = t["bbox"]
        layer = LayerCategory.DIMENSION if t["is_dimension"] else LayerCategory.TEXT
        entity_type = EntityType.DIMENSION if t["is_dimension"] else EntityType.TEXT
        geometric_confidence = max(t["confidence"], 0.35)
        page.entities.append(
            Entity(
                type=entity_type,
                points=[(x0, y1), (x1, y1)],
                layer=layer,
                confidence=geometric_confidence,
                source=EntitySource.DETERMINISTIC,
                page_index=page.index,
                text=t["text"],
                params={"height_px": max(1.0, y1 - y0)},
            )
        )


def _run_ai_fallback(page: Page, image_bgr, gray, config: PipelineConfig, force: bool = False) -> None:
    from engine.confidence.scoring import needs_llm_fallback

    if not force:
        entity_confidences = [e.confidence for e in page.entities]
        should_run = needs_llm_fallback(entity_confidences, config.confidence_threshold) or any(
            not a.resolved for a in page.annotations
        )
        if not should_run:
            return

    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok:
        return

    layer_counts: dict[str, int] = {}
    for e in page.entities:
        layer_counts[e.layer.value] = layer_counts.get(e.layer.value, 0) + 1
    summary = f"Overall confidence: {page.overall_confidence:.2f}. Detected by layer: {layer_counts}."
    annotation_notes = [a.note for a in page.annotations if a.note]

    suggestion = config.ai_provider.suggest_entities(
        image_bytes=encoded.tobytes(),
        media_type="image/png",
        deterministic_summary=summary,
        annotation_notes=annotation_notes,
    )

    quality = float(estimate_local_image_quality(gray, (0, 0, page.width_px, page.height_px)))
    fuse_llm_suggestions(page, suggestion, crop_bbox=(0, 0, page.width_px, page.height_px), local_image_quality=quality)
    page.overall_confidence = rollup_page_confidence([e.confidence for e in page.entities])

    for annotation in page.annotations:
        annotation.resolved = True


def rerun_ai_assist_on_page(page: Page, config: PipelineConfig) -> bool:
    """User-triggered "reprocess this region with AI" — e.g. after
    drawing an annotation. Unlike the automatic per-page fallback, this
    always calls the provider regardless of the current confidence
    (the user asked explicitly), as long as one is configured.

    Returns True if the provider actually ran.
    """
    if not (config.ai_assist_enabled and config.ai_provider and config.ai_provider.is_available()):
        return False

    image_bgr = cv2.imread(page.source_image_path)
    if image_bgr is None:
        return False
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    _run_ai_fallback(page, image_bgr, gray, config, force=True)
    return True


def run_pipeline(source_path: str, out_dir: str, config: PipelineConfig | None = None) -> VectorDocument:
    config = config or PipelineConfig()
    os.makedirs(out_dir, exist_ok=True)
    raster_dir = os.path.join(out_dir, "pages_raster")

    raster_pages = load_pages(source_path, raster_dir, assumed_dpi=config.assumed_dpi)
    document = VectorDocument(source_file=source_path, units=config.units)

    for raster_page in raster_pages:
        document.add_page(digitize_page(raster_page, config))

    return document


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def discover_batch_files(directory: str, recursive: bool = False) -> list[str]:
    """Find every supported drawing file under `directory` — for a firm
    pointing this tool at a legacy archive folder rather than uploading
    one file at a time.
    """
    found = []
    walker = os.walk(directory) if recursive else [(directory, [], os.listdir(directory))]
    for root, _dirs, files in walker:
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                found.append(os.path.join(root, name))
        if not recursive:
            break
    return sorted(found)


@dataclass
class BatchFileResult:
    source_path: str
    success: bool
    page_count: int = 0
    dxf_path: str | None = None
    pdf_path: str | None = None
    error: str | None = None


def run_batch(
    paths: list[str],
    out_dir: str,
    config: PipelineConfig,
    audit_log_path: str | None = None,
) -> list[BatchFileResult]:
    """Digitize every file in `paths` unattended, continuing past a
    single file's failure rather than aborting the whole archive run —
    one corrupt/unreadable legacy scan should not stop the other 500
    from processing.
    """
    from engine.cad.dxf_writer import write_dxf
    from engine.cad.pdf_writer import write_pdf

    results: list[BatchFileResult] = []
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        file_out_dir = os.path.join(out_dir, stem)
        try:
            document = run_pipeline(path, file_out_dir, config)
            dxf_path = write_dxf(document, os.path.join(file_out_dir, "output.dxf"))
            pdf_path = write_pdf(document, os.path.join(file_out_dir, "output.pdf"))
            result = BatchFileResult(
                source_path=path, success=True, page_count=len(document.pages), dxf_path=dxf_path, pdf_path=pdf_path
            )
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the batch
            result = BatchFileResult(source_path=path, success=False, error=str(exc))

        results.append(result)

        if audit_log_path:
            from engine.audit import log_event

            log_event(
                audit_log_path,
                "batch_file_digitized" if result.success else "batch_file_failed",
                {"source_path": path, "page_count": result.page_count, "error": result.error},
            )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Digitize scanned/PDF drawings into DXF + PDF (headless). "
        "Pass a single file, or a directory to batch-process every supported file in it."
    )
    parser.add_argument("source", help="Path to a PDF/image file, or a directory for batch mode.")
    parser.add_argument("--out", default="out", help="Output directory.")
    parser.add_argument("--ai-assist", action="store_true", help="Enable Claude-vision fallback assist.")
    parser.add_argument("--units", default="mm", choices=["mm", "in"])
    parser.add_argument("--recursive", action="store_true", help="In batch mode, search subdirectories too.")
    parser.add_argument("--layer-standard", help="Path to a firm CAD-standard JSON override (see docs/layer_standard.md).")
    parser.add_argument("--confidence-threshold", type=float, default=None, help="Override the LLM-fallback confidence threshold.")
    args = parser.parse_args()

    if args.layer_standard:
        from engine.cad.layer_registry import load_layer_standard_from_file

        load_layer_standard_from_file(args.layer_standard)

    config = PipelineConfig(units=args.units, ai_assist_enabled=args.ai_assist)
    if args.confidence_threshold is not None:
        config.confidence_threshold = args.confidence_threshold
    if args.ai_assist:
        from engine.llm_assist.claude_vision import ClaudeVisionProvider

        config.ai_provider = ClaudeVisionProvider()

    if os.path.isdir(args.source):
        from engine.audit import default_log_path

        paths = discover_batch_files(args.source, recursive=args.recursive)
        if not paths:
            print(f"No supported files found in {args.source}")
            return
        print(f"Found {len(paths)} file(s) to digitize.")

        audit_log_path = default_log_path(args.out)
        results = run_batch(paths, args.out, config, audit_log_path=audit_log_path)

        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        for r in succeeded:
            print(f"OK   {r.source_path} -> {r.page_count} page(s), {r.dxf_path}")
        for r in failed:
            print(f"FAIL {r.source_path}: {r.error}")
        print(f"\n{len(succeeded)} succeeded, {len(failed)} failed. Audit log: {audit_log_path}")
        return

    document = run_pipeline(args.source, args.out, config)

    from engine.cad.dxf_writer import write_dxf
    from engine.cad.pdf_writer import write_pdf

    dxf_path = write_dxf(document, os.path.join(args.out, "output.dxf"))
    pdf_path = write_pdf(document, os.path.join(args.out, "output.pdf"))

    for page in document.pages:
        print(f"Page {page.index}: {len(page.entities)} entities, confidence={page.overall_confidence:.2f}")
    print(f"DXF: {dxf_path}")
    print(f"PDF: {pdf_path}")


if __name__ == "__main__":
    main()
