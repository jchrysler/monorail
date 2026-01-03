"""Command-line interface for Music Man."""

from __future__ import annotations

import click
from pathlib import Path
from rich.console import Console

from .config import (
    Config,
    MM_HOME,
    PROMPTS_DIR,
    ensure_mm_home,
    get_config,
)

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="Music Man")
def main():
    """Music Man - Session continuity for AI coding tools.

    Ya got trouble, right here in River City! And that starts with T
    and that rhymes with P and that stands for Pool!
    """
    pass


@main.command()
def init():
    """Initialize Music Man configuration."""
    console.print("[bold blue]Music Man[/bold blue] - Initializing...\n")

    # Create directory structure
    ensure_mm_home()
    console.print(f"  [green]Created[/green] {MM_HOME}")

    # Copy default prompts
    _copy_default_prompts()
    console.print(f"  [green]Created[/green] {PROMPTS_DIR}")

    # Prompt for API key
    config = get_config()
    if not config.gemini_api_key:
        api_key = click.prompt("\nEnter your Gemini API key", hide_input=True)
        config.gemini_api_key = api_key
        config.save()
        console.print("  [green]Saved[/green] API key to config.yaml")
    else:
        console.print("  [yellow]Skipped[/yellow] API key (already configured)")

    # Print shell aliases
    console.print("\n[bold]Add these to your shell config (.zshrc / .bashrc):[/bold]\n")
    console.print("""[dim]# Music Man session logging - logs go to pool/
alias cc='mkdir -p pool && claude 2>&1 | tee -a pool/.session.log'
alias cx='mkdir -p pool && codex 2>&1 | tee -a pool/.session.log'

# Quick mm commands
alias mms='mm status'
alias mmn='mm note'

# Initialize a project for mm tracking
mm-init-project() {
  mkdir -p pool
  echo "pool/" >> .gitignore
  echo "Project initialized for Music Man tracking."
}[/dim]""")

    console.print("\n[green]Music Man initialized![/green] Run [bold]mm watch[/bold] to start the dashboard.")


@main.command()
def watch():
    """Start the live TUI dashboard (primary mode)."""
    from .tui import run_dashboard
    run_dashboard()


@main.command()
def start():
    """Start Music Man as a background daemon."""
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
    """Add a note to the inbox."""
    from .inbox import add_note
    full_message = " ".join(message)
    add_note(full_message)
    console.print(f"[green]Added to inbox:[/green] {full_message}")


@main.command()
@click.argument("project")
def log(project: str):
    """Open project notes in $EDITOR."""
    import os
    import subprocess

    # Find the project's mm-notes.md
    config = get_config()
    for watch_path in config.watch_paths:
        notes_path = Path(watch_path) / project / "pool" / "mm-notes.md"
        if notes_path.exists():
            editor = os.environ.get("EDITOR", "vim")
            subprocess.run([editor, str(notes_path)])
            return

    console.print(f"[red]Project not found:[/red] {project}")


@main.command()
@click.argument("project")
def archive(project: str):
    """Archive old sessions for a project."""
    from .notes import archive_sessions
    archive_sessions(project)
    console.print(f"[green]Archived old sessions for:[/green] {project}")


def _copy_default_prompts():
    """Copy default prompt templates to ~/.mm/prompts/."""
    # Get the prompts from the package
    package_prompts = Path(__file__).parent.parent / "prompts"

    for prompt_file in ["extract.txt", "summarize.txt", "inbox.txt"]:
        src = package_prompts / prompt_file
        dst = PROMPTS_DIR / prompt_file

        if src.exists() and not dst.exists():
            dst.write_text(src.read_text())
        elif not dst.exists():
            # Write default content if package prompts don't exist
            dst.write_text(_get_default_prompt(prompt_file))


def _get_default_prompt(filename: str) -> str:
    """Get default prompt content."""
    prompts = {
        "extract.txt": """You are a note-taking assistant that extracts structured information from coding session logs.

Given the following terminal session output from a developer using {tool} in the project "{project}":

<session_log>
{log_content}
</session_log>

Previous context (if any):
<previous_context>
{previous_context}
</previous_context>

Extract the following information. Be detailed and specific. Include file paths, function names, and concrete details.

1. STATED_GOAL: What was the developer trying to accomplish?
2. WHAT_HAPPENED: Detailed bullet points of what occurred.
3. LEFT_OFF_AT: Where did the session end? What was the last action?
4. LOOSE_THREADS: Things mentioned but not completed.
5. KEY_ARTIFACTS: Files created or modified.
6. SESSION_COMPLETE: Is this session finished (true) or likely to continue (false)?

Respond in this exact format:

STATED_GOAL: [goal]

WHAT_HAPPENED:
- [item]
...

LEFT_OFF_AT: [specific state]

LOOSE_THREADS:
- [item]
...

KEY_ARTIFACTS:
- [path]: [description]
...

SESSION_COMPLETE: [true/false]
""",
        "summarize.txt": """You are summarizing old coding session logs for archival.

Given these detailed session logs:

<sessions>
{sessions}
</sessions>

Create a condensed summary that preserves:
1. Key decisions made
2. Major features completed
3. Important context for future sessions
4. Unresolved issues

Keep it under {max_tokens} tokens.

Format:

**Summary:** [1-2 sentence overview]

**Completed:**
- [major item]
...

**Key decisions:**
- [decision]
...

**Carried forward:**
- [unresolved item if any]
...
""",
        "inbox.txt": """You are processing notes from a developer's inbox for Music Man.

Current inbox notes:
<inbox>
{inbox_content}
</inbox>

Current project states:
<projects>
{projects_summary}
</projects>

For each inbox note, determine:
1. Which project(s) it applies to (or "global")
2. Type: priority, context, completion, instruction, or observation
3. How to incorporate into project notes

Respond:

NOTE: "[original note]"
APPLIES_TO: [project name or "global"]
TYPE: [type]
ACTION: [what to do]

Repeat for each note.
""",
    }
    return prompts.get(filename, "")


if __name__ == "__main__":
    main()
