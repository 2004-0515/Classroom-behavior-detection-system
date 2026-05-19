from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from classroom_app.core.behavior_labels import POSITIVE_BEHAVIORS, format_behavior_label, format_behavior_stats


TRACKING_TASK_TYPES = {"video", "webcam"}
TRACKING_SUMMARY_VERSION = 2


def _format_count(value: int | float) -> str:
    return f"{int(value or 0)}"


def _format_decimal(value: int | float, digits: int = 1) -> str:
    return f"{float(value or 0.0):.{digits}f}"


def _format_percent(ratio: float) -> str:
    return f"{float(ratio or 0.0) * 100:.1f}%"


def _sorted_items(stats: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(stats.items(), key=lambda item: (-int(item[1] or 0), item[0]))


def _top_behavior_items(stats: dict[str, int], *, limit: int, basis: str) -> list[dict[str, Any]]:
    items = []
    for label, value in _sorted_items(stats)[:limit]:
        items.append(
            {
                "label": label,
                "value": int(value or 0),
                "basis": basis,
                "formatted": f"{int(value or 0)} {'个轨迹' if basis == 'track' else '次检测'}",
            }
        )
    return items


def _merge_group_counts(student_stats: dict[str, int], teacher_stats: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = defaultdict(int)
    for label, value in list(student_stats.items()) + list(teacher_stats.items()):
        merged[label] += int(value or 0)
    return dict(merged)


def _count_positive_ratio(student_stats: dict[str, int], teacher_stats: dict[str, int]) -> float:
    merged = _merge_group_counts(student_stats, teacher_stats)
    total = sum(merged.values())
    positive = sum(value for label, value in merged.items() if label in POSITIVE_BEHAVIORS)
    return (positive / total) if total else 0.0


@dataclass
class TrackRecord:
    source: str
    track_id: int
    first_frame: int
    last_frame: int
    hits: int = 0
    confidence_sum: float = 0.0
    behavior_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def touch(self, behavior: str, confidence: float, frame_number: int) -> None:
        if self.hits == 0:
            self.first_frame = frame_number
        self.last_frame = frame_number
        self.hits += 1
        self.confidence_sum += float(confidence or 0.0)
        self.behavior_counts[behavior] += 1

    @property
    def dominant_behavior(self) -> str:
        if not self.behavior_counts:
            return "未标注行为"
        return _sorted_items(dict(self.behavior_counts))[0][0]

    @property
    def average_confidence(self) -> float:
        return self.confidence_sum / self.hits if self.hits else 0.0

    def as_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "track_id": int(self.track_id),
            "first_frame": int(self.first_frame),
            "last_frame": int(self.last_frame),
            "span_frames": int(self.last_frame - self.first_frame + 1),
            "hits": int(self.hits),
            "dominant_behavior": self.dominant_behavior,
            "average_confidence": float(self.average_confidence),
        }


class SummaryAccumulator:
    def __init__(self, task_type: str):
        self.task_type = str(task_type or "")
        self.student_behavior_stats: dict[str, int] = defaultdict(int)
        self.teacher_behavior_stats: dict[str, int] = defaultdict(int)
        self.total_detections = 0
        self.confidence_sum = 0.0
        self.active_frames: set[int] = set()
        self.frame_track_keys: dict[int, set[str]] = {}
        self.track_records: dict[str, TrackRecord] = {}

    def update_frame(self, frame_number: int, *, student_detections: list[dict[str, Any]], teacher_detections: list[dict[str, Any]]) -> None:
        frame_number = int(frame_number or 0)
        track_keys: set[str] = set()
        frame_has_detection = False

        for source, detections, bucket in (
            ("student", student_detections or [], self.student_behavior_stats),
            ("teacher", teacher_detections or [], self.teacher_behavior_stats),
        ):
            for detection in detections:
                behavior_label = format_behavior_label(detection.get("behavior"))
                confidence = float(detection.get("confidence") or 0.0)
                bucket[behavior_label] += 1
                self.total_detections += 1
                self.confidence_sum += confidence
                frame_has_detection = True

                track_id = detection.get("track_id")
                if track_id is None:
                    continue
                track_key = f"{source}:{int(track_id)}"
                track_keys.add(track_key)
                record = self.track_records.get(track_key)
                if record is None:
                    record = TrackRecord(source=source, track_id=int(track_id), first_frame=frame_number, last_frame=frame_number)
                    self.track_records[track_key] = record
                record.touch(behavior_label, confidence, frame_number)

        if frame_has_detection:
            self.active_frames.add(frame_number)
        if track_keys:
            self.frame_track_keys[frame_number] = track_keys

    def build_payload(self, *, processed_frames: int, total_frames: int, duration: float) -> dict[str, Any]:
        student_stats = dict(self.student_behavior_stats)
        teacher_stats = dict(self.teacher_behavior_stats)
        average_confidence = (self.confidence_sum / self.total_detections) if self.total_detections else 0.0
        derived_metrics = build_derived_metrics(
            task_type=self.task_type,
            student_stats=student_stats,
            teacher_stats=teacher_stats,
            total_detections=self.total_detections,
            average_confidence=average_confidence,
            processed_frames=processed_frames,
            total_frames=total_frames,
            active_frames=len(self.active_frames),
            frame_track_keys=self.frame_track_keys,
            track_records=self.track_records,
        )
        return build_summary_payload(
            task_type=self.task_type,
            student_behavior_stats=student_stats,
            teacher_behavior_stats=teacher_stats,
            total_detections=self.total_detections,
            average_confidence=average_confidence,
            duration=duration,
            processed_frames=processed_frames,
            total_frames=total_frames,
            derived_metrics=derived_metrics,
        )


def build_derived_metrics(
    *,
    task_type: str,
    student_stats: dict[str, int],
    teacher_stats: dict[str, int],
    total_detections: int,
    average_confidence: float,
    processed_frames: int,
    total_frames: int,
    active_frames: int,
    frame_track_keys: dict[int, set[str]] | None = None,
    track_records: dict[str, TrackRecord] | None = None,
) -> dict[str, Any]:
    metric_mode = "tracking" if task_type in TRACKING_TASK_TYPES else "counting"
    track_records = track_records or {}
    frame_track_keys = frame_track_keys or {}
    frame_behavior_counts = _merge_group_counts(student_stats, teacher_stats)

    derived = {
        "summary_version": TRACKING_SUMMARY_VERSION,
        "metric_mode": metric_mode,
        "total_detections": int(total_detections or 0),
        "average_confidence": float(average_confidence or 0.0),
        "processed_frames": int(processed_frames or 0),
        "total_frames": int(total_frames or 0),
        "active_frames": int(active_frames or 0),
        "coverage_ratio": (float(active_frames or 0) / float(processed_frames)) if processed_frames else 0.0,
        "dominant_behaviors_by_frame": _top_behavior_items(frame_behavior_counts, limit=4, basis="frame"),
        "behavior_chart_groups": {
            "student": format_behavior_stats(student_stats),
            "teacher": format_behavior_stats(teacher_stats),
        },
    }

    if metric_mode == "tracking":
        track_behavior_counts: dict[str, int] = defaultdict(int)
        chart_student: dict[str, int] = defaultdict(int)
        chart_teacher: dict[str, int] = defaultdict(int)
        track_previews = []
        for record in sorted(track_records.values(), key=lambda item: (-item.hits, item.source, item.track_id)):
            dominant_behavior = record.dominant_behavior
            track_behavior_counts[dominant_behavior] += 1
            if record.source == "teacher":
                chart_teacher[dominant_behavior] += 1
            else:
                chart_student[dominant_behavior] += 1
            if len(track_previews) < 8:
                track_previews.append(record.as_payload())
        derived.update(
            {
                "unique_targets": len(track_records),
                "peak_concurrency": max((len(keys) for keys in frame_track_keys.values()), default=0),
                "dominant_behaviors_by_track": _top_behavior_items(dict(track_behavior_counts), limit=4, basis="track"),
                "track_preview": track_previews,
                "behavior_chart_groups": {
                    "student": dict(chart_student),
                    "teacher": dict(chart_teacher),
                },
                "track_source_breakdown": {
                    "student": sum(1 for item in track_records.values() if item.source == "student"),
                    "teacher": sum(1 for item in track_records.values() if item.source == "teacher"),
                },
            }
        )
    else:
        derived.update(
            {
                "unique_targets": int(total_detections or 0),
                "peak_concurrency": int(total_detections or 0),
                "dominant_behaviors_by_track": _top_behavior_items(frame_behavior_counts, limit=4, basis="frame"),
                "track_preview": [],
                "track_source_breakdown": {
                    "student": sum(student_stats.values()),
                    "teacher": sum(teacher_stats.values()),
                },
            }
        )

    return derived


def build_display_metrics(
    *,
    task_type: str,
    total_detections: int,
    average_confidence: float,
    duration: float,
    processed_frames: int,
    total_frames: int,
    student_behavior_stats: dict[str, int],
    teacher_behavior_stats: dict[str, int],
    derived_metrics: dict[str, Any],
) -> dict[str, Any]:
    metric_mode = derived_metrics.get("metric_mode") or ("tracking" if task_type in TRACKING_TASK_TYPES else "counting")
    top_behaviors = list(
        derived_metrics.get("dominant_behaviors_by_track")
        if metric_mode == "tracking"
        else derived_metrics.get("dominant_behaviors_by_frame")
        or []
    )
    top_line = "、".join(f'{item["label"]}{item["formatted"]}' for item in top_behaviors[:3]) if top_behaviors else "当前行为分布仍在形成"
    confidence_text = f"{float(average_confidence or 0.0) * 100:.1f}%"
    duration_text = f"{float(duration or 0.0):.1f} 秒"
    positive_ratio = _count_positive_ratio(student_behavior_stats, teacher_behavior_stats)

    if metric_mode == "tracking":
        unique_targets = int(derived_metrics.get("unique_targets") or 0)
        peak_concurrency = int(derived_metrics.get("peak_concurrency") or 0)
        active_frames = int(derived_metrics.get("active_frames") or 0)
        coverage_ratio = float(derived_metrics.get("coverage_ratio") or 0.0)
        cards = [
            {"key": "unique_targets", "label": "独立目标数", "value": unique_targets, "formatted": f"{_format_count(unique_targets)} 个", "accent": True},
            {"key": "peak_concurrency", "label": "峰值同屏目标", "value": peak_concurrency, "formatted": f"{_format_count(peak_concurrency)} 个"},
            {"key": "active_frames", "label": "有效检测帧", "value": active_frames, "formatted": f"{_format_count(active_frames)} 帧"},
            {"key": "coverage_ratio", "label": "有效帧覆盖率", "value": coverage_ratio, "formatted": _format_percent(coverage_ratio)},
        ]
        title = "跟踪覆盖稳定" if unique_targets >= 8 and coverage_ratio >= 0.45 else "已形成有效轨迹摘要" if unique_targets > 0 else "等待有效轨迹"
        highlight_text = (
            f"本次任务累计跟踪 {_format_count(unique_targets)} 个独立目标，峰值同屏 {_format_count(peak_concurrency)} 个，"
            f"有效帧 {_format_count(active_frames)} 帧，覆盖率 {_format_percent(coverage_ratio)}。"
            f" 累计检测 {_format_count(total_detections)} 次，平均置信度 {confidence_text}。"
        )
        history_text = f"亮点：独立目标 {_format_count(unique_targets)} 个，峰值同屏 {_format_count(peak_concurrency)} 个"
        tone_label = "轨迹摘要"
        lead = (
            f"这里展示的是{ '视频' if task_type == 'video' else '实时巡检' }跟踪结果。"
            f" 本次任务累计跟踪 {_format_count(unique_targets)} 个独立目标，峰值同屏 {_format_count(peak_concurrency)} 个，"
            f"有效帧覆盖率 {_format_percent(coverage_ratio)}，累计检测 {_format_count(total_detections)} 次。"
        )
        recommendation_title = "适合讲解连续画面稳定性" if unique_targets > 0 else "建议先生成更多有效轨迹"
        recommendation_text = (
            f"轨迹主行为以 {top_line} 为主。建议结合结果视频说明独立目标、峰值同屏和覆盖率，"
            f"把累计检测次数作为次级补充指标。"
        )
    else:
        cards = [
            {"key": "total_detections", "label": "总检测数", "value": total_detections, "formatted": _format_count(total_detections), "accent": True},
            {"key": "average_confidence", "label": "平均置信度", "value": average_confidence, "formatted": confidence_text},
            {"key": "duration", "label": "处理时长", "value": duration, "formatted": duration_text},
            {"key": "processed_frames", "label": "处理帧数", "value": processed_frames, "formatted": f"{_format_count(processed_frames)} 帧"},
        ]
        title = "检测覆盖较高" if total_detections >= 50 else "结果可用于展示" if total_detections > 0 else "等待有效结果"
        highlight_text = (
            f"本次任务共识别 {_format_count(total_detections)} 个目标，平均置信度 {confidence_text}，"
            f"处理时长 {duration_text}。主要行为为 {top_line}。"
        )
        history_text = f"亮点：{top_line}" if top_behaviors else f"亮点：共识别 {_format_count(total_detections)} 个目标"
        tone_label = "统计摘要"
        lead = {
            "image": "这里展示的是单图检测结果，适合对照原图讲解识别框与行为标签。",
            "batch": "这里展示的是批量检测汇总，适合说明多张素材在统一参数下的输出一致性。",
        }.get(task_type, "这里展示的是当前检测结果。")
        lead = f"{lead} 本次任务共识别 {_format_count(total_detections)} 个目标，平均置信度 {confidence_text}，处理时长 {duration_text}。"
        recommendation_title = "适合答辩讲解" if total_detections > 0 else "建议先生成有效结果"
        recommendation_text = f"主要行为为 {top_line}。建议结合原始图像或批量样本，对照说明识别效果和输出一致性。"

    behavior_sentence = f"主要行为为 {top_line}。" if top_behaviors else "当前还没有足够的行为分布摘要。"
    recommendation_suffix = "当前整体课堂状态偏积极，适合强调参与度和识别稳定性。" if positive_ratio >= 0.55 else "当前可突出系统对复杂课堂状态的持续发现能力。"
    short_speech = f"{lead} {behavior_sentence}"
    long_speech = f"{lead} {behavior_sentence} {recommendation_suffix}"

    return {
        "metric_mode": metric_mode,
        "cards": cards,
        "primary_stat": cards[0] if cards else None,
        "top_behaviors": top_behaviors,
        "behavior_charts": derived_metrics.get("behavior_chart_groups") or {},
        "highlight": {
            "title": title,
            "text": highlight_text,
            "history_text": history_text,
            "tone_label": tone_label,
        },
        "narrative": {
            "lead": lead,
            "behavior_text": behavior_sentence,
            "recommendation_title": recommendation_title,
            "recommendation_text": f"{recommendation_text} {recommendation_suffix}",
            "short_speech": short_speech,
            "long_speech": long_speech,
        },
        "history_sort_value": int(derived_metrics.get("unique_targets") or 0) if metric_mode == "tracking" else int(total_detections or 0),
    }


def build_summary_payload(
    *,
    task_type: str,
    student_behavior_stats: dict[str, int],
    teacher_behavior_stats: dict[str, int],
    total_detections: int,
    average_confidence: float,
    duration: float,
    processed_frames: int,
    total_frames: int,
    derived_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    student_stats = format_behavior_stats(student_behavior_stats)
    teacher_stats = format_behavior_stats(teacher_behavior_stats)
    derived = dict(
        derived_metrics
        or build_derived_metrics(
            task_type=task_type,
            student_stats=student_stats,
            teacher_stats=teacher_stats,
            total_detections=total_detections,
            average_confidence=average_confidence,
            processed_frames=processed_frames,
            total_frames=total_frames,
            active_frames=processed_frames if total_detections else 0,
        )
    )
    display = build_display_metrics(
        task_type=task_type,
        total_detections=total_detections,
        average_confidence=average_confidence,
        duration=duration,
        processed_frames=processed_frames,
        total_frames=total_frames,
        student_behavior_stats=student_stats,
        teacher_behavior_stats=teacher_stats,
        derived_metrics=derived,
    )
    return {
        "student_behavior_stats": student_stats,
        "teacher_behavior_stats": teacher_stats,
        "total_detections": int(total_detections or 0),
        "average_confidence": float(average_confidence or 0.0),
        "duration": float(duration or 0.0),
        "processed_frames": int(processed_frames or 0),
        "total_frames": int(total_frames or 0),
        "derived_metrics": derived,
        "display_metrics": display,
    }
