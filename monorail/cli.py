"""Command-line interface for Monorail."""

from __future__ import annotations

import sys
import io
import os

os.environ["GRPC_VERBOSITY"] = "ERROR"

_original_stderr = sys.stderr
sys.stderr = io.StringIO()

try:
    import warnings
    warnings.filterwarnings("ignore")

    import click
    from pathlib import Path
    from rich.console import Console

    from .config import (
        MONORAIL_HOME,
        PROMPTS_DIR,
        ensure_monorail_home,
        get_config,
    )
finally:
    sys.stderr = _original_stderr

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="Monorail")
def main():
    """Monorail - Automatic session continuity for Claude Code and Codex."""
    pass


@main.command()
def init():
    """Initialize Monorail configuration."""
    ensure_monorail_home()
    _copy_default_prompts()

    config = get_config()
    if not config.gemini_api_key:
        api_key = click.prompt("Gemini API key", hide_input=True)
        config.gemini_api_key = api_key
        config.save()
        console.print("API key saved.")

    console.print(f"Created {MONORAIL_HOME}")
    console.print("Run 'monorail start' to begin watching.")


SESSION_CONTEXT_SECTION = """
## Session Context
At the start of each session, check context/monorail-notes.md for recent session history.
If it exists and is recent, start by briefly telling the user:
- What was being worked on
- Where it left off
- Any loose threads

Example: "I see you were working on the cart API and left off at the quantity update feature. There's a loose thread about a rounding bug. Want to continue there or start something new?"

If monorail-notes.md doesn't exist or is stale (>24 hours), skip this and start fresh.
"""


@main.command("init-project")
@click.option("--no-gitignore", is_flag=True, help="Don't add context/ to .gitignore (if you want to commit session notes)")
def init_project(no_gitignore: bool):
    """Initialize current directory for Monorail tracking."""
    cwd = Path.cwd()
    context_dir = cwd / "context"

    # Create context/ directory
    context_dir.mkdir(exist_ok=True)
    console.print("Created context/")

    from .notes import migrate_project_files
    migrate_project_files(cwd)

    # Add context/ to .gitignore (unless --no-gitignore)
    if not no_gitignore:
        gitignore = cwd / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if "context/" not in content and "context\n" not in content:
                with open(gitignore, "a") as f:
                    f.write("\n# Monorail\ncontext/\n")
                console.print("Updated .gitignore")
        else:
            gitignore.write_text("# Monorail\ncontext/\n")
            console.print("Created .gitignore")

    # Update or create CLAUDE.md
    claude_md = cwd / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if "## Session Context" not in content:
            with open(claude_md, "a") as f:
                f.write(SESSION_CONTEXT_SECTION)
            console.print("Updated CLAUDE.md")
    else:
        claude_md.write_text(SESSION_CONTEXT_SECTION.lstrip())
        console.print("Created CLAUDE.md")

    # Update agents.md if it exists
    agents_md = cwd / "agents.md"
    if agents_md.exists():
        content = agents_md.read_text()
        if "## Session Context" not in content:
            with open(agents_md, "a") as f:
                f.write(SESSION_CONTEXT_SECTION)
            console.print("Updated agents.md")

    # Create empty monorail-notes.md
    notes_file = context_dir / "monorail-notes.md"
    if not notes_file.exists():
        project_name = cwd.name
        notes_file.write_text(f"""# monorail notes
_Project: {project_name}_
_Last updated: never_

## Active Context

**Current task:** Not set
**Blockers:** None

## Session Log

""")
        console.print("Created context/monorail-notes.md")

    console.print("Project ready.")


@main.command()
def watch():
    """Start the live TUI dashboard."""
    ensure_monorail_home()
    _copy_default_prompts()

    config = get_config()
    if not config.gemini_api_key:
        console.print("No Gemini API key configured. Run 'monorail init' to add one.")

    from .tui import run_dashboard
    run_dashboard()


@main.command()
def start():
    """Start Monorail as a background daemon."""
    ensure_monorail_home()
    _copy_default_prompts()

    config = get_config()
    if not config.gemini_api_key:
        console.print("No Gemini API key configured. Run 'monorail init' to add one.")

    from .daemon import start_daemon
    start_daemon()


@main.command()
def stop():
    """Stop the background daemon."""
    from .daemon import stop_daemon
    stop_daemon()


