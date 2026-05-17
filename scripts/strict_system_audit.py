from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from runtime_paths import PYTHON_ENV_VAR, resolve_node, resolve_playwright_node_paths, resolve_python


ROOT = Path(__file__).resolve().parent.parent
STATIC_APP = ROOT / "static" / "app"
ARTIFACT_DIR = ROOT / "docs" / "_artifacts"
SUMMARY_PATH = ARTIFACT_DIR / "strict-system-audit.json"
DEFAULT_ADMIN_USERNAME = "audit_admin"
DEFAULT_ADMIN_PASSWORD = "audit_password_123"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class AuditServerProcess:
    process: subprocess.Popen[str]
    log_path: Path
    log_handle: object


def build_node_path_env() -> dict[str, str]:
    env = os.environ.copy()
    project_node_modules = STATIC_APP / "node_modules"
    candidates = resolve_playwright_node_paths(project_node_modules=project_node_modules)
    if not candidates:
        raise RuntimeError(
            "未找到 Playwright 依赖目录。请先在 static/app 安装依赖，或确认 bundled runtime 中包含 playwright / playwright-core。"
        )
    existing = [item for item in env.get("NODE_PATH", "").split(os.pathsep) if item]
    env["NODE_PATH"] = os.pathsep.join([*(str(item) for item in candidates), *existing])
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def wait_for_server(base_url: str, *, expect_setup_required: bool, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(f"{base_url}/api/auth/session", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            data = payload.get("data") or {}
            if bool(data.get("setup_required")) == expect_setup_required:
                return
            last_error = f"setup_required={data.get('setup_required')}"
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"等待审计服务超时: {base_url} ({last_error})")


def start_audit_server(
    python_bin: Path,
    *,
    port: int,
    without_admin: bool,
    admin_username: str,
    admin_password: str,
    log_name: str,
) -> AuditServerProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env[PYTHON_ENV_VAR] = str(python_bin)
    if not without_admin:
        env["ADMIN_USERNAME"] = admin_username
        env["ADMIN_PASSWORD"] = admin_password

    command = [str(python_bin), "scripts/audit_server.py", "--host", "127.0.0.1", "--port", str(port)]
    if without_admin:
        command.append("--without-admin")

    log_path = ARTIFACT_DIR / f"strict-system-audit-server-{log_name}.log"
    log_handle = log_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return AuditServerProcess(process=process, log_path=log_path, log_handle=log_handle)


def read_process_output(server: AuditServerProcess) -> str:
    if not server.log_path.is_file():
        return ""
    try:
        return server.log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def terminate_process(server: AuditServerProcess) -> None:
    process = server.process
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    finally:
        try:
            server.log_handle.close()
        except Exception:
            pass


def run_node_audit(
    node_bin: Path,
    *,
    base_url: str,
    setup_base_url: str,
    artifact_dir: Path,
    output_path: Path,
    timeout_seconds: int,
    admin_username: str,
    admin_password: str,
) -> int:
    env = build_node_path_env()
    env["STRICT_AUDIT_BASE_URL"] = base_url
    env["STRICT_AUDIT_SETUP_BASE_URL"] = setup_base_url
    env["STRICT_AUDIT_ARTIFACT_DIR"] = str(artifact_dir)
    env["STRICT_AUDIT_OUTPUT_PATH"] = str(output_path)
    env["STRICT_AUDIT_ADMIN_USERNAME"] = admin_username
    env["STRICT_AUDIT_ADMIN_PASSWORD"] = admin_password
    command = [
        str(node_bin),
        str(STATIC_APP / "scripts" / "strict-system-audit.cjs"),
        "--base-url",
        base_url,
        "--setup-base-url",
        setup_base_url,
        "--artifact-dir",
        str(artifact_dir),
        "--output",
        str(output_path),
    ]
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
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the strict Playwright-based browser and UX audit")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--setup-port", type=int, default=5003)
    parser.add_argument("--timeout-seconds", type=int, default=720)
    parser.add_argument("--admin-username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()

    python_bin = resolve_python(current_python=ROOT / ".venv" / "Scripts" / "python.exe")
    node_bin = resolve_node()
    if not python_bin:
        print("未找到可用 Python 运行时")
        return 1
    if not node_bin:
        print("未找到可用 Node.js 运行时")
        return 1

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"
    setup_base_url = f"http://127.0.0.1:{args.setup_port}"

    main_server = start_audit_server(
        python_bin,
        port=args.port,
        without_admin=False,
        admin_username=args.admin_username,
        admin_password=args.admin_password,
        log_name="main",
    )
    setup_server = start_audit_server(
        python_bin,
        port=args.setup_port,
        without_admin=True,
        admin_username=args.admin_username,
        admin_password=args.admin_password,
        log_name="setup",
    )

    try:
        wait_for_server(base_url, expect_setup_required=False)
        wait_for_server(setup_base_url, expect_setup_required=True)
    except Exception as exc:
        terminate_process(main_server)
        terminate_process(setup_server)
        main_output = read_process_output(main_server)
        setup_output = read_process_output(setup_server)
        if main_output:
            print(main_output, end="")
        if setup_output:
            print(setup_output, end="")
        print(f"严格审计服务启动失败: {exc}")
        return 1

    try:
        return run_node_audit(
            node_bin,
            base_url=base_url,
            setup_base_url=setup_base_url,
            artifact_dir=ARTIFACT_DIR,
            output_path=SUMMARY_PATH,
            timeout_seconds=args.timeout_seconds,
            admin_username=args.admin_username,
            admin_password=args.admin_password,
        )
    finally:
        terminate_process(main_server)
        terminate_process(setup_server)


if __name__ == "__main__":
    raise SystemExit(main())
