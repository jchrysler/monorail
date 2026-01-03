"""Notes generation and management."""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from .config import get_config
from .extractor import ExtractionResult


def get_notes_path(project_path: Path) -> Path:
    """Get the path to mm-notes.md for a project."""
    return project_path / "pool" / "mm-notes.md"


def update_notes(
    project_path: Path,
    session_id: str,
    extraction: ExtractionResult,
    tool: str = "claude",
):
    """Update mm-notes.md with extraction results."""
    notes_path = get_notes_path(project_path)
    notes_path.parent.mkdir(parents=True, exist_ok=True)

    project_name = project_path.name
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    # Load existing notes or create new
    if notes_path.exists():
        content = notes_path.read_text()
    else:
        content = _create_initial_notes(project_name)

    # Update active context section
    content = _update_active_context(content, extraction)

    # Add new session entry
    session_entry = _format_session_entry(
        session_id=session_id,
        timestamp=timestamp,
        tool=tool,
        extraction=extraction,
    )
    content = _insert_session_entry(content, session_entry)

    # Update last updated timestamp
    content = _update_timestamp(content, timestamp)

    notes_path.write_text(content)


def _create_initial_notes(project_name: str) -> str:
    """Create initial mm-notes.md content."""
    return f"""# mm notes
_Project: {project_name}_
_Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}_

## Active Context

**Current task:** Not set
**Blockers:** None
**Priority notes:** None

## Session Log

"""


def _update_active_context(content: str, extraction: ExtractionResult) -> str:
    """Update the Active Context section."""
    # Update current task if we have a stated goal
    if extraction.stated_goal:
        content = re.sub(
            r"\*\*Current task:\*\* .+",
            f"**Current task:** {extraction.stated_goal}",
            content,
        )

    return content


def _format_session_entry(
    session_id: str,
    timestamp: str,
    tool: str,
    extraction: ExtractionResult,
) -> str:
    """Format a session entry for the notes."""
    entry = f"""### {session_id} | {timestamp} | {tool}

**Stated goal:** {extraction.stated_goal or "Not stated"}

**What happened:**
"""
    for item in extraction.what_happened:
        entry += f"- {item}\n"

    entry += f"""
**Left off at:**
{extraction.left_off_at or "Not specified"}

**Loose threads:**
"""
    for thread in extraction.loose_threads:
        entry += f"- {thread}\n"

    if extraction.key_artifacts:
        entry += "\n**Key artifacts:**\n"
        for path, desc in extraction.key_artifacts.items():
            entry += f"- {path}: {desc}\n"

    entry += "\n---\n\n"
    return entry


def _insert_session_entry(content: str, entry: str) -> str:
    """Insert a new session entry after the Session Log header."""
    marker = "## Session Log\n\n"
    if marker in content:
        parts = content.split(marker)
        return parts[0] + marker + entry + parts[1]
    else:
        # Append at end
        return content + "\n" + entry


def _update_timestamp(content: str, timestamp: str) -> str:
    """Update the last updated timestamp."""
    return re.sub(
        r"_Last updated: .+_",
        f"_Last updated: {timestamp}_",
        content,
    )


def archive_sessions(project: str) -> bool:
    """Archive old sessions for a project."""
    config = get_config()

    # Find the project
    for watch_path in config.watch_paths:
        notes_path = Path(watch_path) / project / "pool" / "mm-notes.md"
        if notes_path.exists():
            # TODO: Implement archival logic
            # - Count sessions
            # - If > max_sessions_before_archive, summarize old ones
            # - Move to .mm-archive/ directory
            return True

    return False


def get_loose_threads(project_path: Path, limit: int = 5) -> list[str]:
    """Get recent loose threads from a project's notes."""
    notes_path = get_notes_path(project_path)
    if not notes_path.exists():
        return []

    content = notes_path.read_text()
    threads = []

    # Find all loose threads sections
    for match in re.finditer(r"\*\*Loose threads:\*\*\n((?:- .+\n?)+)", content):
        for item in re.findall(r"- (.+)", match.group(1)):
            threads.append(item.strip())

    return threads[:limit]


def get_current_task(project_path: Path) -> str:
    """Get the current task from a project's notes."""
    notes_path = get_notes_path(project_path)
    if not notes_path.exists():
        return ""

    content = notes_path.read_text()
    match = re.search(r"\*\*Current task:\*\* (.+)", content)
    return match.group(1) if match else ""


def get_last_session_time(project_path: Path) -> Optional[datetime]:
    """Get the timestamp of the last session."""
    notes_path = get_notes_path(project_path)
    if not notes_path.exists():
        return None

    content = notes_path.read_text()
    # Look for session headers like "### a7b3f | 2025-01-02 14:15 | claude"
    matches = re.findall(r"### \w+ \| (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \|", content)
    if matches:
        try:
            return datetime.strptime(matches[0], "%Y-%m-%d %H:%M")
        except ValueError:
            return None
    return None
