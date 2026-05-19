import test from "node:test";
import assert from "node:assert/strict";

import { renderHistoryList } from "./history.js";
import { renderTaskSummaryCards } from "./task-summary.js";


function makeFakeContainer() {
    return {
        innerHTML: "",
        querySelectorAll() {
            return [];
        },
    };
}


test("renderTaskSummaryCards prefers tracking display cards over fallback totals", () => {
    const node = makeFakeContainer();
    const summary = {
        total_detections: 9,
        display_metrics: {
            cards: [
                { label: "独立目标数", formatted: "3 个", accent: true },
                { label: "峰值同屏目标", formatted: "2 个" },
                { label: "有效检测帧", formatted: "5 帧" },
                { label: "有效帧覆盖率", formatted: "62.5%" },
            ],
        },
    };

    renderTaskSummaryCards({
        node,
        summary,
        currentMode: "video",
        formatTaskType: () => "视频检测",
    });

    assert.match(node.innerHTML, /独立目标数/);
    assert.match(node.innerHTML, /3 个/);
    assert.match(node.innerHTML, /峰值同屏目标/);
    assert.match(node.innerHTML, /有效帧覆盖率/);
    assert.doesNotMatch(node.innerHTML, /总检测数/);
});


test("renderHistoryList uses tracking primary stat instead of raw detection count", () => {
    const container = makeFakeContainer();
    const task = {
        task_id: "video-1",
        task_type: "video",
        status: "completed",
        file_name: "sample_video.mp4",
        created_at: "2026-05-18T22:00:00",
        total_detections: 9,
    };
    const taskPayloadMap = {
        "video-1": {
            duration: 4.2,
            total_detections: 9,
            display_metrics: {
                primary_stat: {
                    label: "独立目标数",
                    formatted: "3 个",
                },
            },
        },
    };

    renderHistoryList({
        container,
        tasks: [task],
        activeTaskId: "video-1",
        selectedIds: new Set(),
        taskPayloadMap,
        statusPill: (status) => `<span>${status}</span>`,
        formatTaskType: () => "视频检测",
        historyCapabilityBadge: () => "可展示",
        truncate: (text) => text,
        formatFileLabel: (name) => name,
        formatRelativeTimeLabel: () => "刚刚",
        buildTaskHighlight: () => "轨迹摘要",
        renderBehaviorTags: () => "",
        getTopBehaviors: () => [],
        formatNumber: (value, digits = 0) => Number(value).toFixed(digits),
        formatStatus: (status) => status,
        onOpenTask: () => {},
        onToggleSelection: () => {},
    });

    assert.match(container.innerHTML, /独立目标数 3 个/);
    assert.doesNotMatch(container.innerHTML, /检测数 9/);
});
