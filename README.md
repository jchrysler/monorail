# Monorail

**Autosave for your coding sessions.** Keeps all your work on one track.

When you start a new session, Claude knows what happened in your last one—and what changed while you were away.

## Prerequisites

1. **Python 3.9+**
2. **Gemini API key** — Get one free at [Google AI Studio](https://aistudio.google.com/apikey)

## Quick Start

```bash
# Install
pip install monorail-ai

# Run from anywhere - it finds your projects automatically
monorail init
```

The setup wizard will:
1. Prompt for your Gemini API key
2. Discover your Claude Code and Codex projects (from `~/.claude/projects` and `~/.codex/sessions`)
3. Let you select which ones to track
4. Set up each project with `CLAUDE.md` instructions
5. Start the daemon

Run it from any directory—it doesn't matter where.

Or with [pipx](https://pipx.pypa.io/) (recommended for CLI tools):

```bash
pipx install monorail-ai && monorail init
```

<details>
<summary>Install from source</summary>

```bash
git clone https://github.com/jchrysler/monorail.git
cd monorail
pip install -e .
monorail init
```
</details>

## Verify It Works

```bash
# Check daemon is running
monorail status

# Or watch live extractions
monorail watch
```

Start a Claude session, do some work, then check `monorail status` again. You'll see your project listed with the current task.

## Zero Setup Required

Monorail auto-configures each project on first extraction:

1. Creates `context/monorail-notes.md` with your session history
2. Adds a session context block to `CLAUDE.md` (or creates it):

```markdown
<!-- monorail:start - auto-added, safe to modify or remove -->
## Session Context
Read context/monorail-notes.md at session start for continuity.
<!-- monorail:end -->
```

No per-project init needed. Just start working.

**Optional:** Run `monorail init-project` to set up a project manually, add `context/` to `.gitignore`, etc. Use `--no-gitignore` if you want to commit your session notes.

## How It Works

```
Your Claude/Codex sessions
         │
         ▼
~/.claude/projects/*.jsonl   ← Native session logs (already exist)
         │
         ▼
    Monorail daemon          ← Watches for changes
         │
         ▼
    Gemini Flash Lite        ← Extracts structured notes (cheap tokens)
         │
         ▼
project/context/monorail-notes.md   ← Written per-project
         │
         ▼
New session reads notes      ← Claude gives you a quick recap
```

## What Gets Extracted

Monorail uses Gemini to parse your sessions into:

- **Stated Goal** — What you were trying to accomplish
- **What Happened** — Bullet points of actions taken
- **Left Off At** — Where the session ended
- **Loose Threads** — Things mentioned but not completed
- **Key Artifacts** — Files created or modified

Example output in `context/monorail-notes.md`:

```markdown
# monorail notes
_Project: my-app_
_Last updated: 2025-01-03 14:32_
_Git commit: abc123_

## Active Context

**⚠️ 2 commits since last session:**
- def456 Fix login validation bug
- 789abc Update dependencies

**Current task:** Implementing user authentication

## Session Log
### abc123 | 2025-01-03 14:30 | claude
**Stated goal:** Add login form to the app
**What happened:**
- Created LoginForm component
- Added form validation
- Integrated with auth API
**Left off at:** Testing error states
**Loose threads:** Need to add "forgot password" link
---
```

The git tracking means Claude knows when commits happened between sessions—so it won't assume the codebase is exactly how it left it.

## Context Size

Each session adds ~20-40 lines to the notes. Monorail automatically keeps context lean:

- **Auto-archival**: When notes exceed 400 lines or 15 sessions, older sessions are summarized
- **Gemini-powered**: Old sessions get compressed into a "Historical Summary" section
- **Recent sessions preserved**: The last 10 sessions stay intact for immediate context

You can also trigger archival manually:

```bash
monorail archive my-project
```

## Commands

| Command | Description |
|---------|-------------|
| `monorail init` | Interactive setup: API key, project selection, and daemon start |
| `monorail init-project` | Initialize current directory only (`--no-gitignore` to commit notes) |
| `monorail start` | Start background daemon |
| `monorail stop` | Stop daemon |
| `monorail status` | Show daemon and project status |
| `monorail watch` | Live TUI dashboard |
| `monorail log <project>` | Open project notes in $EDITOR |
| `monorail archive <project>` | Manually trigger session archival |

## Configuration

Config lives at `~/.monorail/config.yaml`. For security, restrict permissions on this file since it contains your API key:

```bash
chmod 600 ~/.monorail/config.yaml
```

```yaml
gemini_api_key: "your-key-here"
gemini_model: "gemini-2.5-flash-lite"
poll_interval_seconds: 30
auto_modify_claude_md: true   # Auto-add session context to CLAUDE.md

extract_on:
  min_new_bytes: 500    # Extract after this much new content
  idle_seconds: 60      # Or after 1 minute idle (backup)
```

## Why Monorail?

| Without | With Monorail |
|---------|---------------|
| Manual handoff before clearing | Automatic, always running |
| Burns Claude tokens on summaries | Uses cheap Gemini tokens |
| Single session memory | Multi-session awareness |
| Context lost on /clear | Extracted instantly on /clear |
| Per-project setup | Zero config, auto-detects projects |
| No idea what changed between sessions | Git tracking shows commits you missed |

## Architecture

```
monorail/
├── cli.py        # Command interface
├── daemon.py     # Background process (Unix double-fork)
├── watcher.py    # File monitoring (watchdog)
├── extractor.py  # Gemini API integration
├── notes.py      # Notes file management
├── tui.py        # Live dashboard (textual)
└── config.py     # YAML config
```

## License

MIT
