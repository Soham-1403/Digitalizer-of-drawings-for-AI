import os

from engine.audit import default_log_path, log_event, read_events


def test_log_event_appends_jsonl(tmp_path):
    log_path = default_log_path(str(tmp_path))

    log_event(log_path, "digitized", {"page_count": 3}, actor="alice")
    log_event(log_path, "exported", {"out_dir": "/tmp/out"}, actor="alice")

    events = read_events(log_path)
    assert len(events) == 2
    assert events[0]["event_type"] == "digitized"
    assert events[0]["actor"] == "alice"
    assert events[0]["details"]["page_count"] == 3
    assert events[1]["event_type"] == "exported"


def test_read_events_on_missing_file_returns_empty_list(tmp_path):
    assert read_events(str(tmp_path / "does_not_exist.jsonl")) == []


def test_log_event_defaults_actor_to_current_user(tmp_path):
    log_path = default_log_path(str(tmp_path))
    log_event(log_path, "page_reviewed", {"page_index": 0})

    events = read_events(log_path)
    assert events[0]["actor"]  # non-empty, whatever the OS user happens to be


def test_default_log_path_is_under_work_dir(tmp_path):
    path = default_log_path(str(tmp_path))
    assert os.path.dirname(path) == str(tmp_path)
    assert path.endswith("audit_log.jsonl")
