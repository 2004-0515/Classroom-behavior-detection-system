from __future__ import annotations

import shutil
from pathlib import Path


NODE_FALLBACK = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"


# Prefer user/system Node first, then fall back to the bundled runtime.
def resolve_node() -> Path | None:
    node = shutil.which("node")
    if node:
        return Path(node)
    if NODE_FALLBACK.exists():
        return NODE_FALLBACK
    return None
