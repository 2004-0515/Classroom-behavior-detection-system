from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classroom_app.core.errors import ModelError
from classroom_app.core.model_integrity import ensure_model_manifest_valid, verify_model_manifest, write_manifest


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_manifest_roundtrip() -> None:
    with tempfile.TemporaryDirectory(prefix="classroom-model-integrity-") as temp_dir:
        model_root = Path(temp_dir) / "models"
        model_root.mkdir(parents=True, exist_ok=True)
        (model_root / "alpha.pt").write_bytes(b"alpha")
        write_manifest(model_root)
        issues = verify_model_manifest(model_root)
        assert_equal(issues, [], "freshly generated manifest should verify cleanly")


def test_detects_unapproved_model_file() -> None:
    with tempfile.TemporaryDirectory(prefix="classroom-model-integrity-") as temp_dir:
        model_root = Path(temp_dir) / "models"
        model_root.mkdir(parents=True, exist_ok=True)
        (model_root / "alpha.pt").write_bytes(b"alpha")
        write_manifest(model_root)
        (model_root / "rogue.pt").write_bytes(b"rogue")
        issues = verify_model_manifest(model_root)
        if "未登记模型文件: rogue.pt" not in issues:
            raise AssertionError(f"expected rogue.pt issue, got {issues}")


def test_detects_hash_mismatch() -> None:
    with tempfile.TemporaryDirectory(prefix="classroom-model-integrity-") as temp_dir:
        model_root = Path(temp_dir) / "models"
        model_root.mkdir(parents=True, exist_ok=True)
        target = model_root / "alpha.pt"
        target.write_bytes(b"alpha")
        write_manifest(model_root)
        target.write_bytes(b"beta")
        issues = verify_model_manifest(model_root)
        if "模型文件大小不匹配: alpha.pt (expected 5, got 4)" not in issues:
            raise AssertionError(f"expected alpha.pt size mismatch, got {issues}")


def test_rejects_invalid_manifest_shape() -> None:
    with tempfile.TemporaryDirectory(prefix="classroom-model-integrity-") as temp_dir:
        model_root = Path(temp_dir) / "models"
        model_root.mkdir(parents=True, exist_ok=True)
        (model_root / "alpha.pt").write_bytes(b"alpha")
        manifest_path = model_root / "checksums.json"
        manifest_path.write_text(json.dumps({"version": 1, "models": []}), encoding="utf-8")
        try:
            ensure_model_manifest_valid(model_root)
        except ModelError as exc:
            assert_equal(exc.code, "model_manifest_invalid", "invalid manifest should raise model_manifest_invalid")
        else:
            raise AssertionError("invalid manifest should have raised ModelError")


def main() -> int:
    test_manifest_roundtrip()
    test_detects_unapproved_model_file()
    test_detects_hash_mismatch()
    test_rejects_invalid_manifest_shape()
    print("model_integrity tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
