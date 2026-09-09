import cv2

from engine.model import Entity, EntityType, LayerCategory, Page, VectorDocument
from engine.project.manager import load_project, save_project
from engine.project.schema import Project


def test_save_and_load_project_round_trip(tmp_path, synthetic_drawing_bgr):
    image_path = str(tmp_path / "page_0000.png")
    cv2.imwrite(image_path, synthetic_drawing_bgr)

    page = Page(index=0, width_px=1000, height_px=800, dpi=300.0, source_image_path=image_path)
    page.entities.append(
        Entity(type=EntityType.LINE, points=[(0, 0), (10, 10)], layer=LayerCategory.WALL, confidence=0.8)
    )
    document = VectorDocument(source_file="synthetic.png", units="mm")
    document.add_page(page)

    project = Project(name="test", source_file_name="synthetic.png", document=document, dpi=300.0)
    project.snapshot(note="initial")

    out_path = str(tmp_path / "project.dgz")
    saved_path = save_project(project, {0: image_path}, out_path)

    extract_dir = str(tmp_path / "extracted")
    loaded_project, raster_paths = load_project(saved_path, extract_dir)

    assert loaded_project.name == "test"
    assert len(loaded_project.history) == 1
    assert len(loaded_project.document.pages) == 1
    assert loaded_project.document.pages[0].entities[0].layer == LayerCategory.WALL
    assert 0 in raster_paths
    assert cv2.imread(raster_paths[0]) is not None
