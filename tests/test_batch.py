import os

import cv2

from engine.audit import read_events
from engine.pipeline import PipelineConfig, discover_batch_files, run_batch


def test_discover_batch_files_filters_by_extension_non_recursive(tmp_path):
    (tmp_path / "drawing_a.pdf").write_bytes(b"fake")
    (tmp_path / "drawing_b.png").write_bytes(b"fake")
    (tmp_path / "notes.txt").write_bytes(b"not a drawing")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "drawing_c.png").write_bytes(b"fake")

    found = discover_batch_files(str(tmp_path), recursive=False)
    names = sorted(os.path.basename(p) for p in found)
    assert names == ["drawing_a.pdf", "drawing_b.png"]


def test_discover_batch_files_recursive_includes_subdirectories(tmp_path):
    (tmp_path / "drawing_a.png").write_bytes(b"fake")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "drawing_c.png").write_bytes(b"fake")

    found = discover_batch_files(str(tmp_path), recursive=True)
    names = sorted(os.path.basename(p) for p in found)
    assert names == ["drawing_a.png", "drawing_c.png"]


def test_run_batch_continues_past_a_broken_file(tmp_path, synthetic_drawing_bgr):
    good_path = str(tmp_path / "good.png")
    cv2.imwrite(good_path, synthetic_drawing_bgr)

    broken_path = str(tmp_path / "broken.png")
    (tmp_path / "broken.png").write_bytes(b"not a real png")

    out_dir = str(tmp_path / "out")
    audit_log_path = str(tmp_path / "audit.jsonl")

    results = run_batch([good_path, broken_path], out_dir, PipelineConfig(), audit_log_path=audit_log_path)

    by_path = {r.source_path: r for r in results}
    assert by_path[good_path].success is True
    assert by_path[good_path].page_count == 1
    assert os.path.getsize(by_path[good_path].dxf_path) > 0

    assert by_path[broken_path].success is False
    assert by_path[broken_path].error

    events = read_events(audit_log_path)
    event_types = {e["event_type"] for e in events}
    assert "batch_file_digitized" in event_types
    assert "batch_file_failed" in event_types
