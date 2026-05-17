from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
ARTIFACT_DIR = DOCS_DIR / "_artifacts"


@dataclass(frozen=True)
class PackagePaths:
    zip_path: Path
    manifest_path: Path


def rel_posix(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def sha256_for(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def collect_base_files() -> tuple[list[Path], list[Path]]:
    required = [
        DOCS_DIR / "acceptance-handoff-20260518.md",
        DOCS_DIR / "high-standard-audit-report.md",
        DOCS_DIR / "demo-runbook.md",
        DOCS_DIR / "demo-readiness-checklist.md",
        ARTIFACT_DIR / "verify-all-summary.json",
        ARTIFACT_DIR / "strict-system-audit.json",
        ARTIFACT_DIR / "browser-visual-audit.json",
        ARTIFACT_DIR / "hardening-contracts.json",
        ARTIFACT_DIR / "real-demo-service-audit.json",
        ARTIFACT_DIR / "real-demo-full-browser-summary.json",
    ]
    optional = [
        ARTIFACT_DIR / "browser_audit_server.out.log",
        ARTIFACT_DIR / "browser_audit_server.err.log",
        ARTIFACT_DIR / "strict-system-audit-server-main.log",
        ARTIFACT_DIR / "strict-system-audit-server-setup.log",
        ARTIFACT_DIR / "real-demo-service-audit.out.log",
        ARTIFACT_DIR / "real-demo-service-audit.err.log",
    ]
    return required, optional


def extend_from_browser_visual(summary_path: Path, required: list[Path], optional: list[Path]) -> None:
    payload = load_json(summary_path)
    for screenshot in payload.get("screenshots", []):
        required.append(Path(screenshot))
    batch_zip_path = payload.get("batch_zip_path")
    if batch_zip_path:
        required.append(Path(batch_zip_path))


def extend_from_strict_audit(summary_path: Path, required: list[Path], optional: list[Path]) -> None:
    payload = load_json(summary_path)
    run_dir = payload.get("run_dir")
    if run_dir:
        run_path = ROOT / Path(run_dir)
        if run_path.exists():
            for child in sorted(run_path.rglob("*")):
                if child.is_file():
                    optional.append(child)


def extend_from_real_demo_service(summary_path: Path, required: list[Path], optional: list[Path]) -> None:
    payload = load_json(summary_path)
    artifacts = payload.get("artifacts") or {}
    for key in ("stdout_log", "stderr_log", "batch_zip"):
        relative_path = artifacts.get(key)
        if relative_path:
            optional.append(ROOT / Path(relative_path))


def extend_from_real_demo_browser(summary_path: Path, required: list[Path], optional: list[Path]) -> None:
    payload = load_json(summary_path)
    screenshots = payload.get("screenshots") or {}
    for value in screenshots.values():
        if value:
            optional.append(Path(value))


def resolve_files() -> tuple[list[Path], list[str]]:
    required, optional = collect_base_files()
    extend_from_browser_visual(ARTIFACT_DIR / "browser-visual-audit.json", required, optional)
    extend_from_strict_audit(ARTIFACT_DIR / "strict-system-audit.json", required, optional)
    extend_from_real_demo_service(ARTIFACT_DIR / "real-demo-service-audit.json", required, optional)
    extend_from_real_demo_browser(ARTIFACT_DIR / "real-demo-full-browser-summary.json", required, optional)

    resolved: list[Path] = []
    seen: set[Path] = set()
    missing_optional: list[str] = []

    def add(path: Path, *, optional_flag: bool) -> None:
        target = path.resolve()
        if target in seen:
            return
        if target.exists() and target.is_file():
            seen.add(target)
            resolved.append(target)
            return
        if optional_flag:
            missing_optional.append(str(path))
            return
        raise FileNotFoundError(f"required acceptance package file missing: {path}")

    for path in required:
        add(path, optional_flag=False)
    for path in optional:
        add(path, optional_flag=True)

    resolved.sort(key=lambda item: rel_posix(item))
    missing_optional.sort()
    return resolved, missing_optional


def describe_git_head() -> dict:
    commands = {
        "head_commit": ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        "head_short": ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        "branch": ["git", "-C", str(ROOT), "branch", "--show-current"],
    }
    data: dict[str, str] = {}
    for key, command in commands.items():
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding="utf-8")
        data[key] = result.stdout.strip()
    return data


def build_manifest(*, label: str, acceptance_tag: str, baseline_commit: str, files: list[Path], missing_optional: list[str], paths: PackagePaths) -> dict:
    git_state = describe_git_head()
    package_files = []
    for path in files:
        stat = path.stat()
        package_files.append(
            {
                "path": rel_posix(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "sha256": sha256_for(path),
            }
        )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "acceptance_tag": acceptance_tag,
        "baseline_commit": baseline_commit,
        "head_commit": git_state["head_commit"],
        "head_short": git_state["head_short"],
        "branch": git_state["branch"],
        "zip_path": rel_posix(paths.zip_path),
        "file_count": len(package_files),
        "missing_optional_files": missing_optional,
        "files": package_files,
    }


def build_package(paths: PackagePaths, files: list[Path]) -> None:
    paths.zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(paths.zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=rel_posix(file_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bundle acceptance docs and audit artifacts into a single zip package")
    parser.add_argument("--label", default="acceptance-20260518", help="package label used in output filenames")
    parser.add_argument("--acceptance-tag", default="acceptance-20260518")
    parser.add_argument("--baseline-commit", default="7e2fdb3")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = PackagePaths(
        zip_path=ARTIFACT_DIR / f"{args.label}-package.zip",
        manifest_path=ARTIFACT_DIR / f"{args.label}-package.manifest.json",
    )
    files, missing_optional = resolve_files()
    build_package(paths, files)
    manifest = build_manifest(
        label=args.label,
        acceptance_tag=args.acceptance_tag,
        baseline_commit=args.baseline_commit,
        files=files,
        missing_optional=missing_optional,
        paths=paths,
    )
    paths.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Acceptance package written: {rel_posix(paths.zip_path)}")
    print(f"Acceptance package manifest: {rel_posix(paths.manifest_path)}")
    print(f"Included files: {manifest['file_count']}")
    if missing_optional:
        print(f"Skipped optional files: {len(missing_optional)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
