import test from "node:test";
import assert from "node:assert/strict";

import { compareHistoryTasks } from "./history.js";
import { buildTaskHighlight, getTopBehaviors } from "./summary.js";
import { buildBrowserWebcamTaskPayload } from "./task-payload.js";


test("getTopBehaviors prefers tracking display metrics and fills missing labels", () => {
    const summary = {
        display_metrics: {
            top_behaviors: [
                { raw_label: "reading", value: 4, formatted: "4次" },
                { label: "举手", value: 2, formatted: "2次" },
            ],
        },
        student_behavior_stats: { writing: 99 },
    };

    const result = getTopBehaviors(summary, 2, (raw) => `行为:${raw}`);

    assert.deepEqual(result, [
        { raw_label: "reading", value: 4, formatted: "4次", label: "行为:reading" },
        { label: "举手", value: 2, formatted: "2次" },
    ]);
});


test("buildTaskHighlight prefers tracking history text over fallback behavior summary", () => {
    const task = { status: "completed" };
    const summary = {
        display_metrics: {
            highlight: {
                history_text: "亮点：独立目标 3 个，峰值同屏 2 个",
            },
        },
        student_behavior_stats: { reading: 8 },
    };

    const result = buildTaskHighlight(
        task,
        summary,
        () => [{ label: "阅读", value: 8 }],
        (value) => String(value),
    );

    assert.equal(result, "亮点：独立目标 3 个，峰值同屏 2 个");
});


test("compareHistoryTasks uses tracking history_sort_value before raw detection totals", () => {
    const older = {
        task_id: "older",
        total_detections: 50,
        created_at: "2026-05-18T10:00:00Z",
    };
    const newer = {
        task_id: "newer",
        total_detections: 5,
        created_at: "2026-05-18T11:00:00Z",
    };
    const taskPayloadMap = {
        older: {
            display_metrics: {
                history_sort_value: 2,
            },
        },
        newer: {
            display_metrics: {
                history_sort_value: 6,
            },
        },
    };

    const result = compareHistoryTasks(older, newer, "detections", taskPayloadMap);

    assert.equal(result > 0, true);
});


test("buildBrowserWebcamTaskPayload preserves tracking metrics in local payload", () => {
    const session = {
        taskId: "webcam-1",
        processedFrames: 7,
        studentCounts: { reading: 2 },
        teacherCounts: { head: 1 },
        latestOriginalImage: "orig",
        latestAnnotatedImage: "anno",
    };
    const summaryLike = {
        status: "completed",
        total_detections: 3,
        average_confidence: 0.8,
        duration: 4.5,
        processed_frames: 7,
        display_metrics: {
            metric_mode: "tracking",
            cards: [{ label: "独立目标数", formatted: "3 个" }],
        },
        derived_metrics: {
            metric_mode: "tracking",
            unique_targets: 3,
        },
    };

    const payload = buildBrowserWebcamTaskPayload(session, summaryLike);

    assert.equal(payload.task_id, "webcam-1");
    assert.equal(payload.total_frames, 7);
    assert.deepEqual(payload.display_metrics, summaryLike.display_metrics);
    assert.deepEqual(payload.derived_metrics, summaryLike.derived_metrics);
    assert.notEqual(payload.display_metrics, summaryLike.display_metrics);
    assert.notEqual(payload.derived_metrics, summaryLike.derived_metrics);
});
