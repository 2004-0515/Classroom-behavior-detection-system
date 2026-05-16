from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from runtime_paths import NODE_FALLBACK, resolve_node

ROOT = Path(__file__).resolve().parent.parent
TEST_FILE = ROOT / "static" / "app" / "services" / "task-services.test.js"


# Fast regression entrypoint for frontend service-layer behavior.
def main() -> int:
    node = resolve_node()
    if not node:
        print(f"未找到可用 Node.js，可检查系统 PATH 或 bundled runtime: {NODE_FALLBACK}")
        return 1
    if not TEST_FILE.exists():
        print(f"未找到前端 service 测试文件: {TEST_FILE}")
        return 1

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run([str(node), "--test", str(TEST_FILE)], cwd=ROOT, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
