from __future__ import annotations

import hashlib
import json
from pathlib import Path

from classroom_app.core.errors import ModelError


MANIFEST_FILENAME = "checksums.json"
MANIFEST_VERSION = 1


def normalize_model_root(model_root: str | Path) -> Path:
    return Path(model_root).resolve()


def manifest_path_for(model_root: str | Path) -> Path:
    return normalize_model_root(model_root) / MANIFEST_FILENAME


def normalize_manifest_key(value: str | Path) -> str:
    return Path(value).as_posix().lstrip("./")


def iter_model_files(model_root: str | Path) -> list[Path]:
    root = normalize_model_root(model_root)
    if not root.exists():
        return []
    return sorted((path for path in root.rglob("*.pt") if path.is_file()), key=lambda item: item.relative_to(root).as_posix().lower())


def compute_file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(model_root: str | Path) -> dict:
    root = normalize_model_root(model_root)
    models = {}
    for path in iter_model_files(root):
        relative_key = path.relative_to(root).as_posix()
        models[relative_key] = {
            "sha256": compute_file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
    return {
        "version": MANIFEST_VERSION,
        "models": dict(sorted(models.items(), key=lambda item: item[0].lower())),
    }


def write_manifest(model_root: str | Path, manifest_path: str | Path | None = None) -> Path:
    root = normalize_model_root(model_root)
    target = Path(manifest_path).resolve() if manifest_path else manifest_path_for(root)
    payload = build_manifest(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _manifest_error(message: str) -> ModelError:
    return ModelError(message, code="model_manifest_invalid", status=500)


def load_manifest(model_root: str | Path, manifest_path: str | Path | None = None) -> dict[str, dict[str, int | str]]:
    root = normalize_model_root(model_root)
    target = Path(manifest_path).resolve() if manifest_path else manifest_path_for(root)
    if not target.exists():
        raise _manifest_error(f"模型完整性清单缺失: {target.relative_to(root.parent).as_posix()}")

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise _manifest_error(f"模型完整性清单无法解析: {exc}") from exc

    if not isinstance(payload, dict):
        raise _manifest_error("模型完整性清单格式无效: 顶层必须是对象")
    if payload.get("version") != MANIFEST_VERSION:
        raise _manifest_error(f"模型完整性清单版本无效: {payload.get('version')!r}")

    models = payload.get("models")
    if not isinstance(models, dict):
        raise _manifest_error("模型完整性清单格式无效: models 必须是对象")

    normalized: dict[str, dict[str, int | str]] = {}
    for raw_key, raw_entry in models.items():
        key = normalize_manifest_key(raw_key)
        if not key or key.endswith("/"):
            raise _manifest_error(f"模型完整性清单路径无效: {raw_key!r}")
        if not isinstance(raw_entry, dict):
            raise _manifest_error(f"模型完整性清单条目无效: {key}")
        sha256 = raw_entry.get("sha256")
        size_bytes = raw_entry.get("size_bytes")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise _manifest_error(f"模型完整性清单缺少合法 sha256: {key}")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise _manifest_error(f"模型完整性清单缺少合法 size_bytes: {key}")
        normalized[key] = {
            "sha256": sha256.lower(),
            "size_bytes": size_bytes,
        }
    return normalized


def resolve_model_candidate(model_ref: str | Path, model_root: str | Path) -> tuple[Path, str]:
    root = normalize_model_root(model_root)
    reference = Path(str(model_ref).strip())
    if reference.is_absolute():
        raise ModelError("模型引用必须使用 models/ 目录内的相对路径", code="model_not_approved", status=409)
    candidate = (root / reference).resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ModelError("模型引用超出受信任的 models 目录", code="model_not_approved", status=409) from exc
    return candidate, relative


def validate_model_file(model_path: str | Path, model_root: str | Path, manifest: dict[str, dict[str, int | str]] | None = None) -> Path:
    root = normalize_model_root(model_root)
    path = Path(model_path).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ModelError("模型文件不在受信任的 models 目录内", code="model_not_approved", status=409) from exc

    entries = manifest or load_manifest(root)
    entry = entries.get(relative)
    if entry is None:
        raise ModelError(f"模型文件未登记到完整性清单: {relative}", code="model_not_approved", status=409)
    if not path.exists():
        raise ModelError(f"模型文件不存在: {relative}", code="model_not_found", status=404)

    actual_size = path.stat().st_size
    expected_size = int(entry["size_bytes"])
    if actual_size != expected_size:
        raise ModelError(
            f"模型文件大小不匹配: {relative} (expected {expected_size}, got {actual_size})",
            code="model_integrity_failed",
            status=409,
        )

    actual_sha256 = compute_file_sha256(path)
    expected_sha256 = str(entry["sha256"])
    if actual_sha256 != expected_sha256:
        raise ModelError(
            f"模型文件哈希不匹配: {relative}",
            code="model_integrity_failed",
            status=409,
        )
    return path


def verify_model_manifest(model_root: str | Path, manifest_path: str | Path | None = None) -> list[str]:
    root = normalize_model_root(model_root)
    entries = load_manifest(root, manifest_path=manifest_path)
    issues: list[str] = []

    actual_paths = iter_model_files(root)
    actual_keys = {path.relative_to(root).as_posix() for path in actual_paths}
    manifest_keys = set(entries)

    for key in sorted(actual_keys - manifest_keys):
        issues.append(f"未登记模型文件: {key}")
    for key in sorted(manifest_keys - actual_keys):
        issues.append(f"清单引用了不存在的模型文件: {key}")

    for path in actual_paths:
        relative = path.relative_to(root).as_posix()
        entry = entries.get(relative)
        if entry is None:
            continue
        actual_size = path.stat().st_size
        expected_size = int(entry["size_bytes"])
        if actual_size != expected_size:
            issues.append(f"模型文件大小不匹配: {relative} (expected {expected_size}, got {actual_size})")
            continue
        actual_sha256 = compute_file_sha256(path)
        expected_sha256 = str(entry["sha256"])
        if actual_sha256 != expected_sha256:
            issues.append(f"模型文件哈希不匹配: {relative}")
    return issues


def ensure_model_manifest_valid(model_root: str | Path, manifest_path: str | Path | None = None) -> None:
    issues = verify_model_manifest(model_root, manifest_path=manifest_path)
    if issues:
        message = "；".join(issues[:3])
        if len(issues) > 3:
            message += f"；其余 {len(issues) - 3} 项见健康检查"
        if any("未登记模型文件" in item for item in issues):
            code = "model_not_approved"
        elif any("哈希不匹配" in item or "大小不匹配" in item for item in issues):
            code = "model_integrity_failed"
        else:
            code = "model_not_found"
        raise ModelError(message, code=code, status=409 if code != "model_not_found" else 404)
