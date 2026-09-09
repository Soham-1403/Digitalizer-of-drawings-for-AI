from engine.model import Entity, EntityType, LayerCategory, Page
from engine.review import evaluate_document_readiness, evaluate_page_readiness
from engine.model import VectorDocument


def _page_with_entities(confidences: list[float]) -> Page:
    page = Page(index=0, width_px=100, height_px=100, dpi=300.0, source_image_path="x.png")
    for c in confidences:
        page.entities.append(Entity(type=EntityType.LINE, points=[(0, 0), (1, 1)], layer=LayerCategory.WALL, confidence=c))
    return page


def test_unreviewed_page_with_low_confidence_has_warnings():
    page = _page_with_entities([0.9, 0.2, 0.1])
    readiness = evaluate_page_readiness(page, confidence_threshold=0.55)

    assert not readiness.is_clean
    assert readiness.is_reviewed is False
    assert readiness.low_confidence_count == 2
    assert any("not reviewed" in w for w in readiness.warnings)
    assert any("2 detection" in w for w in readiness.warnings)


def test_marking_reviewed_clears_the_review_warning_but_not_confidence():
    page = _page_with_entities([0.9, 0.2])
    page.mark_reviewed("J. Engineer", "Checked the low-confidence beam manually.")

    readiness = evaluate_page_readiness(page, confidence_threshold=0.55)
    assert readiness.is_reviewed is True
    assert readiness.low_confidence_count == 1
    assert not any("not reviewed" in w for w in readiness.warnings)
    assert any("1 detection" in w for w in readiness.warnings)
    assert not readiness.is_clean  # still has the low-confidence warning


def test_fully_clean_page_has_no_warnings():
    page = _page_with_entities([0.9, 0.95])
    page.mark_reviewed("J. Engineer")

    readiness = evaluate_page_readiness(page, confidence_threshold=0.55)
    assert readiness.is_clean
    assert readiness.warnings == []


def test_clear_review_restores_not_reviewed_state():
    page = _page_with_entities([0.9])
    page.mark_reviewed("Someone")
    assert page.is_reviewed

    page.clear_review()
    assert not page.is_reviewed
    assert page.reviewed_by is None
    assert page.reviewed_at is None


def test_document_readiness_summarizes_only_dirty_pages():
    clean_page = _page_with_entities([0.9])
    clean_page.index = 0
    clean_page.mark_reviewed("Reviewer")

    dirty_page = _page_with_entities([0.1])
    dirty_page.index = 1

    document = VectorDocument(source_file="x.pdf")
    document.add_page(clean_page)
    document.add_page(dirty_page)

    readiness = evaluate_document_readiness(document, confidence_threshold=0.55)
    assert not readiness.is_clean
    lines = readiness.summary_lines()
    assert len(lines) == 1
    assert "Page 2" in lines[0]
