from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from isolated_env import create_and_apply_isolated_runtime

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TEMP_ADMIN_USERNAME = "webcam_probe_admin"
TEMP_ADMIN_PASSWORD = "webcam_probe_password_123"


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def configure_temp_environment() -> Path:
    runtime, _ = create_and_apply_isolated_runtime(
        "webcam-probe",
        admin_username=TEMP_ADMIN_USERNAME,
        admin_password=TEMP_ADMIN_PASSWORD,
        model_folder=ROOT / "models",
    )
    return runtime.root


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the local webcam through the project stream service.")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--live-seconds", type=float, default=0.0, help="Start and stop a real webcam task for this many seconds.")
    parser.add_argument("--use-real-state", action="store_true", help="Write probe outputs into the real project data/uploads/outputs directories.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary isolated probe workspace instead of deleting it on exit.")
    args = parser.parse_args()

    temp_root = None
    payload: dict = {}
    exit_code = 0
    try:
        if args.use_real_state:
            payload["storage"] = {"mode": "real", "cleanup": "none"}
        else:
            temp_root = configure_temp_environment()
            payload["storage"] = {
                "mode": "isolated",
                "temp_root": str(temp_root),
                "cleanup": "kept" if args.keep_temp else "deleted_on_exit",
            }

        from classroom_app import create_app
        from classroom_app.core.errors import AppError

        app = create_app()
        with app.app_context():
            streams = app.extensions["services"].streams
            diagnostics = streams.diagnose_webcam(args.camera_index)
            payload["diagnostics"] = diagnostics

            selected = diagnostics.get("selected")
            if selected and args.live_seconds > 0:
                try:
                    started = streams.start_webcam(args.camera_index, confidence=0.25, iou=0.45)
                    time.sleep(max(0.1, args.live_seconds))
                    stopped = streams.stop_webcam()
                    summary = app.extensions["services"].task_payloads.build_task_payload(
                        stopped["task_id"],
                        include_assets=True,
                        include_live_metrics=False,
                    )
                    payload["live_cycle"] = {
                        "started": started,
                        "stopped": stopped,
                        "summary": summary,
                    }
                except AppError as exc:
                    payload["live_cycle"] = {
                        "error": exc.message,
                        "code": exc.code,
                    }
                    exit_code = 2

            if not selected and exit_code == 0:
                exit_code = 2
    finally:
        if temp_root and not args.keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)
            if isinstance(payload.get("storage"), dict):
                payload["storage"]["cleaned_up"] = True

    _print_json(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
