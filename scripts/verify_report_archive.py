from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

REPORT_TEXT_MARKERS = ("课堂行为检测报告", "学生行为分析")


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def normalize_report_text(value: object) -> str:
    return " ".join(str(value or "").split())


def get_expected_report_metrics(summary: dict, limit: int = 4) -> list[dict]:
    cards = ((summary.get("display_metrics") or {}).get("cards") or [])[:limit]
    return [
        {
            "label": normalize_report_text(item.get("label")),
            "value": normalize_report_text(item.get("formatted") or item.get("value") or "--"),
        }
        for item in cards
    ]


def assert_report_html_contract(
    summary: dict,
    html: str,
    label: str,
    required_markers: list[str] | tuple[str, ...] | None = None,
) -> dict:
    normalized_html = normalize_report_text(html)
    markers = list(REPORT_TEXT_MARKERS)
    if required_markers:
        markers.extend(str(marker) for marker in required_markers if str(marker).strip())
    for marker in markers:
        if marker not in normalized_html:
            raise AssertionError(f"{label} HTML missing marker: {marker}")
    expected_metrics = get_expected_report_metrics(summary)
    if not expected_metrics:
        raise AssertionError(f"{label} summary missing display metric cards")
    for metric in expected_metrics:
        if metric["label"] not in normalized_html:
            raise AssertionError(f"{label} HTML missing metric label: {metric['label']}")
        if metric["value"] not in normalized_html:
            raise AssertionError(f"{label} HTML missing metric value: {metric['value']}")
    return {
        "metric_count": len(expected_metrics),
        "verified_metrics": expected_metrics,
        "required_markers": markers,
    }


def resolve_contract_field(record: dict, dotted_path: str, label: str) -> object:
    current: object = record
    for segment in dotted_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"{label} missing field: {dotted_path}")
        current = current[segment]
    return current


def build_archive_expectations(
    expected_reports: list[dict],
    report_filename_path: str = "report_filename",
    summary_path: str = "summary",
) -> list[dict]:
    expectations: list[dict] = []
    for index, record in enumerate(expected_reports):
        label = f"expected_reports[{index}]"
        report_filename = str(resolve_contract_field(record, report_filename_path, label) or "").strip()
        summary = resolve_contract_field(record, summary_path, label)
        if not report_filename:
            raise ValueError(f"{label} has empty report filename at {report_filename_path}")
        if not isinstance(summary, dict) or not summary:
            raise ValueError(f"{label} has invalid summary at {summary_path}")
        expectations.append({"report_filename": report_filename, "summary": summary})
    return expectations


def assert_batch_archive_contract(archive: zipfile.ZipFile, expected_reports: list[dict], label: str) -> dict:
    names = set(archive.namelist())
    required = {"readme.txt", "manifest.csv"}
    if not required.issubset(names):
        raise AssertionError(f"{label} missing manifest files: {sorted(names)}")
    manifest_text = archive.read("manifest.csv").decode("utf-8", errors="replace")
    readme_text = archive.read("readme.txt").decode("utf-8", errors="replace")
    verified_reports: list[str] = []
    for expected_report in expected_reports:
        report_filename = expected_report["report_filename"]
        if report_filename not in names:
            raise AssertionError(f"{label} missing report file: {report_filename}")
        if report_filename not in manifest_text or report_filename not in readme_text:
            raise AssertionError(f"{label} manifest/readme missing report reference: {report_filename}")
        html = archive.read(report_filename).decode("utf-8", errors="replace")
        assert_report_html_contract(expected_report["summary"], html, f"{label}::{report_filename}")
        verified_reports.append(report_filename)
    return {
        "report_count": len(verified_reports),
        "verified_reports": verified_reports,
        "zip_entries": sorted(names),
    }


def verify_report_html_file(
    html_path: Path,
    summary_path: Path,
    label: str,
    required_markers: list[str] | None = None,
) -> dict:
    if not html_path.exists():
        raise FileNotFoundError(f"html missing: {html_path}")
    if not summary_path.exists():
        raise FileNotFoundError(f"summary missing: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or not summary:
        raise ValueError("summary must be a non-empty JSON object")
    html = html_path.read_text(encoding="utf-8", errors="replace")
    payload = assert_report_html_contract(summary, html, label, required_markers=required_markers)
    payload.update(
        {
            "html_path": str(html_path),
            "summary_path": str(summary_path),
        }
    )
    return payload


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Verify report HTML or report batch archives against expected summaries")
    parser.add_argument("--zip-path", type=Path)
    parser.add_argument("--expectations-path", type=Path)
    parser.add_argument("--html-path", type=Path)
    parser.add_argument("--summary-path", type=Path)
    parser.add_argument("--required-marker", action="append", default=[])
    parser.add_argument("--label", default="report contract")
    args = parser.parse_args()

    zip_mode = args.zip_path is not None or args.expectations_path is not None
    html_mode = args.html_path is not None or args.summary_path is not None
    if zip_mode == html_mode:
        print("choose exactly one mode: zip (--zip-path + --expectations-path) or html (--html-path + --summary-path)", file=sys.stderr)
        return 1

    try:
        if zip_mode:
            if args.zip_path is None or args.expectations_path is None:
                print("zip mode requires --zip-path and --expectations-path", file=sys.stderr)
                return 1
            if not args.zip_path.exists():
                print(f"zip missing: {args.zip_path}", file=sys.stderr)
                return 1
            if not args.expectations_path.exists():
                print(f"expectations missing: {args.expectations_path}", file=sys.stderr)
                return 1
            expected_reports = json.loads(args.expectations_path.read_text(encoding="utf-8"))
            if not isinstance(expected_reports, list) or not expected_reports:
                print("expectations must be a non-empty JSON array", file=sys.stderr)
                return 1
            with zipfile.ZipFile(args.zip_path) as archive:
                payload = assert_batch_archive_contract(archive, expected_reports, args.label)
        else:
            if args.html_path is None or args.summary_path is None:
                print("html mode requires --html-path and --summary-path", file=sys.stderr)
                return 1
            payload = verify_report_html_file(
                args.html_path,
                args.summary_path,
                args.label,
                required_markers=args.required_marker,
            )
    except Exception as exc:
        print(f"{args.label} verification failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
