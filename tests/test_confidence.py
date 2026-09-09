from engine.confidence.scoring import (
    needs_llm_fallback,
    rollup_page_confidence,
    score_entity_confidence,
)


def test_user_locked_entity_is_always_full_confidence():
    assert score_entity_confidence(geometric_confidence=0.0, user_locked=True) == 1.0


def test_confidence_is_bounded():
    for geo in (-1.0, 0.0, 0.5, 1.0, 2.0):
        score = score_entity_confidence(geometric_confidence=geo)
        assert 0.0 <= score <= 1.0


def test_rollup_penalizes_high_variance():
    uniform = rollup_page_confidence([0.6, 0.6, 0.6, 0.6])
    mixed = rollup_page_confidence([0.1, 1.0, 0.1, 1.0])
    assert uniform > mixed  # same mean, but mixed should be penalized for spread


def test_needs_llm_fallback_threshold():
    assert needs_llm_fallback([0.9, 0.95], threshold=0.55) is False
    assert needs_llm_fallback([0.1, 0.2], threshold=0.55) is True
    assert needs_llm_fallback([]) is True
