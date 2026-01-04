"""Configuration management for Monorail."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List
import yaml

LEGACY_HOME = Path.home() / ".mm"

# Default paths
MONORAIL_HOME = Path.home() / ".monorail"
CONFIG_FILE = MONORAIL_HOME / "config.yaml"
PROMPTS_DIR = MONORAIL_HOME / "prompts"
INBOX_FILE = MONORAIL_HOME / "inbox.md"
OVERVIEW_FILE = MONORAIL_HOME / "overview.md"
DAEMON_PID = MONORAIL_HOME / "daemon.pid"
DAEMON_LOG = MONORAIL_HOME / "daemon.log"

# Default configuration
DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash-lite",
    # No longer need watch_paths - we watch ~/.claude/projects and ~/.codex/sessions directly
    "poll_interval_seconds": 30,
    "extract_on": {
        "min_new_bytes": 500,  # Lower threshold for faster feedback
        "idle_seconds": 60,    # Extract after 1 min idle
    },
    "max_sessions_before_archive": 20,
    "archive_summary_max_tokens": 500,
}


def migrate_legacy_home() -> None:
    """Move legacy ~/.mm data into ~/.monorail when possible."""
    if not LEGACY_HOME.exists():
        return

    if not MONORAIL_HOME.exists():
        try:
            LEGACY_HOME.rename(MONORAIL_HOME)
        except OSError:
            return
        return

    for item in LEGACY_HOME.iterdir():
        target = MONORAIL_HOME / item.name
        if target.exists():
            continue
        try:
            item.rename(target)
        except OSError:
            continue

    try:
        LEGACY_HOME.rmdir()
    except OSError:
        pass


class Config:
    """Monorail configuration manager."""

    def __init__(self):
        self._config: dict = {}
        self._load()

    def _load(self):
        """Load configuration from file or use defaults."""
        migrate_legacy_home()
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

        # Merge with defaults
        for key, value in DEFAULT_CONFIG.items():
            if key not in self._config:
                self._config[key] = value

    def save(self):
        """Save configuration to file."""
        MONORAIL_HOME.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)

    def get(self, key: str, default=None):
        """Get a configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value):
        """Set a configuration value."""
        self._config[key] = value

    @property
    def gemini_api_key(self) -> str:
        return self._config.get("gemini_api_key", "")

    @gemini_api_key.setter
    def gemini_api_key(self, value: str):
        self._config["gemini_api_key"] = value

    @property
    def gemini_model(self) -> str:
        return self._config.get("gemini_model", "gemini-2.0-flash-lite")

    @property
    def poll_interval(self) -> int:
        return self._config.get("poll_interval_seconds", 30)

    @property
    def min_new_bytes(self) -> int:
        return self._config.get("extract_on", {}).get("min_new_bytes", 2000)

    @property
    def idle_seconds(self) -> int:
        return self._config.get("extract_on", {}).get("idle_seconds", 120)


def ensure_monorail_home():
    """Ensure ~/.monorail directory structure exists."""
    migrate_legacy_home()
    MONORAIL_HOME.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Create inbox.md if it doesn't exist
    if not INBOX_FILE.exists():
        INBOX_FILE.write_text("# Monorail Inbox\n\n_No pending notes._\n")

    # Create overview.md if it doesn't exist
    if not OVERVIEW_FILE.exists():
        OVERVIEW_FILE.write_text("# Monorail Overview\n\n_No projects tracked yet._\n")


def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()
