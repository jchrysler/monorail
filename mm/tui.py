"""TUI Dashboard for Music Man using Textual."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, DataTable, Input, Label
from textual.reactive import reactive
from rich.text import Text

from .config import get_config
from .watcher import Watcher
from .extractor import Extractor
from .notes import update_notes, get_current_task, get_last_session_time, get_loose_threads
from .inbox import count_pending


class ActivityLog(Static):
    """Live activity log widget."""

    def __init__(self):
        super().__init__()
        self.entries: list[tuple[str, str, str, str]] = []
        self.max_entries = 20

    def add_entry(self, emoji: str, project: str, message: str):
        """Add an entry to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.entries.insert(0, (timestamp, emoji, project, message))
        self.entries = self.entries[:self.max_entries]
        self.refresh_log()

    def refresh_log(self):
        """Refresh the displayed log."""
        lines = []
        for ts, emoji, project, msg in self.entries:
            lines.append(f"  {ts}  {emoji}  {project:<20} {msg}")
        self.update("\n".join(lines) if lines else "  [dim]No activity yet[/dim]")


class LooseThreads(Static):
    """Loose threads display widget."""

    def __init__(self):
        super().__init__()
        self.threads: list[tuple[str, str]] = []

    def set_threads(self, threads: list[tuple[str, str]]):
        """Set the loose threads to display."""
        self.threads = threads[:5]
        self.refresh_display()

    def refresh_display(self):
        """Refresh the displayed threads."""
        if not self.threads:
            self.update("  [dim]No loose threads[/dim]")
            return

        lines = []
        for project, thread in self.threads:
            lines.append(f"  [yellow]•[/yellow] {project}: {thread[:60]}")
        self.update("\n".join(lines))


