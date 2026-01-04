"""Daemon process for Monorail."""

from __future__ import annotations

import os
import sys
import io
import time
import signal
from pathlib import Path
from datetime import datetime

# Suppress stderr during imports
_stderr = sys.stderr
sys.stderr = io.StringIO()
try:
    from rich.console import Console
    from .config import DAEMON_PID, DAEMON_LOG, get_config
    from .watcher import Watcher
    from .extractor import Extractor
    from .notes import update_notes, get_current_task, get_last_session_time
finally:
    sys.stderr = _stderr

console = Console()


def start_daemon():
    """Start Monorail as a background daemon."""
    if DAEMON_PID.exists():
        pid = int(DAEMON_PID.read_text().strip())
        try:
            os.kill(pid, 0)
            console.print(f"[yellow]Daemon already running[/yellow] (PID {pid})")
            return
        except OSError:
            # Process doesn't exist, clean up stale PID file
            DAEMON_PID.unlink()

    # Fork to background
    if os.fork() > 0:
        console.print(f"[green]Started daemon[/green] - logs at {DAEMON_LOG}")
        return

    # Decouple from parent
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)

    # Write PID file
    DAEMON_PID.write_text(str(os.getpid()))

    # Redirect output to log
    sys.stdout = open(DAEMON_LOG, "a")
    sys.stderr = sys.stdout

    # Run the daemon loop
    _run_daemon_loop()


def stop_daemon():
    """Stop the background daemon."""
    if not DAEMON_PID.exists():
        console.print("[yellow]No daemon running[/yellow]")
        return

    pid = int(DAEMON_PID.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        DAEMON_PID.unlink()
        console.print(f"[green]Stopped daemon[/green] (PID {pid})")
    except OSError:
        console.print(f"[red]Daemon not running[/red] (stale PID {pid})")
        DAEMON_PID.unlink()


def show_status(project: str = None):
    """Show daemon and project status."""
    config = get_config()

    # Daemon status
    if DAEMON_PID.exists():
        pid = int(DAEMON_PID.read_text().strip())
        try:
            os.kill(pid, 0)
            console.print(f"[green]Daemon running[/green] (PID {pid})")
        except OSError:
            console.print("[yellow]Daemon not running[/yellow] (stale PID file)")
    else:
        console.print("[dim]Daemon not running[/dim]")

    console.print()

    # Find projects
    projects = _find_projects(config)

    if project:
        # Show specific project
        for p in projects:
            if p["name"] == project:
                _show_project_detail(p)
                return
        console.print(f"[red]Project not found:[/red] {project}")
    else:
        # Show all projects
        if not projects:
            console.print("[dim]No projects found in Claude Code or Codex sessions[/dim]")
            return

        console.print("[bold]Projects:[/bold]")
        for p in projects:
            last_active = _format_time_ago(p["last_active"]) if p["last_active"] else "never"
            task = p["current_task"][:40] + "..." if len(p["current_task"]) > 40 else p["current_task"]
            console.print(f"  {p['name']:<25} {task:<45} {last_active}")


def _find_projects(config) -> list[dict]:
    """Find all projects from Claude Code and Codex native session directories."""
    from .watcher import CLAUDE_PROJECTS_DIR, CODEX_SESSIONS_DIR, decode_claude_project_path, extract_project_from_codex_session

    projects = {}  # Use dict to dedupe by project path

    # Scan Claude projects directory
    if CLAUDE_PROJECTS_DIR.exists():
        try:
            for encoded_folder in CLAUDE_PROJECTS_DIR.iterdir():
                if not encoded_folder.is_dir():
                    continue
                project_path = decode_claude_project_path(encoded_folder.name)
                if not project_path.exists():
                    continue

                session_files = list(encoded_folder.glob("*.jsonl"))
                if not session_files:
                    continue

                last_modified = max(f.stat().st_mtime for f in session_files)
                last_active = datetime.fromtimestamp(last_modified)

                project_key = str(project_path)
                if project_key not in projects or projects[project_key]["last_active"] < last_active:
                    projects[project_key] = {
                        "name": project_path.name,
                        "path": project_path,
                        "current_task": get_current_task(project_path) or "-",
                        "last_active": last_active,
                    }
        except (PermissionError, OSError):
            pass

    # Scan Codex sessions directory
    if CODEX_SESSIONS_DIR.exists():
        try:
            for session_file in CODEX_SESSIONS_DIR.glob("**/*.jsonl"):
                project_path = extract_project_from_codex_session(session_file)
                if not project_path or not project_path.exists():
                    continue

                last_active = datetime.fromtimestamp(session_file.stat().st_mtime)
                project_key = str(project_path)

                if project_key not in projects or projects[project_key]["last_active"] < last_active:
                    projects[project_key] = {
                        "name": project_path.name,
                        "path": project_path,
                        "current_task": get_current_task(project_path) or "-",
                        "last_active": last_active,
                    }
        except (PermissionError, OSError):
            pass

    # Sort by last active
    project_list = list(projects.values())
    project_list.sort(key=lambda p: p["last_active"] or datetime.min, reverse=True)
    return project_list


def _show_project_detail(project: dict):
    """Show detailed status for a project."""
    from .notes import get_loose_threads

    console.print(f"[bold]{project['name']}[/bold]")
    console.print(f"  Path: {project['path']}")
    console.print(f"  Current task: {project['current_task']}")
    console.print(f"  Last active: {_format_time_ago(project['last_active'])}")

    threads = get_loose_threads(project["path"])
    if threads:
        console.print("\n  [bold]Loose threads:[/bold]")
        for thread in threads:
            console.print(f"    - {thread}")


def _format_time_ago(dt: datetime) -> str:
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
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"


def _run_daemon_loop():
    """Main daemon loop."""
    config = get_config()
    extractor = Extractor()

    def on_new_content(project_path: Path, session_id: str, content: str):
        """Handle new session content."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] New content in {project_path.name} ({len(content)} bytes)")

        result = extractor.extract(
            log_content=content,
            project=project_path.name,
        )

        if result:
            update_notes(project_path, session_id, result)
            print(f"[{timestamp}] Updated {project_path.name}/context/monorail-notes.md")
            return True
        return False

    def on_session_end(project_path: Path, session_id: str):
        """Handle session end."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Session ended in {project_path.name}")

    watcher = Watcher(on_new_content, on_session_end)

    def handle_shutdown(signum, frame):
        print("\nShutting down...")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    from .watcher import CLAUDE_PROJECTS_DIR, CODEX_SESSIONS_DIR
    watch_targets = []
    if CLAUDE_PROJECTS_DIR.exists():
        watch_targets.append("Claude Code")
    if CODEX_SESSIONS_DIR.exists():
        watch_targets.append("Codex")
    print(f"Monorail daemon started - watching {' & '.join(watch_targets) if watch_targets else 'nothing'}")
    watcher.start()

    while True:
        time.sleep(config.poll_interval)
        watcher.check_idle()
