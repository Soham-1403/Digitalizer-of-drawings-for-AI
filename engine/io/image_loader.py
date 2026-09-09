"""Image ingestion (PNG/JPG/TIFF, including multi-page TIFF scans).

Normalizes any input image into the same `RasterPage` shape the PDF loader
produces, so the rest of the pipeline never needs to know whether the
original document was a PDF or a scanned image file.
"""

from __future__ import annotations

import os

from PIL import Image, ImageSequence

from engine.io.pdf_loader import RasterPage

DEFAULT_ASSUMED_DPI = 300


def load_image_pages(image_path: str, out_dir: str, assumed_dpi: float | None = None) -> list[RasterPage]:
    """Load a single- or multi-page image file into normalized PNG pages.

    Many scanners write DPI metadata; when present we trust it (it's the
    real physical scale of the scan, which downstream DXF units depend
    on). When absent, we fall back to `assumed_dpi` and record it so the
    UI can prompt the user to correct it — silently guessing a scale for
    a structural drawing is worse than asking.
    """
    os.makedirs(out_dir, exist_ok=True)
    pages: list[RasterPage] = []

    img = Image.open(image_path)
    frames = list(ImageSequence.Iterator(img)) if getattr(img, "n_frames", 1) > 1 else [img]

    for i, frame in enumerate(frames):
        rgb = frame.convert("RGB")
        dpi_meta = frame.info.get("dpi")
        dpi = float(dpi_meta[0]) if dpi_meta else float(assumed_dpi or DEFAULT_ASSUMED_DPI)

        out_path = os.path.join(out_dir, f"page_{i:04d}.png")
        rgb.save(out_path)

        pages.append(
            RasterPage(
                index=i,
                width_px=rgb.width,
                height_px=rgb.height,
                dpi=dpi,
                image_path=out_path,
            )
        )

    return pages


def load_pages(source_path: str, out_dir: str, assumed_dpi: float | None = None) -> list[RasterPage]:
    """Dispatch to the PDF or image loader based on file extension."""
    ext = os.path.splitext(source_path)[1].lower()
    if ext == ".pdf":
        from engine.io.pdf_loader import load_pdf_pages

        return load_pdf_pages(source_path, out_dir, dpi=assumed_dpi or DEFAULT_ASSUMED_DPI)
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        return load_image_pages(source_path, out_dir, assumed_dpi=assumed_dpi)
    raise ValueError(f"Unsupported file type: {ext}. Supported: .pdf, .png, .jpg, .tif, .bmp")
