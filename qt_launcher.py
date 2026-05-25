from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.35):
            return True
    except OSError:
        return False


def _resolve_python() -> Path:
    candidates = [
        os.environ.get("CLASSROOM_PYTHON"),
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        sys.executable,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return Path(sys.executable)


def _start_backend_if_needed() -> subprocess.Popen | None:
    if _is_port_open(DEFAULT_HOST, DEFAULT_PORT):
        return None

    env = os.environ.copy()
    env["APP_HOST"] = DEFAULT_HOST
    env["APP_PORT"] = str(DEFAULT_PORT)
    python = _resolve_python()
    return subprocess.Popen(
        [str(python), str(ROOT / "app.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_backend(timeout_seconds: float = 18.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _is_port_open(DEFAULT_HOST, DEFAULT_PORT):
            return True
        time.sleep(0.25)
    return False


def _run_qt_app(url: str) -> int:
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
    except ImportError as exc:
        print("缺少 Qt 运行库。请先执行: pip install -r requirements-qt.txt", file=sys.stderr)
        print(f"原始错误: {exc}", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("课堂行为检测系统 - Qt 可视化入口")
    window.resize(1180, 760)

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        central = QWidget()
        layout = QVBoxLayout(central)
        label = QLabel(
            "Qt 桌面入口已启动课堂行为检测服务。\n"
            "当前环境未安装 QtWebEngine，点击下方按钮将在默认浏览器打开 Web 控制台。"
        )
        label.setWordWrap(True)
        button = QPushButton("打开课堂行为检测控制台")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        layout.addWidget(label)
        layout.addWidget(button)
        window.setCentralWidget(central)
    else:
        view = QWebEngineView()
        view.setUrl(QUrl(url))
        window.setCentralWidget(view)

    window.show()
    return app.exec()


def main() -> int:
    backend = _start_backend_if_needed()
    if not _wait_for_backend():
        print("Flask 后端未能在限定时间内启动，请先运行 start_demo_session.bat。", file=sys.stderr)
        return 1

    try:
        return _run_qt_app(DEFAULT_URL)
    finally:
        if backend is not None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
