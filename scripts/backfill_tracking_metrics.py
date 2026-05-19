from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Config
from classroom_app.core.summary_metrics import SummaryAccumulator, build_summary_payload
from tracking_fallback import TrackAssignmentState, assign_track_ids_for_frame
from utils.database import Database


@dataclass
class DetectionRow:
    row_id: int
    frame_number: int
    timestamp: float
    behavior: str
    confidence: float
    track_id: int | None
    bbox: tuple[float, float, float, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill track_id and tracking-aware summary metrics for historical video/webcam tasks.")
    parser.add_argument("--task-id", help="Only backfill a single task_id.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of tasks to process.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without writing to the database.")
    parser.add_argument("--force", action="store_true", help="Rebuild summaries even when display_metrics/derived_metrics already exist.")
    return parser.parse_args()


def fetch_candidate_tasks(conn: sqlite3.Connection, task_id: str | None, limit: int, force: bool) -> list[sqlite3.Row]:
    sql = """
        SELECT
            dr.task_id,
            dr.task_type,
            dr.file_name,
            dr.processed_frames,
            dr.total_frames,
            ds.average_confidence,
            ds.duration,
            ds.display_metrics,
            ds.derived_metrics
        FROM detection_records dr
        LEFT JOIN detection_summary ds ON ds.task_id = dr.task_id
        WHERE dr.task_type IN ('video', 'webcam')
    """
    params: list[Any] = []
    if task_id:
        sql += " AND dr.task_id = ?"
        params.append(task_id)
    if not force:
        sql += """
            AND (
                ds.task_id IS NULL
                OR ds.display_metrics IS NULL
                OR ds.derived_metrics IS NULL
                OR EXISTS (SELECT 1 FROM student_detections sd WHERE sd.task_id = dr.task_id AND sd.track_id IS NULL)
                OR EXISTS (SELECT 1 FROM teacher_detections td WHERE td.task_id = dr.task_id AND td.track_id IS NULL)
            )
        """
    sql += " ORDER BY dr.created_at DESC"
    if limit and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    return list(conn.execute(sql, params).fetchall())


def fetch_detections(conn: sqlite3.Connection, table_name: str, task_id: str) -> list[DetectionRow]:
    rows = conn.execute(
        f"""
        SELECT id, frame_number, timestamp, behavior, confidence, track_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2
        FROM {table_name}
        WHERE task_id = ?
        ORDER BY COALESCE(frame_number, 0), id
        """,
        (task_id,),
    ).fetchall()
    detections: list[DetectionRow] = []
    for row in rows:
        detections.append(
            DetectionRow(
                row_id=int(row["id"]),
                frame_number=int(row["frame_number"] or 0),
                timestamp=float(row["timestamp"] or 0.0),
                behavior=str(row["behavior"] or ""),
                confidence=float(row["confidence"] or 0.0),
                track_id=int(row["track_id"]) if row["track_id"] is not None else None,
                bbox=(
                    float(row["bbox_x1"] or 0.0),
                    float(row["bbox_y1"] or 0.0),
                    float(row["bbox_x2"] or 0.0),
                    float(row["bbox_y2"] or 0.0),
                ),
            )
        )
    return detections


def assign_track_ids(rows: list[DetectionRow]) -> tuple[list[DetectionRow], list[tuple[int, int]]]:
    if not rows:
        return rows, []
    # Seed from the max explicit id in the whole task so early fallback rows never collide
    # with tracker-provided ids that appear in later frames.
    state = TrackAssignmentState(next_track_id=max((row.track_id or 0 for row in rows), default=0) + 1)
    updates: list[tuple[int, int]] = []
    rows_by_frame: dict[int, list[DetectionRow]] = defaultdict(list)
    for row in rows:
        rows_by_frame[row.frame_number].append(row)

    for frame_number in sorted(rows_by_frame):
        frame_rows = rows_by_frame[frame_number]
        assignments = assign_track_ids_for_frame(
            [(row, row.bbox, row.track_id) for row in frame_rows],
            frame_number=frame_number,
            state=state,
        )
        for row, track_id in assignments:
            had_track_id = row.track_id is not None
            row.track_id = int(track_id)
            if not had_track_id:
                updates.append((int(track_id), row.row_id))
    return rows, updates


def build_summary_from_rows(task_type: str, student_rows: list[DetectionRow], teacher_rows: list[DetectionRow], *, processed_frames: int, total_frames: int, average_confidence: float, duration: float) -> dict[str, Any]:
    accumulator = SummaryAccumulator(task_type)
    rows_by_frame: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"student": [], "teacher": []})
    for source, rows in (("student", student_rows), ("teacher", teacher_rows)):
        for row in rows:
            rows_by_frame[row.frame_number][source].append(
                {
                    "behavior": row.behavior,
                    "confidence": row.confidence,
                    "track_id": row.track_id,
                }
            )
    for frame_number in sorted(rows_by_frame):
        grouped = rows_by_frame[frame_number]
        accumulator.update_frame(
            frame_number,
            student_detections=grouped["student"],
            teacher_detections=grouped["teacher"],
        )
    payload = accumulator.build_payload(
        processed_frames=processed_frames,
        total_frames=total_frames,
        duration=duration,
    )
    if average_confidence > 0:
        payload["average_confidence"] = average_confidence
    payload["total_detections"] = len(student_rows) + len(teacher_rows)
    payload["display_metrics"] = build_summary_payload(
        task_type=task_type,
        student_behavior_stats=payload["student_behavior_stats"],
        teacher_behavior_stats=payload["teacher_behavior_stats"],
        total_detections=payload["total_detections"],
        average_confidence=payload["average_confidence"],
        duration=duration,
        processed_frames=processed_frames,
        total_frames=total_frames,
        derived_metrics=payload["derived_metrics"],
    )["display_metrics"]
    return payload


