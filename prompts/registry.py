"""Prompt registry: loads .md files, resolves {{include:}} directives, caches."""

import hashlib
import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

_cache: dict[str, dict] = {}


def load_prompt(name: str, reload: bool = False) -> dict:
    """Load prompt by name. Returns {text, version_hash}. Cached after first load."""
    if name in _cache and not reload:
        return _cache[name]

    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")

    def _resolve_include(match: re.Match) -> str:
        include_path = PROMPTS_DIR / match.group(1).strip()
        return include_path.read_text(encoding="utf-8")

    text = re.sub(r"\{\{include:\s*(.+?)\}\}", _resolve_include, text)

    version_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
    result = {"text": text, "version_hash": version_hash}
    _cache[name] = result
    return result


def fill_template(text: str, **kwargs: str) -> str:
    """Replace {{variable}} placeholders in text."""
    for key, value in kwargs.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text
