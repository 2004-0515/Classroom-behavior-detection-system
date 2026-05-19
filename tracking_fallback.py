from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TRACK_ID_FALLBACK_IOU = 0.45
TRACK_ID_FALLBACK_MAX_FRAME_GAP = 2


@dataclass
class ActiveTrackState:
    bbox: tuple[float, float, float, float]
    frame_number: int


@dataclass
class TrackAssignmentState:
    next_track_id: int = 1
    active_tracks: dict[int, ActiveTrackState] = field(default_factory=dict)


def bbox_iou(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - inter
    return inter / union if union > 0 else 0.0


def assign_track_ids_for_frame(
    frame_items: list[tuple[Any, tuple[float, float, float, float], int | None]],
    *,
    frame_number: int,
    state: TrackAssignmentState,
    iou_threshold: float = TRACK_ID_FALLBACK_IOU,
    max_frame_gap: int = TRACK_ID_FALLBACK_MAX_FRAME_GAP,
) -> list[tuple[Any, int]]:
    active_tracks = {
        int(track_id): track_state
        for track_id, track_state in state.active_tracks.items()
        if frame_number - int(track_state.frame_number) <= max_frame_gap
    }
    next_track_id = int(state.next_track_id)
    used_track_ids: set[int] = set()
    assignments: list[tuple[Any, int]] = []

    for item, bbox, track_id in frame_items:
        if track_id is None:
            continue
        assigned_track_id = int(track_id)
        active_tracks[assigned_track_id] = ActiveTrackState(bbox=bbox, frame_number=frame_number)
        used_track_ids.add(assigned_track_id)
        next_track_id = max(next_track_id, assigned_track_id + 1)
        assignments.append((item, assigned_track_id))

    for item, bbox, track_id in frame_items:
        if track_id is not None:
            continue
        best_track_id = None
        best_iou = 0.0
        for active_track_id, track_state in active_tracks.items():
            if active_track_id in used_track_ids:
                continue
            overlap = bbox_iou(track_state.bbox, bbox)
            if overlap >= iou_threshold and overlap > best_iou:
                best_track_id = active_track_id
                best_iou = overlap
        if best_track_id is None:
            best_track_id = next_track_id
            next_track_id += 1
        active_tracks[int(best_track_id)] = ActiveTrackState(bbox=bbox, frame_number=frame_number)
        used_track_ids.add(int(best_track_id))
        assignments.append((item, int(best_track_id)))

    state.active_tracks = active_tracks
    state.next_track_id = next_track_id
    return assignments