class MusicManApp(App):
    """Music Man TUI Dashboard."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        layout: grid;
        grid-size: 1;
        grid-rows: auto 1fr auto;
        height: 100%;
    }

    #projects-section {
        height: auto;
        max-height: 40%;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }

    #activity-section {
        height: 1fr;
        border: solid $secondary;
        margin: 1;
        padding: 1;
    }

    #threads-section {
        height: auto;
        max-height: 25%;
        border: solid $warning;
        margin: 1;
        padding: 1;
    }

    .section-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #inbox-count {
        dock: right;
        width: auto;
        padding-right: 2;
    }

    DataTable {
        height: auto;
        max-height: 100%;
    }

    #note-input {
        display: none;
        dock: bottom;
        height: 3;
        margin: 1;
    }

    #note-input.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_note", "New Note"),
        Binding("r", "refresh", "Refresh"),
        Binding("?", "help", "Help"),
    ]

    inbox_count = reactive(0)

    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.extractor = Extractor()
        self.watcher: Optional[Watcher] = None
        self.activity_log: Optional[ActivityLog] = None
        self.loose_threads_widget: Optional[LooseThreads] = None
        self.projects_table: Optional[DataTable] = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Projects section
            with Vertical(id="projects-section"):
                with Horizontal():
                    yield Label("PROJECTS", classes="section-title")
                    yield Label(f"Inbox: {self.inbox_count} notes", id="inbox-count")
                yield DataTable(id="projects-table")

            # Activity section
            with Vertical(id="activity-section"):
                yield Label("LIVE ACTIVITY", classes="section-title")
                yield ScrollableContainer(ActivityLog())

            # Loose threads section
            with Vertical(id="threads-section"):
                yield Label("LOOSE THREADS (recent)", classes="section-title")
                yield LooseThreads()

        yield Input(placeholder="Enter note...", id="note-input")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the app when mounted."""
        self.title = "Music Man"
        self.sub_title = "Ya got trouble!"

        # Get widget references
        self.activity_log = self.query_one(ActivityLog)
        self.loose_threads_widget = self.query_one(LooseThreads)
        self.projects_table = self.query_one("#projects-table", DataTable)

        # Set up projects table
        self.projects_table.add_columns("", "Project", "Current Task", "Last Active", "Tool")
        self.projects_table.cursor_type = "row"

        # Initial data load
        self.refresh_data()

        # Start the watcher
        self.start_watcher()

        # Set up periodic refresh
        self.set_interval(5, self.refresh_data)
        self.set_interval(self.config.poll_interval, self.check_idle)

    def start_watcher(self):
        """Start the file watcher."""
        def on_new_content(project_path: Path, session_id: str, content: str):
            """Handle new session content."""
            size_kb = len(content) / 1024
            self.call_from_thread(
                self.activity_log.add_entry,
                "📝",
                project_path.name,
                f"+{size_kb:.1f}kb new content",
            )

            # Extract and update
            self.call_from_thread(
                self.activity_log.add_entry,
                "🤖",
                project_path.name,
                "Extracting via Gemini...",
            )

            result = self.extractor.extract(
                log_content=content,
                project=project_path.name,
            )

            if result:
                update_notes(project_path, session_id, result)
                self.call_from_thread(
                    self.activity_log.add_entry,
                    "✅",
                    project_path.name,
                    "Updated mm-notes.md",
                )
                self.call_from_thread(self.refresh_data)
            else:
                self.call_from_thread(
                    self.activity_log.add_entry,
                    "⚠️",
                    project_path.name,
                    "Extraction skipped (rate limit)",
                )

        def on_session_end(project_path: Path, session_id: str):
            """Handle session end."""
            self.call_from_thread(
                self.activity_log.add_entry,
                "🏁",
                project_path.name,
                f"Session {session_id[:5]} ended",
            )

        self.watcher = Watcher(on_new_content, on_session_end)
        self.watcher.start()

        # Log startup
        self.activity_log.add_entry(
            "🎵",
            "Music Man",
            f"Watching {len(self.config.watch_paths)} paths",
        )

    def check_idle(self):
        """Check for idle sessions."""
        if self.watcher:
            self.watcher.check_idle()

    def refresh_data(self):
        """Refresh all displayed data."""
        self.inbox_count = count_pending()
        self.query_one("#inbox-count", Label).update(f"Inbox: {self.inbox_count} notes")

        # Refresh projects table
        self._refresh_projects_table()

        # Refresh loose threads
        self._refresh_loose_threads()

    def _refresh_projects_table(self):
        """Refresh the projects data table."""
        self.projects_table.clear()

        projects = self._find_projects()
        for p in projects:
            priority = "⚑" if p.get("priority") else " "
            last_active = self._format_time_ago(p["last_active"])
            task = p["current_task"]
            if len(task) > 35:
                task = task[:32] + "..."

            self.projects_table.add_row(
                priority,
                p["name"],
                task,
                last_active,
                p.get("tool", "claude"),
            )

    def _refresh_loose_threads(self):
        """Refresh the loose threads display."""
        all_threads = []

        for watch_path in self.config.watch_paths:
            path = Path(watch_path).expanduser()
            if not path.exists():
                continue

            for session_log in path.rglob("pool/.session.log"):
                project_path = session_log.parent.parent
                threads = get_loose_threads(project_path, limit=3)
                for thread in threads:
                    all_threads.append((project_path.name, thread))

        self.loose_threads_widget.set_threads(all_threads[:5])

    def _find_projects(self) -> list[dict]:
        """Find all projects with pool/.session.log files."""
        projects = []

        for watch_path in self.config.watch_paths:
            path = Path(watch_path).expanduser()
            if not path.exists():
                continue

            for session_log in path.rglob("pool/.session.log"):
                project_path = session_log.parent.parent
                projects.append({
                    "name": project_path.name,
                    "path": project_path,
                    "current_task": get_current_task(project_path) or "-",
                    "last_active": get_last_session_time(project_path),
                    "tool": "claude",  # TODO: detect from log content
                })

        # Sort by last active
        projects.sort(key=lambda p: p["last_active"] or datetime.min, reverse=True)
        return projects

    def _format_time_ago(self, dt: datetime) -> str:
        """Format a datetime as 'X ago' string."""
        if not dt:
            return "never"

        delta = datetime.now() - dt
        seconds = delta.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins} min ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"

    def action_new_note(self):
        """Show the note input."""
        note_input = self.query_one("#note-input", Input)
        note_input.add_class("visible")
        note_input.focus()

    def action_refresh(self):
        """Force refresh all data."""
        self.activity_log.add_entry("🔄", "Music Man", "Manual refresh")
        self.refresh_data()

    def action_help(self):
        """Show help."""
        self.activity_log.add_entry(
            "❓",
            "Help",
            "q=quit n=note r=refresh ?=help",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle note submission."""
        if event.input.id == "note-input":
            from .inbox import add_note
            if event.value.strip():
                add_note(event.value.strip())
                self.activity_log.add_entry("📥", "Inbox", f"Added: {event.value[:30]}...")
                self.inbox_count = count_pending()

            event.input.value = ""
            event.input.remove_class("visible")

    def on_unmount(self) -> None:
        """Clean up when app closes."""
        if self.watcher:
            self.watcher.stop()


def run_dashboard():
    """Run the Music Man TUI dashboard."""
    app = MusicManApp()
    app.run()
