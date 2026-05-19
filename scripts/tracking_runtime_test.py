from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.detector import TRACK_ID_FALLBACK_MAX_FRAME_GAP, TrackingRuntime


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def make_detection(*, bbox: list[float], track_id: int | None) -> dict:
    return {
        "behavior": "hand-raising",
        "confidence": 0.72,
        "bbox": bbox,
        "track_id": track_id,
    }


def test_reuses_existing_track_for_missing_tracker_id() -> None:
    runtime = TrackingRuntime("", "", 0.25, 0.45, 640)
    runtime._frame_index = 1
    seeded = [make_detection(bbox=[0.0, 0.0, 100.0, 100.0], track_id=11)]
    runtime._assign_fallback_track_ids("student", seeded)

    runtime._frame_index = 2
    missing = [make_detection(bbox=[4.0, 4.0, 104.0, 104.0], track_id=None)]
    runtime._assign_fallback_track_ids("student", missing)

    assert_equal(missing[0]["track_id"], 11, "matching bbox should inherit the active track id")


def test_assigns_new_track_after_gap_expires() -> None:
    runtime = TrackingRuntime("", "", 0.25, 0.45, 640)
    runtime._frame_index = 1
    seeded = [make_detection(bbox=[0.0, 0.0, 100.0, 100.0], track_id=4)]
    runtime._assign_fallback_track_ids("student", seeded)

    runtime._frame_index = 1 + TRACK_ID_FALLBACK_MAX_FRAME_GAP + 1
    missing = [make_detection(bbox=[1.0, 1.0, 101.0, 101.0], track_id=None)]
    runtime._assign_fallback_track_ids("student", missing)

    assert_equal(missing[0]["track_id"], 5, "expired tracks should not be reused after the max frame gap")


def test_assigns_new_track_when_overlap_is_too_small() -> None:
    runtime = TrackingRuntime("", "", 0.25, 0.45, 640)
    runtime._frame_index = 1
    seeded = [make_detection(bbox=[0.0, 0.0, 100.0, 100.0], track_id=8)]
    runtime._assign_fallback_track_ids("student", seeded)

    runtime._frame_index = 2
    missing = [make_detection(bbox=[140.0, 140.0, 240.0, 240.0], track_id=None)]
    runtime._assign_fallback_track_ids("student", missing)

    assert_equal(missing[0]["track_id"], 9, "low-overlap detections should start a new track id")


def test_student_and_teacher_tracks_remain_isolated() -> None:
    runtime = TrackingRuntime("", "", 0.25, 0.45, 640)
    runtime._frame_index = 1
    runtime._assign_fallback_track_ids("student", [make_detection(bbox=[0.0, 0.0, 60.0, 60.0], track_id=1)])
    runtime._assign_fallback_track_ids("teacher", [make_detection(bbox=[200.0, 200.0, 260.0, 260.0], track_id=1)])

    runtime._frame_index = 2
    student_missing = [make_detection(bbox=[2.0, 2.0, 62.0, 62.0], track_id=None)]
    teacher_missing = [make_detection(bbox=[202.0, 202.0, 262.0, 262.0], track_id=None)]
    runtime._assign_fallback_track_ids("student", student_missing)
    runtime._assign_fallback_track_ids("teacher", teacher_missing)

    assert_equal(student_missing[0]["track_id"], 1, "student track namespace should reuse only student tracks")
    assert_equal(teacher_missing[0]["track_id"], 1, "teacher track namespace should reuse only teacher tracks")


def test_runtime_preserves_explicit_track_ids_in_mixed_frame() -> None:
    runtime = TrackingRuntime("", "", 0.25, 0.45, 640)
    runtime._frame_index = 1
    detections = [
        make_detection(bbox=[0.0, 0.0, 100.0, 100.0], track_id=5),
        make_detection(bbox=[3.0, 3.0, 103.0, 103.0], track_id=None),
    ]

    runtime._assign_fallback_track_ids("student", detections)

    assert_equal(detections[0]["track_id"], 5, "runtime adapter should keep tracker-provided ids unchanged")
    assert_equal(detections[1]["track_id"], 6, "runtime adapter should give the missing peer a fresh id when the explicit id is already consumed")


def main() -> int:
    test_reuses_existing_track_for_missing_tracker_id()
    test_assigns_new_track_after_gap_expires()
    test_assigns_new_track_when_overlap_is_too_small()
    test_student_and_teacher_tracks_remain_isolated()
    test_runtime_preserves_explicit_track_ids_in_mixed_frame()
    print("tracking_runtime tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
