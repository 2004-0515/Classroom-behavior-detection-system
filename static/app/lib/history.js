export function getFilteredHistoryTasks({
    recentTasks = [],
    taskPayloadMap = {},
    keyword = "",
    mode = "all",
    sort = "recent",
    showcaseOnly = false,
    isShowcaseTask,
    compareHistoryTasks,
}) {
    const loweredKeyword = String(keyword || "").trim().toLowerCase();
    return [...recentTasks]
        .filter((task) => {
            const probe = `${task.task_type || ""} ${task.file_name || ""}`.toLowerCase();
            const modeMatch = mode === "all" || task.task_type === mode;
            const showcaseMatch = !showcaseOnly || isShowcaseTask(task, taskPayloadMap[task.task_id]);
            return modeMatch && showcaseMatch && (!loweredKeyword || probe.includes(loweredKeyword));
        })
        .sort((left, right) => compareHistoryTasks(left, right, sort, taskPayloadMap));
}

export function isShowcaseTask(task, taskPayload, getTopBehaviors) {
    if (!task || task.status !== "completed") return false;
    const total = Number(taskPayload?.total_detections ?? task.total_detections ?? 0);
    return total > 0 || getTopBehaviors(taskPayload, 1).length > 0;
}

export function compareHistoryTasks(left, right, sort, taskPayloadMap = {}) {
    const leftSummary = taskPayloadMap[left.task_id] || {};
    const rightSummary = taskPayloadMap[right.task_id] || {};
    if (sort === "detections") {
        const leftMetric = Number(leftSummary.display_metrics?.history_sort_value ?? leftSummary.total_detections ?? left.total_detections ?? 0);
        const rightMetric = Number(rightSummary.display_metrics?.history_sort_value ?? rightSummary.total_detections ?? right.total_detections ?? 0);
        const diff = rightMetric - leftMetric;
        if (diff !== 0) return diff;
    }
    if (sort === "duration") {
        const diff = Number(rightSummary.duration || right.duration || 0) - Number(leftSummary.duration || left.duration || 0);
        if (diff !== 0) return diff;
    }
    return new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime();
}

export function getHistorySelectionMeta(tasks, selectedIds, exporting) {
    const visibleSelected = tasks.filter((task) => selectedIds.has(String(task.task_id))).length;
    const totalSelected = selectedIds.size;
    return {
        visibleSelected,
        totalSelected,
        exporting: Boolean(exporting),
        text: totalSelected ? `已选 ${totalSelected} 条任务${visibleSelected !== totalSelected ? `，当前筛选内可见 ${visibleSelected} 条` : ""}` : "未选择任务",
    };
}

export function toggleHistorySelectionIds(selectedIds, taskId, checked) {
    const next = new Set([...selectedIds].map(String));
    if (checked) next.add(String(taskId));
    else next.delete(String(taskId));
    return [...next];
}

export function getVisibleShowcaseTaskIds(tasks, taskPayloadMap, isShowcaseTaskFn) {
    return tasks
        .filter((task) => isShowcaseTaskFn(task, taskPayloadMap[task.task_id]))
        .map((task) => String(task.task_id));
}

export function getSpecialHistoryTask(tasks, kind) {
    if (!tasks.length) return null;
    if (kind === "detections") return tasks[0] || null;
    return [...tasks].sort((l, r) => new Date(r.created_at || 0) - new Date(l.created_at || 0))[0] || null;
}
