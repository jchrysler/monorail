"""Notes generation and management."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from .config import get_config
from .extractor import ExtractionResult


NOTES_FILENAME = "monorail-notes.md"


def _get_git_head(project_path: Path) -> Optional[str]:
    """Get the current HEAD commit hash for a project."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:7]  # Short hash
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _get_commits_since(project_path: Path, since_hash: str) -> list[str]:
    """Get commit summaries since a given hash."""
    try:
        result = subprocess.run(
            ["git", "log", f"{since_hash}..HEAD", "--oneline", "--no-decorate"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


LEGACY_NOTES_FILENAME = "mm-notes.md"

CLAUDE_MD_BLOCK_START = "<!-- monorail:start -->"
CLAUDE_MD_BLOCK_END = "<!-- monorail:end -->"
CLAUDE_MD_BLOCK = f"""{CLAUDE_MD_BLOCK_START}
## Session Start
- [ ] Read `context/monorail-notes.md` for recent session history
{CLAUDE_MD_BLOCK_END}
"""


def _update_context_instructions(path: Path) -> None:
    """Update session context references in existing project docs."""
    if not path.exists():
        return

    content = path.read_text()
    updated = content.replace("pool/mm-notes.md", "context/monorail-notes.md")
    updated = updated.replace("pool/monorail-notes.md", "context/monorail-notes.md")
    updated = updated.replace("context/mm-notes.md", "context/monorail-notes.md")
    updated = updated.replace("mm-notes.md", "monorail-notes.md")
    updated = updated.replace("music-man", "monorail")
    updated = updated.replace("Music Man", "Monorail")
    if updated != content:
        path.write_text(updated)


def ensure_claude_md_block(project_path: Path) -> None:
    """Ensure CLAUDE.md has the monorail session context block at the TOP."""
    config = get_config()
    if not config.auto_modify_claude_md:
        return

    claude_md = project_path / "CLAUDE.md"

    if claude_md.exists():
        content = claude_md.read_text()

        # Already has the NEW block at the TOP - nothing to do
        if content.lstrip().startswith(CLAUDE_MD_BLOCK_START):
            return

        # Remove any existing monorail block (old or new format, anywhere in file)
        if "<!-- monorail:start" in content:
            content = re.sub(
                r'\n*<!-- monorail:start[^>]*-->.*?<!-- monorail:end -->\n*',
                '', content, flags=re.DOTALL
            )

        # Remove old-style block (without markers)
        if "## Session Context" in content:
            content = re.sub(r'\n*## Session Context\n.*?(?=\n## |\Z)', '', content, flags=re.DOTALL)

        # Prepend the block at TOP for visibility
        claude_md.write_text(CLAUDE_MD_BLOCK + "\n" + content.lstrip())
    else:
        # Create with just the block
        claude_md.write_text(CLAUDE_MD_BLOCK)


def migrate_project_files(project_path: Path) -> None:
    """Migrate legacy project artifacts to Monorail naming."""
    context_dir = project_path / "context"
    legacy_pool_dir = project_path / "pool"

    # Migrate pool/ → context/ (old directory name)
    if legacy_pool_dir.exists() and not context_dir.exists():
        legacy_pool_dir.rename(context_dir)
    elif legacy_pool_dir.exists() and context_dir.exists():
        # Both exist - move files from pool to context
        for f in legacy_pool_dir.iterdir():
            target = context_dir / f.name
            if not target.exists():
                f.rename(target)

    # Migrate mm-notes.md → monorail-notes.md (old filename)
    legacy_notes = context_dir / LEGACY_NOTES_FILENAME
    new_notes = context_dir / NOTES_FILENAME

    if legacy_notes.exists() and not new_notes.exists():
        legacy_notes.rename(new_notes)

    # Update references in project docs
    _update_context_instructions(project_path / "CLAUDE.md")
    _update_context_instructions(project_path / "agents.md")


def get_notes_path(project_path: Path) -> Path:
    """Get the path to monorail-notes.md for a project."""
    migrate_project_files(project_path)
    return project_path / "context" / NOTES_FILENAME


def update_notes(
    project_path: Path,
    session_id: str,
    extraction: ExtractionResult,
    tool: str = "claude",
):
    """Update monorail-notes.md with extraction results."""
    notes_path = get_notes_path(project_path)
    notes_path.parent.mkdir(parents=True, exist_ok=True)

    # Auto-add CLAUDE.md block on first extraction for this project
    ensure_claude_md_block(project_path)

    project_name = project_path.name
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    # Get current git state
    current_git_commit = _get_git_head(project_path)

    # Load existing notes or create new
    if notes_path.exists():
        content = notes_path.read_text()

        # Check for commits since last session
        stored_commit = _get_stored_git_commit(content)
        if stored_commit and current_git_commit and stored_commit != current_git_commit:
            new_commits = _get_commits_since(project_path, stored_commit)
            if new_commits:
                content = _add_commits_warning(content, new_commits)
    else:
        content = _create_initial_notes(project_name, current_git_commit)

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

    # Update last updated timestamp and git commit
    content = _update_timestamp(content, timestamp)
    if current_git_commit:
        content = _update_git_commit(content, current_git_commit)

    notes_path.write_text(content)


def _create_initial_notes(project_name: str, git_commit: Optional[str] = None) -> str:
    """Create initial monorail-notes.md content."""
    git_line = f"\n_Git commit: {git_commit}_" if git_commit else ""
    return f"""# monorail notes
_Project: {project_name}_
_Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}_{git_line}

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


def _get_stored_git_commit(content: str) -> Optional[str]:
    """Extract the stored git commit hash from notes."""
    match = re.search(r"_Git commit: ([a-f0-9]+)_", content)
    return match.group(1) if match else None


def _update_git_commit(content: str, commit: str) -> str:
    """Update or add the git commit line in notes."""
    if "_Git commit:" in content:
        return re.sub(r"_Git commit: [a-f0-9]+_", f"_Git commit: {commit}_", content)
    else:
        # Add after last updated line
        return re.sub(
            r"(_Last updated: .+_)",
            f"\\1\n_Git commit: {commit}_",
            content,
        )


def _add_commits_warning(content: str, commits: list[str]) -> str:
    """Add a warning about commits that happened between sessions."""
    num_commits = len(commits)

    # Format the warning
    if num_commits == 1:
        warning = f"**⚠️ 1 commit since last session:**\n"
    else:
        warning = f"**⚠️ {num_commits} commits since last session:**\n"

    # Show up to 5 commits
    for commit in commits[:5]:
        warning += f"- {commit}\n"
    if num_commits > 5:
        warning += f"- ... and {num_commits - 5} more\n"

    # Insert after Active Context header
    if "## Active Context" in content:
        return content.replace(
            "## Active Context\n",
            f"## Active Context\n\n{warning}\n",
        )
    return content


def archive_sessions(project: str) -> bool:
    """Archive old sessions for a project."""
    from .watcher import CLAUDE_PROJECTS_DIR, CODEX_SESSIONS_DIR, decode_claude_project_path, extract_project_from_codex_session

    # Find the project by searching native session directories
    def find_project_path(name: str) -> Path | None:
        if CLAUDE_PROJECTS_DIR.exists():
            for encoded_folder in CLAUDE_PROJECTS_DIR.iterdir():
                if not encoded_folder.is_dir():
                    continue
                project_path = decode_claude_project_path(encoded_folder.name)
                if project_path.name == name and project_path.exists():
                    return project_path

        if CODEX_SESSIONS_DIR.exists():
            for session_file in CODEX_SESSIONS_DIR.glob("**/*.jsonl"):
                project_path = extract_project_from_codex_session(session_file)
                if project_path and project_path.name == name and project_path.exists():
                    return project_path
        return None

    project_path = find_project_path(project)
    if project_path:
        notes_path = get_notes_path(project_path)
        if notes_path.exists():
            # TODO: Implement archival logic
            # - Count sessions
            # - If > max_sessions_before_archive, summarize old ones
            # - Move to .monorail-archive/ directory
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
