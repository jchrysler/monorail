"""File watcher for Claude Code and Codex native session files."""

from __future__ import annotations

import json
import random
import string
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional
from dataclasses import dataclass, field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

from .config import get_config

# Native session directories
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


@dataclass
class SessionState:
    """State for a single session file."""
    project_path: Path
    session_file: Path
    tool: str  # "claude" or "codex"
    last_position: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None
    pending_jsonl: str = ""
    pending_content: str = ""
    # Display fields (updated after extraction)
    status: str = ""
    vibe: str = ""
    stated_goal: str = ""
    loose_threads: list = field(default_factory=list)
    last_extraction_time: Optional[datetime] = None


def generate_session_id() -> str:
    """Generate a session ID like 'a7b3f-20250102-1415'."""
    chars = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{chars}-{timestamp}"


def decode_claude_project_path(encoded_name: str) -> Path:
    """Decode Claude's encoded project folder name to real path.

    Example: '-Users-jeremy-chrysler-monorail' -> '/Users/jeremy.chrysler/monorail'

    Claude encodes paths by replacing / with - and . with -
    We need to reconstruct the original path by trying combinations.
    """
    if not encoded_name.startswith("-"):
        return Path(encoded_name)

    # Split by hyphens (excluding the leading one)
    parts = encoded_name[1:].split("-")
    # parts = ['Users', 'jeremy', 'chrysler', 'monorail']

    # Try to reconstruct the path by testing if each combination exists
    # Start from the beginning and greedily find valid path segments
    def find_path(parts: list[str], current_path: Path) -> Path | None:
        if not parts:
            return current_path if current_path.exists() else None

        # Try increasingly longer combinations of parts joined by different separators
        for length in range(1, len(parts) + 1):
            segment_parts = parts[:length]
            remaining = parts[length:]

            # Try different separators: /, ., -
            for sep in ['', '.', '-']:
                if sep == '' and length > 1:
                    continue  # Skip empty separator for multi-part
                segment = sep.join(segment_parts) if sep else segment_parts[0]
                test_path = current_path / segment

                if test_path.exists():
                    if not remaining:
                        return test_path
                    result = find_path(remaining, test_path)
                    if result:
                        return result

        return None

    result = find_path(parts, Path("/"))
    if result:
        return result

    # Fallback: simple hyphen-to-slash replacement
    simple_path = "/" + encoded_name[1:].replace("-", "/")
    return Path(simple_path)


