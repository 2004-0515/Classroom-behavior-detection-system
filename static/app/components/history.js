export function renderHistoryList({
    container,
    tasks,
    activeTaskId,
    selectedIds,
    taskPayloadMap,
    statusPill,
    formatTaskType,
    historyCapabilityBadge,
    truncate,
    formatFileLabel,
    formatRelativeTimeLabel,
    buildTaskHighlight,
    renderBehaviorTags,
    getTopBehaviors,
    formatNumber,
    formatStatus,
    onOpenTask,
    onToggleSelection,
}) {
    const getMetricLine = (task) => {
        const summary = taskPayloadMap[task.task_id] || {};
        const primary = summary.display_metrics?.primary_stat;
        if (primary?.label) {
            return `${primary.label} ${primary.formatted || primary.value || 0}`;
        }
        return `检测数 ${formatNumber(summary.total_detections ?? task.total_detections)}`;
    };
    container.innerHTML = tasks.length ? tasks.map((task) => `
        <div class="history-item ${String(activeTaskId) === String(task.task_id) ? "active" : ""} ${selectedIds.has(String(task.task_id)) ? "is-selected" : ""}" data-task-id="${task.task_id}">
            <div class="history-select-row">
                <label class="history-toggle">
                    <input class="history-select" type="checkbox" data-task-id="${task.task_id}" ${selectedIds.has(String(task.task_id)) ? "checked" : ""}>
                    <span>加入批量导出</span>
                </label>
                ${statusPill(task.status)}
            </div>
            <div class="panel-title-row"><strong>${formatTaskType(task.task_type)}</strong><span class="pill info">${historyCapabilityBadge(task, taskPayloadMap[task.task_id])}</span></div>
            <div>${truncate(formatFileLabel(task.file_name, "检测任务"), 20)}</div>
            <small>${formatRelativeTimeLabel(task.created_at)}</small>
            <div class="history-highlight">${buildTaskHighlight(task, taskPayloadMap[task.task_id])}</div>
            <div class="tag-row compact">${renderBehaviorTags(getTopBehaviors(taskPayloadMap[task.task_id], 2))}</div>
            <div class="history-meta">
                <span>${getMetricLine(task)}</span>
                <span>${taskPayloadMap[task.task_id]?.duration ? `${formatNumber(taskPayloadMap[task.task_id].duration, 1)} 秒` : formatStatus(task.status)}</span>
            </div>
        </div>
    `).join("") : `<div class="history-item">没有匹配的历史任务</div>`;

    [...container.querySelectorAll(".history-item[data-task-id]")].forEach((item) => item.addEventListener("click", () => onOpenTask?.(item.dataset.taskId)));
    [...container.querySelectorAll(".history-select-row")].forEach((row) => row.addEventListener("click", (event) => event.stopPropagation()));
    [...container.querySelectorAll(".history-select[data-task-id]")].forEach((input) => {
        input.addEventListener("click", (event) => event.stopPropagation());
        input.addEventListener("change", (event) => onToggleSelection?.(event.target.dataset.taskId, event.target.checked));
    });
}

export function renderHistorySelectionMeta({
    metaNode,
    exportButton,
    showcaseButton,
    clearButton,
    text,
    totalSelected,
    exporting,
}) {
    metaNode.textContent = text;
    exportButton.disabled = totalSelected === 0 || exporting;
    exportButton.textContent = exporting ? "正在导出..." : "导出选中报告";
    showcaseButton.disabled = exporting;
    clearButton.disabled = totalSelected === 0 || exporting;
}
