"""PDF ingestion.

Rasterizes every page of a PDF at a controlled DPI so the rest of the
pipeline always works on pixel-space images with a known, consistent
scale. Also exposes `extract_text_spans`, which pulls any text that is
*already vector* in the PDF (i.e. the PDF was exported from AutoCAD/Revit
rather than being a scanned raster) — a fast, perfectly-accurate source of
dimension/label text when it's available, used as a hint by the
text/dimension vectorization stage instead of relying on OCR for that
subset of documents.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF

DEFAULT_DPI = 300


@dataclass
class RasterPage:
    index: int
    width_px: int
    height_px: int
    dpi: float
    image_path: str


@dataclass
class TextSpan:
    page_index: int
    text: str
    # bbox in PDF point space (72 dpi); caller converts to pixel space
    bbox: tuple[float, float, float, float]


def load_pdf_pages(pdf_path: str, out_dir: str, dpi: float = DEFAULT_DPI) -> list[RasterPage]:
    """Rasterize every page of `pdf_path` into `out_dir` as PNGs.

    Returns one RasterPage per page, in document order.
    """
    os.makedirs(out_dir, exist_ok=True)
    pages: list[RasterPage] = []
    zoom = dpi / 72.0  # PDF native resolution is 72 dpi

    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = os.path.join(out_dir, f"page_{i:04d}.png")
            pix.save(image_path)
            pages.append(
                RasterPage(
                    index=i,
                    width_px=pix.width,
                    height_px=pix.height,
                    dpi=dpi,
                    image_path=image_path,
                )
            )
    finally:
        doc.close()
    return pages


def extract_text_spans(pdf_path: str) -> list[TextSpan]:
    """Extract already-vector text from a "born-digital" PDF, if any.

    Returns an empty list for a pure raster-scan PDF (which is the common
    case for this tool) — callers must not assume this is populated.
    """
    spans: list[TextSpan] = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        spans.append(
                            TextSpan(page_index=i, text=text, bbox=tuple(span["bbox"]))
                        )
    finally:
        doc.close()
    return spans


def is_born_digital(pdf_path: str, min_chars: int = 20) -> bool:
    """Heuristic: does this PDF already contain meaningful vector text?

    Used by the pipeline to decide whether OCR is even necessary for text
    regions on a given page, versus relying purely on scanned raster.
    """
    total = sum(len(s.text) for s in extract_text_spans(pdf_path))
    return total >= min_chars
