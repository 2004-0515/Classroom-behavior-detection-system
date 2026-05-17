from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classroom_app.core.model_integrity import manifest_path_for, verify_model_manifest, write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="模型完整性清单维护工具")
    parser.add_argument("--rewrite", action="store_true", help="按当前 models/**/*.pt 重写 checksums.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_root = ROOT / "models"
    manifest_path = manifest_path_for(model_root)
    if args.rewrite:
        written = write_manifest(model_root, manifest_path=manifest_path)
        print(f"模型完整性清单已重写: {written.relative_to(ROOT).as_posix()}")
        return 0

    issues = verify_model_manifest(model_root, manifest_path=manifest_path)
    if issues:
        print("模型完整性校验失败:")
        for item in issues:
            print(f"- {item}")
        return 1

    print(f"模型完整性清单通过: {manifest_path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
