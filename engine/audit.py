"""A minimal, append-only audit log.

Not a substitute for a firm's actual QA/compliance system — this is
local, unauthenticated, and trivially editable by anyone with file
access. What it *does* give a small/medium deployment for free: a
plain-text, timestamped record of who reviewed, exported, or saved what
and when, in a format (JSON Lines) that's trivial to `grep`, ingest into
a spreadsheet, or forward to a real logging pipeline later if the firm's
IT/compliance function wants one. Every event also carries an `actor`
field (OS username by default) so "who did this" survives even if the
log file is later centralized.
"""

from __future__ import annotations

import getpass
import json
import os
import time
from typing import Any


def default_log_path(work_dir: str) -> str:
    return os.path.join(work_dir, "audit_log.jsonl")


def log_event(log_path: str, event_type: str, details: dict[str, Any], actor: str | None = None) -> None:
    """Append one event. Never raises on a logging failure — an audit
    log that crashes the app defeats its own purpose — but the failure
    is printed to stderr so it isn't silently lost either.
    """
    record = {
        "timestamp": time.time(),
        "actor": actor or getpass.getuser(),
        "event_type": event_type,
        "details": details,
    }
    try:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:  # noqa: BLE001 - logging must never break the caller
        import sys

        print(f"[audit] failed to write event to {log_path}: {exc}", file=sys.stderr)


def read_events(log_path: str) -> list[dict[str, Any]]:
    if not os.path.exists(log_path):
        return []
    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
