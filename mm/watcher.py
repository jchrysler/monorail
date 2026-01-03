"""File watcher for session logs."""

from __future__ import annotations

import time
import random
import string
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional
from dataclasses import dataclass, field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from .config import get_config


@dataclass
class SessionState:
    """State for a single project's session."""
    project_path: Path
    session_log: Path
    last_position: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None
    pending_content: str = ""


def generate_session_id() -> str:
    """Generate a session ID like 'a7b3f-20250102-1415'."""
    chars = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{chars}-{timestamp}"


class SessionLogHandler(FileSystemEventHandler):
    """Handle changes to .session.log files."""

    def __init__(
        self,
        on_new_content: Callable[[Path, str, str], None],
        on_session_end: Callable[[Path, str], None],
    ):
        super().__init__()
        self.sessions: dict[str, SessionState] = {}
        self.on_new_content = on_new_content
        self.on_session_end = on_session_end
        self.config = get_config()

    def on_modified(self, event):
        """Handle file modification events."""
        if not isinstance(event, FileModifiedEvent):
            return

        path = Path(event.src_path)
        if path.name != ".session.log" or "pool" not in path.parts:
            return

        self._process_log_change(path)

    def _process_log_change(self, log_path: Path):
        """Process changes to a session log file."""
        project_path = log_path.parent.parent  # pool/.session.log -> project/
        project_key = str(project_path)

        # Get or create session state
        if project_key not in self.sessions:
            self.sessions[project_key] = SessionState(
                project_path=project_path,
                session_log=log_path,
                session_id=generate_session_id(),
            )

        state = self.sessions[project_key]

        # Read new content
        try:
            with open(log_path, "r") as f:
                f.seek(state.last_position)
                new_content = f.read()
                state.last_position = f.tell()
        except Exception:
            return

        if not new_content:
            return

        state.pending_content += new_content
        state.last_activity = datetime.now()

        # Check for session end phrases
        for phrase in self.config.session_end_phrases:
            if phrase.lower() in new_content.lower():
                self.on_session_end(project_path, state.session_id)
                state.session_id = generate_session_id()
                state.pending_content = ""
                return

        # Check if we have enough content to extract
        if len(state.pending_content.encode()) >= self.config.min_new_bytes:
            self.on_new_content(
                project_path,
                state.session_id,
                state.pending_content,
            )
            state.pending_content = ""

    def check_idle_sessions(self):
        """Check for sessions that have been idle too long."""
        now = datetime.now()
        for key, state in self.sessions.items():
            if state.pending_content:
                idle_time = (now - state.last_activity).total_seconds()
                if idle_time >= self.config.idle_seconds:
                    self.on_new_content(
                        state.project_path,
                        state.session_id,
                        state.pending_content,
                    )
                    state.pending_content = ""


class Watcher:
    """Watches for session log changes across all projects."""

    def __init__(
        self,
        on_new_content: Callable[[Path, str, str], None],
        on_session_end: Callable[[Path, str], None],
    ):
        self.config = get_config()
        self.handler = SessionLogHandler(on_new_content, on_session_end)
        self.observer = Observer()
        self._running = False

    def start(self):
        """Start watching for file changes."""
        for watch_path in self.config.watch_paths:
            path = Path(watch_path).expanduser()
            if path.exists():
                self.observer.schedule(self.handler, str(path), recursive=True)

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
        return [state.project_path for state in self.handler.sessions.values()]
