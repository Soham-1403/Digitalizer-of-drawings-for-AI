import json

import pytest

from engine.cad.layer_registry import (
    export_layer_standard_to_file,
    get_layer_standard,
    load_layer_standard_from_file,
    reset_to_default,
    set_layer_standard,
)
from engine.cad.layers import STRUCTURAL_LAYER_STANDARD
from engine.model import LayerCategory


@pytest.fixture(autouse=True)
def _restore_default_standard():
    yield
    reset_to_default()


def test_default_standard_matches_builtin():
    assert get_layer_standard() == STRUCTURAL_LAYER_STANDARD


def test_partial_override_from_file_merges_onto_default(tmp_path):
    override_path = tmp_path / "firm_standard.json"
    override_path.write_text(
        json.dumps({"S-COLS": {"rgb_hex": "#123456", "lineweight_hundredth_mm": 100}}),
        encoding="utf-8",
    )

    merged = load_layer_standard_from_file(str(override_path))

    assert merged[LayerCategory.COLUMN].rgb_hex == "#123456"
    assert merged[LayerCategory.COLUMN].lineweight_hundredth_mm == 100
    # Untouched fields on the overridden category keep their default.
    assert merged[LayerCategory.COLUMN].linetype == STRUCTURAL_LAYER_STANDARD[LayerCategory.COLUMN].linetype
    # Categories not mentioned in the override file are unaffected.
    assert merged[LayerCategory.WALL] == STRUCTURAL_LAYER_STANDARD[LayerCategory.WALL]

    # And the override is now the active standard everywhere.
    assert get_layer_standard()[LayerCategory.COLUMN].rgb_hex == "#123456"


def test_unknown_layer_name_in_override_raises(tmp_path):
    override_path = tmp_path / "bad_standard.json"
    override_path.write_text(json.dumps({"NOT-A-REAL-LAYER": {"rgb_hex": "#000000"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown layer name"):
        load_layer_standard_from_file(str(override_path))


def test_set_layer_standard_requires_all_categories():
    incomplete = {LayerCategory.GRID: STRUCTURAL_LAYER_STANDARD[LayerCategory.GRID]}
    with pytest.raises(ValueError, match="missing entries"):
        set_layer_standard(incomplete)


def test_export_round_trips_through_load(tmp_path):
    out_path = str(tmp_path / "exported.json")
    export_layer_standard_to_file(out_path)

    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert set(data.keys()) == {c.value for c in LayerCategory}

    # Loading the full export back in should reproduce the same standard.
    reloaded = load_layer_standard_from_file(out_path)
    assert reloaded == STRUCTURAL_LAYER_STANDARD
