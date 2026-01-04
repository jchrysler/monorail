"""Inbox processing for developer notes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import INBOX_FILE


def add_note(message: str):
    """Add a note to the inbox."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Read existing content
    if INBOX_FILE.exists():
        content = INBOX_FILE.read_text()
    else:
        content = "# Monorail Inbox\n\n"

    # Remove the "no pending notes" placeholder if present
    content = content.replace("_No pending notes._\n", "")

    # Add the new note
    note_line = f"- [{timestamp}] {message}\n"

    # Insert after the header
    if "# Monorail Inbox\n\n" in content:
        content = content.replace(
            "# Monorail Inbox\n\n",
            f"# Monorail Inbox\n\n{note_line}",
        )
    else:
        content += note_line

    INBOX_FILE.write_text(content)


def get_pending_notes() -> list[tuple[str, str]]:
    """Get all pending notes from inbox as (timestamp, message) tuples."""
    if not INBOX_FILE.exists():
        return []

    content = INBOX_FILE.read_text()
    notes = []

    for line in content.split("\n"):
        if line.startswith("- ["):
            # Parse "[timestamp] message"
            try:
                ts_end = line.index("]", 3)
                timestamp = line[3:ts_end]
                message = line[ts_end + 2:]
                notes.append((timestamp, message))
            except ValueError:
                continue

    return notes


def clear_inbox():
    """Clear all processed notes from inbox."""
    INBOX_FILE.write_text("# Monorail Inbox\n\n_No pending notes._\n")


def count_pending() -> int:
    """Count pending notes in inbox."""
    return len(get_pending_notes())