def save_summary(conn: sqlite3.Connection, task_id: str, summary: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO detection_summary (
            task_id,
            student_behavior_stats,
            teacher_behavior_stats,
            total_detections,
            average_confidence,
            duration,
            display_metrics,
            derived_metrics
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            student_behavior_stats = excluded.student_behavior_stats,
            teacher_behavior_stats = excluded.teacher_behavior_stats,
            total_detections = excluded.total_detections,
            average_confidence = excluded.average_confidence,
            duration = excluded.duration,
            display_metrics = excluded.display_metrics,
            derived_metrics = excluded.derived_metrics
        """,
        (
            task_id,
            json.dumps(summary.get("student_behavior_stats", {}), ensure_ascii=False),
            json.dumps(summary.get("teacher_behavior_stats", {}), ensure_ascii=False),
            int(summary.get("total_detections", 0) or 0),
            float(summary.get("average_confidence", 0.0) or 0.0),
            float(summary.get("duration", 0.0) or 0.0),
            json.dumps(summary.get("display_metrics", {}), ensure_ascii=False),
            json.dumps(summary.get("derived_metrics", {}), ensure_ascii=False),
        ),
    )


def main() -> int:
    args = parse_args()
    Database()  # Ensure schema is current before backfill.
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    tasks = fetch_candidate_tasks(conn, args.task_id, args.limit, args.force)
    if not tasks:
        print("No matching tasks require backfill.")
        conn.close()
        return 0

    updated_tasks = 0
    updated_detection_rows = 0
    try:
        for task in tasks:
            task_id = str(task["task_id"])
            task_type = str(task["task_type"])
            student_rows, student_updates = assign_track_ids(fetch_detections(conn, "student_detections", task_id))
            teacher_rows, teacher_updates = assign_track_ids(fetch_detections(conn, "teacher_detections", task_id))
            processed_frames = int(task["processed_frames"] or 0)
            if processed_frames <= 0:
                processed_frames = len({row.frame_number for row in student_rows + teacher_rows})
            total_frames = int(task["total_frames"] or 0) or processed_frames
            confidences = [row.confidence for row in student_rows + teacher_rows if row.confidence > 0]
            average_confidence = float(task["average_confidence"] or 0.0)
            if average_confidence <= 0 and confidences:
                average_confidence = sum(confidences) / len(confidences)
            duration = float(task["duration"] or 0.0)
            if duration <= 0:
                duration = max((row.timestamp for row in student_rows + teacher_rows), default=0.0)
            summary = build_summary_from_rows(
                task_type,
                student_rows,
                teacher_rows,
                processed_frames=processed_frames,
                total_frames=total_frames,
                average_confidence=average_confidence,
                duration=duration,
            )
            print(f"[{task_type}] {task_id}: student_updates={len(student_updates)} teacher_updates={len(teacher_updates)} total_detections={summary['total_detections']}")
            if args.dry_run:
                continue
            conn.executemany("UPDATE student_detections SET track_id = ? WHERE id = ?", student_updates)
            conn.executemany("UPDATE teacher_detections SET track_id = ? WHERE id = ?", teacher_updates)
            save_summary(conn, task_id, summary)
            conn.commit()
            updated_tasks += 1
            updated_detection_rows += len(student_updates) + len(teacher_updates)
    finally:
        conn.close()

    if args.dry_run:
        print(f"Dry run complete. Candidate tasks: {len(tasks)}")
    else:
        print(f"Backfill complete. Updated tasks: {updated_tasks}, updated detection rows: {updated_detection_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
