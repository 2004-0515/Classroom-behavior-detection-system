from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from backfill_tracking_metrics import DetectionRow, build_summary_from_rows
from classroom_app.core.summary_metrics import SummaryAccumulator


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_close(actual: float, expected: float, message: str, *, tolerance: float = 1e-9) -> None:
    if abs(float(actual) - float(expected)) > tolerance:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_backfill_summary_uses_track_level_metrics() -> None:
    student_rows = [
        DetectionRow(
            row_id=1,
            frame_number=1,
            timestamp=0.1,
            behavior="reading",
            confidence=0.8,
            track_id=7,
            bbox=(0.0, 0.0, 50.0, 50.0),
        ),
        DetectionRow(
            row_id=2,
            frame_number=2,
            timestamp=0.2,
            behavior="reading",
            confidence=0.82,
            track_id=7,
            bbox=(2.0, 2.0, 52.0, 52.0),
        ),
        DetectionRow(
            row_id=3,
            frame_number=2,
            timestamp=0.2,
            behavior="writing",
            confidence=0.91,
            track_id=8,
            bbox=(100.0, 100.0, 150.0, 150.0),
        ),
    ]
    teacher_rows = [
        DetectionRow(
            row_id=4,
            frame_number=1,
            timestamp=0.1,
            behavior="head",
            confidence=0.88,
            track_id=3,
            bbox=(200.0, 200.0, 240.0, 240.0),
        ),
        DetectionRow(
            row_id=5,
            frame_number=2,
            timestamp=0.2,
            behavior="head",
            confidence=0.9,
            track_id=3,
            bbox=(202.0, 202.0, 242.0, 242.0),
        ),
    ]

    summary = build_summary_from_rows(
        "video",
        student_rows,
        teacher_rows,
        processed_frames=4,
        total_frames=6,
        average_confidence=0.86,
        duration=3.2,
    )

    derived = summary["derived_metrics"]
    display = summary["display_metrics"]

    assert_equal(derived["metric_mode"], "tracking", "video summaries should use tracking metrics")
    assert_equal(derived["unique_targets"], 3, "repeated track ids across frames should count as one unique target")
    assert_equal(derived["peak_concurrency"], 3, "peak concurrency should count unique track keys in the busiest frame")
    assert_equal(derived["track_source_breakdown"], {"student": 2, "teacher": 1}, "track source breakdown should stay source-aware")
    assert_equal(
        derived["behavior_chart_groups"],
        {"student": {"阅读": 1, "书写": 1}, "teacher": {"人头": 1}},
        "tracking charts should count dominant behaviors by track rather than raw detections",
    )
    assert_close(derived["coverage_ratio"], 0.5, "coverage ratio should use active frames over processed frames")
    assert_equal(display["metric_mode"], "tracking", "display metrics should remain in tracking mode")
    assert_equal(summary["total_detections"], 5, "summary should still retain raw detection counts alongside track metrics")


def test_summary_accumulator_dedupes_peak_concurrency_for_same_track_in_frame() -> None:
    accumulator = SummaryAccumulator("video")
    accumulator.update_frame(
        1,
        student_detections=[
            {"behavior": "reading", "confidence": 0.8, "track_id": 5},
            {"behavior": "writing", "confidence": 0.78, "track_id": 5},
        ],
        teacher_detections=[],
    )

    payload = accumulator.build_payload(processed_frames=1, total_frames=1, duration=0.1)
    derived = payload["derived_metrics"]

    assert_equal(derived["unique_targets"], 1, "duplicate same-frame hits for one track should not inflate unique targets")
    assert_equal(derived["peak_concurrency"], 1, "duplicate same-frame hits for one track should not inflate peak concurrency")
    assert_equal(payload["total_detections"], 2, "raw detection count should remain unchanged even when track metrics dedupe")


def test_summary_keeps_same_numeric_track_id_separate_by_source() -> None:
    accumulator = SummaryAccumulator("video")
    accumulator.update_frame(
        1,
        student_detections=[{"behavior": "reading", "confidence": 0.8, "track_id": 1}],
        teacher_detections=[{"behavior": "head", "confidence": 0.9, "track_id": 1}],
    )

    payload = accumulator.build_payload(processed_frames=1, total_frames=1, duration=0.1)
    derived = payload["derived_metrics"]

    assert_equal(derived["unique_targets"], 2, "student and teacher tracks with the same numeric id should remain distinct")
    assert_equal(derived["peak_concurrency"], 2, "same numeric ids from different sources should both contribute to concurrency")
    assert_equal(derived["track_source_breakdown"], {"student": 1, "teacher": 1}, "source breakdown should count each source independently")


def main() -> int:
    test_backfill_summary_uses_track_level_metrics()
    test_summary_accumulator_dedupes_peak_concurrency_for_same_track_in_frame()
    test_summary_keeps_same_numeric_track_id_separate_by_source()
    print("summary_metrics tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