@main.command()
@click.argument("project", required=False)
def status(project: str = None):
    """Show status (optionally for a specific project)."""
    from .daemon import show_status
    show_status(project)


@main.command()
@click.argument("message", nargs=-1, required=True)
def note(message: tuple):
    """[WIP] Add a note to the inbox."""
    from .inbox import add_note
    full_message = " ".join(message)
    add_note(full_message)
    console.print(f"Added: {full_message}")
    console.print("[dim]Note: Inbox routing not yet implemented[/dim]")


@main.command()
@click.argument("project")
def log(project: str):
    """Open project notes in $EDITOR."""
    import subprocess
    from .watcher import CLAUDE_PROJECTS_DIR, CODEX_SESSIONS_DIR, decode_claude_project_path, extract_project_from_codex_session

    def find_project_path(name: str) -> Path | None:
        if CLAUDE_PROJECTS_DIR.exists():
            for encoded_folder in CLAUDE_PROJECTS_DIR.iterdir():
                if not encoded_folder.is_dir():
                    continue
                project_path = decode_claude_project_path(encoded_folder.name)
                if project_path and project_path.name == name and project_path.exists():
                    return project_path

        if CODEX_SESSIONS_DIR.exists():
            for session_file in CODEX_SESSIONS_DIR.glob("**/*.jsonl"):
                project_path = extract_project_from_codex_session(session_file)
                if project_path and project_path.name == name and project_path.exists():
                    return project_path
        return None

    project_path = find_project_path(project)
    if project_path:
        from .notes import migrate_project_files
        migrate_project_files(project_path)
        notes_path = project_path / "context" / "monorail-notes.md"
        if notes_path.exists():
            editor = os.environ.get("EDITOR", "vim")
            subprocess.run([editor, str(notes_path)])
            return
        else:
            console.print(f"No notes file. Run 'monorail init-project' in {project_path}")
            return

    console.print(f"Project not found: {project}")


@main.command()
@click.argument("project")
def archive(project: str):
    """[WIP] Archive old sessions for a project."""
    from .notes import archive_sessions
    if archive_sessions(project):
        console.print(f"[yellow]Archive not yet implemented[/yellow] for {project}")
    else:
        console.print(f"[red]Project not found:[/red] {project}")


def _copy_default_prompts():
    """Copy default prompt templates to ~/.monorail/prompts/."""
    package_prompts = Path(__file__).parent.parent / "prompts"

    for prompt_file in ["extract.txt", "summarize.txt", "inbox.txt"]:
        src = package_prompts / prompt_file
        dst = PROMPTS_DIR / prompt_file

        if src.exists() and not dst.exists():
            dst.write_text(src.read_text())
        elif not dst.exists():
            dst.write_text(_get_default_prompt(prompt_file))


def _get_default_prompt(filename: str) -> str:
    """Get default prompt content."""
    prompts = {
        "extract.txt": """Extract structured notes from this coding session log.

Project: {project}
Tool: {tool}

<session_log>
{log_content}
</session_log>

<previous_context>
{previous_context}
</previous_context>

Extract:
1. STATED_GOAL: What was the developer trying to accomplish?
2. WHAT_HAPPENED: Bullet points of what occurred.
3. LEFT_OFF_AT: Where did the session end?
4. LOOSE_THREADS: Things mentioned but not completed.
5. KEY_ARTIFACTS: Files created or modified.
6. SESSION_COMPLETE: true/false

Format:
STATED_GOAL: [goal]

WHAT_HAPPENED:
- [item]

LEFT_OFF_AT: [state]

LOOSE_THREADS:
- [item]

KEY_ARTIFACTS:
- [path]: [description]

SESSION_COMPLETE: [true/false]
""",
        "summarize.txt": """Summarize these session logs for archival.

<sessions>
{sessions}
</sessions>

Keep under {max_tokens} tokens. Format:

**Summary:** [1-2 sentences]

**Completed:**
- [item]

**Key decisions:**
- [decision]

**Carried forward:**
- [unresolved item]
""",
        "inbox.txt": """Process inbox notes.

<inbox>
{inbox_content}
</inbox>

<projects>
{projects_summary}
</projects>

For each note:
NOTE: "[note]"
APPLIES_TO: [project or "global"]
TYPE: [priority/context/completion/instruction/observation]
ACTION: [what to do]
""",
    }
    return prompts.get(filename, "")


if __name__ == "__main__":
    main()
