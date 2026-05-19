from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from runtime_paths import NODE_FALLBACK, resolve_node

ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = ROOT / "static" / "app"


# Fast regression entrypoint for frontend service-layer behavior.
def main() -> int:
    candidates = []
    primary = resolve_node()
    if primary:
        candidates.append(primary)
    if NODE_FALLBACK.exists() and NODE_FALLBACK not in candidates:
        candidates.append(NODE_FALLBACK)
    if not candidates:
        print(f"未找到可用 Node.js，可检查系统 PATH 或 bundled runtime: {NODE_FALLBACK}")
        return 1
    test_files = sorted(
        path
        for path in TEST_ROOT.rglob("*.test.js")
        if "node_modules" not in path.parts
    )
    if not test_files:
        print(f"未找到前端测试文件: {TEST_ROOT}")
        return 1

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    failures = []
    for node in candidates:
        try:
            result = subprocess.run([str(node), "--test", *[str(path) for path in test_files]], cwd=ROOT, env=env)
        except OSError as exc:
            failures.append(f"{node}: {exc}")
            continue
        return result.returncode

    for item in failures:
        print(item)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
