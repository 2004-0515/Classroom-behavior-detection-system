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


# Lightweight checks for Node runtime discovery without depending on the host PATH.
def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_prefers_node_from_path() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with patch("runtime_paths.shutil.which", return_value=r"C:\Node\node.exe"), patch("runtime_paths.NODE_FALLBACK", fallback):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, Path(r"C:\Node\node.exe"), "PATH node should win over fallback")


def test_uses_fallback_when_path_node_missing() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with patch("runtime_paths.shutil.which", return_value=None), patch("runtime_paths.NODE_FALLBACK", fallback), patch("pathlib.Path.exists", return_value=True):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, fallback, "fallback node should be used when PATH node is absent")


def test_returns_none_when_no_node_available() -> None:
    fallback = Path(r"C:\Fallback\node.exe")
    with patch("runtime_paths.shutil.which", return_value=None), patch("runtime_paths.NODE_FALLBACK", fallback), patch("pathlib.Path.exists", return_value=False):
        resolved = runtime_paths.resolve_node()
    assert_equal(resolved, None, "missing node should return None")


def main() -> int:
    test_prefers_node_from_path()
    test_uses_fallback_when_path_node_missing()
    test_returns_none_when_no_node_available()
    print("runtime_paths tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
