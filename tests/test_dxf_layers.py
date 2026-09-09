import ezdxf

from engine.cad.dxf_writer import write_dxf
from engine.cad.layers import STRUCTURAL_LAYER_STANDARD
from engine.model import Entity, EntitySource, EntityType, LayerCategory, Page, VectorDocument


def _sample_document() -> VectorDocument:
    page = Page(index=0, width_px=1000, height_px=800, dpi=300.0, source_image_path="synthetic.png")
    page.entities = [
        Entity(type=EntityType.LINE, points=[(0, 0), (100, 0)], layer=LayerCategory.GRID, confidence=0.9),
        Entity(type=EntityType.LINE, points=[(0, 50), (0, 150)], layer=LayerCategory.WALL, confidence=0.8),
        Entity(
            type=EntityType.CIRCLE,
            points=[(500, 500)],
            layer=LayerCategory.COLUMN,
            confidence=0.7,
            params={"radius": 20},
        ),
        Entity(
            type=EntityType.TEXT,
            points=[(10, 10)],
            layer=LayerCategory.TEXT,
            confidence=0.6,
            text="NOTE",
            source=EntitySource.LLM,
        ),
    ]
    doc = VectorDocument(source_file="synthetic.png", units="mm")
    doc.add_page(page)
    return doc


def test_write_dxf_creates_layers_with_curated_colors(tmp_path):
    doc = _sample_document()
    out_path = str(tmp_path / "out.dxf")

    write_dxf(doc, out_path)

    result = ezdxf.readfile(out_path)
    for category, spec in STRUCTURAL_LAYER_STANDARD.items():
        layer = result.layers.get(category.value)
        assert layer is not None, f"missing layer {category.value}"
        assert layer.dxf.color == spec.aci

    msp = result.modelspace()
    entity_types = {e.dxftype() for e in msp}
    assert "LINE" in entity_types
    assert "CIRCLE" in entity_types
    assert "TEXT" in entity_types


def test_dxf_entities_carry_confidence_xdata(tmp_path):
    doc = _sample_document()
    out_path = str(tmp_path / "out.dxf")
    write_dxf(doc, out_path)

    result = ezdxf.readfile(out_path)
    msp = result.modelspace()
    lines = [e for e in msp if e.dxftype() == "LINE"]
    assert lines, "expected at least one LINE entity"
    for line in lines:
        assert line.has_xdata("DIGITALIZER")
