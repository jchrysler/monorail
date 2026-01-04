# Monorail

**Keeps your CLI sessions on one track.**

Automatic context continuity for Claude Code and Codex. When you start a new session, Claude knows what happened in your last one.

## Prerequisites

1. **Python 3.9+**
2. **Gemini API key** — Get one free at [Google AI Studio](https://aistudio.google.com/apikey)

## Quick Start

```bash
# Install
pip install monorail-ai

# Configure (paste your Gemini API key when prompted)
monorail init

# Start the daemon
monorail start
```

Or with [pipx](https://pipx.pypa.io/) (recommended for CLI tools):

```bash
pipx install monorail-ai
```

<details>
<summary>Install from source</summary>

```bash
git clone https://github.com/jchrysler/monorail.git
cd monorail
pip install -e .
```
</details>

That's it. Monorail now watches all your Claude Code and Codex sessions.

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

## Active Context
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

## Commands

| Command | Description |
|---------|-------------|
| `monorail init` | First-time setup (prompts for API key) |
| `monorail init-project` | Initialize current directory (`--no-gitignore` to commit notes) |
| `monorail start` | Start background daemon |
| `monorail stop` | Stop daemon |
| `monorail status` | Show daemon and project status |
| `monorail watch` | Live TUI dashboard |
| `monorail log <project>` | Open project notes in $EDITOR |

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
