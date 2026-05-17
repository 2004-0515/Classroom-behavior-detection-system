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
        patch("pathlib.Path.is_file", new=path_is_file_for(r"C:\Node\node.exe", str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, Path(r"C:\Node\node.exe"), "PATH node should win over fallback")


def test_uses_fallback_when_path_node_missing() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=None),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, fallback, "fallback node should be used when PATH node is absent")


def test_ignores_node_directory_candidates() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=r"C:\Node\node-dir"),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("pathlib.Path.is_file", new=path_is_file_for(str(fallback))),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, fallback, "directory candidates should not be accepted as node runtimes")


def test_returns_none_when_no_node_available() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with (
        patch("runtime_paths.shutil.which", return_value=None),
        patch("runtime_paths.NODE_FALLBACK", fallback),
        patch("pathlib.Path.is_file", new=path_is_file_for()),
    ):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, None, "missing node should return None")


def main() -> int:
    test_prefers_python_from_env()
    test_prefers_current_python_when_env_missing()
    test_uses_python_fallback_when_current_missing()
    test_uses_python_from_path_when_other_candidates_missing()
    test_ignores_python_directory_candidates()
    test_returns_none_when_no_python_available()
    test_prefers_node_from_path()
    test_uses_fallback_when_path_node_missing()
    test_ignores_node_directory_candidates()
    test_returns_none_when_no_node_available()
    print("runtime_paths tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
