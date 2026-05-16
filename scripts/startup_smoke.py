from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from isolated_env import create_isolated_runtime


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
HOST = "127.0.0.1"
PORT = 5051
BASE_URL = f"http://{HOST}:{PORT}"
LOGIN_MARKERS = ("课堂行为检测控制台", "课堂行为检测")


def fetch_text(url: str) -> str:
    with urlopen(url, timeout=2) as response:
        return response.read(4096).decode("utf-8", errors="ignore")


def wait_for_ready(proc: subprocess.Popen[str], timeout_seconds: int) -> tuple[bool, str]:
    deadline = time.time() + timeout_seconds
    last_error = "服务未就绪"
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, f"应用提前退出，返回码 {proc.returncode}"
        try:
            body = fetch_text(f"{BASE_URL}/")
            if any(marker in body for marker in LOGIN_MARKERS):
                return True, body
            last_error = "首页已响应，但未命中预期标题"
        except URLError as exc:
            last_error = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
        time.sleep(0.5)
    return False, last_error


def read_admin_username(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload.get("username")


def main() -> int:
    if not PYTHON.exists():
        print(f"未找到虚拟环境 Python: {PYTHON}")
        return 1

    runtime = create_isolated_runtime(
        "startup-smoke",
        admin_username="startup_smoke_admin",
        admin_password="startup_smoke_pass_123",
    )
    log_out = runtime.root / "app.stdout.log"
    log_err = runtime.root / "app.stderr.log"
    admin_config_path = runtime.data_dir / "admin_config.json"

    env = runtime.build_env(
        base_env=os.environ,
        extra={
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "APP_HOST": HOST,
            "APP_PORT": str(PORT),
        },
    )

    proc = None
    stdout_handle = None
    stderr_handle = None
    succeeded = False
    try:
        stdout_handle = log_out.open("w", encoding="utf-8")
        stderr_handle = log_err.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(PYTHON), "app.py"],
            cwd=ROOT,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        ready, detail = wait_for_ready(proc, timeout_seconds=45)
        if not ready:
            print(f"启动烟测失败: {detail}")
            return 1

        session_body = fetch_text(f"{BASE_URL}/api/auth/session")
        if "authenticated" not in session_body:
            print("启动烟测失败: /api/auth/session 未返回认证状态")
            return 1

        bootstrapped_username = read_admin_username(admin_config_path)
        if bootstrapped_username != env["ADMIN_USERNAME"]:
            print("启动烟测失败: 临时管理员配置未按预期生成")
            return 1

        succeeded = True
        print("启动烟测通过。")
        print(f"- URL: {BASE_URL}/")
        print(f"- 临时管理员: {bootstrapped_username}")
        return 0
    except Exception as exc:
        print(f"启动烟测异常: {exc}")
        return 1
    finally:
        if stdout_handle:
            stdout_handle.flush()
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.flush()
            stderr_handle.close()
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        if not succeeded:
            if log_out.exists():
                print("\n--- app stdout ---")
                print(log_out.read_text(encoding="utf-8", errors="replace").strip())
            if log_err.exists():
                print("\n--- app stderr ---")
                print(log_err.read_text(encoding="utf-8", errors="replace").strip())
        shutil.rmtree(runtime.root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
