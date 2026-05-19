from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import runtime_paths


# Lightweight checks for runtime discovery without depending on the host PATH.
def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def path_is_file_for(*existing: str):
    normalized = {str(Path(item)) for item in existing}

    def _is_file(path: Path) -> bool:
        return str(path) in normalized

    return _is_file


def path_is_dir_for(*existing: str):
    normalized = {str(Path(item)) for item in existing}

    def _is_dir(path: Path) -> bool:
        return str(path) in normalized

    return _is_dir


def glob_for(mapping: dict[str, list[Path]]):
    def _glob(path: Path, pattern: str):
        return mapping.get(pattern, [])

    return _glob


def test_prefers_python_from_env() -> None:
    env_python = Path(r"C:\Env\python.exe")
    current_python = Path(r"C:\Current\python.exe")
    fallback_python = Path(r"C:\Fallback\python.exe")
    path_python = Path(r"C:\Path\python.exe")
    with (
        patch.dict("os.environ", {runtime_paths.PYTHON_ENV_VAR: str(env_python)}, clear=False),
        patch("runtime_paths.sys.executable", str(current_python)),
        patch("runtime_paths.PYTHON_FALLBACK", fallback_python),
        patch("runtime_paths.shutil.which", return_value=str(path_python)),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(env_python), str(current_python), str(fallback_python), str(path_python))),
    ):
        resolved = runtime_paths.resolve_python()
    assert_equal(resolved, env_python, "environment python should win over other candidates")


def test_prefers_current_python_when_env_missing() -> None:
    current_python = Path(r"C:\Current\python.exe")
    fallback_python = Path(r"C:\Fallback\python.exe")
    path_python = Path(r"C:\Path\python.exe")
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.sys.executable", str(current_python)),
        patch("runtime_paths.PYTHON_FALLBACK", fallback_python),
        patch("runtime_paths.shutil.which", return_value=str(path_python)),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(current_python), str(fallback_python), str(path_python))),
    ):
        resolved = runtime_paths.resolve_python()
    assert_equal(resolved, current_python, "current interpreter should win when env override is absent")


def test_uses_python_fallback_when_current_missing() -> None:
    current_python = Path(r"C:\Missing\python.exe")
    fallback_python = Path(r"C:\Fallback\python.exe")
    path_python = Path(r"C:\Path\python.exe")
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.sys.executable", str(current_python)),
        patch("runtime_paths.PYTHON_FALLBACK", fallback_python),
        patch("runtime_paths.shutil.which", return_value=str(path_python)),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(fallback_python), str(path_python))),
    ):
        resolved = runtime_paths.resolve_python()
    assert_equal(resolved, fallback_python, "repo .venv python should be used when current interpreter is unavailable")


def test_uses_python_from_path_when_other_candidates_missing() -> None:
    current_python = Path(r"C:\Missing\python.exe")
    fallback_python = Path(r"C:\Fallback\python.exe")
    path_python = Path(r"C:\Path\python.exe")
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.sys.executable", str(current_python)),
        patch("runtime_paths.PYTHON_FALLBACK", fallback_python),
        patch("runtime_paths.shutil.which", return_value=str(path_python)),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(path_python))),
    ):
        resolved = runtime_paths.resolve_python()
    assert_equal(resolved, path_python, "PATH python should be used when env, current, and repo .venv are unavailable")


def test_ignores_python_directory_candidates() -> None:
    env_python_dir = Path(r"C:\Env\python-dir")
    current_python = Path(r"C:\Current\python.exe")
    with (
        patch.dict("os.environ", {runtime_paths.PYTHON_ENV_VAR: str(env_python_dir)}, clear=False),
        patch("runtime_paths.sys.executable", str(current_python)),
        patch("runtime_paths.PYTHON_FALLBACK", Path(r"C:\Fallback\python.exe")),
        patch("runtime_paths.shutil.which", return_value=r"C:\Path\python.exe"),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(current_python))),
    ):
        resolved = runtime_paths.resolve_python()
    assert_equal(resolved, current_python, "directory candidates should not be accepted as python runtimes")


def test_returns_none_when_no_python_available() -> None:
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.sys.executable", r"C:\Missing\python.exe"),
        patch("runtime_paths.PYTHON_FALLBACK", Path(r"C:\Fallback\python.exe")),
        patch("runtime_paths.shutil.which", return_value=None),
        patch("pathlib.Path.is_file", new=path_is_file_for()),
    ):
        resolved = runtime_paths.resolve_python()
    assert_equal(resolved, None, "missing python should return None")


def test_prefers_node_from_path() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=r"C:\Node\node.exe"),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths._can_invoke", return_value=True),
        patch("pathlib.Path.is_file", new=path_is_file_for(r"C:\Node\node.exe", str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, Path(r"C:\Node\node.exe"), "PATH node should win over fallback")


def test_uses_fallback_when_path_node_missing() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=None),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths._can_invoke", return_value=False),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, fallback, "fallback node should be used when PATH node is absent")


def test_falls_back_when_path_node_is_not_invokable() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=r"C:\Node\node.exe"),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths._can_invoke", return_value=False),
        patch("pathlib.Path.is_file", new=path_is_file_for(r"C:\Node\node.exe", str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, fallback, "fallback node should be used when PATH node cannot be executed")


def test_ignores_node_directory_candidates() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=r"C:\Node\node-dir"),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths._can_invoke", return_value=False),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, fallback, "directory candidates should not be accepted as node runtimes")


def test_returns_none_when_no_node_available() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=None),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths._can_invoke", return_value=False),
        patch("pathlib.Path.is_file", new=path_is_file_for()),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, None, "missing node should return None")