def extract_project_from_codex_session(session_file: Path) -> Optional[Path]:
    """Extract project path from Codex session file's session_meta."""
    try:
        with open(session_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("type") == "session_meta":
                    cwd = data.get("payload", {}).get("cwd")
                    if cwd:
                        return Path(cwd)
                break  # Only check first line
    except (json.JSONDecodeError, IOError):
        pass
    return None


def parse_claude_jsonl(content: str) -> str:
    """Parse Claude JSONL and extract readable conversation content."""
    lines = []
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            msg = data.get("message", {})
            role = msg.get("role", "")

            # Extract text content
            content_items = msg.get("content", [])
            if isinstance(content_items, str):
                text = content_items
            elif isinstance(content_items, list):
                text_parts = []
                for item in content_items:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_use":
                            tool_name = item.get("name", "unknown")
                            text_parts.append(f"[Tool: {tool_name}]")
                        elif item.get("type") == "tool_result":
                            text_parts.append("[Tool result]")
                    elif isinstance(item, str):
                        text_parts.append(item)
                text = " ".join(text_parts)
            else:
                text = ""

            if text and role:
                lines.append(f"{role}: {text[:500]}")  # Truncate long messages

        except json.JSONDecodeError:
            continue

    return "\n".join(lines)


def parse_codex_jsonl(content: str) -> str:
    """Parse Codex JSONL and extract readable conversation content."""
    lines = []
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            msg_type = data.get("type", "")

            if msg_type == "response_item":
                payload = data.get("payload", {})
                role = payload.get("role", "")
                content_items = payload.get("content", [])

                text_parts = []
                for item in content_items:
                    if isinstance(item, dict):
                        if item.get("type") == "input_text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "text":
                            text_parts.append(item.get("text", ""))

                text = " ".join(text_parts)
                if text and role:
                    lines.append(f"{role}: {text[:500]}")

        except json.JSONDecodeError:
            continue

    return "\n".join(lines)


class NativeSessionHandler(FileSystemEventHandler):
    """Handle changes to Claude and Codex native session files."""

    def __init__(
        self,
        on_new_content: Callable[[Path, str, str], bool],
        on_session_end: Callable[[Path, str], None],
    ):
        super().__init__()
        self.sessions: dict[str, SessionState] = {}
        self.on_new_content = on_new_content
        self.on_session_end = on_session_end
        self.config = get_config()
        # Track active session file per project (for /clear detection)
        self.active_session_per_project: dict[str, str] = {}  # project_path -> session_key

    def on_modified(self, event):
        """Handle file modification events."""
        if not isinstance(event, FileModifiedEvent):
            return
        self._handle_file_event(Path(event.src_path))

    def on_created(self, event):
        """Handle file creation events."""
        if not isinstance(event, FileCreatedEvent):
            return
        self._handle_file_event(Path(event.src_path))

    def _handle_file_event(self, path: Path):
        """Process a file event for Claude or Codex sessions."""
        if not path.suffix == ".jsonl":
            return

        # Determine if this is Claude or Codex
        path_str = str(path)

        if ".claude/projects" in path_str:
            self._process_claude_session(path)
        elif ".codex/sessions" in path_str:
            self._process_codex_session(path)

    def _process_claude_session(self, session_file: Path):
        """Process a Claude Code session file."""
        # Extract project path from the encoded folder name
        # ~/.claude/projects/-Users-jeremy-chrysler-monorail/session-id.jsonl
        encoded_folder = session_file.parent.name
        project_path = decode_claude_project_path(encoded_folder)

        self._process_session(session_file, project_path, "claude", parse_claude_jsonl)

    def _process_codex_session(self, session_file: Path):
        """Process a Codex session file."""
        # Extract project path from session_meta in the file
        project_path = extract_project_from_codex_session(session_file)
        if not project_path:
            return

        self._process_session(session_file, project_path, "codex", parse_codex_jsonl)

    def _process_session(
        self,
        session_file: Path,
        project_path: Path,
        tool: str,
        parser: Callable[[str], str],
    ):
        """Process changes to a session file."""
        session_key = str(session_file)
        project_key = str(project_path)

        # Check if this is a new session for a project with an existing active session
        # This indicates /clear happened - flush the previous session immediately
        if project_key in self.active_session_per_project:
            prev_session_key = self.active_session_per_project[project_key]
            if prev_session_key != session_key and prev_session_key in self.sessions:
                prev_state = self.sessions[prev_session_key]
                if prev_state.pending_content:
                    # Flush previous session before switching
                    self.on_new_content(
                        prev_state.project_path,
                        prev_state.session_id,
                        prev_state.pending_content,
                    )
                    prev_state.pending_content = ""
                self.on_session_end(prev_state.project_path, prev_state.session_id)

        # Update active session for this project
        self.active_session_per_project[project_key] = session_key

        # Get or create session state
        if session_key not in self.sessions:
            self.sessions[session_key] = SessionState(
                project_path=project_path,
                session_file=session_file,
                tool=tool,
                session_id=generate_session_id(),
            )

        state = self.sessions[session_key]

        # Read new content
        try:
            with open(session_file, "r") as f:
                f.seek(state.last_position)
                new_content = f.read()
                state.last_position = f.tell()
        except Exception:
            return

        if not new_content:
            return

        # Check for time gap BEFORE updating last_activity
        # If there's a large gap (laptop sleep, long break), treat as new session
        if state.pending_content and state.last_activity:
            gap = (datetime.now() - state.last_activity).total_seconds()
            if gap >= self.config.session_gap_seconds:
                # Flush current session before starting new one
                self.on_new_content(
                    state.project_path,
                    state.session_id,
                    state.pending_content,
                )
                state.pending_content = ""
                state.session_id = generate_session_id()

        state.last_activity = datetime.now()

        combined = state.pending_jsonl + new_content
        lines = combined.split("\n")
        if combined.endswith("\n"):
            state.pending_jsonl = ""
        else:
            state.pending_jsonl = lines.pop()

        if not lines:
            return

        # Parse the JSONL content
        parsed_content = parser("\n".join(lines))
        if not parsed_content:
            return

        state.pending_content += parsed_content + "\n"

        # Check if we have enough content to extract
        if len(state.pending_content.encode()) >= self.config.min_new_bytes:
            if self.on_new_content(
                project_path,
                state.session_id,
                state.pending_content,
            ):
                state.pending_content = ""

    def check_idle_sessions(self):
        """Check for sessions that have been idle too long."""
        now = datetime.now()
        for key, state in self.sessions.items():
            if state.pending_content:
                idle_time = (now - state.last_activity).total_seconds()
                if idle_time >= self.config.idle_seconds:
                    if self.on_new_content(
                        state.project_path,
                        state.session_id,
                        state.pending_content,
                    ):
                        state.pending_content = ""


class Watcher:
    """Watches for Claude Code and Codex native session files."""

    def __init__(
        self,
        on_new_content: Callable[[Path, str, str], bool],
        on_session_end: Callable[[Path, str], None],
    ):
        self.config = get_config()
        self.handler = NativeSessionHandler(on_new_content, on_session_end)
        self.observer = Observer()
        self._running = False

    def start(self):
        """Start watching for file changes."""
        # Watch Claude projects directory
        if CLAUDE_PROJECTS_DIR.exists():
            self.observer.schedule(
                self.handler,
                str(CLAUDE_PROJECTS_DIR),
                recursive=True
            )

        # Watch Codex sessions directory
        if CODEX_SESSIONS_DIR.exists():
            self.observer.schedule(
                self.handler,
                str(CODEX_SESSIONS_DIR),
                recursive=True
            )

        self.observer.start()
        self._running = True

    def stop(self):
        """Stop watching for file changes."""
        self.observer.stop()
        self.observer.join()
        self._running = False

    def check_idle(self):
        """Check for idle sessions (call periodically)."""
        self.handler.check_idle_sessions()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def watched_projects(self) -> list[Path]:
        """Get list of projects being watched."""
        return list(set(state.project_path for state in self.handler.sessions.values()))

    @property
    def watch_paths(self) -> list[Path]:
        """Get the paths being watched."""
        paths = []
        if CLAUDE_PROJECTS_DIR.exists():
            paths.append(CLAUDE_PROJECTS_DIR)
        if CODEX_SESSIONS_DIR.exists():
            paths.append(CODEX_SESSIONS_DIR)
        return paths
