import cv2

from engine.cad.dxf_writer import write_dxf
from engine.cad.pdf_writer import write_pdf
from engine.io.pdf_loader import RasterPage
from engine.model import LayerCategory
from engine.pipeline import PipelineConfig, digitize_page


def test_full_pipeline_on_synthetic_drawing(tmp_path, synthetic_drawing_bgr):
    image_path = str(tmp_path / "page_0000.png")
    cv2.imwrite(image_path, synthetic_drawing_bgr)

    raster_page = RasterPage(index=0, width_px=1000, height_px=800, dpi=300.0, image_path=image_path)
    config = PipelineConfig()

    page = digitize_page(raster_page, config)

    assert len(page.entities) > 0
    assert 0.0 <= page.overall_confidence <= 1.0
    for entity in page.entities:
        assert 0.0 <= entity.confidence <= 1.0

    grid_lines = [e for e in page.entities if e.layer == LayerCategory.GRID]
    assert len(grid_lines) >= 3, "expected the 3 synthetic grid lines to be classified as GRID"

    wall_lines = [e for e in page.entities if e.layer == LayerCategory.WALL]
    assert len(wall_lines) >= 2, "expected the parallel wall pair to be classified as WALL"

    from engine.model import VectorDocument

    document = VectorDocument(source_file=image_path, units="mm")
    document.add_page(page)

    dxf_path = write_dxf(document, str(tmp_path / "out.dxf"))
    pdf_path = write_pdf(document, str(tmp_path / "out.pdf"))

    import os

    assert os.path.getsize(dxf_path) > 0
    assert os.path.getsize(pdf_path) > 0
