from __future__ import annotations

from collections import defaultdict


BEHAVIOR_LABELS = {
    "read": "阅读",
    "reading": "阅读",
    "book": "书本",
    "lookbook": "阅读",
    "bookreading": "阅读",
    "看书": "阅读",
    "读书": "阅读",
    "write": "书写",
    "writing": "书写",
    "written": "书写",
    "写字": "书写",
    "hand": "举手",
    "handraising": "举手",
    "handraise": "举手",
    "raisehand": "举手",
    "raisinghand": "举手",
    "举手": "举手",
    "head": "人头",
    "heads": "人头",
    "humanhead": "人头",
    "人头": "人头",
    "bowhead": "低头",
    "低头": "低头",
    "raisehead": "抬头",
    "抬头": "抬头",
    "upright": "坐姿端正",
    "坐姿端正": "坐姿端正",
    "inclusion": "专注听讲",
    "listen": "专注听讲",
    "listening": "专注听讲",
    "lectureattention": "专注听讲",
    "专注听讲": "专注听讲",
    "听讲": "专注听讲",
    "sleep": "睡觉",
    "睡觉": "睡觉",
    "usingphone": "使用手机",
    "using_phone": "使用手机",
    "phone": "使用手机",
    "手机": "使用手机",
    "玩手机": "使用手机",
    "使用手机": "使用手机",
    "computer": "电脑",
    "电脑": "电脑",
    "patches": "课本区域",
    "课本区域": "课本区域",
    "guidingstudents": "巡视指导",
    "guide": "巡视指导",
    "巡视": "巡视指导",
    "巡视指导": "巡视指导",
    "lecture": "讲课",
    "讲课": "讲课",
    "teaching": "讲课",
    "observe": "观察学生",
    "observation": "观察学生",
    "观察": "观察学生",
    "观察学生": "观察学生",
}

POSITIVE_BEHAVIORS = {"举手", "专注听讲", "阅读", "书写", "坐姿端正", "讲课", "巡视指导"}


def normalize_lookup_key(value: str | None) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
        .replace("/", "")
        .replace("\\", "")
    )


def format_behavior_label(value: str | None) -> str:
    if not value:
        return "未标注行为"
    text = str(value).strip()
    lookup_key = normalize_lookup_key(text)
    if lookup_key in BEHAVIOR_LABELS:
        return BEHAVIOR_LABELS[lookup_key]
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return text
    return text.replace("_", " ").replace("-", " ")


def format_behavior_stats(stats: dict | None) -> dict[str, int]:
    merged: dict[str, int] = defaultdict(int)
    for key, value in (stats or {}).items():
        merged[format_behavior_label(str(key))] += int(value or 0)
    return dict(merged)
