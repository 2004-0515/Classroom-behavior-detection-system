from __future__ import annotations

import os
import subprocess
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON_ENV_VAR = "CLASSROOM_PYTHON"
PYTHON_FALLBACK = ROOT / ".venv" / "Scripts" / "python.exe"
NODE_FALLBACK = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
NODE_MODULES_FALLBACK = NODE_FALLBACK.parent.parent / "node_modules"


def _existing_file(candidate: str | Path | None) -> Path | None:
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_file():
        return path.resolve()
    return None


def _existing_dir(candidate: str | Path | None) -> Path | None:
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_dir():
        return path.resolve()
    return None


def _can_invoke(candidate: Path) -> bool:
    try:
        result = subprocess.run(
            [str(candidate), "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


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
    path_node = _existing_file(shutil.which("node"))
    if path_node and _can_invoke(path_node):
        return path_node
    return _existing_file(NODE_FALLBACK)


def resolve_playwright_node_paths(*, project_node_modules: str | Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: str | Path | None) -> None:
        resolved = _existing_dir(candidate)
        if resolved and resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    add(project_node_modules)

    pnpm_root = _existing_dir(NODE_MODULES_FALLBACK / ".pnpm")
    if pnpm_root:
        for package_name in ("playwright", "playwright-core"):
            for match in sorted(pnpm_root.glob(f"{package_name}@*/node_modules")):
                add(match)

    return candidates
