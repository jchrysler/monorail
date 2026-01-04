"""Gemini-based session log extraction."""

from __future__ import annotations

import time
import re
import sys
import io
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Suppress stderr during google imports (they print noisy warnings)
_original_stderr = sys.stderr
sys.stderr = io.StringIO()
try:
    import google.generativeai as genai
finally:
    sys.stderr = _original_stderr

from .config import get_config, PROMPTS_DIR


@dataclass
class ExtractionResult:
    """Result of extracting information from a session log."""
    stated_goal: str = ""
    what_happened: list[str] = None
    left_off_at: str = ""
    loose_threads: list[str] = None
    key_artifacts: dict[str, str] = None
    session_complete: bool = False
    status: str = ""
    vibe: str = ""
    raw_response: str = ""

    def __post_init__(self):
        if self.what_happened is None:
            self.what_happened = []
        if self.loose_threads is None:
            self.loose_threads = []
        if self.key_artifacts is None:
            self.key_artifacts = {}


class Extractor:
    """Extract structured information from session logs using Gemini."""

    def __init__(self):
        self.config = get_config()
        self._last_extraction_time = 0
        self._min_interval = 30  # seconds between extractions
        self._model = None

    def _init_model(self):
        """Initialize the Gemini model."""
        if self._model is None:
            genai.configure(api_key=self.config.gemini_api_key)
            self._model = genai.GenerativeModel(self.config.gemini_model)

    def _load_prompt(self, name: str) -> str:
        """Load a prompt template."""
        prompt_path = PROMPTS_DIR / f"{name}.txt"
        if prompt_path.exists():
            return prompt_path.read_text()
        return ""

    def extract(
        self,
        log_content: str,
        project: str,
        tool: str = "claude",
        previous_context: str = "",
    ) -> Optional[ExtractionResult]:
        """Extract structured information from session log content."""
        # Rate limiting
        now = time.time()
        if now - self._last_extraction_time < self._min_interval:
            return None

        self._init_model()
        self._last_extraction_time = now

        # Load and format prompt
        prompt_template = self._load_prompt("extract")
        if not prompt_template:
            return None

        prompt = prompt_template.format(
            tool=tool,
            project=project,
            log_content=log_content,
            previous_context=previous_context or "None",
        )

        # Call Gemini
        try:
            response = self._model.generate_content(prompt)
            return self._parse_response(response.text)
        except Exception as e:
            # Log error but don't crash
            print(f"Extraction error: {e}")
            return None

    def _parse_response(self, response: str) -> ExtractionResult:
        """Parse Gemini's response into structured data."""
        result = ExtractionResult(raw_response=response)

        # Parse STATED_GOAL
        goal_match = re.search(r"STATED_GOAL:\s*(.+?)(?:\n\n|\nWHAT_HAPPENED)", response, re.DOTALL)
        if goal_match:
            result.stated_goal = goal_match.group(1).strip()

        # Parse WHAT_HAPPENED
        what_match = re.search(r"WHAT_HAPPENED:\s*\n((?:- .+\n?)+)", response)
        if what_match:
            items = re.findall(r"- (.+)", what_match.group(1))
            result.what_happened = [item.strip() for item in items]

        # Parse LEFT_OFF_AT
        left_match = re.search(r"LEFT_OFF_AT:\s*(.+?)(?:\n\n|\nLOOSE_THREADS)", response, re.DOTALL)
        if left_match:
            result.left_off_at = left_match.group(1).strip()

        # Parse LOOSE_THREADS
        threads_match = re.search(r"LOOSE_THREADS:\s*\n((?:- .+\n?)+)", response)
        if threads_match:
            items = re.findall(r"- (.+)", threads_match.group(1))
            result.loose_threads = [item.strip() for item in items]

        # Parse KEY_ARTIFACTS
        artifacts_match = re.search(r"KEY_ARTIFACTS:\s*\n((?:- .+\n?)+)", response)
        if artifacts_match:
            for line in re.findall(r"- (.+)", artifacts_match.group(1)):
                if ":" in line:
                    path, desc = line.split(":", 1)
                    result.key_artifacts[path.strip()] = desc.strip()

        # Parse SESSION_COMPLETE
        complete_match = re.search(r"SESSION_COMPLETE:\s*(true|false)", response, re.IGNORECASE)
        if complete_match:
            result.session_complete = complete_match.group(1).lower() == "true"

        # Parse STATUS
        status_match = re.search(r"STATUS:\s*(.+?)(?:\n|$)", response)
        if status_match:
            result.status = status_match.group(1).strip()

        # Parse VIBE
        vibe_match = re.search(r"VIBE:\s*(\w+)", response)
        if vibe_match:
            result.vibe = vibe_match.group(1).strip().lower()

        return result

    def summarize(self, sessions: str, max_tokens: int = 500) -> str:
        """Summarize multiple sessions for archival. [WIP: Used by archive feature]"""
        self._init_model()

        prompt_template = self._load_prompt("summarize")
        if not prompt_template:
            return ""

        prompt = prompt_template.format(
            sessions=sessions,
            max_tokens=max_tokens,
        )

        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Summarization error: {e}")
            return ""
