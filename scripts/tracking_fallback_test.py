from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from backfill_tracking_metrics import DetectionRow, assign_track_ids as assign_backfill_track_ids
from tracking_fallback import TrackAssignmentState, assign_track_ids_for_frame


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_helper_does_not_reuse_a_track_twice_in_same_frame() -> None:
    state = TrackAssignmentState()
    seed = {"name": "seed"}
    assign_track_ids_for_frame(
        [(seed, (0.0, 0.0, 100.0, 100.0), 5)],
        frame_number=1,
        state=state,
    )

    explicit = {"name": "explicit"}
    missing = {"name": "missing"}
    assignments = assign_track_ids_for_frame(
        [
            (explicit, (2.0, 2.0, 102.0, 102.0), 5),
            (missing, (4.0, 4.0, 104.0, 104.0), None),
        ],
        frame_number=2,
        state=state,
    )

    assigned_ids = {item["name"]: track_id for item, track_id in assignments}
    assert_equal(assigned_ids["explicit"], 5, "explicit track should keep its tracker-provided id")
    assert_equal(assigned_ids["missing"], 6, "missing peer should receive a fresh id when the tracked id is already consumed in the frame")


def test_backfill_assign_track_ids_updates_only_missing_rows() -> None:
    rows = [
        DetectionRow(
            row_id=10,
            frame_number=1,
            timestamp=0.1,
            behavior="reading",
            confidence=0.8,
            track_id=3,
            bbox=(0.0, 0.0, 80.0, 80.0),
        ),
        DetectionRow(
            row_id=11,
            frame_number=2,
            timestamp=0.2,
            behavior="reading",
            confidence=0.82,
            track_id=None,
            bbox=(3.0, 3.0, 83.0, 83.0),
        ),
        DetectionRow(
            row_id=12,
            frame_number=2,
            timestamp=0.2,
            behavior="writing",
            confidence=0.77,
            track_id=8,
            bbox=(200.0, 200.0, 260.0, 260.0),
        ),
        DetectionRow(
            row_id=13,
            frame_number=3,
            timestamp=0.3,
            behavior="writing",
            confidence=0.79,
            track_id=None,
            bbox=(204.0, 204.0, 264.0, 264.0),
        ),
    ]

    assigned_rows, updates = assign_backfill_track_ids(rows)

    assert_equal(assigned_rows[0].track_id, 3, "existing backfill track ids should remain unchanged")
    assert_equal(assigned_rows[1].track_id, 3, "overlapping backfill row should inherit the active track id")
    assert_equal(assigned_rows[2].track_id, 8, "later explicit track id should remain unchanged")
    assert_equal(assigned_rows[3].track_id, 8, "matching row should inherit the later active track id")
    assert_equal(updates, [(3, 11), (8, 13)], "backfill updates should contain only rows that were missing track ids")


def test_helper_expires_stale_tracks_after_gap() -> None:
    state = TrackAssignmentState()
    original = {"name": "original"}
    assign_track_ids_for_frame(
        [(original, (0.0, 0.0, 80.0, 80.0), 4)],
        frame_number=1,
        state=state,
    )

    after_gap = {"name": "after_gap"}
    assignments = assign_track_ids_for_frame(
        [(after_gap, (2.0, 2.0, 82.0, 82.0), None)],
        frame_number=5,
        state=state,
    )

    assigned_ids = {item["name"]: track_id for item, track_id in assignments}
    assert_equal(assigned_ids["after_gap"], 5, "stale tracks should expire after the max frame gap instead of being reused")


def test_backfill_seeds_new_ids_above_later_explicit_track_ids() -> None:
    rows = [
        DetectionRow(
            row_id=20,
            frame_number=1,
            timestamp=0.1,
            behavior="reading",
            confidence=0.8,
            track_id=None,
            bbox=(0.0, 0.0, 40.0, 40.0),
        ),
        DetectionRow(
            row_id=21,
            frame_number=3,
            timestamp=0.3,
            behavior="reading",
            confidence=0.81,
            track_id=12,
            bbox=(200.0, 200.0, 240.0, 240.0),
        ),
        DetectionRow(
            row_id=22,
            frame_number=4,
            timestamp=0.4,
            behavior="reading",
            confidence=0.82,
            track_id=None,
            bbox=(300.0, 300.0, 340.0, 340.0),
        ),
    ]

    assigned_rows, updates = assign_backfill_track_ids(rows)

    assert_equal(assigned_rows[0].track_id, 13, "early fallback rows should avoid colliding with later explicit ids in the same task")
    assert_equal(assigned_rows[1].track_id, 12, "later explicit ids should remain unchanged")
    assert_equal(assigned_rows[2].track_id, 14, "subsequent fallback rows should continue from the seeded high-water mark")
    assert_equal(updates, [(13, 20), (14, 22)], "backfill updates should reflect the seeded new ids for missing rows")


def main() -> int:
    test_helper_does_not_reuse_a_track_twice_in_same_frame()
    test_backfill_assign_track_ids_updates_only_missing_rows()
    test_helper_expires_stale_tracks_after_gap()
    test_backfill_seeds_new_ids_above_later_explicit_track_ids()
    print("tracking_fallback tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
