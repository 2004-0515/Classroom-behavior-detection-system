from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from verify_report_archive import assert_batch_archive_contract, build_archive_expectations, verify_report_html_file


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def sample_summary() -> dict:
    return {
        "display_metrics": {
            "cards": [
                {"label": "总检测数", "formatted": "8"},
                {"label": "平均置信度", "formatted": "77.7%"},
                {"label": "处理时长", "formatted": "0.5 秒"},
                {"label": "处理帧数", "formatted": "1 帧"},
            ]
        }
    }


def sample_html() -> str:
    return """
    <html>
      <body>
        <div>课堂行为检测报告</div>
        <section>学生行为分析</section>
        <div class="report-toolbar">toolbar</div>
        <div class="preview-box">preview</div>
        <div class="analysis-grid">
          <span>总检测数</span><strong>8</strong>
          <span>平均置信度</span><strong>77.7%</strong>
          <span>处理时长</span><strong>0.5 秒</strong>
          <span>处理帧数</span><strong>1 帧</strong>
        </div>
      </body>
    </html>
    """


def test_verify_report_html_file_uses_required_markers() -> None:
    with tempfile.TemporaryDirectory(prefix="verify-report-html-") as temp_dir:
        root = Path(temp_dir)
        html_path = root / "report.html"
        summary_path = root / "summary.json"
        html_path.write_text(sample_html(), encoding="utf-8")
        summary_path.write_text(json.dumps(sample_summary(), ensure_ascii=False), encoding="utf-8")
        payload = verify_report_html_file(
            html_path,
            summary_path,
            "report html",
            required_markers=["report-toolbar", "preview-box", "analysis-grid"],
        )

    assert_equal(payload["metric_count"], 4, "html mode should verify the expected metric cards")
    assert_equal(payload["verified_metrics"][0]["label"], "总检测数", "verified metrics should preserve the summary labels")
    assert_equal(payload["required_markers"][-1], "analysis-grid", "required markers should be appended to the default markers")


def test_build_archive_expectations_supports_nested_paths() -> None:
    expectations = build_archive_expectations(
        [
            {
                "report_payload": {"report_filename": "report-a.html"},
                "summary_payload": sample_summary(),
            }
        ],
        report_filename_path="report_payload.report_filename",
        summary_path="summary_payload",
    )
    assert_equal(
        expectations,
        [{"report_filename": "report-a.html", "summary": sample_summary()}],
        "nested field paths should map into canonical archive expectations",
    )


def test_assert_batch_archive_contract_verifies_reports() -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("readme.txt", "report-a.html\n")
        archive.writestr("manifest.csv", "filename\nreport-a.html\n")
        archive.writestr("report-a.html", sample_html())

    with zipfile.ZipFile(io.BytesIO(archive_buffer.getvalue())) as archive:
        payload = assert_batch_archive_contract(
            archive,
            [{"report_filename": "report-a.html", "summary": sample_summary()}],
            "batch archive",
        )

    assert_equal(payload["report_count"], 1, "batch archive should verify every expected report")
    assert_equal(payload["verified_reports"], ["report-a.html"], "batch archive should report the verified filenames")


def main() -> int:
    test_verify_report_html_file_uses_required_markers()
    test_build_archive_expectations_supports_nested_paths()
    test_assert_batch_archive_contract_verifies_reports()
    print("verify_report_archive tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
