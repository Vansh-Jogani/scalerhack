"""Add package root to sys.path so tests can import prompts/, agents/, orchestrator/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
