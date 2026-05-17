from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "docs" / "_artifacts"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an acceptance package zip against its manifest")
    parser.add_argument("--label", default="acceptance-20260518")
    parser.add_argument("--zip-path", type=Path, default=None)
    parser.add_argument("--manifest-path", type=Path, default=None)
    parser.add_argument(
        "--check-live-files",
        action="store_true",
        help="also verify current workspace files still match manifest entries",
    )
    return parser.parse_args()


def normalize_path(value: Path | None, *, default_name: str) -> Path:
    if value is None:
        return ARTIFACT_DIR / default_name
    if value.is_absolute():
        return value
    return (ROOT / value).resolve()


def verify_manifest_shape(manifest: dict) -> list[str]:
    issues: list[str] = []
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        issues.append("manifest.files missing or empty")
    file_count = manifest.get("file_count")
    if not isinstance(file_count, int):
        issues.append("manifest.file_count missing or not an integer")
    elif isinstance(files, list) and file_count != len(files):
        issues.append(f"manifest.file_count mismatch: expected {len(files)} got {file_count}")
    for key in ("label", "acceptance_tag", "baseline_commit", "head_commit", "zip_path"):
        if not manifest.get(key):
            issues.append(f"manifest.{key} missing")
    return issues


def verify_package(zip_path: Path, manifest_path: Path, *, check_live_files: bool) -> list[str]:
    issues: list[str] = []
    if not manifest_path.exists():
        return [f"manifest missing: {manifest_path}"]
    if not zip_path.exists():
        return [f"package zip missing: {zip_path}"]

    manifest = load_json(manifest_path)
    issues.extend(verify_manifest_shape(manifest))
    files = manifest.get("files") or []
    expected_paths: set[str] = set()

    with zipfile.ZipFile(zip_path) as archive:
        archive_paths = {
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
        }
        for entry in files:
            path = entry.get("path")
            expected_size = entry.get("size_bytes")
            expected_sha256 = entry.get("sha256")
            if not isinstance(path, str) or not path:
                issues.append(f"invalid manifest entry path: {entry!r}")
                continue
            if path in expected_paths:
                issues.append(f"duplicate manifest entry: {path}")
                continue
            expected_paths.add(path)
            if path not in archive_paths:
                issues.append(f"missing zip entry: {path}")
                continue

            payload = archive.read(path)
            actual_size = len(payload)
            if actual_size != expected_size:
                issues.append(f"size mismatch for {path}: manifest={expected_size} zip={actual_size}")
            actual_sha256 = sha256_bytes(payload)
            if actual_sha256 != expected_sha256:
                issues.append(f"sha256 mismatch for {path}: manifest={expected_sha256} zip={actual_sha256}")

            if check_live_files:
                live_path = ROOT / path
                if not live_path.exists():
                    issues.append(f"live file missing: {path}")
                else:
                    live_payload = live_path.read_bytes()
                    if len(live_payload) != expected_size:
                        issues.append(f"live size mismatch for {path}: manifest={expected_size} live={len(live_payload)}")
                    live_sha256 = sha256_bytes(live_payload)
                    if live_sha256 != expected_sha256:
                        issues.append(f"live sha256 mismatch for {path}: manifest={expected_sha256} live={live_sha256}")

        extra_paths = sorted(archive_paths - expected_paths)
        if extra_paths:
            issues.append(f"unexpected zip entries: {extra_paths}")

    return issues


def main() -> int:
    args = parse_args()
    zip_path = normalize_path(args.zip_path, default_name=f"{args.label}-package.zip")
    manifest_path = normalize_path(args.manifest_path, default_name=f"{args.label}-package.manifest.json")
    issues = verify_package(zip_path, manifest_path, check_live_files=args.check_live_files)
    if issues:
        print(f"Acceptance package verification failed: {zip_path}")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print(f"Acceptance package verified: {zip_path}")
    print(f"Manifest verified: {manifest_path}")
    if args.check_live_files:
        print("Live workspace files also match manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
