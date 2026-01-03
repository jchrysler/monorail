"""Configuration management for Music Man."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List
import yaml

# Default paths
MM_HOME = Path.home() / ".mm"
CONFIG_FILE = MM_HOME / "config.yaml"
PROMPTS_DIR = MM_HOME / "prompts"
INBOX_FILE = MM_HOME / "inbox.md"
OVERVIEW_FILE = MM_HOME / "overview.md"
DAEMON_PID = MM_HOME / "daemon.pid"
DAEMON_LOG = MM_HOME / "daemon.log"

# Default configuration
DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.0-flash-lite",
    "watch_paths": [
        str(Path.home() / "projects"),
        str(Path.home() / "work"),
    ],
    "watch_pattern": "**/pool/.session.log",
    "poll_interval_seconds": 30,
    "extract_on": {
        "min_new_bytes": 2000,
        "idle_seconds": 120,
        "session_end_phrases": [
            "goodbye",
            "ending session",
            "talk to you later",
            "/exit",
            "^C",
            "Session ended",
        ],
    },
    "max_sessions_before_archive": 20,
    "archive_summary_max_tokens": 500,
    "ignore_paths": [
        "**/node_modules/**",
        "**/.git/**",
        "**/venv/**",
    ],
}


class Config:
    """Music Man configuration manager."""

    def __init__(self):
        self._config: dict = {}
        self._load()

    def _load(self):
        """Load configuration from file or use defaults."""
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
        MM_HOME.mkdir(parents=True, exist_ok=True)
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
    def watch_paths(self) -> list[str]:
        return self._config.get("watch_paths", [])

    @property
    def poll_interval(self) -> int:
        return self._config.get("poll_interval_seconds", 30)

    @property
    def min_new_bytes(self) -> int:
        return self._config.get("extract_on", {}).get("min_new_bytes", 2000)

    @property
    def idle_seconds(self) -> int:
        return self._config.get("extract_on", {}).get("idle_seconds", 120)

    @property
    def session_end_phrases(self) -> list[str]:
        return self._config.get("extract_on", {}).get("session_end_phrases", [])

    @property
    def ignore_paths(self) -> list[str]:
        return self._config.get("ignore_paths", [])


def ensure_mm_home():
    """Ensure ~/.mm directory structure exists."""
    MM_HOME.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Create inbox.md if it doesn't exist
    if not INBOX_FILE.exists():
        INBOX_FILE.write_text("# Music Man Inbox\n\n_No pending notes._\n")

    # Create overview.md if it doesn't exist
    if not OVERVIEW_FILE.exists():
        OVERVIEW_FILE.write_text("# Music Man Overview\n\n_No projects tracked yet._\n")


def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()
