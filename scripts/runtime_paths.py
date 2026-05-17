from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON_ENV_VAR = "CLASSROOM_PYTHON"
PYTHON_FALLBACK = ROOT / ".venv" / "Scripts" / "python.exe"
NODE_FALLBACK = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"


def _existing_file(candidate: str | Path | None) -> Path | None:
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_file():
        return path.resolve()
    return None


def resolve_python(*, current_python: str | Path | None = None) -> Path | None:
    candidates = [
        os.environ.get(PYTHON_ENV_VAR),
        current_python or sys.executable,
        PYTHON_FALLBACK,
        shutil.which("python"),
    ]
    for candidate in candidates:
        resolved = _existing_file(candidate)
        if resolved:
            return resolved
    return None


# Prefer user/system Node first, then fall back to the bundled runtime.
def resolve_node() -> Path | None:
    return _existing_file(shutil.which("node")) or _existing_file(NODE_FALLBACK)
