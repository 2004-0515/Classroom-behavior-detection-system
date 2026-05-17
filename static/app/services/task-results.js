export async function loadTaskById(taskId, request) {
    const response = await request(`/api/tasks/${taskId}`);
    return response.data;
}

export async function loadVideoPollingSnapshot({
    taskId,
    request,
    normalizeTaskPayload,
}) {
    let task = await loadTaskById(taskId, request);
    let metrics = {};
    try {
        const metricsResponse = await request(`/api/streams/video/${taskId}/metrics`);
        metrics = metricsResponse.data;
    } catch (error) {
        if (task.status === "processing") {
            task = await loadTaskById(taskId, request);
            if (task.status === "processing") {
                throw error;
            }
        }
    }
    return resolveVideoPollingSnapshot({
        task,
        metrics,
        normalizeTaskPayload,
    });
}

export function buildAppliedTaskState({
    task,
    taskPayload,
    normalizeTaskPayload,
}) {
    return {
        currentTask: task,
        activeTaskPayload: normalizeTaskPayload(taskPayload),
        activeImageType: "annotated",
        activeAssetIndex: 0,
    };
}

export function resolveVideoPollingSnapshot({
    task,
    metrics,
    normalizeTaskPayload,
}) {
    const processing = task.status === "processing";
    const taskPayload = processing ? null : normalizeTaskPayload(task);
    return {
        processing,
        task,
        metrics,
        taskPayload,
        statePatch: processing
            ? { currentTask: task }
            : { currentTask: task, activeTaskPayload: taskPayload, activeAssetIndex: 0 },
    };
}

export function resolveWebcamPollingSnapshot({
    task,
    metrics,
    normalizeTaskPayload,
    currentActiveTaskPayload,
}) {
    const processing = task.status === "processing";
    const taskPayload = processing ? (currentActiveTaskPayload || null) : (normalizeTaskPayload(task) || currentActiveTaskPayload || null);
    return {
        processing,
        task,
        metrics,
        taskPayload,
        statePatch: {
            currentTask: task,
            ...(processing ? {} : { activeTaskPayload: taskPayload }),
        },
    };
}

export function resolveHistoryTaskFollowup(task) {
    if (!task || task.status !== "processing") return null;
    if (task.task_type === "video") return { poller: "video", taskId: task.task_id };
    if (task.task_type === "webcam") return { poller: "webcam", taskId: task.task_id };
    return null;
}
