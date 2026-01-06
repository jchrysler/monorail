"""Shared utilities for Monorail."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def format_time_ago(dt: Optional[datetime]) -> str:
    """Format a datetime as a human-readable 'X ago' string.

    Args:
        dt: The datetime to format, or None

    Returns:
        A string like "just now", "5m ago", "2h ago", "3d ago", or "never"
    """
    if not dt:
        return "never"

    delta = datetime.now() - dt
    seconds = delta.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks}w ago"


def find_project_path(name: str) -> Optional[Path]:
    """Find a project path by name from Claude or Codex session directories.

    Args:
        name: The project directory name to find

    Returns:
        The Path to the project, or None if not found
    """
    from .watcher import (
        CLAUDE_PROJECTS_DIR,
        CODEX_SESSIONS_DIR,
        decode_claude_project_path,
        extract_project_from_codex_session,
    )

    # Search Claude projects
    if CLAUDE_PROJECTS_DIR.exists():
        for encoded_folder in CLAUDE_PROJECTS_DIR.iterdir():
            if not encoded_folder.is_dir():
                continue
            project_path = decode_claude_project_path(encoded_folder.name)
            if project_path and project_path.name == name and project_path.exists():
                return project_path

    # Search Codex sessions
    if CODEX_SESSIONS_DIR.exists():
        for session_file in CODEX_SESSIONS_DIR.glob("**/*.jsonl"):
            project_path = extract_project_from_codex_session(session_file)
            if project_path and project_path.name == name and project_path.exists():
                return project_path

    return None
