# Monorail

**Autosave for your coding sessions.** Keeps all your work on one track.

## Why Monorail?

Every time you start a new Claude Code or Codex session, you lose context. You have to explain what you were working on, what's done, what's not. Monorail fixes this.

**How it's different:**

- **Zero tokens burned** — Uses Gemini Flash Lite (very cheap tokens) instead of Claude/Codex tokens for extraction
- **Fully async** — Runs as a background daemon, extracts notes while you work, never interrupts your flow
- **Works with both tools** — Supports Claude Code and OpenAI Codex from the same daemon
- **Git-aware** — Tracks commits between sessions so Claude knows what changed while you were away
- **Auto-archival** — Old sessions get summarized automatically to keep context lean

When you start a new session, Claude reads your notes and picks up exactly where you left off.

## Getting Started

### Step 1: Get a Gemini API Key (free)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click "Create API Key"
3. Copy the key somewhere safe — you'll paste it in Step 3

This is what powers the note extraction. It's free and fast.

### Step 2: Install Monorail

Open your terminal and run:

```bash
pip install monorail-ai
```

That's it. You can run this from any folder.

<details>
<summary>🛠 Troubleshooting install issues</summary>

**"command not found: pip"**
Try `pip3` instead:
```bash
pip3 install monorail-ai
```

**"permission denied"**
Add `--user` to install just for your account:
```bash
pip install --user monorail-ai
```

**"monorail: command not found" after install**
The install worked, but the command isn't in your PATH. Try:
```bash
python3 -m monorail.cli init
```
Or add this alias to your shell config (`~/.zshrc` or `~/.bashrc`):
```bash
alias monorail="python3 -m monorail.cli"
```

**Still stuck?** [Open an issue](https://github.com/jchrysler/monorail/issues) — happy to help.
</details>

### Step 3: Run the Setup Wizard

```bash
monorail init
```

This will:
1. Ask for your Gemini API key (paste what you copied in Step 1)
2. Find your Claude Code and Codex projects automatically
3. Let you pick which ones to track
4. Start the background daemon

**That's it. You're done.** Monorail is now running and will extract notes from your sessions automatically.

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
<!-- monorail:start -->
## Session Start
- [ ] Read `context/monorail-notes.md` for recent session history
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
