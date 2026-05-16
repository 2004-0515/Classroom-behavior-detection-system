export async function stopVideoTask(taskId, request) {
    if (!taskId) return false;
    await request(`/api/streams/video/${taskId}/stop`, { method: "POST" });
    return true;
}

export async function restoreStoppedTaskState({
    taskId,
    emptyTitle,
    emptyCopy,
    loadTaskPayload,
    applyResult,
    focusHistoryTask,
    setEmptyState,
}) {
    if (!taskId) {
        setEmptyState(emptyTitle, emptyCopy);
        return { restored: false, task: null };
    }
    const task = await loadTaskPayload(taskId);
    if (task) {
        applyResult(task);
        focusHistoryTask(taskId);
        return { restored: true, task };
    }
    setEmptyState(emptyTitle, emptyCopy);
    return { restored: false, task: null };
}
