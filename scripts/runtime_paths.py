from __future__ import annotations

import os
import subprocess
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON_ENV_VAR = "CLASSROOM_PYTHON"
FFMPEG_ENV_VAR = "FFMPEG_PATH"
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


def _can_invoke(candidate: Path, *version_args: str) -> bool:
    command = [str(candidate), *(version_args or ("--version",))]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _playwright_browser_roots() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: str | Path | None) -> None:
        resolved = _existing_dir(candidate)
        if resolved and resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_root and env_root != "0":
        add(env_root)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        add(Path(local_app_data) / "ms-playwright")
    add(Path.home() / "AppData" / "Local" / "ms-playwright")
    add(Path.home() / ".cache" / "ms-playwright")
    add(ROOT / "static" / "app" / "node_modules" / "playwright-core" / ".local-browsers")
    add(ROOT / "static" / "app" / "node_modules" / "playwright" / ".local-browsers")
    return candidates


def _iter_playwright_ffmpeg_candidates():
    executable_names = ("ffmpeg-win64.exe", "ffmpeg.exe", "ffmpeg-linux", "ffmpeg-mac", "ffmpeg")
    for browser_root in _playwright_browser_roots():
        for ffmpeg_dir in sorted(browser_root.glob("ffmpeg-*"), reverse=True):
            if not ffmpeg_dir.is_dir():
                continue
            for executable_name in executable_names:
                candidate = ffmpeg_dir / executable_name
                if candidate.is_file():
                    yield candidate.resolve()


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


def resolve_ffmpeg() -> Path | None:
    explicit_ffmpeg = _existing_file(os.environ.get(FFMPEG_ENV_VAR))
    if explicit_ffmpeg and _can_invoke(explicit_ffmpeg, "-version"):
        return explicit_ffmpeg

    path_ffmpeg = _existing_file(shutil.which("ffmpeg"))
    if path_ffmpeg and _can_invoke(path_ffmpeg, "-version"):
        return path_ffmpeg

    for candidate in _iter_playwright_ffmpeg_candidates():
        if _can_invoke(candidate, "-version"):
            return candidate
    return None


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