def test_prefers_ffmpeg_from_env() -> None:
    env_ffmpeg = Path(r"C:\Env\ffmpeg.exe")
    with (
        patch.dict("os.environ", {runtime_paths.FFMPEG_ENV_VAR: str(env_ffmpeg)}, clear=False),
        patch("runtime_paths.shutil.which", return_value=r"C:\Path\ffmpeg.exe"),
        patch("runtime_paths._can_invoke", return_value=True),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(env_ffmpeg), r"C:\Path\ffmpeg.exe")),
    ):
        resolved = runtime_paths.resolve_ffmpeg()
    assert_equal(resolved, env_ffmpeg, "explicit ffmpeg env var should win over PATH and Playwright fallbacks")


def test_uses_ffmpeg_from_path_when_env_missing() -> None:
    path_ffmpeg = Path(r"C:\Path\ffmpeg.exe")
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.shutil.which", return_value=str(path_ffmpeg)),
        patch("runtime_paths._can_invoke", return_value=True),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(path_ffmpeg))),
    ):
        resolved = runtime_paths.resolve_ffmpeg()
    assert_equal(resolved, path_ffmpeg, "PATH ffmpeg should be used when env override is absent")


def test_uses_playwright_ffmpeg_when_env_and_path_missing() -> None:
    browser_root = Path(r"C:\Users\Test\AppData\Local\ms-playwright")
    ffmpeg_dir = browser_root / "ffmpeg-1011"
    ffmpeg_bin = ffmpeg_dir / "ffmpeg-win64.exe"
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.shutil.which", return_value=None),
        patch("runtime_paths._can_invoke", return_value=True),
        patch("pathlib.Path.is_dir", new=path_is_dir_for(str(browser_root), str(ffmpeg_dir))),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(ffmpeg_bin))),
        patch("runtime_paths._playwright_browser_roots", return_value=[browser_root]),
        patch("pathlib.Path.glob", new=glob_for({"ffmpeg-*": [ffmpeg_dir]})),
    ):
        resolved = runtime_paths.resolve_ffmpeg()
    assert_equal(resolved, ffmpeg_bin, "Playwright ffmpeg should be used when env and PATH ffmpeg are unavailable")


def test_returns_none_when_no_ffmpeg_available() -> None:
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("runtime_paths.shutil.which", return_value=None),
        patch("runtime_paths._can_invoke", return_value=False),
        patch("pathlib.Path.is_dir", new=path_is_dir_for()),
        patch("pathlib.Path.is_file", new=path_is_file_for()),
        patch("runtime_paths._playwright_browser_roots", return_value=[]),
    ):
        resolved = runtime_paths.resolve_ffmpeg()
    assert_equal(resolved, None, "missing ffmpeg should return None")


def test_resolve_playwright_node_paths_prefers_project_node_modules() -> None:
    project_node_modules = Path(r"D:\Repo\static\app\node_modules")
    fallback = Path(r"C:\Fallback\node.exe")
    bundled_modules = Path(r"C:\Bundled\node_modules")
    bundled_pnpm = bundled_modules / ".pnpm"
    playwright_dir = bundled_pnpm / "playwright@1.59.1" / "node_modules"
    playwright_core_dir = bundled_pnpm / "playwright-core@1.59.1" / "node_modules"

    with (
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths.NODE_MODULES_FALLBACK", bundled_modules),
        patch("pathlib.Path.is_dir", new=path_is_dir_for(str(project_node_modules), str(bundled_pnpm), str(playwright_dir), str(playwright_core_dir))),
        patch("pathlib.Path.glob", new=glob_for({"playwright@*/node_modules": [playwright_dir], "playwright-core@*/node_modules": [playwright_core_dir]})),
    ):
        resolved = runtime_paths.resolve_playwright_node_paths(project_node_modules=project_node_modules)
    assert_equal(
        resolved,
        [project_node_modules, playwright_dir, playwright_core_dir],
        "project node_modules should be first, followed by bundled playwright pnpm paths",
    )


def test_resolve_playwright_node_paths_ignores_missing_directories() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    bundled_modules = Path(r"C:\Bundled\node_modules")
    bundled_pnpm = bundled_modules / ".pnpm"
    playwright_dir = bundled_pnpm / "playwright@1.59.1" / "node_modules"

    with (
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("runtime_paths.NODE_MODULES_FALLBACK", bundled_modules),
        patch("pathlib.Path.is_dir", new=path_is_dir_for(str(bundled_pnpm), str(playwright_dir))),
        patch("pathlib.Path.glob", new=glob_for({"playwright@*/node_modules": [playwright_dir], "playwright-core@*/node_modules": []})),
    ):
        resolved = runtime_paths.resolve_playwright_node_paths(project_node_modules=Path(r"D:\Missing\node_modules"))
    assert_equal(resolved, [playwright_dir], "missing project directories should be skipped")


def main() -> int:
    test_prefers_python_from_env()
    test_prefers_current_python_when_env_missing()
    test_uses_python_fallback_when_current_missing()
    test_uses_python_from_path_when_other_candidates_missing()
    test_ignores_python_directory_candidates()
    test_returns_none_when_no_python_available()
    test_prefers_node_from_path()
    test_uses_fallback_when_path_node_missing()
    test_falls_back_when_path_node_is_not_invokable()
    test_ignores_node_directory_candidates()
    test_returns_none_when_no_node_available()
    test_prefers_ffmpeg_from_env()
    test_uses_ffmpeg_from_path_when_env_missing()
    test_uses_playwright_ffmpeg_when_env_and_path_missing()
    test_returns_none_when_no_ffmpeg_available()
    test_resolve_playwright_node_paths_prefers_project_node_modules()
    test_resolve_playwright_node_paths_ignores_missing_directories()
    print("runtime_paths tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
