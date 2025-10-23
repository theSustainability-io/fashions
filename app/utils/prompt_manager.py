from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict

from app.config import get_settings


class PromptManager:
    """Loads and persists customizable prompt templates."""

    DEFAULT_PROMPTS: Dict[str, str] = {
        "h2_heading": (
            "Given the main collection keyword: {keyword}. Suggest one complementary, "
            "semantically relevant H2 subtopic that helps shoppers discover related items.\n"
            "- Keep it 2-5 words.\n"
            "- Avoid repeating the main keyword verbatim.\n"
            "- Be specific, non-brand, and non-location.\n"
            "Return just the phrase."
        ),
        "paragraph": (
            "Write an informative, customer-friendly paragraph (~{target_words} words) expanding "
            "on the subtopic: {subtopic} in the context of {keyword}.\n"
            "- Tone: helpful, concise, non-fluffy.\n"
            "- Include practical shopping guidance (fit, fabrics, occasions, styling).\n"
            "- No brand claims, no pricing.\n"
            "- Avoid keyword stuffing.\n"
            "- Return plain HTML <p> only (no inline styles)."
        ),
        "h3_heading": (
            "For the main keyword {keyword}, suggest another complementary subtopic for an H3 heading "
            "that differs from {h2_keyword}.\n"
            "- 2-5 words, concise, non-brand.\n"
            "Return just the phrase."
        ),
    }

    def __init__(self, prompt_file: Path) -> None:
        self._prompt_file = prompt_file
        self._overrides: Dict[str, str] | None = None

    def get_prompt(self, key: str) -> str:
        """Return the prompt template for the given key, falling back to defaults."""
        if key not in self.DEFAULT_PROMPTS:
            raise KeyError(f"Unknown prompt key: {key}")
        overrides = self._load_overrides()
        value = overrides.get(key, "").strip()
        return value or self.DEFAULT_PROMPTS[key]

    def get_effective_prompts(self) -> Dict[str, str]:
        """Return the prompts currently in effect (overrides merged onto defaults)."""
        overrides = self._load_overrides()
        return {
            key: overrides.get(key, "").strip() or default
            for key, default in self.DEFAULT_PROMPTS.items()
        }

    def get_overrides(self) -> Dict[str, str]:
        """Return only user-provided overrides (without defaults)."""
        return dict(self._load_overrides())

    def save_overrides(self, prompts: Dict[str, str]) -> None:
        """Persist overrides that are non-empty; remove entries to fall back to defaults."""
        sanitized: Dict[str, str] = {}
        for key, value in prompts.items():
            if key not in self.DEFAULT_PROMPTS:
                continue
            cleaned = (value or "").strip()
            if cleaned:
                sanitized[key] = cleaned

        self._prompt_file.write_text(json.dumps(sanitized, indent=2))
        self._overrides = sanitized

    def _load_overrides(self) -> Dict[str, str]:
        if self._overrides is not None:
            return self._overrides
        if not self._prompt_file.exists():
            self._overrides = {}
            return self._overrides
        try:
            data = json.loads(self._prompt_file.read_text())
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        filtered: Dict[str, str] = {}
        for key, value in data.items():
            if key in self.DEFAULT_PROMPTS and isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    filtered[key] = cleaned
        self._overrides = filtered
        return self._overrides


@lru_cache()
def get_prompt_manager() -> PromptManager:
    settings = get_settings()
    return PromptManager(settings.prompt_file)
