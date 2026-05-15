"""Prompt registry — loads, caches, and version-hashes agent prompts from markdown files."""

import hashlib
import re
from pathlib import Path
from typing import TypedDict

_PROMPTS_DIR = Path(__file__).parent
_CACHE: dict[str, "PromptEntry"] = {}

_INCLUDE_PATTERN = re.compile(r'\{\{include:\s*([^}]+?)\s*\}\}')


class PromptEntry(TypedDict):
    text: str
    version_hash: str


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def _resolve_includes(text: str, base_dir: Path, _seen: frozenset[str] = frozenset()) -> str:
    """Replace {{include: path}} directives with file contents, recursively."""

    def replace_include(match: re.Match) -> str:
        rel_path = match.group(1).strip()
        abs_path = (base_dir / rel_path).resolve()
        key = str(abs_path)
        if key in _seen:
            return f"[circular include skipped: {rel_path}]"
        if not abs_path.exists():
            raise FileNotFoundError(f"Prompt include not found: {abs_path}")
        included_text = abs_path.read_text(encoding="utf-8")
        return _resolve_includes(included_text, abs_path.parent, _seen | {key})

    return _INCLUDE_PATTERN.sub(replace_include, text)


def load_prompt(name: str, *, reload: bool = False) -> PromptEntry:
    """Return prompt text and content hash for the named prompt.

    Prompts are loaded from prompts/<name>.md, includes are resolved at load
    time. Results are cached — pass reload=True in dev to force re-read.
    """
    if not reload and name in _CACHE:
        return _CACHE[name]

    prompt_path = _PROMPTS_DIR / f"{name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt '{name}' not found at {prompt_path}. "
            f"Available: {list_prompts()}"
        )

    raw = prompt_path.read_text(encoding="utf-8")
    resolved = _resolve_includes(raw, _PROMPTS_DIR)

    entry: PromptEntry = {
        "text": resolved,
        "version_hash": _content_hash(resolved),
    }
    _CACHE[name] = entry
    return entry


def fill_template(text: str, **kwargs: str) -> str:
    """Replace {{variable}} placeholders with runtime values.

    Distinct from include directives (which use `{{include: path}}`).
    Only substitutes plain {{key}} patterns where the key is a word token.
    Unknown keys are left as-is.
    """
    def replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(kwargs[key]) if key in kwargs else match.group(0)

    return re.sub(r'\{\{(\w+)\}\}', replacer, text)


def list_prompts() -> list[str]:
    """Return all prompt names available in the registry (no _shared files)."""
    return sorted(
        p.stem for p in _PROMPTS_DIR.glob("*.md") if not p.stem.startswith("_")
    )
