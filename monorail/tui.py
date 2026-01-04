"""TUI Dashboard for Monorail using Textual."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import threading

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Log, Static
from textual.containers import Container, Vertical

from .config import get_config
from .watcher import Watcher, CLAUDE_PROJECTS_DIR, CODEX_SESSIONS_DIR
from .extractor import Extractor, ExtractionResult
from .notes import update_notes


# Vibe emoji mapping
VIBE_EMOJI = {
    "smooth": "🟢",
    "just-started": "🔵",
    "exploring": "🟣",
    "stuck": "🟡",
    "wrapping-up": "🟠",
}


@dataclass
class SessionDisplay:
    """Display state for a session."""
    project_name: str
    session_id: str
    status: str = ""
    vibe: str = ""
    stated_goal: str = ""
    last_update: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    loose_threads: list = field(default_factory=list)
    left_off_at: str = ""


class ContextSection(Static):
    """A section showing contextual session info."""

    DEFAULT_CSS = """
    ContextSection {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }
    """


class MonorailApp(App):
    """Monorail TUI Dashboard."""

    CSS = """
    Screen {
        background: #000000;
        color: #F0E68C;
    }

    #context-panel {
        height: 1fr;
        border: heavy #D2B48C;
        padding: 1;
    }

    #event-log {
        height: 10;
        border: heavy #8B7355;
    }

    .section-header {
        text-style: bold;
        color: #FFD700;
        margin-bottom: 1;
    }

    .session-entry {
        margin-left: 2;
        margin-bottom: 1;
    }

    .attention-item {
        color: #FFA500;
        margin-left: 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self):
        self.watcher: Optional[Watcher] = None
        self.log_widget: Optional[Log] = None
        self.context_widget: Optional[Static] = None
        self.config = get_config()
        self.extractor = Extractor()
        self._shutting_down = False
        self._thread_id = threading.get_ident()

        # Session display state
        self.active_sessions: dict[str, SessionDisplay] = {}
        self.finished_sessions: list[SessionDisplay] = []
        self.attention_items: list[tuple[str, str]] = []  # (project, issue)

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Static(id="context-panel"),
            id="main-container"
        )
        yield Log(id="event-log")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Monorail"
        self.log_widget = self.query_one("#event-log", Log)
        self.context_widget = self.query_one("#context-panel", Static)
        self.start_watcher()
        self.set_interval(self.config.poll_interval, self._check_idle)
        self.set_interval(5, self._refresh_display)  # Refresh display every 5s
        self._refresh_display()

    def _log(self, msg: str):
        """Write to event log (must be called from main thread)."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_widget.write_line(f"{ts}  {msg}")

    def _safe_log(self, msg: str):
        """Write to event log from any thread."""
        if threading.get_ident() == self._thread_id:
            self._log(msg)
        else:
            self.call_from_thread(self._log, msg)

    def _safe_refresh(self):
        """Refresh display from any thread."""
        if threading.get_ident() == self._thread_id:
            self._refresh_display()
        else:
            self.call_from_thread(self._refresh_display)

    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as 'X ago' string."""
        delta = datetime.now() - dt
        if delta.total_seconds() < 60:
            return "just now"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() / 60)
            return f"{mins}m ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}h ago"
        else:
            days = int(delta.total_seconds() / 86400)
            return f"{days}d ago"

    def _refresh_display(self):
        """Refresh the contextual display."""
        lines = []

        # RIGHT NOW section
        lines.append("[bold #FFD700]RIGHT NOW[/]")
        lines.append("─" * 40)

        active = [s for s in self.active_sessions.values() if s.is_active]
        if active:
            for session in active:
                vibe_emoji = VIBE_EMOJI.get(session.vibe, "⚪")
                lines.append(f"{vibe_emoji} [bold]{session.project_name}[/] ({session.session_id[:8]})")
                if session.status:
                    lines.append(f"   {session.status}")
                elif session.stated_goal:
                    lines.append(f"   Working on: {session.stated_goal[:60]}")
                lines.append("")
        else:
            lines.append("   [dim]No active sessions[/]")
            lines.append("")

        # RECENTLY FINISHED section
        lines.append("[bold #FFD700]RECENTLY FINISHED[/]")
        lines.append("─" * 40)

        recent = self.finished_sessions[:3]  # Show last 3
        if recent:
            for session in recent:
                time_ago = self._format_time_ago(session.last_update)
                lines.append(f"[dim]{session.project_name}[/] ({session.session_id[:8]}) - {time_ago}")
                if session.left_off_at:
                    lines.append(f"   Left off: {session.left_off_at[:50]}")
                lines.append("")
        else:
            lines.append("   [dim]None yet[/]")
            lines.append("")

        # NEEDS ATTENTION section
        lines.append("[bold #FFA500]NEEDS ATTENTION[/]")
        lines.append("─" * 40)

        # Collect loose threads from all sessions
        attention = []
        for session in list(self.active_sessions.values()) + self.finished_sessions[:5]:
            for thread in session.loose_threads[:2]:  # Max 2 per session
                attention.append((session.project_name, thread))

        if attention:
            for project, issue in attention[:5]:  # Show max 5
                lines.append(f"   • [bold]{project}[/]: {issue[:50]}")
        else:
            lines.append("   [dim]All clear[/]")

        self.context_widget.update("\n".join(lines))

    def _update_session(self, project_path: Path, session_id: str, result: ExtractionResult):
        """Update session display state from extraction result."""
        key = f"{project_path.name}:{session_id}"

        session = self.active_sessions.get(key, SessionDisplay(
            project_name=project_path.name,
            session_id=session_id,
        ))

        session.status = result.status
        session.vibe = result.vibe
        session.stated_goal = result.stated_goal
        session.loose_threads = result.loose_threads or []
        session.left_off_at = result.left_off_at
        session.last_update = datetime.now()
        session.is_active = not result.session_complete

        if result.session_complete:
            # Move to finished
            if key in self.active_sessions:
                del self.active_sessions[key]
            self.finished_sessions.insert(0, session)
            # Keep only last 10 finished
            self.finished_sessions = self.finished_sessions[:10]
        else:
            self.active_sessions[key] = session

    def start_watcher(self):
        def on_new_content(project_path: Path, session_id: str, content: str):
            size_kb = len(content) / 1024
            self._safe_log(f"📝 {project_path.name}: New content ({size_kb:.1f}KB)")
            self._safe_log(f"🤖 {project_path.name}: Extracting...")

            result = self.extractor.extract(log_content=content, project=project_path.name)
            if result:
                update_notes(project_path, session_id, result)
                self._update_session(project_path, session_id, result)

                # Show status in log if available
                if result.status:
                    self._safe_log(f"✅ {project_path.name}: {result.status[:50]}")
                else:
                    self._safe_log(f"✅ {project_path.name}: Notes updated")

                self._safe_refresh()
                return True
            else:
                self._safe_log(f"⚠️  {project_path.name}: Skipped")
                return False

        def on_session_end(project_path: Path, session_id: str):
            self._safe_log(f"🏁 {project_path.name}: Session ended")

            # Mark session as finished
            key = f"{project_path.name}:{session_id}"
            if key in self.active_sessions:
                session = self.active_sessions.pop(key)
                session.is_active = False
                self.finished_sessions.insert(0, session)
                self.finished_sessions = self.finished_sessions[:10]
                self._safe_refresh()

        self.watcher = Watcher(on_new_content, on_session_end)
        self.watcher.start()

        targets = []
        if CLAUDE_PROJECTS_DIR.exists():
            targets.append("Claude")
        if CODEX_SESSIONS_DIR.exists():
            targets.append("Codex")
        self._log(f"🎵 Watching {' & '.join(targets) or 'nothing'}")

    def _check_idle(self):
        if self.watcher and not self._shutting_down:
            self.watcher.check_idle()

            # Mark sessions as inactive if idle too long (5 minutes)
            now = datetime.now()
            for key, session in list(self.active_sessions.items()):
                if (now - session.last_update).total_seconds() > 300:
                    session.is_active = False

    def action_refresh(self):
        self._log("🔄 Refresh")
        self._refresh_display()

    def on_unmount(self) -> None:
        self._shutting_down = True
        if self.watcher:
            self.watcher.stop()


def run_dashboard():
    MonorailApp().run()
