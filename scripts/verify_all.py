from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from runtime_paths import PYTHON_ENV_VAR, resolve_python


ROOT = Path(__file__).resolve().parent.parent
PYTHON = resolve_python(current_python=ROOT / ".venv" / "Scripts" / "python.exe")
ARTIFACT_DIR = ROOT / "docs" / "_artifacts"
SUMMARY_PATH = ARTIFACT_DIR / "verify-all-summary.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ordered top-level verification chain for demo/readiness acceptance.
CHECKS: list[tuple[str, list[str], int]] = []
if PYTHON:
    CHECKS.extend(
        [
            ("healthcheck", [str(PYTHON), "scripts/healthcheck.py"], 120),
            ("startup_smoke", [str(PYTHON), "scripts/startup_smoke.py"], 90),
            ("frontend_service_tests", [str(PYTHON), "scripts/frontend_service_tests.py"], 60),
            ("ui_smoke", [str(PYTHON), "scripts/ui_smoke.py"], 120),
            ("interaction_smoke", [str(PYTHON), "scripts/interaction_smoke.py"], 120),
            ("regression_smoke", [str(PYTHON), "scripts/regression_smoke.py"], 180),
            ("hardening_contracts", [str(PYTHON), "scripts/hardening_contracts.py"], 240),
            ("audit_readiness", [str(PYTHON), "scripts/audit_readiness.py"], 120),
            ("strict_system_audit", [str(PYTHON), "scripts/strict_system_audit.py"], 720),
        ]
    )
CHECKS.append(
    (
        "browser_visual_audit",
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/browser_visual_audit.ps1"],
        180,
    )
)


def run_check(name: str, command: list[str], timeout_seconds: int) -> tuple[bool, float]:
    started = time.time()
    print(f"\n=== {name} ===")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if PYTHON:
        env[PYTHON_ENV_VAR] = str(PYTHON)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - started
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        print(f"{name} TIMEOUT after {timeout_seconds}s ({duration:.1f}s)")
        return False, duration
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    duration = time.time() - started
    if result.returncode != 0:
        print(f"{name} FAILED ({duration:.1f}s)")
        return False, duration
    print(f"{name} OK ({duration:.1f}s)")
    return True, duration


def write_summary(summary: list[tuple[str, bool, float]]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python": str(PYTHON) if PYTHON else None,
        "checks": [
            {
                "name": name,
                "status": "OK" if ok else "FAILED",
                "duration_seconds": round(duration, 3),
            }
            for name, ok, duration in summary
        ],
        "overall_status": "OK" if summary and all(ok for _, ok, _ in summary) and len(summary) == len(CHECKS) else "FAILED",
    }
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    if not PYTHON:
        print("未找到可用 Python 运行时")
        return 1

    summary: list[tuple[str, bool, float]] = []
    for name, command, timeout_seconds in CHECKS:
        ok, duration = run_check(name, command, timeout_seconds)
        summary.append((name, ok, duration))
        if not ok:
            break

    print("\n验证汇总:")
    for name, ok, duration in summary:
        print(f"- {name}: {'OK' if ok else 'FAILED'} ({duration:.1f}s)")
    write_summary(summary)
    print(f"\n验证汇总已写入: {SUMMARY_PATH.relative_to(ROOT).as_posix()}")

    return 0 if summary and all(ok for _, ok, _ in summary) and len(summary) == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
